"""Unit tests for the skill script ``scripts/intake_readiness.py`` (the readiness rule).

The script is stdlib-only and lives in the skill folder, which is not a Python
package, so it is imported by path like the builder imports it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.agents.workflow_builder.skill_package import SKILL_DIR
from tests.factories.intake_brief_factory import (
    PDF_QUESTIONS,
    IntakeBriefFactory,
    question,
)


def _load() -> ModuleType:
    path = SKILL_DIR / "scripts" / "intake_readiness.py"
    spec = importlib.util.spec_from_file_location("intake_readiness_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rule = _load()


def _filled() -> dict[str, Any]:
    return IntakeBriefFactory.filled_email()["slots"]


def test_evaluate_returns_ready_filled_when_every_blocking_slot_is_filled() -> None:
    result = rule.evaluate(_filled())

    assert result["ready"] is True
    assert result["reason"] == "filled"
    assert result["missing"] == []


def test_evaluate_returns_gaps_when_a_blocking_slot_is_assumed() -> None:
    slots = _filled()
    slots["input_source"] = {
        "value": "uploads",
        "source": "assumed",
        "criticality": "blocking",
    }

    result = rule.evaluate(slots)

    assert result["ready"] is False
    assert result["reason"] == "gaps"
    assert result["missing"] == ["input_source"]


def test_evaluate_treats_not_applicable_as_unfilled_when_slot_does_not_allow_it() -> (
    None
):
    slots = _filled()
    slots["goal"] = {
        "value": None,
        "source": "not_applicable",
        "criticality": "blocking",
        "reason": "x",
    }

    result = rule.evaluate(slots)

    assert result["missing"] == ["goal"]
    assert result["invalid_not_applicable"] == ["goal"]


def test_evaluate_treats_not_applicable_as_unfilled_when_reason_is_missing() -> None:
    slots = _filled()
    slots["external_systems"] = {
        "value": None,
        "source": "not_applicable",
        "criticality": "blocking",
    }

    result = rule.evaluate(slots)

    assert result["missing"] == ["external_systems"]
    assert result["invalid_not_applicable"] == ["external_systems"]


def test_evaluate_treats_request_source_as_unfilled_when_value_is_empty() -> None:
    slots = _filled()
    slots["goal"] = {"value": "  ", "source": "request", "criticality": "blocking"}

    assert rule.evaluate(slots)["missing"] == ["goal"]


def test_evaluate_forces_ready_when_user_explicitly_accepts_defaults() -> None:
    slots = IntakeBriefFactory.vague_pdf()["slots"]

    result = rule.evaluate(slots, explicit_defaults=True)

    assert result["ready"] is True
    assert result["reason"] == "explicit_defaults"
    assert (
        "Assumption: done_when = Every PDF converted - correct me if wrong"
        in result["assumptions"]
    )


def test_evaluate_forces_ready_when_rounds_reach_the_limit() -> None:
    slots = IntakeBriefFactory.vague_pdf()["slots"]

    assert rule.evaluate(slots, rounds_asked=2, max_rounds=2)["reason"] == "max_rounds"
    assert rule.evaluate(slots, rounds_asked=1, max_rounds=2)["reason"] == "gaps"


def test_evaluate_echoes_only_important_assumptions_when_ready_is_not_forced() -> None:
    result = rule.evaluate(IntakeBriefFactory.vague_pdf()["slots"])

    assert result["assumptions"] == [
        "Assumption: volume_scale = up to 8 PDFs per run - correct me if wrong"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "defaults",
        "Defaults please",
        "Defaults!",
        "use the defaults",
        "  use defaults. ",
        "you decide",
        "You decide.",
        "your call",
        "go ahead",
        "just do it",
        "OK, just do it",
        "1a, rest as recommended",
        "1a 2b, the rest defaults",
        "accept all recommended options",
        "no preference",
        "I don\u2019t mind",
    ],
)
def test_is_explicit_defaults_returns_true_when_reply_is_essentially_the_keyword(
    text: str,
) -> None:
    assert rule.is_explicit_defaults(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "1a 2b 3c",
        "they are scanned invoices",
        "",
        "I don't want the defaults, use OCR",
        "no defaults",
        "defaults are wrong for scanned files",
        "you decide the format but the PDFs are scans",
        "the default is fine except question 2",
    ],
)
def test_is_explicit_defaults_returns_false_when_reply_only_mentions_the_keyword(
    text: str,
) -> None:
    assert rule.is_explicit_defaults(text) is False


def test_parse_answer_codes_maps_codes_when_formats_vary() -> None:
    questions = list(PDF_QUESTIONS)

    assert rule.parse_answer_codes("1a 2) b, 3:B 4-a 5.c", questions) == {
        0: 0,
        1: 1,
        2: 1,
        3: 0,
        4: 2,
    }


def test_parse_answer_codes_ignores_codes_when_question_or_option_does_not_exist() -> (
    None
):
    questions = list(PDF_QUESTIONS)

    assert rule.parse_answer_codes("9a 1e 2 apples", questions) == {}


def test_parse_answer_codes_keeps_last_code_when_question_is_answered_twice() -> None:
    assert rule.parse_answer_codes("1a 1b", list(PDF_QUESTIONS)) == {0: 1}


def test_apply_answers_sets_user_source_when_a_real_option_is_chosen() -> None:
    slots = IntakeBriefFactory.vague_pdf()["slots"]

    merged, answered = rule.apply_answers(slots, list(PDF_QUESTIONS), {1: 1})

    assert merged["input_variability"] == {
        "value": "Some scans",
        "source": "user",
        "criticality": "blocking",
    }
    assert answered == {"input_variability"}


def test_apply_answers_sets_recommended_as_assumed_when_fallback_is_chosen() -> None:
    slots = IntakeBriefFactory.vague_pdf()["slots"]

    merged, _ = rule.apply_answers(slots, list(PDF_QUESTIONS), {0: 2})

    assert merged["input_source"]["value"] == "Uploaded at launch"
    assert merged["input_source"]["source"] == "assumed"


def test_apply_defaults_fills_open_questions_and_leaves_answers_when_forced() -> None:
    slots, answered = rule.apply_answers(
        IntakeBriefFactory.vague_pdf()["slots"], list(PDF_QUESTIONS), {1: 1}
    )

    merged = rule.apply_defaults(slots, list(PDF_QUESTIONS), answered)

    assert merged["input_variability"]["source"] == "user"
    assert merged["input_source"] == {
        "value": "Uploaded at launch",
        "source": "assumed",
        "criticality": "blocking",
    }
    assert merged["done_when"]["source"] == "assumed"
    assert all(merged[name]["source"] != "unknown" for name in rule.BLOCKING_SLOTS)
    assert all(
        merged[name].get("value") or merged[name]["source"] == "not_applicable"
        for name in rule.BLOCKING_SLOTS
    )


def test_apply_defaults_gives_placeholder_when_blocking_slot_has_no_question() -> None:
    slots = IntakeBriefFactory.slots()

    merged = rule.apply_defaults(slots, [])

    assert merged["goal"]["source"] == "assumed"
    assert merged["goal"]["value"] == rule.UNSPECIFIED_VALUE


def test_main_exits_zero_and_one_when_brief_is_ready_or_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ready = tmp_path / "ready.json"
    ready.write_text(json.dumps(IntakeBriefFactory.filled_email()), encoding="utf-8")
    vague = tmp_path / "vague.json"
    vague.write_text(json.dumps(IntakeBriefFactory.vague_pdf()), encoding="utf-8")

    assert rule.main([str(ready)]) == 0
    assert rule.main([str(vague)]) == 1
    assert rule.main([str(vague), "--defaults", "--json"]) == 0
    assert '"reason": "explicit_defaults"' in capsys.readouterr().out


def test_main_exits_two_when_file_has_no_slots(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")

    assert rule.main([str(bad)]) == 2
    assert rule.main([str(tmp_path / "absent.json")]) == 2


# --- Writes outside the run: destination, approval question, "post automatically" ------


def _slack_slots(**overrides: dict[str, Any]) -> dict[str, Any]:
    slots = IntakeBriefFactory.filled_slack()["slots"]
    slots.update(overrides)
    return slots


def test_evaluate_requires_write_destination_when_workflow_posts_outside_the_run() -> (
    None
):
    slots = _slack_slots(
        write_destinations={
            "value": None,
            "source": "not_applicable",
            "criticality": "blocking",
            "reason": "x",
        }
    )

    result = rule.evaluate(slots)

    assert result["missing"] == ["write_destinations"]
    assert "write_destinations" in result["invalid_not_applicable"]


def test_evaluate_allows_no_write_destination_when_nothing_is_written() -> None:
    assert rule.evaluate(_filled())["missing"] == []


def test_evaluate_refuses_not_applicable_approval_when_workflow_posts() -> None:
    slots = _slack_slots(
        human_approval_points={
            "value": None,
            "source": "not_applicable",
            "criticality": "blocking",
            "reason": "x",
        }
    )

    assert rule.evaluate(slots)["missing"] == ["human_approval_points"]


@pytest.mark.parametrize(
    "label",
    [
        "No, post automatically",
        "Post automatically",
        "no review",
        "Skip the approval",
        "Post without review",
    ],
)
def test_removes_person_returns_true_when_option_takes_the_person_out(
    label: str,
) -> None:
    assert rule.removes_person(label) is True


@pytest.mark.parametrize(
    "label",
    [
        "Approve the final message before it posts",
        "Approve the draft earlier, post automatically after edits still gated by a confirm step",
    ],
)
def test_removes_person_returns_false_when_a_person_still_approves(label: str) -> None:
    assert rule.removes_person(label) is False


def test_question_violations_flags_no_gate_option_when_workflow_posts() -> None:
    bad = question(
        "human_approval_points",
        "Approve first?",
        ("Yes, approve first", "No, post automatically"),
    )

    problems = rule.question_violations(_slack_slots(), [bad])

    assert len(problems) == 1
    assert "removes that person" in problems[0]


def test_question_violations_allows_whether_question_when_nothing_is_written() -> None:
    whether = question(
        "human_approval_points", "Review first?", ("No review", "Review first")
    )

    assert rule.question_violations(_filled(), [whether]) == []


def test_enforce_platform_rules_records_platform_gate_when_user_says_post_automatically() -> (
    None
):
    slots = _slack_slots(
        human_approval_points={
            "value": "post automatically",
            "source": "user",
            "criticality": "blocking",
        }
    )

    merged, notes = rule.enforce_platform_rules(slots)

    assert (
        merged["human_approval_points"]["value"]
        == "gate-before-post (platform requirement)"
    )
    assert merged["human_approval_points"]["source"] == "user"
    assert notes == [
        rule.PLATFORM_GATE_NOTE.format(
            action="the irreversible action (Posts the release notes to Slack)"
        )
    ]


def test_enforce_platform_rules_keeps_approval_when_a_person_approves() -> None:
    merged, notes = rule.enforce_platform_rules(_slack_slots())

    assert (
        merged["human_approval_points"]["value"] == "The final message before it posts"
    )
    assert notes == []


def test_apply_defaults_leaves_no_slot_unknown_when_ready_is_forced() -> None:
    slots = IntakeBriefFactory.vague_pdf()["slots"]

    merged = rule.apply_defaults(slots, list(PDF_QUESTIONS))

    assert [n for n in rule.ALL_SLOTS if merged[n]["source"] == "unknown"] == []
    assert merged["depth"] == {
        "value": "Full (the skill's default depth)",
        "source": "assumed",
        "criticality": "important",
    }
    assert merged["trigger"]["value"] == rule.UNSPECIFIED_VALUE


def test_enforce_platform_rules_adds_note_when_model_already_recorded_platform_gate() -> (
    None
):
    slots = _slack_slots(
        human_approval_points={
            "value": rule.PLATFORM_GATE_VALUE,
            "source": "user",
            "criticality": "blocking",
        }
    )

    merged, notes = rule.enforce_platform_rules(slots)

    assert merged["human_approval_points"]["value"] == rule.PLATFORM_GATE_VALUE
    assert len(notes) == 1 and notes[0].startswith(
        "The approval step before the irreversible action"
    )


# --- Question plan: blocking first, then important to fill 5 ---------------------------


def _three_open_blocking() -> dict[str, Any]:
    slots = IntakeBriefFactory.filled_email()["slots"]
    for name in ("input_source", "output_structure", "deliverable"):
        slots[name] = {"value": None, "source": "unknown", "criticality": "blocking"}
    return slots


def test_question_plan_problems_accepts_three_blocking_plus_two_important_when_three_are_open() -> (
    None
):
    questions = [
        question("input_source", "Where?", ("a", "b")),
        question("output_structure", "What?", ("a", "b")),
        question("deliverable", "Which?", ("a", "b")),
        question("quality_bar", "Who checks?", ("a", "b")),
        question("constraints", "Tone?", ("a", "b")),
    ]

    assert (
        rule.question_plan_problems(_three_open_blocking(), questions, first_round=True)
        == []
    )


def test_question_plan_problems_asks_for_five_when_only_the_blocking_three_are_asked() -> (
    None
):
    questions = [
        question(s, "Q?", ("a", "b"))
        for s in ("input_source", "output_structure", "deliverable")
    ]

    problems = rule.question_plan_problems(
        _three_open_blocking(), questions, first_round=True
    )

    assert len(problems) == 1 and problems[0].startswith("ask 5 questions")


def test_question_plan_problems_refuses_important_question_when_a_blocking_slot_is_left_out() -> (
    None
):
    questions = [
        question(s, "Q?", ("a", "b"))
        for s in (
            "input_source",
            "output_structure",
            "quality_bar",
            "constraints",
            "volume_scale",
        )
    ]

    problems = rule.question_plan_problems(
        _three_open_blocking(), questions, first_round=True
    )

    assert problems[0].startswith(
        "ask every open blocking slot before any important one"
    )


def test_question_plan_problems_needs_one_question_when_a_later_round_has_gaps() -> (
    None
):
    assert (
        rule.question_plan_problems(_three_open_blocking(), [], first_round=False) != []
    )
    assert (
        rule.question_plan_problems(
            _three_open_blocking(),
            [question("deliverable", "Q?", ("a", "b"))],
            first_round=False,
        )
        == []
    )


def test_order_questions_puts_writes_first_and_important_last() -> None:
    questions = [
        question(s, "Q?", ("a", "b"))
        for s in (
            "constraints",
            "human_approval_points",
            "input_variability",
            "write_destinations",
            "input_source",
        )
    ]

    assert [q["slot"] for q in rule.order_questions(questions)] == [
        "write_destinations",
        "input_variability",
        "human_approval_points",
        "input_source",
        "constraints",
    ]


# --- Answer text after a code (follow-up facts) -------------------------------------------


def _with_followup() -> list[dict[str, Any]]:
    q = question(
        "irreversible_actions",
        "Send it anywhere?",
        ("Only returned", "Also posted to Slack"),
    )
    q["options"][1].update(
        {
            "followup_text": "name the channel in your reply",
            "followup_slot": "write_destinations",
        }
    )
    return [question("input_source", "Where?", ("Jira", "Paste")), q]


def test_parse_answers_keeps_text_after_code_when_an_addendum_is_given() -> None:
    assert rule.parse_answers("1a 2b #release-notes", _with_followup()) == {
        0: (0, ""),
        1: (1, "#release-notes"),
    }


def test_parse_answers_returns_empty_text_when_codes_stand_alone() -> None:
    assert rule.parse_answers("1a, 2b.", _with_followup()) == {0: (0, ""), 1: (1, "")}


def test_apply_answers_fills_followup_slot_when_option_asks_for_one_more_fact() -> None:
    slots = IntakeBriefFactory.slots()

    merged, answered = rule.apply_answers(
        slots,
        _with_followup(),
        rule.parse_answers("1a 2b #release-notes", _with_followup()),
    )

    assert merged["irreversible_actions"]["value"] == "Also posted to Slack"
    assert merged["write_destinations"] == {
        "value": "#release-notes",
        "source": "user",
        "criticality": "blocking",
    }
    assert answered == {"input_source", "irreversible_actions", "write_destinations"}


def test_apply_answers_leaves_followup_slot_open_when_no_text_follows_the_code() -> (
    None
):
    merged, _ = rule.apply_answers(
        IntakeBriefFactory.slots(), _with_followup(), {1: (1, "")}
    )

    assert merged["write_destinations"]["source"] == "unknown"


def test_apply_answers_adds_free_text_to_value_when_option_has_no_followup() -> None:
    merged, _ = rule.apply_answers(
        IntakeBriefFactory.slots(), _with_followup(), {0: (0, "the ENG project")}
    )

    assert merged["input_source"]["value"] == "Jira; the ENG project"


def test_question_violations_requires_whether_form_when_no_write_is_named() -> None:
    where_what = question(
        "human_approval_points",
        "What should a person approve?",
        ("The final notes", "The drafts"),
    )

    problems = rule.question_violations(_filled(), [where_what])

    assert problems and "ask WHETHER a person reviews" in problems[0]


def test_question_violations_accepts_where_what_when_the_user_answer_named_a_write() -> (
    None
):
    slots = _slack_slots(
        irreversible_actions={
            "value": "Posts to Slack",
            "source": "user",
            "criticality": "blocking",
        }
    )
    where_what = question(
        "human_approval_points",
        "What should a person approve?",
        ("The final post", "The draft"),
    )

    assert rule.question_violations(slots, [where_what]) == []


def test_question_violations_ignores_assumed_write_when_choosing_the_form() -> None:
    slots = _slack_slots(
        irreversible_actions={
            "value": "Posts to Slack",
            "source": "assumed",
            "criticality": "blocking",
        }
    )
    whether = question(
        "human_approval_points", "Review first?", ("No review", "Review first")
    )

    assert rule.question_violations(slots, [whether]) == []


def test_missing_destination_followups_finds_write_options_and_skips_reads() -> None:
    q = question(
        "external_systems",
        "Where?",
        ("Returned in the run", "Also added as a Jira comment", "Also posted to Slack"),
    )
    q["options"][2].update(
        {"followup_text": "name the channel", "followup_slot": "write_destinations"}
    )
    reads = question(
        "external_systems", "From where?", ("Read from GitHub releases", "Pasted")
    )

    assert rule.missing_destination_followups([q, reads]) == [
        (0, 1, "name the Jira project or issue in your reply")
    ]


def test_drop_unavailable_write_clears_crm_write_when_a_feasibility_note_exists() -> (
    None
):
    slots = _slack_slots(
        irreversible_actions={
            "value": "Writes into the CRM",
            "source": "request",
            "criticality": "blocking",
        }
    )
    systems = frozenset({"slack", "jira", "github", "gitlab"})

    merged, changed = rule.drop_unavailable_write(
        slots, systems, has_feasibility_note=True
    )

    assert changed is True
    assert merged["irreversible_actions"]["source"] == "not_applicable"
    assert rule.write_is_named(merged) is False
    assert (
        rule.drop_unavailable_write(slots, systems, has_feasibility_note=False)[1]
        is False
    )


def test_drop_unavailable_write_keeps_write_to_an_available_system() -> None:
    merged, changed = rule.drop_unavailable_write(
        _slack_slots(), frozenset({"slack"}), has_feasibility_note=True
    )

    assert changed is False
    assert merged["irreversible_actions"]["value"] == "Posts the release notes to Slack"
