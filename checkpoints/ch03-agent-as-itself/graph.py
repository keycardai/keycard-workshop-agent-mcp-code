import os

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

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
    # A streamed turn can leave a thinking block holding a signature but no
    # text: the model opened the block, wrote nothing, and signed it, and
    # langchain-anthropic (<= 1.4.8) merges those chunks into a block with no
    # "thinking" field at all, which the API then rejects when the turn's next
    # model call sends the conversation back. Restore the field; empty is
    # exactly what the model produced.
    for message in request.messages:
        if not isinstance(message.content, list):
            continue
        for block in message.content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                block.setdefault("thinking", "")
    return handler(request)


def build_agent(
    llm: BaseChatModel, tools: list[BaseTool], identity: str | None = None
) -> CompiledStateGraph:
    # A hint for guessing addresses from names, not an allowlist; read here
    # with a default because nothing else configures the prompt.
    system_prompt = SYSTEM_PROMPT.format(
        email_domain=os.environ.get("EMAIL_DOMAIN", "").strip() or "example.com"
    )
    if identity:
        system_prompt += (
            f' The signed-in user is {identity}; '
            'read "me" and "my requests" as them.'
        )
    return create_agent(
        llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[_repair_thinking_blocks],
    )
