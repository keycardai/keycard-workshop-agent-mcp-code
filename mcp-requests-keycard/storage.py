"""Storage for the request dashboard.

With REQUESTS_API_URL set (the workshop default), every operation goes to
the hosted requests API that the whole cohort shares. Without it, the
dashboard is process-local and empty at startup, so the repo runs offline.
"""

import os
import threading
from urllib.parse import quote, urlencode

import httpx


class DashboardError(Exception):
    """A dashboard failure the agent can relay in plain words."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DashboardError(f"{name} is not set; copy mcp-requests/.env.example to .env")
    return value


def _authorization_needed() -> str:
    """The consent-class exchange failure, phrased for the person who can fix
    it: only an interactive authorization can create or revive the caller's
    grant, so the error carries the authorizer link when one is configured.
    """
    message = (
        "The requests API isn't authorized to act on your behalf yet, or the "
        "authorization expired."
    )
    base = os.environ.get("AUTHORIZER_URL", "").strip().rstrip("/")
    if not base:
        return (
            message + " Ask an instructor about the authorizer page, then "
            "refresh the dashboard or try again."
        )
    # Name the zone, client id, and resource explicitly instead of leaning on
    # the page's baked-in defaults.
    query = [
        ("zone", _require("KEYCARD_ZONE_URL")),
        ("client_id", os.environ.get("AUTHORIZER_CLIENT_ID", "").strip()),
        ("resource", _require("REQUESTS_API_RESOURCE")),
    ]
    link = f"{base}/?{urlencode([(k, v) for k, v in query if v], quote_via=quote)}"
    # The link goes last with nothing after it: renderers pull trailing
    # punctuation into URLs, and a stray comma joins the resource identifier.
    return (
        f"{message} Refresh the dashboard or send your request again after "
        f"authorizing access here: {link}"
    )


def _headers(credential: str | None) -> dict:
    # Each tool's grant already minted this per-call credential; storage only
    # has to present it. Nothing is stored.
    return {"Authorization": f"Bearer {credential}"} if credential else {}


def _api_url() -> str:
    return os.environ.get("REQUESTS_API_URL", "").strip().rstrip("/")


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


# The offline dashboard: same shape as the API's rows, empty until someone
# creates a request. A lock keeps concurrent tool calls consistent.
_local: list[dict] = []
_local_lock = threading.Lock()
_local_seq = 1000


def _local_create(fields: dict, identity: str | None) -> dict:
    global _local_seq
    with _local_lock:
        _local_seq += 1
        row = {
            "id": f"REQ-{_local_seq}",
            "title": fields["title"],
            "description": fields.get("description", ""),
            "requester": identity or "api-key",
            "assignee": fields.get("assignee", ""),
            "priority": fields.get("priority", "normal"),
            "status": "open",
            "due": fields.get("due"),
            "created_at": "",
        }
        _local.append(row)
        return row


def _local_find(request_id: str) -> dict:
    for row in _local:
        if row["id"] == request_id:
            return row
    raise DashboardError(f"{request_id} does not exist (already deleted?).")


def list_requests(credential: str | None = None) -> list[dict]:
    if _api_url():
        return _call("GET", "/requests", credential)
    with _local_lock:
        return [dict(row) for row in _local]


def get_request(request_id: str, credential: str | None = None) -> dict:
    if _api_url():
        return _call("GET", f"/requests/{request_id}", credential)
    with _local_lock:
        return dict(_local_find(request_id))


def create_request(fields: dict, identity: str | None = None, credential: str | None = None) -> dict:
    if _api_url():
        return _call("POST", "/requests", credential, body=fields)
    return _local_create(fields, identity)


def update_request(request_id: str, fields: dict, credential: str | None = None) -> dict:
    if _api_url():
        return _call("PATCH", f"/requests/{request_id}", credential, body=fields)
    with _local_lock:
        row = _local_find(request_id)
        row.update({k: v for k, v in fields.items() if v is not None})
        return dict(row)


def delete_request(request_id: str, credential: str | None = None) -> dict:
    if _api_url():
        return _call("DELETE", f"/requests/{request_id}", credential)
    with _local_lock:
        row = _local_find(request_id)
        _local.remove(row)
        return dict(row)
