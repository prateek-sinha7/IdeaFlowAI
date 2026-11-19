"""Unit tests for ``tools/builder_eval/report.py`` on synthetic turn records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.builder_eval.report import render, spend, summarize


def _record(request: str, turn: int, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "request_id": request,
        "turn": turn,
        "draft_accepted": False,
        "intake_enabled": True,
        "prompt_version": "intake.v3:abc",
        "intake_questions": [],
        "usage": {"input": 1000, "output": 100},
        "intake_effort": "max",
        "critic_scores": {},
        "critic_status": None,
    }
    base.update(fields)
    return base


def _write(folder: Path, request: str, records: list[dict[str, Any]]) -> None:
    (folder / request).mkdir(parents=True)
    for r in records:
        (folder / request / f"turn{r['turn']}.json").write_text(
            json.dumps(r), encoding="utf-8"
        )


def test_summarize_reports_asked_first_build_class_and_critic_pass(
    tmp_path: Path,
) -> None:
    questions = [
        {"slot": "input_source", "criticality": "blocking"},
        {"slot": "constraints", "criticality": "important"},
    ]
    built = {
        "draft_accepted": True,
        "validator_verdict": "VALID",
        "prompt_version": "v1:x+intake.v3:y",
        "manifest_shape": {
            "root_steps": 3,
            "intake_step": False,
            "irreversible_steps": [{"step": "post", "gated": True}],
        },
        "critic_status": "ok",
        "critic_scores": {"prompt_depth": 5, "loop_caps": 4},
    }
    _write(
        tmp_path,
        "H1",
        [_record("H1", 1, intake_questions=questions), _record("H1", 2, **built)],
    )
    _write(
        tmp_path,
        "R3",
        [_record("R3", 1, **{**built, "critic_scores": {"prompt_depth": 3}})],
    )
    _write(
        tmp_path,
        "vague-c",
        [_record("vague-c", 1, draft_accepted=True, prompt_version="v1:only")],
    )

    summary = summarize(tmp_path, frozenset({"R3"}))

    assert summary["asked_first"] == (1, 2)
    assert summary["build_class_ok"] == (1, 1)
    assert summary["blocking_vs_important"] == (1, 1)
    assert summary["fallback"] == (1, 3)
    assert summary["valid"] == (2, 3)
    assert summary["irreversible_gated"] == (2, 2)
    assert summary["critic_pass"] == (1, 2)
    assert "| asked_first | 1/2 (50%) |" in render({"set": summary})


def test_spend_prices_each_record_at_its_own_models_rates() -> None:
    sonnet = [
        {
            "usage": {"input": 1_000_000, "output": 0},
            "critic_usage": [{"output_tokens": 100_000}],
        }
    ]
    haiku = [
        {
            "model_id": "eu.anthropic.claude-haiku-5-5",
            "usage": {"input": 1_000_000, "output": 0},
        }
    ]

    # estimate_cost_usd applies the platform's EU regional premium (x1.1).
    assert round(spend(sonnet), 2) == 3.3
    assert round(spend(haiku), 2) == 0.11


def test_summarize_counts_where_what_approval_asked_without_an_external_write(
    tmp_path: Path,
) -> None:
    built = {
        "draft_accepted": True,
        "manifest_shape": {},
        "prompt_version": "v1:x+intake.v3:y",
    }
    _write(
        tmp_path,
        "H1",
        [
            _record("H1", 1, approval_question_form="where_what"),
            _record("H1", 2, irreversible_action_after_intake=False, **built),
        ],
    )
    _write(
        tmp_path,
        "H2",
        [
            _record("H2", 1, approval_question_form="where_what"),
            _record("H2", 2, irreversible_action_after_intake=True, **built),
        ],
    )
    _write(
        tmp_path,
        "H3",
        [
            _record("H3", 1, approval_question_form="whether"),
            _record("H3", 2, irreversible_action_after_intake=False, **built),
        ],
    )

    summary = summarize(tmp_path)

    assert summary["approval_where_without_write"] == (1, 2)
    assert summary["approval_where_without_write_ids"] == ["H1"]


def test_summarize_excludes_infra_failures_from_every_denominator(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "H1",
        [
            _record(
                "H1",
                1,
                infra_failure="still failing after 3 retries (getaddrinfo failed)",
                transient_retries=["getaddrinfo failed"] * 3,
            )
        ],
    )
    _write(
        tmp_path,
        "H2",
        [
            _record(
                "H2",
                1,
                intake_questions=[{"slot": "input_source", "criticality": "blocking"}],
            )
        ],
    )

    summary = summarize(tmp_path)

    assert summary["infra_failures"] == (1, 2)
    assert summary["infra_failure_ids"] == ["H1"]
    assert summary["asked_first"] == (1, 1)
    assert summary["transient_retries"] == 3
