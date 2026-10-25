# observational-memory

Observational memory beside compaction. As a session runs, an observer model reads the transcript and writes short, rated, timestamped observations, each citing the transcript lines behind it. A reflector distils durable reflections from them, and a dropper retires the ones that are safe to retire. After each compaction, observational-memory adds the notes to the context, after the harness's own summary. The `recall` tool returns the exact transcript lines behind any note's id.

It is a port of [pi-observational-memory](https://github.com/elpapi42/pi-observational-memory) (commit `022da5e`) to plain hooks, and replaces an earlier Claude Code mod ([decisions](https://github.com/piyushsatti/workbench/blob/main/docs/decisions.md#what-each-piece-is)). The model and every deviation are in [SPEC.md](SPEC.md).

## Pieces

- `bin/observational-memory` is one Python 3 script, standard library only, installed to `~/.local/bin/observational-memory` by `install.json`. Hooks and the MCP server call that installed copy.
- `hooks/claude.json`, `hooks/codex.json` and `hooks/cursor.json` are named by their manifests.
- `opencode/observational-memory.js` is an OpenCode 2 plugin (a default export with an `id` and `setup`, no dependencies), installed to `~/.config/opencode/plugins/observational-memory.js` by `install.json`, where OpenCode loads it on its own. It sends each turn's messages to `observational-memory hook opencode stop`, adds the notes to compactions through `hook opencode compacting`, and registers the `recall` tool, so OpenCode needs no MCP entry. OpenCode 1.x plugins have a different shape and are not supported.
- `.mcp.json` and `mcp.json` are identical. Each registers the server `observational-memory`, which runs `"$HOME/.local/bin/observational-memory" recall-mcp` through `sh -c`, so `$HOME` expands the same in every harness.
- `commands/` holds `/observational-memory:status`, `/observational-memory:view`, `/observational-memory:on`, `/observational-memory:off` and `/observational-memory:mode` for Claude Code and Cursor, answered by the prompt hook.
- `skills/observational-memory/` tells the agent about the notes and `recall`. In Codex it is also how the user reaches observational-memory.
- Data lives in `~/.local/state/observational-memory/`: `config.json`, and per session `<harness>/<session>.jsonl` (the ledger), `.state.json` and `.lock`, OpenCode's transcript mirrors in `opencode/transcripts/<session>.jsonl`, plus `hooks.log` and `observational-memory.log`. All of it is owner-only.

## Harness support

| Harness | Works | Reduced | Missing |
|---|---|---|---|
| Claude Code | Async Stop observer; PreCompact catch-up; notes after the summary through SessionStart `compact`; `/observational-memory:` commands; SubagentStop per-subagent notes (`/observational-memory:mode agents both`); `recall`; `observational-memory statusline` segment for cc-status | Notes are added after the native summary, never in its place; SessionStart waits up to 30 s for the catch-up | om.tsx's `observational-memory` mode (notes instead of the summary); the in-footer O/C/X gauges; proactive compaction |
| Codex | Verified on Codex 0.163.0 (V4): Stop observer; PreCompact catch-up; notes after the compaction through SessionStart `compact`; `recall`; the skill | The plugin's hooks run only after you trust them in `/hooks`. There are no commands: the TUI rejects `/observational-memory:…`, and Codex lists `commands/` as skills, which run `observational-memory status --harness codex` and the like. The rollout format is unstable, so parsing may break on a Codex update | Statusline; slash commands; SubagentStop untested |
| Cursor | stop observer; preCompact catch-up; `/observational-memory:` commands through beforeSubmitPrompt; `recall`; the skill | No post-compaction hook: the notes go in on the next postToolUse, once, so a turn without a tool call gets none (untested); the transcript format is undocumented | Statusline; a reliable post-compaction injection point |
| OpenCode 2 | Turn-end observer (`session.execution.succeeded`); compaction catch-up, then the notes go **into** the compaction's input, so OpenCode's own summary carries them with their ids; `recall` as a plugin tool; reflector and dropper | The transcript is a mirror the plugin writes from `ctx.session.context`, so turns from before the plugin was installed, or from a server without it, are never observed; whether the notes survive depends on the summary model following the instruction to copy them (it did in the run on record); the observer's default model is OpenCode's default, through `opencode run --standalone`, and each call adds a session to OpenCode's list | Slash commands (run `observational-memory status --harness opencode`); statusline; subagent child sessions are routed by `parentID`, which is untested |

Claude Code, Codex and OpenCode have run it end to end (V3 and V4). Cursor has not run it inside the harness yet. See [VERIFIED.md](VERIFIED.md).

## Settings

Edit `~/.local/state/observational-memory/config.json`; keys left out keep their defaults (SPEC.md lists them). For example:

```json
{"model": "sonnet", "observe_after_tokens": 10000, "model_command": {"codex": ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "-"]}}
```

`model_command.<harness>` is the headless command that answers the observer, with the prompt on stdin; `{model}` in it becomes `model`. It runs with `OBSERVATIONAL_MEMORY_CHILD=1`, so its own session fires no observational-memory hooks. For OpenCode the default is `["opencode", "run", "--standalone"]` with OpenCode's default model; add `"-m", "provider/model"` to pick one (`{model}` defaults to the Claude name `sonnet`, which OpenCode may not have).

## Shell

```
observational-memory status [--harness h --session s]  gauges and counts (default: the newest ledger)
observational-memory view [full]                        the notes a compaction would add; full lists dropped ones
observational-memory mode [main|agents] both|off        show or set the mode (global)
observational-memory observe --harness h --session s --transcript p [--force]
observational-memory recall <id>                         the recall tool once
observational-memory reflect                            run the reflector and dropper now
observational-memory inject                             print the rendered notes
```

## Tests

From the repo root: `python3 -m unittest discover -s tests`. The model is `tests/fake_model.py`, hook stdin comes from `tests/fixtures/`, transcripts are synthetic, and HOME is a temp folder.
