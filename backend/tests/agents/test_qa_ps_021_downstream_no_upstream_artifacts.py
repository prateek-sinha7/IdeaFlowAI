"""QA-PS-021 — downstream agents in a custom workflow receive no upstream
artifacts and either compensate with wrong content or emit diagnostic output.

Each test pins one card. ISS-733/734/735 were rewritten 2026-09-23 to the
decisions recorded on ESCALATIONS.md#qa-ps-021 (1a + 2a) — their earlier
assertions asked for contracts that were rejected, not for defects:

  * ISS-733 (root, retired as covered by FIX-608/612/615/634) — a `custom`
    step that completes WITHOUT raising but hands back a compensation
    degrades the run; a clean run that wrote no file stays clean (zero file
    writes is `streamed_text`'s declared happy path).
  * ISS-699 (self-narration instance) — the shared trigger:
    `ExecutionEngine._apply_selections` has no `tools` overlay branch, so a
    user-selected `write_files` grant never reaches the compiled step.
  * ISS-734 (won't fix, decision 1a) — the `validation` gate keeps
    validating the run-level deliverable when a declared upstream is
    missing; the run-level zero-coverage signal is what catches it.
  * ISS-735 (decision 2a, no new column) — a revision seeded via
    `parent_run_id` reads the parent's existing `status`/`error`, so a
    degraded parent does not seed as if it were clean.

All run offline (no live LLM / Bedrock / Chromium).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.agents._scripted_model import _drive


# ---------------------------------------------------------------------------
# ISS-733 — a step that completes without raising but hands back a
# compensation must not be reported clean (retired as covered, 2026-09-23).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.issue("ISS-733")
async def test_custom_workflow_compensating_step_is_not_reported_clean():
    """Rewritten to the covered contract (ESCALATIONS.md#qa-ps-021). The old
    assertion — `agents_failed` truthy for a clean 9/9 `custom` run that wrote
    no file — contradicted `custom/workflow.yaml:17-19`: `streamed_text`
    publishes the last step's streamed text, so zero file writes IS the
    declared happy path. What ISS-733 needed is what FIX-612 built into the
    shared completion gate: that clean run stays clean, and the same run whose
    last step completes WITHOUT raising but narrates its missing input
    (ISS-699's reproduced text) is reported degraded.
    """
    from unittest.mock import patch

    import agents.execution_engine.engine as engine_mod
    import tests.agents._scripted_model as _sm
    from tests.agents._scripted_model import _ScriptedTurn
    # Stubs the harness finalizer, whose non-UUID run id would otherwise
    # degrade every run for an unrelated reason and mask the clean half.
    from tests.agents.test_qa_ps_027_placeholder_completion import _clean_finalizer

    narration = "Since I cannot use write_file, I'll compose them as responses to the user:"
    orig = _sm._scripts_for

    def _narrating_last_step(agent_id: str):
        if agent_id == "task-list-planner":  # last step of custom/workflow.yaml
            return [_ScriptedTurn(texts=[narration], usage=(15, 8))]
        return orig(agent_id)

    def _complete(events: list[dict]) -> dict:
        completes = [e for e in events if e.get("type") == "pipeline_complete"]
        assert len(completes) == 1, [e.get("type") for e in events]
        return completes[0]["data"]

    with patch.object(engine_mod, "finalize_terminal_run", _clean_finalizer()):
        clean = _complete(await _drive("custom"))
        _sm._scripts_for = _narrating_last_step
        try:
            compensated = _complete(await _drive("custom"))
        finally:
            _sm._scripts_for = orig

    assert not clean.get("agents_failed") and not clean.get("degraded_reason"), (
        "a clean custom run that wrote no file is streamed_text's declared "
        f"happy path and must stay clean. pipeline_complete.data={clean}"
    )
    assert compensated.get("final_output") == narration, compensated
    assert compensated.get("degraded_reason"), (
        "a step that completed without raising but handed back narration "
        "instead of its deliverable was reported clean (ISS-733). "
        f"pipeline_complete.data={compensated}"
    )


# ---------------------------------------------------------------------------
# ISS-699 — the shared trigger: no `tools` overlay branch in _apply_selections.
# ---------------------------------------------------------------------------


@pytest.mark.issue("ISS-699")
def test_apply_selections_carries_write_files_grant_onto_compiled_step():
    """documentation-agent's prompt (AGENT.md) assumes it can `write_file` a
    README/API-doc/ADR — reproduced 3/3 live (ISS-699): denied that tool, it
    narrates the discovery ("Since I cannot use write_file, I'll compose
    them as responses to the user:") instead of clean deliverable content.

    The composer lets a user select `tools: {write_files: true}` per step,
    but `ExecutionEngine._apply_selections`'s `patch` dict
    (engine.py:12767-12911) has branches for validators/gates/model/retry/
    injects/skills/strategy/fanout/task_source — and NO `tools` branch, so a
    selected write_files grant never reaches the compiled step. This is the
    card's own documented fix direction.
    """
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    base = compile_for_run("custom")
    selections = {"documentation-agent": {"tools": {"write_files": True}}}
    overlaid, _ = ExecutionEngine._apply_selections(base, selections)
    step = next(s for s in overlaid.steps if s.agent_id == "documentation-agent")

    tools = getattr(step, "tools", None)
    granted = bool(tools and (getattr(tools, "write_files", None) or (isinstance(tools, dict) and tools.get("write_files"))))
    assert granted, (
        "user selected tools.write_files=True for documentation-agent, but the "
        "compiled step's tools were not changed — _apply_selections has no "
        f"tools overlay branch (ISS-699/698). step.tools={tools!r}"
    )


# ---------------------------------------------------------------------------
# ISS-734 — won't fix (decision 1a, WONTFIX.md#qa-ps-021): a missing declared
# upstream is caught at the RUN level, not by the validation gate.
# ---------------------------------------------------------------------------


@pytest.mark.issue("ISS-734")
def test_missing_declared_upstream_is_caught_at_run_level_not_by_the_validation_gate():
    """Rewritten to decision 1a (ESCALATIONS.md#qa-ps-021): the gate does
    nothing new. The old assertion (`target is None`) would have handed None
    to `validator.validate(target)` — `_build_validation_target`'s one caller,
    validation.py:100 — for every `gates: [validation]` step. The contract
    instead: the gate keeps validating the run-level deliverable, and the
    missing upstream is caught where the decision put it — the shared
    completion gate's zero-coverage signal (FIX-634) degrades the run.
    """
    from agents.capabilities.deliverables._coverage import dropped_section_reason
    from agents.capabilities.gates.validation import _build_validation_target

    class _Runner:
        def deliverable_context(self, **kwargs):
            return SimpleNamespace(path="output.md", content="run-level content")

    ctx = SimpleNamespace(
        runner=_Runner(),
        deliverable=SimpleNamespace(name="output.md"),
        revision_baseline_static=None,
    )
    target = _build_validation_target(ctx, "downstream-validator", None)
    assert target is not None and target.content == "run-level content", (
        f"the validation gate must keep a real run-level target. target={target!r}"
    )

    # The declared upstream builder produced nothing; the step regenerated
    # the deliverable itself (> the 2000-char narration bound).
    regenerated = "<section><h2>Slide</h2><p>Regenerated.</p></section>" * 60
    assert dropped_section_reason(regenerated, {"prototype-build": ""}), (
        "a deliverable built while its declared upstream produced nothing must "
        "degrade the run — the run-level signal decision 1a relies on"
    )


# ---------------------------------------------------------------------------
# ISS-735 — a revision seeded from a degraded (compensated) parent must know
# it (decision 2a: read the parent's existing status/error, no new column).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.issue("ISS-735")
async def test_custom_revision_seed_carries_the_degraded_parent_status(monkeypatch):
    """Rewritten to decision 2a (ESCALATIONS.md#qa-ps-021) — the old test
    asserted a new `compensated` column. The compensation signals already
    persist: the completion gate's `degraded_reason` lands on the parent's
    `WorkflowRun.status` / `error` (run_commands.py launch driver). What was
    missing is the READ: `_handle_revision` — the one seed seam every revision
    launch routes through (`_drive_revision_to_queue`) — composed the
    revision's context from the parent's deliverable alone, so a degraded
    parent seeded exactly like a clean one. The seed is composed before
    dispatch, so dispatch is stubbed; a clean parent must seed unchanged.
    """
    import app.models.artifact_ref  # noqa: F401 — register tables for create_all
    import app.models.run_event  # noqa: F401
    import app.models.workspace  # noqa: F401
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from agents.execution_engine.engine import ExecutionEngine
    from app.models.artifact_ref import ArtifactRef
    from app.models.database import Base
    from app.models.workflow import WorkflowRun

    db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=db)
    Session = sessionmaker(bind=db)
    monkeypatch.setattr("app.models.database.SessionLocal", Session, raising=False)

    reason = (
        "deliverable is 4210 characters but upstream agent 'report-generator', "
        "one of its declared sources, produced no content at all"
    )
    s = Session()
    for run_id, status, error in (("p-degraded", "degraded", reason), ("p-clean", "completed", None)):
        s.add(WorkflowRun(
            id=run_id, user_id="owner", owner_id="owner", workspace_id="ws", title="t",
            type="custom", status=status, error=error, input="t",
        ))
        s.add(ArtifactRef(
            id=f"ref-{run_id}", run_id=run_id, owner_id="owner", workspace_id="ws",
            kind="deliverable", producer_step="s", producer_agent="task-list-planner",
            content="# Report", content_hash="h", location="artifact_refs/deliverable",
            version=1, visibility="workspace",
        ))
    s.commit()
    s.close()

    seeded: dict[str, str] = {}

    async def _capture_seed(self, **kw):
        seeded[kw["parent_run_id"]] = kw["user_message"]
        return
        yield  # async generator, like execute()

    async def _send(event: dict) -> None:
        pass

    monkeypatch.setattr(ExecutionEngine, "execute", _capture_seed)
    try:
        for parent in ("p-degraded", "p-clean"):
            await ExecutionEngine()._handle_revision(
                parent_run_id=parent, target_artifact_type="custom_output",
                instruction="Tighten the summary", pipeline_run_id=f"rev-{parent}",
                websocket_send_fn=_send, owner_id="owner",
            )
    finally:
        Base.metadata.drop_all(bind=db)

    assert reason in seeded["p-degraded"], (
        "the parent run is persisted degraded with a recorded reason, yet the "
        "custom_revision seed carries neither — it revises compensated content "
        f"as if it were clean (ISS-735). seed={seeded['p-degraded']!r}"
    )
    assert seeded["p-clean"].endswith("=== END REVISION INSTRUCTION ==="), (
        f"a clean parent must seed exactly as before. seed={seeded['p-clean']!r}"
    )


# ---------------------------------------------------------------------------
# ISS-850 — a validator-role step that fully regenerates a deliverable under
# the wrong attribution, when its declared upstream artifact never arrived,
# is caught by neither placeholder_narration_reason nor dropped_section_reason
# (INFERRED, not reproduced live; residual gap after FIX-608/612/615).
# ---------------------------------------------------------------------------


@pytest.mark.issue("ISS-850")
def test_wrong_attribution_full_regeneration_is_flagged_when_upstream_missing():
    """Mirrors the reporter's `ppt-validator`/`prototype-validate` examples
    (BUGS.md#qa-ps-021): a validator/QA-role step finds no upstream artifact
    to validate and, instead of narrating the absence (caught by
    `placeholder_narration_reason`) or dropping a section from a document it
    IS copying (caught by `dropped_section_reason`), regenerates the entire
    deliverable itself under its own attribution — long-form, well-formed
    content with no first-person marker and no upstream source to diff
    against, so today NEITHER signal fires and the shared completion gate
    (`engine.py:7456-7490`) has no third check for "did this content actually
    come from the role that was supposed to produce it".
    """
    from agents.capabilities.deliverables._coverage import dropped_section_reason
    from agents.capabilities.deliverables._placeholder import placeholder_narration_reason

    # A full, well-formed HTML deck the validator regenerated itself — long,
    # no "I can't"/"unable to" markers, nothing a narration check would catch.
    final_output = (
        "<!DOCTYPE html><html><head><title>Deck</title></head><body>"
        + "<section><h2>Slide</h2><p>Regenerated content.</p></section>" * 80
        + "</body></html>"
    )
    assert len(final_output) > 2000  # clears placeholder's narration length bound

    # The declared upstream composer step never produced anything (ISS-850's
    # own trigger: the builder was never granted write_files, or chose not to
    # call it) -- there is no source document to diff sections against.
    upstream_outputs: dict[str, str] = {"composer": ""}

    narration_reason = placeholder_narration_reason(final_output)
    drop_reason = dropped_section_reason(final_output, upstream_outputs)

    assert narration_reason or drop_reason, (
        "a validator-role step regenerated the full deliverable itself under "
        "its own attribution, with its declared upstream artifact never "
        "produced, and the shared completion gate's only two content signals "
        "both missed it: placeholder_narration_reason found no first-person "
        "marker in this well-formed regenerated document "
        f"({narration_reason!r}), and dropped_section_reason found nothing to "
        f"diff against since the upstream source never existed ({drop_reason!r}). "
        "ISS-850: no third, attribution-based signal exists in "
        "engine.py:7456-7490 for this shape."
    )
