# observational-memory: verification

One row per run, on the [verification ladder](https://github.com/piyushsatti/workbench/blob/main/CONVENTIONS.md#verification-ladder).

| Level | Claude Code | Codex | Cursor |
|---|---|---|---|
| V0 lint | pass, 2026-10-22: `python3 scripts/lint_plugins.py` → 5 plugins, 0 errors, 0 warnings (catalogs included) | same run | same run |
| V1 native validator | pass, 2026-10-22, Claude Code 2.1.307: `claude plugin validate` | no validator found; lint checks the documented fields | no validator found; lint checks the documented fields |
| V2 script tests | pass, 2026-10-22, Python 3.15.0: 36 tests OK | pass, same run | pass, same run |
| V3 loads without install | not run | not run | not run |
| V4 runtime behaviour | not run | not run | not run |
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
