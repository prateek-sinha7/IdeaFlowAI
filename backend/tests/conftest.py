"""Shared pytest fixtures for backend tests.

The former ``fk_session`` / ``make_fk_sqlite_engine`` FK-enforcing fixtures were
removed in 05-07 alongside their sole consumer (``test_artifact_store_fk.py``):
that regression covered the now-deleted thin-store ``workflow_artifacts`` FK path.
Tests that need an FK-enforcing in-memory SQLite session build it locally (see the
ScopedStore bootstrap in ``tests/unit/test_revision_intelligence.py`` / the typed
``artifact_refs`` suites).

ISS-102 — this module also carries the **offline live-model-client guard**: an
autouse fixture that makes constructing a real provider client (ChatAnthropic /
ChatBedrockConverse / ChatMistralAI) a loud test failure unless the test is
explicitly allowed. See ``_forbid_live_model_clients`` at the bottom of the file.

------------------------------------------------------------------------------
HERMETIC DATABASE (see ``_pin_database_url`` below)
------------------------------------------------------------------------------
The test suite must never touch a real database. Before this block existed it
did: ``app/models/database.py`` builds its engine at IMPORT time from
``settings.DATABASE_URL``, and ``backend/.env`` points that at the developer's
live ``flowin_local`` Postgres. Any test using ``SessionLocal`` / ``get_db``
without overriding the dependency therefore read and wrote a real database —
and only appeared to work because that database already had a migrated schema.

The symptom was a wall of
``psycopg2.errors.ForeignKeyViolation ... is not present in table "workflow_runs"``
on every run: the engine's best-effort persistence (PERSIST-02/03) writing run
events for runs whose parent row it never created. Those writes are swallowed,
so nothing failed — the suite was silently dependent on an external service.
"""

from __future__ import annotations

import functools
import importlib
import os

import pytest

import app.models  # noqa: F401 — importing the package registers every model on Base.metadata
import os
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# This MUST run before ``app.core.config`` / ``app.models.database`` are
# imported, because the engine is constructed at module import time. conftest.py
# is imported before any test module, so top-of-file is the only hook early
# enough — an autouse fixture would run long after the engine already exists.
# ---------------------------------------------------------------------------

# One database FILE per xdist worker. Two deliberate choices:
#
#   * A FILE, not ``sqlite:///:memory:``. SQLAlchemy gives an in-memory SQLite
#     engine a SingletonThreadPool, so each THREAD gets its own empty database.
#     FastAPI's TestClient runs endpoints on a threadpool, so a table created on
#     the test thread would be invisible to the request thread. A file is shared
#     across threads and behaves like the real thing.
#   * PER WORKER. Under ``-n auto`` every worker is a separate process; one
#     shared file would mean concurrent writers, SQLite lock contention, and
#     cross-test interference that looks like flakiness.
#
# ``PYTEST_DATABASE_URL`` is an explicit escape hatch for the suites that
# genuinely need Postgres (they start their own container and pass an explicit
# env to subprocesses — see ``test_phase8_resume.py``).
#   * PER PROCESS, not merely per worker. The worker id (`gw0`, `gw1`, …)
#     restarts from zero for every pytest invocation, so two suites running at
#     once — a developer's run alongside a CI run or a background one — both map
#     to `gw0` and share a file. One then deletes and recreates it under the
#     other, which surfaces as `sqlite3.DatabaseError: malformed database schema`
#     in whichever run lost the race. The pid makes each invocation's file its
#     own; it is stable for the life of the process, so sessionfinish removes
#     exactly the file sessionstart created.
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")
_DB_DIR = Path(tempfile.gettempdir()) / "velocity-pytest-db"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / f"test-{_WORKER}-{os.getpid()}.db"

# Start each worker from a clean database — a file left behind by a previous
# run would make results depend on run history.
if _DB_PATH.exists():
    _DB_PATH.unlink()

os.environ["DATABASE_URL"] = os.environ.get(
    "PYTEST_DATABASE_URL", f"sqlite:///{_DB_PATH}"
)

import pytest  # noqa: E402 — must follow the env pin above

import app.models  # noqa: F401,E402 — importing the package registers every model on Base.metadata


def pytest_sessionstart(session):  # noqa: ARG001
    """Create the schema in this worker's database.

    Tests that use the app's global ``SessionLocal`` previously inherited a
    schema from the developer's already-migrated Postgres. With a fresh file
    per worker there is nothing to inherit, so the tables have to be created —
    ``import app.models`` above has registered every model on ``Base.metadata``
    by the time this runs.

    ``create_all`` (not Alembic) on purpose: this is the CURRENT model schema,
    which is what these tests assert against. The migration chain has its own
    dedicated suites (``test_alembic.py`` / ``test_migrations.py``), and running
    it here would couple every test to migration health.
    """
    from app.models.database import Base, engine

    Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Drop this worker's database file — created per run, removed after."""
    try:
        if _DB_PATH.exists():
            _DB_PATH.unlink()
    except OSError:
        pass  # a leftover temp file must never fail a run


@pytest.fixture(autouse=True)
def _reset_checkpointer_shutdown_latch():
    """Release the checkpointer's one-way ``_closed`` latch between tests.

    ``close_checkpointer()`` sets a module-global ``_closed = True`` that is
    deliberately ONE-WAY (D7 / KAN-139): in production a process hosts exactly one
    app lifetime, and a straggler task calling ``get_checkpointer()`` after shutdown
    must get a ``RuntimeError`` rather than silently open a pool nothing will close.

    A pytest worker hosts MANY app lifetimes. Any test that runs the real lifespan —
    ``with TestClient(app)`` in ``tests/integration/test_handoff_api.py``, which
    triggers the shutdown hook at ``app/main.py:224`` — latches the flag for the rest
    of that worker's life, and every later test that reaches ``get_checkpointer()``
    dies with ``RuntimeError: ... called after close_checkpointer()``.

    That made the suite nondeterministic rather than merely broken: which tests share
    a worker with the latching test depends on xdist's scheduling, so the failure set
    moved between runs and vanished entirely when a file was run on its own.

    Resetting ONLY the latch restores the intended per-lifetime semantics without
    changing the cached-singleton behaviour tests already rely on (``close_checkpointer``
    nulls ``_checkpointer``/``_pool`` itself, so the next call rebuilds cleanly).
    """
    import app.agents.checkpointer as _cp

    _cp._closed = False
    yield
    _cp._closed = False


@pytest.fixture(autouse=True)
def _no_live_model_from_a_unit_test(request, monkeypatch):
    """Fail loudly if a grading unit test tries to build a REAL judge model.

    A test that forgets to fake `judge.grade` does not fail — it reaches the
    provider, hangs on the network and spends real tokens. That happened while
    writing these tests. Blowing up on the attempt turns a silent bill into an
    immediate, obvious error naming the missing fixture.
    """
    if "grading" not in request.node.nodeid:
        return
    import app.agents.model_factory

    def refuse(*_args, **_kwargs):
        raise AssertionError(
            "a unit test tried to build a REAL model — add the `judgements` fixture, "
            "or patch build_model yourself if that is what you are testing"
        )

    # Applied first, so a test that deliberately patches build_model still wins.
    monkeypatch.setattr(app.agents.model_factory, "build_model", refuse)

# ═══════════════════════════════════════════════════════════════════════════════
# ISS-102 — offline live-model-client construction guard
#
# Why the guard exists at all: the suite has **no offline-by-default state**.
# ``AWS_REGION`` (app/core/config.py:130), ``BEDROCK_INFERENCE_PROFILE_ID`` (:123)
# and ``BEDROCK_MODEL_ID`` (:118) are hardcoded CODE defaults and there is no
# ``backend/.env`` file, so unsetting env vars cannot make ``build_model()``
# offline. The only thing standing between this suite and an AWS bill is whether
# credentials happen to resolve — which they now do on this machine.
#
# Why the three provider CLASSES rather than ``build_model()``: a ``build_model``
# guard would be theatre. ``agents/planner/smart_planner.py:173/:189/:196``
# bypasses ``build_model()`` entirely, and ``deepagents.create_deep_agent(
# model="anthropic:...")`` constructs ChatAnthropic through langchain's own
# ``init_chat_model`` — a ``build_model`` guard misses all six of those. It would
# also be defeated by the by-value ``from app.agents.model_factory import
# build_model`` imports at ``deep_agent_runner.py:58`` and ``cached_invoke.py:44``.
# The app has no ``init_chat_model`` call, no direct boto3 bedrock-runtime invoke
# and no raw anthropic/httpx model call, so these three classes are the true
# chokepoint.
# ═══════════════════════════════════════════════════════════════════════════════

# LATENT-HAZARD CLASS (D6). Every nodeid below CONSTRUCTS a real provider client
# but never invokes it, so it costs nothing today — one added ``.ainvoke`` /
# ``.astream`` in any of them turns it into live spend. They are filed as their
# own ISS row; do NOT modify those test files to "fix" this here.
#
# Why a nodeid dict rather than a marker on each test (D5): the whole guard stays
# in ONE reviewable, greppable file instead of scattering exemptions across four
# test files, and it FAILS CLOSED — rename a test and it drops out of this dict,
# so the guard fires loudly instead of silently keeping an exemption it should
# have lost. Matching is therefore EXACT nodeid membership: no prefix matching,
# no parametrize-suffix stripping.
_CONSTRUCTS_BUT_NEVER_INVOKES: dict[str, str] = {
    "tests/unit/test_brief_max_chars.py::test_full_brief_reaches_planner_uncut":
        "SmartPlanner builds its model, then the test asserts on the composed prompt only; the model is never invoked.",
    "tests/unit/test_brief_max_chars.py::test_ceiling_still_enforced_above_cap":
        "Same SmartPlanner prompt-only assertion at the cap boundary; construction only.",
    "tests/unit/test_cached_invoke.py::test_bedrock_call_places_cache_control_on_stable_prefix":
        "Builds a real ChatBedrockConverse to exercise cache_control shaping; the request is never sent.",
    "tests/unit/test_cached_invoke.py::test_cache_control_suppressed_when_flag_off":
        "Same cache_control shaping with the flag off; construction only.",
    "tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_present_when_design_context_supplied":
        "SmartPlanner design-note prompt assertion; construction only.",
    "tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_absent_when_design_context_none":
        "Same, design context absent; construction only.",
    "tests/agents/test_iss056_clarify_quality_fixes.py::TestH3SmartPlannerDesignNote::test_design_note_absent_when_both_names_missing":
        "Same, both names missing; construction only.",
    "tests/agents/test_mcp_client.py::test_bound_mcp_tool_augments_a_deepagents_agent":
        "create_deep_agent resolves the 'anthropic:' model string via init_chat_model; the graph is inspected, never run.",
}


class LiveModelClientConstructed(BaseException):
    """Raised when an offline test constructs a real LLM provider client.

    Derives from ``BaseException``, NOT ``Exception``, on purpose.
    ``app/agents/deep_agent_runner.py:586`` is
    ``except Exception as exc:  # noqa: BLE001 — mirror the legacy swallow``, which
    converts the exception into a yielded ``{"type": "error"}`` event — that is
    precisely how the ISS-102 ``ExpiredTokenException`` surfaced as a log line at
    :610 instead of a test failure. An ``Exception``-derived guard error raised on
    that path would be swallowed the same way and the test would pass silently,
    which is the opposite of this guard's purpose. Verified on pytest 8.3.4: a
    custom ``BaseException`` subclass is reported as a normal ``FAILED`` and the
    session continues; only ``KeyboardInterrupt`` and ``Exit`` abort a run.
    """


@functools.lru_cache(maxsize=1)
def _guarded_classes() -> tuple[tuple[str, type], ...]:
    """Resolve the provider classes to guard, skipping any that aren't installed.

    Resolved lazily inside the function rather than at module import so the
    ~0.84s cost of importing ``langchain_aws`` + ``langchain_anthropic`` is paid
    once per session on first use, and never at collection time.
    ``langchain_mistralai`` is not installed on this machine (it is also the cause
    of the six pre-existing ``test_model_factory.py`` reds), so each class is
    resolved in its own try/except and simply skipped when unavailable.
    """
    targets = (
        ("langchain_anthropic", "ChatAnthropic"),
        ("langchain_aws", "ChatBedrockConverse"),
        ("langchain_mistralai", "ChatMistralAI"),
    )
    resolved: list[tuple[str, type]] = []
    for module_name, class_name in targets:
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except (ImportError, AttributeError):
            continue
        resolved.append((class_name, cls))
    return tuple(resolved)


def _blocked_init(nodeid: str, class_name: str):
    """Build the replacement ``__init__`` that refuses construction, loudly."""

    def __init__(self, *args, **kwargs):
        raise LiveModelClientConstructed(
            f"ISS-102 — offline test constructed a LIVE model client.\n"
            f"  test:  {nodeid}\n"
            f"  class: {class_name}\n"
            f"This test would make a real, billable provider call. Fix it in one of "
            f"three ways:\n"
            f"  (a) patch the construction seam in the test — e.g. "
            f"monkeypatch.setattr(rc_module, \"_resolve_concierge\", lambda: fake), or "
            f"replace the class attribute on the SOURCE module the way "
            f"tests/unit/test_model_factory.py:77/83/89 already does;\n"
            f"  (b) mark the test @pytest.mark.requires_api_key if it genuinely needs a "
            f"live provider;\n"
            f"  (c) if it provably constructs but NEVER invokes, add its nodeid plus a "
            f"one-line reason to _CONSTRUCTS_BUT_NEVER_INVOKES in "
            f"backend/tests/conftest.py."
        )

    return __init__


@pytest.fixture(autouse=True)
def _forbid_live_model_clients(request, monkeypatch):
    """Make constructing a real LLM provider client a loud failure (ISS-102).

    Lives in the root conftest so it covers all of ``testpaths = ["tests"]``;
    ``tests/agents/conftest.py`` declares no autouse fixture and does not conflict.

    Exactly three allowances, no others:
      1. ``RUN_LIVE_BEDROCK=1`` — the established env opt-in for live suites.
      2. the ``requires_api_key`` marker (declared in ``backend/pyproject.toml``).
      3. an exact nodeid match in ``_CONSTRUCTS_BUT_NEVER_INVOKES``.

    Patches ``__init__`` on the real class and NEVER replaces the class object, so
    ``isinstance()`` keeps working (``deep_agent_runner._maybe_apply:234``,
    ``cached_invoke:79``), ``object.__new__(ChatBedrockConverse)`` keeps working
    (``tests/agents/test_bedrock_cache_and_thinking.py::_bedrock_instance``), and
    tests that swap the whole class attribute on the source module are unaffected —
    the factory picks up their stub and never reaches the real class. monkeypatch
    restores ``__init__`` after every test.
    """
    if os.getenv("RUN_LIVE_BEDROCK") == "1":
        return
    if request.node.get_closest_marker("requires_api_key") is not None:
        return
    nodeid = request.node.nodeid
    if nodeid in _CONSTRUCTS_BUT_NEVER_INVOKES:
        return
    for class_name, cls in _guarded_classes():
        monkeypatch.setattr(cls, "__init__", _blocked_init(nodeid, class_name))
