"""Tools for the directory MCP server.

The directory is hosted for the whole workshop and holds org data, not user
data, so the agent asks as itself: a client credentials grant with the
application's own identity releases the directory key from the Keycard vault,
per call. Compare tools/requests_queue.py, where a user is in the chain.
"""

from keycardai.oauth import BasicAuth, Client
from keycardai.oauth.exceptions import OAuthError, OAuthProtocolError
from langchain_core.tools import BaseTool, tool

from ..config import MissingConfig, Settings, require
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

    def _credential() -> str:
        # The agent's own identity, proven with its client credentials; the
        # vault releases the directory key to it per call, and every retrieval
        # lands in the audit log. Nothing is stored.
        with Client(
            require(settings.keycard_zone_url, "KEYCARD_ZONE_URL"),
            auth=BasicAuth(
                require(settings.keycard_client_id, "KEYCARD_CLIENT_ID"),
                require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET"),
            ),
        ) as client:
            response = client.client_credentials_grant(
                resource=require(settings.directory_key_resource, "DIRECTORY_KEY_RESOURCE")
            )
        return response.access_token

    def _call(tool_name: str, args: dict) -> str:
        try:
            credential = _credential()
        except MissingConfig as exc:
            return f"Authorization error: {exc}"
        except OAuthProtocolError as exc:
            if exc.error == "invalid_target":
                return (
                    f"Authorization error: Keycard doesn't recognize the resource "
                    f"{settings.directory_key_resource!r}. DIRECTORY_KEY_RESOURCE must "
                    "match the identifier registered in Keycard byte-for-byte."
                )
            return f"Authorization error: Keycard refused the credential request ({exc.error})."
        except OAuthError as exc:
            return f"Authorization error: could not reach Keycard ({exc})."
        return call_mcp(settings.directory_mcp, tool_name, args, credential)

    return [search_directory, get_entry]
