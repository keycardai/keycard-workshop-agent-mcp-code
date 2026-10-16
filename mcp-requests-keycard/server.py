"""The requests MCP server: the team's shared queue of asks.

Protected with Keycard. Every call arrives with a delegated token naming the
real user, so the dashboard can enforce what the API key never could: you create
requests as yourself, the requester and assignee may move a request's status,
and only the requester may change its priority, delete it, or reassign it.
"""

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from keycardai.mcp.server.auth import AccessContext, AuthProvider, ClientSecret
from keycardai.oauth import Client
from keycardai.oauth.exceptions import ConfigError, OAuthError
from keycardai.oauth.utils.jwt import get_claims
from mcp.server.mcpserver import Context, MCPServer

import storage
from storage import DashboardError, _authorization_needed

load_dotenv(Path(__file__).resolve().parent / ".env")

STATUSES = ("open", "in_progress", "done")


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set; copy mcp-requests/.env.example to .env")
    return value


ZONE_URL = _env("KEYCARD_ZONE_URL").rstrip("/")

# The resource this server exchanges the caller's token for; must match the
# identifier registered in Keycard byte-for-byte.
API = _env("REQUESTS_API_RESOURCE")

# The zone's userinfo endpoint doubles as a registered resource: granting it
# mints a credential that endpoint accepts. Discovered once at boot; the
# server can't verify tokens without the zone anyway.
try:
    with Client(ZONE_URL) as _client:
        _metadata = _client.discover_server_metadata()
except OAuthError as exc:
    raise SystemExit(f"Could not reach Keycard at {ZONE_URL} ({exc})") from exc
USERINFO = _metadata.userinfo_endpoint
if not USERINFO:
    raise SystemExit(f"{ZONE_URL} publishes no userinfo_endpoint; check KEYCARD_ZONE_URL")

# One AuthProvider does both jobs: it verifies the delegated token on the way
# in, and it holds the server's own credential for the exchanges each tool's
# grant() declares.
auth = AuthProvider(
    zone_url=ZONE_URL,
    mcp_server_name="Requests MCP Server",
    mcp_server_url="http://localhost:8300",
    # Accept only tokens minted for this server's registered resource.
    audience="http://localhost:8300/mcp",
    application_credential=ClientSecret(
        (_env("REQUESTS_MCP_CLIENT_ID"), _env("REQUESTS_MCP_CLIENT_SECRET"))
    ),
)
mcp = MCPServer("Requests MCP Server")


def _credential(access: AccessContext) -> str:
    """The minted requests-API credential. The grant already ran before the
    tool did; failures are recorded on the AccessContext, never raised.
    """
    error = access.get_error() or access.get_resource_error(API)
    if error is None:
        return access.access(API).access_token
    if error.get("code") in ("insufficient_authorization", "consent_required"):
        # A missing user grant is the one failure the caller can fix themselves.
        raise DashboardError(_authorization_needed())
    detail = error.get("description") or error.get("message") or error.get("code")
    raise DashboardError(f"Token exchange for the requests API failed: {detail}")


def _caller(access: AccessContext, ctx: Context) -> str:
    """The caller's email, for ownership checks against the dashboard's rows.
    Zone access tokens are authorization-only, so the email usually lives
    behind the zone's userinfo endpoint, reached with the credential the
    tool's grant minted."""
    user = ctx.request_context.request.user
    claims = get_claims(user.access_token) if getattr(user, "access_token", None) else {}
    if claims.get("email"):
        return claims["email"]
    try:
        if access.get_resource_error(USERINFO) is None:
            with Client(ZONE_URL) as client:
                info = client.userinfo(
                    access.access(USERINFO).access_token, metadata=_metadata
                )
            if info.claims.get("email"):
                return info.claims["email"]
    except (OAuthError, ConfigError):
        # Identity degrades to the sub instead of failing the whole call.
        pass
    return claims.get("sub") or "unknown"


def _forbidden(request_id: str, owner: str, caller: str, action: str) -> dict:
    return {
        "error": "forbidden",
        "detail": (
            f"{request_id} belongs to {owner or 'no one'}; you are {caller}. "
            f"You can only {action} your own requests."
        ),
    }


@mcp.tool()
@auth.grant(API)
def list_requests(*, access: AccessContext, ctx: Context) -> list[dict] | dict:
    """List every request on the team dashboard, with requester, assignee,
    priority, and status."""
    try:
        return storage.list_requests(_credential(access))
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
@auth.grant(API)
def get_request(request_id: str, *, access: AccessContext, ctx: Context) -> dict:
    """Look up one request by id, e.g. REQ-1042."""
    try:
        return storage.get_request(request_id, _credential(access))
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
@auth.grant([API, USERINFO])
def create_request(
    title: str, priority: str = "normal", assignee: str = "",
    *, access: AccessContext, ctx: Context,
) -> dict:
    """File a new request on the dashboard. Priority is low, normal, or high;
    assignee is an email address."""
    try:
        return storage.create_request(
            {"title": title, "priority": priority, "assignee": assignee},
            identity=_caller(access, ctx),
            credential=_credential(access),
        )
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
@auth.grant([API, USERINFO])
def update_request_status(
    request_id: str, status: str, *, access: AccessContext, ctx: Context
) -> dict:
    """Move a request to a new status: open, in_progress, or done. Only the
    requester or the current assignee may do this."""
    if status not in STATUSES:
        return {"error": "invalid_status", "detail": f"status must be one of: {', '.join(STATUSES)}"}
    try:
        credential = _credential(access)
        row = storage.get_request(request_id, credential)
        caller = _caller(access, ctx)
        if caller not in (row.get("requester"), row.get("assignee")):
            return _forbidden(request_id, row.get("requester", ""), caller, "update")
        return storage.update_request(request_id, {"status": status}, credential)
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
@auth.grant([API, USERINFO])
def set_request_priority(
    request_id: str, priority: str, *, access: AccessContext, ctx: Context
) -> dict:
    """Change a request's priority: low, normal, or high. Only the requester
    may change it."""
    if priority not in ("low", "normal", "high"):
        return {"error": "invalid_priority", "detail": "priority must be one of: low, normal, high"}
    try:
        credential = _credential(access)
        row = storage.get_request(request_id, credential)
        caller = _caller(access, ctx)
        if row.get("requester") != caller:
            return _forbidden(request_id, row.get("requester", ""), caller, "reprioritize")
        return storage.update_request(request_id, {"priority": priority}, credential)
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
@auth.grant([API, USERINFO])
def delete_request(request_id: str, *, access: AccessContext, ctx: Context) -> dict:
    """Delete a request from the dashboard. Only the requester may delete it."""
    try:
        credential = _credential(access)
        row = storage.get_request(request_id, credential)
        caller = _caller(access, ctx)
        if row.get("requester") != caller:
            return _forbidden(request_id, row.get("requester", ""), caller, "delete")
        # "deleted" marks the row gone, not updated; the agent's panel drops it.
        return {**storage.delete_request(request_id, credential), "deleted": True}
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


@mcp.tool()
@auth.grant([API, USERINFO])
def reassign_request(
    request_id: str, assignee: str, *, access: AccessContext, ctx: Context
) -> dict:
    """Reassign a request to someone else. Assignee is an email address.
    Only the requester may reassign it."""
    try:
        credential = _credential(access)
        row = storage.get_request(request_id, credential)
        caller = _caller(access, ctx)
        if row.get("requester") != caller:
            return _forbidden(request_id, row.get("requester", ""), caller, "reassign")
        return storage.update_request(request_id, {"assignee": assignee}, credential)
    except DashboardError as exc:
        return {"error": "dashboard_error", "detail": str(exc)}


if __name__ == "__main__":
    uvicorn.run(auth.app(mcp), host="127.0.0.1", port=8300, log_level="warning")
