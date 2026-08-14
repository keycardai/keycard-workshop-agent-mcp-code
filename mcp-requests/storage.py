"""Storage for the request dashboard.

With REQUESTS_API_URL set (the workshop default), every operation goes to
the hosted requests API that the whole cohort shares. Without it, the
dashboard is process-local and empty at startup, so the repo runs offline.
"""

import os
import threading

import httpx


class DashboardError(Exception):
    """A dashboard failure the agent can relay in plain words."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DashboardError(f"{name} is not set; copy mcp-requests/.env.example to .env")
    return value


def _headers() -> dict:
    # TODO(ch02): the shared API key is the antipattern this workshop tears
    # out. Chapter 2 replaces this body with a per-call token exchange.
    return {"X-API-Key": _require("REQUESTS_API_KEY")}


def _api_url() -> str:
    return os.environ.get("REQUESTS_API_URL", "").strip().rstrip("/")


def _call(method: str, path: str, body: dict | None = None) -> dict | list:
    try:
        response = httpx.request(
            method, f"{_api_url()}{path}", json=body, headers=_headers(), timeout=15
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


def list_requests() -> list[dict]:
    if _api_url():
        return _call("GET", "/requests")
    with _local_lock:
        return [dict(row) for row in _local]


def get_request(request_id: str) -> dict:
    if _api_url():
        return _call("GET", f"/requests/{request_id}")
    with _local_lock:
        return dict(_local_find(request_id))


def create_request(fields: dict, identity: str | None = None) -> dict:
    if _api_url():
        return _call("POST", "/requests", body=fields)
    return _local_create(fields, identity)


def update_request(request_id: str, fields: dict) -> dict:
    if _api_url():
        return _call("PATCH", f"/requests/{request_id}", body=fields)
    with _local_lock:
        row = _local_find(request_id)
        row.update({k: v for k, v in fields.items() if v is not None})
        return dict(row)


def delete_request(request_id: str) -> dict:
    if _api_url():
        return _call("DELETE", f"/requests/{request_id}")
    with _local_lock:
        row = _local_find(request_id)
        _local.remove(row)
        return dict(row)
