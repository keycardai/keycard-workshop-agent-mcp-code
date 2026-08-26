"""Tools for the directory MCP server.

The directory is hosted for the whole workshop and holds org data, not user
data. Compare tools/requests_queue.py, where every call goes out on the
signed-in user's behalf.
"""

from keycardai.langchain import get_access_context
from langchain_core.tools import BaseTool, tool

from ..config import Settings
from .remote import call_mcp


def make_directory_tools(settings: Settings) -> list[BaseTool]:
    @tool
    def search_directory(query: str) -> str:
        """Search the environment directory by keyword. Entries describe the
        workshop world: its services, agents, resources, policies, runbooks,
        and recent changes."""
        return _call("search_directory", {"query": query})

    @tool
    def get_entry(entry_id: str) -> str:
        """Look up one directory entry by its id, e.g. requests-api or
        rb-401-vs-403."""
        return _call("get_entry", {"entry_id": entry_id})

    def _call(tool_name: str, args: dict) -> str:
        # The middleware already asked Keycard before this ran; failures are
        # recorded on the AccessContext, not raised.
        try:
            access = get_access_context()
        except RuntimeError:
            return (
                "Authorization error: no grant middleware is wired into "
                "this run, so there is no identity to act under. Chapter 5 "
                "wires it into chat; `python -m agent brief` already runs "
                "with it."
            )
        if access.has_error():
            return f"Authorization error: {access.get_error()['message']}"
        error = access.get_resource_error(settings.directory_key_resource)
        if error is not None:
            if error.get("code") == "invalid_target":
                return (
                    f"Authorization error: Keycard doesn't recognize the resource "
                    f"{settings.directory_key_resource!r}. DIRECTORY_KEY_RESOURCE must "
                    "match the identifier registered in Keycard byte-for-byte."
                )
            detail = error.get("description") or error.get("message")
            return f"Authorization error: Keycard refused the credential request ({detail})."
        credential = access.access(settings.directory_key_resource).access_token
        return call_mcp(settings.directory_mcp, tool_name, args, credential)

    return [search_directory, get_entry]
