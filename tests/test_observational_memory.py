"""Tests for bin/observational-memory (V2 on the verification ladder): standard library only, no harness involved.

Run from the repo root:  python3 -m unittest discover -s tests

Every test gets its own HOME in a temp folder, so ~/.local/state/observational-memory is fresh and nothing real is read
or written. The model call is tests/fake_model.py, set as the model command for every harness.
Hook stdin comes from tests/fixtures/<harness>/<event>.json; transcripts are synthetic, built here.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "bin" / "observational-memory"
FAKE = HERE / "fake_model.py"
FIXTURES = HERE / "fixtures"


def load_script():
    loader = importlib.machinery.SourceFileLoader("observational_memory_script", str(SCRIPT))
    spec = importlib.util.spec_from_loader("observational_memory_script", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


mem = load_script()

FILLER = "The synthetic widget module needs its parser split into two files before release. " * 4


# ---------------------------------------------------------------- synthetic transcripts


def claude_lines(start: int, count: int) -> list[dict]:
    """Claude Code transcript lines: prompts, replies with thinking, a tool call and its result, metadata."""
    out = []
    for i in range(start, start + count):
        ts = f"2026-10-22T09:{i % 60:02d}:00Z"
        if i % 4 == 0:
            out.append({"type": "user", "uuid": f"u-{i:04d}", "timestamp": ts, "message": {"role": "user", "content": f"Prompt {i}: {FILLER}"}})
        elif i % 4 == 1:
            content = [{"type": "thinking", "thinking": "SECRET-THINKING"}, {"type": "text", "text": f"Reply {i}: {FILLER}"}, {"type": "tool_use", "id": f"t{i}", "name": "Read", "input": {"file_path": "src/widget.py"}}]
            out.append({"type": "assistant", "uuid": f"u-{i:04d}", "timestamp": ts, "message": {"role": "assistant", "content": content}})
        elif i % 4 == 2:
            content = [{"type": "tool_result", "tool_use_id": f"t{i - 1}", "content": f"def parse(): pass  # {FILLER}"}]
            out.append({"type": "user", "uuid": f"u-{i:04d}", "timestamp": ts, "message": {"role": "user", "content": content}})
        else:
            out.append({"type": "user", "uuid": f"u-{i:04d}", "timestamp": ts, "isMeta": True, "message": {"role": "user", "content": "META-CAVEAT"}})
    return out


def codex_lines(start: int, count: int) -> list[dict]:
    """Codex rollout lines: session meta, injected context, messages, reasoning, a function call and output."""
    out = []
    for i in range(start, start + count):
        ts = f"2026-10-22T10:{i % 60:02d}:00.000Z"
        k = i % 6
        if k == 0:
            out.append({"timestamp": ts, "type": "session_meta", "payload": {"id": "META-ID"}})
        elif k == 1:
            out.append({"timestamp": ts, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>ENV-CONTEXT</environment_context>"}]}})
        elif k == 2:
            out.append({"timestamp": ts, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"Prompt {i}: {FILLER}"}]}})
        elif k == 3:
            out.append({"timestamp": ts, "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "SECRET-REASONING"}]}})
        elif k == 4:
            out.append({"timestamp": ts, "type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": json.dumps({"command": ["ls", "src"]}), "call_id": f"c{i}"}})
        else:
            out.append({"timestamp": ts, "type": "response_item", "payload": {"type": "function_call_output", "call_id": f"c{i - 1}", "output": f"widget.py {FILLER}"}})
    return out


def cursor_lines(start: int, count: int) -> list[dict]:
    """Cursor transcript lines in role/message.content form."""
    out = []
    for i in range(start, start + count):
        role = "user" if i % 2 == 0 else "assistant"
        out.append({"role": role, "message": {"content": [{"type": "text", "text": f"{role} {i}: {FILLER}"}]}})
    return out


BUILDERS = {"claude": claude_lines, "codex": codex_lines, "cursor": cursor_lines}
SESSIONS = {"claude": "s-claude-1", "codex": "s-codex-1", "cursor": "c-cursor-1", "opencode": "ses_opencode1"}


def write_lines(path: Path, lines: list[dict], append: bool = False) -> None:
    with open(path, "a" if append else "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def fixture(harness: str, event: str, **subs) -> str:
    """A fixture's JSON with {placeholders} filled in."""
    data = json.loads((FIXTURES / harness / f"{event}.json").read_text())

    def fill(v):
        if isinstance(v, str):
            for key, value in subs.items():
                v = v.replace("{" + key + "}", str(value))
            return v
        if isinstance(v, list):
            return [fill(x) for x in v]
        if isinstance(v, dict):
            return {k: fill(x) for k, x in v.items()}
        return v

    return json.dumps(fill(data))


class OmCase(unittest.TestCase):
    """A fresh HOME, low thresholds and the fake model for every test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.saved_env = dict(os.environ)
        os.environ["HOME"] = str(self.home)
        os.environ.pop("OBSERVATIONAL_MEMORY_CHILD", None)
        os.environ.pop("OBSERVATIONAL_MEMORY_FAKE", None)
        os.environ["OBSERVATIONAL_MEMORY_SYNC"] = "1"
        fake = [sys.executable, "-I", str(FAKE)]
        mem.save_config(
            {
                "observe_after_tokens": 200,
                "reflect_after_tokens": 200,
                "pool_target_tokens": 10,
                "inject_wait_seconds": 0,
                "model_command": {"claude": fake, "codex": fake, "cursor": fake, "opencode": fake},
            }
        )
        self.work = self.home / "work"
        self.work.mkdir()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved_env)
        self.tmp.cleanup()

    def transcript(self, harness: str, count: int = 12, name: str = "transcript.jsonl") -> Path:
        path = self.work / f"{harness}-{name}"
        write_lines(path, BUILDERS[harness](0, count))
        return path

    def calls(self) -> list[dict]:
        path = self.home / "model-calls.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def hook(self, harness: str, event: str, fixture_event: str | None = None, env: dict | None = None, **subs) -> tuple[str, Path]:
        """Runs `observational-memory hook` as the harness would: a subprocess, fixture JSON on stdin."""
        subs.setdefault("cwd", self.work)
        subs.setdefault("transcript", "")
        subs.setdefault("agent_transcript", "")
        subs.setdefault("prompt", "hello")
        done = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "hook", harness, event],
            input=fixture(harness, fixture_event or event, **subs),
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, "", "a hook writes nothing to stderr")
        return done.stdout.strip(), mem.ledger_path(harness, SESSIONS[harness])

    def entries(self, harness: str, kind: str | None = None) -> list[dict]:
        return [e for e in mem.read_ledger(harness, SESSIONS[harness]) if kind is None or e["type"] == kind]


# ---------------------------------------------------------------- parsers


class TestParsers(OmCase):
    def test_claude_parser_skips_thinking_meta_and_own_notes(self):
        path = self.transcript("claude", 8)
        write_lines(path, [{"type": "user", "uuid": "u-notes", "message": {"role": "user", "content": mem.INSTRUCTIONS}}], append=True)
        sources = mem.read_sources("claude", str(path), None)
        text = "\n".join(mem.render_source(s) for s in sources)
        self.assertEqual([s["id"] for s in sources], ["u-0000", "u-0001", "u-0002", "u-0004", "u-0005", "u-0006"])
        self.assertNotIn("SECRET-THINKING", text)
        self.assertNotIn("META-CAVEAT", text)
        self.assertNotIn("u-notes", text)
        self.assertIn("[Tool result @", text)
        self.assertIn("tool Read", text)

    def test_codex_parser_reads_response_items_only(self):
        sources = mem.read_sources("codex", str(self.transcript("codex", 6)), None)
        self.assertEqual([s["id"] for s in sources], ["L3", "L5", "L6"])
        text = "\n".join(mem.render_source(s) for s in sources)
        for hidden in ("ENV-CONTEXT", "SECRET-REASONING", "META-ID"):
            self.assertNotIn(hidden, text)
        self.assertIn("tool shell", text)

    def test_codex_0_163_rollout(self):
        # Trimmed from a real Codex CLI 0.163.0 run: developer and environment messages, reasoning,
        # the compacted record and the injected notes are not source entries; custom_tool_call_output
        # carries a list of input_text items, read as their text.
        path = str(FIXTURES / "codex" / "rollout-0.163.0.jsonl")
        sources = mem.read_sources("codex", path, None)
        self.assertEqual([s["id"] for s in sources], ["L7", "L8", "L10", "L11", "L12", "L14"])
        self.assertEqual([s["role"] for s in sources], ["User", "Assistant", "Assistant", "Assistant", "Tool result", "Assistant"])
        self.assertIn("pet tortoise", sources[0]["text"])
        self.assertTrue(sources[3]["text"].startswith("tool exec "))
        result = sources[4]["text"]
        self.assertIn("Script completed", result)
        self.assertIn("tortoise-ready", result)
        self.assertNotIn("input_text", result)
        text = "\n".join(mem.render_source(s) for s in sources)
        for hidden in ("SECRET-REASONING", "skills_instructions", "environment_context", mem.NOTES_HEADER):
            self.assertNotIn(hidden, text)

    def test_codex_tool_output_shapes(self):
        self.assertEqual(mem.codex_output_text("plain"), "plain")
        self.assertEqual(mem.codex_output_text([{"type": "input_text", "text": "a"}, {"type": "input_image", "image_url": "x"}]), "a\n[input_image]")
        self.assertEqual(mem.codex_output_text({"content": "c", "success": True}), "c")
        self.assertEqual(mem.codex_output_text({"other": 1}), '{"other": 1}')

    def test_cursor_parser_reads_role_message_content(self):
        sources = mem.read_sources("cursor", str(self.transcript("cursor", 3)), None)
        self.assertEqual([(s["id"], s["role"]) for s in sources], [("L1", "User"), ("L2", "Assistant"), ("L3", "User")])

    def test_malformed_lines_are_skipped(self):
        path = self.transcript("cursor", 2)
        with open(path, "a") as f:
            f.write("not json\n")
        write_lines(path, cursor_lines(3, 1), append=True)
        self.assertEqual([s["id"] for s in mem.read_sources("cursor", str(path), None)], ["L1", "L2", "L4"])


# ---------------------------------------------------------------- ledger and watermark


class TestLedger(OmCase):
    def test_observe_appends_and_moves_the_watermark(self):
        for harness in ("claude", "codex", "cursor"):
            with self.subTest(harness=harness):
                path = self.transcript(harness, 12)
                session = SESSIONS[harness]
                self.assertEqual(mem.observe(harness, session, str(path)), "recorded")
                recorded = self.entries(harness, "observational-memory.observations.recorded")
                self.assertEqual(len(recorded), 1)
                data = recorded[0]["data"]
                every = [s["id"] for s in mem.read_sources(harness, str(path), None)]
                self.assertEqual(data["coversUpToId"], every[-1])
                ids = [o["id"] for o in data["observations"]]
                self.assertTrue(all(mem.MEMORY_ID.match(i) for i in ids))
                # The observation citing an id not in the chunk was rejected.
                self.assertNotIn("Invented", json.dumps(data))
                self.assertEqual(len(ids), len(every))
                for o in data["observations"]:
                    self.assertTrue(set(o["sourceEntryIds"]) <= set(every))
                    self.assertEqual(o["tokenCount"], mem.tokens(len(o["content"])))

                # Nothing new: no call, no entry.
                before = len(self.calls())
                mem.observe(harness, session, str(path))
                self.assertEqual(len(self.entries(harness, "observational-memory.observations.recorded")), 1)
                self.assertEqual(len([c for c in self.calls()[before:] if c["kind"] == "observer"]), 0)

                # New lines: only they are read.
                write_lines(path, BUILDERS[harness](12, 12), append=True)
                fresh = [s["id"] for s in mem.read_sources(harness, str(path), mem.watermark(self.entries(harness), "main"))]
                self.assertTrue(fresh and not set(fresh) & set(every))
                mem.observe(harness, session, str(path))
                observer_calls = [c for c in self.calls() if c["kind"] == "observer"]
                self.assertEqual(observer_calls[-1]["ids"], fresh)

    def test_below_threshold_does_not_call_the_model(self):
        path = self.transcript("claude", 1)
        self.assertEqual(mem.observe("claude", "s-claude-1", str(path)), "below")
        self.assertEqual(self.calls(), [])
        self.assertEqual(mem.observe("claude", "s-claude-1", str(path), force=True), "none")
        self.assertEqual(len(self.entries("claude", "observational-memory.observations.recorded")), 1)

    def test_ledger_is_append_only(self):
        path = self.transcript("claude", 12)
        mem.observe("claude", "s-claude-1", str(path))
        first = mem.ledger_path("claude", "s-claude-1").read_text()
        write_lines(path, claude_lines(12, 12), append=True)
        mem.observe("claude", "s-claude-1", str(path))
        self.assertTrue(mem.ledger_path("claude", "s-claude-1").read_text().startswith(first))

    def test_rewritten_transcript_falls_back_to_searching_for_the_watermark(self):
        path = self.transcript("claude", 8)
        mem.observe("claude", "s-claude-1", str(path))
        mark = mem.watermark(self.entries("claude"), "main")
        # A line put in front moves every offset; the watermark is found by id and hash instead.
        lines = [json.loads(x) for x in path.read_text().splitlines()]
        write_lines(path, [{"type": "summary", "summary": "x"}] + lines + claude_lines(8, 4))
        fresh = mem.read_sources("claude", str(path), mark)
        self.assertEqual([s["id"] for s in fresh], ["u-0008", "u-0009", "u-0010"])

    def test_model_failure_keeps_the_watermark_and_records_the_error(self):
        path = self.transcript("codex", 12)
        os.environ["OBSERVATIONAL_MEMORY_FAKE"] = "fail"
        self.assertEqual(mem.observe("codex", "s-codex-1", str(path)), "error")
        self.assertEqual(self.entries("codex"), [])
        self.assertIn("observer", mem.load_state("codex", "s-codex-1")["lastError"])
        os.environ.pop("OBSERVATIONAL_MEMORY_FAKE")
        self.assertEqual(mem.observe("codex", "s-codex-1", str(path)), "recorded")
        self.assertIsNone(mem.load_state("codex", "s-codex-1")["lastError"])

    def test_empty_run_backs_off_until_another_threshold(self):
        path = self.transcript("cursor", 6)
        os.environ["OBSERVATIONAL_MEMORY_FAKE"] = "empty"
        self.assertEqual(mem.observe("cursor", "c-cursor-1", str(path)), "empty")
        self.assertEqual(mem.observe("cursor", "c-cursor-1", str(path)), "backoff")
        self.assertEqual(len([c for c in self.calls() if c["kind"] == "observer"]), 1)
        self.assertEqual(self.entries("cursor"), [])

    def test_lock_held_means_busy(self):
        path = self.transcript("claude", 12)
        with mem.session_lock("claude", "s-claude-1") as got:
            self.assertTrue(got)
            self.assertTrue(mem.is_busy("claude", "s-claude-1"))
            self.assertEqual(mem.observe("claude", "s-claude-1", str(path)), "busy")
        self.assertFalse(mem.is_busy("claude", "s-claude-1"))

    def test_reflector_then_dropper(self):
        path = self.transcript("claude", 24)
        # Force reads everything without the reflector; a normal turn after that runs it.
        mem.observe("claude", "s-claude-1", str(path), force=True)
        mem.observe("claude", "s-claude-1", str(path))
        kinds = [c["kind"] for c in self.calls()]
        self.assertEqual(kinds[-2:], ["reflector", "dropper"])
        refl = self.entries("claude", "observational-memory.reflections.recorded")
        drops = self.entries("claude", "observational-memory.observations.dropped")
        self.assertEqual(len(refl), 1)
        self.assertEqual(len(drops), 1)
        # The invented id the fake dropper named is filtered out.
        self.assertEqual(len(drops[0]["data"]["observationIds"]), 1)
        folded = mem.fold(self.entries("claude"))
        self.assertNotIn(drops[0]["data"]["observationIds"][0], [o["id"] for o in folded["active"]])
        self.assertEqual(len(folded["dropped"]), 1)
        self.assertTrue(set(refl[0]["data"]["reflections"][0]["supportingObservationIds"]) <= {o["id"] for o in folded["active"] + folded["dropped"]})


# ---------------------------------------------------------------- recursion guard


class TestRecursionGuard(OmCase):
    def test_model_call_sets_observational_memory_child(self):
        mem.observe("claude", "s-claude-1", str(self.transcript("claude", 12)))
        self.assertTrue(self.calls())
        self.assertTrue(all(c["observational_memory_child"] == "1" for c in self.calls()))

    def test_every_hook_exits_at_once_under_observational_memory_child(self):
        expected = {"claude": "", "codex": "{}", "cursor": "{}"}
        events = {
            "claude": ["Stop", "SubagentStop", "PreCompact", "SessionStart", "UserPromptSubmit"],
            "codex": ["Stop", "SubagentStop", "PreCompact", "SessionStart", "UserPromptSubmit"],
            "cursor": ["stop", "subagentStop", "preCompact", "postToolUse", "sessionStart", "beforeSubmitPrompt"],
        }
        mem.save_config({"agents": "both"})
        for harness, names in events.items():
            path = self.transcript(harness, 12)
            for event in names:
                with self.subTest(harness=harness, event=event):
                    out, ledger = self.hook(harness, event, env={"OBSERVATIONAL_MEMORY_CHILD": "1"}, transcript=path, agent_transcript=path, prompt="/observational-memory:status")
                    want = '{"continue": true}' if event == "beforeSubmitPrompt" else expected[harness]
                    self.assertEqual(out, want)
                    self.assertFalse(ledger.exists())
        self.assertEqual(self.calls(), [])
        log = (mem.root() / "hooks.log").read_text().splitlines()
        self.assertEqual(len(log), 16)
        self.assertTrue(all(line.endswith("child-skip") for line in log))


# ---------------------------------------------------------------- hooks: stop, compaction, injection


class TestHooks(OmCase):
    def test_stop_observes_in_each_harness(self):
        for harness, event in (("claude", "Stop"), ("codex", "Stop"), ("cursor", "stop")):
            with self.subTest(harness=harness):
                out, _ = self.hook(harness, event, transcript=self.transcript(harness, 12))
                self.assertEqual(out, "" if harness == "claude" else "{}")
                self.assertEqual(len(self.entries(harness, "observational-memory.observations.recorded")), 1)

    def test_claude_and_codex_inject_at_session_start_compact(self):
        for harness in ("claude", "codex"):
            with self.subTest(harness=harness):
                path = self.transcript(harness, 12)
                self.hook(harness, "PreCompact", transcript=path)  # the catch-up, synchronous under OBSERVATIONAL_MEMORY_SYNC
                out, _ = self.hook(harness, "SessionStart", transcript=path)
                body = json.loads(out)
                self.assertEqual(set(body), {"hookSpecificOutput"})
                self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "SessionStart")
                text = body["hookSpecificOutput"]["additionalContext"]
                self.assertIn(mem.NOTES_HEADER, text)
                self.assertIn("## Observations", text)
                ids = [o["id"] for o in mem.fold(self.entries(harness))["active"]]
                self.assertTrue(all(f"[{i}]" in text for i in ids))
                injected = self.entries(harness, "observational-memory.injected")
                self.assertEqual(len(injected), 1)
                self.assertEqual(injected[0]["data"]["observationIds"], ids)

    def test_session_start_other_than_compact_injects_nothing(self):
        path = self.transcript("claude", 12)
        self.hook("claude", "PreCompact", transcript=path)
        out, _ = self.hook("claude", "SessionStart", fixture_event="SessionStart-startup", transcript=path)
        self.assertEqual(out, "")

    def test_nothing_to_inject_prints_the_noop(self):
        out, _ = self.hook("claude", "SessionStart", transcript=self.transcript("claude", 1))
        self.assertEqual(out, "")
        out, _ = self.hook("codex", "SessionStart", transcript=self.transcript("codex", 1))
        self.assertEqual(out, "{}")

    def test_cursor_injects_once_on_the_next_post_tool_use(self):
        path = self.transcript("cursor", 12)
        out, _ = self.hook("cursor", "postToolUse", transcript=path)
        self.assertEqual(out, "{}")  # no compaction yet
        out, _ = self.hook("cursor", "preCompact", transcript=path)
        self.assertEqual(out, "{}")
        self.assertTrue(mem.load_state("cursor", "c-cursor-1")["pendingInject"])
        out, _ = self.hook("cursor", "postToolUse", transcript=path)
        body = json.loads(out)
        self.assertEqual(set(body), {"additional_context"})
        self.assertIn("## Observations", body["additional_context"])
        out, _ = self.hook("cursor", "postToolUse", transcript=path)
        self.assertEqual(out, "{}")  # once

    def test_cursor_session_start_injects_only_when_pending(self):
        path = self.transcript("cursor", 12)
        out, _ = self.hook("cursor", "sessionStart", transcript=path)
        self.assertEqual(out, "{}")
        self.hook("cursor", "preCompact", transcript=path)
        out, _ = self.hook("cursor", "sessionStart", transcript=path)
        self.assertIn("additional_context", json.loads(out))

    def test_subagents_are_observed_under_their_own_stream(self):
        main = self.transcript("claude", 4)
        agent = self.transcript("claude", 12, name="agent.jsonl")
        out, _ = self.hook("claude", "SubagentStop", transcript=main, agent_transcript=agent)
        self.assertEqual(self.entries("claude"), [])  # agents off by default (om.tsx)
        mem.save_config({"agents": "both"})
        self.hook("claude", "SubagentStop", transcript=main, agent_transcript=agent)
        recorded = self.entries("claude", "observational-memory.observations.recorded")
        self.assertEqual([e["stream"] for e in recorded], ["agent:agent-7f3a"])
        self.assertIsNone(mem.watermark(self.entries("claude"), "main"))
        text = mem.inject("claude", "s-claude-1")
        self.assertIn("(subagent agent-7f)", text)

    def test_hook_error_still_prints_the_noop(self):
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "hook", "codex", "Stop"], input="{not json", capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(done.stdout.strip(), "{}")
        self.assertIn("hook error", (mem.root() / "observational-memory.log").read_text())


# ---------------------------------------------------------------- commands


class TestCommands(OmCase):
    def test_commands_are_answered_in_each_harness(self):
        for harness, event in (("claude", "UserPromptSubmit"), ("codex", "UserPromptSubmit"), ("cursor", "beforeSubmitPrompt")):
            with self.subTest(harness=harness):
                path = self.transcript(harness, 12)
                mem.observe(harness, SESSIONS[harness], str(path))
                out, _ = self.hook(harness, event, transcript=path, prompt="/observational-memory:status")
                body = json.loads(out)
                if harness == "cursor":
                    self.assertEqual(body["continue"], False)
                    text = body["user_message"]
                else:
                    self.assertEqual(body["decision"], "block")
                    text = body["reason"]
                self.assertTrue(text.startswith("observational-memory both"))
                self.assertIn("next observer", text)
                out, _ = self.hook(harness, event, transcript=path, prompt="/observational-memory:view")
                self.assertIn("## Observations", out)

    def test_command_files_tell_codex_what_to_run(self):
        # Codex 0.163 turns commands/*.md into skills (`observational-memory:source-command-<name>`) and its
        # TUI rejects `/observational-memory:<name>` as an unknown command, so the body names the shell command.
        for f in sorted((HERE.parent / "commands").glob("*.md")):
            body = f.read_text()
            self.assertIn("Codex lists this command as a skill", body, f.name)
            self.assertIn('"$HOME/.local/bin/observational-memory" ' + ("mode" if f.stem in ("on", "off", "mode") else f.stem), body, f.name)

    def test_other_prompts_pass_through(self):
        self.assertEqual(self.hook("claude", "UserPromptSubmit", prompt="/omelette please")[0], "")
        self.assertEqual(self.hook("codex", "UserPromptSubmit", prompt="tell me about observational-memory")[0], "{}")
        self.assertEqual(self.hook("cursor", "beforeSubmitPrompt", prompt="/status")[0], '{"continue": true}')

    def test_off_writes_nothing_and_on_starts_from_here(self):
        path = self.transcript("claude", 12)
        out, ledger = self.hook("claude", "UserPromptSubmit", transcript=path, prompt="/observational-memory:off")
        self.assertIn("observational-memory main off", json.loads(out)["reason"])
        self.assertEqual(mem.load_config()["mode"], "off")
        self.hook("claude", "Stop", transcript=path)
        self.hook("claude", "PreCompact", transcript=path)
        self.assertEqual(self.hook("claude", "SessionStart", transcript=path)[0], "")
        self.assertFalse(ledger.exists())
        self.assertEqual(self.calls(), [])

        out, _ = self.hook("claude", "UserPromptSubmit", transcript=path, prompt="/observational-memory:on")
        self.assertIn("observational-memory main both", json.loads(out)["reason"])
        skipped = self.entries("claude", "observational-memory.coverage.skipped")
        self.assertEqual(len(skipped), 1)
        self.hook("claude", "Stop", transcript=path)
        self.assertEqual(self.calls(), [])  # what was said while off is not read
        write_lines(path, claude_lines(12, 12), append=True)
        self.hook("claude", "Stop", transcript=path)
        self.assertTrue(all(i >= "u-0012" for i in self.calls()[0]["ids"]))

    def test_mode_command(self):
        self.assertIn("main both · agents off", mem.mode_command(""))
        self.assertIn("observational-memory agents both", mem.mode_command("agents both"))
        self.assertEqual(mem.load_config()["agents"], "both")
        self.assertIn("observational-memory main off", mem.mode_command("off"))
        self.assertIn("Expected", mem.mode_command("main sideways"))
        out, _ = self.hook("cursor", "beforeSubmitPrompt", prompt="/observational-memory:mode main both")
        self.assertIn("observational-memory main both", json.loads(out)["user_message"])


# ---------------------------------------------------------------- recall and the MCP server


class TestRecall(OmCase):
    def observed(self, harness="claude"):
        path = self.transcript(harness, 12)
        mem.observe(harness, SESSIONS[harness], str(path), force=True)  # force: no reflector or dropper
        obs = self.entries(harness, "observational-memory.observations.recorded")[0]["data"]["observations"]
        lines = path.read_text().splitlines()
        return path, obs, lines

    def test_recall_returns_the_exact_transcript_lines(self):
        for harness in ("claude", "codex", "cursor"):
            with self.subTest(harness=harness):
                _, obs, lines = self.observed(harness)
                o = obs[0]
                text = mem.recall(o["id"])
                self.assertIn("observation (active)", text)
                self.assertIn(o["content"], text)
                sid = o["sourceEntryIds"][0]
                exact = next(x for i, x in enumerate(lines, 1) if mem.line_id(harness, json.loads(x), i) == sid)
                self.assertIn(exact, text.splitlines())

    def test_recall_marks_dropped_and_resolves_reflections(self):
        path = self.transcript("claude", 24)
        mem.observe("claude", "s-claude-1", str(path), force=True)
        mem.observe("claude", "s-claude-1", str(path))
        drop = self.entries("claude", "observational-memory.observations.dropped")[0]["data"]["observationIds"][0]
        self.assertIn("observation (dropped)", mem.recall(drop))
        refl = self.entries("claude", "observational-memory.reflections.recorded")[0]["data"]["reflections"][0]
        text = mem.recall(f"[{refl['id']}]")
        self.assertTrue(text.startswith("reflection "))
        self.assertEqual(text.count("\nobservation ("), len(refl["supportingObservationIds"]))

    def test_recall_rejects_bad_and_unknown_ids(self):
        self.assertTrue(mem.recall("xyz").startswith("invalid id"))
        self.assertTrue(mem.recall("abcdefabcdef").startswith("no observation"))

    def test_mcp_server_over_stdio(self):
        _, obs, _ = self.observed("codex")
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "recall", "arguments": {"id": obs[0]["id"]}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "recall", "arguments": {"id": "nope"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
        ]
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "recall-mcp"], input="".join(json.dumps(m) + "\n" for m in messages), capture_output=True, text=True, env=dict(os.environ), timeout=30)
        replies = [json.loads(x) for x in done.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])  # no reply to the notification
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "observational-memory")
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual([t["name"] for t in replies[1]["result"]["tools"]], ["recall"])
        # Codex refuses an MCP call under `codex exec` (approval policy never) unless the tool is read-only.
        self.assertTrue(replies[1]["result"]["tools"][0]["annotations"]["readOnlyHint"])
        self.assertFalse(replies[1]["result"]["tools"][0]["annotations"]["destructiveHint"])
        self.assertFalse(replies[2]["result"]["isError"])
        self.assertIn(obs[0]["content"], replies[2]["result"]["content"][0]["text"])
        self.assertTrue(replies[3]["result"]["isError"])
        self.assertEqual(replies[4]["error"]["code"], -32601)


# ---------------------------------------------------------------- rendering, status, statusline


class TestPermissions(OmCase):
    def test_state_is_owner_only(self):
        # A state folder left wide open by an older version is tightened on the next write.
        os.chmod(mem.root(), 0o755)
        (mem.root() / "codex").mkdir(mode=0o755)
        os.chmod(mem.root() / "codex", 0o755)
        old_log = mem.root() / "hooks.log"
        old_log.write_text("")
        os.chmod(old_log, 0o644)
        for harness, event in (("claude", "Stop"), ("codex", "Stop"), ("cursor", "preCompact")):
            self.hook(harness, event, transcript=self.transcript(harness, 12))
        mem.update_state("claude", "s-claude-1", probe=True)
        dirs = [mem.root()] + [p for p in mem.root().rglob("*") if p.is_dir()]
        files = [p for p in mem.root().rglob("*") if p.is_file()]
        self.assertGreaterEqual(len(dirs), 4)
        names = {p.name for p in files}
        for want in ("config.json", "hooks.log", "s-claude-1.jsonl", "s-claude-1.state.json", "s-claude-1.lock", "s-codex-1.jsonl", "c-cursor-1.state.json"):
            self.assertIn(want, names)
        for p in dirs:
            self.assertEqual(p.stat().st_mode & 0o777, 0o700, p)
        for p in files:
            self.assertEqual(p.stat().st_mode & 0o777, 0o600, p)

    def test_symlinked_ledger_is_refused(self):
        target = self.work / "elsewhere.jsonl"
        target.write_text("")
        mem.private_dir(mem.root() / "claude")
        mem.ledger_path("claude", "s-claude-1").symlink_to(target)
        with self.assertRaises(OSError):
            mem.append_ledger("claude", "s-claude-1", "observational-memory.test", {})
        self.assertEqual(target.read_text(), "")


class TestRendering(OmCase):
    def test_render_keeps_newest_within_budget_and_says_what_it_left_out(self):
        obs = [{"id": f"{i:012x}", "content": f"note {i} " + "x" * 200, "timestamp": f"2026-10-22 10:{i:02d}", "relevance": "medium", "stream": "main"} for i in range(40)]
        text, _, kept = mem.render_notes({"active": obs, "reflections": []}, 1000)
        self.assertTrue(kept and len(kept) < 40)
        self.assertEqual(kept[-1]["id"], obs[-1]["id"])
        self.assertIn("left out to fit", text)
        self.assertEqual(mem.render_notes({"active": [], "reflections": []}, 1000)[0], "")

    def test_status_and_view(self):
        path = self.transcript("claude", 12)
        mem.observe("claude", "s-claude-1", str(path), force=True)
        status = mem.status_text("claude", "s-claude-1", str(path))
        active = len(mem.fold(self.entries("claude"))["active"])
        self.assertIn(f"observations {active} active", status)
        self.assertIn("next reflector", status)
        full = mem.view_text("claude", "s-claude-1", "full")
        self.assertIn("0 dropped observations", full)
        cli = subprocess.run([sys.executable, "-I", str(SCRIPT), "status"], capture_output=True, text=True, env=dict(os.environ))
        self.assertIn("session claude/s-claude-1", cli.stdout)

    def test_statusline(self):
        path = self.transcript("claude", 12)
        run = lambda: subprocess.run([sys.executable, "-I", str(SCRIPT), "statusline"], input=fixture("claude", "statusline", transcript=path, cwd=self.work), capture_output=True, text=True, env=dict(os.environ)).stdout.strip()  # noqa: E731
        self.assertEqual(run(), "mem O 100% · X 42% · 0 notes")
        mem.observe("claude", "s-claude-1", str(path))
        self.assertRegex(run(), r"^mem O 0% · X 42% · \d+ notes$")
        mem.save_config({"mode": "off"})
        self.assertEqual(run(), "mem off")

    def test_model_command_defaults(self):
        cfg = mem.load_config()
        cfg["model_command"] = {"claude": None, "codex": None, "cursor": None}
        self.assertEqual(mem.model_command(cfg, "claude"), ["claude", "-p", "--model", "sonnet"])
        self.assertEqual(mem.model_command(cfg, "codex")[:2], ["codex", "exec"])
        self.assertIn("--ephemeral", mem.model_command(cfg, "codex"))  # observer calls stay out of `codex resume`
        cfg["model_command"]["opencode"] = None
        self.assertEqual(mem.model_command(cfg, "opencode"), ["opencode", "run", "--standalone"])


# ---------------------------------------------------------------- OpenCode: the plugin's payloads


class TestOpenCode(OmCase):
    """The plugin sends the session's messages (ctx.session.context) on stdin; fixtures are in the shape
    OpenCode 2.1.4 returned in a real session, with synthetic text."""

    SESSION = "ses_opencode1"

    def payload(self, name: str) -> dict:
        return json.loads(fixture("opencode", name, cwd=self.work))

    def mirror(self) -> Path:
        return mem.opencode_transcript(self.SESSION)

    def test_sync_mirrors_messages_once_in_order_and_stops_at_a_streaming_reply(self):
        path = mem.sync_opencode(self.SESSION, self.payload("compacting")["messages"])
        ids = [json.loads(x)["id"] for x in Path(path).read_text().splitlines()]
        self.assertEqual(ids, ["msg_0001user", "msg_0002asst", "msg_0003asst", "msg_0004idle", "msg_0007user"])  # msg_0008asst still streaming
        # After the compaction, context() starts at OpenCode's summary: only what is new is appended.
        mem.sync_opencode(self.SESSION, self.payload("stop-after-compaction")["messages"])
        ids = [json.loads(x)["id"] for x in Path(path).read_text().splitlines()]
        self.assertEqual(ids[5:], ["msg_0005comp", "msg_0006idle", "msg_0008asst", "msg_0009idle"])
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")

    def test_parser_reads_user_text_and_tools_and_skips_reasoning_idle_and_the_native_summary(self):
        mem.sync_opencode(self.SESSION, self.payload("stop")["messages"] + self.payload("stop-after-compaction")["messages"])
        sources = mem.read_sources("opencode", str(self.mirror()), None)
        self.assertEqual([s["id"] for s in sources], ["msg_0001user", "msg_0002asst", "msg_0003asst", "msg_0007user", "msg_0008asst"])
        self.assertEqual([s["role"] for s in sources[:3]], ["User", "Assistant", "Assistant"])
        text = "\n".join(s["text"] for s in sources)
        self.assertIn('tool shell {"command": "ls src"}', text)
        self.assertIn("result: widget.py", text)
        self.assertNotIn("SECRET-REASONING", text)
        self.assertNotIn("NATIVE-SUMMARY", text)
        self.assertRegex(sources[0]["ts"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")

    def test_stop_mirrors_and_observes(self):
        out, ledger = self.hook("opencode", "stop")
        self.assertEqual(out, "{}")
        recorded = self.entries("opencode", "observational-memory.observations.recorded")
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["transcript_path"], str(self.mirror()))
        self.assertTrue(all(s.startswith("msg_") for o in recorded[0]["data"]["observations"] for s in o["sourceEntryIds"]))
        self.assertTrue(ledger.exists())

    def test_compacting_catches_up_and_answers_the_notes_for_the_compaction(self):
        mem.save_config({"observe_after_tokens": 100_000})  # the turn-end observer stays below
        self.hook("opencode", "stop")
        self.assertEqual(self.entries("opencode", "observational-memory.observations.recorded"), [])
        out, _ = self.hook("opencode", "compacting")
        context = json.loads(out)["context"]
        self.assertTrue(context.startswith(mem.OPENCODE_PREAMBLE))
        self.assertIn(mem.NOTES_HEADER, context)
        recorded = self.entries("opencode", "observational-memory.observations.recorded")
        self.assertEqual(len(recorded), 1)  # forced catch-up below the threshold
        for o in recorded[0]["data"]["observations"]:
            self.assertIn(f"[{o['id']}]", context)
        injected = self.entries("opencode", "observational-memory.injected")
        self.assertEqual(injected[-1]["data"]["event"], "compacting")
        self.assertIn("into the compaction input", mem.status_text("opencode", self.SESSION))

    def test_compacting_with_nothing_to_add_prints_the_noop(self):
        os.environ["OBSERVATIONAL_MEMORY_FAKE"] = "empty"
        out, _ = self.hook("opencode", "compacting")
        self.assertEqual(out, "{}")
        self.assertEqual(self.entries("opencode", "observational-memory.injected"), [])

    def test_off_mirrors_and_observes_nothing(self):
        mem.save_config({"mode": "off"})
        for event in ("stop", "compacting"):
            self.assertEqual(self.hook("opencode", event)[0], "{}")
        self.assertFalse(self.mirror().exists())
        self.assertEqual(self.calls(), [])

    def test_child_session_goes_to_the_parent_ledger_only_with_agents_both(self):
        self.assertEqual(self.hook("opencode", "stop", fixture_event="stop-child")[0], "{}")
        self.assertEqual(self.calls(), [])
        mem.save_config({"agents": "both"})
        self.hook("opencode", "stop", fixture_event="stop-child")
        recorded = self.entries("opencode", "observational-memory.observations.recorded")
        self.assertEqual({e["stream"] for e in recorded}, {"agent:ses_child1"})
        self.assertFalse(mem.ledger_path("opencode", "ses_child1").exists())

    def test_recursion_guard(self):
        for event in ("stop", "compacting"):
            out, ledger = self.hook("opencode", event, env={"OBSERVATIONAL_MEMORY_CHILD": "1"})
            self.assertEqual(out, "{}")
            self.assertFalse(ledger.exists())
        self.assertFalse(self.mirror().exists())
        self.assertEqual(self.calls(), [])
        self.assertTrue(all(x.endswith("child-skip") for x in (mem.root() / "hooks.log").read_text().splitlines()))

    def test_recall_returns_the_mirrored_message_and_the_cli_prints_it(self):
        self.hook("opencode", "stop")
        o = self.entries("opencode", "observational-memory.observations.recorded")[0]["data"]["observations"][0]
        lines = self.mirror().read_text().splitlines()
        exact = next(x for x in lines if json.loads(x)["id"] == o["sourceEntryIds"][0])
        self.assertIn(exact, mem.recall(o["id"]).splitlines())
        done = subprocess.run([sys.executable, "-I", str(SCRIPT), "recall", o["id"]], capture_output=True, text=True, env=dict(os.environ), timeout=30)
        self.assertIn(exact, done.stdout.splitlines())

    def test_plugin_is_a_v2_default_export_and_calls_the_handled_events(self):
        js = (HERE.parent / "opencode" / "observational-memory.js").read_text()
        self.assertIn('id: "observational-memory"', js)
        self.assertIn("export default {", js)
        self.assertIn("process.env.OBSERVATIONAL_MEMORY_CHILD", js)
        for call in ('["hook", "opencode", "stop"]', '["hook", "opencode", "compacting"]', '["recall", '):
            self.assertIn(call, js)
        self.assertIn('ctx.session.hook("compaction"', js)
        manifest = json.loads((HERE.parent / "install.json").read_text())
        self.assertIn({"src": "opencode/observational-memory.js", "dest": "~/.config/opencode/plugins/observational-memory.js", "mode": "0644"}, manifest["files"])


if __name__ == "__main__":
    unittest.main()
