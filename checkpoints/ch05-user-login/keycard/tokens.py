import time

import httpx
from keycardai.oauth import BasicAuth, Client
from keycardai.oauth.exceptions import OAuthProtocolError
from keycardai.oauth.utils.jwt import get_claims

from ..config import Settings, load_settings, require

# Error codes that mean "consent is missing or expired"; the user can
# fix these by signing in again. A policy `access_denied` is deliberately not
# here: re-authenticating won't change the decision.
_CONSENT_CODES = {"insufficient_authorization", "consent_required"}


class NotLoggedIn(Exception):
    pass


class ExchangeDenied(Exception):
    pass


class TokenStore:
    """Holds the signed-in user's token, in memory only. Exchanged
    credentials are never stored; request one per call with `exchange()`.
    """

    def __init__(self) -> None:
        self._user_token: str | None = None
        self._userinfo: tuple[str, dict] | None = None  # (token, claims)

    def set_user_token(self, token: str) -> None:
        self._user_token = token

    def clear(self) -> None:
        self._user_token = None
        self._userinfo = None

    @property
    def user_token(self) -> str:
        # Capture before the expiry check: claims() clears the slot when the
        # token expires, and a concurrent request may hit that first.
        token = self._user_token
        if token is None:
            raise NotLoggedIn("No user is signed in. Sign in first.")
        if self.claims() is None:
            raise NotLoggedIn("Your session expired. Sign in again.")
        return token

    def claims(self) -> dict | None:
        # Expiry clears the token here so the chat page's /me check flips to
        # signed-out too, not just the tools' exchange path.
        if self._user_token is None:
            return None
        claims = get_claims(self._user_token)
        if claims.get("exp", 0) <= time.time():
            self._user_token = None
            return None
        return claims

    def _userinfo_claims(self) -> dict:
        """Identity claims from the zone's userinfo endpoint. Zone access
        tokens are authorization-only (audience + scopes); who the user is
        (email, groups) lives behind userinfo. Cached per token; a failed
        fetch isn't cached, so the next call retries.
        """
        token = self._user_token
        if token is None:
            return {}
        if self._userinfo is not None and self._userinfo[0] == token:
            return self._userinfo[1]
        settings = load_settings()
        try:
            metadata = httpx.get(
                f"{settings.keycard_zone_url}/.well-known/openid-configuration",
                timeout=10,
            ).json()
            response = httpx.get(
                metadata["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            response.raise_for_status()
        except (httpx.HTTPError, KeyError, ValueError):
            # Identity display degrades to the sub; nothing else breaks.
            return {}
        claims = response.json()
        self._userinfo = (token, claims)
        return claims

    def identity(self) -> str:
        claims = self.claims() or {}
        return (
            claims.get("email")
            or self._userinfo_claims().get("email")
            or claims.get("sub")
            or "unknown"
        )

    def groups(self) -> list[str]:
        claims = self.claims() or {}
        groups = claims.get("groups") or self._userinfo_claims().get("groups", [])
        return groups if isinstance(groups, list) else [groups]


# The process's single user session: the sign-in callback fills it, tools
# exchange from it.
store = TokenStore()


def exchange(settings: Settings, resource: str) -> str:
    """Exchange the user's token for a short-lived credential scoped to
    `resource` (RFC 8693).
    """
    with Client(
        require(settings.keycard_zone_url, "KEYCARD_ZONE_URL"),
        auth=BasicAuth(
            require(settings.keycard_client_id, "KEYCARD_CLIENT_ID"),
            require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET"),
        ),
    ) as client:
        try:
            response = client.exchange_token(
                subject_token=store.user_token,
                resource=resource,
            )
        except OAuthProtocolError as exc:
            if exc.error in _CONSENT_CODES:
                raise NotLoggedIn(
                    "Consent for this resource is missing or expired. "
                    "Sign in again and approve access."
                ) from exc
            if exc.error == "access_denied":
                raise ExchangeDenied(
                    "Keycard's policy denied this request. Signing in again "
                    "won't change that. Check who you're signed in as (the "
                    "header of the chat page) and flag an instructor."
                ) from exc
            if exc.error == "invalid_target":
                raise ExchangeDenied(
                    f"Keycard doesn't recognize the resource {resource!r}. "
                    "REQUESTS_MCP must match the identifier registered in "
                    "Keycard byte-for-byte."
                ) from exc
            raise
    return response.access_token
