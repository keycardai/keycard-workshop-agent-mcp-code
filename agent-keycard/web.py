"""The agent's web app: the chat page, the chat endpoint, and sign-in routes."""

import json
import os
import socket
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from keycardai.langchain import KeycardIdentity
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from pydantic import BaseModel

from .config import MissingConfig, load_settings
from .graph import build_agent, shared_middleware
from .keycard.login import router as keycard_router
from .keycard.tokens import NotLoggedIn, store
from .llm import get_llm
from .review import review_filed
from .tools import get_tools
from .tools.requests_queue import REQUEST_TOOLS

settings = load_settings()
tools = get_tools(settings)

app = FastAPI(title="Workshop agent")
app.include_router(keycard_router)

INDEX = Path(__file__).resolve().parent / "index.html"

# One user, one process, memory only; the lock keeps a second browser tab
# from interleaving turns.
messages: list[BaseMessage] = []
chat_lock = threading.Lock()

# The panel's dashboard view; panel_error is the last fetch failure in plain words.
panel_view: list[dict] = []
panel_error: str | None = None

def panel_records(
    history: list[BaseMessage], base: list[dict]
) -> tuple[list[dict], bool]:
    """Fold the request tools' JSON output onto base: a full listing replaces
    it, a single request merges in by "id". The second element reports whether
    any real dashboard data arrived.
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


def dashboard_snapshot() -> tuple[list[dict] | None, str | None]:
    """The dashboard, fetched through the same governed tool the agent uses
    in chat: grant() serves the tool's access context outside a run. None
    means the fetch failed; the second element says why.
    """
    try:
        keycard = shared_middleware(settings)
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


@app.post("/chat")
def chat(body: ChatRequest) -> StreamingResponse:
    # The page gates itself behind sign-in; this backstop covers everything
    # that isn't the page. With nobody signed in, there's nobody to act for.
    try:
        subject_token = store.user_token
    except NotLoggedIn as exc:
        refusal = {"reply": str(exc), "records": panel_view, "error": panel_error}
        return StreamingResponse(
            iter([json.dumps(refusal) + "\n"]), media_type="application/x-ndjson"
        )

    def events():
        global messages, panel_view, panel_error
        with chat_lock:
            # Built per turn: nothing the model holds outlives the request.
            try:
                llm = get_llm(settings)
                agent = build_agent(
                    llm,
                    tools,
                    identity=store.identity(),
                    keycard=shared_middleware(settings),
                )
            except MissingConfig as exc:
                yield json.dumps(
                    {"reply": f"Configuration error: {exc}", "records": panel_view}
                ) + "\n"
                return
            # The turn joins the history only once the model finishes, so a
            # failed call leaves nothing behind.
            turn = messages + [HumanMessage(body.message)]
            streaming_id = None
            for mode, payload in agent.stream(
                {"messages": turn},
                # Who this run acts for: the middleware takes your session
                # token to Keycard before each tool call.
                context=KeycardIdentity(subject_token=subject_token),
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    chunk, _ = payload
                    if not isinstance(chunk, AIMessageChunk) or not chunk.text:
                        continue
                    # A new model step starts the bubble over; only the final
                    # step's text is the reply.
                    if chunk.id != streaming_id:
                        if streaming_id is not None:
                            yield json.dumps({"restart": True}) + "\n"
                        streaming_id = chunk.id
                    yield json.dumps({"delta": str(chunk.text)}) + "\n"
                else:
                    turn = payload["messages"]
                    # Fold only this turn's new tool results; earlier turns
                    # are already in.
                    panel_view, saw_data = panel_records(turn[len(messages):], panel_view)
                    if saw_data:
                        panel_error = None
                    if turn[-1].type == "ai" and turn[-1].tool_calls:
                        for call in turn[-1].tool_calls:
                            yield json.dumps({"tool": call["name"]}) + "\n"
            reply = str(turn[-1].text)
            # Chapter 7: the agent reviews each request this turn filed, as itself.
            panel_view, note = review_filed(turn[len(messages):], panel_view, llm, settings)
            if note:
                reply += f"\n\n{note}"
                turn = turn + [AIMessage(note)]
            messages = turn
            yield json.dumps(
                {"reply": reply, "records": panel_view, "error": panel_error}
            ) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.get("/panel")
def panel() -> dict:
    return {"records": panel_view, "error": panel_error}


@app.post("/panel/refresh")
def refresh_panel() -> dict:
    """Re-snapshot the dashboard; a failed fetch keeps the current view and
    reports why."""
    global panel_view, panel_error
    fresh, panel_error = dashboard_snapshot()
    if fresh is not None:
        panel_view = fresh
    return {"records": panel_view, "ok": fresh is not None, "error": panel_error}


@app.get("/history")
def history() -> dict:
    global panel_view, panel_error
    # Final replies only: tool-calling interludes must not reappear on refresh.
    turns = [
        {"role": "you" if m.type == "human" else "agent", "text": m.text}
        for m in messages
        if m.text and (m.type == "human" or m.type == "ai" and not m.tool_calls)
    ]
    # Re-read the dashboard on every page load, so an authorization granted
    # since the last error clears it.
    fresh, panel_error = dashboard_snapshot()
    if fresh is not None:
        panel_view = fresh
    return {"turns": turns, "records": panel_view, "error": panel_error}


@app.post("/reset")
def reset() -> dict:
    """Clear the chat; the panel survives, the dashboard outlives conversations."""
    global messages
    with chat_lock:
        messages = []
    return {"ok": True}


@app.get("/me")
def me() -> dict:
    # The login URL doubles as the page's cue to show the Sign in button.
    if store.claims() is None:
        return {"signed_in": False, "login": "/login"}
    return {"signed_in": True, "identity": store.identity(), "groups": store.groups()}


def serve() -> None:
    # Probe the port first so a conflict fails with a message that says what
    # to do about it. Match uvicorn's SO_REUSEADDR so TIME_WAIT sockets don't
    # read as a conflict; skip it on Windows, where the flag would let the
    # probe bind straight over a still-running agent.
    probe = socket.socket()
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
    # One worker: state lives in module memory. Passing the app object
    # (not an import string) keeps reload off.
    uvicorn.run(app, host="127.0.0.1", port=settings.agent_port, log_level="warning")
