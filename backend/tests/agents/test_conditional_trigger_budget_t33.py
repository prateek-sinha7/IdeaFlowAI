"""tests/agents/test_conditional_trigger_budget_t33.py — T33 (spec 014 / Phase 4,
plan.md task 5, decision-log #19): regression test for the R-15 budget addendum.

Mints a triggered run via ``KernelServices.run_trigger_workflow`` (T28) — the SAME
kernel delegate the T29 engine ``trigger: workflow`` arm calls — and confirms its
spend is visible in the SAME ``BudgetManager.workspace_ceiling`` aggregate as the
triggering run: ``reserve()``'s existing ``workspace_spent + requested >
workspace_ceiling`` check already scopes both runs together, because the triggered
run's ``ExecutionContext`` carries the UNCONDITIONALLY inherited ``workspace_id``
(and ``owner_id``) — R-15.

This is a "prove no new code is needed" test (the clarification recorded during
``/speckit-clarify``): it drives the EXISTING ``run_trigger_workflow`` →
``_launch_run_core`` mint path plus the EXISTING ``ScopedStore.record_subagent_run``
/ ``workspace_budget_spent`` / ``BudgetManager.reserve`` mechanism end-to-end and
asserts the aggregate already includes both runs. No new budget mechanism is added
by this test, or by T28/T29.

Offline: in-memory SQLite (StaticPool) + a stub execution engine (mirrors
``tests/unit/test_rest_run_launch.py``'s harness) so the triggered run's background
driver mints/persists for real but never calls Bedrock.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the launch path touches on Base.metadata BEFORE create_all
# (mirrors tests/unit/test_rest_run_launch.py's ``env`` fixture).
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.subagent_run  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod


class _StubEngine:
    """No-op execution engine — the triggered run's background driver must not reach
    Bedrock; only the mint (owner_id/workspace_id inheritance) matters here."""

    async def execute(self, **kwargs):
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": ""}}


class _TriggerEctx:
    """Minimal ExecutionContext stand-in carrying only what ``run_trigger_workflow``
    reads (R-15/R-18): ``run_id`` / ``owner_id`` / ``workspace_id`` / ``trigger_depth``."""

    def __init__(self, run_id, owner_id, workspace_id, trigger_depth=0):
        self.run_id = run_id
        self.owner_id = owner_id
        self.workspace_id = workspace_id
        self.trigger_depth = trigger_depth


@pytest.fixture
def env(monkeypatch):
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    # run_commands binds its OWN `_get_db` reference at import time, so both modules
    # need patching (the same reason tests/unit/test_rest_run_launch.py does it).
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    import app.api.run_commands as rc_module
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _StubEngine())

    yield {"Session": TestingSession, "rc": rc_module}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


@pytest.mark.asyncio
async def test_triggered_run_spend_visible_in_triggering_runs_workspace_aggregate(env):
    from agents.authz import ScopedStore
    from agents.execution_engine.budget import BudgetExceeded, BudgetManager
    from agents.execution_engine.kernel_services import KernelServices
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    OWNER = "alice"
    WORKSPACE = "ws-shared"
    TRIGGERING_RUN_ID = "run-triggering"

    session = env["Session"]()
    # Seed the user (WorkflowRun.user_id is FK'd/not-null) + the triggering run's own
    # row, both under the SAME (owner_id, workspace_id) the triggered run must inherit.
    session.add(User(id=OWNER, email="alice@example.com", password_hash="x"))
    session.add(
        WorkflowRun(
            id=TRIGGERING_RUN_ID, user_id=OWNER, owner_id=OWNER, workspace_id=WORKSPACE,
            type="user_stories", status="running", input="go",
        )
    )
    session.commit()
    session.close()

    # ── (1) Mint the triggered run via the T28 kernel delegate ("self" — R-12) ────
    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type = "user_stories"
    ks._ordered_agents = []
    ectx = _TriggerEctx(TRIGGERING_RUN_ID, OWNER, WORKSPACE, trigger_depth=0)

    # ``run_trigger_workflow`` returns ``(run_id, resolved_workflow_id)`` — the second
    # element is what T29's ``pipeline_diverted`` payload reports as
    # ``diverted_to_workflow`` (R-28: the resolved target, never the "self" sentinel).
    # Unpacked the same way engine.py's own call site does.
    triggered_run_id, resolved_workflow_id = await ks.run_trigger_workflow(
        None, ectx, workflow_ref="self"
    )
    # "self" resolves to THIS run's own pipeline_type before minting (R-12/R-28).
    assert resolved_workflow_id == "user_stories"

    # Let the spawned background driver (T29's fire-and-forget mint+drive) settle —
    # this test only needs the row minted; the stub engine yields immediately.
    task = env["rc"]._PIPELINE_TASKS.get(triggered_run_id)
    if task is not None:
        await task

    # ── (2) R-15: the triggered run inherited owner_id/workspace_id UNCONDITIONALLY ──
    verify_session = env["Session"]()
    triggered_row = (
        verify_session.query(WorkflowRun).filter(WorkflowRun.id == triggered_run_id).first()
    )
    assert triggered_row is not None
    assert triggered_row.owner_id == OWNER
    assert triggered_row.workspace_id == WORKSPACE
    assert triggered_row.parent_run_id == TRIGGERING_RUN_ID
    verify_session.close()

    # ── (3) Simulate the TRIGGERED run's own fan-out spend — recorded under ITS OWN
    # run_id, but the SAME (owner_id, workspace_id) it inherited from the triggering
    # run. This is exactly what a real fan-out inside that run would do via the
    # EXISTING ScopedStore.record_subagent_run writer — no new mechanism.
    record_session = env["Session"]()
    triggered_store = ScopedStore(owner_id=OWNER, workspace_id=WORKSPACE, session=record_session)
    for _ in range(3):
        await triggered_store.record_subagent_run(
            triggered_run_id, parent_step="fan", worker_agent="w",
            depth=0, isolation="shared_read", status="complete",
        )
    record_session.close()

    # ── (4) THE ASSERTION: the TRIGGERING run's own workspace_budget_spent() read
    # (the aggregate reserve() checks before a spawn) already sees the triggered
    # run's spend — same owner_id + workspace_id, with NO knowledge of the
    # triggered run's id required.
    read_session = env["Session"]()
    triggering_store = ScopedStore(owner_id=OWNER, workspace_id=WORKSPACE, session=read_session)
    aggregate = await triggering_store.workspace_budget_spent(WORKSPACE)
    read_session.close()
    assert aggregate["subagents"] == 3, (
        "the triggered run's spend must be visible in the triggering run's own "
        "workspace aggregate — they share workspace_id by construction (R-15)"
    )

    # ── (5) reserve()'s EXISTING check already scopes both runs together: a
    # low-enough ceiling refuses the TRIGGERING run's OWN reserve purely because of
    # the TRIGGERED run's spend (the triggering run itself has spent ZERO subagents
    # in this test) — proving the two runs share one aggregate, not two.
    budget = BudgetManager.from_limits(None, workspace_ceiling=3)
    with pytest.raises(BudgetExceeded) as exc:
        budget.reserve(subagents=1, workspace_spent=aggregate["subagents"])
    assert exc.value.dimension == "workspace"

    # Control: a ceiling high enough to absorb both runs' spend is NOT refused —
    # confirms the check is a real aggregate comparison, not an incidental reject.
    permissive_budget = BudgetManager.from_limits(None, workspace_ceiling=10)
    permissive_budget.reserve(subagents=1, workspace_spent=aggregate["subagents"])
    assert permissive_budget.spent().subagents == 1
