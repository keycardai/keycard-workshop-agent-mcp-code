"""The requests MCP server: the team's shared queue of asks.

Protected with Keycard. Every call arrives with a delegated token naming the
real user, so the dashboard can enforce what the API key never could: you create
requests as yourself, the requester and assignee may move a request's status,
and only the requester may change its priority, delete it, or reassign it.
"""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from keycardai.fastmcp import AuthProvider
from keycardai.oauth import BasicAuth, Client
from keycardai.oauth.exceptions import OAuthError

import storage
from storage import DashboardError, _require

load_dotenv(Path(__file__).resolve().parent / ".env")

STATUSES = ("open", "in_progress", "done")

ZONE_URL = os.environ.get("KEYCARD_ZONE_URL", "").strip().rstrip("/")
if not ZONE_URL:
    raise SystemExit("KEYCARD_ZONE_URL is not set; copy mcp-requests/.env.example to .env")

# The audience is this server's URL + /mcp and must match the resource
# registered in Keycard byte-for-byte.
auth = AuthProvider(
    zone_url=ZONE_URL,
    mcp_server_name="Requests MCP Server",
    mcp_server_url="http://localhost:8300",
)
mcp = FastMCP("Requests MCP Server", auth=auth.get_remote_auth_provider())


def _caller() -> str:
    """The caller's stable identity. Zone access tokens are authorization-only
    (audience + scopes); the user's email lives behind the zone's userinfo
    endpoint, and it has to: the dashboard's rows carry emails, so ownership
    checks must compare like for like."""
    claims = get_access_token().claims or {}
    email = claims.get("email")
    if not email:
        try:
            email = _userinfo().get("email")
        except DashboardError:
            # Identity degrades to the sub rather than failing the whole call.
            email = None
    return email or claims.get("sub") or "unknown"


# The endpoint location is configuration and safe to cache; the answer is
# authorization data and never is.
_userinfo_endpoint: str | None = None


def _userinfo() -> dict:
    """Identity claims from the zone's userinfo endpoint. Userinfo answers
    only tokens minted for it, so the server first exchanges the delegated
    token it received for a userinfo credential (RFC 8693), the same
    per-call, user-as-subject exchange storage.py runs for the requests API.
    The endpoint URL doubles as the registered resource identifier."""
    global _userinfo_endpoint
    try:
        if _userinfo_endpoint is None:
            metadata = httpx.get(f"{ZONE_URL}/.well-known/openid-configuration").json()
            _userinfo_endpoint = metadata["userinfo_endpoint"]
        with Client(
            ZONE_URL,
            auth=BasicAuth(
                _require("REQUESTS_MCP_CLIENT_ID"),
                _require("REQUESTS_MCP_CLIENT_SECRET"),
            ),
        ) as client:
            minted = client.exchange_token(
                subject_token=get_access_token().token,
                resource=_userinfo_endpoint,
                scope="openid email",
            )
        response = httpx.get(
            _userinfo_endpoint,
            headers={"Authorization": f"Bearer {minted.access_token}"},
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, OAuthError, KeyError, ValueError) as exc:
        raise DashboardError(f"Could not fetch your identity from the zone: {exc}") from exc


def _forbidden(request_id: str, owner: str, caller: str, action: str) -> dict:
    return {
        "error": "forbidden",
        "detail": (
            f"{request_id} belongs to {owner or 'no one'}; you are {caller}. "
            f"You can only {action} your own requests."
        ),
    }


@mcp.tool
def list_requests() -> list[dict] | dict:
    """List every request on the team dashboard, with requester, assignee,
    priority, and status."""
    try:
        return storage.list_requests()
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool
def get_request(request_id: str) -> dict:
    """Look up one request by id, e.g. REQ-1042."""
    try:
        return storage.get_request(request_id)
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool
def create_request(title: str, priority: str = "normal", assignee: str = "") -> dict:
    """File a new request on the dashboard. Priority is low, normal, or high;
    assignee is an email address."""
    try:
        return storage.create_request(
            {"title": title, "priority": priority, "assignee": assignee},
            identity=_caller(),
        )
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool
def update_request_status(request_id: str, status: str) -> dict:
    """Move a request to a new status: open, in_progress, or done. Only the
    requester or the current assignee may do this."""
    if status not in STATUSES:
        return {"error": "invalid_status", "detail": f"status must be one of: {', '.join(STATUSES)}"}
    try:
        row = storage.get_request(request_id)
        caller = _caller()
        if caller not in (row.get("requester"), row.get("assignee")):
            return _forbidden(request_id, row.get("requester", ""), caller, "update")
        return storage.update_request(request_id, {"status": status})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool
def set_request_priority(request_id: str, priority: str) -> dict:
    """Change a request's priority: low, normal, or high. Only the requester
    may change it."""
    if priority not in ("low", "normal", "high"):
        return {"error": "invalid_priority", "detail": "priority must be one of: low, normal, high"}
    try:
        row = storage.get_request(request_id)
        caller = _caller()
        if row.get("requester") != caller:
            return _forbidden(request_id, row.get("requester", ""), caller, "reprioritize")
        return storage.update_request(request_id, {"priority": priority})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool
def delete_request(request_id: str) -> dict:
    """Delete a request from the dashboard. Only the requester may delete it."""
    try:
        row = storage.get_request(request_id)
        caller = _caller()
        if row.get("requester") != caller:
            return _forbidden(request_id, row.get("requester", ""), caller, "delete")
        # The marker tells consumers this row is gone, not updated; the
        # agent's panel drops it instead of folding it back in.
        return {**storage.delete_request(request_id), "deleted": True}
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool
def reassign_request(request_id: str, assignee: str) -> dict:
    """Reassign a request to someone else. Assignee is an email address.
    Only the requester may reassign it."""
    try:
        row = storage.get_request(request_id)
        caller = _caller()
        if row.get("requester") != caller:
            return _forbidden(request_id, row.get("requester", ""), caller, "reassign")
        return storage.update_request(request_id, {"assignee": assignee})
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8300)
