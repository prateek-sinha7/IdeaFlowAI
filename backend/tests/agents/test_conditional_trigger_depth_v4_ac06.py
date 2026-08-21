"""V4 (spec 014 / Phase 4 validator, NOT a numbered task — ad hoc harness written
during PASS/FAIL validation, alongside ``test_conditional_divert_v4_validation.py``):
AC-06 — a 6-level-deep ``trigger: workflow`` chain must fail closed on the 6th hop.

    "AC-06: A chain of `trigger: workflow` outcomes exceeding `trigger_max_depth` fails
    closed rather than recursing unboundedly."

R-18/R-19 fix the ceiling at 5 (exact-equality check in ``KernelServices.
run_trigger_workflow``, not a variable/``>=`` check). This drives 6 SEQUENTIAL calls to
the REAL ``run_trigger_workflow`` delegate (T28) — the same one T29's engine arm and
T33's budget test call — each one's ``ectx.trigger_depth`` set to exactly what the
PREVIOUS hop's real mint would have produced for the new run (mirrors the ``+1``
propagation ``run_trigger_workflow`` itself performs at its own mint call site,
verified by reading ``kernel_services.py`` directly): hops 1-5 (starting
``trigger_depth`` 0,1,2,3,4) must each mint successfully; hop 6 (starting
``trigger_depth`` 5, the fixed ceiling) must raise ``BudgetExceeded`` BEFORE any mint —
i.e. no 6th ``WorkflowRun`` row ever appears.

Offline: in-memory SQLite (StaticPool) + a stub execution engine — same recipe as
T33's ``test_conditional_trigger_budget_t33.py`` (no live Bedrock; only the mint +
depth-guard logic is under test).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.subagent_run  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod


class _StubEngine:
    """No-op execution engine — every triggered run's background driver must not
    reach Bedrock; only the mint (id/parent_run_id/trigger_depth propagation) matters."""

    async def execute(self, **kwargs):
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": ""}}


class _TriggerEctx:
    """Minimal ExecutionContext stand-in carrying only what ``run_trigger_workflow``
    reads (R-15/R-18): ``run_id`` / ``owner_id`` / ``workspace_id`` / ``trigger_depth``."""

    def __init__(self, run_id, owner_id, workspace_id, trigger_depth):
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

    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    import app.api.run_commands as rc_module
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _StubEngine())

    yield {"Session": TestingSession, "rc": rc_module}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


@pytest.mark.asyncio
async def test_six_level_chain_fails_closed_on_sixth_hop_AC06(env):
    from agents.execution_engine.budget import BudgetExceeded
    from agents.execution_engine.kernel_services import KernelServices
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    OWNER = "v4-chain-owner"
    WORKSPACE = "v4-chain-ws"

    session = env["Session"]()
    session.add(User(id=OWNER, email="v4chain@example.com", password_hash="x"))
    root_run_id = "run-chain-root"
    session.add(
        WorkflowRun(
            id=root_run_id, user_id=OWNER, owner_id=OWNER, workspace_id=WORKSPACE,
            type="user_stories", status="running", input="go",
        )
    )
    session.commit()
    session.close()

    ks = KernelServices.__new__(KernelServices)
    ks._pipeline_type = "user_stories"
    ks._ordered_agents = []

    rc = env["rc"]
    minted_run_ids: list[str] = [root_run_id]

    # ── Hops 1-5: trigger_depth 0,1,2,3,4 on the CALLING run -> each must mint ──
    current_run_id = root_run_id
    for hop in range(1, 6):
        calling_depth = hop - 1  # hop 1 called with depth 0, hop 5 called with depth 4
        ectx = _TriggerEctx(current_run_id, OWNER, WORKSPACE, trigger_depth=calling_depth)
        new_run_id, resolved = await ks.run_trigger_workflow(None, ectx, workflow_ref="self")
        assert resolved == "user_stories"

        task = rc._PIPELINE_TASKS.get(new_run_id)
        if task is not None:
            await task

        verify = env["Session"]()
        row = verify.query(WorkflowRun).filter(WorkflowRun.id == new_run_id).first()
        assert row is not None, f"hop {hop} (calling depth={calling_depth}) failed to mint"
        assert row.parent_run_id == current_run_id
        verify.close()

        minted_run_ids.append(new_run_id)
        current_run_id = new_run_id

    assert len(minted_run_ids) == 6, (
        f"expected 5 successful hops (root + 5 minted runs = 6 total rows), got "
        f"{len(minted_run_ids)}: {minted_run_ids}"
    )

    # ── Hop 6: the 6th run in the chain now calls with trigger_depth=5 (the fixed
    # ceiling) — must fail closed with BudgetExceeded, NOT mint a 7th row. ──────
    ectx_at_ceiling = _TriggerEctx(current_run_id, OWNER, WORKSPACE, trigger_depth=5)

    before_count = env["Session"]().query(WorkflowRun).count()

    with pytest.raises(BudgetExceeded) as exc:
        await ks.run_trigger_workflow(None, ectx_at_ceiling, workflow_ref="self")
    assert exc.value.dimension == "trigger_depth", (
        f"AC-06: expected BudgetExceeded(dimension='trigger_depth'), got "
        f"dimension={exc.value.dimension!r}"
    )

    after_count = env["Session"]().query(WorkflowRun).count()
    assert after_count == before_count, (
        "AC-06: the refused 6th hop must mint ZERO new WorkflowRun rows — a "
        f"silent infinite mint would show up here (before={before_count}, "
        f"after={after_count})"
    )
