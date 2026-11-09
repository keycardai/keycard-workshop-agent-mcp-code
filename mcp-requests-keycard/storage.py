"""Storage for the request dashboard.

Every operation goes to the hosted requests API that the whole cohort
shares; REQUESTS_API_URL in .env says where.
"""

import os

import httpx


class DashboardError(Exception):
    """A dashboard failure the agent can relay in plain words."""


def _authorization_needed() -> str:
    """The consent-class exchange failure, phrased for the person who can fix
    it: signing in to the agent again is the remedy, so say that plainly."""
    return (
        "The token exchange for the requests API was refused because your "
        "authorization is missing or expired. Sign in to the agent again and "
        "approve access, then retry. If it keeps happening, flag an instructor."
    )


def _headers(credential: str | None) -> dict:
    # Each tool's grant already minted this per-call credential; storage only
    # has to present it. Nothing is stored.
    return {"Authorization": f"Bearer {credential}"} if credential else {}


def _api_url() -> str:
    url = os.environ.get("REQUESTS_API_URL", "").strip().rstrip("/")
    if not url:
        raise DashboardError("REQUESTS_API_URL is not set; copy the value from your instructors into mcp-requests/.env")
    return url


def _call(method: str, path: str, credential: str | None, body: dict | None = None) -> dict | list:
    try:
        response = httpx.request(
            method, f"{_api_url()}{path}", json=body, headers=_headers(credential), timeout=15
        )
    except httpx.HTTPError as exc:
        raise DashboardError(f"Could not reach the requests API at {_api_url()}: {exc}") from exc
    if response.status_code == 401:
        challenge = response.headers.get("www-authenticate", "")
        try:
            detail = response.json().get("detail", "")
        except ValueError:
            detail = ""
        raise DashboardError(
            f"The requests API refused the credentials (401). {challenge} {detail}".strip()
        )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise DashboardError(str(detail)[:300])
    return response.json()


def list_requests(credential: str | None = None) -> list[dict]:
    return _call("GET", "/requests", credential)


def get_request(request_id: str, credential: str | None = None) -> dict:
    return _call("GET", f"/requests/{request_id}", credential)


def create_request(fields: dict, identity: str | None = None, credential: str | None = None) -> dict:
    # The token names the user by id, not email, so the requester travels
    # in the body; the API records it as the row's owner.
    return _call("POST", "/requests", credential, body={**fields, "requester": identity or ""})


def update_request(request_id: str, fields: dict, credential: str | None = None) -> dict:
    return _call("PATCH", f"/requests/{request_id}", credential, body=fields)


def delete_request(request_id: str, credential: str | None = None) -> dict:
    return _call("DELETE", f"/requests/{request_id}", credential)
