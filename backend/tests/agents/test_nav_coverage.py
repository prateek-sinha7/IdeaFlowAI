"""tests/agents/test_nav_coverage.py — nav-coverage + render seam + INV-3 guard.

quick-260701-bob: prove the hardened render_check + static_check catch the
runtime-navigation defects (dead/parameterized dynamic routes, wrong-section
activation, uncovered nav) that slipped through with Chromium PRESENT, that the
single render_coverage_status seam fails closed / records a distinct skip, AND
that none of it false-positives on the golden templates (INV-3).

Browser-dependent assertions skip gracefully when Chromium/Playwright is
unavailable (via ``_render_available``); the pure / static / seam tests run
offline unconditionally. Offline — no live LLM / Bedrock.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.gates.base import GATE_BLOCK
from agents.capabilities.registry import CapabilityRegistry
from agents.capabilities.validators.severity import (
    map_severity,
    render_coverage_status,
)
from app.agents.render_check import (
    NavResult,
    RenderResult,
    _coverage_finding,
    _extract_handler_routes,
    _first_path_segment,
    _nav_ok,
    render_check,
)
from app.agents.static_check import _href_target_id, static_check

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "imc-inventory-certificate-management.html"
).resolve()
# The FULL 414KB comprehensive regression fixture (ITEM 1 / FULL-FILE-REGRESSION).
# Kept ALONGSIDE the trimmed fixture (additive) — the trimmed one backs the fast unit
# tests; this one pins the FINAL measured counts after ITEM 3 (render un-dedup) +
# ITEM 4 (static router-dead).
_FULL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "imc-inventory-certificate-management-full.html"
).resolve()
# B — the FIXED-router regression fixture (quick-260701-go2 round 3): the same SPA with
# an alias/parametric routes ARRAY + a scoped ``.page-section[data-page]`` navigateTo.
# It MUST PASS both tiers (static ok=True 0 dead/0 router-dead; render ok=True 17/17).
# Committed ALONGSIDE the trimmed + full fixtures (additive).
_FIXED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "imc-inventory-certificate-management-fixed.html"
).resolve()

# ── FINAL measured counts on the full fixture (A). MEASURED under the round-3
# route-table-aware validators (quick-260701-go2) — these SUPERSEDE the round-2 pins
# (11/0/16/17/2): the object routes-table now RESOLVES A's routes, so the static dead
# links dedupe per unreachable target (11 → 5); render is unchanged (A's runtime is
# genuinely broken — navigateTo activates the sidebar <a>, not the <section>). Pinned as
# EXACT integers — a drift here is a real behavioral regression. ──
_FULL_STATIC_DEAD_LINKS = 5    # round-3: deduped unreachable targets — was 11 (round-2)
_FULL_STATIC_ROUTER_DEAD = 0   # router-dead: A's routes resolve, none section-less-in-map
_FULL_RENDER_SIDEBAR_DEAD = 16  # NavResults ok=False (router targets nav links, not
#                                 sections → sections never activate — a real defect)
_FULL_RENDER_NAV_TOTAL = 17     # total NavResults exercised (only dashboard is ok)
# Overlap between the static dead/router-dead TARGETS and the render dead TARGETS
# (first-path-segment). Measured value — asserted EXACTLY (not "disjoint").
_FULL_STATIC_RENDER_OVERLAP = 2  # {'certificates', 'inventory'} (round-3 measured)
_GOLDEN_DIR = (Path(__file__).parent / "characterization" / "golden").resolve()

# The pre-existing static_check issue the minimal golden stubs already emit BEFORE
# this change (they are trivial deliverable snapshots, not real prototypes). The
# INV-3 guard asserts NO issue BEYOND this baseline is introduced by the hardening.
_GOLDEN_PREEXISTING = {
    'no active page: expected one <section data-page> with class="is-active"'
}


# ════════════════════════════════════════════════════════════════════════════
# Registry save/restore (real html_render + render_coverage_status are used)
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_registry():
    registry_mod.discover()
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


# ── Browser-availability skip helper ────────────────────────────────────────


def _render_available(tmp_path: Path) -> bool:
    """True iff Chromium/Playwright can actually render (else the caller skips)."""
    probe = tmp_path / "_probe.html"
    probe.write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
    res = asyncio.run(render_check(probe.resolve()))
    return bool(getattr(res, "available", False))


# ── static/render result + target/runner stand-ins ──────────────────────────


class _FakeRunner:
    """Minimal runner handle: render_check + a capturing record_validation_result."""

    def __init__(self, render_result):
        self._render = render_result
        self.records: list[dict] = []

    async def render_check(self, path):
        return self._render

    def static_check(self, path):
        return SimpleNamespace(ok=True, issues=[], warnings=[])

    async def record_validation_result(
        self, step, validator, *, severity=None, attempt=0, issues=None
    ):
        self.records.append(
            {"step": step, "validator": validator, "severity": severity,
             "attempt": attempt, "issues": issues}
        )
        return f"vr-{len(self.records)}"


class _Target:
    def __init__(self, runner, *, require_render=None, step="prototype-build"):
        self.name = "prototype.html"
        self.runner = runner
        self.path = "/tmp/prototype.html"
        self.step = step
        self.task_meta = {"attempt": 1}
        self.require_render = require_render


# ════════════════════════════════════════════════════════════════════════════
# Scenario 1 — the fixture is flagged by BOTH tiers
# ════════════════════════════════════════════════════════════════════════════


def test_scenario1_static_flags_fixture_dynamic_nav_dead_link():
    """static_check (offline) flags the fixture's dynamic-nav dead link as an ERROR."""
    r = static_check(_FIXTURE)
    assert r.issues, "fixture must be flagged by static_check"
    assert any(
        "dead nav link" in i and "onclick/navigateTo" in i for i in r.issues
    ), r.issues
    # The parameterized #/inventory/{id} route (first segment 'inventory') is the
    # dead link — there is no <section data-page="inventory">.
    assert any("inventory" in i for i in r.issues)


def test_scenario1_render_flags_fixture(tmp_path):
    """render_check on the fixture is available=True, ok=False (dead parameterized nav)."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    rr = asyncio.run(render_check(_FIXTURE))
    assert rr.available is True
    assert rr.ok is False
    # A dead nav OR a coverage finding — here the parameterized route is a dead nav.
    dead = [n for n in rr.nav_results if not n.ok]
    assert dead or rr.coverage_errors, (rr.nav_results, rr.coverage_errors)
    # And the correct-section routes DID activate (proves discovery + activation work).
    assert any(n.ok and n.activated == n.expected for n in rr.nav_results)


# ════════════════════════════════════════════════════════════════════════════
# Scenario 2 — wrong-section-activation regression (pure _nav_ok, offline)
# ════════════════════════════════════════════════════════════════════════════


def test_scenario2_nav_ok_pure():
    assert _nav_ok("dashboard", "dashboard") is True       # correct activation
    assert _nav_ok("settings", "dashboard") is False       # wrong-section activation
    assert _nav_ok(None, "dashboard") is False             # nothing activated


# ════════════════════════════════════════════════════════════════════════════
# Scenario 3 — coverage=0 on a multi-section SPA (pure _coverage_finding, offline)
# ════════════════════════════════════════════════════════════════════════════


def test_scenario3_coverage_finding_pure():
    # >=2 sections AND 0 exercised → a finding.
    finding = _coverage_finding(3, 0)
    assert finding and "0" in finding
    # >=2 sections but some nav exercised → no finding.
    assert _coverage_finding(3, 2) is None
    # single section → never a finding (INV-3: goldens are single/no-section).
    assert _coverage_finding(1, 0) is None
    assert _coverage_finding(0, 0) is None


def test_scenario3_first_path_segment_and_handler_extract():
    """The shared first-path-segment + handler-route extraction back the coverage math."""
    assert _first_path_segment("#/inventory/4521") == "inventory"
    assert _first_path_segment("#/certificate-list?status=x") == "certificate-list"
    routes = _extract_handler_routes(
        "window.location.hash = '#/inventory-list'; navigateTo('#/reports')"
    )
    assert "#/inventory-list" in routes and "#/reports" in routes


def test_scenario3_coverage_finding_end_to_end(tmp_path):
    """A multi-section SPA with NO discoverable nav → a coverage finding (browser-gated)."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    html = (
        "<!doctype html><html><body>"
        "<section data-page='a' class='is-active'>A</section>"
        "<section data-page='b'>B</section>"
        "</body></html>"  # two sections, ZERO nav elements
    )
    p = tmp_path / "nonav.html"
    p.write_text(html, encoding="utf-8")
    rr = asyncio.run(render_check(p.resolve()))
    assert rr.available is True
    assert rr.coverage_errors, "coverage=0 on a 2-section SPA must be flagged"
    assert rr.ok is False


# ════════════════════════════════════════════════════════════════════════════
# Scenario 4 — render-unavailable + require_render=true fails CLOSED
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scenario4a_html_render_require_render_emits_one_p0():
    """html_render.validate (fake render available=False) + require_render=true → 1 P0."""
    runner = _FakeRunner(RenderResult(ok=True, available=False, note="Chromium unavailable"))
    target = _Target(runner, require_render=True)
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert len(issues) == 1
    assert issues[0].severity == "P0"
    assert "require_render" in issues[0].message
    # The skip was ALSO recorded as a distinct validator_skipped row (not swallowed).
    assert any(r["severity"] == "SKIPPED" for r in runner.records)


class _GateRunner:
    """A ctx.runner for the ValidationGate: builds the target + records gate/vr rows."""

    def __init__(self, render_result):
        self._render = render_result
        self.run_id = "run-gate"
        self.gate_events: list[dict] = []
        self.validation_records: list[dict] = []

    def deliverable_context(self, *, name, step="", content=None, task_meta=None,
                            require_render=None):
        return _Target(self, require_render=require_render, step=step)

    async def render_check(self, path):
        return self._render

    async def record_validation_result(self, step, validator, *, severity=None,
                                       attempt=0, issues=None):
        self.validation_records.append({"validator": validator, "severity": severity})
        return "vr-1"

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.gate_events.append({"gate": gate, "outcome": outcome})
        return "gate-1"


@pytest.mark.asyncio
async def test_scenario4b_require_render_drives_validation_gate_block():
    """The P0 drives the EXISTING ValidationGate.evaluate → GATE_BLOCK (no new outcome)."""
    runner = _GateRunner(RenderResult(ok=True, available=False, note="Chromium unavailable"))
    ctx = SimpleNamespace(runner=runner, deliverable=SimpleNamespace(name="prototype.html"))
    step = SimpleNamespace(
        agent_id="prototype-revision-agent",
        validators=["html_render"],
        gates=["validation"],
        require_render=True,
    )
    gate = CapabilityRegistry().resolve("gate", "validation")
    result = await gate.evaluate(step, ctx)
    assert result.outcome == GATE_BLOCK
    assert runner.gate_events[-1]["outcome"] == GATE_BLOCK


@pytest.mark.asyncio
async def test_scenario4c_fixloop_render_unavailable_no_fix_thread(tmp_path, monkeypatch):
    """_run_validation_fix_loop (clean static + render unavailable + require_render=true)
    does NOT re-invoke the sub-agent (create_runner never called)."""
    from agents.execution_engine import engine as engine_mod

    html_file = tmp_path / "prototype.html"
    html_file.write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")

    # Clean static, render unavailable (skip).
    monkeypatch.setattr(
        engine_mod, "static_check",
        lambda p: SimpleNamespace(ok=True, issues=[], summary=lambda: "OK"),
        raising=False,
    )

    async def _fake_render(p):
        return RenderResult(ok=True, available=False, note="Chromium unavailable")

    # engine._run_validation_fix_loop imports these names locally from the app modules.
    import app.agents.render_check as rc_mod
    import app.agents.static_check as sc_mod
    monkeypatch.setattr(rc_mod, "render_check", _fake_render, raising=True)
    monkeypatch.setattr(
        sc_mod, "static_check",
        lambda p: SimpleNamespace(ok=True, issues=[], summary=lambda: "OK"),
        raising=True,
    )

    called = {"create_runner": 0}

    def _boom_create_runner(*a, **k):
        called["create_runner"] += 1
        raise AssertionError("create_runner must NOT be called on a render skip")

    monkeypatch.setattr(engine_mod, "create_runner", _boom_create_runner, raising=True)

    sandbox = SimpleNamespace(path_for=lambda name: html_file)
    # self is unused on the non-failing path — a dummy suffices.
    await engine_mod.ExecutionEngine._run_validation_fix_loop(
        SimpleNamespace(),
        ctx=SimpleNamespace(),
        sandbox=sandbox,
        pipeline_run_id="run-1",
        task_num=1,
        total_tasks=1,
        cancel_event=None,
        filename="prototype.html",
        require_render=True,
    )
    assert called["create_runner"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Scenario 5 — render-unavailable + require_render=false passes BUT records a skip
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scenario5_require_render_false_passes_but_records_skip():
    """html_render.validate returns [] (pass) BUT a distinct validator_skipped row is
    recorded (severity=SKIPPED) — the skip is never swallowed."""
    runner = _FakeRunner(RenderResult(ok=True, available=False, note="Chromium unavailable"))
    target = _Target(runner, require_render=False)
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert issues == []
    skips = [r for r in runner.records if r["severity"] == "SKIPPED"]
    assert len(skips) == 1
    assert skips[0]["validator"] == "html_render"
    # The SKIPPED sentinel maps without raising (audit-row-only; gate never maps it).
    assert map_severity("SKIPPED") == "SKIPPED"


# ════════════════════════════════════════════════════════════════════════════
# Scenario 6 — static_check flags the fixture independently of any render
# ════════════════════════════════════════════════════════════════════════════


def test_scenario6_static_flags_fixture_independently():
    r = static_check(_FIXTURE)
    assert not r.ok
    assert any("dead nav link" in i for i in r.issues)


# ════════════════════════════════════════════════════════════════════════════
# Scenario 7 — producer guardrail: dead nav / page_errors are available=True FAILURES
# ════════════════════════════════════════════════════════════════════════════


def test_scenario7_producer_classification_failure_not_skip():
    """A RenderResult with available=True + a dead nav / page_errors is ok=False but
    available=True (a FAILURE, never a skip)."""
    dead = RenderResult(
        ok=False, available=True,
        nav_results=[NavResult(href="#/x", activated=None, ok=False, expected="x")],
    )
    assert dead.available is True and dead.ok is False
    assert render_coverage_status(dead, require_render=False) == "ok"  # ran → ok status

    perr = RenderResult(ok=False, available=True, page_errors=["boom"])
    assert perr.available is True and perr.ok is False
    # ONLY an unavailable render is a skip.
    skip = RenderResult(ok=True, available=False, note="Chromium unavailable")
    assert render_coverage_status(skip, require_render=False) == "skipped_allowed"
    assert render_coverage_status(skip, require_render=True) == "skipped_blocked"


# ════════════════════════════════════════════════════════════════════════════
# Scenario 8 — INV-3 false-positive guard on the 3 golden templates
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("name", ["prototype", "od_prototype", "prototype_revision"])
def test_scenario8_static_zero_new_issues_on_goldens(name):
    """static_check raises zero NEW issues on the golden templates (INV-3)."""
    g = static_check(_GOLDEN_DIR / f"{name}.html")
    new = set(g.issues) - _GOLDEN_PREEXISTING
    assert not new, f"{name}: NEW static issues introduced by the hardening: {new}"
    # The new dynamic-nav check never fires on the goldens (no onclick/navigateTo).
    assert not any("onclick/navigateTo" in i for i in g.issues)


@pytest.mark.parametrize("name", ["prototype", "od_prototype", "prototype_revision"])
def test_scenario8_render_zero_new_issues_on_goldens(name, tmp_path):
    """render_check raises no NEW issues on the goldens — the >=2-section coverage rule
    never trips on a single/no-section golden (browser-gated, INV-3)."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    rr = asyncio.run(render_check((_GOLDEN_DIR / f"{name}.html").resolve()))
    assert rr.available is True
    assert rr.ok is True, (rr.nav_results, rr.coverage_errors, rr.console_errors, rr.page_errors)
    assert not rr.coverage_errors
    assert not [n for n in rr.nav_results if not n.ok]


# ════════════════════════════════════════════════════════════════════════════
# Scenario 9 — ITEM 4: static_check router-dead cross-check (offline, guarded)
# ════════════════════════════════════════════════════════════════════════════

# A minimal SPA that HAS a routes map (dashboard only) + a <section data-page="reports">
# reachable by a nav route but with NO routes-map entry → a router-dead nav link.
_ROUTER_DEAD_HTML = (
    "<!doctype html><html><body>"
    "<a class='nav-item' href='#/dashboard'>D</a>"
    "<a class='nav-item' href='#/reports'>R</a>"
    "<section data-page='dashboard' class='is-active'>D</section>"
    "<section data-page='reports'>R</section>"
    "<script>const routes = { dashboard: '#/dashboard' };"
    "function go(){ location.hash = '#/dashboard'; }</script>"
    "</body></html>"
)

# The SAME markup with NO ``const routes={}`` map — the guard must skip the whole
# routes-map block, so NO router-dead (nor routes-map-missing) issue is emitted.
_ROUTER_DEAD_HTML_NO_MAP = (
    "<!doctype html><html><body>"
    "<a class='nav-item' href='#/dashboard'>D</a>"
    "<a class='nav-item' href='#/reports'>R</a>"
    "<section data-page='dashboard' class='is-active'>D</section>"
    "<section data-page='reports'>R</section>"
    "<script>function go(){ location.hash = '#/dashboard'; }</script>"
    "</body></html>"
)


def test_scenario9_router_dead_emitted_when_map_present():
    """A nav route target with a section but NO routes-map entry → router-dead issue."""
    r = static_check(_ROUTER_DEAD_HTML)
    router_dead = [i for i in r.issues if "router-dead nav link" in i]
    assert len(router_dead) == 1, r.issues
    assert "reports" in router_dead[0]
    # 'reports' HAS a section → it is NOT reported as a plain dead nav link.
    assert not any("dead nav link" in i and "router-dead" not in i and "reports" in i
                   for i in r.issues), r.issues


def test_scenario9_router_dead_deduped_per_target():
    """Multiple nav routes to the same map-less section → ONE router-dead issue."""
    html = (
        "<!doctype html><html><body>"
        "<a class='nav-item' href='#/reports'>R</a>"
        "<button onclick=\"location.hash='#/reports/2024'\">R2</button>"
        "<section data-page='dashboard' class='is-active'>D</section>"
        "<section data-page='reports'>R</section>"
        "<script>const routes = { dashboard: '#/dashboard' };</script>"
        "</body></html>"
    )
    r = static_check(html)
    router_dead = [i for i in r.issues if "router-dead nav link" in i]
    assert len(router_dead) == 1, r.issues
    assert "reports" in router_dead[0]


def test_scenario9_no_router_dead_without_map():
    """No ``const routes={}`` map → the routes-map block (incl. router-dead) is skipped."""
    r = static_check(_ROUTER_DEAD_HTML_NO_MAP)
    assert not any("router-dead" in i for i in r.issues), r.issues
    # and the map-completeness checks are ALSO skipped (guard proven).
    assert not any("routes map" in i for i in r.issues), r.issues


# ════════════════════════════════════════════════════════════════════════════
# Scenario 10 — ITEM 3: render_check un-dedup + ${…} exclusion + settle knob
# ════════════════════════════════════════════════════════════════════════════


def test_scenario10_render_check_exposes_settle_knob():
    """render_check accepts nav_settle_ms (default 50 == the prior hardcoded wait)."""
    import inspect

    from app.agents.render_check import _NAV_SETTLE_MS

    assert _NAV_SETTLE_MS == 50
    sig = inspect.signature(render_check)
    assert "nav_settle_ms" in sig.parameters
    assert sig.parameters["nav_settle_ms"].default == _NAV_SETTLE_MS


def test_scenario10_undedup_malformed_and_skip_template(tmp_path):
    """Two malformed same-first-segment routes → TWO ok=False NavResults (un-dedup);
    a ${id} route is NOT exercised but still counts as discovered (no false coverage-0)."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    html = (
        "<!doctype html><html><body>"
        "<section data-page='home' class='is-active'>H</section>"
        "<section data-page='about'>A</section>"
        "<button onclick=\"location.hash='#/x/1'\">x1</button>"
        "<button onclick=\"location.hash='#/x/2'\">x2</button>"
        "<button onclick=\"location.hash='#/y/${id}'\">y</button>"
        "<script>"
        "window.addEventListener('hashchange',()=>{"
        "document.querySelectorAll('[data-page]').forEach(s=>s.classList.remove('is-active'));"
        "const id=(location.hash.split('/')[1]||'');"
        "const el=document.querySelector('[data-page=\\''+id+'\\']');"
        "if(el)el.classList.add('is-active');});"
        "</script>"
        "</body></html>"
    )
    p = tmp_path / "undedup.html"
    p.write_text(html, encoding="utf-8")
    rr = asyncio.run(render_check(p.resolve()))
    assert rr.available is True
    # Both #/x/1 and #/x/2 are kept as their OWN dead NavResults (un-dedup).
    x_dead = [n for n in rr.nav_results if n.expected == "x" and not n.ok]
    assert len(x_dead) == 2, rr.nav_results
    hrefs = {n.href for n in x_dead}
    assert hrefs == {"#/x/1", "#/x/2"}, hrefs
    # The ${id} template route is NEVER exercised (no NavResult for it).
    assert not any("${" in n.href for n in rr.nav_results), rr.nav_results
    # …but it was DISCOVERED → coverage is not falsely zero (nav was found).
    assert not rr.coverage_errors, rr.coverage_errors


def test_scenario10_only_template_route_no_false_coverage_zero(tmp_path):
    """A multi-section SPA whose ONLY nav is a ${…} route → discovered>0, no coverage-0."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    html = (
        "<!doctype html><html><body>"
        "<section data-page='home' class='is-active'>H</section>"
        "<section data-page='about'>A</section>"
        "<button onclick=\"location.hash='#/detail/${id}'\">d</button>"
        "</body></html>"
    )
    p = tmp_path / "only_template.html"
    p.write_text(html, encoding="utf-8")
    rr = asyncio.run(render_check(p.resolve()))
    assert rr.available is True
    # The only nav is a template literal → not exercised, but discovered → NO coverage-0.
    assert not rr.coverage_errors, rr.coverage_errors
    assert rr.nav_results == [], rr.nav_results


# ════════════════════════════════════════════════════════════════════════════
# Scenario 11 — ITEM 2: require_render:true threads through the compiler (manifest)
# ════════════════════════════════════════════════════════════════════════════


def test_scenario11_require_render_true_compiles_on_build_and_revision():
    """The manifest flip threads through the REAL compiler → Step.require_render is True
    on the prototype-build step AND the prototype-revision-agent step."""
    from agents.execution_engine.engine import compile_for_run

    built = compile_for_run("prototype")
    build_step = next(s for s in built.steps if s.agent_id == "prototype-build")
    assert build_step.require_render is True, "prototype-build must require_render=True"

    rev = compile_for_run("prototype_revision")
    rev_step = next(s for s in rev.steps if s.agent_id == "prototype-revision-agent")
    assert rev_step.require_render is True, "revision step must require_render=True"


# ════════════════════════════════════════════════════════════════════════════
# Scenario 12 — ITEM 1: the full 414KB fixture — pinned FINAL counts + overlap
# ════════════════════════════════════════════════════════════════════════════


def _static_dead_and_router_dead_targets(result) -> set[str]:
    """The first-path-segment TARGETS of the static dead-link + router-dead issues."""
    targets: set[str] = set()
    for issue in result.issues:
        if issue.startswith("dead nav link"):
            m = re.search(r"route '([^']+)'", issue) or re.search(r"href '([^']+)'", issue)
            if m:
                targets.add(_href_target_id(m.group(1)))
        elif issue.startswith("router-dead"):
            m = re.search(r"target '([^']+)'", issue)
            if m:
                targets.add(m.group(1))
    return targets


def test_scenario12_full_fixture_is_committed():
    """The full 414KB regression fixture is committed alongside the trimmed one."""
    assert _FULL_FIXTURE.is_file(), f"full fixture missing: {_FULL_FIXTURE}"
    assert _FIXTURE.is_file(), "the trimmed fixture must be KEPT (additive)"
    assert _FULL_FIXTURE.stat().st_size > 400_000, "full fixture should be the ~414KB file"


def test_scenario12_static_final_counts_pinned():
    """static_check on the full fixture pins the FINAL dead-link + router-dead counts."""
    r = static_check(_FULL_FIXTURE)
    dead = [i for i in r.issues if i.startswith("dead nav link")]
    router_dead = [i for i in r.issues if i.startswith("router-dead")]
    assert len(dead) == _FULL_STATIC_DEAD_LINKS, dead
    assert len(router_dead) == _FULL_STATIC_ROUTER_DEAD, router_dead


def test_scenario12_render_final_counts_pinned(tmp_path):
    """render_check on the full fixture pins the FINAL sidebar-dead count + total
    (browser-gated). The router targets nav links (not sections), so sections never
    activate — a real navigation defect the un-dedup surfaces route-by-route."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    rr = asyncio.run(render_check(_FULL_FIXTURE))
    assert rr.available is True
    dead = [n for n in rr.nav_results if not n.ok]
    assert len(rr.nav_results) == _FULL_RENDER_NAV_TOTAL, rr.nav_results
    assert len(dead) == _FULL_RENDER_SIDEBAR_DEAD, dead
    # No false coverage-0 (nav WAS discovered/exercised).
    assert not rr.coverage_errors, rr.coverage_errors


def test_scenario12_static_render_overlap_pinned(tmp_path):
    """The overlap between static dead/router-dead TARGETS and render dead TARGETS is
    pinned to its MEASURED exact value (browser-gated) — NOT asserted 'disjoint'."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    r = static_check(_FULL_FIXTURE)
    static_targets = _static_dead_and_router_dead_targets(r)
    rr = asyncio.run(render_check(_FULL_FIXTURE))
    render_targets = {n.expected for n in rr.nav_results if not n.ok}
    overlap = static_targets & render_targets
    assert len(overlap) == _FULL_STATIC_RENDER_OVERLAP, (
        f"overlap drift: {sorted(overlap)} (static={sorted(static_targets)}, "
        f"render={sorted(render_targets)})"
    )


@pytest.mark.asyncio
async def test_scenario12_full_fixture_fail_closed_offline():
    """Offline fail-closed: a FAKE render (available=False) + require_render=true →
    html_render.validate returns EXACTLY one P0 (static can never silently substitute
    for an absent browser). Reuses the _FakeRunner/_Target stand-ins."""
    runner = _FakeRunner(
        RenderResult(ok=True, available=False, note="Chromium unavailable")
    )
    target = _Target(runner, require_render=True)
    hr = CapabilityRegistry().resolve("validator", "html_render")
    issues = await hr.validate(target)
    assert len(issues) == 1, issues
    assert issues[0].severity == "P0"
    assert "require_render" in issues[0].message
    # The skip was ALSO recorded as a distinct validator_skipped row (never swallowed).
    assert any(rec["severity"] == "SKIPPED" for rec in runner.records)


# ════════════════════════════════════════════════════════════════════════════
# Scenario 13 — quick-260701-go2 (round 3): route-table-aware A=fail / B=pass
# ════════════════════════════════════════════════════════════════════════════
#
# B (the FIXED fixture) has an alias/parametric routes ARRAY + a scoped navigateTo:
# it MUST PASS both tiers. A (the full fixture) has an object routes table but a
# genuinely broken runtime: static now RESOLVES its routes (dead links dedupe per
# unreachable target), yet A MUST FAIL via render. This is the tier division: static
# proves the table is structurally sound; render proves the runtime actually works.


def test_scenario13_fixed_fixture_is_committed():
    """The FIXED (B) regression fixture is committed alongside the trimmed + full ones."""
    assert _FIXED_FIXTURE.is_file(), f"fixed fixture missing: {_FIXED_FIXTURE}"
    assert _FIXED_FIXTURE.stat().st_size > 400_000, "fixed fixture should be the ~417KB file"


def test_scenario13_B_passes_static():
    """B passes tier 1 (static): ok=True, ZERO dead-link + ZERO router-dead (offline)."""
    r = static_check(_FIXED_FIXTURE)
    assert r.ok is True, r.issues
    assert [i for i in r.issues if i.startswith("dead nav link")] == [], r.issues
    assert [i for i in r.issues if i.startswith("router-dead")] == [], r.issues


def test_scenario13_B_passes_render(tmp_path):
    """B passes tier 2 (render): available=True, ok=True, every discovered route
    activates its correct RESOLVED section (alias/:id included) — browser-gated."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    rr = asyncio.run(render_check(_FIXED_FIXTURE))
    assert rr.available is True
    assert rr.ok is True, (rr.nav_results, rr.coverage_errors, rr.console_errors, rr.page_errors)
    assert [n for n in rr.nav_results if not n.ok] == [], rr.nav_results
    assert not rr.coverage_errors, rr.coverage_errors
    # Spot-check: at least one alias/:id route (an href with a '/') resolved to a
    # hyphenated detail/list page id AND activated exactly that section.
    resolved = [
        n
        for n in rr.nav_results
        if "/" in n.href.lstrip("#/")
        and n.ok
        and n.expected
        and "-" in n.expected
        and n.activated == n.expected
    ]
    assert resolved, [(n.href, n.activated, n.expected) for n in rr.nav_results]


def test_scenario13_A_fails_via_render(tmp_path):
    """A fails via render (the tier-division point): the routes table resolves, but the
    runtime activates the sidebar <a> not the <section> → ok=False — browser-gated."""
    if not _render_available(tmp_path):
        pytest.skip("Chromium/Playwright unavailable — browser-gated")
    rr = asyncio.run(render_check(_FULL_FIXTURE))
    assert rr.available is True
    assert rr.ok is False
    assert len([n for n in rr.nav_results if not n.ok]) >= 1, rr.nav_results
