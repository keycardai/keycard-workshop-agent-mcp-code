import time

from keycardai.oauth import Client
from keycardai.oauth.exceptions import OAuthError
from keycardai.oauth.utils.jwt import get_claims

from ..config import load_settings


class NotLoggedIn(Exception):
    pass


class TokenStore:
    """The signed-in user's token, in memory only. Per-call resource
    credentials are minted by the grant middleware, never stored here.
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
        # Capture before the expiry check: claims() clears the slot on
        # expiry, and a concurrent request may hit that first.
        token = self._user_token
        if token is None:
            raise NotLoggedIn("No user is signed in. Sign in first.")
        if self.claims() is None:
            raise NotLoggedIn("Your session expired. Sign in again.")
        return token

    def claims(self) -> dict | None:
        # Expiry clears the token here so /me flips to signed-out too, not
        # just the tools' exchange path.
        if self._user_token is None:
            return None
        claims = get_claims(self._user_token)
        if claims.get("exp", 0) <= time.time():
            self._user_token = None
            return None
        return claims

    def _userinfo_claims(self) -> dict:
        """Identity claims from the zone's userinfo endpoint: zone access
        tokens are authorization-only, so email and groups live behind
        userinfo. Cached per token; a failed fetch retries next call.
        """
        token = self._user_token
        if token is None:
            return {}
        if self._userinfo is not None and self._userinfo[0] == token:
            return self._userinfo[1]
        settings = load_settings()
        try:
            with Client(settings.keycard_zone_url) as client:
                response = client.userinfo(token)
        except OAuthError:
            # Identity display degrades to the sub; nothing else breaks.
            return {}
        self._userinfo = (token, response.claims)
        return response.claims

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


# The process's single user session: the sign-in callback fills it, the grant
# middleware exchanges from it.
store = TokenStore()
