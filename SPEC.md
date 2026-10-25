# observational-memory spec

observational-memory keeps observational memory beside a harness's own compaction. The spec is upstream [pi-observational-memory](https://github.com/elpapi42/pi-observational-memory) at commit `022da5e` (its V3 ledger model). The behaviour the Claude mod had (`packages/claude-mods/om/hooks/om.tsx`) fills in where upstream says nothing. `bin/observational-memory` implements this spec. Where this port departs from upstream, it says so under [Deviations](#deviations-from-upstream).

## The model

### Source entries

The observer reads **source entries**. These are the person's and the agent's messages, tool calls and tool results from the harness transcript, oldest first. Thinking blocks, harness metadata, injected environment context and observational-memory's own notes are not source entries. Each entry has an id:

| Harness | Transcript | Source id |
|---|---|---|
| Claude Code | JSONL at `transcript_path` | the line's `uuid` |
| Codex | rollout JSONL; only `response_item` records (message, function_call, function_call_output, custom tool calls) | `L<line number>` |
| Cursor | JSONL in `role` / `message.content` form | `L<line number>` |
| OpenCode 2 | `~/.local/state/observational-memory/opencode/transcripts/<session>.jsonl`: a mirror with one OpenCode message per line, as `ctx.session.context` returns it, appended by the hook from the plugin's payload (OpenCode keeps sessions in SQLite, and `context` drops what a compaction covered); `user` and `assistant` messages only, so `idle` and OpenCode's own `compaction` summary are skipped | the message's `id` (`msg_…`) |

An entry's size is estimated as characters / 4 tokens. A tool's input is cut to 300 characters and its result to 600 (om.tsx), because the model's own words carry the decisions.

### Ledger

Each session has one append-only JSONL ledger at `~/.local/state/observational-memory/<harness>/<session>.jsonl`. Lines are never rewritten. Memory is what you get by folding the ledger from the top:

| Entry `type` | `data` | Written by |
|---|---|---|
| `observational-memory.observations.recorded` | `observations[]`, `coversUpToId`, `coversUpTo` {id, hash, offset, line}, `sourceTokens` | observer |
| `observational-memory.reflections.recorded` | `reflections[]`, `coversUpToId`, `observedTokens` | reflector |
| `observational-memory.observations.dropped` | `observationIds[]`, `coversUpToId` | dropper |
| `observational-memory.coverage.skipped` | `coversUpToId`, `coversUpTo` | `/observational-memory:on` after `/observational-memory:off` (om.tsx: read on from here) |
| `observational-memory.injected` | `observationIds[]`, `reflectionIds[]`, `tokens`, `event` | the hook that put the notes into context (upstream's "visible memory") |

Every entry also carries `v`, `at` and, where it applies, `stream` (`main`, or `agent:<id>`) and `transcript_path`.

- **Observation:** `{id, content, timestamp "YYYY-MM-DD HH:MM", relevance low|medium|high|critical, sourceEntryIds[], tokenCount}`.
- **Reflection:** `{id, content, supportingObservationIds[], tokenCount}`.
- **Ids** are deterministic, 12 lowercase hex characters (a sha256 prefix of the content and its sources). They are computed in code, never by the model.
- **Watermark:** `coversUpToId` is a progress marker, not provenance. Provenance is `sourceEntryIds` and `supportingObservationIds`. The observer resumes after the newest watermark for its stream. observational-memory adds `coversUpTo` (the line's byte offset and content hash), so a turn reads only the new bytes and a rewritten file is noticed.
- **Fold:** active observations are those recorded and not dropped. Dropped ones stay in the ledger, and `recall` still finds them.

### Actors

**Observer.** It runs at turn end, detached, under a per-session lockfile.
1. It counts the source tokens after the watermark. Below `observe_after_tokens` it does nothing.
2. It takes the oldest chunk, up to `chunk_tokens`. The chunk always holds at least one entry, so one huge entry cannot stall coverage.
3. It shows the model the current reflections and the newest active observations, within `worker_memory_max_tokens`.
4. It checks every cited source id against the chunk. An observation without a valid one is rejected.
5. It appends one `observational-memory.observations.recorded` entry, and only if at least one observation was accepted. An empty result writes nothing and backs off until another `observe_after_tokens` has arrived. A failed call writes nothing and records `lastError`, so the same stretch is read again.

**Reflector.** It runs at turn end, only when the observer is not due (upstream gives the observer priority), and only once another `reflect_after_tokens` of source has been observed since the last reflection.
- It sees each active observation with a coverage tier: `none`, `partial` (one reflection cites it) or `strong` (two or more).
- It writes only new durable reflections. Each must cite valid active observation ids.
- An empty result backs off by another `reflect_after_tokens`.

**Dropper.** It runs only right after the reflector recorded something, and only when the active pool is over `pool_target_tokens`.
- Its maximum is `ceil((pool − target) / average observation tokens)`. That is a bound, not a goal.
- It can only name active ids, and the code filters and caps them. It appends `observational-memory.observations.dropped` as tombstones.

**Compaction.** At PreCompact, a catch-up observer runs: forced, below the threshold too, at most `catch_up_calls` chunks, without the reflector. The first hook after the compaction then renders the folded memory and adds it to the context. Rendering is deterministic and model-free, and it is upstream's renderer:
- usage instructions, then `## Reflections` and `## Observations`, within `summary_max_tokens`;
- observations are guaranteed half the budget;
- records are picked newest first, and one that does not fit is skipped rather than ending the list;
- a note says how many were left out.

**Recall.** The `recall` tool (MCP server `observational-memory`, from `observational-memory recall-mcp`) takes one id.
- It searches every ledger, newest first.
- For an observation, it returns the observation, `active` or `dropped`, and the **exact transcript lines** of its source ids.
- For a reflection, it returns the reflection and its supporting observations with their lines.
- Output stops at 60,000 characters, and anything left out is named.

### Thresholds

Defaults. Every one can be overridden in `~/.local/state/observational-memory/config.json`.

| Key | Default | From |
|---|---|---|
| `observe_after_tokens` | 10,000 | upstream `observeAfterTokens` (and om.tsx) |
| `reflect_after_tokens` | 20,000 | upstream `reflectAfterTokens` |
| `pool_target_tokens` | 10,000 | upstream `observationsPoolTargetTokens` |
| `chunk_tokens` | 60,000 | upstream observer chunk fallback (and om.tsx `CHUNK_TOKENS`) |
| `summary_max_tokens` | 8,000 | upstream summary fallback (and om.tsx `COMPACT_NOTES_TOKENS`) |
| `worker_memory_max_tokens` | 16,000 | upstream worker-memory fallback |
| `catch_up_calls` | 4 | om.tsx `CATCH_UP_CALLS` |
| `model_timeout_seconds` | 180 | om.tsx |
| `inject_wait_seconds` | 30 | observational-memory: how long SessionStart waits for a running catch-up |

Upstream's `compactAfterTokens` (81,000) and `observationsPoolMaxTokens` (20,000) have no counterpart here; see below.

### Modes and commands

- `mode`: `both`, the default (observe, and add the notes after the harness's summary), or `off` (no observing, nothing added, nothing written to the ledger). `agents` is `both` or `off`, default `off` (om.tsx). Both settings are global, in `config.json`.
- Commands: `/observational-memory:status`, `/observational-memory:view [full]`, `/observational-memory:on`, `/observational-memory:off`, `/observational-memory:mode [main|agents] both|off`. The prompt hook answers them, and the agent never sees them.

### Recursion guard

The observer, reflector and dropper call a headless CLI with `OBSERVATIONAL_MEMORY_CHILD=1` in its environment, from the state folder as working directory. Every `observational-memory hook` call exits at once when `OBSERVATIONAL_MEMORY_CHILD` is set. It prints only the harness's no-op answer and logs `child-skip`. The OpenCode plugin checks the variable first: under it, `setup` registers nothing, so the observer's own `opencode run --standalone` server never calls the hook at all.

### State and logs

Everything lives under `~/.local/state/observational-memory/`: `config.json`, the ledgers, `<session>.state.json` (lastError, model-call count, backoffs, Cursor's pending-inject flag), `<session>.lock`, `hooks.log` (one content-free line per hook call) and `observational-memory.log` (worker errors). Folders are 0700 and files 0600, because the ledger holds text from transcripts. Files are opened with `O_NOFOLLOW`.

## Deviations from upstream

### Everywhere

- **The notes are added after the harness's own summary, not in its place.** No hook in Claude Code, Codex or Cursor can replace the compaction summary. OpenCode 2's `compaction` hook could, by setting `result`; this port keeps OpenCode's summary as well and puts the notes into its input, where the summarizer is told to copy them verbatim (see Per harness). That copy is only as faithful as the summary model. Upstream's compaction is model-free and the notes *are* the summary; here the harness still runs its summarizer, and observational-memory's notes follow it. om.tsx's `observational-memory` mode (notes plus the newest messages, no summary) is gone, so the modes are `both` and `off`.
- **No proactive compaction.** Upstream calls `ctx.compact()` once `compactAfterTokens` of source has built up. Hooks cannot start a compaction, so the harness's own trigger decides.
- **No normal versus full fold.** Upstream applies reflections and drops at compaction only once the visible pool reaches `observationsPoolMaxTokens`, to keep the summary stable. Here every injection renders the full fold, because the summary is not ours to keep stable.
- **The compaction path is not instant.** Upstream's compaction hook never waits on the observer. Here PreCompact starts a catch-up, and SessionStart waits up to `inject_wait_seconds` for it, so the notes reach the compaction point.
- **The model replies with JSON, not tool calls.** A headless CLI gives text back, so the prompts are upstream's three, condensed, asking for one JSON object. Upstream's multi-call "progress receipt" loop is gone: one call per chunk.
- **Model choice.** The command is configurable per harness. The defaults are `claude -p --model <model>` for Claude Code, `codex exec --ephemeral --skip-git-repo-check --sandbox read-only -` (`--ephemeral`, so the observer's calls stay out of `codex resume`) for Codex, for Cursor whichever of those is installed, and `opencode run --standalone` for OpenCode (no `{model}`: `sonnet` is not an OpenCode model name, so OpenCode's default model answers unless the command adds `-m`). `{model}` (default `sonnet`) is substituted. Upstream uses the session's model API in-process.
- **Branches.** Upstream's ledger is branch-local in Pi's session tree. These harnesses have linear transcripts, so it is one ledger per session.
- **Recall searches every observational-memory ledger**, not only the current branch. An MCP server is not told which session called it, and ids are content hashes, so collisions are not a practical concern.
- **`/observational-memory:view`** prints the notes but does not copy them to the clipboard. `/observational-memory:status` shows the observer, reflector and pool gauges and the last injection, but not upstream's visible-versus-full drift counts.

### What this port keeps from om.tsx

- The mode commands (`/observational-memory:on`, `/observational-memory:off`, `/observational-memory:mode main|agents`), with modes global across sessions. Turning observational-memory back on starts observing from the current end of the transcript (`observational-memory.coverage.skipped`), not from everything said while it was off.
- **Per-subagent notes.** With `agents both`, SubagentStop reads the subagent's own transcript in one go (forced, up to `catch_up_calls` chunks), under its own stream `agent:<id>`. Its notes go into the parent session's ledger and are rendered with `(subagent <id>)`. om.tsx observed a subagent when *it* compacted and dropped its notes when it ended. Hooks have no subagent compaction point, so the notes now outlive the subagent and reach the parent's next compaction.
- Thinking blocks are kept from the observer (pi issue #97). Tool text is clipped. A failed call leaves the watermark where it was. There is one model call per session at a time, and a turn that ends meanwhile is picked up by the next.
- The statusline gauges, as a text segment for cc-status: `mem O <unread %> · X <context used %> · <n> notes` (`mem off` when the mode is off). The C gauge (consolidation) is gone with the consolidator, which the reflector and dropper replace.
- Not kept: `/observational-memory:config` (edit `config.json`), `/observational-memory:observe` (`observational-memory observe --force` from a shell), and `/observational-memory:notes` (`/observational-memory:view`).

### Per harness

| | Claude Code | Codex | Cursor | OpenCode 2 |
|---|---|---|---|---|
| Turn end | `Stop` (`async: true`) starts a detached observer | `Stop` starts a detached observer | `stop` starts a detached observer | the plugin sees `session.execution.succeeded` (or `session.idle`) on `ctx.event.subscribe`, and `hook opencode stop` gets the session's messages, mirrors them and starts a detached observer |
| Before compaction | `PreCompact` catch-up | `PreCompact` catch-up | `preCompact` catch-up, and a pending-inject flag is set | the session `compaction` hook, before the summary model call: `hook opencode compacting` mirrors, starts the catch-up and waits up to `inject_wait_seconds` for it |
| After compaction | `SessionStart` matcher `compact`, `additionalContext` | the same | **No post-compaction hook.** The notes go in on the next `postToolUse` (`additional_context`), once. A turn with no tool call gets none until one happens. `sessionStart` also injects if the flag is still set. Untested. | **Nothing after: the notes go into the compaction.** The hook answers `{"context": notes}`; the plugin pushes it onto the summarizer's system prompt with an instruction to copy the notes verbatim, ids included, into a final `## observational-memory` section, so OpenCode's own summary carries them |
| Commands | `UserPromptSubmit` → `{"decision":"block","reason":…}` | the same hook is installed, but Codex has no plugin commands; the skill tells the agent to run `observational-memory status --harness codex` | `beforeSubmitPrompt` → `{"continue":false,"user_message":…}`; the `/observational-memory:` spelling Cursor sends is untested | none; the skill names `observational-memory status --harness opencode` |
| Subagents | `SubagentStop`: `agent_id`, `agent_transcript_path` | `SubagentStop`, same field names assumed | `subagentStop`, field names guessed (`subagent_id` or `agent_id`, `agent_transcript_path`) | a child session (`parentID` from `ctx.session.get`, field name assumed) goes to the parent's ledger as `agent:<child session>` with `agents both`; untested |
| Transcript | documented JSONL | rollout JSONL, format unstable | undocumented JSONL | the plugin's mirror of `ctx.session.context`, in the shape OpenCode 2.1.4 returned |
| Statusline | `observational-memory statusline` segment | none | none | none |
| Recall | MCP server | MCP server | MCP server | the plugin's own `recall` tool (`observational-memory recall <id>`); no MCP entry needed |
| Model call | `claude -p` | `codex exec` | `claude -p` or `codex exec`, whichever exists | `opencode run --standalone`, prompt on stdin, OpenCode's default model; its private server inherits `OBSERVATIONAL_MEMORY_CHILD` and the plugin registers nothing there |
