"""Unit tests for prototype-analyze's ONE custom precheck hook (required
subsection headers + valid Readiness verdict enum + a Findings table — the
checks the generic model_graded/precheck.py config cannot express).
"""

from __future__ import annotations

from evals.model_graded.agents.prototype_analyze.analysis_structure_check import check

GOOD_ANALYSIS = """<analysis>
## Spec Kit Analysis Report

### Summary
Spec and tasks are well aligned.

### Findings

| # | Category | Status | Detail |
|---|----------|--------|--------|
| 1 | Consistency | ✅ Clear | Tasks match spec pages exactly |

### Issues requiring attention
No blocking issues found.

### Risk register
Task 2 — Dashboard Page: minor risk.

### Suggested next actions
1. **Proceed** — Analysis is clean.

### Readiness verdict
READY TO BUILD
All checks pass.
</analysis>"""


def test_passes_on_well_formed_analysis():
    passed, reason = check(GOOD_ANALYSIS)
    assert passed is True
    assert "all 6 required sections" in reason


def test_fails_when_a_required_header_is_missing():
    missing = GOOD_ANALYSIS.replace("### Risk register\nTask 2 — Dashboard Page: minor risk.\n\n", "")
    passed, reason = check(missing)
    assert passed is False
    assert "Risk register" in reason


def test_fails_on_invalid_verdict_value():
    bad = GOOD_ANALYSIS.replace("READY TO BUILD", "LOOKS GOOD")
    passed, reason = check(bad)
    assert passed is False
    assert "no valid verdict" in reason


def test_fails_when_findings_has_no_table():
    no_table = GOOD_ANALYSIS.replace(
        "| # | Category | Status | Detail |\n|---|----------|--------|--------|\n"
        "| 1 | Consistency | ✅ Clear | Tasks match spec pages exactly |",
        "Everything looks fine, no issues found anywhere in the artifacts.",
    )
    passed, reason = check(no_table)
    assert passed is False
    assert "no markdown table" in reason


def test_wrapper_missing_is_not_this_checks_job():
    """Division of labor: the custom hook only checks header/verdict/table
    structure — a missing <analysis> wrapper is the generic precheck's
    concern, not this one's."""
    unwrapped = GOOD_ANALYSIS.replace("<analysis>\n", "").replace("\n</analysis>", "")
    passed, _ = check(unwrapped)
    assert passed is True
