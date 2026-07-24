from keycardai.oauth import BasicAuth, Client
from keycardai.oauth.exceptions import OAuthError, OAuthProtocolError
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from .config import MissingConfig, Settings, require


def _api_key(settings: Settings) -> str:
    # The agent's own identity, proven with its client credentials; the vault
    # releases the LLM key to it per turn, and every retrieval lands in the
    # audit log. Nothing is stored.
    with Client(
        require(settings.keycard_zone_url, "KEYCARD_ZONE_URL"),
        auth=BasicAuth(
            require(settings.keycard_client_id, "KEYCARD_CLIENT_ID"),
            require(settings.keycard_client_secret, "KEYCARD_CLIENT_SECRET"),
        ),
    ) as client:
        response = client.client_credentials_grant(
            resource=require(settings.llm_key_resource, "LLM_KEY_RESOURCE")
        )
    return response.access_token


def get_llm(settings: Settings) -> BaseChatModel:
    model = require(settings.model, "MODEL")
    try:
        key = _api_key(settings)
    except OAuthProtocolError as exc:
        if exc.error == "invalid_target":
            raise MissingConfig(
                f"Keycard doesn't recognize the resource "
                f"{settings.llm_key_resource!r}. LLM_KEY_RESOURCE must match "
                "the identifier registered in Keycard byte-for-byte."
            ) from exc
        raise MissingConfig(
            f"Keycard refused the credential request ({exc.error})."
        ) from exc
    except OAuthError as exc:
        raise MissingConfig(f"Could not reach Keycard ({exc}).") from exc
    try:
        return init_chat_model(model, api_key=key)
    except Exception as exc:
        raise MissingConfig(
            f"Could not initialize MODEL={settings.model!r}: {exc}\n"
            "Check the provider variables in agent/.env (see .env.example)."
        ) from exc
