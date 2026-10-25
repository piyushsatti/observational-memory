"""A stand-in for the headless model command (`claude -p`, `codex exec`) in observational-memory's tests.

Reads the prompt on stdin and answers like the real observer, reflector or dropper would, from the ids
in the prompt alone. Each call is logged to $HOME/model-calls.jsonl with whether OBSERVATIONAL_MEMORY_CHILD was set, so
the tests can check the recursion guard. OBSERVATIONAL_MEMORY_FAKE=fail exits non-zero; OBSERVATIONAL_MEMORY_FAKE=empty records nothing.
"""

import json
import os
import re
import sys
from pathlib import Path

prompt = sys.stdin.read()
mode = os.environ.get("OBSERVATIONAL_MEMORY_FAKE", "ok")

if "observation agent" in prompt:
    kind = "observer"
    chunk = prompt.split("New conversation chunk:", 1)[-1]
    ids = re.findall(r"\[Source entry id: ([^\]]+)\]", chunk)
elif "reflection agent" in prompt:
    kind = "reflector"
    ids = re.findall(r"^\[([a-f0-9]{12})\]", prompt.split("Current observations:", 1)[-1], re.M)
else:
    kind = "dropper"
    ids = re.findall(r"^\[([a-f0-9]{12})\]", prompt.split("Current observations:", 1)[-1], re.M)

with open(Path(os.path.expanduser("~")) / "model-calls.jsonl", "a") as log:
    log.write(json.dumps({"kind": kind, "observational_memory_child": os.environ.get("OBSERVATIONAL_MEMORY_CHILD"), "ids": ids}) + "\n")

if mode == "fail":
    sys.stderr.write("synthetic failure\n")
    sys.exit(3)

levels = ["medium", "high", "low", "critical"]
if mode == "empty":
    body = {"observations": []} if kind == "observer" else {"reflections": []} if kind == "reflector" else {"drop": []}
elif kind == "observer":
    body = {
        "observations": [
            {"timestamp": "2026-10-22 10:00", "relevance": levels[i % 4], "content": f"Synthetic observation of entry {sid}", "sourceEntryIds": [sid]}
            for i, sid in enumerate(ids)
        ]
        # One that cites an id not in the chunk: the code must reject it.
        + [{"timestamp": "2026-10-22 10:00", "relevance": "high", "content": "Invented", "sourceEntryIds": ["not-a-real-id"]}]
    }
elif kind == "reflector":
    body = {"reflections": [{"content": "Synthetic durable fact drawn from the first observations", "supportingObservationIds": ids[:2]}]}
else:
    body = {"drop": ids[:1] + ["000000000000"]}

# Wrapped in prose and a fence, as real replies sometimes are.
print("Here is the result.\n```json\n" + json.dumps(body) + "\n```")
