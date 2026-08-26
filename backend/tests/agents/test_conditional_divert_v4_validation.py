"""V4 (spec 014 / Phase 4 validator, NOT a numbered task — ad hoc harness written
during PASS/FAIL validation): end-to-end divert scenario for
``ex_A3_divert`` (A3) driven through the REAL launch path
(``_launch_run_core`` -> ``_drive_launch_to_queue`` -> ``ExecutionEngine.execute()``)
for BOTH the triggering and the triggered run — not the DB-less
``_scripted_model._drive`` harness T23-T26 use, because AC-05 requires checking
real ``WorkflowRun`` DB rows (status/parent_run_id/owner_id/workspace_id) that
only exist once minted through the real launch core, and AC-11 requires
checking the actual per-run SSE queue, not just the generator's yielded events.

Offline: in-memory SQLite (StaticPool) + scripted models (mirrors
``tests/agents/_scripted_model.py``'s create_runner patch) — no live Bedrock.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.artifact_ref  # noqa: F401
import app.models.gate_events  # noqa: F401
import app.models.hook_runs  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.subagent_run  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
import agents.factory as factory_mod

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


def _scripts_for_divert(agent_id: str):
    # `language` is the conditional step in ex_A3_divert/workflow.yaml, and its
    # outcomes are english (trigger: step) | spanish | dutch (trigger: workflow).
    # Only a WORKFLOW-trigger outcome mints a child run and emits
    # `pipeline_diverted`, so this scenario has to answer spanish or dutch — the
    # earlier `decide`/`divert` pair belonged to a draft of the fixture that no
    # longer exists, and left the gate with no matching outcome (fail-closed, no
    # default_next) so the run ended at gate_blocked instead of diverting.
    if agent_id == "custom-agent:language":
        return [_ScriptedTurn(texts=['{"decision": "spanish"}'], usage=(5, 3))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.fixture
def env(monkeypatch):
    import app.models.database as db_module
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    # run_commands binds its OWN `_get_db` reference at import time (mirrors
    # tests/unit/test_rest_run_launch.py / test_conditional_trigger_budget_t33.py).
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    import app.api.run_commands as rc_module
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    # state_machine._persist and authz.ScopedStore both do a FRESH
    # `from app.models.database import SessionLocal` INSIDE the method body on
    # every call — patching the module attribute (not a bound name) redirects
    # them onto the same in-memory DB.
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _sm._RUNS_ROOT

    yield {"Session": TestingSession, "rc": rc_module}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


@pytest.fixture
def scripted_engine(monkeypatch):
    """Patch create_runner globally (both bound names) to inject a scripted model
    per agent_id, mirroring ``_scripted_model._drive``'s own patch — but left
    live across BOTH the triggering and the triggered run's background drivers
    (not restored between them), since this test drives two real launches."""
    orig_create_runner = factory_mod.create_runner
    orig_engine_create_runner = engine_mod.create_runner

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for_divert(agent_id))
        return orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    try:
        yield
    finally:
        factory_mod.create_runner = orig_create_runner
        engine_mod.create_runner = orig_engine_create_runner


@pytest.mark.asyncio
async def test_divert_end_to_end_AC05_AC11(env, scripted_engine):
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    rc = env["rc"]
    Session = env["Session"]

    OWNER = "v4-owner"
    session = Session()
    session.add(User(id=OWNER, email="v4@example.com", password_hash="x"))
    session.commit()
    session.close()

    user = _FakeUser(id=OWNER)

    # ── Mint + drive the TRIGGERING run for real (mirrors T27's regression test) ──
    mint_result = await rc._launch_run_core(
        content="go",
        pipeline_type="ex_A3_divert",
        agents=[],
        compiled=None,
        od_context=None,
        validated_images=[],
        model_overrides={},
        user=user,
        source_workflow_run_id=None,
        selections=None,
        gate_agent_ids=None,
        attached_skills=None,
        attached_hooks=None,
    )
    first_run_id = mint_result["run_id"]

    # ── Drain the FIRST run's real SSE-equivalent queue (AC-11) ──────────────────
    # `_get_or_create_queue` is idempotent — this is the SAME queue object the
    # driver pushes into and a real SSE endpoint would drain.
    queue = rc._get_or_create_queue(first_run_id)
    first_run_events: list = []
    while True:
        item = await queue.get()
        if item is None:  # driver's terminal sentinel — stream closed
            break
        first_run_events.append(item)

    # Let the driver's own post-loop DB write finish (the `None` sentinel is
    # pushed in a `finally`, AFTER the status-resolution block, so draining to
    # `None` already guarantees the write below has landed).
    task = rc._PIPELINE_TASKS.get(first_run_id)
    if task is not None:
        await task

    types = [e.get("type") for e in first_run_events]
    print("FIRST RUN EVENT TYPES:", types)

    diverted_events = [e for e in first_run_events if e.get("type") == "pipeline_diverted"]
    assert len(diverted_events) == 1, (
        f"AC-11: expected exactly one pipeline_diverted event before the stream "
        f"closed, got {len(diverted_events)}. All types: {types}"
    )
    payload = diverted_events[0]["data"]
    assert set(payload.keys()) >= {
        "pipeline_run_id", "diverted_to_run_id", "diverted_to_workflow",
    }, f"AC-11 payload shape wrong: {payload}"
    assert payload["pipeline_run_id"] == first_run_id
    assert payload["diverted_to_workflow"] == "ex_A3_b_spanish", (
        f"AC-11/R-28: diverted_to_workflow must be the ACTUAL resolved workflow "
        f"id, never the literal 'self' — got {payload['diverted_to_workflow']!r}"
    )
    second_run_id = payload["diverted_to_run_id"]

    # No event of any kind after pipeline_diverted (R-13: no default_next, no
    # further steps dispatched by the first run).
    idx = types.index("pipeline_diverted")
    assert idx == len(types) - 1, (
        f"AC-05/R-13: the first run dispatched further events after diverting: "
        f"{types[idx + 1:]}"
    )

    # ── AC-05: the first run's WorkflowRun.status == 'diverted' ──────────────────
    verify = Session()
    first_row = verify.query(WorkflowRun).filter(WorkflowRun.id == first_run_id).first()
    assert first_row is not None
    print("FIRST ROW status:", first_row.status, "error:", first_row.error)
    assert first_row.status == "diverted", (
        f"AC-05: expected the first run's WorkflowRun.status == 'diverted', got "
        f"{first_row.status!r} (error={first_row.error!r})"
    )

    # ── R-20 (T41): diverted_at_step_id is the instance_id of "language" (the
    # conditional-gate step in ex_A3_divert/workflow.yaml
    # whose `route.outcomes.divert` fired this trigger), and it flows through
    # the SAME _run_response the real GET /api/runs/{id} endpoint uses. ────
    from app.api.runs import _run_response

    assert first_row.diverted_at_step_id == "language", (
        f"R-20: expected diverted_at_step_id == 'decide' on the diverting run's "
        f"own row, got {first_row.diverted_at_step_id!r}"
    )
    get_response = _run_response(first_row, first_run_id)
    assert get_response.diverted_at_step_id == "language", (
        f"R-20: GET response diverted_at_step_id should be 'decide', got "
        f"{get_response.diverted_at_step_id!r}"
    )

    first_owner_id, first_workspace_id = first_row.owner_id, first_row.workspace_id
    verify.close()

    # Let the SECOND run's own background driver finish before checking its row.
    second_task = rc._PIPELINE_TASKS.get(second_run_id)
    if second_task is not None:
        await second_task

    verify2 = Session()
    second_row = verify2.query(WorkflowRun).filter(WorkflowRun.id == second_run_id).first()
    assert second_row is not None, "AC-05: no second WorkflowRun was minted at all"
    assert second_row.parent_run_id == first_run_id
    assert second_row.type == "ex_A3_b_spanish"
    assert second_row.owner_id == first_owner_id
    assert second_row.workspace_id == first_workspace_id
    verify2.close()
