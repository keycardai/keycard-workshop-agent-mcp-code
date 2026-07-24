# Keycard Builder Workshop

Run a local LangChain agent against a hosted directory and a shared team
request dashboard, both over MCP, then give every hop a real identity through
[Keycard](https://keycard.ai). The closing chapter revokes both shared keys
live, and the finished stack keeps working: by then every access
is minted per call and audited.

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

The two hosted services have no folder here. Instructors run the directory
MCP server at `https://keycard-workshop-directory-mcp.fly.dev/mcp` and the shared
requests API at `https://keycard-workshop-requests-api.fly.dev`; attendees never run or edit
either.

## How to run

Run two local processes, each in its own shell with the venv active:

```
python -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt -r mcp-requests/requirements.txt

cd mcp-requests && python server.py     # shell 1: requests MCP server, port 8300
python -m agent                         # shell 2: the agent, http://localhost:8484
```

On Windows, activate with `.\.venv\Scripts\Activate.ps1` instead. Each folder's
`.env.example` explains its configuration. Chapter 0 fills in two sections of
`agent/.env`: your model settings, and `DIRECTORY_KEY`, the shared guest key
for the hosted directory that instructors hand out at the start. The
[guide](https://keycard-workshop-agent-mcp-docs.fly.dev) walks through the
rest in order.
