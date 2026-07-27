"""Shared fixtures for the eval suite (tests/evals).

Conventions (design.md D-02/D-03/D-04):
  - every module in this package sets ``pytestmark = pytest.mark.eval``;
  - default tier is fully offline (scripted models, no network, 0 tokens) —
    the ``runs_root`` fixture gives each test a writable sandbox root so the
    real ``RunSandbox`` works locally (the shipped default ``/app/runs`` is
    not writable on dev machines);
  - scenario declarations live in ``revision_fulfillment/fixtures/scenarios.yaml``
    and are loaded via the ``scenarios`` fixture (intent as data, scripted
    tool-call mechanics as code — D-05).
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "revision_fulfillment" / "fixtures"


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    """Point ``settings.RUNS_ROOT`` at a fresh temp dir for this test.

    ``RunSandbox.__init__`` reads ``settings.RUNS_ROOT`` at call time, so a
    runtime settings patch is sufficient (same approach as the runtime patch
    in ``tests/agents/_scripted_model.py``).
    """
    from app.core.config import settings

    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setattr(settings, "RUNS_ROOT", str(root))
    return root


@pytest.fixture(scope="session", autouse=True)
def _hermetic_db():
    """Point the sync ``app.models.database`` engine at an in-memory SQLite DB
    for the whole eval session, and skip the checkpointer's Postgres branch.

    ``app.models.database.engine``/``SessionLocal`` are built ONCE at import
    time from ``settings.DATABASE_URL`` — patching ``settings`` per-test is too
    late, the module is already imported by the time a test fixture runs. So
    this swaps the module-level ``engine``/``SessionLocal`` objects directly
    (session-scoped: once, before any eval test runs) rather than the setting.
    ``StaticPool`` keeps every connection on the one shared in-memory DB (the
    default SQLite in-memory behavior is one DB PER connection, which would
    make each session see an empty database).

    Without this, every persistence call in the pipeline (run_events,
    artifact_refs, hooks, WorkflowMemory — a SEPARATE subsystem from the
    LangGraph checkpointer patched per-test in test_scenarios.py) tries the
    real Postgres URL from the dev env, fails with a connection-refused
    warning per call (or worse, hangs retrying if Postgres is reachable but
    slow), and clutters output — all while degrading gracefully by design
    (PERSIST-02/03 best-effort), so tests still pass, just noisily. This makes
    the whole eval suite fully offline (D-03), matching the checkpointer fix.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models.database as db

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.Base.metadata.create_all(bind=test_engine)
    db.engine = test_engine
    db.SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, expire_on_commit=False, bind=test_engine
    )


@pytest.fixture(scope="session")
def scenarios() -> dict:
    """Load the S1/S2/S3 scenario matrix (scenarios.yaml) keyed by id.

    Returns an empty dict until the file exists (T-014) so Phase-0/1 tests
    can depend on the loader without ordering coupling.
    """
    path = FIXTURES_DIR / "scenarios.yaml"
    if not path.is_file():
        return {}
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {s["id"]: s for s in data.get("scenarios", [])}
