"""Unit tests for evals.model_graded.precheck — the GENERIC,
agent-agnostic deterministic pre-check (specs/005-prompt-eval-scoring/
clarifications.md Q10). Deliberately uses fixture configs that are NOT
prototype-specify-shaped, to prove genericity (task T4).
"""

from __future__ import annotations

import pytest

from evals.model_graded.precheck import run_precheck, validate_precheck_config

GENERIC_CONFIG = {
    "wrapper": "<doc>",
    "min_sections": 2,
    "section_pattern": r"^## ",
    "forbidden": ["TODO", "placeholder"],
}


def test_passes_when_all_checks_satisfied():
    response = "<doc>\n## One\ncontent\n## Two\nmore content\n</doc>"
    passed, reason = run_precheck(response, GENERIC_CONFIG)
    assert passed is True
    assert "2 section(s)" in reason


def test_fails_missing_wrapper():
    response = "## One\ncontent\n## Two\nmore\n"
    passed, reason = run_precheck(response, GENERIC_CONFIG)
    assert passed is False
    assert "not wrapped" in reason


def test_fails_under_min_sections():
    response = "<doc>\n## Only One\ncontent\n</doc>"
    passed, reason = run_precheck(response, GENERIC_CONFIG)
    assert passed is False
    assert "need >= 2" in reason


def test_fails_forbidden_string_case_insensitive():
    response = "<doc>\n## One\nSome PLACEHOLDER text\n## Two\nmore\n</doc>"
    passed, reason = run_precheck(response, GENERIC_CONFIG)
    assert passed is False
    assert "forbidden placeholder string present" in reason


def test_generic_across_a_second_unrelated_config_shape():
    """Proves genericity: a totally different wrapper/pattern/forbidden set
    works identically — no hardcoded assumption about <spec> or any agent."""
    config = {
        "wrapper": "[[REPORT]]",
        "min_sections": 1,
        "section_pattern": r"^--- ",
        "forbidden": ["N/A"],
    }
    good = "[[REPORT]]\n--- section one\ndata\n[[REPORT]]"
    passed, _ = run_precheck(good, config)
    assert passed is True


def test_validate_precheck_config_raises_on_missing_key():
    with pytest.raises(ValueError, match="missing required key"):
        validate_precheck_config({"wrapper": "<doc>", "section_pattern": "^## "})


def test_min_sections_defaults_to_1_when_absent_in_config():
    config = {"wrapper": "<doc>", "section_pattern": r"^## ", "forbidden": []}
    passed, _ = run_precheck("<doc>\n## One\n</doc>", config)
    assert passed is True
