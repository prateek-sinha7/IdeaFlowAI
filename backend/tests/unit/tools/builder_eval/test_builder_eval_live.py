"""Unit tests for the live eval harness's pure helpers (no model, no turn)."""

from __future__ import annotations

from typing import Any

from tools.builder_eval.builder_eval_live import (
    answer_codes,
    count_questions,
    manifest_shape,
    shape_diff,
)

_Q: list[dict[str, Any]] = [
    {
        "slot": "input_variability",
        "options": ["Digital only", "Some scans: add OCR", "Not sure - use default"],
        "recommended_flags": [True, False, False],
    },
    {
        "slot": "human_approval_points",
        "options": ["No review", "Yes, review first", "Not sure - use default"],
        "recommended_flags": [True, False, False],
    },
    {
        "slot": "volume_scale",
        "options": ["One file", "Many files", "Not sure - use default"],
        "recommended_flags": [True, False, False],
    },
]


def test_answer_codes_uses_the_planned_letter_and_recommended_otherwise() -> None:
    plan = {"input_variability": "b", "human_approval_points": "B"}

    assert answer_codes(_Q, plan) == "1b 2b 3a"


def test_answer_codes_falls_back_to_recommended_when_letter_does_not_exist() -> None:
    assert answer_codes(_Q, {"input_variability": "f"}) == "1a 2a 3a"


def _step(instance_id: str, **fields: Any) -> dict[str, Any]:
    return {"agent": "custom-agent", "instance_id": instance_id, **fields}


def test_manifest_shape_reports_gate_before_slack_post_when_previous_step_has_human_gate() -> (
    None
):
    manifest = {
        "deliverable": {"strategy": "streamed_text"},
        "steps": [
            _step("draft", gates=["human"]),
            _step(
                "post",
                depends_on=["custom-agent:draft"],
                tools={"mcp": ["slack.post_message"]},
            ),
        ],
    }

    shape = manifest_shape(manifest)

    assert shape["irreversible_steps"] == [{"step": "post", "gated": True}]
    assert shape["human_gates"] == 1


def test_manifest_shape_reports_ungated_post_when_no_gate_precedes_it() -> None:
    manifest = {"steps": [_step("post", tools={"mcp": ["slack.post_message"]})]}

    assert manifest_shape(manifest)["irreversible_steps"] == [
        {"step": "post", "gated": False}
    ]


def test_shape_diff_lists_added_features_when_shapes_differ() -> None:
    base = {
        "root_steps": 2,
        "human_gates": 0,
        "deliverable": "single_file",
        "fan_out": False,
        "ocr": False,
    }
    other = {
        "root_steps": 4,
        "human_gates": 1,
        "deliverable": "serialized_sandbox",
        "fan_out": True,
        "ocr": True,
    }

    assert shape_diff(base, other) == (
        "+ fan out, + ocr, root steps 2 -> 4, human gates 0 -> 1, "
        "deliverable single_file -> serialized_sandbox"
    )


def test_shape_diff_says_no_change_when_shapes_match() -> None:
    shape = {"root_steps": 2, "human_gates": 0}

    assert shape_diff(shape, dict(shape)) == "no shape change"


def test_count_questions_counts_numbered_questions_and_lettered_options() -> None:
    reply = (
        "1. Where?\n   - a) Upload (recommended)\n   - b) Paste\n2. Scans?\n   - a) No"
    )

    assert count_questions(reply)[0] == 2
    assert count_questions(reply)[2] == 3


def test_answer_codes_picks_followup_option_and_adds_default_text_when_asked() -> None:
    questions = [
        {
            "slot": "irreversible_actions",
            "options": ["Only returned", "Also posted to Slack", "Not sure"],
            "recommended_flags": [True, False, False],
            "followups": {
                "1": {"text": "name the channel", "slot": "write_destinations"}
            },
        }
    ]

    assert (
        answer_codes(
            questions, {"_prefer_followup": True, "_followup_default": "#eng-status"}
        )
        == "1b #eng-status"
    )
    assert answer_codes(questions, {"irreversible_actions": "b #ops"}) == "1b #ops"


def test_is_transient_follows_the_cause_chain() -> None:
    from tools.builder_eval.builder_eval_live import is_transient

    try:
        try:
            raise ConnectionResetError(
                10054, "An existing connection was forcibly closed"
            )
        except ConnectionResetError as inner:
            raise RuntimeError("stream failed") from inner
    except RuntimeError as outer:
        assert is_transient(outer) is True
    assert is_transient(ValueError("bad JSON")) is False


async def test_retrying_retries_transient_errors_then_returns(monkeypatch: Any) -> None:
    import tools.builder_eval.builder_eval_live as live_mod

    monkeypatch.setattr(live_mod, "_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("getaddrinfo failed")
        return "ok"

    seen: list[str] = []
    assert await live_mod._retrying(flaky, seen)() == "ok"
    assert seen == ["OSError", "OSError"]


def test_turn_record_persists_critic_status_and_infra_fields() -> None:
    from tools.builder_eval.builder_eval_live import TurnRecord

    names = set(TurnRecord.__dataclass_fields__)

    assert {
        "critic_status",
        "critic_model",
        "infra_failure",
        "transient_retries",
        "intake_failure",
    } <= names


def test_transient_log_keeps_error_text_without_local_paths_when_an_error_is_logged() -> (
    None
):
    import logging

    from tools.builder_eval.builder_eval_live import _TransientLog

    log = _TransientLog()
    log.emit(
        logging.LogRecord("x", logging.WARNING, __file__, 1, "intake retry", None, None)
    )
    log.emit(
        logging.LogRecord(
            "x",
            logging.ERROR,
            __file__,
            1,
            r"runner failed at C:\Users\someone\proj\a.py: boom",
            None,
            None,
        )
    )

    assert log.errors == ["runner failed at <path> boom"]
