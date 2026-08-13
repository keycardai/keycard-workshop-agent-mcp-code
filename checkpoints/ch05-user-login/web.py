"""The agent's web app: the chat page, the chat endpoint, and sign-in routes."""

import json
import os
import socket
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from keycardai.langchain import KeycardGrantMiddleware, KeycardIdentity
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from .config import MissingConfig, load_settings
from .graph import build_agent, make_keycard_middleware
from .keycard.login import router as keycard_router
from .keycard.tokens import NotLoggedIn, store
from .llm import get_llm
from .tools import get_tools
from .tools.requests_queue import REQUEST_TOOLS

settings = load_settings()
tools = get_tools(settings)

app = FastAPI(title="Workshop agent")
app.include_router(keycard_router)

INDEX = Path(__file__).resolve().parent / "index.html"

# One user, one process, memory only. The lock keeps a second browser tab
# from interleaving turns.
messages: list[BaseMessage] = []
chat_lock = threading.Lock()

# Interrupt plumbing, not conversation memory: the grant middleware pauses a
# run by checkpointing it, so each turn gets a throwaway thread and the saver
# lives for the process. pending_thread names the one paused run, if any.
checkpointer = InMemorySaver()
pending_thread: str | None = None

# The dashboard view the page's panel shows: seeded on page load, folded forward
# after every streamed step, kept across resets. panel_error is the last fetch
# failure in plain words, or None while the view is honest.
panel_view: list[dict] = []
panel_error: str | None = None

def panel_records(
    history: list[BaseMessage], base: list[dict]
) -> tuple[list[dict], bool]:
    """Fold the request tools' JSON output onto base, the latest known dashboard
    view: a full listing replaces it, a single request merges in by "id".
    The page never fetches the dashboard itself; everything it shows went
    through the agent's tools (dashboard_snapshot seeds the page load). The
    second element reports whether any real dashboard data arrived, the cue
    that a standing panel error is stale.
    """
    records = list(base)
    saw_data = False
    for message in history:
        if message.type != "tool" or message.name not in REQUEST_TOOLS:
            continue
        try:
            data = json.loads(message.text)
        except ValueError:
            continue
        if isinstance(data, list) and all(isinstance(r, dict) and "id" in r for r in data):
            records = data
            saw_data = True
        elif isinstance(data, dict) and "id" in data:
            merged = {r["id"]: r for r in records}
            if data.get("deleted"):
                merged.pop(data["id"], None)
            else:
                merged[data["id"]] = data
            records = list(merged.values())
            saw_data = True
    return records, saw_data


# One middleware for the process, built on first use so a missing setting
# surfaces as a message where it's noticed, not a crash at import. It holds
# no identity (that arrives per run via context), and sharing it keeps its
# per-loop client cache and metadata discovery warm across turns.
_keycard: KeycardGrantMiddleware | None = None


def _middleware() -> KeycardGrantMiddleware:
    global _keycard
    if _keycard is None:
        _keycard = make_keycard_middleware(settings)
    return _keycard


def dashboard_snapshot() -> tuple[list[dict] | None, str | None]:
    """The dashboard, fetched through the same governed tool the agent uses
    in chat: grant() serves the tool's access context outside a run, so this
    page plumbing takes the exact code path (and error wording) tool calls
    do. None records means the fetch failed, and the second element says why.
    """
    try:
        keycard = _middleware()
        identity = KeycardIdentity(subject_token=store.user_token)
    except (MissingConfig, NotLoggedIn) as exc:
        return None, f"Authorization error: {exc}"
    lister = next(t for t in tools if t.name == "list_requests")
    with keycard.grant(identity, tool_name="list_requests"):
        raw = lister.invoke({})
    try:
        data = json.loads(raw)
    except ValueError:
        # Failures arrive as plain sentences ("Authorization error: ...").
        return None, str(raw)
    if isinstance(data, list) and all(isinstance(r, dict) and "id" in r for r in data):
        return data, None
    if isinstance(data, dict) and data.get("detail"):
        return None, str(data["detail"])
    return None, None


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


def _refusal(reply: str) -> StreamingResponse:
    def one_line():
        yield json.dumps(
            {"reply": reply, "records": panel_view, "error": panel_error}
        ) + "\n"
    return StreamingResponse(one_line(), media_type="application/x-ndjson")


def _stream_turn(graph_input, thread_id: str):
    """One agent run as NDJSON events: graph_input is the user's new message,
    or a resume Command. The run is checkpointed under thread_id so the grant
    middleware can pause it; a pause ends the stream with an "interrupt"
    event and leaves the history untouched until the resumed run finishes.
    """
    global messages, panel_view, panel_error, pending_thread
    with chat_lock:
        # Assembled under the lock: a racing second tab reads the finished
        # history, not a stale snapshot it would later overwrite.
        if isinstance(graph_input, HumanMessage):
            graph_input = {"messages": messages + [graph_input]}
        # Captured before the run: the session can expire between the
        # endpoint's backstop and this generator actually running.
        try:
            subject_token = store.user_token
        except NotLoggedIn as exc:
            yield json.dumps(
                {"reply": str(exc), "records": panel_view, "error": panel_error}
            ) + "\n"
            return
        # Assembled per turn: nothing the model holds outlives the request.
        # The Keycard middleware is the one exception, shared because it
        # holds no identity, only warm plumbing (see _middleware).
        try:
            agent = build_agent(
                get_llm(settings),
                tools,
                identity=store.identity() if store.claims() else None,
                keycard=_middleware(),
                checkpointer=checkpointer,
            )
        except MissingConfig as exc:
            yield json.dumps(
                {"reply": f"Configuration error: {exc}", "records": panel_view}
            ) + "\n"
            return
        # "messages" streams tokens to the page; "values" refreshes the
        # panel after each tool result; "updates" carries the middleware's
        # pause, if any. The turn joins the history only once the model
        # finishes, so a failed or paused call leaves nothing behind.
        turn = messages
        streaming_id = None
        interrupt_payload = None
        for mode, payload in agent.stream(
            graph_input,
            {"configurable": {"thread_id": thread_id}},
            # Runtime context is not checkpointed: every run, resumed ones
            # included, re-supplies the signed-in user's identity.
            context=KeycardIdentity(subject_token=subject_token),
            stream_mode=["messages", "values", "updates"],
        ):
            if mode == "messages":
                chunk, _ = payload
                if not isinstance(chunk, AIMessageChunk) or not chunk.text:
                    continue
                # A new model step (after a tool call) starts the bubble
                # over: only the final step's text is the reply.
                if chunk.id != streaming_id:
                    if streaming_id is not None:
                        yield json.dumps({"restart": True}) + "\n"
                    streaming_id = chunk.id
                yield json.dumps({"delta": str(chunk.text)}) + "\n"
            elif mode == "values":
                turn = payload["messages"]
                # Fold this turn's new tool results onto the latest known
                # view; earlier turns are already in. Real data arriving
                # means any standing panel error has been outlived.
                panel_view, saw_data = panel_records(turn[len(messages):], panel_view)
                if saw_data:
                    panel_error = None
                if turn[-1].type == "ai" and turn[-1].tool_calls:
                    for call in turn[-1].tool_calls:
                        yield json.dumps({"tool": call["name"]}) + "\n"
            elif "__interrupt__" in payload:
                interrupt_payload = payload["__interrupt__"][0].value
        if interrupt_payload is not None:
            pending_thread = thread_id
            yield json.dumps(
                {"interrupt": {
                    "type": interrupt_payload.get("type"),
                    # Why sign-in is needed: "missing_identity" or
                    # "subject_token_expired". The page words its card by this.
                    "reason": interrupt_payload.get("reason"),
                    "message": interrupt_payload.get("message"),
                    "url": interrupt_payload.get("authorization_url")
                    or interrupt_payload.get("sign_in_url"),
                }, "records": panel_view, "error": panel_error}
            ) + "\n"
            return
        messages = turn
        pending_thread = None
        yield json.dumps(
            {"reply": str(messages[-1].text), "records": panel_view,
             "error": panel_error}
        ) + "\n"


@app.post("/chat")
def chat(body: ChatRequest) -> StreamingResponse:
    global pending_thread
    # The page gates itself behind sign-in; this backstop covers everything
    # that isn't the page. No user, no agent: there is nobody to act for.
    if store.claims() is None:
        return _refusal("No one is signed in. Sign in first.")
    # A new message abandons any paused run: fresh thread, fresh turn.
    pending_thread = None
    return StreamingResponse(
        _stream_turn(HumanMessage(body.message), uuid.uuid4().hex),
        media_type="application/x-ndjson",
    )


@app.post("/chat/resume")
def chat_resume() -> StreamingResponse:
    """Continue the one paused run after the user granted access or signed
    in. The consent lives in the zone, not the session, so resuming just
    retries the exchange under the same identity.
    """
    if store.claims() is None:
        return _refusal("No one is signed in. Sign in first.")
    # Captured once: a racing new message clears the global mid-request.
    thread_id = pending_thread
    if thread_id is None:
        return _refusal("Nothing is waiting to resume.")
    return StreamingResponse(
        _stream_turn(Command(resume="granted"), thread_id),
        media_type="application/x-ndjson",
    )


@app.get("/panel")
def panel() -> dict:
    return {"records": panel_view, "error": panel_error}


@app.post("/panel/refresh")
def refresh_panel() -> dict:
    """The page's refresh button: re-snapshot the dashboard and make that the
    panel's latest known view. A failed fetch keeps the current one and
    reports why it can't be trusted."""
    global panel_view, panel_error
    fresh, panel_error = dashboard_snapshot()
    if fresh is not None:
        panel_view = fresh
    return {"records": panel_view, "ok": fresh is not None, "error": panel_error}


@app.get("/history")
def history() -> dict:
    global panel_view, panel_error
    # Final replies only: the live view clears tool-calling interludes, so
    # they must not reappear on refresh.
    turns = [
        {"role": "you" if m.type == "human" else "agent", "text": m.text}
        for m in messages
        if m.text and (m.type == "human" or m.type == "ai" and not m.tool_calls)
    ]
    # Every page load re-reads the dashboard, so the panel reflects the world
    # as it stands now (an authorization granted since the last error clears
    # it), not the last thing that happened to this process.
    fresh, panel_error = dashboard_snapshot()
    if fresh is not None:
        panel_view = fresh
    # pending survives the sign-in redirect: the page re-offers Resume.
    return {
        "turns": turns, "records": panel_view, "error": panel_error,
        "pending": pending_thread is not None,
    }


@app.post("/reset")
def reset() -> dict:
    """Clear the chat. Sign-in and the panel survive; the dashboard outlives
    conversations."""
    global messages, pending_thread
    with chat_lock:
        messages = []
        pending_thread = None
    return {"ok": True}


@app.get("/me")
def me() -> dict:
    # The login URL doubles as the page's cue to show the Sign in button.
    if store.claims() is None:
        return {"signed_in": False, "login": "/login"}
    return {"signed_in": True, "identity": store.identity(), "groups": store.groups()}


def serve() -> None:
    # Fail before uvicorn does, with a message that says what to do about it.
    probe = socket.socket()
    # Match uvicorn's SO_REUSEADDR so TIME_WAIT sockets from a just-closed
    # run don't read as a conflict. Skip it on Windows, where the flag would
    # let the probe bind straight over a still-running agent.
    if os.name != "nt":
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", settings.agent_port))
    except OSError:
        raise SystemExit(
            f"Port {settings.agent_port} is already in use; close the previous "
            "agent, or change AGENT_PORT and the application's redirect URI "
            "together."
        ) from None
    finally:
        probe.close()

    print(f"Agent running. Open http://localhost:{settings.agent_port}")
    # One process, one worker: the token store and conversation live in module
    # memory. Passing the app object (not an import string) keeps reload off.
    uvicorn.run(app, host="127.0.0.1", port=settings.agent_port, log_level="warning")
