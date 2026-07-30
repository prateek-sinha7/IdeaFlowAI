"""app/agents/checkpointer.py — LangGraph checkpointer factory.

Backs durable HITL review-gate pauses and crash/disconnect resume. The thread id
is the ``pipeline_run_id``, so a run can pause at a gate and resume later — even
after a process restart, when backed by Postgres.

Provider selection from ``DATABASE_URL``:
  - ``postgresql://…`` → AsyncPostgresSaver (production; survives restarts)
  - anything else (sqlite dev) → InMemorySaver (no cross-restart resume; dev only)

The Postgres saver owns a small async connection pool for the app's lifetime.
Wire :func:`get_checkpointer` on startup and :func:`close_checkpointer` on
shutdown (done by the engine in Phase 3). Imports are lazy so this module loads
even before ``langgraph-checkpoint-postgres`` is installed.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("app.agents.checkpointer")

_checkpointer = None  # cached process-wide singleton
_pool = None          # AsyncConnectionPool when on Postgres
_closed = False       # D7 (KAN-139): one-way latch set by close_checkpointer()


def _is_postgres() -> bool:
    return settings.DATABASE_URL.startswith(("postgresql://", "postgresql+", "postgres://"))


async def get_checkpointer():
    """Return the process-wide checkpointer, creating it on first call.

    On Postgres: opens an async pool and runs ``.setup()`` once (idempotent) to
    create the checkpoint tables. On sqlite/dev: returns an in-memory saver and
    warns that pauses won't survive a restart.

    D7 (KAN-139): raises ``RuntimeError`` when called after ``close_checkpointer()``
    so a straggler task never silently opens a new pool that nothing will close.
    """
    global _checkpointer, _pool
    # D7: latch guard — a straggler task calling get_checkpointer() AFTER shutdown
    # gets RuntimeError rather than a fresh pool that will never be closed.
    if _closed:
        raise RuntimeError(
            "get_checkpointer() called after close_checkpointer() — "
            "the checkpointer has been shut down and cannot be reused."
        )
    if _checkpointer is not None:
        return _checkpointer

    if not _is_postgres():
        from langgraph.checkpoint.memory import InMemorySaver

        logger.warning(
            "Checkpointer: DATABASE_URL is not Postgres — using InMemorySaver. "
            "HITL pauses work within the process but do NOT survive a restart."
        )
        _checkpointer = InMemorySaver()
        return _checkpointer

    # Windows local-dev guard: psycopg's async driver cannot run on the
    # ProactorEventLoop, which is the loop uvicorn forces on Windows (for
    # subprocess support). Attempting AsyncPostgresSaver there raises
    # "Psycopg cannot use the 'ProactorEventLoop'" on every run. Rather than
    # break local dev, fall back to InMemorySaver when we detect that loop.
    # Production runs on Linux (epoll-based SelectorEventLoop), so this branch
    # never triggers there and durable Postgres checkpointing is preserved.
    import asyncio
    import sys

    if sys.platform == "win32":
        try:
            _running_loop = asyncio.get_running_loop()
        except RuntimeError:
            _running_loop = None
        if _running_loop is not None and not isinstance(
            _running_loop, asyncio.SelectorEventLoop
        ):
            from langgraph.checkpoint.memory import InMemorySaver

            logger.warning(
                "Checkpointer: Postgres is configured but the running event loop "
                "is %s. psycopg's async driver requires a SelectorEventLoop, which "
                "uvicorn does not use on Windows — falling back to InMemorySaver. "
                "HITL pauses work within the process but do NOT survive a restart. "
                "This affects Windows local dev only; Linux/production keeps the "
                "durable Postgres checkpointer.",
                type(_running_loop).__name__,
            )
            _checkpointer = InMemorySaver()
            return _checkpointer

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    # psycopg wants a plain libpq DSN, not the SQLAlchemy "+driver" form.
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    _pool = AsyncConnectionPool(
        conninfo=dsn,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # idempotent table bootstrap
    logger.info("Checkpointer: AsyncPostgresSaver ready (durable HITL + resume).")
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the Postgres pool on app shutdown.

    D7 (KAN-139) hardening:
    1. **One-way ``_closed`` latch**: set BEFORE any global is nulled so a concurrent
       ``get_checkpointer()`` call arriving during shutdown sees the closed state.
    2. **Atomic global nulling BEFORE pool.close()**: nulls both ``_checkpointer`` and
       ``_pool`` before calling ``_pool.close()`` so a straggler ``get_checkpointer()``
       call AFTER the pool is half-closed gets ``RuntimeError`` instead of a new pool.
    3. **Non-raising on pool.close() failure**: catches any exception from
       ``pool.close()`` and logs a warning; the latch is already set and the globals are
       already null so the process state is consistent even on a failed close.
    4. **RuntimeError guard in get_checkpointer()**: callers after close get an
       immediate error, not a fresh pool that nothing will ever close.
    Idempotent: calling twice is safe (second call returns immediately at the latch).
    """
    global _checkpointer, _pool, _closed
    if _closed:
        return
    _closed = True
    # Null the globals FIRST so any concurrent get_checkpointer() call after this
    # point hits RuntimeError rather than returning a partially-closed pool.
    pool_to_close = _pool
    _pool = None
    _checkpointer = None
    if pool_to_close is not None:
        try:
            await pool_to_close.close()
        except Exception as exc:  # noqa: BLE001 — non-raising, latch already set
            logger.warning("close_checkpointer: pool.close() raised (non-fatal): %s", exc)
