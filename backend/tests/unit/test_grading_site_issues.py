"""Unit tests for evals.grading.site.issues — grouping, not dumping.

The point of the module: a phase with five rows produces five critiques plus a
browser sweep each, and the same defect usually spans several rows. What a
reader needs is the group and its count, not every line.
"""

from __future__ import annotations

from evals.grading.site import issues, model

from tests.unit.test_grading_site_model import row, runs_root, simple_stage, write_run  # noqa: F401


def _stage(runs_root, *, rows, weaknesses=None, strengths=None, findings=None):  # noqa: F811
    run_dir = write_run(
        runs_root, "260730-100000-small",
        stages=[("s-a", {
            "score": {
                "results": rows,
                "recurring_weaknesses": weaknesses or [],
                "recurring_strengths": strengths or [],
            },
            "grade": [
                {"row_id": r["row_id"], "weaknesses": r.pop("_weaknesses", []),
                 "strengths": r.pop("_strengths", []),
                 "score_caps": r.pop("_caps", {})}
                for r in rows
            ],
        })],
        findings={"s-a": findings} if findings else None,
    )
    return model.load_run(run_dir, "prototype").stages[0]


def test_no_issues_is_an_empty_summary(runs_root):  # noqa: F811
    summary = issues.summarize(_stage(runs_root, rows=[row("r1", 90)]))
    assert summary.total == 0
    assert summary.groups == ()
    assert summary.clean_rows == 1


def test_the_judges_own_clusters_are_used_as_given(runs_root):  # noqa: F811
    """The grader already clustered these; re-clustering would second-guess it."""
    stage = _stage(
        runs_root,
        rows=[row("r1", 90), row("r2", 80)],
        weaknesses=[{"evidence": "nav is cramped", "row_ids": ["r1", "r2"]}],
    )
    summary = issues.summarize(stage)
    assert summary.distinct == 1
    group = summary.groups[0]
    assert group.count == 2
    assert group.row_ids == ("r1", "r2")
    assert group.detail == "nav is cramped"
    assert group.source == issues.SOURCE_JUDGE


def test_the_same_defect_on_several_rows_becomes_one_group(runs_root):  # noqa: F811
    stage = _stage(runs_root, rows=[row("r1", 90), row("r2", 80)], findings={
        "r1": {"code_score": 70, "issues": ["route /reports has no section"]},
        "r2": {"code_score": 60, "issues": ["route /reports has no section"]},
    })
    summary = issues.summarize(stage)
    assert summary.distinct == 1
    assert summary.groups[0].count == 2
    assert summary.total == 2


def test_numbers_and_quotes_do_not_split_a_group(runs_root):  # noqa: F811
    """'3 of 12 buttons' and '5 of 9 buttons' are one defect, not two."""
    stage = _stage(runs_root, rows=[row("r1", 90), row("r2", 80)], findings={
        "r1": {"code_score": 70, "issues": ["3 of 12 buttons do nothing"]},
        "r2": {"code_score": 70, "issues": ["5 of 9 buttons do nothing"]},
    })
    summary = issues.summarize(stage)
    assert summary.distinct == 1
    assert summary.groups[0].count == 2
    # …and the group shows a real example, not the masked grouping key.
    assert "buttons do nothing" in summary.groups[0].detail
    assert "#" not in summary.groups[0].detail


def test_judge_and_code_never_merge(runs_root):  # noqa: F811
    """Different authority: an opinion and a reproducible browser finding."""
    stage = _stage(
        runs_root,
        rows=[dict(row("r1", 90), _weaknesses=["nav is cramped"])],
        findings={"r1": {"code_score": 70, "issues": ["nav is cramped"]}},
    )
    summary = issues.summarize(stage)
    assert summary.distinct == 2
    assert summary.weakness_count == 1
    assert summary.code_count == 1


def test_weaknesses_strengths_and_code_are_counted_apart(runs_root):  # noqa: F811
    """Merging them buries the actionable half — the reason they are separate."""
    stage = _stage(
        runs_root,
        rows=[dict(row("r1", 90), _weaknesses=["cramped nav"], _strengths=["clear copy"])],
        findings={"r1": {"code_score": 70, "issues": ["dead route"]}},
    )
    summary = issues.summarize(stage)
    assert summary.weakness_count == 1
    assert summary.code_count == 1
    assert summary.strength_count == 1
    # A strength is never something to act on, so it is not a problem.
    assert summary.problem_count == 2
    assert summary.total == 3


def test_strengths_are_grouped_from_the_judges_clusters(runs_root):  # noqa: F811
    stage = _stage(
        runs_root,
        rows=[row("r1", 90), row("r2", 80)],
        strengths=[{"evidence": "clear hierarchy", "row_ids": ["r1", "r2"]}],
    )
    summary = issues.summarize(stage)
    assert summary.strength_count == 2
    assert summary.strengths[0].detail == "clear hierarchy"
    assert summary.weakness_count == 0


def test_every_code_finding_kind_is_collected(runs_root):  # noqa: F811
    stage = _stage(runs_root, rows=[row("r1", 90)], findings={"r1": {
        "code_score": 20,
        "issues": ["a static issue"],
        "warnings": ["a static warning"],
        "render": {
            "console_errors": ["a console error"],
            "page_errors": ["an uncaught exception"],
            "coverage_errors": ["a coverage gap"],
            "nav_results": [{"ok": False, "href": "#x", "expected": "x", "activated": "y"}],
        },
        "interactions": {"failures": [{"action": "click", "target": "#b",
                                       "errors": ["boom"]}]},
    }})
    kinds = {group.kind for group in issues.summarize(stage).groups}
    assert kinds == {
        "static issue", "static warning", "console error", "uncaught exception",
        "nav coverage", "dead nav", "interaction failure",
    }


def test_a_score_reduction_is_an_issue_under_the_old_schema(runs_root):  # noqa: F811
    stage = _stage(runs_root, rows=[
        dict(row("r1", 90), _caps={"a11y": {"reported": 60, "capped_to": 40}}),
    ])
    summary = issues.summarize(stage)
    assert summary.distinct == 1
    assert summary.groups[0].kind == "score reduction"
    assert "a11y reduced 60 → 40" == summary.groups[0].detail


def test_a_score_reduction_is_an_issue_under_the_severity_schema(runs_root):  # noqa: F811
    """The calibrated judge writes `final`, not `capped_to`."""
    stage = _stage(runs_root, rows=[
        dict(row("r1", 90), _caps={"data_realism": {"reported": 95, "final": 94, "minor": 1}}),
    ])
    summary = issues.summarize(stage)
    assert summary.distinct == 1
    assert "data_realism reduced 95 → 94" == summary.groups[0].detail


def test_a_cap_that_reduced_nothing_is_not_an_issue(runs_root):  # noqa: F811
    """And neither key present must never render as "95 → None"."""
    stage = _stage(runs_root, rows=[
        dict(row("r1", 90), _caps={"a": {"reported": 95, "final": 95},
                                   "b": {"reported": 95}}),
    ])
    assert issues.summarize(stage).total == 0


def test_a_clustered_weakness_is_not_counted_twice(runs_root):  # noqa: F811
    """It appears in the judge's cluster AND on the row; it is one defect."""
    stage = _stage(
        runs_root,
        rows=[dict(row("r1", 90), _weaknesses=["nav is cramped"])],
        weaknesses=[{"evidence": "nav is cramped", "row_ids": ["r1"]}],
    )
    summary = issues.summarize(stage)
    assert summary.distinct == 1
    assert summary.total == 1


def test_groups_are_ordered_widest_first(runs_root):  # noqa: F811
    stage = _stage(runs_root, rows=[row("r1", 90), row("r2", 80), row("r3", 70)],
                   findings={
                       "r1": {"code_score": 70, "issues": ["everywhere", "just here"]},
                       "r2": {"code_score": 70, "issues": ["everywhere"]},
                       "r3": {"code_score": 70, "issues": ["everywhere"]},
                   })
    counts = [group.count for group in issues.summarize(stage).groups]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == 3


def test_totals_count_rows_affected_and_clean(runs_root):  # noqa: F811
    stage = _stage(runs_root, rows=[row("r1", 90), row("r2", 80), row("r3", 70)],
                   findings={"r1": {"code_score": 70, "issues": ["one", "two"]}})
    summary = issues.summarize(stage)
    assert summary.total == 2
    assert summary.distinct == 2
    assert summary.rows_affected == 1
    assert summary.rows_total == 3
    assert summary.clean_rows == 2
    assert summary.code_count == 2
    assert summary.weakness_count == 0
