"""Chapter 7: the agent reviews each request you file, acting as itself."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from .config import Settings


def review_filed(
    new_messages: list[BaseMessage],
    records: list[dict],
    llm: BaseChatModel,
    settings: Settings,
) -> tuple[list[dict], str]:
    # TODO(ch07): review what this turn filed, as the agent itself. Until
    # Chapter 7 this changes nothing and adds no note to the reply.
    return records, ""
