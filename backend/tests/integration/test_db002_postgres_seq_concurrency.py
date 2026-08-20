"""tests/integration/test_db002_postgres_seq_concurrency.py — DB-001/DB-002
(task.md R-02/R-06): real PostgreSQL migration + concurrent seq-allocation proof.

The SQLite-backed ``test_resume_marker_workspace.py::
test_stamp_resume_marker_survives_concurrent_racing_writers`` proves the fix
functionally (no writer's marker is silently dropped), but every existing
`run_events` seq test — including that one — runs against SQLite. Task.md's
DB-001/DB-002 explicitly call for a REAL PostgreSQL run at migration head
(the ``uq_run_events_scope_seq`` unique constraint's IntegrityError-and-retry
path is Postgres-specific transaction/locking behavior that SQLite's simpler
locking model does not exercise the same way).

This test:
  1. Starts ``postgres:16`` in docker (the SAME fixture pattern
     ``test_phase8_resume.py::postgres_url`` uses — skips cleanly if docker is
     unavailable, e.g. this repo's Windows dev environment).
  2. Runs ``alembic upgrade head`` against it (DB-002: proves migration head
     0032 applies cleanly to a real, empty PostgreSQL instance, and that the
     ``uq_run_events_scope_seq``/``uq_run_events_scope_event`` constraints
     0024/0028/0029 restored actually exist afterward).
  3. Drives N concurrent ``ScopedStore.append_event_next_seq`` callers against
     the SAME run_id under real PostgreSQL — the exact allocator
     ``_stamp_resume_marker`` now uses (DB-001) — and asserts every writer
     survives with a distinct, contiguous seq under genuine transaction
     concurrency (not SQLite's single-writer-lock semantics).

Skips (pytest.skip, never fails) when docker is unavailable — this is the ONE
sanctioned exception to "a platform-specific production test must run on that
platform": it is not skipped because Postgres is optional, it is skipped
because CI (Linux, has docker) is where it actually runs; a Windows dev box
without docker cannot execute it and must not be blocked by that.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"
_PG_IMAGE = "postgres:16"
_PG_READY_TIMEOUT_S = 90


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        return proc.returncode == 0
    except Exception:
        return False


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _wait_for_postgres(dsn: str, timeout_s: int) -> None:
    import psycopg

    deadline = time.time() + timeout_s
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(1.0)
    raise TimeoutError(
        f"Postgres at {dsn} did not become ready within {timeout_s}s; "
        f"last error: {type(last_exc).__name__}: {last_exc}"
    )


@pytest.fixture(scope="module")
def postgres_url():
    """Start ``postgres:16`` on a free port; yield a SQLAlchemy-shaped DSN; rm -f after.

    Mirrors ``test_phase8_resume.py::postgres_url`` exactly (same image, same
    readiness probe, same teardown) — kept as its own copy rather than a shared
    import because the two suites' docker lifecycles must not be coupled (a
    failure importing one module must never skip/break the other's fixture).
    """
    if not _docker_available():
        pytest.skip("docker is not available — skipping PostgreSQL migration/concurrency test.")

    port = _free_port()
    name = f"flowin-db002-pg-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", name,
            "-p", f"{port}:5432",
            "-e", "POSTGRES_PASSWORD=postgres",
            _PG_IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if run.returncode != 0:
        pytest.skip(
            f"could not start docker Postgres ({_PG_IMAGE}): {run.stderr.strip() or run.stdout.strip()}"
        )
    container_id = run.stdout.strip()

    # psycopg (v3) DSN for the readiness probe; SQLAlchemy uses the same
    # connection string via the psycopg driver too (postgresql+psycopg://).
    raw_dsn = f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres"
    try:
        _wait_for_postgres(raw_dsn, _PG_READY_TIMEOUT_S)
        yield f"postgresql+psycopg://postgres:postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(["docker", "rm", "-f", container_id or name], capture_output=True, timeout=60)


def _migrate_to_head(db_url: str) -> None:
    """DB-002: run the REAL migration chain (0001..0032) against ``db_url``."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


@pytest.mark.requires_postgres
def test_migration_head_applies_cleanly_to_real_postgres(postgres_url):
    """DB-002: migration head 0032 applies to a real, empty PostgreSQL 16
    instance with no manual intervention, and the run_events uniqueness
    backstops (0024/0028/0029) actually exist afterward."""
    from sqlalchemy import create_engine, inspect

    _migrate_to_head(postgres_url)

    engine = create_engine(postgres_url)
    try:
        inspector = inspect(engine)
        assert inspector.has_table("run_events")
        constraint_names = {
            uc["name"] for uc in inspector.get_unique_constraints("run_events")
        }
        assert "uq_run_events_scope_seq" in constraint_names, (
            "uq_run_events_scope_seq must exist on a freshly migrated PostgreSQL "
            f"instance at head — found unique constraints: {constraint_names}"
        )
        assert "uq_run_events_scope_event" in constraint_names
    finally:
        engine.dispose()


@pytest.mark.requires_postgres
def test_concurrent_seq_allocation_survives_under_real_postgres_locking(postgres_url):
    """DB-001 (task.md R-02) against REAL PostgreSQL: N concurrent
    ``append_event_next_seq`` callers targeting the SAME run_id — the exact
    allocator ``_stamp_resume_marker`` now uses — must all survive with a
    distinct, contiguous seq under genuine multi-connection transaction
    concurrency (IntegrityError-and-retry on ``uq_run_events_scope_seq``,
    which only a real ACID database enforces the way production does)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from agents.authz import ScopedStore

    _migrate_to_head(postgres_url)

    engine = create_engine(postgres_url)
    SessionLocal = sessionmaker(bind=engine)

    run_id = f"db002-{uuid.uuid4().hex[:8]}"
    owner_id = "db002-owner"
    workspace_id = "db002-ws"

    # Seed the owning workflow_runs row (run_events has no FK requiring it in
    # this schema, but seeding keeps the shape realistic) — best-effort, the
    # seq allocator itself does not require it.
    async def _one_writer(idx: int) -> None:
        session = SessionLocal()
        try:
            store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id, session=session)
            await store.append_event_next_seq(
                run_id,
                event_id=f"db002-writer-{idx}-{uuid.uuid4().hex[:6]}",
                type="run_resuming",
                payload_json={"writer": idx},
            )
        finally:
            session.close()

    async def _drive() -> None:
        N = 12
        await asyncio.gather(*[_one_writer(i) for i in range(N)])

    asyncio.run(_drive())

    session = SessionLocal()
    try:
        from app.models.run_event import RunEvent

        rows = (
            session.query(RunEvent)
            .filter(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq.asc())
            .all()
        )
        assert len(rows) == 12, (
            f"every concurrent writer must persist its OWN row under real "
            f"PostgreSQL locking — expected 12, got {len(rows)}"
        )
        seqs = [r.seq for r in rows]
        assert seqs == list(range(1, 13)), (
            f"seqs must be unique and contiguous under real concurrency, got {seqs}"
        )
    finally:
        session.close()
        engine.dispose()
