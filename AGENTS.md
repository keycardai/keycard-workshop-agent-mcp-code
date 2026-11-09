# Keycard Agent + MCP Workshop

This repo is a hands-on workshop: you help an attendee wire a local LangChain
agent and an MCP server into Keycard, one chapter at a time.

**Before helping, read the workshop helper skill and follow it:**
`.claude/skills/keycard-workshop/SKILL.md` (also at `.agents/skills/keycard-workshop/SKILL.md`).
It defines how to orient, which chapter to build, and the guardrails. The ones that matter
most: build one chapter at a time, in order, never run ahead, and treat the docs as the
source of truth.

Key layout:

- You work in `agent/` and `mcp-requests/` for the entire workshop (the
  Chapter 0 baseline).
- `agent-keycard/` and `mcp-requests-keycard/` are the finished trees,
  read-only references.
- The workshop guide is the hosted docs site at
  https://keycard-workshop-agent-mcp-docs.fly.dev. Start at the
  prerequisites, then work through the chapters in order.
