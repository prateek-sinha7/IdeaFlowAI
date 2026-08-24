"""SC-001 RECONCILE PROOF — the whole 48-01/48-02/48-03 resume-reconcile path
(content-addressed keys + cumulative common-prefix skip + orphan-fragment
exclusion) drives a BRAND-NEW, NON-prototype ``task_loop`` workflow with ZERO
name-literals under ``backend/agents/execution_engine/`` (RESUME-16 / SC-001, the
ROADMAP SC4 proof).

``CLAUDE.md`` Core Value / SC-001:

    "A brand-new custom workflow can replicate ``prototype`` by manifest +
     AGENT.md only — with zero engine edits."

The sibling ``test_sc001_nonprototype_task_loop.py`` proves a non-prototype
``task_loop`` workflow RUNS clean end-to-end. THIS module proves the RESUME
reconciler behaves identically for that non-prototype workflow — it skips
completed-and-still-present tasks, re-runs the edited/new/divergence-onward
tasks, and EXCLUDES a deleted-completed task's artifact from BOTH the next
task's on-disk context basis AND the assembled deliverable — while keying ONLY
on generic identity (``strategy`` / ``producer_agent`` / ``task_id``), never a
workflow/agent NAME.

The synthetic workflow reuses the ``fixtures/sc001_task_loop/`` declarations:
deliverable ``app.py`` (NOT ``prototype.html``) and the DECLARED task/spec source
steps ``sc001-plan`` / ``sc001-spec`` (NOT the ``prototype-plan`` /
``prototype-specify`` literals). It drives:

  1. the ``task_loop`` STRATEGY through a complete-2-of-4 → gate-edit (delete one
     COMPLETED task + edit one PENDING task + add one NEW task) → resume ladder,
     asserting the EXACT re-run set (the divergence suffix; the surviving prefix
     task skipped) with the deliverable resolved as ``app.py`` (Test 1);
  2. the KERNEL reconciler (``_compute_cumulative_boundaries`` →
     ``_rematerialize_artifacts_to_disk``) over the SAME synthetic step, proving
     the deleted-completed task's ``app.py`` version is EXCLUDED — the boundary
     restores the surviving prefix task's version, not the orphan's (Test 2);
  3. the two-part SC-001 name-freedom acceptance — every capability the workflow
     uses is ``registry.is_registered`` True, and the engine package carries ZERO
     ``sc001`` / ``pipeline_type ==`` / ``spec.id ==`` name-literals (Test 3).

OFFLINE + deterministic (no network, no live Bedrock, no scripted model needed —
the reconcile is driven directly over the strategy + kernel seams). NO production
code is changed by this proof.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.capabilities import task_identity

# The synthetic (NON-prototype) workflow declarations — cloned from the
# sc001_task_loop fixture: an app.py deliverable + DECLARED source/spec steps.
_DELIVERABLE_NAME = "app.py"
_SOURCE_STEP = "sc001-plan"
_BUILD_AGENT = "sc001-build"

# The ORIGINAL 4-task plan (complete 2 of 4 = Alpha + Bravo).
_PLAN_ORIG = (
    "## Task 1: Alpha\nCreate the app skeleton.\n\n"
    "## Task 2: Bravo\nAdd the config loader.\n\n"
    "## Task 3: Charlie\nAdd the request handler.\n\n"
    "## Task 4: Delta\nAdd the response formatter.\n"
)
# The EDITED plan after the gate-edit: delete the COMPLETED Bravo, EDIT the pending
# Charlie (its body changes → its key rotates), ADD a new Echo. Alpha (Task 1) is
# unchanged (its normalized content + ordinal are position-independent → same key).
_PLAN_EDITED = (
    "## Task 1: Alpha\nCreate the app skeleton.\n\n"
    "## Task 2: Charlie\nAdd the request handler WITH auth.\n\n"
    "## Task 3: Delta\nAdd the response formatter.\n\n"
    "## Task 4: Echo\nAdd structured logging.\n"
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sc001_task_loop"


def _keys_for(plan_text: str, upstream_hash: str) -> list[str]:
    """Content-addressed keys for a heading plan under a given upstream hash."""
    from agents.capabilities.task_parsers.heading_tasks import HeadingTasksParser

    tasks = HeadingTasksParser().parse(plan_text)
    ords = task_identity.occurrence_ordinals(tasks)
    return [
        task_identity.compute_task_key(
            upstream_hash, task_identity.normalize_task_content(t), ords[i]
        )
        for i, t in enumerate(tasks)
    ]


@pytest.mark.asyncio
async def test_sc001_reconcile_reruns_exact_set_over_app_py() -> None:
    """SC-001 / RESUME-16: the synthetic NON-prototype task_loop resume re-runs the
    EXACT set on a complete-2-of-4 → gate-edit → resume ladder — the surviving prefix
    task is skipped, the edited/new/divergence-onward tasks re-run — and the deliverable
    resolves to the DECLARED ``app.py`` (never ``prototype.html``).

    Original [Alpha, Bravo, Charlie, Delta]; completed [Alpha, Bravo]. Gate-edit:
    delete COMPLETED Bravo + edit PENDING Charlie + add NEW Echo → current
    [Alpha, Charlie', Delta, Echo]. Common prefix vs completed [Alpha, Bravo]: pos 0
    Alpha==Alpha ✓; pos 1 Charlie' != Bravo → p=1 → skip Alpha, re-run
    [Charlie', Delta, Echo] (task_numbers 2,3,4).
    """
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy
    from agents.workflows.plan import Step, TaskSource
    from tests.agents.test_strategies import _FakeRunner, _FakeSandbox

    # _FakeRunner.upstream_context_hash is a fixed "u-fake" (a list-edit, not a spec
    # edit, so the upstream hash does NOT rotate — the completed keys use the same hash).
    completed = _keys_for(_PLAN_ORIG, "u-fake")  # [Alpha, Bravo, Charlie, Delta]
    completed_ordered = [completed[0], completed[1]]  # Alpha + Bravo ran pre-edit

    sandbox = _FakeSandbox(files={_DELIVERABLE_NAME: "# app.py skeleton\n"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={_SOURCE_STEP: _PLAN_EDITED},  # CURRENT (edited) list
        sandbox=sandbox,
    )
    ctx = SimpleNamespace(
        runner=runner,
        resume_completed_ordered={_BUILD_AGENT: completed_ordered},
        deliverable=SimpleNamespace(name=_DELIVERABLE_NAME),  # NON-prototype deliverable
    )
    step = Step(
        agent_id=_BUILD_AGENT,
        strategy="task_loop",
        task_source=TaskSource(
            kind="parsed", parser="heading_tasks", source_step=_SOURCE_STEP
        ),
    )

    _ = [ev async for ev in TaskLoopStrategy().run(step, ctx)]

    dispatched = [c["task_number"] for c in runner.run_agent_calls]
    assert dispatched == [2, 3, 4], (
        "the synthetic reconcile must SKIP the surviving prefix task (Alpha) and re-run "
        f"EXACTLY the divergence suffix [Charlie', Delta, Echo]; got task_nums {dispatched}"
    )

    # The deliverable resolved to the DECLARED app.py — never prototype.html — for the
    # per-task typed persist AND the validation fix-loop (proves the reconcile path is
    # workflow-name-free at the deliverable seam too).
    assert runner.persist_filenames and all(
        f == _DELIVERABLE_NAME for f in runner.persist_filenames
    ), f"per-task persist did not target {_DELIVERABLE_NAME!r}: {runner.persist_filenames}"
    assert runner.fix_filenames and all(
        f == _DELIVERABLE_NAME for f in runner.fix_filenames
    ), f"fix-loop did not target {_DELIVERABLE_NAME!r}: {runner.fix_filenames}"

    # The deleted COMPLETED task's key (Bravo) is confidently orphaned: absent from the
    # current key set (excluded from the re-run identity) AND never skipped.
    current = _keys_for(_PLAN_EDITED, "u-fake")
    assert completed[1] not in set(current), (
        "the deleted completed task (Bravo) must be ABSENT from the current key set "
        "(confidently orphaned)"
    )


@pytest.mark.asyncio
async def test_sc001_reconcile_orphan_excluded_from_context_and_assembly(tmp_path) -> None:
    """SC-001 / RESUME-16: the KERNEL reconciler EXCLUDES the deleted-completed task's
    ``app.py`` version from BOTH the next task's on-disk context basis AND the assembled
    deliverable — the cumulative boundary restores the SURVIVING prefix task's version,
    not the orphan's — over the synthetic NON-prototype step, name-free.

    The on-disk state after re-materialization is the SINGLE source both the assembled
    deliverable (read from disk) and the next re-run task (its file basis) consume — so
    restoring the boundary (Alpha) version, not the deleted Bravo's, excludes the orphan
    from both at once (Pitfall 4).
    """
    from agents.artifacts.graph import ArtifactGraph
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices
    from agents.workflows.plan import Step, TaskSource
    from app.agents.sandbox import RunSandbox

    from tests.agents.test_restart_resume import (
        _build_rematerialize_ctx,
        _make_session,
        _seed_ref,
    )

    session, _db = _make_session()
    owner, ws = "sc-user", "ws-sc"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    # The graph carries the EDITED (max-version) plan the reconciler re-parses + the
    # upstream 'spec' the build step consumes (its content_hash feeds the upstream hash).
    graph = ArtifactGraph()
    graph.write_ref(
        run_id=run_id, owner_id=owner, workspace_id=ws, kind="task_list",
        producer_step=_SOURCE_STEP, producer_agent=_SOURCE_STEP, task_id=None,
        content=_PLAN_EDITED, location=f"artifact_refs/{_SOURCE_STEP}",
    )
    ectx.artifacts = graph

    engine = ExecutionEngine()
    _rs = RunSandbox(owner, run_id, runs_root=str(tmp_path))
    _rs.ensure()
    ordered = [
        SimpleNamespace(id=_SOURCE_STEP, produces=["task_list"], consumes=[]),
        SimpleNamespace(id=_BUILD_AGENT, produces=[], consumes=["task_list"]),
    ]
    runner = KernelServices(
        engine=engine, ectx=ectx, sandbox=_rs, ordered_agents=ordered,
        user_message="brief", pipeline_run_id=run_id, pipeline_type="sc001_task_loop",
        planning_context={}, attached_skills=None, attached_hooks=None,
        model_id=None, results=[], cancel_event=None,
    )
    ectx.runner = runner

    step = Step(
        agent_id=_BUILD_AGENT,
        strategy="task_loop",
        task_source=TaskSource(
            kind="parsed", parser="heading_tasks", source_step=_SOURCE_STEP
        ),
    )
    compiled = SimpleNamespace(steps=[step])

    # The reconciler's own upstream hash → the completed keys must match it. Alpha
    # survives (Task 1 of both lists); Bravo is the deleted-completed orphan.
    uhash = engine._compute_upstream_context_hash(step, ectx)
    orig_keys = _keys_for(_PLAN_ORIG, uhash)  # [Alpha, Bravo, Charlie, Delta]
    key_alpha, key_bravo = orig_keys[0], orig_keys[1]

    # Durable app.py versions on the store: Alpha's file (v1) + the DELETED Bravo's
    # file (v2, the global-max that must NOT win).
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location=_DELIVERABLE_NAME, content="after-Alpha", version=1,
                    producer_agent=_BUILD_AGENT, task_id=key_alpha)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location=_DELIVERABLE_NAME, content="after-Bravo-DELETED", version=2,
                    producer_agent=_BUILD_AGENT, task_id=key_bravo)
    session.commit()

    # The reconciler computes the boundary from the edited list + the completed cursor
    # (build order [Alpha, Bravo]). p=1 (Alpha survives at index 0, Bravo diverges).
    boundaries = engine._compute_cumulative_boundaries(
        ectx, ordered, compiled, {_BUILD_AGENT: [key_alpha, key_bravo]}
    )
    assert boundaries.get(_BUILD_AGENT) == {
        "restore_nothing": False,
        "boundary_task_id": key_alpha,
    }, (
        "the reconciler must select the SURVIVING prefix task (Alpha) as the boundary — "
        f"got {boundaries.get(_BUILD_AGENT)}"
    )

    await engine._rematerialize_artifacts_to_disk(
        ectx, sandbox, boundary_by_agent=boundaries
    )

    assert sandbox.read(_DELIVERABLE_NAME) == "after-Alpha", (
        "orphan exclusion: the deleted-completed Bravo's app.py version (global-max) must "
        "NOT reach disk; the boundary restores Alpha's version — excluding the orphan "
        "from BOTH the next task's context basis and the assembled deliverable"
    )
    session.close()


def test_sc001_reconcile_zero_engine_name_literals() -> None:
    """SC-001 two-part acceptance: (a) every capability the synthetic reconcile workflow
    uses is ``registry.is_registered`` True (it runs on already-registered capabilities,
    no kernel edit); (b) the engine package carries ZERO ``sc001`` name-literals AND zero
    ``pipeline_type ==`` / ``spec.id ==`` dispatch literals — the kernel is
    workflow-agnostic in NAME across the whole reconcile path (INV-1 / Pitfall 8).
    """
    from agents.capabilities.registry import CapabilityRegistry

    # (a) The workflow uses ONLY already-registered capabilities.
    reg = CapabilityRegistry()
    assert reg.is_registered("strategy", "task_loop"), "task_loop must be registered"
    assert reg.is_registered("strategy", "single_shot"), "single_shot must be registered"
    assert reg.is_registered("deliverable", "single_file"), "single_file must be registered"
    assert reg.is_registered("task_parser", "heading_tasks"), (
        "heading_tasks must be registered"
    )

    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    engine_pkg = repo_root / "backend" / "agents" / "execution_engine"

    from tests.agents._portable_grep import grep_lines_matching, grep_files_matching

    # (b1) ZERO synthetic-workflow name-literals anywhere under the engine package —
    # the reconcile keys on generic identity, never the workflow/agent name.
    hits = grep_lines_matching("sc001", engine_pkg)
    assert hits.returncode != 0 and hits.stdout.strip() == "", (
        f"the engine package must carry ZERO sc001 name-literals; found:\n{hits.stdout}"
    )

    # (b2) ZERO pipeline/spec dispatch literals (the standing INV-1 grep).
    lit = grep_files_matching(r"pipeline_type ==|spec\.id ==", engine_pkg, regex=True)
    assert lit.returncode != 0 and lit.stdout.strip() == "", (
        f"the engine package must carry ZERO name-dispatch literals; found:\n{lit.stdout}"
    )

    # The synthetic fixture (manifest + AGENT.md) lives entirely OUTSIDE the engine
    # package — the workflow runs purely on the workflow-agnostic kernel.
    for rel in (
        "workflow.yaml",
        "sc001-spec/AGENT.md",
        "sc001-plan/AGENT.md",
        "sc001-build/AGENT.md",
    ):
        assert (_FIXTURE_DIR / rel).is_file(), f"missing fixture artifact: {rel}"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
