"""QA-KB-094 — the ex_A4 .http runners must answer the conditional gate with the
JSON decision object the gate parses (condition_agent: ask), not a bare word.

Static and DB-free: reads the two runner files and the fixture manifest.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
AUTO = ROOT / "tools/api/runs/run.ex_A4_human_gate_auto.http"
TWIN = ROOT / "tools/api/runs/run.ex_A4_human_gate.http"
MANIFEST = ROOT / "backend/agents/workflows/ex_A4_human_gate/workflow.yaml"

# edited_content value inside a JSON body ("..." with \" escapes) or a printed curl
# hint, where the JS source may double the backslashes (\\\")
_EDIT = re.compile(
    r'edited_content\\?"\s*:\s*\\?"((?:\\\\\\"|\\"|\\\\"|[^"\\])*?)\\?"\s*[},\n]'
)


def _outcomes() -> set[str]:
    spec = yaml.safe_load(MANIFEST.read_text())
    found: list[set[str]] = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("condition_agent") == "ask" and "outcomes" in n:
                found.append(set(n["outcomes"]))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(spec)
    assert found, "fixture has no route with condition_agent: ask"
    return found[0]


def _edits(path: Path) -> list[str]:
    text = path.read_text()
    vals = []
    for line in text.splitlines():
        if "edited_content" not in line or line.lstrip().startswith("//"):
            continue
        m = re.search(r'edited_content\\*"\s*:\s*"((?:[^"\\]|\\.)*)"', line)
        if m:
            vals.append(m.group(1))
    return vals


def _assert_json_decision(path: Path) -> None:
    edits = _edits(path)
    assert edits, f"no edited_content found in {path.name}"
    for raw in edits:
        decoded = raw.replace("\\\\", "\\").replace('\\"', '"')
        try:
            obj = json.loads(decoded)
        except ValueError:
            pytest.fail(
                f"{path.name}: edited_content {raw!r} is not JSON; gate needs "
                '{"decision": <outcome>}'
            )
        assert (
            isinstance(obj, dict) and obj.get("decision") in _outcomes()
        ), f"{path.name}: edited_content {raw!r} lacks a valid decision"


@pytest.mark.issue("ISS-1042")
def test_auto_runner_answers_gate_with_json_decision():
    """ISS-1042 — the auto runner POSTs a JSON decision, not the bare word."""
    _assert_json_decision(AUTO)


@pytest.mark.issue("ISS-1045")
def test_interactive_runner_hint_prints_json_decision():
    """ISS-1045 — the curl hint printed for a human carries a JSON decision."""
    _assert_json_decision(TWIN)


@pytest.mark.issue("ISS-1046")
@pytest.mark.parametrize("runner", [AUTO, TWIN], ids=lambda p: p.name)
def test_a4_assertions_do_not_model_pre_adr0026_engine(runner):
    """ISS-1046 — no stale "fell through" text, and no failure keyed on
    pick-language's own reply (the gate routes on `ask`, not on that reply)."""
    text = runner.read_text()
    assert "fell through" not in text
    assert not re.search(r"does not match decision", text)
