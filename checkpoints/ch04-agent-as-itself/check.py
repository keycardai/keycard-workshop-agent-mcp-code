"""Preflight for Chapter 3: verify each connection before going further."""

from collections.abc import Callable

import httpx
from keycardai.oauth import Client

from .config import Settings, load_settings, require
from .llm import get_llm


def main() -> int:
    settings = load_settings()
    results = [
        _check("LLM responds", _check_llm, settings),
        _check("Keycard discovery", _check_discovery, settings),
        _check("Application credentials present", _check_credentials, settings),
        _check("Requests MCP server reachable", _check_requests, settings),
    ]
    return 0 if all(results) else 1


def _check(label: str, fn: Callable[[Settings], None], settings: Settings) -> bool:
    try:
        fn(settings)
    except Exception as exc:
        print(f"FAIL  {label}: {exc}")
        return False
    print(f"PASS  {label}")
    return True


def _check_llm(settings: Settings) -> None:
    get_llm(settings).invoke("Reply with the word: pong")


def _check_discovery(settings: Settings) -> None:
    with Client(require(settings.keycard_zone_url, "KEYCARD_ZONE_URL")) as client:
        client.discover_server_metadata()


def _check_credentials(settings: Settings) -> None:
    # Presence only; the first tool call proves them.
    require(settings.keycard_client_id, "KEYCARD_CLIENT_ID")
    require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET")


def _check_requests(settings: Settings) -> None:
    # Any HTTP answer proves the server is up; a 401 means it's already protected.
    httpx.get(settings.requests_mcp)
    # Chapter 7's reviewer calls the API behind it directly; the URL is pre-filled.
    require(settings.requests_api_url, "REQUESTS_API_URL")
