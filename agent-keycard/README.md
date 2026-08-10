# Workshop agent, finished reference

The completed agent, exactly as `../agent/` looks at the end of Chapter 8.
Read it, diff against your working copy, or restore it with
`python scripts/restore_checkpoint.py finished`. Don't edit this folder.

## Run

From the repo root, with the venv active and `agent/.env` filled in:

```
python -m agent          # chat app: open http://localhost:8484
python -m agent check    # preflight: verifies every connection (Chapter 3)
```

The requests MCP server must be running too (Chapter 0 starts it); the
hosted directory is already up.

To try the finished agent without touching your working copy, run this
folder directly: `python -m agent-keycard` (it reads `agent-keycard/.env`).

## Layout

| Module | Role |
|--------|------|
| `web.py` | The web app: chat endpoint, live request panel, sign-in wiring |
| `index.html` | The chat page (scaffolding; never edited in the workshop) |
| `graph.py`, `llm.py` | LangChain agent + model (all LangChain surface lives here) |
| `keycard/login.py` | Browser sign-in routes (ships complete) |
| `keycard/tokens.py` | User-token store + RFC 8693 token exchange (ships complete) |
| `tools/directory.py` | Directory tools: the client-credentials pattern (Chapter 4) |
| `tools/requests_queue.py` | Request dashboard tools: the on-behalf-of pattern (Chapter 6) |
| `tools/remote.py` | One short-lived MCP session per tool call (shared plumbing) |
| `tools/__init__.py` | Tool registry, the swap point for your own resources |
