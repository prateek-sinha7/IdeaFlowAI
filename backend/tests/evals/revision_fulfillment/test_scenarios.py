"""Phase-2 scenario evals — S1/S2/S3 (R-13/R-14/R-15, design.md D-05).

End-to-end OFFLINE drives of the real ``prototype_revision`` pipeline
(``ExecutionEngine.execute()`` via the ``_drive`` harness) with per-scenario
scripted revision-agent behavior injected at the ``_scripts_for`` seam.

S1/S2 assert the DESIRED behavior (the delivered ``prototype.html``
satisfies the user's instruction) and are ``xfail(strict=True)`` until the
Phase-3 instruction-fulfillment fix lands — they are the mechanical
reproduction of the defect. Their scripts already carry a SECOND-invocation
"fix" turn, so the moment a fulfillment retry re-invokes the revision agent,
the scripted fix applies and the assertions pass (→ strict xpass errors →
markers must be removed in the fix diff).

S3 is the control: genuinely satisfied on the first pass, exactly one
revision-agent invocation, clean completion — must stay green before AND
after the fix.

0 tokens: scripted models only.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path

import pytest

from tests.evals.conftest import FIXTURES_DIR

pytestmark = pytest.mark.eval

XFAIL_REASON = (
    "FINDINGS A2/A7 — no instruction-fulfillment check; see "
    ".investigations/revision-pipeline-thinking-issue (Phase 3 removes this marker)"
)

MINI_HTML = (FIXTURES_DIR / "mini_prototype.html").read_text(encoding="utf-8").strip()


def _framed(instruction: str) -> str:
    return (
        "=== REVISION REQUEST ===\n"
        f"{instruction}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{MINI_HTML}\n"
        "=== END EXISTING HTML ==="
    )


# ── Edit anchors (each asserted present in the fixture — self-validating) ────

S1_NOOP_OLD = "intentionally has NO handler"
S1_NOOP_NEW = "deliberately lacks a handler"
S1_FIX_BTN_OLD = '<button type="button" id="save-btn">Save</button>'
S1_FIX_BTN_NEW = '<button type="button" id="save-btn" onclick="saveSettings()">Save</button>'
S1_FIX_FN_OLD = "window.addEventListener('load', route);"
S1_FIX_FN_NEW = (
    "window.addEventListener('load', route);\n"
    "  function saveSettings() { document.title = 'saved'; }"
)

S2_SECTION_OLD = '<section id="settings" data-page="settings">'
S2_SECTION_NEW = (
    '<section id="reports" data-page="reports"><h2>Reports</h2>'
    "<table><tr><th>Report</th><th>Rows</th></tr>"
    "<tr><td>Weekly usage</td><td>12</td></tr></table></section>\n    "
    '<section id="settings" data-page="settings">'
)
S2_ROUTES_OLD = "const routes = { dashboard: '#/dashboard', settings: '#/settings' };"
S2_ROUTES_NEW = (
    "const routes = { dashboard: '#/dashboard', settings: '#/settings', "
    "reports: '#/reports' };"
)
S2_FIX_NAV_OLD = '<a class="nav-item" href="#/settings">Settings</a>'
S2_FIX_NAV_NEW = (
    '<a class="nav-item" href="#/settings">Settings</a>\n    '
    '<a class="nav-item" href="#/reports">Reports</a>'
)
S2_NAV_LINK = '<a class="nav-item" href="#/reports">Reports</a>'

S3_TITLE_OLD = '<div class="topbar"><h1>Acme Admin</h1></div>'
S3_TITLE_NEW = '<div class="topbar"><h1>Acme Console</h1></div>'


def test_anchors_exist_in_fixture() -> None:
    """Self-check: every scripted old_string is present (and unique enough)."""
    for anchor in (
        S1_NOOP_OLD, S1_FIX_BTN_OLD, S1_FIX_FN_OLD,
        S2_SECTION_OLD, S2_ROUTES_OLD, S2_FIX_NAV_OLD, S3_TITLE_OLD,
    ):
        assert MINI_HTML.count(anchor) == 1, f"anchor not unique in fixture: {anchor!r}"


# ── Scripted-agent script builders (D-05: mechanics as code) ─────────────────


def _edit(old: str, new: str, call_id: str):
    return (
        "edit_file",
        json.dumps({"file_path": "prototype.html", "old_string": old, "new_string": new}),
        call_id,
    )


def _revision_scripts(scenario_id: str, invocation: int):
    """Return the revision agent's script for its Nth invocation (1-based).

    Invocation 1 is the scenario's defining behavior; invocation 2+ is the
    scripted FIX the fulfillment retry (Phase 3) will trigger — pre-fix it is
    simply never consumed.
    """
    from tests.agents._scripted_model import _ScriptedTurn

    first = invocation == 1
    if scenario_id == "S1":
        if first:  # clean no-op: edits an unrelated comment
            return [
                _ScriptedTurn(
                    texts=["Revising. "],
                    tool_calls=[_edit(S1_NOOP_OLD, S1_NOOP_NEW, "s1_noop")],
                    usage=(30, 15),
                ),
                _ScriptedTurn(texts=["Revision complete."], usage=(8, 4)),
            ]
        # ONE tool call per turn: multiple edit_file calls in a single turn can
        # execute as a concurrent read-modify-write race (last write wins) and
        # nondeterministically drop an edit — sequential turns are deterministic.
        return [  # the real fix, applied only if a retry ever fires
            _ScriptedTurn(
                texts=["Wiring the Save button. "],
                tool_calls=[_edit(S1_FIX_BTN_OLD, S1_FIX_BTN_NEW, "s1_fix_btn")],
                usage=(30, 15),
            ),
            _ScriptedTurn(
                texts=["Adding the handler. "],
                tool_calls=[_edit(S1_FIX_FN_OLD, S1_FIX_FN_NEW, "s1_fix_fn")],
                usage=(20, 10),
            ),
            _ScriptedTurn(texts=["Save button wired."], usage=(8, 4)),
        ]
    if scenario_id == "S2":
        if first:  # partial: section + route, NO sidebar link
            # One tool call per turn (see S1 note — avoids the concurrent-edit race).
            return [
                _ScriptedTurn(
                    texts=["Adding Reports page. "],
                    tool_calls=[_edit(S2_SECTION_OLD, S2_SECTION_NEW, "s2_section")],
                    usage=(30, 15),
                ),
                _ScriptedTurn(
                    texts=["Registering the route. "],
                    tool_calls=[_edit(S2_ROUTES_OLD, S2_ROUTES_NEW, "s2_routes")],
                    usage=(20, 10),
                ),
                _ScriptedTurn(texts=["Reports page added."], usage=(8, 4)),
            ]
        return [
            _ScriptedTurn(
                texts=["Adding the sidebar link. "],
                tool_calls=[_edit(S2_FIX_NAV_OLD, S2_FIX_NAV_NEW, "s2_fix_nav")],
                usage=(30, 15),
            ),
            _ScriptedTurn(texts=["Sidebar link added."], usage=(8, 4)),
        ]
    if scenario_id == "S3":  # genuinely does what was asked, every time
        return [
            _ScriptedTurn(
                texts=["Renaming the topbar. "],
                tool_calls=[_edit(S3_TITLE_OLD, S3_TITLE_NEW, "s3_title")],
                usage=(30, 15),
            ),
            _ScriptedTurn(texts=["Topbar renamed."], usage=(8, 4)),
        ]
    raise ValueError(f"unknown scenario {scenario_id}")


# ── Driver ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fresh_checkpointer(monkeypatch):
    """Reset the process-wide checkpointer singleton before each scenario, and
    force the InMemorySaver regardless of the machine's DATABASE_URL.

    ``app/agents/checkpointer.py`` caches the checkpointer module-globally; its
    internal ``asyncio.Lock`` binds to the event loop of the FIRST run, so the
    second ``_drive`` in one pytest process dies with "bound to a different
    event loop" → every agent errors "The model rejected this request." (This
    same leak is the likely cause of the pre-existing second-``_drive``
    failures in the characterization/phase-5 suites on this branch — see
    STATUS.md.) Deliberately no restore of the singleton: leaving the fresh
    instance matches the single-run state every other harness user sees.

    The DATABASE_URL patch keeps the suite hermetic (D-03): with a Postgres
    URL configured but the server down, the psycopg pool retries localhost:5432
    for ~90s and the scenario fails on an environmental condition, not the
    behavior under test. Scenario evals never need cross-restart resume, so
    the in-memory saver is always correct here.
    """
    import app.agents.checkpointer as cp
    from app.core.config import settings

    cp._checkpointer = None
    cp._pool = None
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///eval-hermetic.db")


async def _run_scenario(monkeypatch, scenarios, scenario_id: str):
    """Drive prototype_revision end-to-end with this scenario's scripts.

    Returns (events, final_html, invocation_counts).
    """
    import tests.agents._scripted_model as sm
    import app.agents.render_check as render_mod
    from app.agents.render_check import RenderResult

    # Determinism (D-03): pin render_check to a clean deterministic result.
    # Real Chromium is timing-flaky (an occasional spurious dead-nav line fires
    # the structural fix loop, consumes the scripted retry turn, and flips
    # S1/S2 to xpass) — and render behavior is NOT what these scenarios
    # assert. static_check still runs for real.
    async def _clean_render(path):
        return RenderResult(ok=True, available=True)

    monkeypatch.setattr(render_mod, "render_check", _clean_render)

    scenario = scenarios[scenario_id]
    counts: dict[str, int] = defaultdict(int)
    orig_scripts_for = sm._scripts_for

    def _patched(agent_id: str):
        counts[agent_id] += 1
        if agent_id == "prototype-revision-agent":
            return _revision_scripts(scenario_id, counts[agent_id])
        return orig_scripts_for(agent_id)

    monkeypatch.setattr(sm, "_scripts_for", _patched)

    run_id = f"eval-{scenario_id.lower()}-{uuid.uuid4().hex[:8]}"
    try:
        events = await sm._drive(
            "prototype_revision",
            user_message=_framed(scenario["instruction"]),
            pipeline_run_id=run_id,
        )
    finally:
        # Close the checkpointer WHILE this test's event loop is still alive.
        # When the env has Postgres configured, get_checkpointer() builds a real
        # psycopg AsyncConnectionPool whose worker tasks belong to THIS loop —
        # abandoning it (the _fresh_checkpointer reset alone) leaves them to die
        # noisily at loop close ("Task was destroyed but it is pending!" /
        # "Event loop is closed" teardown spam). Best-effort: never fail a test
        # over cleanup.
        import app.agents.checkpointer as cp

        try:
            await cp.close_checkpointer()
        except Exception:  # noqa: BLE001 — cleanup must never mask the test result
            cp._checkpointer = None
            cp._pool = None
    final = Path(sm._RUNS_ROOT) / "harness-user" / run_id / "prototype.html"
    assert final.is_file(), "run produced no prototype.html deliverable"
    return events, final.read_text(encoding="utf-8"), counts


def _assert_clean_completion(events: list[dict]) -> None:
    types = [e.get("type") for e in events]
    assert "pipeline_complete" in types
    assert "pipeline_failed" not in types
    assert "error" not in types


# ── S3 control (T-016) — green today, green after the fix ────────────────────


@pytest.mark.asyncio
async def test_s3_control_satisfied_first_pass(monkeypatch, scenarios) -> None:
    events, final_html, counts = await _run_scenario(monkeypatch, scenarios, "S3")

    _assert_clean_completion(events)
    assert S3_TITLE_NEW in final_html                      # the edit landed
    assert "Acme Admin</h1>" not in final_html
    # No retry: the revision agent ran exactly once (cost guard, R-15).
    assert counts["prototype-revision-agent"] == 1


# ── S1/S2 defect evals (T-017) — DESIRED behavior, xfail until Phase 3 ───────


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=XFAIL_REASON)
async def test_s1_noop_edit_is_caught_and_fixed(monkeypatch, scenarios) -> None:
    """A structurally clean no-op edit must NOT be delivered as success:
    the pipeline should detect the unmet instruction, retry, and deliver a
    Save button that is actually wired."""
    events, final_html, counts = await _run_scenario(monkeypatch, scenarios, "S1")

    _assert_clean_completion(events)
    assert 'onclick="saveSettings()"' in final_html
    assert counts["prototype-revision-agent"] >= 2         # a retry fired


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=XFAIL_REASON)
async def test_s2_partial_fix_is_caught_and_completed(monkeypatch, scenarios) -> None:
    """'Reachable from the sidebar' means a nav link, not just a section +
    route. The fulfillment check must flag the missing half."""
    events, final_html, counts = await _run_scenario(monkeypatch, scenarios, "S2")

    _assert_clean_completion(events)
    assert S2_NAV_LINK in final_html
    assert counts["prototype-revision-agent"] >= 2


# ── T-015 note (D-05): prove today's validators genuinely MISS S1/S2 ─────────


def _apply(html: str, *edits: tuple[str, str]) -> str:
    for old, new in edits:
        assert old in html
        html = html.replace(old, new, 1)
    return html


def test_s1_noop_html_passes_static_check_today() -> None:
    """The S1 post-edit file is statically CLEAN — documents that the existing
    validator lane cannot see the defect (companion to L5's root-cause test)."""
    from app.agents.static_check import static_check

    edited = _apply(MINI_HTML, (S1_NOOP_OLD, S1_NOOP_NEW))
    res = _static_on(edited)
    assert res.ok, f"expected clean, got: {res.issues}"


def test_s2_partial_html_passes_static_check_today() -> None:
    """S2's half-done edit (section + route, no nav link) raises NO static
    error — 'section with no nav entry' is an advisory warning by design, so
    nothing in the current pipeline can fail on it."""
    edited = _apply(MINI_HTML, (S2_SECTION_OLD, S2_SECTION_NEW), (S2_ROUTES_OLD, S2_ROUTES_NEW))
    res = _static_on(edited)
    assert res.ok, f"expected clean, got: {res.issues}"


def _static_on(html: str):
    import tempfile
    from pathlib import Path as _P

    from app.agents.static_check import static_check

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        path = _P(f.name)
    try:
        return static_check(path)
    finally:
        path.unlink(missing_ok=True)
