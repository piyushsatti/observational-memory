---
description: "observational-memory: show or set the mode, for the main conversation and for subagents"
argument-hint: "[main|agents] both|off"
---
observational-memory answers this command from its UserPromptSubmit (Claude Code) or beforeSubmitPrompt (Cursor) hook, before the prompt reaches you. Codex lists this command as a skill instead and does not run it through a hook: there, run `"$HOME/.local/bin/observational-memory" mode` with the user's arguments (`[main|agents] both|off`) and `--harness codex`, and show the output. Anywhere else, if this text reached you, the hook did not run: say so, and suggest checking that `~/.local/bin/observational-memory` is installed and the plugin's hooks are loaded.
