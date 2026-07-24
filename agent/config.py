import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

_SET_IN_CHAPTER = {
    "MODEL": "Chapter 0",
    "DIRECTORY_KEY": "Chapter 0",
    "AGENT_RESOURCE": "Chapter 2",
    "KEYCARD_ZONE_URL": "Chapter 2",
    "KEYCARD_CLIENT_ID": "Chapter 2",
    "KEYCARD_CLIENT_SECRET": "Chapter 2",
    "LLM_KEY_RESOURCE": "Chapter 7",
}


class MissingConfig(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    model: str
    keycard_zone_url: str
    keycard_client_id: str
    keycard_client_secret: str
    directory_key: str
    directory_key_resource: str
    llm_key_resource: str
    agent_resource: str
    directory_mcp: str
    requests_mcp: str
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
        directory_key=env("DIRECTORY_KEY", "").strip(),
        # These identifiers are matched byte-for-byte against what is
        # registered in Keycard, so no trailing-slash trimming here.
        directory_key_resource=env("DIRECTORY_KEY_RESOURCE", "").strip(),
        llm_key_resource=env("LLM_KEY_RESOURCE", "").strip(),
        agent_resource=env("AGENT_RESOURCE", "").strip(),
        requests_mcp=env("REQUESTS_MCP", "http://localhost:8300/mcp").strip(),
        # The hosted directory server; not a Keycard resource, just a URL.
        directory_mcp=env("DIRECTORY_MCP", "https://keycard-workshop-directory-mcp.fly.dev/mcp").strip(),
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
