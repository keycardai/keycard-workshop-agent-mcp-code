from keycardai.langchain import KeycardIdentity
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from .config import MissingConfig, Settings, require
from .graph import shared_middleware


def _api_key(settings: Settings) -> str:
    # The agent's own identity, proven with its client credentials; the vault
    # releases the LLM key to it per turn, and every retrieval lands in the
    # audit log. Nothing is stored. The key is a model credential with no
    # tool behind it, so it rides resources= instead of a tool_resources
    # entry, granted through the same middleware instance the tools use.
    resource = require(settings.llm_key_resource, "LLM_KEY_RESOURCE")
    keycard = shared_middleware(settings)
    with keycard.grant(KeycardIdentity(as_self=True), resources=[resource]) as access:
        # There is no run to pause, so nothing interrupts here: failures
        # stay on the AccessContext, exactly as tools see them.
        error = access.get_error() or access.get_resource_error(resource)
        if error is not None:
            raise MissingConfig(_describe(error, resource))
        return access.access(resource).access_token


def _describe(error: dict, resource: str) -> str:
    if error.get("code") == "invalid_target":
        return (
            f"Keycard doesn't recognize the resource {resource!r}. "
            "LLM_KEY_RESOURCE must match the identifier registered in "
            "Keycard byte-for-byte."
        )
    if error.get("code"):
        return f"Keycard refused the credential request ({error['code']})."
    return f"Could not reach Keycard ({error.get('message') or error})."


def get_llm(settings: Settings) -> BaseChatModel:
    model = require(settings.model, "MODEL")
    key = _api_key(settings)
    try:
        return init_chat_model(model, api_key=key)
    except Exception as exc:
        raise MissingConfig(
            f"Could not initialize MODEL={settings.model!r}: {exc}\n"
            "Check the provider variables in agent/.env (see .env.example)."
        ) from exc
