"""Browser sign-in: OAuth authorization code + PKCE, served by the agent itself.

The agent's web app owns the registered redirect URI: GET /login sends the
browser to Keycard, GET /callback receives the code and redeems it. The SDK's
web-app flow does the OAuth work in two calls around those routes; this file
only keeps what the SDK hands back between them.
"""

import html

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from keycardai.oauth import (
    AuthorizationDeniedError,
    Client,
    OAuthError,
    StateMismatchError,
)
from keycardai.oauth.exceptions import ConfigError
from keycardai.oauth.pkce import (
    AuthorizationRedirect,
    begin_authorization,
    complete_authorization,
)

from ..config import MissingConfig, load_settings, require
from .tokens import store

router = APIRouter()

# The sign-in attempt in flight: /login fills it, /callback consumes it.
# One slot only; starting a new sign-in invalidates the previous one.
_pending: AuthorizationRedirect | None = None


@router.get("/login")
async def login() -> Response:
    global _pending
    settings = load_settings()
    try:
        client_id = require(settings.keycard_client_id, "KEYCARD_CLIENT_ID")
        require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET")
        issuer = require(settings.keycard_zone_url, "KEYCARD_ZONE_URL")
        # Both resources are named during authorization (RFC 8707). The agent
        # resource comes first: it is the token's home audience, and only the
        # app providing that audience may exchange the token onward. The
        # requests MCP resource rides along so consent covers the resource
        # Chapter 6 exchanges the token for.
        resource = require(settings.agent_resource, "AGENT_RESOURCE")
        requests_mcp = require(settings.requests_mcp, "REQUESTS_MCP")
    except MissingConfig as exc:
        return _error_page(str(exc))

    try:
        # Discovers Keycard's endpoints, generates the PKCE pair and state,
        # and builds the authorization URL. The state and verifier come back
        # for this process to hold until the callback.
        _pending = await begin_authorization(
            client_id=client_id,
            issuer=issuer,
            redirect_uri=settings.redirect_uri,
            resources=[resource, requests_mcp],
            scopes=["openid", "email", "profile"],
        )
    except OAuthError as exc:
        return _error_page(
            f"Couldn't reach Keycard at {issuer} ({exc}). Check "
            "KEYCARD_ZONE_URL in agent/.env and your network, then try again."
        )
    return RedirectResponse(_pending.url)


@router.get("/callback")
async def callback(request: Request) -> Response:
    global _pending
    pending, _pending = _pending, None
    if pending is None:
        # Replays land here: a finished attempt leaves no pending state.
        return _error_page(
            "This sign-in didn't start from this agent. "
            "Go back to the chat page and sign in again."
        )

    settings = load_settings()
    try:
        # Checks the returned state against the stored one, then redeems the
        # code with the stored verifier. No resource is named here: the
        # token's audience was fixed when Keycard issued the code.
        token = await complete_authorization(
            callback_params=request.query_params,
            state=pending.state,
            code_verifier=pending.code_verifier,
            client_id=settings.keycard_client_id,
            client_secret=settings.keycard_client_secret,
            issuer=settings.keycard_zone_url,
            redirect_uri=settings.redirect_uri,
        )
    except AuthorizationDeniedError as exc:
        return _error_page(
            f"Keycard returned an error: {exc.error_description or exc.error}"
        )
    except StateMismatchError:
        # State proves this callback answers a sign-in this agent started.
        return _error_page(
            "This sign-in didn't start from this agent (state mismatch). "
            "Go back to the chat page and sign in again."
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
