"""Unit tests for ``app.api.workflow_builder.gate.ServerGate``.

The save check (``validate``) is a recording stub, so these tests do not reach the
compiler. The Builder_Rules run for real. The model entitlement gate is replaced
by a stub where a test needs it to fire, because its answer depends on the tier
table. Covered: ``HTTPException(422)`` mapped to a ``save_check`` issue, other
statuses propagating, detail clipping, rules and entitlement refused before the
compile, the trust decision on a few examples (Property 9 covers the rest), and
``dry_run`` on unreadable, invalid and valid files.

Requirements: 23.3, 23.4, 23.8, 36.1, 36.2, 48.5, 48.6, 48.13, 49.2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from app.agents.workflow_builder.events import TargetTrust
from app.agents.workflow_builder.ports import GateResult
from app.api.workflow_builder import gate as gate_module
from app.api.workflow_builder.gate import ServerGate

LABEL = "workflow:unit"
MANIFEST: dict[str, Any] = {
    "steps": [{"key": "draft", "agent": "custom-agent", "prompt": "Write the draft."}]
}
# Breaks the step-model rule: the Step_List passed to the gate below is empty.
BAD_MODEL_MANIFEST: dict[str, Any] = {
    "steps": [
        {
            "key": "draft",
            "agent": "custom-agent",
            "prompt": "Write.",
            "model": {"model": "not-on-the-list"},
        }
    ]
}


class _Save:
    """A save check that fails at the trusts in ``failing`` with ``error``."""

    def __init__(
        self,
        failing: frozenset[str] = frozenset(),
        error: HTTPException | None = None,
    ) -> None:
        self.failing = failing
        self.error = error or HTTPException(status_code=422, detail="compile failed")
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, manifest: dict[str, Any] | None, source_label: str, *, trust: str
    ) -> None:
        self.calls.append((source_label, trust))
        if trust in self.failing:
            raise self.error


def _gate(
    save: _Save, *, max_trust: TargetTrust = "user", tier: str = "enterprise"
) -> ServerGate:
    return ServerGate(
        tier=tier, max_trust=max_trust, step_models=(), label=LABEL, validate=save
    )


# --- Save check mapping --------------------------------------------------------------


async def test_check_accepts_at_user_when_save_check_passes() -> None:
    save = _Save()

    result = await _gate(save).check(MANIFEST, requested_trust="user")

    assert result == GateResult(True, "user", ())
    assert save.calls == [(LABEL, "user")]


async def test_check_maps_422_to_save_check_issue_when_compile_fails() -> None:
    save = _Save(frozenset({"user"}), HTTPException(422, "Step 'x' needs a prompt."))

    result = await _gate(save).check(MANIFEST, requested_trust="user")

    assert result.accepted is False
    assert result.trust is None
    assert [(i.rule, i.path, i.message) for i in result.issues] == [
        ("save_check", "", "Step 'x' needs a prompt.")
    ]


async def test_check_reraises_when_save_check_raises_other_status() -> None:
    save = _Save(frozenset({"user"}), HTTPException(500, "boom"))

    with pytest.raises(HTTPException) as caught:
        await _gate(save).check(MANIFEST, requested_trust="user")

    assert caught.value.status_code == 500


async def test_check_uses_fixed_message_when_422_detail_is_not_text() -> None:
    save = _Save(frozenset({"user"}), HTTPException(422, {"loc": ["steps"]}))

    result = await _gate(save).check(MANIFEST, requested_trust="user")

    assert result.issues[0].message == "The workflow manifest was refused."


async def test_check_clips_message_when_422_detail_is_long() -> None:
    save = _Save(frozenset({"user"}), HTTPException(422, "x" * 5000))

    result = await _gate(save).check(MANIFEST, requested_trust="user")

    assert len(result.issues[0].message) == 1003
    assert result.issues[0].message.endswith("...")


async def test_check_rejects_without_save_check_when_manifest_is_empty() -> None:
    save = _Save()

    result = await _gate(save).check({}, requested_trust="user")

    assert result.accepted is False
    assert "non-empty 'steps' list" in result.issues[0].message
    assert save.calls == []


# --- Rules and entitlement come before the compile -----------------------------------


async def test_check_rejects_before_compile_when_builder_rule_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate_module, "_model_entitlement_error", lambda *a, **k: None)
    save = _Save()

    result = await _gate(save).check(BAD_MODEL_MANIFEST, requested_trust="user")

    assert result.accepted is False
    assert [i.rule for i in result.issues] == ["step_model"]
    assert result.issues[0].path == "steps[0].model.model"
    assert save.calls == []


async def test_check_adds_entitlement_issue_and_skips_compile_when_tier_lacks_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, object]] = []

    def entitlement(tier: str, *, manifest: Any = None, **_: Any) -> tuple[int, str]:
        seen.append((tier, manifest))
        return 403, "Your plan does not include this model."

    monkeypatch.setattr(gate_module, "_model_entitlement_error", entitlement)
    save = _Save()

    result = await _gate(save, tier="basic").check(MANIFEST, requested_trust="user")

    assert seen == [("basic", MANIFEST)]
    assert [(i.rule, i.path, i.message) for i in result.issues] == [
        ("model_entitlement", "", "Your plan does not include this model.")
    ]
    assert save.calls == []


async def test_check_lists_rule_and_entitlement_issues_together_when_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gate_module, "_model_entitlement_error", lambda *a, **k: (403, "no")
    )

    result = await _gate(_Save()).check(BAD_MODEL_MANIFEST, requested_trust="user")

    assert [i.rule for i in result.issues] == ["step_model", "model_entitlement"]


# --- Trust decision (examples; Property 9 covers the table) --------------------------


async def test_check_accepts_at_user_when_db_requested_but_user_compiles() -> None:
    save = _Save()

    result = await _gate(save, max_trust="db").check(MANIFEST, requested_trust="db")

    assert (result.accepted, result.trust) == (True, "user")
    assert save.calls == [(LABEL, "user")]


async def test_check_accepts_at_db_when_only_db_compiles_and_db_is_requested_and_allowed() -> (
    None
):
    save = _Save(frozenset({"user"}))

    result = await _gate(save, max_trust="db").check(MANIFEST, requested_trust="db")

    assert (result.accepted, result.trust) == (True, "db")
    assert save.calls == [(LABEL, "user"), (LABEL, "db")]


async def test_check_adds_db_hint_when_only_db_compiles_and_db_was_not_requested() -> (
    None
):
    save = _Save(frozenset({"user"}))

    result = await _gate(save, max_trust="db").check(MANIFEST, requested_trust="user")

    assert result.accepted is False
    assert "target_trust='db'" in result.issues[-1].message
    assert result.issues[-1].rule == "save_check"


async def test_check_never_tries_db_when_max_trust_is_user() -> None:
    save = _Save(frozenset({"user"}))

    result = await _gate(save, max_trust="user").check(MANIFEST, requested_trust="db")

    assert result.accepted is False
    assert save.calls == [(LABEL, "user")]


# --- dry_run ------------------------------------------------------------------------


async def test_dry_run_matches_check_when_file_holds_valid_manifest(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.workflow.json"
    path.write_text('{"steps": [{"key": "d", "agent": "custom-agent", "prompt": "p"}]}')
    save = _Save()

    result = await _gate(save).dry_run(path, requested_trust="user")

    assert (result.accepted, result.trust) == (True, "user")
    assert save.calls == [(LABEL, "user")]


async def test_dry_run_rejects_when_file_is_missing(tmp_path: Path) -> None:
    save = _Save()

    result = await _gate(save).dry_run(tmp_path / "none.json", requested_trust="user")

    assert result.accepted is False
    assert result.issues[0].rule == "save_check"
    assert "could not be read" in result.issues[0].message
    assert save.calls == []


async def test_dry_run_rejects_when_file_is_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "bin.json"
    path.write_bytes(b"\xff\xfe\x00")

    result = await _gate(_Save()).dry_run(path, requested_trust="user")

    assert "could not be read" in result.issues[0].message


async def test_dry_run_reports_position_only_when_json_is_invalid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{\n  "prompt": SECRET_TEXT\n}')
    save = _Save()

    result = await _gate(save).dry_run(path, requested_trust="user")

    assert result.issues[0].message == (
        "The manifest file is not valid JSON (line 2, column 13)."
    )
    assert "SECRET_TEXT" not in result.issues[0].message
    assert save.calls == []


async def test_dry_run_rejects_when_json_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2]")

    result = await _gate(_Save()).dry_run(path, requested_trust="user")

    assert result.issues[0].message == "The manifest file must hold one JSON object."
