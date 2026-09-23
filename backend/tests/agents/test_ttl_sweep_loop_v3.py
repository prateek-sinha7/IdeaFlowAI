"""tests/agents/test_ttl_sweep_loop_v3.py

Behavioral test for sandbox-git-versioning-v2, task V2.

Coverage (Requirement 3 / FR-003):
─────────────────────────────────
The TTL sweep coroutine in main.py (``_sandbox_sweep_loop``, the nested
coroutine started inside ``lifespan()``, ``app/main.py:179-294``) builds the
protected set from gate-paused (non-terminal) rows in the database, ensuring
they are not swept even if the sandbox mtime is past the TTL.

These tests drive the REAL coroutine: ``app.main.lifespan(app)`` is entered as
an async context manager with ``settings.SANDBOX_SWEEP_INTERVAL_SECONDS``
patched down so the loop fires almost immediately, and
``app.agents.sandbox.sweep_expired`` is monkeypatched to a capturing stub so
the ``protected_run_ids`` argument the loop actually builds can be asserted
on. Nothing about the loop's own logic (the DB query, the
``resolve_revision_root`` walk, the fail-closed branch) is re-implemented
here — only the two seams (the interval, and the sweep call) are patched.

Rows are seeded AFTER entering the lifespan context, not before. The reason:
``lifespan()`` also runs ``ExecutionEngine.restore_non_terminal_runs()``
*before* it creates the sweep task; that scan is destructive — it re-derives
a stateless `waiting_for_user` row's status if it finds no durable open gate
for it, and it would find exactly the row this test needs to keep as
`waiting_for_user` for the sweep loop to observe. Seeding after the
`async with` block has entered means the restore scan (which ran against an
empty non-terminal set) never touches these rows.

DB isolation: ``tests/conftest.py`` pins ``DATABASE_URL`` to a hermetic sqlite
file, but only from its own top-of-file line — and its own early ``import
app.models`` (before that pin) already pulls in ``app.models.database``,
whose module-level ``engine = create_engine(settings.DATABASE_URL, ...)``
therefore binds to whatever ``.env`` says (this repo's ``.env`` points at the
real dev Postgres, ``flowin_local_pdf``, before the pin ever runs). Every
existing test that drives the real ``app.main`` app (``test_handoff_api.py``,
``test_register_password_echo_fixture_mounts_real_app.py``) works around this
the same way: build an isolated engine and monkeypatch
``app.models.database.engine`` / ``SessionLocal`` onto it. This file does the
same, module-scoped so ``app.main`` (which binds ``engine`` by name at its own
import time) only needs patching once — never the real database.

Requirement 2 AC 13–14: every non-terminal run protects its revision root.
Requirement 2 AC 11, AC 15: a resolver failure (e.g. cyclic ancestry) protects
the run's own id (fail closed).
Requirement 2 AC 17: a fully terminal family is never protected.

Requirement: 3 / FR-003
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path setup — make ``backend/`` importable
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Isolated DB — see the module docstring's "DB isolation" note. Module-scoped
# and autouse: applies before the first test in this file imports app.main
# (which binds `engine` by name at import time), and stays applied for every
# test in the file so app.main is only ever imported against this engine.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _sweep_test_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield engine, test_session_local
    engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def _patch_db_engine(_sweep_test_engine):
    """Point ``app.models.database`` (and ``app.main``'s own bound name) at the
    isolated sqlite engine for the whole file — never the real database.
    """
    import app.models.database as db_module

    engine, test_session_local = _sweep_test_engine
    mp = pytest.MonkeyPatch()
    mp.setattr(db_module, "engine", engine)
    mp.setattr(db_module, "SessionLocal", test_session_local)
    import app.main as main_module  # first import in this file happens here, already patched

    mp.setattr(main_module, "engine", engine)
    yield
    mp.undo()


# ---------------------------------------------------------------------------
# Seed helpers — insert through the app's ``SessionLocal`` name (the same one
# ``_sandbox_sweep_loop`` opens at runtime via ``from app.models.database
# import SessionLocal``, a fresh lookup every iteration), so the loop's own DB
# session sees these rows. ``parent_run_id`` / ``user_id`` are real FKs on the
# model, so a real User row is seeded and any ``parent_run_id`` referenced
# already exists (or is filled in after, for the cyclic case) at commit time —
# kept even though this isolated engine does not enable sqlite FK enforcement,
# so the seeding stays valid if that ever changes.
# ---------------------------------------------------------------------------


def _run_id() -> str:
    return str(uuid.uuid4())


def _seed_user(session):
    from tests.factories.user_factory import create_user

    return create_user(
        session, f"ttl-sweep-{uuid.uuid4()}@test.local", "irrelevant-pw-12345"
    )


def _seed_run(
    session,
    *,
    run_id: str,
    user_id: str,
    parent_run_id: str | None = None,
    status: str = "running",
) -> str:
    """Insert a minimal ``workflow_runs`` row and return its id."""
    from app.models.workflow import WorkflowRun

    session.add(
        WorkflowRun(
            id=run_id,
            user_id=user_id,
            title="test",
            type="prototype",
            status=status,
            input="idea",
            parent_run_id=parent_run_id,
        )
    )
    session.commit()
    return run_id


@pytest.fixture()
def db():
    """The app's real DB session; teardown removes only the rows this file added.

    ``parent_run_id`` is nulled out for every seeded row before deletion so a
    parent/child chain (or the deliberate cycle in the fail-closed test) never
    trips the FK constraint on delete.
    """
    from app.models.database import SessionLocal
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    session = SessionLocal()
    run_ids: list[str] = []
    user_ids: list[str] = []
    try:
        yield session, run_ids, user_ids
    finally:
        if run_ids:
            session.query(WorkflowRun).filter(WorkflowRun.id.in_(run_ids)).update(
                {"parent_run_id": None}, synchronize_session=False
            )
            session.commit()
            session.query(WorkflowRun).filter(WorkflowRun.id.in_(run_ids)).delete(
                synchronize_session=False
            )
        if user_ids:
            session.query(User).filter(User.id.in_(user_ids)).delete(
                synchronize_session=False
            )
        session.commit()
        session.close()


async def _drive_sweep_once(monkeypatch, *, seed) -> list[set[str]]:
    """Patch the sweep interval + spy on ``sweep_expired``, run the real
    ``lifespan(app)``, seed rows via ``seed()`` AFTER startup, and wait for
    one sweep iteration.

    Returns every ``protected_run_ids`` set the real loop passed to
    ``sweep_expired`` (stops polling as soon as it has captured one).
    """
    from app.core.config import settings
    import app.agents.sandbox as sandbox_module

    monkeypatch.setattr(settings, "SANDBOX_SWEEP_INTERVAL_SECONDS", 0.05)

    captured: list[set[str]] = []

    def _fake_sweep_expired(*, ttl_hours=None, runs_root=None, protected_run_ids=None):
        captured.append(set(protected_run_ids or ()))
        return 0

    monkeypatch.setattr(sandbox_module, "sweep_expired", _fake_sweep_expired)

    from app.main import app, lifespan

    async with lifespan(app):
        # Seeded AFTER startup — see the module docstring: restore_non_terminal_runs()
        # already ran (against an empty non-terminal set) before we get here, so it
        # never touches the rows `seed()` is about to insert.
        seed()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        while not captured and loop.time() < deadline:
            await asyncio.sleep(0.02)

    return captured


# ===========================================================================
# Tests: TTL sweep loop builds protected set from gate-paused rows
# ===========================================================================


class TestTTLSweepLoopBuildingProtectedSet:
    """Drive ``app.main``'s real ``_sandbox_sweep_loop`` (via ``lifespan()``)
    and assert on the ``protected_run_ids`` set it actually builds and passes
    to ``sweep_expired`` — never a re-implementation of the loop's body.
    """

    @pytest.mark.asyncio
    async def test_gate_paused_run_resolves_to_protected_root(
        self, monkeypatch, db
    ) -> None:
        """A gate-paused run in the DB resolves to its family root, which the
        real loop adds to the protected set.

        Requirement 2 AC 14: durable pause is NOT treated as inactivity.
        """
        session, run_ids, user_ids = db
        user = _seed_user(session)
        user_ids.append(user.id)
        root_id, child_id = _run_id(), _run_id()

        def seed():
            _seed_run(session, run_id=root_id, user_id=user.id, status="completed")
            run_ids.append(root_id)
            _seed_run(
                session,
                run_id=child_id,
                user_id=user.id,
                parent_run_id=root_id,
                status="waiting_for_user",  # gate-paused, non-terminal
            )
            run_ids.append(child_id)

        captured = await _drive_sweep_once(monkeypatch, seed=seed)

        assert captured, "sweep_expired was never called by the real sweep loop"
        assert root_id in captured[0], (
            "the gate-paused child should resolve to its family root, which the "
            f"real loop then protects — got {captured[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_multiple_gate_paused_descendants_share_root_in_protected_set(
        self, monkeypatch, db
    ) -> None:
        """Two gate-paused descendants of the same root both resolve to it, so
        the real loop's protected set contains the root exactly once.

        Requirement 2 AC 13: every non-terminal run protects its revision root.
        """
        session, run_ids, user_ids = db
        user = _seed_user(session)
        user_ids.append(user.id)
        root_id, child1_id, child2_id = _run_id(), _run_id(), _run_id()

        def seed():
            _seed_run(session, run_id=root_id, user_id=user.id, status="completed")
            run_ids.append(root_id)
            for child_id in (child1_id, child2_id):
                _seed_run(
                    session,
                    run_id=child_id,
                    user_id=user.id,
                    parent_run_id=root_id,
                    status="waiting_for_user",
                )
                run_ids.append(child_id)

        captured = await _drive_sweep_once(monkeypatch, seed=seed)

        assert captured, "sweep_expired was never called by the real sweep loop"
        assert captured[0] == {root_id}, (
            "both gate-paused children should resolve to the same root and "
            f"protect it exactly once — got {captured[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_terminal_runs_not_included_in_non_terminal_query(
        self, monkeypatch, db
    ) -> None:
        """Terminal runs never reach the real loop's protected set; only the
        gate-paused run does.

        Requirement 2 AC 17: fully terminal families can be swept.
        """
        session, run_ids, user_ids = db
        user = _seed_user(session)
        user_ids.append(user.id)
        completed_id, failed_id, gate_paused_id = _run_id(), _run_id(), _run_id()

        def seed():
            for run_id, status in (
                (completed_id, "completed"),
                (failed_id, "failed"),
                (gate_paused_id, "waiting_for_user"),
            ):
                _seed_run(session, run_id=run_id, user_id=user.id, status=status)
                run_ids.append(run_id)

        captured = await _drive_sweep_once(monkeypatch, seed=seed)

        assert captured, "sweep_expired was never called by the real sweep loop"
        assert gate_paused_id in captured[0]
        assert completed_id not in captured[0]
        assert failed_id not in captured[0]

    @pytest.mark.asyncio
    async def test_resolver_failure_protect_closed(self, monkeypatch, db) -> None:
        """A resolver failure (cyclic ancestry) makes the real loop protect the
        run's own id — fail closed.

        Requirement 2 AC 11, AC 15: resolver failure is PROTECTED.
        """
        session, run_ids, user_ids = db
        user = _seed_user(session)
        user_ids.append(user.id)
        run_id_a, run_id_b = _run_id(), _run_id()

        def seed():
            from app.models.workflow import WorkflowRun

            # FK-safe two-step insert for the cycle A -> B -> A: A first with
            # no parent (so it can be referenced), then B -> A, then rewrite
            # A -> B — no row is ever inserted whose parent doesn't exist yet.
            _seed_run(session, run_id=run_id_a, user_id=user.id, status="waiting_for_user")
            run_ids.append(run_id_a)
            _seed_run(
                session,
                run_id=run_id_b,
                user_id=user.id,
                parent_run_id=run_id_a,
                status="completed",
            )
            run_ids.append(run_id_b)
            session.query(WorkflowRun).filter(WorkflowRun.id == run_id_a).update(
                {"parent_run_id": run_id_b}, synchronize_session=False
            )
            session.commit()

        captured = await _drive_sweep_once(monkeypatch, seed=seed)

        assert captured, "sweep_expired was never called by the real sweep loop"
        assert run_id_a in captured[0], (
            "a cyclic ancestry must fail closed — the run's own id must be "
            f"protected — got {captured[0]!r}"
        )
