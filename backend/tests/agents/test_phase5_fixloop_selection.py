"""Phase-5 (task T1) verify gate — UNIT tests for the PURE fix-loop issue
selection helpers extracted from ``_run_validation_fix_loop``.

Task T1 generalized ``ExecutionEngine._run_validation_fix_loop`` so the SAME
bounded internal fix-loop serves both the prototype BUILD path (Phase 4) and the
prototype REVISION path (Phase 5, task T2). The selection of *which* validation
issues to feed back to the fixing sub-agent was factored into three module-level,
pure, side-effect-free helpers so T2's code AND these tests use the *same*
normalization:

  * ``_static_issue_sigs(sres)``  — set of a StaticCheckResult's issue signatures
  * ``_console_sigs(rres)``       — set of a RenderResult's console-error signatures
  * ``_select_issues_to_fix(sres, rres, baseline_static, baseline_console)``
        — the ordered, de-duplicated fix-list, applying the locked Phase-5 policy.

The locked Phase-5 selection policy these tests pin:
  * Static REGRESSIONS — static issues NOT in ``baseline_static`` (empty/None
    baseline ⇒ ALL static issues, i.e. today's BUILD behavior = fix-all).
  * Hard render-breakage, ALWAYS included regardless of baseline — uncaught page
    errors and dead nav links. A dead nav is worded by its ACTUAL failure class
    (round-4 null-honesty): ``activated is None`` ⇒ a BLANK page (activated NOTHING,
    never coerced to a nav-link name); a real-but-wrong ``activated`` ⇒ a mis-routed
    nav ("activated 'x' but expected 'y'").
  * Console errors NOT in ``baseline_console`` (empty/None ⇒ all, = today).
  * Render contributes ONLY when ``rres.available`` (a skipped render — Chromium
    absent — never adds issues).

These are PURE unit tests: no agent, no engine, no network, no sandbox, no
Chromium. They construct the REAL ``StaticCheckResult`` / ``RenderResult`` /
``NavResult`` dataclasses (they are plain, dependency-light dataclasses) and feed
them straight to the helper — so a regression in the selection policy is caught
in milliseconds, independently of the (heavier) Phase-4 ``_run_build_task_loop``
integration test.
"""

from __future__ import annotations

from agents.execution_engine.engine import (
    _console_sigs,
    _select_issues_to_fix,
    _static_issue_sigs,
)
from app.agents.render_check import NavResult, RenderResult
from app.agents.static_check import StaticCheckResult

# --------------------------------------------------------------------------- #
# Tiny builders for the real result dataclasses.
# --------------------------------------------------------------------------- #


def _static(issues: list[str]) -> StaticCheckResult:
    return StaticCheckResult(ok=not issues, issues=list(issues))


def _render(
    *,
    available: bool = True,
    console_errors: list[str] | None = None,
    page_errors: list[str] | None = None,
    nav: list[NavResult] | None = None,
) -> RenderResult:
    console_errors = console_errors or []
    page_errors = page_errors or []
    nav = nav or []
    ok = not console_errors and not page_errors and all(n.ok for n in nav)
    return RenderResult(
        ok=ok,
        available=available,
        console_errors=console_errors,
        page_errors=page_errors,
        nav_results=nav,
    )


def _dead_nav(href: str) -> NavResult:
    return NavResult(href=href, activated=None, ok=False)


def _live_nav(href: str, page: str) -> NavResult:
    return NavResult(href=href, activated=page, ok=True)


def _wrong_nav(href: str, activated: str, expected: str) -> NavResult:
    # A route that activated a real-but-WRONG section (mis-routed, not blank).
    return NavResult(href=href, activated=activated, ok=False, expected=expected)


# --------------------------------------------------------------------------- #
# Signature helpers (the normalization T2 imports).
# --------------------------------------------------------------------------- #


class TestSignatureHelpers:
    def test_static_issue_sigs_are_the_issue_strings(self):
        sres = _static(["dead nav link: '#/x'", "routes map missing 'y'"])
        assert _static_issue_sigs(sres) == {
            "dead nav link: '#/x'",
            "routes map missing 'y'",
        }

    def test_static_issue_sigs_empty_when_ok(self):
        assert _static_issue_sigs(_static([])) == set()

    def test_console_sigs_are_the_console_messages_when_available(self):
        rres = _render(console_errors=["TypeError: x is undefined", "404 /a.js"])
        assert _console_sigs(rres) == {"TypeError: x is undefined", "404 /a.js"}

    def test_console_sigs_empty_when_render_unavailable(self):
        # A skipped render exposes no console signatures — its errors must never
        # seed a baseline (else a later available render would look "clean").
        rres = _render(available=False, console_errors=["should be ignored"])
        assert _console_sigs(rres) == set()


# --------------------------------------------------------------------------- #
# BUILD mode (baseline_static=None, baseline_console=None) — parity with today.
# --------------------------------------------------------------------------- #


class TestBuildModeParity:
    def test_selects_all_static_plus_render_break_plus_all_console(self):
        sres = _static(["static issue A", "static issue B"])
        rres = _render(
            console_errors=["console boom"],
            page_errors=["ReferenceError: foo"],
            nav=[_dead_nav("#/orders"), _live_nav("#/home", "home")],
        )
        selected = _select_issues_to_fix(sres, rres, None, None)

        # Every static issue + every console error + page error + dead nav.
        assert "static issue A" in selected
        assert "static issue B" in selected
        assert "console error: console boom" in selected
        assert "uncaught exception: ReferenceError: foo" in selected
        assert (
            "dead nav link: '#/orders' activated NOTHING (no <section data-page> "
            "became active — blank page)"
            in selected
        )
        # The live nav must NOT appear.
        assert all("#/home" not in line for line in selected)

    def test_build_order_pins_canonical_honest_wording_and_order(self):
        # Pin the EXACT ordering + the honest dead-nav wording (round-4): static
        # issues, then console errors, then uncaught exceptions, then dead nav
        # links. The dead-nav line names its ACTUAL failure class — a null
        # ``activated`` is a BLANK page (activated NOTHING), never coerced to a name.
        sres = _static(["S1", "S2"])
        rres = _render(
            console_errors=["C1"],
            page_errors=["P1"],
            nav=[_dead_nav("#/n1")],
        )
        selected = _select_issues_to_fix(sres, rres, None, None)
        assert selected == [
            "S1",
            "S2",
            "console error: C1",
            "uncaught exception: P1",
            "dead nav link: '#/n1' activated NOTHING (no <section data-page> "
            "became active — blank page)",
        ]

    def test_dead_nav_wrong_section_names_actual_and_expected(self):
        # Round-4 honesty: a dead nav that activated a REAL-but-WRONG section is
        # worded as a mis-route (activated 'x' but expected 'y'), NOT a blank page.
        sres = _static([])
        rres = _render(nav=[_wrong_nav("#/x", activated="settings", expected="dashboard")])
        selected = _select_issues_to_fix(sres, rres, None, None)
        assert selected == [
            "dead nav link: '#/x' activated 'settings' but expected 'dashboard'"
        ]
        # And it is NOT the blank-page wording.
        assert all("activated NOTHING" not in line for line in selected)

    def test_empty_baseline_set_behaves_like_none(self):
        sres = _static(["S1"])
        rres = _render(console_errors=["C1"])
        assert _select_issues_to_fix(sres, rres, set(), set()) == _select_issues_to_fix(
            sres, rres, None, None
        )

    def test_clean_build_selects_nothing(self):
        # All-OK static + available render with no errors and only live navs ⇒
        # empty selection ⇒ the loop's ``failing`` is False (passes), matching
        # today's ``(not sres.ok) or render_failed`` == False.
        sres = _static([])
        rres = _render(nav=[_live_nav("#/home", "home")])
        assert _select_issues_to_fix(sres, rres, None, None) == []

    def test_skipped_render_contributes_nothing(self):
        # Chromium absent (available=False): its console/page/nav fields must be
        # ignored entirely — only static issues drive the selection (= today,
        # where render-skipped is never a failure).
        sres = _static(["S1"])
        rres = _render(
            available=False,
            console_errors=["ignored"],
            page_errors=["ignored too"],
            nav=[_dead_nav("#/ignored")],
        )
        assert _select_issues_to_fix(sres, rres, None, None) == ["S1"]

    def test_failing_equivalence_static_only_render_skipped(self):
        # Build equivalence corner: a static issue with render skipped ⇒
        # selection non-empty ⇒ failing True (today: not sres.ok == True).
        sres = _static(["S1"])
        rres = _render(available=False)
        assert bool(_select_issues_to_fix(sres, rres, None, None)) is True


# --------------------------------------------------------------------------- #
# REVISION mode (populated baselines) — smart hybrid: regressions ∪ hard breaks.
# --------------------------------------------------------------------------- #


class TestRevisionModeSelection:
    def test_static_regression_only_new_signature_selected(self):
        # baseline_static = {sigA}; post-edit static sigs = {sigA, sigB}.
        # Only sigB (the regression introduced by the edit) is selected; sigA
        # (a pre-existing nit) is left alone.
        sig_a = "pre-existing nit: orphan section 'about'"
        sig_b = "dead nav link: href '#/contact' has no matching <section data-page=\"contact\">"
        sres = _static([sig_a, sig_b])
        rres = _render()  # available, clean
        selected = _select_issues_to_fix(sres, rres, {sig_a}, set())

        assert sig_b in selected
        assert sig_a not in selected
        assert selected == [sig_b]

    def test_dead_nav_render_break_selected_even_if_target_preexisted(self):
        # A dead-nav render failure is HARD render-breakage and is ALWAYS
        # selected, even when its static counterpart pre-existed on the baseline
        # (the page won't display content regardless of "who broke it").
        preexisting_static = "dead nav link: href '#/orders' has no matching <section data-page=\"orders\">"
        sres = _static([preexisting_static])
        rres = _render(nav=[_dead_nav("#/orders")])
        selected = _select_issues_to_fix(
            sres, rres, baseline_static={preexisting_static}, baseline_console=set()
        )

        # The pre-existing STATIC line is suppressed (it's in the baseline) …
        assert preexisting_static not in selected
        # … but the RENDER-break dead-nav line is included regardless of baseline.
        assert (
            "dead nav link: '#/orders' activated NOTHING (no <section data-page> "
            "became active — blank page)"
            in selected
        )

    def test_page_error_always_selected_regardless_of_baseline(self):
        # Uncaught page exceptions are hard breakage — always fed back. There's
        # no page-error baseline param, so a populated static/console baseline
        # never suppresses them.
        sres = _static([])
        rres = _render(page_errors=["ReferenceError: handleClick is not defined"])
        selected = _select_issues_to_fix(
            sres, rres, baseline_static={"anything"}, baseline_console={"anything"}
        )
        assert selected == [
            "uncaught exception: ReferenceError: handleClick is not defined"
        ]

    def test_console_baseline_suppresses_preexisting_not_new(self):
        # A console error present in baseline_console (benign pre-existing noise)
        # is NOT selected; a NEW console error IS.
        pre = "Deprecation warning: foo() is deprecated"
        new = "Uncaught TypeError: cannot read 'x' of null"
        sres = _static([])
        rres = _render(console_errors=[pre, new])
        selected = _select_issues_to_fix(
            sres, rres, baseline_static=set(), baseline_console={pre}
        )

        assert f"console error: {new}" in selected
        assert f"console error: {pre}" not in selected
        assert selected == [f"console error: {new}"]

    def test_combined_regression_plus_hard_break_minus_preexisting(self):
        # The full smart-hybrid case in one shot:
        #   * sigA (static) pre-existing  -> ignored
        #   * sigB (static) new           -> selected (regression)
        #   * console_pre (in baseline)   -> ignored
        #   * console_new (not baseline)  -> selected
        #   * a dead nav                  -> selected (hard break, baseline-agnostic)
        #   * a page error                -> selected (hard break, baseline-agnostic)
        sig_a = "static pre-existing"
        sig_b = "static regression"
        console_pre = "benign pre-existing console noise"
        console_new = "new console error from the edit"
        sres = _static([sig_a, sig_b])
        rres = _render(
            console_errors=[console_pre, console_new],
            page_errors=["TypeError: boom"],
            nav=[_dead_nav("#/broken"), _live_nav("#/ok", "ok")],
        )
        selected = _select_issues_to_fix(
            sres,
            rres,
            baseline_static={sig_a},
            baseline_console={console_pre},
        )

        assert sig_b in selected
        assert sig_a not in selected
        assert f"console error: {console_new}" in selected
        assert f"console error: {console_pre}" not in selected
        assert "uncaught exception: TypeError: boom" in selected
        assert (
            "dead nav link: '#/broken' activated NOTHING (no <section data-page> "
            "became active — blank page)"
            in selected
        )
        # Order: static regressions, then console, then page errors, then dead nav.
        assert selected == [
            sig_b,
            f"console error: {console_new}",
            "uncaught exception: TypeError: boom",
            "dead nav link: '#/broken' activated NOTHING (no <section data-page> "
            "became active — blank page)",
        ]

    def test_revision_skipped_render_ignores_render_signals(self):
        # Even in revision mode, an unavailable render contributes nothing — a
        # baselined-away static issue + skipped render ⇒ empty selection.
        sig = "pre-existing static nit"
        sres = _static([sig])
        rres = _render(
            available=False, page_errors=["would-be break"], nav=[_dead_nav("#/x")]
        )
        assert _select_issues_to_fix(sres, rres, baseline_static={sig}) == []

    def test_dedup_preserves_first_seen_order(self):
        # Duplicate signals (e.g. the same console error reported twice) collapse
        # to one line, keeping first-seen order.
        sres = _static(["S1", "S1"])  # duplicate static
        rres = _render(console_errors=["C1", "C1"])
        assert _select_issues_to_fix(sres, rres, None, None) == [
            "S1",
            "console error: C1",
        ]
