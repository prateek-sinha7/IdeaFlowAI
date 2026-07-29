"""Unit tests for evals.model_graded.judge — one shared rubric-prompt
builder (generic over agent), grade_run() error handling (task T7).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from evals.model_graded.judge import (
    DEFAULT_JUDGE_THRESHOLD,
    build_rubric_prompt,
    grade_run,
)


def test_build_rubric_prompt_is_generic_across_two_different_rubrics():
    """Proves genericity: build_rubric_prompt takes rubric as a plain string
    argument, no per-agent lookup (clarifications.md Q10)."""
    common_kwargs = dict(
        system_prompt="SYS",
        prompt="PROMPT",
        response="RESPONSE",
        precheck_reason="PRECHECK",
    )
    prompt_a = build_rubric_prompt(rubric="Rubric A criteria", **common_kwargs)
    prompt_b = build_rubric_prompt(rubric="Rubric B criteria", **common_kwargs)

    assert "Rubric A criteria" in prompt_a
    assert "Rubric B criteria" in prompt_b
    assert "Rubric A criteria" not in prompt_b
    # Everything else about the two prompts is identical except the rubric.
    assert prompt_a.replace("Rubric A criteria", "X") == prompt_b.replace(
        "Rubric B criteria", "X"
    )


def test_build_rubric_prompt_includes_all_required_inputs():
    prompt = build_rubric_prompt(
        system_prompt="SYSTEM_PROMPT_MARKER",
        prompt="USER_PROMPT_MARKER",
        response="RESPONSE_MARKER",
        rubric="RUBRIC_MARKER",
        precheck_reason="PRECHECK_MARKER",
    )
    for marker in (
        "SYSTEM_PROMPT_MARKER",
        "USER_PROMPT_MARKER",
        "RESPONSE_MARKER",
        "RUBRIC_MARKER",
        "PRECHECK_MARKER",
    ):
        assert marker in prompt


@dataclass
class _FakeScenario:
    agent_id: str
    prompt: str
    rubric: str


@dataclass
class _FakeResult:
    response: str


class _FakeParsed:
    def __init__(self, score, rationale, strengths=None, weaknesses=None):
        self.score = score
        self.rationale = rationale
        self.strengths = strengths or []
        self.weaknesses = weaknesses or []


class _FakeStructuredModel:
    def __init__(self, parsed=None, raise_exc=None):
        self._parsed = parsed
        self._raise_exc = raise_exc

    async def ainvoke(self, _prompt):
        if self._raise_exc:
            raise self._raise_exc
        return self._parsed


class _FakeJudgeModel:
    def __init__(self, structured):
        self._structured = structured

    def with_structured_output(self, _schema):
        return self._structured


def _patch_judge_deps(monkeypatch, *, structured_model, spec=object()):
    import agents.factory as factory_module
    import agents.loader as loader_module
    import app.agents.model_factory as model_factory_module

    monkeypatch.setattr(loader_module, "load_agent_spec", lambda agent_id: spec)
    monkeypatch.setattr(
        factory_module, "_compose_system_prompt", lambda spec, ctx, no_tools=True: "COMPOSED"
    )
    monkeypatch.setattr(
        model_factory_module,
        "build_model",
        lambda model, provider=None: _FakeJudgeModel(structured_model),
    )


@pytest.mark.asyncio
async def test_grade_run_returns_verdict_on_success(monkeypatch):
    _patch_judge_deps(
        monkeypatch,
        structured_model=_FakeStructuredModel(
            parsed=_FakeParsed(
                82,
                "good spec",
                strengths=["realistic invoice numbers"],
                weaknesses=["dashboard page is generic"],
            )
        ),
    )
    scenario = _FakeScenario(agent_id="prototype-specify", prompt="brief", rubric="rubric text")
    result = _FakeResult(response="<spec>...</spec>")

    verdict = await grade_run(scenario, result, "precheck ok")

    assert verdict.score == 82
    assert verdict.rationale == "good spec"
    assert verdict.passed is True
    assert verdict.errored is False
    assert verdict.strengths == ["realistic invoice numbers"]
    assert verdict.weaknesses == ["dashboard page is generic"]


@pytest.mark.asyncio
async def test_grade_run_errored_verdict_has_empty_strengths_weaknesses(monkeypatch):
    _patch_judge_deps(
        monkeypatch,
        structured_model=_FakeStructuredModel(raise_exc=ConnectionError("down")),
    )
    scenario = _FakeScenario(agent_id="prototype-specify", prompt="brief", rubric="rubric text")
    result = _FakeResult(response="<spec>...</spec>")

    verdict = await grade_run(scenario, result, "precheck ok")

    assert verdict.strengths == []
    assert verdict.weaknesses == []


@pytest.mark.asyncio
async def test_grade_run_threshold_boundary(monkeypatch):
    _patch_judge_deps(
        monkeypatch, structured_model=_FakeStructuredModel(parsed=_FakeParsed(72, "ok"))
    )
    scenario = _FakeScenario(agent_id="prototype-specify", prompt="brief", rubric="rubric text")
    result = _FakeResult(response="<spec>...</spec>")

    default_verdict = await grade_run(scenario, result, "precheck ok")
    assert default_verdict.passed is True  # 72 >= DEFAULT_JUDGE_THRESHOLD (70)

    strict_verdict = await grade_run(scenario, result, "precheck ok", threshold=75)
    assert strict_verdict.passed is False  # 72 < 75


@pytest.mark.asyncio
async def test_grade_run_never_raises_on_network_failure(monkeypatch):
    _patch_judge_deps(
        monkeypatch,
        structured_model=_FakeStructuredModel(raise_exc=ConnectionError("network down")),
    )
    scenario = _FakeScenario(agent_id="prototype-specify", prompt="brief", rubric="rubric text")
    result = _FakeResult(response="<spec>...</spec>")

    verdict = await grade_run(scenario, result, "precheck ok")

    assert verdict.errored is True
    assert "network down" in verdict.error_reason
    assert verdict.passed is False


@pytest.mark.asyncio
async def test_grade_run_never_raises_on_malformed_structured_output(monkeypatch):
    import app.agents.model_factory as model_factory_module

    class _BrokenStructuredModel:
        async def ainvoke(self, _prompt):
            raise ValueError("could not parse structured output")

    monkeypatch.setattr(
        model_factory_module,
        "build_model",
        lambda model, provider=None: _FakeJudgeModel(_BrokenStructuredModel()),
    )
    import agents.factory as factory_module
    import agents.loader as loader_module

    monkeypatch.setattr(loader_module, "load_agent_spec", lambda agent_id: object())
    monkeypatch.setattr(
        factory_module, "_compose_system_prompt", lambda spec, ctx, no_tools=True: "COMPOSED"
    )

    scenario = _FakeScenario(agent_id="prototype-specify", prompt="brief", rubric="rubric text")
    result = _FakeResult(response="<spec>...</spec>")

    verdict = await grade_run(scenario, result, "precheck ok")
    assert verdict.errored is True


def test_default_threshold_constant_is_70():
    assert DEFAULT_JUDGE_THRESHOLD == 70


def test_judge_module_does_not_import_report():
    judge_path = Path(__file__).resolve().parents[2] / "evals/model_graded/judge.py"
    tree = ast.parse(judge_path.read_text())
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert "evals.model_graded.report" not in imported_modules
