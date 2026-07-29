"""Unit tests for evals.grading.render — the single formatting layer.

Offline and trivial by construction: values in, strings out. The point of this
suite is that BOTH renderers (terminal and REPORT.md) go through here, so a
style is defined once and cannot drift between the two views of one run.
"""

from __future__ import annotations

import pytest

from evals.grading import grade_runner, markdown_report, render


# ── values ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [(1.0, "1.00"), (0.9166, "0.92"), (3, "3"), (None, render.DASH)],
)
def test_number_is_for_rates_and_keeps_two_decimals(value, expected):
    assert render.number(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(85.5, "85.5"), (74.0, "74"), (0.5, "0.5"), (None, render.DASH)],
)
def test_score_drops_false_precision(value, expected):
    """`85.50` claims a hundredth of a point the judge never expressed."""
    assert render.score(value) == expected


@pytest.mark.parametrize(
    "count,expected", [(0, "0"), (999, "999"), (1000, "1.0k"), (20689, "20.7k"), (None, "0")]
)
def test_tokens_are_abbreviated(count, expected):
    assert render.tokens(count) == expected


def test_negative_reads_as_a_fraction_or_a_dash():
    assert render.negative({"correct": 0, "total": 1}) == "0/1"
    assert render.negative({"correct": 0, "total": 0}) == render.DASH
    assert render.negative(None) == render.DASH


def test_model_label_names_an_unset_provider_honestly():
    assert render.model_label({"provider": "mistral", "model": "m-small"}) == "mistral/m-small"
    assert render.model_label({"model": "m-small"}) == "implicit/m-small"
    assert render.model_label({}) == render.DASH
    assert render.model_label({}, unset="(implicit chain)") == "(implicit chain)"


def test_truncate_collapses_newlines_and_marks_the_cut():
    assert render.truncate("a\n  b\tc") == "a b c"
    assert render.truncate("x" * 50, 10) == "x" * 9 + "…"
    assert render.truncate(None) == ""


def test_short_hash_strips_the_algorithm_prefix():
    assert render.short_hash("sha256:f33c10a2c3c69ae5") == "f33c10a2c3c6"
    assert render.short_hash(None) == render.DASH


# ── layout ────────────────────────────────────────────────────────────────


def test_table_pads_every_column_and_leaves_the_last_one_free():
    columns = [("stage", 10, "<"), ("rows", 5, ">"), ("baseline", render.FLEXIBLE, "<")]
    lines = render.table(columns, [["specify", 3, "REFUSED"], ["plan", 12, "PASS"]])

    assert lines[0] == "  stage      rows  baseline"
    assert lines[1] == "  specify       3  REFUSED"
    assert lines[2] == "  plan         12  PASS"
    assert not any(line.endswith(" ") for line in lines), "no trailing whitespace"


def test_md_table_escapes_a_pipe_that_would_split_the_row():
    lines = render.md_table(["a", "b"], [["x | y", 1]], "lr")

    assert lines[0] == "| a | b |"
    assert lines[1] == "| --- | ---: |"
    assert lines[2] == r"| x \| y | 1 |"
    assert lines[2].count("|") - lines[2].count(r"\|") == 3, "still a 2-column row"


def test_rule_is_padded_to_the_requested_width():
    line = render.rule("results", 20).lstrip("\n")

    assert line.startswith("results ")
    assert len(line) == 20


# ── the two renderers agree ───────────────────────────────────────────────


def test_both_renderers_format_a_score_identically():
    """The drift this module exists to prevent: 85.5 on screen, 85.50 in the file."""
    assert render.score(85.5) == "85.5"
    assert "85.50" not in render.score(85.5)


def test_neither_renderer_keeps_a_private_copy_of_a_formatter():
    """A local `_number`/`_negative` is how the two views drifted apart before."""
    owned = ("_number", "_negative", "_one_line", "_short", "_model_label", "_tokens")
    for module in (grade_runner, markdown_report):
        for name in owned:
            assert not hasattr(module, name), (
                f"{module.__name__} defines its own {name} — it belongs in render.py"
            )


@pytest.mark.parametrize(
    "count,expected",
    [(0, "0 rows"), (1, "1 row"), (2, "2 rows"), (12, "12 rows")],
)
def test_plural_agrees_with_its_count(count, expected):
    """`1 rows selected` reads like a draft; it appeared in three places."""
    assert render.plural(count, "row") == expected


def test_plural_handles_a_multi_word_noun():
    assert render.plural(1, "model call") == "1 model call"
    assert render.plural(5, "model call") == "5 model calls"
