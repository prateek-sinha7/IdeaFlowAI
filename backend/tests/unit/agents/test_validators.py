"""tests/agents/test_validators.py — the Validator registry + generic fix-loop (08-04).

08-04 stands up the ``Validator`` registry backbone (D-04/D-05/D-06):

  * ``html_static`` / ``html_render`` registered ``Validator``s wrapping
    ``static_check`` / ``render_check`` app-side, reached via the KernelServices
    handle (``target.runner.static_check`` — no kernel→app import);
  * the generic ``FixPolicy`` fix-loop (deliverable name + max_attempts + fix-prompt
    template, NOT hardcoded ``prototype.html``);
  * the Tier#4/5/6 validators resolve (``spec_plan_coverage`` / ``task_done_when`` /
    ``design_quality``);
  * every validator maps severity through the SINGLE imported ``map_severity``
    (08-01, VALID-03 single source);
  * the ``task_loop`` re-point routes declared validators through the handle,
    event-free.

The eight tests that PERSIST a ``validation_results`` row through a real ``ScopedStore``
moved to ``tests/integration/agents/test_validators_db.py`` in Batch 6.

Offline — no live LLM / Bedrock / Chromium, and no database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry
from tests.fakes.validation_stubs import _RenderResult, _StaticResult, _Target


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


# The static/render result stand-ins, the deliverable target and the recording runner
# are shared with tests/integration/agents/test_validators_db.py — see
# tests/fakes/validation_stubs.py.


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


# ════════════════════════════════════════════════════════════════════════════
# 2. Both validators take their severity decision from the SINGLE severity module
#    (no second definition anywhere) — VALID-03
# ════════════════════════════════════════════════════════════════════════════


def test_validators_take_severity_from_the_single_severity_module():
    """Each validator's severity function IS the canonical object, not a copy.

    The two validators reach the same module by DIFFERENT names, and that is correct:
    ``html_static`` maps an issue severity with ``map_severity``, while ``html_render``
    decides through the ``render_coverage_status`` seam introduced by
    `242a1e38` ("single render_coverage_status seam + require_render knob + skip
    audit", 2026-07-01); `c7ace9a8` (2026-08-26) then dropped the by-then-unused
    ``map_severity`` import from ``html_render``.

    This test asserted ``hr_mod.map_severity`` until Batch 6 and had therefore been
    red since 2026-08-26. The invariant it exists to protect is unchanged — no module
    may define its own severity mapping — so it now asserts that invariant against the
    real seam, and additionally that neither module re-defines either function.
    """
    import agents.capabilities.validators.severity as sev_mod
    import app.agents.validators.html_render as hr_mod
    import app.agents.validators.html_static as hs_mod

    assert hs_mod.map_severity is sev_mod.map_severity
    assert hr_mod.render_coverage_status is sev_mod.render_coverage_status

    # Neither validator carries a local definition (a copy would shadow the import).
    for mod in (hs_mod, hr_mod):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "def map_severity" not in src, f"{mod.__name__} redefines map_severity"
        assert (
            "def render_coverage_status" not in src
        ), f"{mod.__name__} redefines render_coverage_status"


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

    def __init__(self) -> None:
        # ExecutionContext.pending_validation_fix (Req 14 AC 4) — per-instance, so
        # the fix loop's seed/drain on one test can never leak into another.
        self.pending_validation_fix: dict = {}


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
    assert call["filename"] == "app.py"  # config-driven, NOT prototype.html
    assert call["max_attempts"] == 3


@pytest.mark.asyncio
async def test_fixloop_filename_backcompat_wraps_default_policy():
    """A bare filename= caller is wrapped into a default FixPolicy (byte-identical)."""
    engine = _FakeEngine()
    kernel = _make_kernel(engine)
    await kernel.run_validation_fix_loop(
        _FakeStep(),
        task_num=1,
        total_tasks=1,
        filename="prototype.html",
    )
    call = engine.calls[0]
    assert call["filename"] == "prototype.html"
    assert call["max_attempts"] == 2  # the Phase-7 default bound


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
        return _Target(
            name=name, runner=self, step=step, task_meta=dict(task_meta or {})
        )

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
    assert policy.max_attempts == 2  # no declared step.fix → Phase-7 default

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
