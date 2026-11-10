# Keycard Builder Workshop

Run a local LangChain agent against a shared team request dashboard over
MCP, then give every hop a real identity through
[Keycard](https://keycard.ai). By the end, nothing in the chain uses the
shared API key: every access is minted per call and audited.

The workshop guide lives at
**[keycard-workshop-agent-mcp-docs.fly.dev](https://keycard-workshop-agent-mcp-docs.fly.dev)**;
start there with **Prerequisites**.

## What's in this repo

| Path | What it is |
|------|------------|
| `agent/` | Your working copy of the LangChain agent (starter state) |
| `agent-keycard/` | The finished agent, for reference and recovery |
| `mcp-requests/` | The requests MCP server, port 8300 (starter state, shared API key) |
| `mcp-requests-keycard/` | The finished requests MCP server: protected, with per-call token exchange downstream |
| `checkpoints/` | Known-good snapshots of the agent to catch up from |
| `scripts/` | `restore_checkpoint.py`, for catching up from a checkpoint |

The hosted service has no folder here. Instructors run the shared requests
API at `REQUESTS_API_URL`; attendees never run or edit it.

## How to run

Run two local processes, each in its own shell with the venv active:

```
python -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt -r mcp-requests/requirements.txt

cd mcp-requests && python server.py     # shell 1: requests MCP server, port 8300
python -m agent                         # shell 2: the agent, http://localhost:8484
```

On Windows, activate with `.\.venv\Scripts\Activate.ps1` instead. Each folder's
`.env.example` explains its configuration. Chapter 0 fills in your model
settings in `agent/.env`. The
[guide](https://keycard-workshop-agent-mcp-docs.fly.dev) walks through the
rest in order.

## License

Apache-2.0 — see [LICENSE](LICENSE) and, for the copyright notice,
[NOTICE](NOTICE). You are free to keep, modify and reuse the code you write
during the workshop. The Keycard name and logo are trademarks;
[TRADEMARKS.md](TRADEMARKS.md) states how they may be used.
