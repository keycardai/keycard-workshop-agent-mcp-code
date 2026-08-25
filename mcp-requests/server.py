"""The requests MCP server: the team's shared queue of asks.

Chapter 2 protects this server with Keycard and pushes the caller's identity
through to the dashboard. Until then it is wide open: anyone can create, change,
or delete anyone's requests, and the dashboard attributes it all to the API key.
"""

from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

import storage
from storage import DashboardError

load_dotenv(Path(__file__).resolve().parent / ".env")

STATUSES = ("open", "in_progress", "done")

# TODO(ch02): protect this server with Keycard (the workshop guide has the
# AuthProvider block to paste).
mcp = MCPServer("Requests MCP Server")


@mcp.tool()
def list_requests() -> list[dict] | dict:
    """List every request on the team dashboard, with requester, assignee,
    priority, and status."""
    try:
        return storage.list_requests()
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
def get_request(request_id: str) -> dict:
    """Look up one request by id, e.g. REQ-1042."""
    try:
        return storage.get_request(request_id)
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
def create_request(title: str, priority: str = "normal", assignee: str = "") -> dict:
    """File a new request on the dashboard. Priority is low, normal, or high;
    assignee is an email address."""
    try:
        return storage.create_request({"title": title, "priority": priority, "assignee": assignee})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
def update_request_status(request_id: str, status: str) -> dict:
    """Move a request to a new status: open, in_progress, or done."""
    if status not in STATUSES:
        return {"error": "invalid_status", "detail": f"status must be one of: {', '.join(STATUSES)}"}
    try:
        return storage.update_request(request_id, {"status": status})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
def set_request_priority(request_id: str, priority: str) -> dict:
    """Change a request's priority: low, normal, or high."""
    if priority not in ("low", "normal", "high"):
        return {"error": "invalid_priority", "detail": "priority must be one of: low, normal, high"}
    try:
        return storage.update_request(request_id, {"priority": priority})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
def delete_request(request_id: str) -> dict:
    """Delete a request from the dashboard."""
    try:
        # The marker tells consumers this row is gone, not updated; the
        # agent's panel drops it instead of folding it back in.
        return {**storage.delete_request(request_id), "deleted": True}
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
def reassign_request(request_id: str, assignee: str) -> dict:
    """Reassign a request to someone else. Assignee is an email address."""
    try:
        return storage.update_request(request_id, {"assignee": assignee})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


if __name__ == "__main__":
    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8300, log_level="warning")
