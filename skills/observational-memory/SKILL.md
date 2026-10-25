---
name: observational-memory
description: Use when the context holds a block starting "observational-memory: condensed memories from earlier in this session", when a bracketed 12-character hex id such as [d4e5f6a1b2c3] in those notes matters to a decision, or when the user asks about observational-memory, its notes, its status or the recall tool.
---

# Observational memory

observational-memory runs beside this harness's own compaction. As the session runs, an observer model reads the transcript and records **observations** (timestamped, rated low/medium/high/critical, each citing the transcript entries behind it) and, less often, **reflections** (durable facts distilled from observations). After a compaction, observational-memory adds the notes to the context, after the harness's own summary.

## Reading the notes

- Lines look like `[d4e5f6a1b2c3] 2026-10-22 14:30 [high] User chose Lucia for auth.` (observation) or `[a1b2c3d4e5f6] User prefers short answers.` (reflection).
- They are past records. Where they are more specific than the compaction summary, they hold. When two conflict, the newer is the latest known state, and anything said after the compaction overrides them.
- Work an observation marks `completed:` should not be redone unless the user asks.

## The `recall` tool

The `observational-memory` MCP server has one tool, `recall` (in OpenCode the observational-memory plugin provides the same `recall` tool, and the notes arrive inside OpenCode's compaction summary under `## observational-memory`). Call it with one id from the notes (`{"id": "d4e5f6a1b2c3"}`) and it returns that observation or reflection, whether it is active or dropped, and the exact transcript lines behind it.

- Use it when a note matters to what you do next and is too compressed to act on safely: an exact error, path, command, number or user wording.
- It is not a search. Do not call it for every note, and do not paste its raw output back unless the user needs it.

## Commands

In Claude Code and Cursor the user types `/observational-memory:status`, `/observational-memory:view [full]`, `/observational-memory:on`, `/observational-memory:off` or `/observational-memory:mode [main|agents] both|off`; a hook answers them before they reach you. In Codex there are no plugin commands: if the user asks for observational-memory's status or notes, run `"$HOME/.local/bin/observational-memory" status --harness codex` or `"$HOME/.local/bin/observational-memory" view --harness codex` (the newest Codex session; add `--session <id>` for another) and show the output. OpenCode has no observational-memory commands either: use the same two commands with `--harness opencode`. Changing the mode (`"$HOME/.local/bin/observational-memory" mode off`) affects every session, so do it only when the user asks.
