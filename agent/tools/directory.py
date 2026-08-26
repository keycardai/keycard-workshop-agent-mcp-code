"""Tools for the directory MCP server.

The directory is hosted for the whole workshop and holds org data, not user
data. Compare tools/requests_queue.py, where every call goes out on the
signed-in user's behalf.
"""

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
        # TODO(ch04): the whole authentication story is a shared key from
        # .env. Chapter 4 replaces it with a key the agent fetches from the
        # Keycard vault under its own identity, per call.
        return call_mcp(settings.directory_mcp, tool_name, args, settings.directory_key)

    return [search_directory, get_entry]
