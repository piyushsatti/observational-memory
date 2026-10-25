# observational-memory: verification

One row per run, on the [verification ladder](https://github.com/piyushsatti/workbench/blob/main/CONVENTIONS.md#verification-ladder).

| Level | Claude Code | Codex | Cursor |
|---|---|---|---|
| V0 lint | pass, 2026-10-22: `python3 scripts/lint_plugins.py` → 5 plugins, 0 errors, 0 warnings (catalogs included) | same run | same run |
| V1 native validator | pass, 2026-10-22, Claude Code 2.1.307: `claude plugin validate` | no validator found; lint checks the documented fields | no validator found; lint checks the documented fields |
| V2 script tests | pass, 2026-10-22, Python 3.15.0: 36 tests OK | pass, same run | pass, same run |
| V3 loads without install | pass, 2026-10-25, Claude Code 2.1.307: `claude -p --plugin-dir` loads the five hooks, the `observational-memory` MCP server and the commands ([below](#claude-code-v3-and-v4-2026-10-25)) | pass, 2026-10-25, Codex 0.163.0: installed from a local marketplace in a throwaway `HOME`/`CODEX_HOME`; the five hooks, the `observational-memory` MCP server and the skill load ([below](#codex-v3-and-v4-2026-10-25)) | not run |
| V4 runtime behaviour | pass, 2026-10-25, Claude Code 2.1.307: Stop observer writes the ledger, PreCompact catch-up, SessionStart `compact` adds the notes after the compaction, `recall` over MCP, `/om status` ([below](#claude-code-v3-and-v4-2026-10-25)) | pass, 2026-10-25, Codex 0.163.0: Stop observer writes the ledger, PreCompact catch-up, SessionStart `compact` adds the notes after the compaction, `recall` over MCP; `/observational-memory:` commands do not work ([below](#codex-v3-and-v4-2026-10-25)) | not run |
| V5 in use | not run | not run | not run |

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

## Claude Code V3 and V4, 2026-10-25

Claude Code 2.1.307, session model and observer model `haiku`, `observe_after_tokens` set to 300 in `config.json`. One session, run as `claude -p --plugin-dir <repo> --output-format json`, then `--resume <id>` four more times.

1. Turn 1 stated two facts. `hooks.log`: `UserPromptSubmit pass`, `Stop spawned`; the observer logged `below` (one short turn is under 300 tokens).
2. Turn 2 read a file with the Read tool and stated a decision. `Stop spawned`, then the observer logged `recorded`: one `observations.recorded` entry with five observations (the decision at `critical`), 1,049 source tokens.
3. Turn 3 was `/compact`. `hooks.log`: `PreCompact catch-up`, `SubagentStop agents-off` (the compaction's own agent), `SessionStart injected`. The transcript holds a `hook_additional_context` attachment starting with the notes header, after the compact boundary.
4. Turn 4 allowed only the `recall` tool and asked for the database decision. The model called `recall` with id `81bda680b32a` and quoted the observation.
5. Turn 5 was `/om status`. UserPromptSubmit blocked the prompt and returned the status panel (5 observations, last injection 471 tokens) with no model turn.

Not run: SubagentStop with `agents both`, the reflector and the dropper, automatic compaction.

## Codex V3 and V4, 2026-10-25

Codex CLI 0.163.0, model `gpt-6-astra` at low effort. Every command ran with a throwaway `HOME` and `CODEX_HOME=$HOME/.codex` holding only a copied `auth.json` and a minimal `config.toml`; `bin/observational-memory` was installed to `$HOME/.local/bin/` (0755), and `$HOME/.local/state/observational-memory/config.json` set `observe_after_tokens` to 500.

### V3: the plugin loads

- `codex plugin marketplace add $HOME/mkt` → `Added marketplace omtest`. The marketplace's `.agents/plugins/marketplace.json` has one entry, `{"source": "local", "path": "./plugins/observational-memory"}`, where `plugins/observational-memory` links to the repo. An absolute `path` is not accepted: `codex plugin add` then answers `plugin observational-memory was not found in marketplace omtest`.
- `codex plugin add observational-memory@omtest` → `Added plugin observational-memory from marketplace omtest`. Codex copies the plugin to `$CODEX_HOME/plugins/cache/omtest/observational-memory/2026.10.22/`, so a change to the repo needs another `plugin add`. `codex plugin list` shows it `installed, enabled`.
- Skills: the session's skill list holds `observational-memory:observational-memory`. Codex also turns `commands/*.md` into skills, `observational-memory:source-command-status` and the rest, under `.codex-plugin/migrated-command-skills/`.
- Hooks: plugin hooks need no feature flag (`hooks` and `plugins` are stable and on), but they do not run until trusted. Without trust, `codex exec` ran and the state folder stayed empty. The TUI showed `Hooks need review` and `5 hooks are new or changed`, and `/hooks` listed PreCompact, SessionStart, UserPromptSubmit, Stop and SubagentStop from the plugin. Pressing `t` (trust all) wrote five `[hooks.state."observational-memory@omtest:hooks/codex.json:<event>:0:0"]` entries with a `trusted_hash` to `config.toml`. The first exec runs used `--dangerously-bypass-hook-trust` instead. The runs after the trust used no flag.
- MCP: the session lists the `observational-memory` server's `recall` tool (below).

### V4: runtime behaviour

The session ran as `codex exec`, then `codex exec resume <id>`, four turns, with the hooks trusted.

1. Turn 1 set three project facts and ran one shell command. `hooks.log` shows `UserPromptSubmit pass` and then `Stop spawned`. The observer's own `codex exec` logged `UserPromptSubmit child-skip` and `Stop child-skip`, so the recursion guard held. The ledger got one `observations.recorded` entry: four observations citing `L10`, `L21` and `L26`, 1,084 source tokens.
2. Turn 2 added a fourth fact. That was below the threshold, so the observer did not run.
3. Turn 3 ran with `-c model_auto_compact_token_limit=8000`. Codex compacted before the prompt and printed `hook: PreCompact`, `context compacted`, `hook: SessionStart`, `hook: UserPromptSubmit` and `hook: Stop` in that order. `PreCompact catch-up` recorded the fourth fact (`L34`) below the threshold. `SessionStart injected` came 9 s later and wrote `observational-memory.injected` with five observations. The rollout has the `compacted` record at line 45, and then, at line 51, a developer message holding the notes block. With no tools allowed, the model listed all four facts and said the notes block was in its context.
4. Turn 4 asked for `recall` on `f98f9c0bda01`. `codex exec --json` shows an `mcp_tool_call` to `observational-memory`/`recall` that completed with the observation and transcript line `L34`.

### What did not work, and the fixes

- **`recall` was refused under `codex exec`**: `MCP tool call requires approval, but approval policy is never`. The fix gives the tool `annotations` with `readOnlyHint: true`, and Codex then ran it without asking.
- **Tool output was read as JSON text.** Codex 0.163.0 writes `custom_tool_call_output.output` as a list of `{"type": "input_text", "text": ...}` items. The parser now reads their text. `tests/fixtures/codex/rollout-0.163.0.jsonl` is trimmed from this run.
- **The observer's calls filled the session list.** Each `codex exec` the observer ran left a rollout in `$CODEX_HOME/sessions`. The default command now passes `--ephemeral`. One check showed the session count unchanged.
- **Commands do not work in Codex.** The TUI answers `/observational-memory:status` (also with a leading space) with `Unrecognized command`, and no hook runs. Under `codex exec`, UserPromptSubmit blocks the prompt (`hook: UserPromptSubmit Blocked`), but exec never shows the `reason`, nor a `systemMessage`. Codex lists `commands/*.md` as skills, so their text now gives the agent the shell command to run in Codex.
- Not run: SubagentStop and `agents both`, the reflector and the dropper (the threshold was not reached), and interactive TUI compaction (`/compact`).

`python3 -m unittest discover -s tests`: 39 tests OK. The new ones cover the 0.163.0 rollout fixture, the tool-output shapes, the `recall` annotations, `--ephemeral`, and the Codex line in each command file.
