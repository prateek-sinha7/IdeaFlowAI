"""Unit tests for evals.grading.judge (task T5).

Offline only — no network, no real model. Covers the static 0-100 schema, id-keyed
sub-scores, the no-`score`/no-`passed` contract, and the hard failure on a judge
provider `build_model` cannot honour.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

import app.agents.model_factory
import app.core.config
from evals.grading import judge

RUBRIC_PATH = (
    Path(__file__).resolve().parents[2]
    / "evals/grading/model/workflows/prototype/prototype_specify_rubric.yaml"
)


@pytest.fixture(autouse=True)
def anthropic_credential(monkeypatch):
    """The real rubric pins provider `anthropic`, which needs a credential to resolve."""
    monkeypatch.setattr(app.core.config.settings, "ANTHROPIC_API_KEY", "sk-test")


@pytest.fixture
def rubric() -> dict:
    """The REAL prototype-specify rubric, loaded fresh per test."""
    return yaml.safe_load(RUBRIC_PATH.read_text())


class _FakeDimension:
    """Stand-in for one DimensionScore entry in a judge reply."""

    def __init__(self, id: str, score: int, evidence: str = "quoted"):
        self.id = id
        self.score = score
        self.evidence = evidence


class _FakeParsed:
    """Stand-in for a parsed JudgeOutput."""

    def __init__(self, dimensions, rationale="ok", strengths=None, weaknesses=None):
        self.dimensions = dimensions
        self.rationale = rationale
        self.strengths = strengths or []
        self.weaknesses = weaknesses or []


class _FakeRaw:
    """Stand-in for the raw AIMessage `include_raw=True` returns alongside the parse."""

    def __init__(self, tokens_in=0, tokens_out=0):
        self.usage_metadata = {"input_tokens": tokens_in, "output_tokens": tokens_out}


class _FakeStructured:
    """Structured-output wrapper that replays an `include_raw=True` reply or raises.

    Mirrors the real `{raw, parsed, parsing_error}` envelope, so the token
    capture and the parse-error path are exercised rather than stubbed past.
    """

    def __init__(self, parsed=None, raise_exc=None, parsing_error=None, raw=None):
        self._parsed = parsed
        self._raise_exc = raise_exc
        self._parsing_error = parsing_error
        self._raw = raw or _FakeRaw()

    async def ainvoke(self, _prompt):
        """Return the canned reply envelope, or raise the canned exception."""
        if self._raise_exc:
            raise self._raise_exc
        return {"raw": self._raw, "parsed": self._parsed, "parsing_error": self._parsing_error}


class _FakeModel:
    """Chat-model stand-in exposing model id + with_structured_output."""

    def __init__(self, structured, model="fake-judge-model"):
        self._structured = structured
        self.model = model

    def with_structured_output(self, _schema, **_kwargs):
        """Return the canned structured wrapper, ignoring the schema and flags."""
        return self._structured


def _patch_build_model(monkeypatch, model):
    """Make judge.resolve_judge_model return the given fake model."""
    monkeypatch.setattr(
        app.agents.model_factory, "build_model", lambda m=None, **kwargs: model
    )


def _patch_settings(monkeypatch, **values):
    """Override credential fields on the shared settings object."""
    for name, value in values.items():
        monkeypatch.setattr(app.core.config.settings, name, value)


def _grade_kwargs(rubric: dict) -> dict:
    """The non-response arguments every grade() call needs."""
    return dict(
        rubric=rubric,
        system_prompt="SYSTEM_PROMPT_MARKER",
        prompt="USER_PROMPT_MARKER",
        precheck_reason="PRECHECK_MARKER",
    )


@pytest.mark.asyncio
async def test_well_formed_reply_maps_to_sub_scores_keyed_by_id(monkeypatch, rubric):
    parsed = _FakeParsed(
        [
            _FakeDimension("data_realism", 88, "invoice INV-2291"),
            _FakeDimension("brief_intent_match", 74, "the triage page"),
            _FakeDimension("design_system_coherence", 61, "the .ops-grid class"),
        ],
        rationale="specific rationale",
        strengths=["real invoice ids"],
        weaknesses=["thin settings page"],
    )
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured(parsed=parsed)))

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is False
    assert verdict.sub_scores == {
        "data_realism": 88,
        "brief_intent_match": 74,
        "design_system_coherence": 61,
    }
    assert verdict.evidence["data_realism"] == "invoice INV-2291"
    assert verdict.rationale == "specific rationale"
    assert verdict.strengths == ["real invoice ids"]
    assert verdict.weaknesses == ["thin settings page"]
    assert verdict.resolved_model_id == "fake-judge-model"


@pytest.mark.asyncio
async def test_dimensions_out_of_order_still_map_correctly(monkeypatch, rubric):
    """Proves keying by id, not by list index — ordering is not guaranteed."""
    parsed = _FakeParsed(
        [
            _FakeDimension("design_system_coherence", 61),
            _FakeDimension("data_realism", 88),
            _FakeDimension("brief_intent_match", 74),
        ]
    )
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured(parsed=parsed)))

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is False
    assert verdict.sub_scores == {
        "data_realism": 88,
        "brief_intent_match": 74,
        "design_system_coherence": 61,
    }


@pytest.mark.asyncio
async def test_missing_dimension_id_gives_errored_verdict_naming_it(monkeypatch, rubric):
    parsed = _FakeParsed(
        [_FakeDimension("data_realism", 88), _FakeDimension("brief_intent_match", 74)]
    )
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured(parsed=parsed)))

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is True
    assert "design_system_coherence" in verdict.error_reason
    assert "missing" in verdict.error_reason
    assert verdict.sub_scores == {}


@pytest.mark.asyncio
async def test_unknown_dimension_id_gives_errored_verdict_naming_it(monkeypatch, rubric):
    parsed = _FakeParsed(
        [
            _FakeDimension("data_realism", 88),
            _FakeDimension("brief_intent_match", 74),
            _FakeDimension("design_system_coherence", 61),
            _FakeDimension("tone_of_voice", 50),
        ]
    )
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured(parsed=parsed)))

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is True
    assert "tone_of_voice" in verdict.error_reason
    assert "unexpected" in verdict.error_reason


def test_verdict_has_no_score_and_no_passed():
    """Contract guard: the weighted total and the threshold live in scoring.py."""
    verdict = judge.JudgeVerdict()
    assert not hasattr(verdict, "score")
    assert not hasattr(verdict, "passed")
    assert "score" not in judge.JudgeVerdict.__dataclass_fields__
    assert "passed" not in judge.JudgeVerdict.__dataclass_fields__


@pytest.mark.asyncio
async def test_changing_a_dimension_weight_does_not_cause_an_error(monkeypatch, rubric):
    """Weights are not in the schema: 35 with weight 20 must still validate."""
    edited = copy.deepcopy(rubric)
    edited["dimensions"][0]["weight"] = 20
    parsed = _FakeParsed(
        [
            _FakeDimension("data_realism", 35),
            _FakeDimension("brief_intent_match", 74),
            _FakeDimension("design_system_coherence", 61),
        ]
    )
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured(parsed=parsed)))

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(edited))

    assert verdict.errored is False
    assert verdict.sub_scores["data_realism"] == 35


def test_dimension_score_schema_is_static_zero_to_hundred():
    """Every dimension is bounded 0-100, never by its rubric weight."""
    field = judge.DimensionScore.model_fields["score"]
    bounds = {type(m).__name__: getattr(m, "ge", getattr(m, "le", None)) for m in field.metadata}
    assert bounds == {"Ge": 0, "Le": 100}


def test_resolve_judge_model_raises_for_anthropic_without_credential(monkeypatch):
    _patch_settings(monkeypatch, ANTHROPIC_API_KEY="")
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured()))

    with pytest.raises(judge.JudgeConfigurationError) as excinfo:
        judge.resolve_judge_model({"provider": "anthropic", "model": "claude-sonnet-5"})

    assert "anthropic" in str(excinfo.value)


def test_resolve_judge_model_raises_for_bogus_provider(monkeypatch):
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured()))

    with pytest.raises(judge.JudgeConfigurationError) as excinfo:
        judge.resolve_judge_model({"provider": "openai", "model": "gpt-x"})

    assert "openai" in str(excinfo.value)


def test_resolve_judge_model_accepts_anthropic_with_credential(monkeypatch):
    _patch_settings(monkeypatch, ANTHROPIC_API_KEY="sk-test")
    model = _FakeModel(_FakeStructured())
    _patch_build_model(monkeypatch, model)

    assert judge.resolve_judge_model({"provider": "anthropic"}) is model


def test_resolve_judge_model_raises_for_mistral_without_credential(monkeypatch):
    _patch_settings(monkeypatch, MISTRAL_API_KEY="")
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured()))

    with pytest.raises(judge.JudgeConfigurationError):
        judge.resolve_judge_model({"provider": "mistral"})


@pytest.mark.asyncio
async def test_model_exception_returns_errored_verdict_not_raise(monkeypatch, rubric):
    _patch_build_model(
        monkeypatch,
        _FakeModel(_FakeStructured(raise_exc=ConnectionError("network down"))),
    )

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is True
    assert "network down" in verdict.error_reason
    assert verdict.sub_scores == {}


@pytest.mark.asyncio
async def test_resolved_model_id_is_captured_on_an_errored_verdict(monkeypatch, rubric):
    _patch_build_model(
        monkeypatch,
        _FakeModel(_FakeStructured(raise_exc=ValueError("parse failed")), model="judge-v9"),
    )

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is True
    assert verdict.resolved_model_id == "judge-v9"


def test_build_judge_prompt_includes_prompt_dimensions_anchors_and_precheck(rubric):
    prompt = judge.build_judge_prompt(
        system_prompt="SYSTEM_PROMPT_MARKER",
        prompt="USER_PROMPT_MARKER",
        response="RESPONSE_MARKER",
        rubric=rubric,
        precheck_reason="PRECHECK_MARKER",
    )

    for marker in (
        "SYSTEM_PROMPT_MARKER",
        "USER_PROMPT_MARKER",
        "RESPONSE_MARKER",
        "PRECHECK_MARKER",
        "data_realism",
        "brief_intent_match",
        "design_system_coherence",
    ):
        assert marker in prompt
    for band in ("90", "70", "50", "30"):
        assert f"- {band}:" in prompt
    assert "Data a domain practitioner would accept as a real export." in prompt


# ── narrative salvage (regression: run 260729-173145) ──────────────────────
#
# mistral-large returned every rationale/strengths/weaknesses INSIDE the
# dimension entries. JudgeOutput required them at the top level, so both rows
# failed validation and a paid-for run reported zero scores.


def test_judge_output_lifts_narrative_nested_inside_dimensions():
    parsed = judge.JudgeOutput.model_validate(
        {
            "dimensions": [
                {
                    "id": "data_realism",
                    "score": 85,
                    "evidence": "Invoice table shows ACME Corp $12,480.00",
                    "strengths": ["plausible amounts"],
                    "weaknesses": ["few edge cases"],
                },
                {
                    "id": "brief_intent_match",
                    "score": 90,
                    "evidence": "covers failed-payment recovery",
                    "rationale": "Matches the brief well.",
                    "weaknesses": ["few edge cases"],
                },
            ]
        }
    )

    assert {d.id: d.score for d in parsed.dimensions} == {
        "data_realism": 85,
        "brief_intent_match": 90,
    }
    assert parsed.rationale == "Matches the brief well."
    assert parsed.strengths == ["plausible amounts"]
    assert parsed.weaknesses == ["few edge cases"], "duplicates across dimensions collapse"


def test_judge_output_prefers_top_level_narrative_over_nested():
    parsed = judge.JudgeOutput.model_validate(
        {
            "dimensions": [
                {"id": "a", "score": 1, "evidence": "e", "weaknesses": ["nested"]}
            ],
            "rationale": "top",
            "strengths": ["top-s"],
            "weaknesses": ["top-w"],
        }
    )

    assert parsed.rationale == "top"
    assert parsed.strengths == ["top-s"]
    assert parsed.weaknesses == ["top-w"]


def test_judge_output_accepts_scores_with_no_narrative_anywhere():
    parsed = judge.JudgeOutput.model_validate(
        {"dimensions": [{"id": "a", "score": 42, "evidence": "e"}]}
    )

    assert parsed.dimensions[0].score == 42
    assert (parsed.rationale, parsed.strengths, parsed.weaknesses) == ("", [], [])


def test_judge_prompt_demands_top_level_narrative_fields():
    prompt = judge.build_judge_prompt(
        system_prompt="s", prompt="p", response="r", rubric={}, precheck_reason="ok"
    )

    assert "TOP LEVEL" in prompt
    assert "NOT inside the dimension" in prompt


# ── judge token capture ────────────────────────────────────────────────────
#
# The judge's own spend used to be invisible: every report counted agent tokens
# only, so a judged run under-reported its cost by roughly half.


@pytest.mark.asyncio
async def test_verdict_carries_the_judges_own_token_usage(monkeypatch, rubric):
    parsed = _FakeParsed(
        [
            _FakeDimension("data_realism", 80),
            _FakeDimension("brief_intent_match", 70),
            _FakeDimension("design_system_coherence", 60),
        ]
    )
    _patch_build_model(
        monkeypatch,
        _FakeModel(_FakeStructured(parsed, raw=_FakeRaw(tokens_in=4100, tokens_out=830))),
    )

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is False
    assert (verdict.tokens_in, verdict.tokens_out) == (4100, 830)


@pytest.mark.asyncio
async def test_a_failed_parse_still_reports_the_tokens_it_burned(monkeypatch, rubric):
    """The whole point: a judge call that produced nothing still cost money."""
    _patch_build_model(
        monkeypatch,
        _FakeModel(
            _FakeStructured(
                parsed=None,
                parsing_error="3 validation errors for JudgeOutput",
                raw=_FakeRaw(tokens_in=4100, tokens_out=120),
            )
        ),
    )

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is True
    assert "3 validation errors" in str(verdict.error_reason)
    assert (verdict.tokens_in, verdict.tokens_out) == (4100, 120)


@pytest.mark.asyncio
async def test_a_wrapper_returning_the_parse_directly_still_works(monkeypatch, rubric):
    """Tolerating the bare shape keeps token capture from costing us verdicts."""

    class _BareStructured:
        async def ainvoke(self, _prompt):
            return _FakeParsed(
                [
                    _FakeDimension("data_realism", 50),
                    _FakeDimension("brief_intent_match", 50),
                    _FakeDimension("design_system_coherence", 50),
                ]
            )

    _patch_build_model(monkeypatch, _FakeModel(_BareStructured()))

    verdict = await judge.grade("<spec>...</spec>", **_grade_kwargs(rubric))

    assert verdict.errored is False
    assert verdict.sub_scores == {
        "data_realism": 50,
        "brief_intent_match": 50,
        "design_system_coherence": 50,
    }
    assert (verdict.tokens_in, verdict.tokens_out) == (0, 0)


def test_evidence_accepts_a_list_of_quotes(rubric):
    """A judge citing three places in a 16k HTML file is doing its job well.

    Requiring exactly one string threw away the whole verdict — scores
    included — over how the quotes happened to be packaged.
    """
    parsed = judge.JudgeOutput.model_validate(
        {
            "dimensions": [
                {"id": "a", "score": 85, "evidence": ["Dashboard grid", "Low stock table"]},
                {"id": "b", "score": 90, "evidence": "a single quote still works"},
                {"id": "c", "score": 70, "evidence": []},
            ]
        }
    )

    assert parsed.dimensions[0].evidence == "Dashboard grid · Low stock table"
    assert parsed.dimensions[1].evidence == "a single quote still works"
    assert parsed.dimensions[2].evidence == ""
    assert [d.score for d in parsed.dimensions] == [85, 90, 70], "scores survive"
