"""Workstream A (POR §3) — parent-link ownership hardening at BOTH ingress sites.

The two attacker-facing parent-link ingress sites in ``websocket.py`` used to
verify only that the candidate parent row EXISTS, not that the caller OWNS it:

  * Site 1 — ``_handle_workflow_execution`` (:1688): the ``run_pipeline``
    ``source_workflow_run_id`` chaining link (the primary IDOR path).
  * Site 2 — ``_handle_revision_execution`` (:2247): the ``run_revision``
    row-creation ``parent_run_id`` link.

An exists-only check let a foreign (other user's) run id be persisted as a
``parent_run_id`` edge. Engine ``assert_owns`` gates content reads, but the new
revision-family read walk (``runs.py`` ``/family`` + ``root_run_id``) follows
``parent_run_id`` edges — so a foreign ROW linkage leaks foreign run metadata.

Both sites now route through the single ownership-checked resolver
``_resolve_owned_parent_run_id(db, candidate_id, user_id)`` (D-06 — keyed on
``WorkflowRun.user_id``, never the nullable backfilled ``owner_id``).

This suite pins three behavior groups:
  (1) the resolver directly (owned → id; foreign → None; missing → None;
      falsy → None with no query);
  (2) Site 2 at the handler level via the offline harness copied from
      ``test_run_revision_ws_dispatch.py`` (foreign parent → row NOT linked but
      the stub engine IS still invoked; owned parent → row linked);
  (3) Site 1 at the source level via ``inspect.getsource`` (the FULL call
      signature ``_resolve_owned_parent_run_id(db, source_workflow_run_id,
      user.id)`` is present — pinning the exact ``user.id`` argument so a
      mis-wired user variable at the primary IDOR site cannot pass — and the
      old exists-only pattern is gone).

Offline — in-memory SQLite (StaticPool) monkeypatched onto the WS module's
``_get_db``; stub engine via ``agents.execution_engine.engine
.get_execution_engine``; no Bedrock, no network.
"""

from __future__ import annotations

import inspect
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the handler path touches on Base.metadata BEFORE
# create_all (db_factory pattern, see test_run_revision_ws_dispatch.py).
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from app.models.database import Base
from app.models.user import User
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Harness — fake WS, stub engine, in-memory DB (copied from
# test_run_revision_ws_dispatch.py so Site 2 is proven on the real handler).
# ════════════════════════════════════════════════════════════════════════════


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class _StubEngine:
    """Records every ``_handle_revision`` call so a test can assert the engine
    was still invoked (dispatch unchanged) even when the ROW link is dropped."""

    def __init__(self, behavior) -> None:
        self._behavior = behavior
        self.calls: list[dict] = []

    async def _handle_revision(self, **kwargs) -> None:
        self.calls.append(kwargs)
        await self._behavior(kwargs)


@pytest.fixture
def ws_env(monkeypatch):
    """Offline harness for ``_handle_revision_execution``: in-memory SQLite
    wired into the WS module's ``_get_db``."""
    from app.api import websocket as ws_module

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    yield ws_module, TestingSession

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(TestingSession, *, email_prefix="u") -> User:
    db = TestingSession()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _seed_run(TestingSession, *, owner_id: str, run_type="od_ppt") -> str:
    run_id = str(uuid.uuid4())
    db = TestingSession()
    try:
        db.add(WorkflowRun(
            id=run_id,
            user_id=owner_id,
            owner_id=owner_id,
            title="parent deck",
            type=run_type,
            status="completed",
            input="make a deck",
            agent_count=3,
        ))
        db.commit()
    finally:
        db.close()
    return run_id


def _row(TestingSession, run_id: str) -> WorkflowRun | None:
    db = TestingSession()
    try:
        return db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    finally:
        db.close()


def _install_stub(monkeypatch, behavior) -> _StubEngine:
    stub = _StubEngine(behavior)
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: stub)
    return stub


async def _noop_complete(kwargs):
    send = kwargs["websocket_send_fn"]
    await send({"type": "pipeline_complete", "data": {"final_output": "x"}})


# ════════════════════════════════════════════════════════════════════════════
# (1) The resolver directly — owned/foreign/missing/falsy
# ════════════════════════════════════════════════════════════════════════════


class TestResolverDirect:
    def test_owned_candidate_returns_id(self, ws_env):
        ws_module, TestingSession = ws_env
        owner = _seed_user(TestingSession)
        run_id = _seed_run(TestingSession, owner_id=owner.id)

        db = TestingSession()
        try:
            assert ws_module._resolve_owned_parent_run_id(db, run_id, owner.id) == run_id
        finally:
            db.close()

    def test_foreign_owned_candidate_returns_none(self, ws_env):
        ws_module, TestingSession = ws_env
        owner = _seed_user(TestingSession, email_prefix="owner")
        attacker = _seed_user(TestingSession, email_prefix="attacker")
        run_id = _seed_run(TestingSession, owner_id=owner.id)

        db = TestingSession()
        try:
            # The attacker names a real run id — but it is not theirs → dropped.
            assert ws_module._resolve_owned_parent_run_id(db, run_id, attacker.id) is None
        finally:
            db.close()

    def test_missing_candidate_returns_none(self, ws_env):
        ws_module, TestingSession = ws_env
        owner = _seed_user(TestingSession)

        db = TestingSession()
        try:
            assert ws_module._resolve_owned_parent_run_id(
                db, "does-not-exist", owner.id
            ) is None
        finally:
            db.close()

    def test_falsy_candidate_returns_none_without_query(self, ws_env):
        ws_module, TestingSession = ws_env
        owner = _seed_user(TestingSession)

        class _ExplodingDb:
            def query(self, *a, **k):  # pragma: no cover - must never be called
                raise AssertionError("a falsy candidate must not issue a query")

        for falsy in (None, ""):
            assert ws_module._resolve_owned_parent_run_id(
                _ExplodingDb(), falsy, owner.id
            ) is None


# ════════════════════════════════════════════════════════════════════════════
# (2) Site 2 handler-level — foreign parent NOT linked, engine STILL invoked;
#     owned parent → linked. Dispatch behavior unchanged either way.
# ════════════════════════════════════════════════════════════════════════════


class TestSite2RevisionRowLinkage:
    @pytest.mark.asyncio
    async def test_foreign_parent_row_not_linked_but_engine_invoked(
        self, ws_env, monkeypatch
    ):
        ws_module, TestingSession = ws_env
        owner = _seed_user(TestingSession, email_prefix="owner")
        attacker = _seed_user(TestingSession, email_prefix="attacker")
        # A real run owned by someone ELSE — the attacker points a revision at it.
        foreign_parent = _seed_run(TestingSession, owner_id=owner.id)

        stub = _install_stub(monkeypatch, _noop_complete)
        ws = _FakeWebSocket()

        await ws_module._handle_revision_execution(
            ws, attacker, foreign_parent, "od_ppt_output", "Steal the deck.",
        )

        run_id = stub.calls[0]["pipeline_run_id"]
        row = _row(TestingSession, run_id)
        assert row is not None
        # ROW linkage dropped — the family walk can never reach the foreign run.
        assert row.parent_run_id is None, (
            "a foreign parent id must NOT be persisted as a family edge (POR §3)"
        )
        # Dispatch behavior unchanged — the engine is still invoked identically
        # (engine assert_owns stays the content gate; only linkage is conditioned).
        assert len(stub.calls) == 1, "revision dispatch must run regardless of linkage"

    @pytest.mark.asyncio
    async def test_owned_parent_row_is_linked(self, ws_env, monkeypatch):
        ws_module, TestingSession = ws_env
        owner = _seed_user(TestingSession, email_prefix="owner")
        owned_parent = _seed_run(TestingSession, owner_id=owner.id)

        stub = _install_stub(monkeypatch, _noop_complete)
        ws = _FakeWebSocket()

        await ws_module._handle_revision_execution(
            ws, owner, owned_parent, "od_ppt_output", "Revise my own deck.",
        )

        run_id = stub.calls[0]["pipeline_run_id"]
        row = _row(TestingSession, run_id)
        assert row is not None
        assert row.parent_run_id == owned_parent, (
            "an OWNED parent must still link (family lineage intact)"
        )


# ════════════════════════════════════════════════════════════════════════════
# (3) Site 1 source-level — the primary run_pipeline IDOR path is wired through
#     the resolver with the EXACT user.id argument, and the exists-only pattern
#     is gone. (inspect.getsource — the codebase's additive-source idiom.)
# ════════════════════════════════════════════════════════════════════════════


class TestSite1Source:
    def test_workflow_execution_wires_resolver_with_user_id(self, ws_env):
        ws_module, _ = ws_env
        src = inspect.getsource(ws_module._handle_workflow_execution)
        # Pin the FULL call signature — not merely the helper name — so a
        # mis-wired user-id argument at the primary IDOR site cannot pass.
        assert "_resolve_owned_parent_run_id(db, source_workflow_run_id, user.id)" in src

    def test_workflow_execution_drops_exists_only_check(self, ws_env):
        ws_module, _ = ws_env
        src = inspect.getsource(ws_module._handle_workflow_execution)
        # The old exists-only pattern (a WorkflowRun.id filter on the source id
        # WITHOUT a user_id condition) must no longer appear.
        assert "WorkflowRun.id == source_workflow_run_id" not in src
