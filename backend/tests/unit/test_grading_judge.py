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
from evals.grading.model import judge

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

    def __init__(self, id: str, score: int, evidence: str = "quoted", weaknesses=None,
                 findings=None):
        self.id = id
        self.score = score
        self.evidence = evidence
        self.strengths = []
        self.weaknesses = weaknesses or []
        # Mirrors DimensionScore's reconciliation so a double built from the
        # legacy shape behaves like the real model rather than diverging from it.
        self.findings = findings or [
            judge.Finding(severity="major", detail=text)
            for text in self.weaknesses
            if str(text).strip()
        ]
        self.severity_fallback = bool(self.findings) and findings is None


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
    for band in ("95", "85", "70", "50", "30"):
        assert f"- {band}:" in prompt
    assert "Data a domain practitioner would accept as a real export." in prompt
    # The scoring-discipline contract: the prompt must state how findings turn
    # into deductions, so the judge knows a nit is cheap and a blocking finding
    # is not — and must NOT ask it to be stingy in the abstract, which is what
    # made 84 the effective ceiling for any thoroughly-inspected artifact.
    assert "SCORING DISCIPLINE" in prompt
    assert "PRICED IN CODE" in prompt
    assert "caps the dimension at 45" in prompt
    assert "capped at 84" not in prompt, "the count-based cap no longer exists"
    assert "should be rare" not in prompt, "stinginess is enforced by severity now"


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


def test_scores_follow_finding_severity_not_finding_count():
    """Replaces the count-based cap test (spec 008 T5).

    The old table charged 84 for one weakness and 74 for two whatever they said.
    These four dimensions carry the SAME counts as before and now price by what
    the findings actually are.
    """
    dims = [
        judge.DimensionScore(id="clean", score=95, evidence="q"),
        judge.DimensionScore(
            id="one_nit", score=95, evidence="q",
            findings=[judge.Finding(severity="minor",
                                    detail="labels are 11.5px, body is 14px")],
        ),
        judge.DimensionScore(
            id="one_real_gap", score=95, evidence="q",
            findings=[judge.Finding(severity="major",
                                    detail="table has three rows, brief asked five")],
        ),
        judge.DimensionScore(
            id="broken", score=90, evidence="q",
            findings=[judge.Finding(severity="blocking",
                                    detail="the detail page renders nothing")],
        ),
    ]
    sub_scores, caps = judge._capped_sub_scores(dims)

    assert sub_scores == {"clean": 95, "one_nit": 94, "one_real_gap": 87, "broken": 45}
    # Under the old table one_nit and one_real_gap were BOTH 84. That collapse is
    # the defect this spec exists to fix.
    assert sub_scores["one_nit"] > sub_scores["one_real_gap"] > sub_scores["broken"]
    assert caps["broken"]["blocking_cap_applied"] is True
    assert caps["clean"]["final"] == 95


# ── T1: severity-tagged findings (spec 008-grading-calibration) ───────────
#
# SCORE-NEUTRAL BY DESIGN. This slice introduces the vocabulary only; the
# pricing that consumes it lands in T4/T5. If a score moves here, something is
# wrong — which is what test_findings_do_not_change_any_score asserts.


def test_finding_accepts_the_three_severities():
    """The severity vocabulary is closed: blocking, major, minor — nothing else."""
    for severity in ("blocking", "major", "minor"):
        finding = judge.Finding(severity=severity, detail="the detail page is empty")
        assert finding.severity == severity

    with pytest.raises(Exception):
        judge.Finding(severity="critical", detail="not a permitted severity")


def test_finding_rejects_an_empty_detail():
    """A finding with no text is not a finding — it cannot be priced or audited."""
    for blank in ("", "   ", "\n\t "):
        with pytest.raises(Exception):
            judge.Finding(severity="minor", detail=blank)


def test_findings_populate_weaknesses_so_every_existing_reader_keeps_working():
    """`weaknesses` stays a list[str] — scoring, reports and clustering read it."""
    dimension = judge.DimensionScore(
        id="data_realism",
        score=92,
        evidence="the 1,800 TPS metric",
        findings=[
            judge.Finding(severity="minor", detail="node labels are 11.5px, body is 14px"),
            judge.Finding(severity="major", detail="the detail page has no records"),
        ],
    )

    assert dimension.weaknesses == [
        "node labels are 11.5px, body is 14px",
        "the detail page has no records",
    ]
    assert all(isinstance(text, str) for text in dimension.weaknesses)


def test_explicit_weaknesses_are_not_overwritten_by_the_sync():
    """A judge that sent only `weaknesses` keeps them verbatim."""
    dimension = judge.DimensionScore(
        id="page_completeness", score=84, evidence="q", weaknesses=["thin settings page"]
    )
    assert dimension.weaknesses == ["thin settings page"]


def test_the_two_shapes_price_identically_for_the_same_severities():
    """Which shape the judge answered in must never change the number.

    Written as T1's score-neutrality guard while the count-based cap was still
    in place; since T5 the equivalence is severity-based, which is the stronger
    property — the legacy list lifts to `major`, so the comparison must too.
    """
    via_findings = judge.DimensionScore(
        id="d", score=92, evidence="q",
        findings=[
            judge.Finding(severity="major", detail="first"),
            judge.Finding(severity="major", detail="second"),
        ],
    )
    via_weaknesses = judge.DimensionScore(
        id="d", score=92, evidence="q", weaknesses=["first", "second"]
    )

    assert judge._capped_sub_scores([via_findings])[0] == \
           judge._capped_sub_scores([via_weaknesses])[0] == {"d": 92 - 16}


def test_judge_prompt_defines_every_severity(rubric):
    """The prompt and the schema must use the same words, or severity is noise."""
    prompt = judge.build_judge_prompt(
        system_prompt="sys", prompt="brief", response="<html>",
        rubric=rubric, precheck_reason="clean",
    )

    lowered = prompt.lower()
    assert "blocking" in lowered and "major" in lowered and "minor" in lowered
    assert "refuse to ship" in lowered, "the blocking definition must be stated"
    assert "not a defect" in lowered, "the minor definition must be stated"
    # The schema's Literal and the prompt's wording are one contract.
    assert judge.SEVERITY_GUIDANCE in prompt


# ── T2/T3: legacy-shape fallback and verdict carriage ─────────────────────


def test_legacy_weaknesses_lift_to_major_findings():
    """A judge that never heard of severity still produces priceable findings.

    Untagged is treated as `major` — strict but not fatal. It costs points and
    can never force a fail, so a schema miss degrades a score rather than
    inventing a blocking defect that was never reported.
    """
    dimension = judge.DimensionScore(
        id="d", score=90, evidence="q", weaknesses=["no empty state", "generic names"]
    )

    assert [f.severity for f in dimension.findings] == ["major", "major"]
    assert [f.detail for f in dimension.findings] == ["no empty state", "generic names"]
    assert dimension.severity_fallback is True


def test_findings_win_when_a_judge_sends_both_shapes():
    """Both shapes present means the judge answered properly — do not double-count."""
    dimension = judge.DimensionScore(
        id="d", score=90, evidence="q",
        weaknesses=["stale copy of the same complaint"],
        findings=[judge.Finding(severity="minor", detail="the real, tagged one")],
    )

    assert len(dimension.findings) == 1
    assert dimension.findings[0].severity == "minor"
    assert dimension.severity_fallback is False


def test_a_dimension_with_neither_shape_is_clean():
    """No complaints is a real answer, not a parse failure."""
    dimension = judge.DimensionScore(id="d", score=97, evidence="q")
    assert dimension.findings == []
    assert dimension.weaknesses == []
    assert dimension.severity_fallback is False


def test_blank_legacy_weaknesses_are_dropped_not_raised():
    """An empty string in a legacy list must not kill the whole verdict."""
    dimension = judge.DimensionScore(
        id="d", score=90, evidence="q", weaknesses=["real complaint", "   ", ""]
    )
    assert [f.detail for f in dimension.findings] == ["real complaint"]


@pytest.mark.asyncio
async def test_verdict_carries_findings_and_counts_fallbacks(monkeypatch, rubric):
    """The verdict records findings verbatim so a reduced score stays auditable."""
    parsed = judge.JudgeOutput(
        dimensions=[
            judge.DimensionScore(
                id="data_realism", score=92, evidence="q",
                findings=[judge.Finding(severity="minor", detail="labels are 11.5px")],
            ),
            judge.DimensionScore(
                id="brief_intent_match", score=88, evidence="q",
                weaknesses=["settings page is generic"],
            ),
            judge.DimensionScore(id="design_system_coherence", score=95, evidence="q"),
        ]
    )
    _patch_build_model(monkeypatch, _FakeModel(_FakeStructured(parsed=parsed)))

    verdict = await judge.grade("<spec/>", **_grade_kwargs(rubric))

    assert verdict.dimension_findings["data_realism"] == [
        {"severity": "minor", "detail": "labels are 11.5px"}
    ]
    assert verdict.dimension_findings["brief_intent_match"][0]["severity"] == "major"
    assert "design_system_coherence" not in verdict.dimension_findings
    assert verdict.severity_fallbacks == 1, "one dimension answered in the legacy shape"
    assert verdict.dimension_weaknesses["brief_intent_match"] == ["settings page is generic"]


@pytest.mark.asyncio
async def test_an_errored_verdict_still_reports_its_token_cost(monkeypatch, rubric):
    """A judge call that failed to parse still spent tokens — hiding them understates spend."""
    structured = _FakeStructured(parsing_error="malformed", raw=_FakeRaw(120, 45))
    _patch_build_model(monkeypatch, _FakeModel(structured))

    verdict = await judge.grade("<spec/>", **_grade_kwargs(rubric))

    assert verdict.errored is True
    assert (verdict.tokens_in, verdict.tokens_out) == (120, 45)
    assert verdict.severity_fallbacks == 0


# ── T4/T5: severity pricing replaces count-based caps ─────────────────────


def _f(severity: str, n: int = 1):
    """`n` findings of one severity, each with distinct text."""
    return [judge.Finding(severity=severity, detail=f"{severity} finding {i}") for i in range(n)]


@pytest.mark.parametrize(
    "findings, expected, why",
    [
        ([], 95, "nothing found — the judge's number stands"),
        (_f("minor", 4), 91, "four nits cost the -4 floor"),
        (_f("minor", 8), 91, "nits cannot compound into a failure"),
        (_f("major", 1), 87, "one real gap costs 8"),
        (_f("major", 2), 79, "two cost 16"),
        (_f("blocking", 1), 45, "a must-fix defect is a failing dimension"),
        (_f("blocking", 2), 45, "still capped, and priced lower before the cap"),
        (_f("blocking", 1) + _f("major", 1), 45, "a blocking finding dominates"),
    ],
)
def test_price_findings_matches_the_designed_table(findings, expected, why):
    """Every row of design.md's severity->outcome table, priced from 95."""
    assert judge.price_findings(95, findings)[0] == expected, why


def test_pricing_is_monotonic_and_clamped():
    """Adding a finding may never raise a score, and nothing leaves 0..100."""
    previous = judge.price_findings(100, [])[0]
    for count in range(1, 6):
        current = judge.price_findings(100, _f("major", count))[0]
        assert current <= previous, "adding a finding raised the score"
        previous = current

    assert judge.price_findings(3, _f("major", 5))[0] == 0, "floored at 0"
    assert judge.price_findings(100, [])[0] == 100, "ceiled at 100"


def test_two_blockings_price_below_one_before_the_cap():
    """The cap applies AFTER penalties, so severity still accumulates underneath."""
    one = judge.price_findings(95, _f("blocking", 1))[1]
    two = judge.price_findings(95, _f("blocking", 2))[1]
    assert two["severe_penalty"] > one["severe_penalty"]
    assert one["blocking_cap_applied"] is two["blocking_cap_applied"] is True


def test_the_breakdown_explains_every_deduction():
    """A capped score that cannot be explained is a mystery, not a grade."""
    score, breakdown = judge.price_findings(
        92, _f("major", 1) + _f("minor", 3)
    )
    assert score == 92 - 8 - 3
    assert breakdown["severe"] == 1
    assert breakdown["minor"] == 3
    assert breakdown["severe_penalty"] == 8
    assert breakdown["minor_penalty"] == 3
    assert breakdown["blocking_cap_applied"] is False


def test_the_old_count_based_cap_is_gone():
    """Counting was the wrong operation — no caller may resurrect it."""
    assert not hasattr(judge, "consistency_cap")
    assert not hasattr(judge, "CONSISTENCY_CAPS")
    assert not hasattr(judge, "CONSISTENCY_CAP_FLOOR")


def test_score_caps_records_every_dimension_not_only_reduced_ones():
    """An absent entry used to be indistinguishable from 'not recorded'."""
    dims = [
        judge.DimensionScore(id="clean", score=95, evidence="q"),
        judge.DimensionScore(id="nitpicked", score=98, evidence="q",
                             findings=_f("minor", 2)),
        judge.DimensionScore(id="broken", score=90, evidence="q",
                             findings=_f("blocking", 1)),
    ]
    sub_scores, caps = judge._capped_sub_scores(dims)

    assert sub_scores == {"clean": 95, "nitpicked": 96, "broken": 45}
    assert set(caps) == {"clean", "nitpicked", "broken"}, "every dimension is recorded"
    assert caps["clean"]["reported"] == caps["clean"]["final"] == 95
    assert caps["broken"]["blocking_cap_applied"] is True
    assert caps["nitpicked"]["findings"] == [
        {"severity": "minor", "detail": "minor finding 0"},
        {"severity": "minor", "detail": "minor finding 1"},
    ]


# ── T6: the golden replay (spec 008-grading-calibration) ──────────────────
#
# The executable form of the whole spec, and free: no model, no network.
# `golden/calibration/top/mission_control.verdict.json` freezes what the OLD
# scale did to a hand-verified artifact that scores 100 on the code track —
# 11 of its 15 dimensions capped by cosmetic remarks, dropping a judge-reported
# mean of 94.51 to a recorded 85.15. Re-pricing that stored verdict is what
# proves the new scale recovers it, and what stops a future cap-table edit
# quietly re-breaking it.

GOLDEN_VERDICT_PATH = (
    Path(__file__).resolve().parents[2]
    / "evals/grading/model/workflows/prototype/golden/calibration/top"
    / "mission_control.verdict.json"
)


@pytest.fixture
def golden_verdict() -> dict:
    """The frozen golden verdict. A MISSING fixture must fail, never skip."""
    import json

    assert GOLDEN_VERDICT_PATH.exists(), (
        f"the calibration fixture is missing at {GOLDEN_VERDICT_PATH}. It was "
        "extracted from a gitignored .runs/ folder precisely because it is the "
        "only durable evidence for this spec — restore it, do not skip this test."
    )
    return json.loads(GOLDEN_VERDICT_PATH.read_text(encoding="utf-8"))


def _replay_stage(stage: dict) -> float:
    """Re-price one frozen stage under the current scale, returning its total."""
    total = 0.0
    for dimension_id, weight in stage["weights"].items():
        findings = [
            judge.Finding(severity="minor", detail=detail)
            for detail in stage["findings_by_dimension"].get(dimension_id, [])
        ]
        scored, _ = judge.price_findings(stage["judge_reported"][dimension_id], findings)
        total += scored * weight
    return total / 100.0


def test_the_golden_recovers_under_severity_pricing(golden_verdict):
    """Every stage rises, none exceeds what the judge actually said, mean >= 93."""
    replayed = {name: _replay_stage(stage) for name, stage in golden_verdict["stages"].items()}

    for name, stage in golden_verdict["stages"].items():
        assert replayed[name] > stage["capped_total"], (
            f"{name} did not recover: {replayed[name]:.2f} <= {stage['capped_total']}"
        )
        assert replayed[name] <= stage["reported_total"] + 1e-9, (
            f"{name} exceeded the judge's own number — pricing may only subtract"
        )

    mean = sum(replayed.values()) / len(replayed)
    assert golden_verdict["headline"]["mean_capped_total"] == pytest.approx(85.15, abs=0.01)
    assert mean >= 93, f"golden mean only recovered to {mean:.2f}, expected >= 93"


def test_no_golden_dimension_is_capped_any_more(golden_verdict):
    """11 of 15 dimensions were capped, and not one by a real defect."""
    assert golden_verdict["headline"]["dimensions_capped"] == 11
    assert golden_verdict["headline"]["dimensions_total"] == 15

    still_capped = 0
    for stage in golden_verdict["stages"].values():
        for dimension_id, reported in stage["judge_reported"].items():
            findings = [
                judge.Finding(severity="minor", detail=detail)
                for detail in stage["findings_by_dimension"].get(dimension_id, [])
            ]
            scored, breakdown = judge.price_findings(reported, findings)
            assert breakdown["blocking_cap_applied"] is False
            # Nits may shade a score by at most the minor floor; nothing more.
            assert reported - scored <= judge.MINOR_FLOOR
            if reported - scored > judge.MINOR_FLOOR:
                still_capped += 1

    assert still_capped == 0


# ── T9: every rubric teaches the same severity vocabulary ─────────────────

WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2] / "evals/grading/model/workflows/prototype"
)


@pytest.mark.parametrize(
    "stage",
    ["specify", "plan", "analyze", "build", "validate"],
)
def test_every_rubric_carries_the_findings_instruction(stage):
    """A judge told to tag severities must be told what the tags mean, everywhere.

    If one stage's rubric omits it, that stage's findings are tagged on an
    invented meaning and its scores stop being comparable to the others' — which
    is the whole reason the five rubrics share one judge in the first place.
    """
    rubric = yaml.safe_load(
        (WORKFLOW_DIR / f"prototype_{stage}_rubric.yaml").read_text(encoding="utf-8")
    )

    assert "REPORTING FINDINGS" in rubric["rubric"]
    for severity in ("blocking", "major", "minor"):
        assert severity in rubric["rubric"], f"{stage} never names `{severity}`"
    assert "do not\n  pre-deduct" in rubric["rubric"].replace("\n", "\n  ") or \
           "pre-deduct" in rubric["rubric"], "double-charging must be forbidden"


@pytest.mark.parametrize(
    "stage",
    ["specify", "plan", "analyze", "build", "validate"],
)
def test_no_rubric_still_advertises_the_retired_cap_scale(stage):
    """The threshold must be documented as re-derived, not left flagged stale.

    Written during T9, when every baseline was marked STALE because the severity
    scale had landed but no calibration had run yet. T14's live run closed that:
    the comment now has to name the run it came from instead.
    """
    text = (WORKFLOW_DIR / f"prototype_{stage}_rubric.yaml").read_text(encoding="utf-8")

    assert "STALE" not in text, f"{stage}'s baseline was re-derived — drop the stale flag"
    assert "RE-DERIVED from `grade.sh calibrate`" in text
    assert "capped scale" not in text.split("Previously:")[0], (
        "the retired scale may be mentioned as history, never as the live rationale"
    )


# ── T14: the re-pinned baselines match the rubrics they describe ──────────


@pytest.mark.parametrize(
    "stage", ["specify", "plan", "analyze", "build", "validate"]
)
def test_each_baseline_is_pinned_to_its_own_current_rubric(stage):
    """A stale pin makes every run read REFUSED and every threshold meaningless.

    `rubric_hash` covers precheck + judge + rubric + dimensions + anchors, so
    editing any of them must be followed by a calibration run and a re-pin. This
    test is what makes forgetting that step loud.
    """
    from evals.grading import config

    rubric = config.load_rubric(WORKFLOW_DIR, f"prototype-{stage}")
    expected = config._hash({key: rubric.get(key) for key in config.RUBRIC_HASH_KEYS})
    pinned = rubric["baseline"]["set_from"]["rubric_hash"]

    assert pinned == expected, (
        f"prototype-{stage}'s baseline is pinned to a rubric that no longer exists. "
        "Run `./grade.sh calibrate` and re-pin from its output — never from a prediction."
    )


@pytest.mark.parametrize(
    "stage", ["specify", "plan", "analyze", "build", "validate"]
)
def test_each_baseline_records_where_its_numbers_came_from(stage):
    """A threshold with no provenance cannot be trusted or re-derived."""
    from evals.grading import config

    baseline = config.load_rubric(WORKFLOW_DIR, f"prototype-{stage}")["baseline"]

    assert baseline["set_from"]["judge_resolved_model_id"] == "mistral-large-latest"
    calibrated = baseline["set_from"]["calibrated"]
    assert "grade.sh calibrate" in calibrated, "the numbers must name the run that set them"
    assert "90.96" in calibrated, "the observed ceiling is recorded, not just the date"


@pytest.mark.parametrize(
    "stage", ["specify", "plan", "analyze", "build", "validate"]
)
def test_a_matching_run_now_evaluates_instead_of_refusing(stage):
    """Between T9 and T14 every run read REFUSED. This proves that window closed.

    `evaluate_baseline` refuses outright when the recorded hashes differ from the
    run's — correct, because thresholds calibrated against a different rubric mean
    nothing. After the re-pin it must actually evaluate again.
    """
    from evals.grading import config
    from evals.grading.model import scoring

    rubric = config.load_rubric(WORKFLOW_DIR, f"prototype-{stage}")
    baseline = rubric["baseline"]
    hashes = {
        "rubric_hash": config._hash(
            {key: rubric.get(key) for key in config.RUBRIC_HASH_KEYS}
        ),
        "judge_resolved_model_id": "mistral-large-latest",
    }
    # A summary comfortably above every threshold, so only the REFUSAL logic is
    # under test here — not whether the golden happens to clear the floor.
    summary = {
        "precheck_pass_rate": 1.0,
        "negative_rows_correct": {"correct": 1, "total": 1, "rate": 1.0},
        "counts": {"judged": 6},
        "scores": {
            "average_precheck_passed": 91.0,
            "average_all": 91.0,
            "distinct_score_count": 5,
            "stddev": 1.2,
        },
    }

    verdict = scoring.evaluate_baseline(summary, baseline, hashes)
    assert verdict["verdict"] == "PASS", verdict["failures"]


def test_the_floor_sits_below_the_observed_golden_ceiling():
    """A floor at or above the ceiling would fail the reference artifact itself."""
    from evals.grading import config

    observed_ceiling = 90.96  # worst golden brief, grade.sh calibrate 2026-07-30
    for stage in ("specify", "plan", "analyze", "build", "validate"):
        baseline = config.load_rubric(WORKFLOW_DIR, f"prototype-{stage}")["baseline"]
        floor = baseline["min_average_score"]
        assert floor < observed_ceiling, f"prototype-{stage} floor {floor} >= the ceiling"
        assert observed_ceiling - floor >= 15, (
            f"prototype-{stage} floor {floor} leaves no headroom under the ceiling — "
            "a competent run that is not reference quality would fail"
        )
