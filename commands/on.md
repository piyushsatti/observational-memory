---
description: "observational-memory: observe from here on, and add the notes after each compaction summary (every session; same as /observational-memory:mode both)"
---
observational-memory answers this command from its UserPromptSubmit (Claude Code) or beforeSubmitPrompt (Cursor) hook, before the prompt reaches you. Codex lists this command as a skill instead and does not run it through a hook: there, run `"$HOME/.local/bin/observational-memory" mode both --harness codex` and show the output (`--harness codex` starts the newest Codex session from here instead of re-reading what was said while off). Anywhere else, if this text reached you, the hook did not run: say so, and suggest checking that `~/.local/bin/observational-memory` is installed and the plugin's hooks are loaded.
