"""Validator runs that PERSIST — scoped ``validation_results`` rows (08-04).

Moved out of ``tests/unit/agents/test_validators.py`` in Batch 6. These eight tests
seed a ``workflow_runs`` parent row and drive each validator through a REAL
``ScopedStore`` so the owner/workspace-scoped ``validation_results`` write is genuinely
exercised (T-08-04-ID) — that needs a real engine and a real ORM mapping.

Still in the unit suite: validator resolution, the single-``map_severity`` identity
check, the generic ``FixPolicy`` fix-loop, and the ``task_loop`` re-point routing — all
of which run against fakes with no database.

The stand-ins (static/render results, the deliverable target, the recording runner) are
shared with the unit half and live in ``tests/fakes/validation_stubs.py``.

Offline — no live LLM / Bedrock / Chromium: ``render_check`` is stubbed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import agents.capabilities.registry as registry_mod
from agents.authz import ScopedStore
from agents.capabilities.registry import CapabilityRegistry
from agents.capabilities.validators.severity import map_severity
from app.models.database import Base
from app.models.validation_results import ValidationResult
from app.models.workflow import WorkflowRun
from tests.fakes.validation_stubs import (
    _FakeRunner,
    _NavResult,
    _RenderResult,
    _StaticResult,
    _Target,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Snapshot the capability registry after ``discover()`` and restore it after.

    Mirrors the identical fixture in ``tests/unit/agents/test_validators.py`` (08-01
    pattern). Kept local to both files rather than promoted to a conftest because
    making it autouse for a whole folder would change registry behaviour for every
    other test there; worth revisiting as one shared plugin fixture.
    """
    registry_mod.discover()  # bind built-ins (+ app-side validators) before snapshot
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED
    try:
        yield
    finally:
        registry_mod._KNOWN.clear()
        registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear()
        registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear()
        registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_run(session, *, run_id, owner_id, workspace_id):
    session.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="t",
            type="prototype",
            status="running",
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
    )
    session.commit()


@pytest.mark.asyncio
async def test_html_static_reaches_static_check_via_handle(db_session, tmp_path):
    """html_static.validate reaches static_check via target.runner + maps severity."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    static_result = _StaticResult(
        ok=False,
        issues=["dead nav link: href '#/x' has no matching section"],
        warnings=["orphan section: data-page='y' has no nav link"],
    )
    runner = _FakeRunner(
        static_result=static_result,
        render_result=_RenderResult(),
        store=store,
        run_id="run-1",
    )
    target = _Target(
        name="prototype.html", runner=runner, path=tmp_path / "prototype.html"
    )

    hs = CapabilityRegistry().resolve("validator", "html_static")
    issues = await hs.validate(target)

    # One fatal issue (P0/CRITICAL) + one advisory warning (P3/LOW).
    assert any(i.severity == "P0" for i in issues)
    assert any(i.severity == "P3" for i in issues)
    # The validator maps through the imported map_severity (single source).
    assert map_severity("P0") == "CRITICAL"
    assert map_severity("P3") == "LOW"


@pytest.mark.asyncio
async def test_html_render_degrades_offline(db_session, tmp_path):
    """html_render with an unavailable browser emits NO blocking issues (skip-is-a-pass,
    default require_render=False) BUT records a distinct validator_skipped row so the
    skip is never swallowed (quick-260701-bob / VALIDATOR-SKIPPED)."""
    _seed_run(db_session, run_id="run-2", owner_id="bob", workspace_id="ws-2")
    store = ScopedStore(owner_id="bob", workspace_id="ws-2", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(available=False),
        store=store,
        run_id="run-2",
    )
    target = _Target(
        name="prototype.html",
        runner=runner,
        path=tmp_path / "prototype.html",
        step="prototype-build",
    )
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert issues == []
    # The skip is RECORDED (severity=SKIPPED sentinel) — not silently dropped.
    skips = [r for r in runner.records if r["severity"] == "SKIPPED"]
    assert len(skips) == 1
    assert skips[0]["validator"] == "html_render"


@pytest.mark.asyncio
async def test_html_render_flags_console_and_nav_errors(db_session, tmp_path):
    """An available render with console errors + dead nav emits P0 issues."""
    _seed_run(db_session, run_id="run-3", owner_id="carol", workspace_id="ws-3")
    store = ScopedStore(owner_id="carol", workspace_id="ws-3", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(
            ok=False,
            available=True,
            console_errors=["Uncaught TypeError: x is not a function"],
            nav_results=[_NavResult(href="#/dead", ok=False)],
        ),
        store=store,
        run_id="run-3",
    )
    target = _Target(
        name="prototype.html", runner=runner, path=tmp_path / "prototype.html"
    )
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert len(issues) == 2
    assert all(i.severity == "P0" for i in issues)


@pytest.mark.asyncio
async def test_validator_run_writes_validation_results_row(db_session, tmp_path):
    """html_static writing through the handle persists a scoped validation_results row."""
    _seed_run(db_session, run_id="run-4", owner_id="dave", workspace_id="ws-4")
    store = ScopedStore(owner_id="dave", workspace_id="ws-4", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=False, issues=["boom"]),
        render_result=_RenderResult(),
        store=store,
        run_id="run-4",
    )
    target = _Target(
        name="prototype.html",
        runner=runner,
        path=tmp_path / "prototype.html",
        step="prototype-build",
        task_meta={"attempt": 1},
    )
    hs = CapabilityRegistry().resolve("validator", "html_static")
    await hs.validate(target)

    rows = (
        db_session.query(ValidationResult)
        .filter(ValidationResult.run_id == "run-4")
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.owner_id == "dave"
    assert row.workspace_id == "ws-4"
    assert row.validator == "html_static"
    assert row.severity == "CRITICAL"  # worst issue P0 -> CRITICAL
    assert row.attempt == 1

    # Cross-owner read returns nothing (default-deny precedent, T-08-04-ID).
    _mallory = ScopedStore(owner_id="mallory", workspace_id="ws-9", session=db_session)
    others = (
        db_session.query(ValidationResult)
        .filter(ValidationResult.run_id == "run-4")
        .filter(ValidationResult.owner_id == "mallory")
        .all()
    )
    assert others == []


@pytest.mark.asyncio
async def test_tier_spec_plan_coverage_flags_gap(db_session):
    """spec_plan_coverage flags a spec requirement with no matching plan task (P1)."""
    _seed_run(db_session, run_id="run-t4", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(),
        store=store,
        run_id="run-t4",
    )
    target = _Target(
        name="tasks.md",
        runner=runner,
        step="planner",
        task_meta={
            "spec_text": "## Authentication\n## Payments\n",
            "plan_text": "## Task 1: build authentication login form\n",
        },
    )
    v = CapabilityRegistry().resolve("validator", "spec_plan_coverage")
    issues = await v.validate(target)
    # 'payments' is uncovered → a P1 coverage gap; 'authentication' is covered.
    assert any("payments" in i.message.lower() for i in issues)
    assert all(i.severity == "P1" for i in issues)


@pytest.mark.asyncio
async def test_tier_task_done_when_flags_unmet_criterion(db_session):
    """task_done_when flags a done_when criterion with no evidence in the deliverable."""
    _seed_run(db_session, run_id="run-t5", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(),
        store=store,
        run_id="run-t5",
    )
    target = _Target(
        name="app.py",
        runner=runner,
        step="code-gen",
        task_meta={"done_when": ["renders a pricing table", "exports a CSV report"]},
        content="def render_pricing_table(): ...",
    )
    v = CapabilityRegistry().resolve("validator", "task_done_when")
    issues = await v.validate(target)
    # The CSV criterion has no evidence → P1; the pricing-table one is evidenced.
    assert any("csv" in i.message.lower() for i in issues)
    assert all(i.severity == "P1" for i in issues)


@pytest.mark.asyncio
async def test_tier_design_quality_is_non_blocking(db_session):
    """design_quality emits ONLY P2/P3 — it can never block (warnings-first)."""
    _seed_run(db_session, run_id="run-t6", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(),
        store=store,
        run_id="run-t6",
    )
    target = _Target(
        name="prototype.html",
        runner=runner,
        step="prototype-build",
        content=(
            "<html><body><p>Lorem ipsum placeholder</p>"
            "<img src='x.png'></body></html>"
        ),
    )
    v = CapabilityRegistry().resolve("validator", "design_quality")
    issues = await v.validate(target)
    assert issues, "design_quality should surface placeholder/a11y advisories"
    # NON-BLOCKING invariant: never P0/P1 (the gate blocks only on CRITICAL/P0).
    assert all(i.severity in ("P2", "P3") for i in issues)
    labels = {map_severity(i.severity) for i in issues}
    assert labels <= {"MEDIUM", "LOW"}


@pytest.mark.asyncio
async def test_tier_validators_write_validation_results_rows(db_session):
    """Each Tier validator run persists a validation_results row (owner-scoped)."""
    _seed_run(db_session, run_id="run-t7", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(),
        store=store,
        run_id="run-t7",
    )
    registry = CapabilityRegistry()
    target = _Target(
        name="x",
        runner=runner,
        step="s",
        task_meta={
            "done_when": ["does a thing not present"],
            "spec_text": "## Foo\n",
            "plan_text": "",
        },
        content="unrelated body",
    )
    for name in ("spec_plan_coverage", "task_done_when", "design_quality"):
        await registry.resolve("validator", name).validate(target)

    rows = (
        db_session.query(ValidationResult)
        .filter(ValidationResult.run_id == "run-t7")
        .all()
    )
    written = {r.validator for r in rows}
    assert {"spec_plan_coverage", "task_done_when", "design_quality"} <= written
    assert all(r.owner_id == "alice" for r in rows)
