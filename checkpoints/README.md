# Checkpoints

Known-good snapshots of the agent's Python and HTML files.

| Name | State |
|------|-------|
| `starter` | Chapter 0 baseline: the untouched starter agent |
| `ch04-agent-as-itself` | End of Chapter 4: the LLM key comes from the Keycard vault, fetched as the agent itself |
| `ch05-user-login` | End of Chapter 5: sign-in wired, the chat page shows your identity |
| `ch06-on-behalf-of` | End of Chapter 6: tool calls carry the user's delegated token |
| `finished` | The completed agent (lives in `../agent-keycard/`) |

## Restore

From the repo root:

```
python scripts/restore_checkpoint.py ch05-user-login
```

Only `.py` and `.html` files are copied; `agent/.env` is never touched.
Restart the agent afterward. Every checkpoint from `ch04-agent-as-itself` on
fetches the LLM key from the Keycard vault, so do Chapter 4's console and
`.env` steps before restoring one of them.

Checkpoints cover the agent tree only. The requests MCP server's finished state
is the full tree at `../mcp-requests-keycard/`; copy `server.py` and `storage.py`
back by hand if needed.
