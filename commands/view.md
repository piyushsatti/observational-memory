---
description: "observational-memory: the notes as the next compaction would add them; full lists dropped ones too"
argument-hint: "[full]"
---
observational-memory answers this command from its UserPromptSubmit (Claude Code) or beforeSubmitPrompt (Cursor) hook, before the prompt reaches you. Codex lists this command as a skill instead and does not run it through a hook: there, run `"$HOME/.local/bin/observational-memory" view --harness codex` (with `full` added if the user asked for it) and show the output. Anywhere else, if this text reached you, the hook did not run: say so, and suggest checking that `~/.local/bin/observational-memory` is installed and the plugin's hooks are loaded.
