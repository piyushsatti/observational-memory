# observational-memory: verification

One row per run, on the [verification ladder](https://github.com/piyushsatti/workbench/blob/main/CONVENTIONS.md#verification-ladder).

| Level | Claude Code | Codex | Cursor | OpenCode |
|---|---|---|---|---|
| V0 lint | pass, 2026-10-22: `python3 scripts/lint_plugins.py` → 5 plugins, 0 errors, 0 warnings (catalogs included) | same run | same run | not run (the plugin is not in a lint catalog) |
| V1 native validator | pass, 2026-10-22, Claude Code 2.1.307: `claude plugin validate` | no validator found; lint checks the documented fields | no validator found; lint checks the documented fields | no validator found; OpenCode's loader is the check (V3) |
| V2 script tests | pass, 2026-10-22, Python 3.15.0: 36 tests OK | pass, same run | pass, same run | pass, 2026-10-25, Python 3.15.0: 46 tests OK |
| V3 loads without install | not run | not run | not run | pass, 2026-10-25, OpenCode 2.1.4: the server logged `loading plugin` for `observational-memory.js` and no `failed to load plugin` |
| V4 runtime behaviour | not run | not run | not run | pass, 2026-10-25, OpenCode 2.1.4; see below |
| V5 in use | not run | not run | not run | not run |

## V2, 2026-10-22

`python3 -m unittest discover -s tests` from the repo root: `Ran 36 tests ... OK`. HOME was a temp folder, the model was `tests/fake_model.py`, and the hook stdin and transcripts were synthetic. The run covered:

- the parsers for all three transcript shapes;
- ledger append and the watermark (offset fast path, rewritten-file fallback, model failure, empty-run backoff, lock);
- reflector then dropper;
- the recursion guard on all 16 hook and event pairs, and `OBSERVATIONAL_MEMORY_CHILD=1` on the model call;
- the injection output shape per harness, including Cursor's preCompact-then-postToolUse once;
- per-subagent streams;
- command interception per harness, `/observational-memory:off` writing nothing, `/observational-memory:on` starting from the current end;
- `recall` and the MCP stdio server;
- the renderer budget, status, view and statusline;
- owner-only folders and files, and a refused symlinked ledger.

V2 shows the script handles the documented and assumed input shapes. It does not show that any harness sends those shapes.

## V2, 2026-10-25 (OpenCode)

`Ran 46 tests ... OK`: the 36 above plus 10 for OpenCode. The hook payloads in `tests/fixtures/opencode/` have the shape OpenCode 2.1.4 returned from `ctx.session.context` in the V4 run, with synthetic text. They cover the mirror (append-only, deduplicated, ordered, stopping at a streaming reply, owner-only), the parser (user text, tool calls and results; no reasoning, `idle` or native compaction summary), turn-end observing, the compaction catch-up and its `{"context": …}` answer, `off`, child sessions with `agents off` and `both`, the recursion guard, `recall` from the mirror and the `recall` CLI, the default model command, and a static check of the plugin file and `install.json`.

## V4, 2026-10-25 (OpenCode)

OpenCode 2.1.4, with a throwaway HOME: only `auth.json` copied in, no `opencode.json`, the worktree's `bin/observational-memory` in its `~/.local/bin` and `opencode/observational-memory.js` in its `~/.config/opencode/plugins/`. A private `opencode serve` on 127.0.0.1 took the turns (`opencode run --server … --session <id>`); one more turn ran through `opencode run --standalone`. The model was `opencode/deepseek-v4.1-flash-free` for the session and, through `model_command.opencode`, for the observer. `config.json` set `observe_after_tokens` 150 and `reflect_after_tokens` 600.

- **Plugin API.** OpenCode 2 loads `{id, setup(ctx)}` default exports. The OpenCode 1 shape in the older docs (an exported function returning `event` and `experimental.session.compacting` handlers) fails to load in 2.1.4 with `Plugin must export a default definition with an id and an effect or setup function`. The plugin follows <https://opencode.ai/v2/docs/build/plugins/>.
- **Turn end.** OpenCode 2.1.4 emitted `session.execution.succeeded` at the end of every turn and never `session.idle`. `hooks.log` shows `opencode stop spawned` 8 times: after each of 6 turns, including the `--standalone` one, whose server shut down right after the turn, and after each of the 2 compactions, which OpenCode also runs as an execution.
- **Observer.** Four turns in one session (facts, a shell tool call, a decision, a deploy target) produced 4 `observations.recorded` entries and 9 observations citing `msg_…` ids from the mirror, then 1 `reflections.recorded` with 5 reflections. `lastError` stayed empty.
- **Compaction.** `opencode api --server … POST /api/session/<id>/compact` ran two compactions. Each logged `opencode compacting injected`; the first catch-up recorded the turn the turn-end observer had not read yet, before the notes were rendered. The `injected` entries carry `event: compacting`. With the final instruction text, OpenCode's stored summary (the `compaction` message's `summary` in `GET /api/session/<id>/context`) ended with a `## observational-memory` section holding all 8 rendered observations verbatim with their ids. The first instruction, which only asked the summarizer to carry the notes, produced a summary that used their content but dropped the ids.
- **Recall.** After the compaction, the agent called the plugin's `recall` tool with an id from the summary. The tool returned the observation and the exact mirrored user message, and the agent quoted the user's words from it.
- **Recursion guard.** Each of the 5 observer and reflector calls started its own `opencode run --standalone` server with the plugin loaded. Those sessions appear in `opencode session list`, but none got a ledger, a mirror or a `hooks.log` line: the plugin returned from `setup` under `OBSERVATIONAL_MEMORY_CHILD=1`.

Not exercised: subagent child sessions (the `parentID` field is assumed), automatic compaction on context overflow, a server restart in the middle of a session, and any model other than the free one above.
