"""L5 — selection semantics: the unit-level ROOT CAUSE statement.

FINDINGS A2 (.investigations/revision-pipeline-thinking-issue/FINDINGS.md):
``_select_issues_to_fix`` is the fix-loop's ONLY failure signal
(``failing = bool(selected)``). For a revision it selects:

  * static issues NOT on the pre-edit baseline (regressions),
  * console errors NOT on the baseline,
  * hard render-breakage (page errors, dead nav) always.

Nothing in its input mentions the user's instruction — so an edit that is a
structurally clean NO-OP (satisfies nothing the user asked, breaks nothing)
selects ``[]`` ⇒ ``failing=False`` ⇒ the loop exits reporting success.
These tests PASS against current code: they pin the gap precisely, so the
Phase-2 scenario evals (which xfail) can point here as the mechanism.

Pure-function tests, no mocks beyond dataclass construction.
"""

from __future__ import annotations

import pytest

from app.agents.render_check import RenderResult
from app.agents.static_check import StaticCheckResult

pytestmark = pytest.mark.eval


def _select(sres, rres, base_static=None, base_console=None):
    from agents.execution_engine.engine import _select_issues_to_fix

    return _select_issues_to_fix(
        sres, rres, base_static, base_console, require_render=True
    )


def test_clean_noop_edit_selects_nothing__the_root_cause() -> None:
    """FINDINGS A2 — the defect's mechanism, stated as a passing test.

    Post-edit file: statically clean, renders clean. The user's instruction
    ("make the Save button save") is UNSATISFIED — but that fact is not an
    input to this function, so the selection is empty and the fix-loop's
    ``failing`` is False. This is WHY a no-op revision reports success.
    """
    sres = StaticCheckResult(ok=True, issues=[])
    rres = RenderResult(ok=True, available=True)

    selected = _select(sres, rres, {"static-preexisting"}, {"console-preexisting"})

    assert selected == []          # nothing to fix, per the loop's only signal
    assert not bool(selected)      # == failing=False: loop exits, "success"


def test_preexisting_issues_are_baselined_out_by_design() -> None:
    """The baseline filter itself is intentional (don't chase pre-existing
    nits) — the gap is that instruction-fulfillment has no lane, not that
    the baseline filter exists."""
    sres = StaticCheckResult(ok=False, issues=["static-preexisting"])
    rres = RenderResult(ok=True, available=True, console_errors=["console-preexisting"])

    selected = _select(sres, rres, {"static-preexisting"}, {"console-preexisting"})

    assert selected == []


def test_new_regressions_are_selected() -> None:
    """Control: the loop DOES catch what it was built for — NEW static issues
    and always-included hard breakage. The machinery works; its question is
    just narrower than the user's."""
    sres = StaticCheckResult(ok=False, issues=["static-preexisting", "static-NEW"])
    rres = RenderResult(
        ok=False,
        available=True,
        console_errors=["console-NEW"],
        page_errors=["boom"],
    )

    selected = _select(sres, rres, {"static-preexisting"}, {"console-preexisting"})

    assert "static-NEW" in selected
    assert "console error: console-NEW" in selected
    assert "uncaught exception: boom" in selected
    assert "static-preexisting" not in selected
