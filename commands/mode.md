---
description: "observational-memory: show or set the mode, for the main conversation and for subagents"
argument-hint: "[main|agents] both|off"
---
observational-memory answers this command from its UserPromptSubmit (Claude Code) or beforeSubmitPrompt (Cursor) hook, before the prompt reaches you. If this text reached you, the hook did not run: say so, and suggest checking that `~/.local/bin/observational-memory` is installed and the plugin's hooks are loaded.
