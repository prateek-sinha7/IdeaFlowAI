"""Unit tests for ``app.agents.workflow_builder.draft_tool`` (``propose_draft``).

The tool runs against a real sandbox folder under ``tmp_path``, a ``FakeGate`` with
scripted verdicts and a ``FakeTurnPort``. Covered: tool-use mistakes that are not
gate rejections (path, missing file, invalid JSON, non-object, size), the second
draft in a turn, a stopping turn, rejection counting and the stop after the second
rejection, and the accepted path (events, stage signals, stored draft).

Requirements: 7.1, 23.1, 23.2, 23.10, 23.11, 23.12, 23.13, 23.14, 30.4, 49.2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agents.workflow_builder.draft_tool import (
    ALREADY_APPLIED_MESSAGE,
    MAX_MANIFEST_BYTES,
    STOPPING_MESSAGE,
    DraftToolContext,
    build_draft_tool,
)
from app.agents.workflow_builder.events import (
    BuilderEvent,
    CheckResultEvent,
    DraftApplied,
)
from app.agents.workflow_builder.ports import GateIssue, GateResult
from app.agents.workflow_builder.script_runner import Roots
from app.agents.workflow_builder.stages import GateAccepted, ToolStarted
from tests.fakes.builder_gate import FakeGate, accepted_result, rejected_result
from tests.fakes.builder_turn import FakeTurnPort

MANIFEST: dict[str, Any] = {
    "steps": [{"agent": "custom-agent", "instance_id": "writer", "prompt": "Write."}]
}
PATH = "/workflows/a.workflow.json"


@pytest.fixture
def roots(tmp_path: Path) -> Roots:
    """A sandbox with a ``workflows`` folder and an empty skill folder."""
    sandbox = tmp_path / "sandbox"
    (sandbox / "workflows").mkdir(parents=True)
    skill = tmp_path / "skill"
    skill.mkdir()
    return Roots(sandbox=sandbox, skill=skill)


def _write(
    roots: Roots, name: str = "a.workflow.json", data: bytes | None = None
) -> None:
    payload = data if data is not None else json.dumps(MANIFEST).encode()
    (roots.sandbox / "workflows" / name).write_bytes(payload)


async def _propose(
    turn: FakeTurnPort, gate: FakeGate, roots: Roots, **args: Any
) -> str:
    tool = build_draft_tool(DraftToolContext(turn=turn, gate=gate, roots=roots))
    return str(await tool.ainvoke({"path": PATH, **args}))


def _checks(events: list[BuilderEvent]) -> list[CheckResultEvent]:
    return [e for e in events if isinstance(e, CheckResultEvent)]


# --- Tool-use mistakes are not rejections --------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "/notes.workflow.json",
        "/workflows/a.json",
        "/workflows/sub/a.workflow.json",
        "/workflows/.workflow.json",
        "/workflows/../a.workflow.json",
        "/workflows",
    ],
)
async def test_propose_draft_refuses_path_without_counting_when_path_is_not_a_workflow_file(
    roots: Roots, bad_path: str
) -> None:
    _write(roots)
    _write(roots, "a.json")
    turn, gate = FakeTurnPort(), FakeGate()
    tool = build_draft_tool(DraftToolContext(turn=turn, gate=gate, roots=roots))

    result = str(await tool.ainvoke({"path": bad_path}))

    assert "directly under /workflows/" in result
    assert "Nothing was checked" in result
    assert gate.check_calls == []
    assert turn.report_gate_rejection() == 1  # none of the above was counted
    assert turn.events == []


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(None, "There is no file at that path", id="missing"),
        pytest.param(b"{not json", "The file is not valid JSON", id="bad-json"),
        pytest.param(b"[1, 2]", "must hold one JSON object", id="list"),
        pytest.param(b'"text"', "must hold one JSON object", id="scalar"),
        pytest.param(b"\xff\xfe\x00", "not valid UTF-8 JSON", id="bad-utf8"),
        pytest.param(b"x" * (MAX_MANIFEST_BYTES + 1), "larger than", id="too-large"),
    ],
)
async def test_propose_draft_returns_mistake_text_without_counting_when_file_is_unusable(
    roots: Roots, data: bytes | None, expected: str
) -> None:
    if data is not None:
        _write(roots, data=data)
    turn, gate = FakeTurnPort(), FakeGate()

    result = await _propose(turn, gate, roots)

    assert expected in result
    assert "Nothing was checked" in result
    assert gate.check_calls == []
    assert turn.signals == []
    assert turn.report_gate_rejection() == 1


async def test_propose_draft_reports_position_only_when_json_is_invalid(
    roots: Roots,
) -> None:
    _write(roots, data=b'{\n  "steps": SECRET_PROMPT_TEXT\n}')

    result = await _propose(FakeTurnPort(), FakeGate(), roots)

    assert "line 2, column 12" in result
    assert "SECRET_PROMPT_TEXT" not in result


async def test_propose_draft_returns_mistake_text_when_file_name_is_a_folder(
    roots: Roots,
) -> None:
    (roots.sandbox / "workflows" / "dir.workflow.json").mkdir()
    turn, gate = FakeTurnPort(), FakeGate()
    tool = build_draft_tool(DraftToolContext(turn=turn, gate=gate, roots=roots))

    result = str(await tool.ainvoke({"path": "/workflows/dir.workflow.json"}))

    assert "There is no file at that path" in result
    assert gate.check_calls == []


# --- Stopping turn and second draft --------------------------------------------------


async def test_propose_draft_applies_nothing_when_turn_is_stopping(
    roots: Roots,
) -> None:
    _write(roots)
    turn, gate = FakeTurnPort(), FakeGate()
    turn.stop("time")

    result = await _propose(turn, gate, roots)

    assert result == STOPPING_MESSAGE
    assert gate.check_calls == []
    assert turn.accepted == []
    assert turn.events == []


async def test_propose_draft_applies_nothing_when_turn_stops_during_the_gate_check(
    roots: Roots,
) -> None:
    _write(roots)
    turn = FakeTurnPort()

    class _StoppingGate(FakeGate):
        async def check(
            self, manifest: dict[str, Any], *, requested_trust: Any
        ) -> GateResult:
            turn.stop("cancelled")
            return await super().check(manifest, requested_trust=requested_trust)

    result = await _propose(turn, _StoppingGate(), roots)

    assert result == STOPPING_MESSAGE
    assert turn.accepted == []
    assert [e for e in turn.events if isinstance(e, DraftApplied)] == []


async def test_propose_draft_refuses_second_draft_when_turn_already_applied_one(
    roots: Roots,
) -> None:
    _write(roots)
    turn, gate = FakeTurnPort(), FakeGate()

    first = await _propose(turn, gate, roots)
    second = await _propose(turn, gate, roots)

    assert first.startswith("Applied as revision 1")
    assert second == ALREADY_APPLIED_MESSAGE
    assert len(gate.check_calls) == 1
    assert len(turn.accepted) == 1
    assert turn.report_gate_rejection() == 1


# --- Rejection ----------------------------------------------------------------------


async def test_propose_draft_counts_rejection_and_lists_issues_when_gate_rejects_first_time(
    roots: Roots,
) -> None:
    _write(roots)
    issues = (
        GateIssue("step_model", "steps[0].model", "Model m is not allowed."),
        GateIssue("save_check", "", "Needs a name."),
    )
    turn = FakeTurnPort()
    gate = FakeGate(check=GateResult(False, None, issues))

    result = await _propose(turn, gate, roots)

    lines = result.splitlines()
    assert "attempt 1" in lines[0]
    assert "1 attempt(s) left" in lines[0]
    assert lines[1] == "1. [step_model] steps[0].model: Model m is not allowed."
    assert lines[2] == "2. [save_check] Needs a name."
    assert turn.stop_reasons == []
    check = _checks(turn.events)[0]
    assert (check.verdict, check.errors, check.warnings) == ("invalid", 2, 0)
    assert (check.attempt, check.attempts_left, check.source) == (1, 1, "server_gate")
    assert turn.accepted == []


async def test_propose_draft_stops_turn_when_gate_rejects_second_time(
    roots: Roots,
) -> None:
    _write(roots)
    turn = FakeTurnPort()
    gate = FakeGate(check=[rejected_result("one"), rejected_result("two")])

    first = await _propose(turn, gate, roots)
    second = await _propose(turn, gate, roots)

    assert "attempt 1" in first
    assert "attempt 2" in second
    assert "No attempts are left" in second
    checks = _checks(turn.events)
    assert [(c.attempt, c.attempts_left) for c in checks] == [(1, 1), (2, 0)]
    assert turn.stop_reasons == ["gate_rejections"]


async def test_propose_draft_counts_only_gate_rejections_when_mistakes_come_between(
    roots: Roots,
) -> None:
    turn = FakeTurnPort()
    gate = FakeGate(check=[rejected_result("one"), rejected_result("two")])

    await _propose(turn, gate, roots)  # file missing: not counted
    _write(roots)
    await _propose(turn, gate, roots)  # rejection 1
    _write(roots, data=b"{bad")
    await _propose(turn, gate, roots)  # invalid JSON: not counted

    assert turn.stop_reasons == []
    assert turn.report_gate_rejection() == 2


# --- Acceptance ---------------------------------------------------------------------


async def test_propose_draft_applies_draft_and_emits_events_when_gate_accepts(
    roots: Roots,
) -> None:
    _write(roots)
    turn, gate = FakeTurnPort(), FakeGate()

    result = await _propose(turn, gate, roots)

    assert result == "Applied as revision 1. The canvas now shows it."
    assert [type(e) for e in turn.events] == [CheckResultEvent, DraftApplied]
    check, applied = turn.events
    assert isinstance(check, CheckResultEvent)
    assert (check.verdict, check.errors, check.attempt, check.attempts_left) == (
        "valid",
        0,
        None,
        None,
    )
    assert isinstance(applied, DraftApplied)
    assert applied.revision == 1
    assert applied.target_trust == "user"
    assert applied.manifest == MANIFEST
    assert applied.change_summary.added != []
    assert turn.signals == [
        ToolStarted(name="propose_draft", path=PATH),
        GateAccepted(),
    ]
    stored = turn.accepted[0]
    assert stored.manifest == MANIFEST
    assert stored.source_file == PATH
    assert stored.trust == "user"
    assert list(stored.launch_needs) == applied.launch_needs
    assert turn.report_gate_rejection() == 1


async def test_propose_draft_forwards_requested_trust_and_uses_gate_trust_when_db_requested(
    roots: Roots,
) -> None:
    _write(roots)
    turn = FakeTurnPort()
    gate = FakeGate(check=accepted_result("db"))

    await _propose(turn, gate, roots, target_trust="db", trust_reason="needs exec")

    assert gate.check_calls[0].requested_trust == "db"
    assert gate.check_calls[0].manifest == MANIFEST
    assert turn.accepted[0].trust == "db"


async def test_propose_draft_defaults_to_user_trust_when_no_trust_is_given(
    roots: Roots,
) -> None:
    _write(roots)
    gate = FakeGate(check=accepted_result("user"))

    await _propose(FakeTurnPort(), gate, roots)

    assert gate.check_calls[0].requested_trust == "user"


async def test_propose_draft_computes_change_against_canvas_state_when_canvas_matches(
    roots: Roots,
) -> None:
    _write(roots)
    turn = FakeTurnPort(canvas_state=MANIFEST)

    await _propose(turn, FakeGate(), roots)

    summary = turn.accepted[0].change_summary
    assert (summary.added, summary.removed) == ([], [])
