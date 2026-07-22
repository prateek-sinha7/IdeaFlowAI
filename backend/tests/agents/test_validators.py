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
    """html_render with an unavailable browser emits NO blocking issues (skip-is-a-pass,
    default require_render=False) BUT records a distinct validator_skipped row so the
    skip is never swallowed (quick-260701-bob / VALIDATOR-SKIPPED)."""
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


# ════════════════════════════════════════════════════════════════════════════
# 4. Generic FixPolicy fix-loop — config-driven, NOT hardcoded prototype.html
# ════════════════════════════════════════════════════════════════════════════


class _FakeEngine:
    """Records the filename/max_attempts the kernel threads into the fix-loop."""

    def __init__(self):
        self.calls: list[dict] = []

    def _resolve_model(self, ectx, spec, model_id):
        return "fake-model"

    async def _run_validation_fix_loop(self, **kwargs):
        self.calls.append(kwargs)


class _FakeEctx:
    od_context = None
    disk_principal = "alice"
    checkpointer = None
    scoped_store = None
    build_task_number = ""
    build_task_total = ""
    current_task_block = ""
    current_prototype_skeleton = ""


class _FakeSpec:
    id = "code-gen"


class _FakeStep:
    agent_id = "code-gen"


def _make_kernel(engine):
    """Build a KernelServices wired to a fake engine (no live run)."""
    from agents.execution_engine.kernel_services import KernelServices

    return KernelServices(
        engine=engine,
        ectx=_FakeEctx(),
        sandbox=None,
        ordered_agents=[_FakeSpec()],
        user_message="idea",
        pipeline_run_id="run-x",
        pipeline_type="app_builder",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        results=[],
        cancel_event=None,
    )


@pytest.mark.asyncio
async def test_fixloop_drives_off_fixpolicy_deliverable():
    """The fix-loop runs against the FixPolicy deliverable (app.py), not prototype.html."""
    from agents.execution_engine.kernel_services import FixPolicy

    engine = _FakeEngine()
    kernel = _make_kernel(engine)
    await kernel.run_validation_fix_loop(
        _FakeStep(),
        task_num=1,
        total_tasks=1,
        agent_id="code-gen",
        policy=FixPolicy(deliverable="app.py", max_attempts=3),
    )
    assert engine.calls, "engine fix-loop was not invoked"
    call = engine.calls[0]
    assert call["filename"] == "app.py"     # config-driven, NOT prototype.html
    assert call["max_attempts"] == 3


@pytest.mark.asyncio
async def test_fixloop_filename_backcompat_wraps_default_policy():
    """A bare filename= caller is wrapped into a default FixPolicy (byte-identical)."""
    engine = _FakeEngine()
    kernel = _make_kernel(engine)
    await kernel.run_validation_fix_loop(
        _FakeStep(), task_num=1, total_tasks=1, filename="prototype.html",
    )
    call = engine.calls[0]
    assert call["filename"] == "prototype.html"
    assert call["max_attempts"] == 2   # the Phase-7 default bound


# ════════════════════════════════════════════════════════════════════════════
# 5. Tier#4/5/6 validators — register, run against a test manifest, design_quality
#    is non-blocking (P2/P3 only)
# ════════════════════════════════════════════════════════════════════════════


def test_tier_validators_resolve_after_discover():
    """spec_plan_coverage / task_done_when / design_quality each resolve."""
    registry = CapabilityRegistry()
    for name in ("spec_plan_coverage", "task_done_when", "design_quality"):
        v = registry.resolve("validator", name)
        assert v.name == name


@pytest.mark.asyncio
async def test_tier_spec_plan_coverage_flags_gap(db_session):
    """spec_plan_coverage flags a spec requirement with no matching plan task (P1)."""
    _seed_run(db_session, run_id="run-t4", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    runner = _FakeRunner(
        static_result=_StaticResult(ok=True), render_result=_RenderResult(),
        store=store, run_id="run-t4",
    )
    target = _Target(
        name="tasks.md", runner=runner, step="planner",
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
        static_result=_StaticResult(ok=True), render_result=_RenderResult(),
        store=store, run_id="run-t5",
    )
    target = _Target(
        name="app.py", runner=runner, step="code-gen",
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
        static_result=_StaticResult(ok=True), render_result=_RenderResult(),
        store=store, run_id="run-t6",
    )
    target = _Target(
        name="prototype.html", runner=runner, step="prototype-build",
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
        static_result=_StaticResult(ok=True), render_result=_RenderResult(),
        store=store, run_id="run-t7",
    )
    registry = CapabilityRegistry()
    target = _Target(
        name="x", runner=runner, step="s",
        task_meta={"done_when": ["does a thing not present"],
                   "spec_text": "## Foo\n", "plan_text": ""},
        content="unrelated body",
    )
    for name in ("spec_plan_coverage", "task_done_when", "design_quality"):
        await registry.resolve("validator", name).validate(target)

    rows = db_session.query(ValidationResult).filter(
        ValidationResult.run_id == "run-t7"
    ).all()
    written = {r.validator for r in rows}
    assert {"spec_plan_coverage", "task_done_when", "design_quality"} <= written
    assert all(r.owner_id == "alice" for r in rows)


# ════════════════════════════════════════════════════════════════════════════
# 6. task_loop re-point — drives the DECLARED registered validators, event-free
# ════════════════════════════════════════════════════════════════════════════


class _RoutingRunner:
    """A task_loop handle stub exercising the D-06 re-point helpers.

    Records make_fix_policy + deliverable_context + record_validation_result calls
    so the test proves task_loop routes the post-fix validation through the
    REGISTERED validators (resolve + the handle) without emitting any event.
    """

    def __init__(self):
        from agents.execution_engine.kernel_services import FixPolicy

        self._FixPolicy = FixPolicy
        self.run_id = "run-route"
        self.cancel_event = None
        self.fix_loop_calls: list[dict] = []
        self.validation_records: list[dict] = []
        self.deliverable_contexts: list[dict] = []
        self.static_result = _StaticResult(ok=True)
        self.render_result = _RenderResult(available=False)

    # — fix-loop —
    def make_fix_policy(self, deliverable, *, max_attempts=2):
        return self._FixPolicy(deliverable=deliverable, max_attempts=max_attempts)

    async def run_validation_fix_loop(self, step, **kwargs):
        self.fix_loop_calls.append(kwargs)

    # — registered validator target —
    def deliverable_context(self, *, name, step="", content=None, task_meta=None):
        self.deliverable_contexts.append(
            {"name": name, "step": step, "task_meta": dict(task_meta or {})}
        )
        return _Target(name=name, runner=self, step=step,
                       task_meta=dict(task_meta or {}))

    def static_check(self, path):
        return self.static_result

    async def render_check(self, path):
        return self.render_result

    async def record_validation_result(
        self, step, validator, *, severity=None, attempt=0, issues=None
    ):
        self.validation_records.append(
            {"step": step, "validator": validator, "attempt": attempt}
        )
        return f"vr-{len(self.validation_records)}"


class _RouteStep:
    agent_id = "prototype-build"
    validators = ["html_static", "html_render"]
    fix = None


@pytest.mark.asyncio
async def test_task_loop_runs_registered_validators_via_policy_and_handle():
    """task_loop's _run_registered_validators routes declared validators event-free."""
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy

    strat = TaskLoopStrategy()
    runner = _RoutingRunner()
    step = _RouteStep()

    # The FixPolicy is built via the handle (deliverable-driven, not prototype.html).
    policy = strat._fix_policy(runner, step, "prototype.html")
    assert policy is not None
    assert policy.deliverable == "prototype.html"
    assert policy.max_attempts == 2   # no declared step.fix → Phase-7 default

    # Running the declared validators writes validation_results rows per attempt
    # via the handle — and yields NO event (additive / event-free, D-06).
    await strat._run_registered_validators(
        runner, step, "prototype.html", task_num=2, total_tasks=3
    )
    written = {r["validator"] for r in runner.validation_records}
    assert written == {"html_static", "html_render"}
    # The attempt is keyed on the task number (the validation_results.attempt col).
    assert all(r["attempt"] == 2 for r in runner.validation_records)


@pytest.mark.asyncio
async def test_task_loop_no_validators_is_noop():
    """A step declaring no validators routes nothing (no validation_results rows)."""
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy

    strat = TaskLoopStrategy()
    runner = _RoutingRunner()

    class _NoValStep:
        agent_id = "code-gen"
        validators: list = []
        fix = None

    await strat._run_registered_validators(
        runner, _NoValStep(), "app.py", task_num=1, total_tasks=1
    )
    assert runner.validation_records == []
