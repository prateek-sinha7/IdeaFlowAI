"""EXPERIMENT ONLY (QA-KB-098 analysis): after test_three_runs_produce_three_distinct_log_paths,
list every .logs/*.jsonl the real engine wrote under the harness RUNS_ROOT with a per-event-type
count, to see which run's file the per-agent RunLog entries (engine.py:9633) landed in.
App/test-harness imports are lazy (inside the fixture)."""
import collections
import json
import pathlib

import pytest

OUT = "/private/tmp/claude-502/-Users-bilala-Developer-Projects-VELOCITY-AI-worktrees-feat-user-stories-v2/2d1a1575-310a-48fd-8155-2763a084604d/scratchpad/qa-kb-098/logs.txt"


@pytest.fixture(autouse=True)
def _dump_logs():
    yield
    from tests.agents.live_harness import _RUNS_ROOT

    with open(OUT, "w") as fh:
        for p in sorted(pathlib.Path(_RUNS_ROOT).glob("**/.logs/*.jsonl")):
            kinds = collections.Counter()
            for line in p.read_text().splitlines():
                try:
                    d = json.loads(line)
                except Exception:
                    kinds["<unparseable>"] += 1
                    continue
                kinds[str(d.get("event") or d.get("type") or d.get("kind") or sorted(d)[:3])] += 1
            role = "CHAIN ROOT (sandbox dir name)" if p.stem == p.parent.parent.name else "revision"
            fh.write(f"{p.name}  [{role}]: {sum(kinds.values())} lines {dict(kinds)}\n")
