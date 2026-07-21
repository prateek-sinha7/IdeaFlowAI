"""tests/agents/test_sc001_gate_flag.py — SC-001 name-free update-specs discriminator.

Phase 32-04 closes the SC-001 literal leak AT ITS SOURCE. Today ``review_gate_ready``
carries only the generic ``redoable`` fence, so the FE decides "is this an analyze /
update-specs gate?" by matching the ``prototype-analyze`` / ``prototype-specify`` /
``prototype-plan`` agent-id STRING LITERAL — that IS the leak (RESEARCH §2).

This suite pins the backend half of the fix, mirroring the proven ``redoable`` precedent:

  * The engine stamps a GENERIC ``update_specs_eligible: bool`` + ``artifact_kind: str``
    on ``review_gate_ready.data`` — stamped ONLY at the inline analyze/spec call site,
    defaulting False on the declared/user path (exactly as ``redoable`` defaults False).
  * Eligibility is derived STRUCTURALLY from ``_artifact_kind_for(spec)`` — the same
    kind resolver the call site already uses — NEVER a workflow/agent-id literal (SC-001).
    Only the analyze gate (``summary`` kind) is eligible — MD-01 narrowed this to
    analyze-only; the spec/plan authoring (spec / task_list) and build / validation
    (html_file / validation_report) gates are NOT.
  * Both new keys are added to ``_VOLATILE_STRIP_KEYS`` so the 5 characterization goldens
    stay BYTE-identical (INV-3) — proven empirically by the golden suites, asserted
    structurally here.

Offline-safe: the review pause/resume API (``get_review_event`` / the in-memory state
machine) is real but needs no Bedrock / Postgres / Chromium; no agent is run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.execution_engine.engine import ExecutionEngine


class _FakeSpec:
    """Minimal spec shape for ``_artifact_kind_for`` (reads ``.id`` only)."""

    def __init__(self, agent_id: str) -> None:
        self.id = agent_id
        self.name = agent_id


async def _first_review_ready(gen) -> dict:
    """Pull the first ``review_gate_ready`` event from a ``_run_review_gate`` drive,
    then close the generator (it would otherwise block waiting for user response)."""
    try:
        while True:
            ev = await gen.__anext__()
            if ev.get("type") == "review_gate_ready":
                return ev
    finally:
        await gen.aclose()


# ===========================================================================
# 1. The emit helper stamps the generic discriminator next to ``redoable``
# ===========================================================================


@pytest.mark.asyncio
async def test_inline_call_site_stamps_eligible_true() -> None:
    """The inline analyze/spec call site passes update_specs_eligible=True +
    the resolved artifact_kind → both land on review_gate_ready.data."""
    engine = ExecutionEngine()
    gen = engine._run_review_gate(
        pipeline_run_id="sc001-run-1",
        agent_id="prototype-specify",
        agent_name="Specify",
        output="the spec",
        redoable=True,
        update_specs_eligible=True,
        artifact_kind="spec",
    )
    ev = await _first_review_ready(gen)
    data = ev["data"]
    assert data["update_specs_eligible"] is True
    assert data["artifact_kind"] == "spec"
    # Stamped NEXT TO redoable, not instead of it (the two fences coexist).
    assert data["redoable"] is True


@pytest.mark.asyncio
async def test_declared_path_defaults_eligible_false() -> None:
    """A declared/user-composed gate that reaches the primitive WITHOUT passing the
    flag defaults to update_specs_eligible=False (exactly as redoable defaults False),
    so a non-spec-authoring gate shows no Update-the-Specs affordance."""
    engine = ExecutionEngine()
    gen = engine._run_review_gate(
        pipeline_run_id="sc001-run-2",
        agent_id="some-declared-agent",
        agent_name="Declared",
        output="output",
        # redoable / update_specs_eligible / artifact_kind all omitted → declared path.
    )
    ev = await _first_review_ready(gen)
    data = ev["data"]
    assert data["update_specs_eligible"] is False
    assert data["redoable"] is False
    # The key is ALWAYS present (like redoable) — the FE reads a stable shape.
    assert "artifact_kind" in data


# ===========================================================================
# 2. Eligibility is derived STRUCTURALLY from the artifact kind (name-free)
# ===========================================================================


@pytest.mark.parametrize(
    "agent_id, expected_kind",
    [
        ("prototype-analyze", "summary"),  # unmapped → fallback kind (D-01)
    ],
)
def test_spec_authoring_gates_are_eligible(agent_id, expected_kind) -> None:
    """The analyze gate resolves to the ``summary`` kind, the sole kind in the declared
    eligible-kind set — so eligibility is True WITHOUT naming any agent literal
    (SC-001). MD-01 narrowed this to analyze-only: the spec/plan authoring gates are NO
    LONGER eligible (see test_build_and_validation_gates_are_not_eligible)."""
    engine = ExecutionEngine()
    ek = engine._artifact_kind_for(_FakeSpec(agent_id))
    assert ek == expected_kind
    assert ek in ExecutionEngine._UPDATE_SPECS_ELIGIBLE_KINDS


@pytest.mark.parametrize(
    "agent_id, expected_kind",
    [
        ("prototype-specify", "spec"),  # MD-01: spec authoring gate → NOT eligible
        ("prototype-plan", "task_list"),  # MD-01: plan authoring gate → NOT eligible
        ("prototype-build", "html_file"),
        ("prototype-validate", "validation_report"),
    ],
)
def test_build_and_validation_gates_are_not_eligible(agent_id, expected_kind) -> None:
    """A spec/plan authoring gate (MD-01) or a build / validation gate resolves to a
    kind OUTSIDE the eligible set → NOT eligible. This is the SC-001 generalization:
    only the analyze gate (``summary``) offers the Update-the-Specs affordance; any
    other gate gets none, IFF the structural kind does not match."""
    engine = ExecutionEngine()
    ek = engine._artifact_kind_for(_FakeSpec(agent_id))
    assert ek == expected_kind
    assert ek not in ExecutionEngine._UPDATE_SPECS_ELIGIBLE_KINDS


# ===========================================================================
# 3. Name-freedom — no prototype-* literal ties to the eligibility decision
# ===========================================================================


def test_eligibility_introduces_no_agent_id_literal() -> None:
    """Every engine line that mentions update_specs_eligible derives it from the kind
    resolver, NEVER from a spec.id == "prototype-*" comparison; the eligible-kind set
    holds only artifact kinds, never agent-id literals (SC-001)."""
    import agents.execution_engine.engine as engine_mod

    lines = Path(engine_mod.__file__).read_text().splitlines()
    elig_lines = [ln for ln in lines if "update_specs_eligible" in ln]
    assert elig_lines, "update_specs_eligible never appears in engine.py"
    for ln in elig_lines:
        assert "prototype-" not in ln, (
            f"eligibility line names a workflow/agent literal (SC-001 leak): {ln!r}"
        )
    # The declared eligible-kind set is pure artifact kinds — no agent-id leak.
    assert all(
        "prototype" not in k for k in ExecutionEngine._UPDATE_SPECS_ELIGIBLE_KINDS
    ), "eligible-kind set contains a workflow/agent-id literal (SC-001 leak)"


# ===========================================================================
# 4. Goldens-neutral — both keys are stripped so INV-3 holds
# ===========================================================================


def test_new_keys_are_in_volatile_strip_set() -> None:
    """update_specs_eligible + artifact_kind are additive metadata NOT in the required
    keys, so they must be stripped from the canonical-JSON multiset — mirroring the
    redoable precedent — keeping the 5 characterization goldens byte-identical (INV-3)."""
    from tests.agents.characterization._normalize import _VOLATILE_STRIP_KEYS

    assert "update_specs_eligible" in _VOLATILE_STRIP_KEYS
    assert "artifact_kind" in _VOLATILE_STRIP_KEYS
