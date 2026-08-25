"""A background one-shot with no user anywhere: the environment brief.

The agent runs as itself (KeycardIdentity(as_self=True)): the vault releases
the directory key to the application's own identity, per call, and every
retrieval is an audit event attributed to the agent alone. As-itself runs
never pause for sign-in or consent (there is no user to send anywhere), so
this needs no checkpointer and no interrupt handling.

Run: python -m agent-keycard brief
"""

from keycardai.langchain import KeycardIdentity
from langchain_core.messages import HumanMessage

from .config import MissingConfig, load_settings
from .graph import build_agent, shared_middleware
from .llm import get_llm
from .tools.directory import make_directory_tools

PROMPT = (
    "Compile a short environment brief from the directory: the services and "
    "agents that make up this environment, anything recently changed, and "
    "any policies or runbooks worth knowing about. Plain prose with a few "
    "headers, under 200 words."
)


def main() -> int:
    settings = load_settings()
    try:
        agent = build_agent(
            get_llm(settings),
            make_directory_tools(settings),
            keycard=shared_middleware(settings),
        )
    except MissingConfig as exc:
        print(f"Configuration error: {exc}")
        return 1
    result = agent.invoke(
        {"messages": [HumanMessage(PROMPT)]},
        context=KeycardIdentity(as_self=True),
    )
    print(result["messages"][-1].text)
    return 0
