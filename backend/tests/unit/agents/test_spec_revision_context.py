"""tests/agents/test_spec_revision_context.py — the spec-revision prompt contract.

`.planning/BUGFIX-SPEC-REVISION-CONTEXT.md` D1/D3. The revision sub-pipeline tells the
spec writer to "preserve unchanged sections" while the writer has ``consumes: []`` and
``tools: []`` — so the document it is asked to preserve never reaches it. Nothing under
``backend/tests/`` asserted on the revision payload before this file; that gap is why the
defect shipped.

Three properties, all on the scripted-model harness (no Bedrock / Postgres / Chromium):

  * D1 — the specify re-dispatch reaches the PRIOR artifact, asserted for BOTH
    ``_gate_update_specs`` consumer sites (``[live]`` = the post-stream consumer at
    engine.py:4296; ``[reentry]`` = the RESUME-17 gate re-entry at engine.py:3270). The
    restart scenario that exposed the bug enters via the re-entry site, so covering
    only one site would leave the reported path unguarded. M10 (GAPS §0.3/§1 P1 Q4
    rollout) changed the CHANNEL: prototype-specify is migrated, so the PRIOR artifact
    no longer rides the composed prompt — it reaches the agent via a disk read
    (``.agents/01-prototype-specify.md``, its Sandbox Reading Guide) instead. The
    analysis REPORT stays on the composed prompt (row 15a, control, never gated).
  * D1 no-leak — the prior artifact is published for the specify dispatch ONLY, and the
    scratch field is empty once the sub-pipeline returns (consume-once).
  * D3 — the sub-pipeline dispatches on a FRESH ``:rev{N}`` checkpoint thread, so the
    revision no longer depends on the checkpointer replaying the first pass.
"""

from __future__ import annotations

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import ScriptedFakeChatModel  # noqa: E402

# Sentinels no scripted-model output can produce by accident.
PRIOR = "PRIOR-SPEC-SENTINEL ## Workflow Completion Checklist"
REPORT = "REPORT-SENTINEL"
PRIOR_BLOCK = "=== PRIOR ARTIFACT UNDER REVISION ==="


def _revision_triple():
    """Three real text-only agents so ``index=2`` gives specify/plan/analyze structurally.

    M10 (GAPS §0.3/§1 P1 Q4 rollout): this WAS ``PIPELINE_AGENTS["user_stories"][:3]``
    (domain-analyst/epic-architect/story-estimator), used purely structurally per
    INV-1. But ``update_specs``/the spec-revision sub-pipeline this file exists to
    guard (``.planning/BUGFIX-SPEC-REVISION-CONTEXT.md``) is reachable ONLY through
    `prototype`'s own review-gate + ``produces_solution_plan`` wiring — no other
    workflow's agents ever enter ``_run_spec_revision_sub_pipeline`` in production, so
    a user_stories stand-in tests a scenario nothing real exercises. Now that
    `prototype-specify` carries a read tool and a Sandbox Reading Guide for exactly
    this case (M10), the real production agents are both more faithful AND the only
    ones for which the assertions below can be genuinely satisfied (see R2's journal
    "Open items" — this swap was anticipated there, not invented here).
    """
    from agents.loader import load_agent_spec
    from agents.registry import PIPELINE_AGENTS

    return [load_agent_spec(a) for a in PIPELINE_AGENTS["prototype"][:3]]


def _write_ref(ectx, run_id: str, producer_id: str, content: str) -> None:
    ectx.artifacts.write_ref(
        run_id=run_id,
        owner_id="anon",
        workspace_id="ws",
        kind="summary",
        producer_step=producer_id,
        producer_agent=producer_id,
        task_id=None,
        content=content,
        location=f"artifact_refs/{producer_id}",
    )


def _scripted_gate(calls: dict):
    """Gate stub: the first firing requests update_specs, every later firing approves.

    ``**kwargs`` is load-bearing — ``_run_review_gate`` grew ``update_specs_eligible`` /
    ``artifact_kind`` / ``cancel_event``, and the three stale stubs in
    ``test_redo_gate_safety.py`` are red precisely because they pin the old signature.
    The analyzer re-runs INSIDE the sub-pipeline and gates again, so this is called at
    least three times; later calls must approve rather than IndexError.
    """

    async def _gate(
        pipeline_run_id, agent_id, agent_name, output, redoable=False, **kwargs
    ):
        i = calls["n"]
        calls["n"] += 1
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable},
        }
        if i == 0:
            yield {"type": "_gate_update_specs", "analysis_report": REPORT}

    return _gate


async def _drive_revision(mode: str):
    """Drive a REAL ``_run_spec_revision_sub_pipeline`` through one of the two consumer
    sites. Returns ``(prompts_by_agent_id, ectx, thread_ids, ordered)``.

    The sub-pipeline is deliberately NOT stubbed — this file exists to prove what it does.
    """
    from app.agents.sandbox import RunSandbox
    from tests.unit.agents.test_redo_gate_safety import (
        _EngineHarness,
        _drive_agent,
        _make_ectx,
        _text_turn,
    )

    ordered = _revision_triple()
    run_id = f"rev-{mode}"
    calls = {"n": 0}

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(
            _text_turn(f"{aid} regenerated output. ")
        )
    ) as h:
        h.engine._run_review_gate = _scripted_gate(calls)  # type: ignore[assignment]
        ectx = _make_ectx(run_id, gate_agent_ids=[ordered[2].id])
        _write_ref(ectx, run_id, ordered[0].id, PRIOR)
        # M10: the typed-artifact ref above is what the pre-M10 inline paste read from
        # (``_latest_typed_content`` — the FIX-217 channel). The retired channel's
        # replacement is a DISK file — the SAME file `write_agent_output` writes at the
        # end of EVERY real dispatch (``agent_output_relpath``, step index 0 for the
        # first agent) — which prototype-specify's Sandbox Reading Guide now points at.
        # Pre-seed it via the REAL naming function (not a hardcoded guess) so this
        # synthetic harness's disk state matches what a real prior specify pass would
        # have left behind, and so a drift between the naming formula and the guide's
        # documented path fails this test (see the path-contract assertion below).
        from app.agents.sandbox import agent_output_relpath

        prior_relpath = agent_output_relpath(index=0, agent_id=ordered[0].id)
        _sandbox = RunSandbox(ectx.disk_principal, ectx.run_id)
        _sandbox.ensure()
        _sandbox.write(prior_relpath, f"# Spec Writer Agent\n\n{PRIOR}")
        results: list[dict] = []

        if mode == "reentry":
            # Arm the RESUME-17 restart-parked gate: a durable ref for the gated
            # analyzer + the gate_reentry sentinel + a runner for the audit/seed reads.
            from tests.fakes.gate_runner import _FakeGateRunner

            _write_ref(ectx, run_id, ordered[2].id, "PERSISTED ANALYSIS")
            ectx.runner = _FakeGateRunner()
            ectx.gate_reentry = {
                "agent_id": ordered[2].id,
                "artifact_kind": "summary",
                "gate_key": f"{run_id}:{ordered[2].id}",
            }
            results = [{"agent_id": ordered[2].id, "output": "PERSISTED ANALYSIS"}]

        events = await _drive_agent(
            h.engine, ordered[2], ectx, results, ordered, index=2
        )
        thread_ids = list(h.thread_ids)

    prompts: dict[str, list[str]] = {}
    for e in events:
        if e.get("type") == "agent_input":
            d = e["data"]
            prompts.setdefault(d["agent_id"], []).append(d["context_message"])
    return prompts, ectx, thread_ids, ordered


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["live", "reentry"])
async def test_revision_injects_prior_artifact_into_specify_dispatch(mode) -> None:
    """D1, updated by M10 (GAPS §0.3/§1 P1 Q4 rollout): the specify re-dispatch must
    still be ABLE to reach the document it is asked to revise — but prototype-specify
    is now migrated (``prompt_policy: body_only``), so the analysis REPORT (control,
    row 15a, never gated) keeps arriving inline while the PRIOR artifact (world, row
    15b, retired for prototype-specify in M10) is no longer pasted: it reaches the
    agent because it can now read its own ``.agents/01-prototype-specify.md`` (its
    Sandbox Reading Guide says so), which this test's setup pre-seeds to mirror what a
    real prior pass leaves on disk.

    Parametrized over BOTH ``_gate_update_specs`` consumer sites (TRAP 2).
    """
    from agents.loader import load_agent_spec
    from app.agents.sandbox import agent_output_relpath

    prompts, _ectx, _tids, ordered = await _drive_revision(mode)
    specify_id = ordered[0].id

    assert (
        specify_id in prompts
    ), f"the {mode} consumer never re-dispatched the specify agent: {sorted(prompts)}"
    msg = prompts[specify_id][-1]
    assert REPORT in msg, "the analysis report must still reach the specify re-dispatch"
    assert PRIOR not in msg, (
        "D1 (M10): the PRIOR artifact must no longer be PASTED into the specify "
        f"re-dispatch — it retired in favor of a disk read. prompt was:\n{msg[-2000:]}"
    )
    assert (
        PRIOR_BLOCK not in msg
    ), "the prior-artifact block must be gone from a migrated specify agent's message"

    # D1 (M10) path contract: `_drive_revision` seeded the prior artifact at the path
    # the REAL naming function computes for this agent's step-0 output — prove
    # prototype-specify's own Sandbox Reading Guide names that SAME path, not a
    # coincidentally-similar string that would silently diverge if the naming
    # formula (or the guide) ever changes.
    expected_relpath = agent_output_relpath(index=0, agent_id=specify_id)
    guide = load_agent_spec(specify_id).prompt_body or ""
    assert expected_relpath in guide, (
        f"prototype-specify's Sandbox Reading Guide does not name {expected_relpath!r} "
        "— the exact path write_agent_output uses for its own prior output "
        "(a real prior pass leaves the artifact there; a stale guide path means the "
        "agent has no working channel to it at all)"
    )


@pytest.mark.asyncio
async def test_revision_prior_artifact_does_not_leak_to_plan_or_analyze() -> None:
    """D1 no-leak: only the specify dispatch gets the block, and the scratch field is
    empty once the sub-pipeline returns (consume-once, including the error path)."""
    prompts, ectx, _tids, ordered = await _drive_revision("live")
    plan_id, analyze_id = ordered[1].id, ordered[2].id

    for aid in (plan_id, analyze_id):
        for msg in prompts.get(aid, []):
            assert (
                PRIOR_BLOCK not in msg
            ), f"the prior-artifact block leaked into the {aid} dispatch"

    # The analyzer consumes the plan agent only, so PRIOR cannot reach it through the
    # legitimate produces/consumes channel — its absence is a clean no-leak signal.
    for msg in prompts.get(analyze_id, []):
        assert (
            PRIOR not in msg
        ), f"the prior artifact text leaked into the {analyze_id} dispatch"

    # DIRECT attribute access, not getattr-with-default: pre-fix the field does not
    # exist, so this raises AttributeError and the test is a genuine RED instead of
    # passing vacuously against an unimplemented injection.
    assert (
        not ectx.spec_revision_prior_artifact
    ), "the prior-artifact scratch field must be cleared when the sub-pipeline returns"


@pytest.mark.asyncio
async def test_revision_dispatch_uses_a_fresh_checkpoint_thread() -> None:
    """D3: the revision re-run threads ``:rev1``, so it can never be served the first
    pass's checkpoint replay (the same class as the ``:redo{N}`` / ``:retry{n}`` fixes)."""
    _prompts, _ectx, thread_ids, ordered = await _drive_revision("live")
    run_id = "rev-live"
    first_pass = f"{run_id}:{ordered[2].id}"

    assert (
        thread_ids[0] == first_pass
    ), f"expected the first pass on the unsuffixed thread; got {thread_ids}"
    sub_threads = thread_ids[1:]
    assert (
        len(sub_threads) == 3
    ), f"the sub-pipeline must dispatch specify/plan/analyze; got {thread_ids}"
    assert all(
        t.endswith(":rev1") for t in sub_threads
    ), f"every revision dispatch must thread a fresh :rev1 checkpoint; got {sub_threads}"
    assert (
        first_pass not in sub_threads
    ), f"a revision dispatch reused the first pass's thread id: {sub_threads}"
