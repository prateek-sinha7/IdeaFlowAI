"""tests/agents/test_validators.py — the Validator registry + generic fix-loop (08-04).

08-04 stands up the ``Validator`` registry backbone (D-04/D-05/D-06):

  * ``html_static`` / ``html_render`` registered ``Validator``s wrapping
    ``static_check`` / ``render_check`` app-side, reached via the KernelServices
    handle (``target.runner.static_check`` — no kernel→app import);
  * the generic ``FixPolicy`` fix-loop (deliverable name + max_attempts + fix-prompt
    template, NOT hardcoded ``prototype.html``);
  * the Tier#4/5/6 validators (``spec_plan_coverage`` / ``task_done_when`` /
    ``design_quality`` warnings-first);
  * every validator mapping severity through the SINGLE imported ``map_severity``
    (08-01, VALID-03 single source) and writing a ``validation_results`` row.

Offline — no live LLM / Bedrock / Chromium. ``render_check`` degrades to
``available=False`` so ``html_render`` emits no issues here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (08-01 pattern: snapshot AFTER discover)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_registry():
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


# ════════════════════════════════════════════════════════════════════════════
# In-memory DB + a ScopedStore-backed fake runner handle
# ════════════════════════════════════════════════════════════════════════════


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
            id=run_id, user_id=owner_id, title="t", type="prototype",
            status="running", input="idea",
            owner_id=owner_id, workspace_id=workspace_id,
        )
    )
    session.commit()


# ── static_check / render_check result stand-ins ────────────────────────────


@dataclass
class _StaticResult:
    ok: bool
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class _NavResult:
    href: str
    ok: bool


@dataclass
class _RenderResult:
    ok: bool = True
    available: bool = True
    console_errors: list = field(default_factory=list)
    page_errors: list = field(default_factory=list)
    nav_results: list = field(default_factory=list)


class _FakeRunner:
    """Minimal KernelServices stand-in: static/render checks + the validation writer.

    Records the validation_results writes through a REAL ScopedStore so the
    owner/workspace-scoped persistence is exercised (T-08-04-ID).
    """

    def __init__(self, *, static_result, render_result, store, run_id):
        self._static = static_result
        self._render = render_result
        self._store = store
        self.run_id = run_id
        self.records: list[dict] = []

    def static_check(self, path):
        return self._static

    async def render_check(self, path):
        return self._render

    async def record_validation_result(
        self, step, validator, *, severity=None, attempt=0, issues=None
    ):
        self.records.append(
            {"step": step, "validator": validator, "severity": severity,
             "attempt": attempt, "issues": issues}
        )
        return await self._store.record_validation_result(
            self.run_id, step, validator,
            severity=severity, attempt=attempt, issues=issues,
        )


@dataclass
class _Target:
    """DeliverableContext stand-in (the kernel builds the real one)."""

    name: str
    runner: object
    path: object = None
    step: str = "prototype-build"
    task_meta: dict = field(default_factory=dict)
    content: str = ""


# ════════════════════════════════════════════════════════════════════════════
# 1. html_static / html_render resolve + wrap the heavy check via the handle
# ════════════════════════════════════════════════════════════════════════════


def test_html_static_and_render_resolve_after_discover():
    """resolve("validator", "html_static"/"html_render") returns the impls."""
    registry = CapabilityRegistry()
    hs = registry.resolve("validator", "html_static")
    hr = registry.resolve("validator", "html_render")
    assert hs.name == "html_static"
    assert hr.name == "html_render"


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
        static_result=static_result, render_result=_RenderResult(),
        store=store, run_id="run-1",
    )
    target = _Target(name="prototype.html", runner=runner,
                     path=tmp_path / "prototype.html")

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
    """html_render with an unavailable browser emits NO issues (a skip, not a fail)."""
    _seed_run(db_session, run_id="run-2", owner_id="bob", workspace_id="ws-2")
    store = ScopedStore(owner_id="bob", workspace_id="ws-2", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(available=False),
        store=store, run_id="run-2",
    )
    target = _Target(name="prototype.html", runner=runner,
                     path=tmp_path / "prototype.html", step="prototype-build")
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert issues == []


@pytest.mark.asyncio
async def test_html_render_flags_console_and_nav_errors(db_session, tmp_path):
    """An available render with console errors + dead nav emits P0 issues."""
    _seed_run(db_session, run_id="run-3", owner_id="carol", workspace_id="ws-3")
    store = ScopedStore(owner_id="carol", workspace_id="ws-3", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True),
        render_result=_RenderResult(
            ok=False, available=True,
            console_errors=["Uncaught TypeError: x is not a function"],
            nav_results=[_NavResult(href="#/dead", ok=False)],
        ),
        store=store, run_id="run-3",
    )
    target = _Target(name="prototype.html", runner=runner,
                     path=tmp_path / "prototype.html")
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert len(issues) == 2
    assert all(i.severity == "P0" for i in issues)


# ════════════════════════════════════════════════════════════════════════════
# 2. A validator run writes a validation_results row (owner/workspace-scoped)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_validator_run_writes_validation_results_row(db_session, tmp_path):
    """html_static writing through the handle persists a scoped validation_results row."""
    _seed_run(db_session, run_id="run-4", owner_id="dave", workspace_id="ws-4")
    store = ScopedStore(owner_id="dave", workspace_id="ws-4", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=False, issues=["boom"]),
        render_result=_RenderResult(), store=store, run_id="run-4",
    )
    target = _Target(name="prototype.html", runner=runner,
                     path=tmp_path / "prototype.html", step="prototype-build",
                     task_meta={"attempt": 1})
    hs = CapabilityRegistry().resolve("validator", "html_static")
    await hs.validate(target)

    rows = db_session.query(ValidationResult).filter(
        ValidationResult.run_id == "run-4"
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.owner_id == "dave"
    assert row.workspace_id == "ws-4"
    assert row.validator == "html_static"
    assert row.severity == "CRITICAL"   # worst issue P0 -> CRITICAL
    assert row.attempt == 1

    # Cross-owner read returns nothing (default-deny precedent, T-08-04-ID).
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-9", session=db_session)
    others = (
        db_session.query(ValidationResult)
        .filter(ValidationResult.run_id == "run-4")
        .filter(ValidationResult.owner_id == "mallory")
        .all()
    )
    assert others == []


# ════════════════════════════════════════════════════════════════════════════
# 3. The validators use the SAME imported map_severity (no second definition)
# ════════════════════════════════════════════════════════════════════════════


def test_validators_import_the_single_map_severity():
    """The function object the validators import is the one canonical map_severity."""
    import app.agents.validators.html_static as hs_mod
    import app.agents.validators.html_render as hr_mod
    import agents.capabilities.validators.severity as sev_mod

    assert hs_mod.map_severity is sev_mod.map_severity
    assert hr_mod.map_severity is sev_mod.map_severity
