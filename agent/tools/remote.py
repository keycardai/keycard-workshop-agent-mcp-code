"""One call to a remote MCP tool: a short-lived session, opened per call and
closed before the result returns. Credentials arrive from the caller; this
module neither requests nor stores them.
"""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError


def _leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for sub in exc.exceptions for leaf in _leaves(sub)]
    return [exc]


def call_mcp(url: str, tool_name: str, args: dict, credential: str | None = None) -> str:
    # The transport reports a refused call as a generic protocol error, so
    # the HTTP statuses are recorded on the way through and read on failure.
    statuses: list[int] = []

    async def _record(response) -> None:
        statuses.append(response.status_code)

    async def _run() -> str:
        headers = {"Authorization": f"Bearer {credential}"} if credential else None
        async with create_mcp_http_client(headers=headers) as http:
            http.event_hooks["response"].append(_record)
            async with streamable_http_client(url, http_client=http) as (read, write, *_):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, args)
        if result.is_error:
            # Tool failures arrive as a flagged result, not an exception.
            text = result.content[0].text if result.content else "unknown error"
            return f"The tool call failed: {text}"
        # An empty list serializes to zero content blocks, not "[]".
        return result.content[0].text if result.content else "[]"

    try:
        # The agent's tools are sync and each web request runs in its own
        # thread, so a private event loop per call is safe and simple.
        return asyncio.run(_run())
    except Exception as exc:
        # The transport runs on task groups, so failures arrive wrapped in
        # (sometimes nested) ExceptionGroups; classify by the leaves. Its
        # HTTP errors come from a vendored httpx, so match by module, not
        # by class.
        leaves = _leaves(exc)
        if 401 in statuses:
            return f"Authorization error: the MCP server at {url} refused the call (401)."
        refused = next((s for s in statuses if s >= 400), None)
        if refused is not None:
            return f"The MCP server at {url} returned {refused}."
        for leaf in leaves:
            if type(leaf).__module__.partition(".")[0] in ("httpx", "httpx2", "httpcore", "httpcore2"):
                return f"Could not reach the MCP server at {url}: {leaf}"
        for leaf in leaves:
            if isinstance(leaf, MCPError):
                # e.g. the server dropped or refused the session mid-call.
                return f"The MCP server at {url} ended the session: {leaf}"
        raise
