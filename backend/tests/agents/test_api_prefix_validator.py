"""tests/agents/test_api_prefix_validator.py — the ``api_prefix`` validator (19-02 / ISS-005).

Covers the deterministic ``/api/v1`` backstop:

  * Task 1 — the pure-stdlib ``api_prefix`` Validator: a violation infra file (a bare
    ``/health`` healthcheck / nginx ``location /health`` / smoke ``curl .../users``)
    yields exactly one P2 ``Issue`` per violation AND records a ``validation_results``
    row; a clean ``/api/v1/...`` target yields zero issues; an empty/absent sandbox
    degrades to ``[]`` without raising.
  * Task 2 — the BLOCKER guard: after ``discover()`` both new ``resolve()`` pairs
    (``post_step:api_prefix_audit`` + ``validator:api_prefix``) return an instance
    (not raise), proving ``_builtin_modules`` fired ``@register`` → ``_IMPLS`` is bound.
  * Task 2 — the INV-3 fault-injection: the ``ValidationGate`` wiring (the REJECTED
    hack) emits a ``validation_warning`` event on a residual P2 — the event the
    app_builder golden does NOT contain — proving WHY the event-free post_step is
    required.

Offline — no live LLM / Bedrock / Chromium. The validation_results write goes through
a REAL ScopedStore so the owner/workspace-scoped persistence is exercised (T-08-04-ID).
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
from agents.capabilities.validators.api_prefix import ApiPrefixValidator
from app.models.database import Base
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (08-01 pattern: snapshot AFTER discover)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_registry():
    registry_mod.discover()  # bind built-ins (incl. the 19-02 modules) before snapshot
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
# In-memory DB + a ScopedStore-backed fake runner handle + a tmp-dir sandbox
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
            id=run_id, user_id=owner_id, title="t", type="app_builder",
            status="running", input="idea",
            owner_id=owner_id, workspace_id=workspace_id,
        )
    )
    session.commit()


@dataclass
class _FakeSandbox:
    """RunSandbox stand-in: only ``.root`` is read by the validator's globber."""

    root: Path


class _FakeRunner:
    """Minimal KernelServices stand-in: a sandbox + the validation_results writer.

    Records the validation_results writes through a REAL ScopedStore so the
    owner/workspace-scoped persistence is exercised (T-08-04-ID).
    """

    def __init__(self, *, sandbox, store, run_id):
        self.sandbox = sandbox
        self._store = store
        self.run_id = run_id
        self.records: list[dict] = []

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
    step: str = "app-infra-generator"
    task_meta: dict = field(default_factory=dict)
    content: str = ""


def _make_target(tmp_path, db_session, *, infra_files: dict[str, str]):
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    for rel, body in infra_files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    runner = _FakeRunner(sandbox=_FakeSandbox(root=tmp_path), store=store, run_id="run-1")
    return _Target(name="app", runner=runner), runner


# ════════════════════════════════════════════════════════════════════════════
# 1. Task 1 — the validator's four behaviors
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_violation_yields_one_p2_issue_and_records_row(tmp_path, db_session):
    """A bare ``/health`` healthcheck → exactly one P2 Issue + one recorded row."""
    target, runner = _make_target(
        tmp_path,
        db_session,
        infra_files={
            "Dockerfile": (
                "FROM node:20\n"
                'HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1\n'
            ),
        },
    )
    validator = ApiPrefixValidator()
    issues = await validator.validate(target)

    p2 = [i for i in issues if i.severity == "P2"]
    assert len(p2) == 1, f"expected exactly one P2 issue, got {issues!r}"
    assert "/health" in p2[0].message
    assert "/api/v1" in p2[0].message
    # record_validation_result awaited exactly once with a MEDIUM (P2) severity.
    assert len(runner.records) == 1
    assert runner.records[0]["severity"] == "MEDIUM"
    assert runner.records[0]["issues"], "the recorded row must carry the issues payload"


@pytest.mark.asyncio
async def test_nginx_location_violation_is_flagged(tmp_path, db_session):
    """An nginx ``location /users`` block → one P2 Issue."""
    target, runner = _make_target(
        tmp_path,
        db_session,
        infra_files={"nginx.conf": "server {\n  location /users {\n    proxy_pass http://app;\n  }\n}\n"},
    )
    validator = ApiPrefixValidator()
    issues = await validator.validate(target)
    assert [i.severity for i in issues] == ["P2"]
    assert "/users" in issues[0].message


@pytest.mark.asyncio
async def test_clean_api_v1_target_yields_zero_issues(tmp_path, db_session):
    """Endpoints all under ``/api/v1`` → zero issues (a row may still be recorded)."""
    target, runner = _make_target(
        tmp_path,
        db_session,
        infra_files={
            "Dockerfile": (
                "FROM node:20\n"
                'HEALTHCHECK CMD curl -f http://localhost:8080/api/v1/health || exit 1\n'
            ),
            "nginx.conf": "server {\n  location /api/v1/ {\n    proxy_pass http://app;\n  }\n}\n",
        },
    )
    validator = ApiPrefixValidator()
    issues = await validator.validate(target)
    assert issues == [], f"clean /api/v1 target must yield zero issues, got {issues!r}"
    # spec_plan_coverage-style always-record behavior: a row is still written.
    assert len(runner.records) == 1
    assert runner.records[0]["severity"] is None


@pytest.mark.asyncio
async def test_absent_sandbox_degrades_to_empty(db_session):
    """A runner whose sandbox is absent → ``[]`` without raising (degrade-not-crash)."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    class _NoSandboxRunner(_FakeRunner):
        def __init__(self):
            self.sandbox = None
            self._store = store
            self.run_id = "run-1"
            self.records = []

    target = _Target(name="app", runner=_NoSandboxRunner())
    validator = ApiPrefixValidator()
    issues = await validator.validate(target)
    assert issues == []


@pytest.mark.asyncio
async def test_empty_sandbox_no_infra_files_yields_empty(tmp_path, db_session):
    """An empty sandbox (no infra files) → ``[]`` (the golden-run degrade path)."""
    target, runner = _make_target(tmp_path, db_session, infra_files={})
    validator = ApiPrefixValidator()
    issues = await validator.validate(target)
    assert issues == []


def test_single_api_prefix_constant():
    """SC-001: the module defines exactly one ``API_PREFIX = '/api/v1'`` constant."""
    from agents.capabilities.validators import api_prefix as mod

    assert mod.API_PREFIX == "/api/v1"


# ════════════════════════════════════════════════════════════════════════════
# 2. Task 2 — the BLOCKER guard: resolve() returns an instance for BOTH new pairs
# ════════════════════════════════════════════════════════════════════════════


def test_resolve_returns_instances_for_both_new_pairs():
    """After ``discover()``, BOTH new (kind,name) pairs resolve to a bound instance.

    This directly proves ``discover()``'s ``_builtin_modules`` tuple fired ``@register``
    on BOTH new modules → ``_IMPLS`` is bound → ``resolve()`` returns an instance
    instead of raising ``RuntimeError("known but has no bound impl")`` at the engine
    post_step seam (engine.py:~1720).
    """
    reg = CapabilityRegistry()
    post = reg.resolve("post_step", "api_prefix_audit")
    val = reg.resolve("validator", "api_prefix")
    assert getattr(post, "name", None) == "api_prefix_audit"
    assert getattr(val, "name", None) == "api_prefix"


# ════════════════════════════════════════════════════════════════════════════
# 3. Task 2 — the INV-3 fault-injection: the gate wiring (REJECTED) emits an event
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gate_wiring_emits_validation_warning(tmp_path, db_session):
    """FAULT-INJECTION: wiring api_prefix through the ``validation`` gate emits a
    ``validation_warning`` event on a residual P2 — the event the app_builder golden
    does NOT contain. This proves WHY the event-free post_step (NOT a gate) is the
    load-bearing INV-3 decision: the gate path would break the byte-identical golden.
    """
    from agents.capabilities.gates.validation import ValidationGate

    target, runner = _make_target(
        tmp_path,
        db_session,
        infra_files={
            "Dockerfile": (
                "FROM node:20\n"
                'HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1\n'
            ),
        },
    )

    # The gate reads step.validators + ctx.runner; build a tiny ctx/step pair that
    # routes the gate at the api_prefix validator against our violating target.
    @dataclass
    class _Step:
        agent_id: str = "app-infra-generator"
        validators: list = field(default_factory=lambda: ["api_prefix"])

    class _Ctx:
        def __init__(self, runner):
            self.runner = runner
            # The gate's _build_validation_target degrades to passing ctx through when
            # the runner has no deliverable_context factory — so the validator reads
            # our target's sandbox directly off ctx.runner. Mirror the DeliverableContext
            # surface onto ctx so the validator's getattr(target,'runner') chain works.
            self.deliverable = None
            self.scoped_store = None

    ctx = _Ctx(runner)
    outcome = await ValidationGate().evaluate(_Step(), ctx)

    warning_events = [e for e in outcome.events if e.get("type") == "validation_warning"]
    assert warning_events, (
        "the validation gate MUST emit a validation_warning on a residual P2 — this is "
        "the event that would break the byte-identical app_builder golden (INV-3)"
    )
