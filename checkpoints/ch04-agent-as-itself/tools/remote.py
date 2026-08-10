"""One call to a remote MCP tool: a short-lived session, opened per call and
closed before the result returns. Credentials arrive from the caller; this
module neither requests nor stores them.
"""

import asyncio

import httpx
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import McpError


def call_mcp(url: str, tool_name: str, args: dict, credential: str | None = None) -> str:
    async def _run() -> str:
        auth = BearerAuth(credential) if credential else None
        async with Client(url, auth=auth) as client:
            result = await client.call_tool(tool_name, args)
            # An empty list serializes to zero content blocks, not "[]".
            return result.content[0].text if result.content else "[]"

    try:
        # The agent's tools are sync and each web request runs in its own
        # thread, so a private event loop per call is safe and simple.
        return asyncio.run(_run())
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            return f"Authorization error: the MCP server at {url} refused the call (401)."
        return f"The MCP server at {url} returned {exc.response.status_code}."
    except httpx.HTTPError as exc:
        return f"Could not reach the MCP server at {url}: {exc}"
    except RuntimeError as exc:
        # fastmcp surfaces connect failures as a plain RuntimeError, not an httpx error.
        return f"Could not reach the MCP server at {url}: {exc}"
    except ToolError as exc:
        return f"The tool call failed: {exc}"
    except McpError as exc:
        # e.g. "Session terminated": the server dropped the session mid-call.
        return f"The MCP server at {url} ended the session: {exc}"
