# Checkpoints

Known-good snapshots of the agent's Python and HTML files.

| Name | State |
|------|-------|
| `starter` | Chapter 0 baseline: the untouched starter agent |
| `ch03-agent-as-itself` | End of Chapter 3: directory tools mint credentials as the application |
| `ch04-user-login` | End of Chapter 4: sign-in wired, the chat page shows your identity |
| `ch05-on-behalf-of` | End of Chapter 5: tool calls carry the user's delegated token |
| `finished` | The completed agent (lives in `../agent-keycard/`) |

## Restore

From the repo root:

```
python scripts/restore_checkpoint.py ch04-user-login
```

Only `.py` and `.html` files are copied; `agent/.env` is never touched.
Restart the agent afterward.

Checkpoints cover the agent tree only. The requests MCP server's finished state
is the full tree at `../mcp-requests-keycard/`; copy `server.py` and `storage.py`
back by hand if needed.
