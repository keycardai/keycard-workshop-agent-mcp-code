from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from .config import MissingConfig, Settings, require


def get_llm(settings: Settings) -> BaseChatModel:
    model = require(settings.model, "MODEL")
    try:
        return init_chat_model(model)
    except Exception as exc:
        raise MissingConfig(
            f"Could not initialize MODEL={settings.model!r}: {exc}\n"
            "Check the provider variables in agent/.env (see .env.example)."
        ) from exc
