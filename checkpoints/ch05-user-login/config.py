import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

_SET_IN_CHAPTER = {
    "MODEL": "Chapter 0",
    "REQUESTS_API_URL": "Chapter 0",
    "AGENT_RESOURCE": "Chapter 3",
    "KEYCARD_ZONE_URL": "Chapter 3",
    "KEYCARD_CLIENT_ID": "Chapter 3",
    "KEYCARD_CLIENT_SECRET": "Chapter 3",
    "LLM_KEY_RESOURCE": "Chapter 4",
}


class MissingConfig(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    model: str
    keycard_zone_url: str
    keycard_client_id: str
    keycard_client_secret: str
    llm_key_resource: str
    agent_resource: str
    requests_mcp: str
    requests_api_url: str
    requests_api_integrations: str
    agent_port: int

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.agent_port}/callback"


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        model=env("MODEL", "").strip(),
        keycard_zone_url=env("KEYCARD_ZONE_URL", "").strip().rstrip("/"),
        keycard_client_id=env("KEYCARD_CLIENT_ID", "").strip(),
        keycard_client_secret=env("KEYCARD_CLIENT_SECRET", "").strip(),
        # Matched byte-for-byte against what's registered in Keycard, so no
        # trailing-slash trimming here.
        llm_key_resource=env("LLM_KEY_RESOURCE", "").strip(),
        agent_resource=env("AGENT_RESOURCE", "").strip(),
        requests_mcp=env("REQUESTS_MCP", "http://localhost:8300/mcp").strip(),
        # Chapter 7's reviewer calls the requests API directly, as the agent
        # itself, with a token Keycard mints for the API's Integrations resource.
        requests_api_url=env("REQUESTS_API_URL", "").strip().rstrip("/"),
        requests_api_integrations=env(
            "REQUESTS_API_INTEGRATIONS",
            "urn:keycard-workshop:requests:api:integrations",
        ).strip(),
        agent_port=int(env("AGENT_PORT", "8484")),
    )


def require(value: str, env_name: str) -> str:
    if not value:
        chapter = _SET_IN_CHAPTER.get(env_name)
        hint = f" (set in {chapter})" if chapter else ""
        raise MissingConfig(
            f"{env_name} is missing from agent/.env{hint}. See agent/.env.example."
        )
    return value
