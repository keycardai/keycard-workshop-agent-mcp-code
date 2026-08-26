"""Browser sign-in: OAuth authorization code + PKCE, served by the agent itself.

The agent's web app owns the registered redirect URI: GET /login sends the
browser to Keycard, GET /callback receives the code and redeems it. Built
from the SDK's flow pieces rather than its ready-made flows, which run their
own callback server or take a single RFC 8707 resource; /login must name two.
"""

import html
import secrets

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from keycardai.oauth import BasicAuth, Client, build_authorize_url
from keycardai.oauth.exceptions import ConfigError, OAuthError
from keycardai.oauth.utils.pkce import PKCEGenerator

from ..config import MissingConfig, load_settings, require
from .tokens import store

router = APIRouter()

# The sign-in attempt in flight: /login fills it, /callback consumes it.
# One slot only; starting a new sign-in invalidates the previous one.
_pending: dict | None = None


@router.get("/login")
def login() -> Response:
    global _pending
    settings = load_settings()
    try:
        client_id = require(settings.keycard_client_id, "KEYCARD_CLIENT_ID")
        client_secret = require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET")
        issuer = require(settings.keycard_zone_url, "KEYCARD_ZONE_URL")
        # The agent resource must be named during authorization AND code
        # exchange (RFC 8707): it becomes the token's audience, and only the
        # app providing that audience may exchange the token onward. The
        # requests MCP resource rides along for consent only; the token stays
        # audienced to the agent resource alone.
        resource = require(settings.agent_resource, "AGENT_RESOURCE")
        requests_mcp = require(settings.requests_mcp, "REQUESTS_MCP")
    except MissingConfig as exc:
        return _error_page(str(exc))

    try:
        with Client(issuer, auth=BasicAuth(client_id, client_secret)) as client:
            metadata = client.discover_server_metadata()
    except OAuthError as exc:
        return _error_page(
            f"Couldn't reach Keycard at {issuer} ({exc}). Check "
            "KEYCARD_ZONE_URL in agent/.env and your network, then try again."
        )
    pkce = PKCEGenerator().generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    _pending = {"verifier": pkce.code_verifier, "state": state}
    url = build_authorize_url(
        metadata.authorization_endpoint,
        client_id=client_id,
        redirect_uri=settings.redirect_uri,
        pkce=pkce,
        resources=[resource, requests_mcp],
        scope="openid email profile",
        state=state,
    )
    return RedirectResponse(url)


@router.get("/callback")
def callback(
    code: str = "", state: str = "", error: str = "", error_description: str = ""
) -> Response:
    global _pending
    if error:
        return _error_page(f"Keycard returned an error: {error_description or error}")
    if _pending is None or state != _pending["state"]:
        # State proves this callback answers a sign-in this agent started;
        # replays land here too, since a finished attempt leaves no pending state.
        return _error_page(
            "This sign-in didn't start from this agent (state mismatch). "
            "Go back to the chat page and sign in again."
        )
    pending, _pending = _pending, None

    settings = load_settings()
    try:
        with Client(
            settings.keycard_zone_url,
            auth=BasicAuth(settings.keycard_client_id, settings.keycard_client_secret),
        ) as client:
            token = client.exchange_authorization_code(
                code=code,
                redirect_uri=settings.redirect_uri,
                code_verifier=pending["verifier"],
                client_id=settings.keycard_client_id,
                resource=settings.agent_resource,
            )
    except OAuthError as exc:
        return _error_page(
            f"Token exchange failed ({exc}). Check KEYCARD_CLIENT_ID and "
            "KEYCARD_CLIENT_SECRET in agent/.env."
        )
    store.set_user_token(token.access_token)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout() -> Response:
    """Sign out fully: drop the agent's token, then end the zone session in
    the browser, so the next sign-in runs the whole flow from the top.
    """
    store.clear()
    settings = load_settings()
    try:
        with Client(settings.keycard_zone_url) as client:
            end_session = client.discover_server_metadata().end_session_endpoint
    except (OAuthError, ConfigError):
        end_session = None
    if not end_session:
        # The agent side is signed out regardless; the browser keeps its zone
        # session, so the next sign-in may skip the login screen.
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(end_session)


def _error_page(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<p>{html.escape(message)}</p><p><a href=\"/\">Back to chat</a></p>",
        status_code=400,
    )
