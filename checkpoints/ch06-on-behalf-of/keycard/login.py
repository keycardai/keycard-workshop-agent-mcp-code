"""Browser sign-in: OAuth authorization code + PKCE, served by the agent itself.

The agent's web app owns the registered redirect URI: GET /login sends the
browser to Keycard, GET /callback receives the code and redeems it. Built
from the SDK's flow pieces: `keycardai.oauth.pkce.authenticate` runs its own
one-shot callback server (this app already is one), and the web-app pair in
`keycardai.oauth.pkce.web` takes a single RFC 8707 resource, while /login
below must name two (the agent resource for audience, the requests MCP for
consent).
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
        # The agent resource must be requested explicitly during authorization
        # AND code exchange (RFC 8707); it becomes the token's audience, and
        # only the app that provides that audience may exchange the token
        # onward, which Chapter 6 does. The requests MCP resource rides along
        # for consent only: naming it makes the consent screen ask again
        # whenever consent is missing, instead of trusting the zone to
        # notice a dependency change. The token stays audienced to the agent
        # resource alone; the code exchange below names only that.
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
        # Some denials render an error page on Keycard instead; those never
        # reach this route, and the message stays in the browser tab.
        return _error_page(f"Keycard returned an error: {error_description or error}")
    if _pending is None or state != _pending["state"]:
        # State proves this callback answers a sign-in this agent started.
        # Replays land here too: a finished attempt leaves no pending state.
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
    the browser. Both halves matter: the zone session is what lets the next
    sign-in skip the login (and any consent screen); ending it makes the next
    sign-in run the whole flow from the top.
    """
    store.clear()
    settings = load_settings()
    try:
        with Client(settings.keycard_zone_url) as client:
            end_session = client.discover_server_metadata().end_session_endpoint
    except (OAuthError, ConfigError):
        end_session = None
    if not end_session:
        # The agent side is signed out regardless; without the zone's logout
        # endpoint the browser keeps its zone session, so the next sign-in
        # may skip the login screen. Landing home keeps that failure soft.
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(end_session)


def _error_page(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<p>{html.escape(message)}</p><p><a href=\"/\">Back to chat</a></p>",
        status_code=400,
    )
