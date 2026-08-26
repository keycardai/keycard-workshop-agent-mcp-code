import os

from keycardai.langchain import KeycardGrantMiddleware, KeycardIdentity
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from .config import Settings, require
from .tools.requests_queue import REQUEST_TOOLS

SYSTEM_PROMPT = (
    "You are the team's desk assistant. You can consult the environment "
    "directory, which describes the world you work in: its services, "
    "agents, resources, policies, runbooks, and recent changes. You can also work the "
    "team's request dashboard: file requests, look them up, move their status "
    "and priority, reassign them, and delete them. Requests can name any system, in the "
    "directory or not; take those names at face value rather than checking "
    "that they exist. People on the dashboard are identified by email, and "
    "workshop emails take the form firstname.lastname@{email_domain}, though a "
    "few may differ. When the user names a person instead of giving an "
    "email, work out their likely address and confirm it before writing, "
    "unless it already appears on the dashboard. Use the directory when the "
    "user asks about the environment itself, and only then: it holds no "
    "people or email addresses, so never search it to identify a person. "
    "Before filing a new request, list the dashboard and point out an "
    "identical open request instead of filing a duplicate. If a tool reports an "
    "authorization or ownership error, relay it to the user plainly; never "
    "retry it or invent data. Reply in simple markdown: short paragraphs, "
    "lists, bold, inline code, and links when they help. Never use markdown "
    "tables: the chat page does not render them; use lists instead."
)


@wrap_model_call
def _repair_thinking_blocks(request, handler):
    # langchain-anthropic (<= 1.4.8) merges a streamed thinking block that
    # holds a signature but no text into one with no "thinking" field, which
    # the API rejects on the turn's next model call. Restore the field;
    # empty is what the model produced.
    for message in request.messages:
        if not isinstance(message.content, list):
            continue
        for block in message.content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                block.setdefault("thinking", "")
    return handler(request)


def make_keycard_middleware(settings: Settings) -> KeycardGrantMiddleware:
    """Before each tool call, take the run's KeycardIdentity (the agent
    itself, or the signed-in user) to Keycard and mint a token for that
    tool's resource. Nothing is stored; every mint lands in the audit log.
    """
    return KeycardGrantMiddleware(
        zone_url=require(settings.keycard_zone_url, "KEYCARD_ZONE_URL"),
        client_id=require(settings.keycard_client_id, "KEYCARD_CLIENT_ID"),
        client_secret=require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET"),
        # Every tool is mapped explicitly; an unmapped tool gets no access.
        resources=[],
        tool_resources={
            "search_directory": [settings.directory_key_resource],
            "get_entry": [settings.directory_key_resource],
            **{name: [settings.requests_mcp] for name in REQUEST_TOOLS},
        },
        # A run with no identity pauses for sign-in; a missing grant pauses
        # for consent. As-itself runs never pause: no user to send anywhere.
        sign_in_url="/login",
        authorization_url=settings.keycard_zone_url,
    )


# Built on first use so a missing setting surfaces as a message, not an
# import-time crash. One instance per process is load-bearing: it owns a
# background event loop and a warm client cache, so building it per request
# would leak a thread per turn. It holds no identity; that arrives per run.
_keycard: KeycardGrantMiddleware | None = None


def shared_middleware(settings: Settings) -> KeycardGrantMiddleware:
    global _keycard
    if _keycard is None:
        _keycard = make_keycard_middleware(settings)
    return _keycard


def build_agent(
    llm: BaseChatModel,
    tools: list[BaseTool],
    identity: str | None = None,
    keycard: KeycardGrantMiddleware | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    # A hint for guessing addresses from names, not an allowlist.
    system_prompt = SYSTEM_PROMPT.format(
        email_domain=os.environ.get("EMAIL_DOMAIN", "").strip() or "example.com"
    )
    if identity:
        system_prompt += (
            f' The signed-in user is {identity}; '
            'read "me" and "my requests" as them.'
        )
    middleware = [keycard, _repair_thinking_blocks] if keycard else [_repair_thinking_blocks]
    return create_agent(
        llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        context_schema=KeycardIdentity,
        checkpointer=checkpointer,
    )
