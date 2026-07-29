"""Unit tests for evals.grading.precheck — the deterministic gate.

The load-bearing test here is the false-positive regression: the old bare
substring list forbade "placeholder" and "stub", which rejected 7 of 11 real
specs for using ordinary UI vocabulary. Offline, no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.grading.precheck import closing_tag, run, validate_config

WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "grading"
    / "model"
    / "workflows"
    / "prototype"
)
RUBRIC_PATH = WORKFLOW_DIR / "prototype_specify_rubric.yaml"
RUN_ARTIFACT_PATH = WORKFLOW_DIR / "example-run" / "artifacts" / "prototype_specify_run.json"

SIMPLE_CONFIG = {
    "wrapper": "<doc>",
    "section_pattern": r"^## ",
    "min_sections": 2,
    "forbidden": [{"pattern": r"(?i)lorem ipsum", "reason": "filler text"}],
}


def real_precheck_config() -> dict:
    """The `precheck:` block from the committed prototype-specify rubric."""
    return yaml.safe_load(RUBRIC_PATH.read_text())["precheck"]


def wrap(body: str) -> str:
    """Wrap a snippet in a minimal spec that satisfies wrapper + section count."""
    sections = "\n".join(f"### Page {index}\n{body}" for index in range(1, 5))
    return f"<spec>\n{sections}\n</spec>"


def passing_response() -> str:
    """A response that satisfies every check in SIMPLE_CONFIG."""
    return "<doc>\n## One\ncontent\n## Two\nmore content\n</doc>"


# ── validate_config ───────────────────────────────────────────────────────


def test_validate_config_accepts_a_complete_config():
    validate_config(SIMPLE_CONFIG)


def test_validate_config_names_the_missing_keys():
    with pytest.raises(ValueError) as error:
        validate_config({"wrapper": "<doc>"})
    message = str(error.value)
    assert "section_pattern" in message
    assert "forbidden" in message


def test_validate_config_does_not_require_min_sections():
    validate_config({"wrapper": "<doc>", "section_pattern": r"^## ", "forbidden": []})


# ── closing_tag ───────────────────────────────────────────────────────────


def test_closing_tag_derives_the_closing_form():
    assert closing_tag("<spec>") == "</spec>"


def test_closing_tag_falls_back_to_the_wrapper_itself():
    assert closing_tag("=== SPEC ===") == "=== SPEC ==="


# ── wrapper check ─────────────────────────────────────────────────────────


def test_wrapper_missing_fails():
    passed, reason = run("## One\ncontent\n## Two\nmore\n", SIMPLE_CONFIG)
    assert passed is False
    assert "not wrapped in <doc>...</doc>" in reason


def test_preamble_before_the_wrapper_fails():
    passed, reason = run("Sure! Here you go:\n" + passing_response(), SIMPLE_CONFIG)
    assert passed is False
    assert "not wrapped" in reason


def test_postamble_after_the_wrapper_fails():
    passed, reason = run(passing_response() + "\nLet me know if you want changes.", SIMPLE_CONFIG)
    assert passed is False
    assert "not wrapped" in reason


def test_wrapper_check_is_case_insensitive():
    response = "<DOC>\n## One\ncontent\n## Two\nmore content\n</DOC>"
    passed, reason = run(response, SIMPLE_CONFIG)
    assert passed is True
    assert "wrapper ok" in reason


def test_close_wrapper_override_for_a_non_derivable_closing_form():
    config = {
        "wrapper": "<!doctype html>",
        "close_wrapper": "</html>",
        "section_pattern": r"^<section",
        "min_sections": 1,
        "forbidden": [],
    }
    response = "<!doctype html>\n<section id=one></section>\n</html>"
    passed, reason = run(response, config)
    assert passed is True
    assert "wrapper ok" in reason


# ── section count ─────────────────────────────────────────────────────────


def test_too_few_sections_fails():
    passed, reason = run("<doc>\n## Only one\ncontent\n</doc>", SIMPLE_CONFIG)
    assert passed is False
    assert "only 1 section(s)" in reason
    assert "need >= 2" in reason


def test_pass_reason_states_what_was_verified():
    passed, reason = run(passing_response(), SIMPLE_CONFIG)
    assert passed is True
    assert reason == "wrapper ok, 2 section(s) >= 2, no forbidden patterns"


# ── forbidden regexes — the false-positive regression ─────────────────────


LEGITIMATE_UI_VOCABULARY = [
    'Search input placeholder: "Search waitlist..."',
    '`.form-input` "Room" placeholder "e.g., Conf Room 3"',
    "click student row -> `#/students/{id}` (stub page)",
]


@pytest.mark.parametrize("snippet", LEGITIMATE_UI_VOCABULARY)
def test_legitimate_ui_vocabulary_is_not_forbidden(snippet):
    passed, reason = run(wrap(snippet), real_precheck_config())
    assert passed is True, reason


REAL_FILLER = [
    "Lorem ipsum dolor sit amet",
    "Owner: TBD",
    "Reports page — coming soon",
    "Body copy is placeholder text for now",
    "Customer A owes $1,200",
]


@pytest.mark.parametrize("snippet", REAL_FILLER)
def test_real_filler_still_fails(snippet):
    passed, reason = run(wrap(snippet), real_precheck_config())
    assert passed is False
    assert "forbidden pattern" in reason


def test_forbidden_failure_reports_the_reason_and_the_match():
    passed, reason = run(wrap("Lorem Ipsum everywhere"), real_precheck_config())
    assert passed is False
    assert "Lorem Ipsum" in reason
    assert "filler text instead of real invented data" in reason


def test_first_forbidden_match_wins():
    config = {
        "wrapper": "<doc>",
        "section_pattern": r"^## ",
        "min_sections": 1,
        "forbidden": [
            {"pattern": r"(?i)first", "reason": "the first rule"},
            {"pattern": r"(?i)second", "reason": "the second rule"},
        ],
    }
    passed, reason = run("<doc>\n## S\nfirst and second\n</doc>", config)
    assert passed is False
    assert "the first rule" in reason
    assert "the second rule" not in reason


# ── hook combination ──────────────────────────────────────────────────────


def hook_pass(response: str) -> tuple[bool, str]:
    """A custom hook that always passes."""
    return True, "all nav targets resolved"


def hook_fail(response: str) -> tuple[bool, str]:
    """A custom hook that always fails."""
    return False, "nav target '#/missing' has no page section"


def test_no_hook_returns_the_generic_reason_alone():
    passed, reason = run(passing_response(), SIMPLE_CONFIG)
    assert passed is True
    assert "generic:" not in reason


def test_both_pass():
    passed, reason = run(passing_response(), SIMPLE_CONFIG, hook=hook_pass)
    assert passed is True
    assert reason == (
        "generic: wrapper ok, 2 section(s) >= 2, no forbidden patterns "
        "| custom: all nav targets resolved"
    )


def test_hook_passes_but_generic_fails():
    passed, reason = run("no wrapper here", SIMPLE_CONFIG, hook=hook_pass)
    assert passed is False
    assert "generic: response not wrapped" in reason
    assert "custom: all nav targets resolved" in reason


def test_generic_passes_but_hook_fails():
    passed, reason = run(passing_response(), SIMPLE_CONFIG, hook=hook_fail)
    assert passed is False
    assert "generic: wrapper ok" in reason
    assert "custom: nav target '#/missing' has no page section" in reason


def test_generic_check_runs_even_when_the_hook_fails():
    """The generic reason must still be reported, never short-circuited."""
    passed, reason = run(wrap("Lorem ipsum"), real_precheck_config(), hook=hook_fail)
    assert passed is False
    assert "forbidden pattern" in reason
    assert "custom:" in reason


# ── replay against the committed run ──────────────────────────────────────


def test_narrowed_config_passes_every_committed_positive_response():
    """The 11 real specs the old bare-substring list rejected 7 of."""
    rows = [row for row in json.loads(RUN_ARTIFACT_PATH.read_text()) if row["expect"] == "pass"]
    assert len(rows) == 11
    config = real_precheck_config()
    failures = {}
    for row in rows:
        passed, reason = run(row["response"], config)
        if not passed:
            failures[row["scenario_id"]] = reason
    assert failures == {}
