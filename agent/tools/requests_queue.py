"""Tools for the requests MCP server.

The dashboard is user data, so every call is meant to go out on the
signed-in user's behalf: the user's token is exchanged for a credential
minted for the dashboard (RFC 8693), one per call, never stored.
"""

from langchain_core.tools import BaseTool, tool

from ..config import Settings
from .remote import call_mcp

# The tools the data panel renders from; web.py folds tool output with these
# names into the request queue view.
REQUEST_TOOLS = (
    "list_requests",
    "get_request",
    "create_request",
    "update_request_status",
    "set_request_priority",
    "delete_request",
    "reassign_request",
)


def make_request_tools(settings: Settings) -> list[BaseTool]:
    @tool
    def list_requests() -> str:
        """List every request on the team dashboard, with requester, assignee,
        priority, and status."""
        return _call("list_requests", {})

    @tool
    def get_request(request_id: str) -> str:
        """Look up one request by id, e.g. REQ-1042."""
        return _call("get_request", {"request_id": request_id})

    @tool
    def create_request(
        title: str, description: str = "", priority: str = "normal", assignee: str = ""
    ) -> str:
        """File a new request on the dashboard. Title is a short label, a few
        words naming what is asked for; description says what is needed and
        why, in the user's own terms. Priority is low, normal, or high.
        assignee is an email address, or empty to leave it unassigned; if the
        user gives a name instead, resolve it to an email and confirm before
        filing, and never file an invented address. If the user hasn't said
        why, ask before filing, and never invent a reason."""
        return _call(
            "create_request",
            {"title": title, "description": description, "priority": priority, "assignee": assignee},
        )

    @tool
    def update_request_status(request_id: str, status: str) -> str:
        """Move a request to a new status: open, in_progress, or done."""
        return _call("update_request_status", {"request_id": request_id, "status": status})

    @tool
    def set_request_priority(request_id: str, priority: str) -> str:
        """Change a request's priority: low, normal, or high."""
        return _call("set_request_priority", {"request_id": request_id, "priority": priority})

    @tool
    def delete_request(request_id: str) -> str:
        """Delete a request from the dashboard."""
        return _call("delete_request", {"request_id": request_id})

    @tool
    def reassign_request(request_id: str, assignee: str) -> str:
        """Reassign a request to someone else. assignee is an email address.
        If the user gives a name, resolve it to an email and confirm before
        reassigning, and never invent one."""
        return _call("reassign_request", {"request_id": request_id, "assignee": assignee})

    def _call(tool_name: str, args: dict) -> str:
        # TODO(ch06): the agent presents nothing here. Chapter 6 exchanges
        # the signed-in user's token for a credential minted for the dashboard.
        return call_mcp(settings.requests_mcp, tool_name, args)

    return [
        list_requests,
        get_request,
        create_request,
        update_request_status,
        set_request_priority,
        delete_request,
        reassign_request,
    ]
