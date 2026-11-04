# Workshop agent

A LangChain agent that works the team's shared request dashboard over a
remote MCP server. This folder is your working copy; the workshop guide walks
you through the changes it needs (Chapters 4 to 7). The completed version lives in
`../agent-keycard/`.

## Run

From the repo root, with the venv active and `agent/.env` filled in:

```
python -m agent          # chat app: open http://localhost:8484
python -m agent check    # preflight: verifies every connection (Chapter 3)
```

The requests MCP server must be running too (Chapter 0 starts it).

## Layout

| Module | Role |
|--------|------|
| `web.py` | The web app: chat endpoint, live request panel, sign-in wiring |
| `index.html` | The chat page (scaffolding; you never edit it) |
| `graph.py` | The LangChain agent (all LangChain surface lives here) |
| `llm.py` | The model, with its key fetched from the Keycard vault as the agent itself (Chapter 4) |
| `keycard/` | The Keycard integration; doesn't exist yet, you create it in Chapter 5 |
| `tools/requests_queue.py` | Request dashboard tools: the on-behalf-of pattern (Chapter 6) |
| `review.py` | The request reviewer: approves standard requests as the agent itself (Chapter 7) |
| `tools/remote.py` | One short-lived MCP session per tool call (shared plumbing) |
| `tools/__init__.py` | Tool registry, the swap point for your own resources |
