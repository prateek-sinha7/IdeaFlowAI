"""tests/agents/test_per_task_capture.py — RESUME-07 generic per-task capture.

Phase 46-02. ``KernelServices.persist_task_html`` (kernel_services.py:1313) is the
per-task capture seam driven by ``task_loop`` (``if hasattr(runner,
"persist_task_html")`` at task_loop.py:293/358). Historically it dual-wrote ONLY the
single DECLARED deliverable file as an ``html_file`` ref. RESUME-07 makes it GENERIC:
after each task, EVERY file that task wrote into the run sandbox is durably captured
per ``task_id`` — the declared file stays a byte-identical ``html_file`` ref and every
OTHER changed file is captured as a ``file_bundle`` ref under the same ``task_id``,
deduped by ``content_hash``, with ``.uploads/`` excluded (Phase-47 fence) and NO new
WS event type (capture is EVENT-FREE, best-effort).

These are offline direct-invocation tests: seed a durable ``workflow_runs`` row, build
a real ``ScopedStore`` over an in-memory SQLite session, a real ``ExecutionContext``
carrying that store + a temp ``RunSandbox``, then invoke ``persist_task_html`` directly
and assert against ``store.tree(run_id)`` (the durable mirror). The seed-durable-then-
invoke scaffolding mirrors ``test_restart_resume.py``'s Phase-45 idiom.

RED on HEAD: the multi-file capture test FAILS (siblings not captured — only the
``html_file`` ref exists). The byte-neutrality test PASSES on HEAD (a single declared
file already produces exactly one ``html_file`` ref) — proving the golden path is
unperturbed.

Offline / in-memory SQLite / no API key / no network.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.agents._scripted_model import _RUNS_ROOT  # noqa: F401 — sets RUNS_ROOT env


def _make_session():
    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base

    db = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=db)
    Session = sessionmaker(bind=db, autocommit=False, autoflush=False)
    return Session(), db


def _seed_workflow_run(session, run_id, *, owner, workspace_id, status="generating"):
    from app.models.workflow import WorkflowRun

    session.add(
        WorkflowRun(
            id=run_id, user_id=owner, owner_id=owner, workspace_id=workspace_id,
            status=status, type="prototype", input="brief",
        )
    )
    session.commit()


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _build_capture_runner(session, tmp_path):
    """Return ``(runner, ectx, sandbox, store)`` for a direct capture invocation.

    The runner is a real ``KernelServices`` bound to a real ``ExecutionEngine`` (only
    its ``_dual_write_artifact`` is exercised), a real ``ExecutionContext`` (its
    ``ArtifactGraph`` + a ``ScopedStore`` over ``session``), and a temp ``RunSandbox``.
    """
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices
    from app.agents.sandbox import RunSandbox

    run_id = f"pt-{uuid.uuid4().hex[:8]}"
    owner = "pt-user"
    workspace_id = "ws-pt"
    _seed_workflow_run(session, run_id, owner=owner, workspace_id=workspace_id)

    ectx = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal=owner)
    ectx.workspace_id = workspace_id
    ectx.scoped_store = ScopedStore(
        owner_id=owner, workspace_id=workspace_id, session=session
    )

    sandbox = RunSandbox(owner, run_id, runs_root=str(tmp_path))
    sandbox.ensure()

    runner = KernelServices(
        engine=ExecutionEngine(),
        ectx=ectx,
        sandbox=sandbox,
        ordered_agents=[],
        user_message="",
        pipeline_run_id=run_id,
        pipeline_type="prototype",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        results=[],
        cancel_event=None,
    )
    return runner, ectx, sandbox, ectx.scoped_store


@pytest.mark.asyncio
async def test_multifile_task_capture_produces_sibling_file_bundles(tmp_path):
    """RESUME-07 (RED on HEAD): a task that wrote the declared file PLUS siblings
    must durably capture the declared file as ``html_file`` AND each sibling as a
    ``file_bundle`` ref under the same ``task_id`` — with ``.uploads/`` NEVER captured.

    On HEAD only the ``html_file`` ref exists (siblings absent) → this FAILS.
    """
    session, _db = _make_session()
    runner, ectx, sandbox, store = _build_capture_runner(session, tmp_path)

    declared = "prototype.html"
    sandbox.write(declared, "<html>declared</html>")
    sandbox.write("part_b.txt", "sibling B content")
    sandbox.write("nested/part_c.md", "# sibling C")
    sandbox.write(".uploads/doc.txt", "uploaded — must never be captured")

    await runner.persist_task_html(task_num=1, agent_id="prototype-build", filename=declared)

    rows = await store.tree(ectx.run_id)

    html_rows = [r for r in rows if r.kind == "html_file"]
    assert len(html_rows) == 1, f"exactly one html_file ref expected, got {len(html_rows)}"
    assert html_rows[0].location == declared
    assert html_rows[0].content == "<html>declared</html>"
    assert html_rows[0].task_id == "1"

    bundle_locs = {r.location for r in rows if r.kind == "file_bundle"}
    assert bundle_locs == {"part_b.txt", "nested/part_c.md"}, (
        f"every non-declared sibling must be captured as file_bundle; got {bundle_locs}"
    )

    # .uploads/ is the Phase-47 fence — NEVER captured (no ref at any .uploads/ path).
    assert not any(r.location.startswith(".uploads/") for r in rows), (
        "a file under .uploads/ must never be captured"
    )

    # Every task-tagged ref carries this task's id.
    for r in rows:
        if r.kind in ("html_file", "file_bundle"):
            assert r.task_id == "1", f"{r.location} should be tagged task_id=1, got {r.task_id!r}"

    session.close()


@pytest.mark.asyncio
async def test_sibling_dedup_no_runaway_versions(tmp_path):
    """RESUME-07 (RED on HEAD): re-invoking capture with an UNCHANGED sibling must
    NOT spawn a new ``file_bundle`` version for that location (content-hash dedup)."""
    session, _db = _make_session()
    runner, ectx, sandbox, store = _build_capture_runner(session, tmp_path)

    declared = "prototype.html"
    sandbox.write(declared, "<html>v1</html>")
    sandbox.write("part_b.txt", "unchanged sibling")

    await runner.persist_task_html(task_num=1, agent_id="prototype-build", filename=declared)
    # Second capture — the sibling content is byte-identical.
    await runner.persist_task_html(task_num=1, agent_id="prototype-build", filename=declared)

    rows = await store.tree(ectx.run_id)
    bundle_b = [r for r in rows if r.kind == "file_bundle" and r.location == "part_b.txt"]
    assert len(bundle_b) == 1, (
        f"an unchanged sibling must not spawn a new version; got {len(bundle_b)} refs"
    )

    session.close()


@pytest.mark.asyncio
async def test_sibling_recaptured_when_content_changes(tmp_path):
    """A sibling whose content CHANGED between captures produces a new version."""
    session, _db = _make_session()
    runner, ectx, sandbox, store = _build_capture_runner(session, tmp_path)

    declared = "prototype.html"
    sandbox.write(declared, "<html>v1</html>")
    sandbox.write("part_b.txt", "first")
    await runner.persist_task_html(task_num=1, agent_id="prototype-build", filename=declared)

    sandbox.write("part_b.txt", "second — edited")
    await runner.persist_task_html(task_num=1, agent_id="prototype-build", filename=declared)

    rows = await store.tree(ectx.run_id)
    bundle_b = [r for r in rows if r.kind == "file_bundle" and r.location == "part_b.txt"]
    assert len(bundle_b) == 2, f"a changed sibling must be recaptured; got {len(bundle_b)}"
    assert {r.content for r in bundle_b} == {"first", "second — edited"}

    session.close()


@pytest.mark.asyncio
async def test_prototype_byte_neutrality_single_html_file(tmp_path):
    """Byte-neutrality (PASSES on HEAD): a task that wrote ONLY the declared file
    produces exactly one ``html_file`` ref and NO ``file_bundle`` — the prototype
    golden path is unperturbed by the generic capture (siblings = ∅)."""
    session, _db = _make_session()
    runner, ectx, sandbox, store = _build_capture_runner(session, tmp_path)

    declared = "prototype.html"
    sandbox.write(declared, "<html>only declared</html>")

    await runner.persist_task_html(task_num=1, agent_id="prototype-build", filename=declared)

    rows = await store.tree(ectx.run_id)
    html_rows = [r for r in rows if r.kind == "html_file"]
    bundle_rows = [r for r in rows if r.kind == "file_bundle"]

    assert len(html_rows) == 1, f"exactly one html_file ref, got {len(html_rows)}"
    assert html_rows[0].location == declared
    assert html_rows[0].content == "<html>only declared</html>"
    assert html_rows[0].task_id == "1"
    assert bundle_rows == [], f"no sibling file_bundle expected, got {bundle_rows}"

    session.close()
