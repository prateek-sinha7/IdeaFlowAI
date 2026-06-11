"""tests/agents/test_subagent_runs.py — Wave-0 fan-out persistence backbone (Phase 11 / FANOUT-10).

Drives the additive ``0019 subagent_runs`` persistence layer fully OFFLINE (no DB /
Bedrock / API key / network), mirroring ``test_exec_runs.py`` (0018) +
``test_repositories_persistence.py`` (0017):

  * the additive ``0019`` migration is reversible against a fresh SQLite DB
    (``upgrade head`` -> ``downgrade -1`` -> ``upgrade head``) with NO ``sa.Enum``;
  * ``ScopedStore.record_subagent_run`` writes EXACTLY ONE owner/workspace-scoped
    ``subagent_runs`` row per child, round-tripping depth/isolation/status/tokens,
    and ``update_subagent_run`` flips the row terminal;
  * a cross-owner ``read_subagent_runs`` returns nothing (default-deny scoping —
    the FANOUT-10 mitigation, T-11-01-03);
  * the budget seam (``BudgetManager`` defaults + the stub ``reserve()``) +
    ``FanoutSpec.count``/``workers`` + ``CompiledWorkflow.allowed_workers`` +
    ``compiler._compile_fanout`` materialization land.

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore

# Importing app.models registers every model on Base.metadata (Pitfall 5) so
# create_all builds subagent_runs (+ the rest) for the test DB.
import app.models  # noqa: F401
from app.models.database import Base
from app.models.subagent_run import SubagentRun


# ---------------------------------------------------------------------------
# Alembic reversibility (0019) — mirrors test_exec_runs.py::test_0018_reversible
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

_EXPECTED_SUBAGENT_COLUMNS = {
    "id",
    "parent_run_id",
    "owner_id",
    "workspace_id",
    "parent_step",
    "worker_agent",
    "depth",
    "isolation",
    "status",
    "tokens",
    "cost",
    "created_at",
}


def _make_config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "alembic_subagent_runs.db"
    return f"sqlite:///{db_path}"


def test_0019_reversible_offline(fresh_db_url: str) -> None:
    """``upgrade head`` -> ``downgrade -1`` -> ``upgrade head`` round-trips clean."""
    cfg = _make_config(fresh_db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("subagent_runs"), "subagent_runs missing after upgrade head"
    cols = {c["name"] for c in inspector.get_columns("subagent_runs")}
    assert _EXPECTED_SUBAGENT_COLUMNS.issubset(cols), (
        f"subagent_runs missing columns: {sorted(_EXPECTED_SUBAGENT_COLUMNS - cols)}"
    )
    engine.dispose()

    # downgrade -1 drops subagent_runs (0019 is the head; -1 lands on 0018).
    command.downgrade(cfg, "-1")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert not inspector.has_table("subagent_runs"), (
        "downgrade -1 must drop subagent_runs"
    )
    engine.dispose()

    # upgrade head recreates it.
    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("subagent_runs"), "subagent_runs missing after re-upgrade"
    engine.dispose()


def test_0019_migration_uses_free_string_status() -> None:
    """No ``sa.Enum`` on the 0019 migration — status is a free String (Q3/INV-3)."""
    mig = _BACKEND_DIR / "alembic" / "versions" / "0019_subagent_runs.py"
    text = mig.read_text()
    assert "sa.Enum" not in text, "0019 must use a free String status (NO sa.Enum)"
    assert 'revision = "0019"' in text
    assert 'down_revision = "0018"' in text


# ---------------------------------------------------------------------------
# ScopedStore.record_subagent_run — scoped write + default-deny read
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_record_subagent_run_writes_scoped_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_subagent_run(
        "parent-run-1",
        parent_step="build",
        worker_agent="prototype-build",
        depth=1,
        isolation="shared_read",
        status="running",
        tokens=42,
        cost={"cost_class": 3},
    )
    assert row_id, "record_subagent_run must return a non-empty id"

    rows = db_session.query(SubagentRun).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == row_id
    assert row.parent_run_id == "parent-run-1"
    assert row.owner_id == "alice"        # AUTHZ-01
    assert row.workspace_id == "ws-1"     # AUTHZ-01
    assert row.parent_step == "build"
    assert row.worker_agent == "prototype-build"
    assert row.depth == 1
    assert row.isolation == "shared_read"
    assert row.status == "running"
    assert row.tokens == 42
    assert row.cost == {"cost_class": 3}


@pytest.mark.asyncio
async def test_update_subagent_run_flips_terminal(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_subagent_run(
        "parent-run-1",
        parent_step="build",
        worker_agent="prototype-build",
        depth=0,
        isolation="shared_read",
        status="running",
    )
    await store.update_subagent_run(row_id, status="complete", tokens=100)

    rows = db_session.query(SubagentRun).all()
    assert len(rows) == 1
    assert rows[0].status == "complete"
    assert rows[0].tokens == 100


@pytest.mark.asyncio
async def test_cross_owner_subagent_read_returns_nothing(db_session):
    """FANOUT-10 / T-11-01-03: a different owner reads zero subagent_runs rows."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await alice.record_subagent_run(
        "parent-run-1",
        parent_step="build",
        worker_agent="w0",
        depth=0,
        isolation="shared_read",
        status="running",
    )

    # Cross-owner scoped read returns nothing.
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_subagent_runs("parent-run-1") == []

    # The true owner still resolves it (the filter is not a blanket deny).
    assert len(await alice.read_subagent_runs("parent-run-1")) == 1


# ---------------------------------------------------------------------------
# Budget seam (BudgetManager defaults + stub reserve())
# ---------------------------------------------------------------------------


def test_budget_module_constants_present():
    from agents.execution_engine import budget as b

    assert b.DEFAULT_MAX_SUBAGENTS == 8
    assert b.DEFAULT_MAX_CONCURRENCY == 4
    assert b.DEFAULT_MAX_DEPTH == 2
    assert b.DEFAULT_WALL_CLOCK_SECONDS == 900
    assert b.MERGE_AGENT_MAX_ATTEMPTS == 2
    assert b.BUDGET_WARN_THRESHOLD == 0.8


def test_budget_manager_reserve_is_a_stub_seam():
    """reserve() records units and returns WITHOUT raising (enforcement is 11-04)."""
    from agents.execution_engine.budget import BudgetManager, BudgetExceeded, BudgetSnapshot

    mgr = BudgetManager()
    # The stub seam never raises in this plan (FANOUT-09 enforcement lands 11-04).
    mgr.reserve(tokens=1000, subagents=3, concurrency=4, depth=1)
    snap = mgr.spent()
    assert isinstance(snap, BudgetSnapshot)
    assert snap.subagents == 3
    assert snap.tokens == 1000
    assert issubclass(BudgetExceeded, Exception)


def test_budget_manager_resolves_caps_from_limits():
    from agents.execution_engine.budget import BudgetManager, DEFAULT_MAX_SUBAGENTS
    from agents.workflows.plan import Limits

    mgr = BudgetManager(Limits(max_subagents=5, max_depth=1))
    assert mgr.max_subagents == 5
    assert mgr.max_depth == 1
    # Unspecified caps fall back to the module defaults.
    assert BudgetManager().max_subagents == DEFAULT_MAX_SUBAGENTS


# ---------------------------------------------------------------------------
# ExecutionContext.budget field
# ---------------------------------------------------------------------------


def test_execution_context_has_budget_field():
    from agents.execution_engine.context import ExecutionContext
    from agents.artifacts.graph import ArtifactGraph

    ctx = ExecutionContext(run_id="r1", owner_id="alice", artifacts=ArtifactGraph())
    assert ctx.budget is None  # per-run object, default None (INV-2)


# ---------------------------------------------------------------------------
# FanoutSpec / allowed_workers / compiler._compile_fanout
# ---------------------------------------------------------------------------


def test_fanout_spec_additive_fields():
    from agents.workflows.plan import FanoutSpec

    spec = FanoutSpec(mode="parallel", max_parallel=2, agent="self", count=3, workers=["w1"])
    assert spec.mode == "parallel"
    assert spec.max_parallel == 2
    assert spec.agent == "self"
    assert spec.count == 3
    assert spec.workers == ["w1"]
    # Defaults additive (existing manifests keep mode/max_parallel only).
    bare = FanoutSpec()
    assert bare.agent is None and bare.count is None and bare.workers == []


def test_compiled_workflow_has_allowed_workers():
    from agents.workflows.plan import CompiledWorkflow

    cw = CompiledWorkflow(id="wf")
    assert cw.allowed_workers == []


def test_compiler_materializes_fanout_and_allowed_workers():
    from agents.capabilities.registry import CapabilityRegistry, discover
    from agents.workflows.compiler import WorkflowCompiler
    from agents.workflows.manifest import WorkflowManifest

    discover()
    registry = CapabilityRegistry()
    manifest = WorkflowManifest(
        id="fanout-wf",
        steps=[
            {
                "agent": "worker-a",
                "strategy": "single_shot",
                "fanout": {"mode": "parallel", "max_parallel": 3, "agent": "self", "count": 3},
            }
        ],
        deliverable={"strategy": "streamed_text", "name": "out.txt"},
        planner="skip",
        clarify={"mode": "off", "defaults": []},
        allowed_workers=["worker-a", "worker-b"],
    )
    compiled = WorkflowCompiler().compile(manifest, registry)
    step = compiled.steps[0]
    assert step.fanout is not None
    assert step.fanout.mode == "parallel"
    assert step.fanout.count == 3
    assert step.fanout.agent == "self"
    assert compiled.allowed_workers == ["worker-a", "worker-b"]


def test_compiler_materializes_on_conflict_and_merge_agent():
    """CR-03: on_conflict + fanout.merge_agent survive compilation (not dropped)."""
    from agents.capabilities.registry import CapabilityRegistry, discover
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.manifest import WorkflowManifest

    discover()
    registry = CapabilityRegistry()

    def _manifest(on_conflict="abort", merge_agent="merge-worker"):
        return WorkflowManifest(
            id="conflict-wf",
            steps=[
                {
                    "agent": "worker-a",
                    "strategy": "single_shot",
                    "on_conflict": on_conflict,
                    "fanout": {"mode": "parallel", "merge_agent": merge_agent},
                }
            ],
            deliverable={"strategy": "streamed_text", "name": "out.txt"},
            planner="skip",
            clarify={"mode": "off", "defaults": []},
        )

    compiled = WorkflowCompiler().compile(_manifest(), registry)
    step = compiled.steps[0]
    # The authored policy is carried — NOT silently downgraded to human_gate.
    assert step.on_conflict == "abort"
    # The designated merge worker is materialized onto the FanoutSpec.
    assert step.fanout.merge_agent == "merge-worker"

    # An omitted on_conflict keeps the human_gate default (parity).
    no_policy = WorkflowCompiler().compile(
        WorkflowManifest(
            id="default-wf",
            steps=[{"agent": "worker-a", "strategy": "single_shot"}],
            deliverable={}, planner="skip", clarify={"mode": "off", "defaults": []},
        ),
        registry,
    )
    assert no_policy.steps[0].on_conflict == "human_gate"

    # An unknown policy is a fail-loud CompilerError (never a silent fallback).
    import pytest as _pytest

    with _pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(_manifest(on_conflict="overwrite"), registry)
    assert "on_conflict" in str(exc.value)
