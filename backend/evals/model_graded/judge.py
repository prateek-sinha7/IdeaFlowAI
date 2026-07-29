"""model_graded/judge.py — LLM-as-judge grading, generic over agent.

Builds the grading prompt via ONE shared prompt-builder, parameterized by a
scenario's plain-text ``rubric:`` YAML block — never a per-agent Python
module lookup (clarifications.md Q10). Reuses ``build_model()`` exactly as
every other caller does by default (clarifications.md Q1: no forced distinct
provider — keeps ``--judge`` frictionless on a machine with only
``ANTHROPIC_API_KEY`` configured), overridable via ``provider=``/``model=``.

The judge returns a SCORE plus explicit STRENGTHS/WEAKNESSES lists, not just
one prose rationale paragraph — makes ``report --worst`` output scannable
without re-reading a paragraph to extract "what was actually wrong."

Never imports ``report.py`` (Component Boundaries) and never raises out of
``grade_run`` — a judge failure degrades to an errored ``JudgeVerdict``, it
never crashes the run or masks the deterministic pre-check result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

DEFAULT_JUDGE_THRESHOLD = 70


class _JudgeStructuredOutput(BaseModel):
    """The structured-output schema requested from the judge model."""

    score: int = Field(ge=0, le=100, description="Overall quality score, 0-100.")
    strengths: list[str] = Field(
        description="Specific things the response did well, per the rubric. Empty list if none."
    )
    weaknesses: list[str] = Field(
        description="Specific things the response did poorly, per the rubric. Empty list if none."
    )
    rationale: str = Field(description="One-paragraph summary tying the score to the rubric.")


@dataclass
class JudgeVerdict:
    score: int
    passed: bool
    rationale: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    resolved_model_id: str = "unknown"
    errored: bool = False
    error_reason: str | None = None


def build_rubric_prompt(
    *,
    system_prompt: str,
    prompt: str,
    response: str,
    rubric: str,
    precheck_reason: str,
) -> str:
    """The ONE shared judge-grading prompt builder — generic over every agent
    onboarded onto this branch. Takes the scenario's rubric as plain text, not
    a per-agent module.
    """
    return (
        "You are grading an AI agent's response as part of an automated eval "
        "suite. Score the response 0-100, and list SPECIFIC strengths and "
        "weaknesses (not generic praise/criticism) tied to the rubric below.\n\n"
        "=== AGENT SYSTEM PROMPT (what the agent was instructed to do) ===\n"
        f"{system_prompt}\n"
        "=== END AGENT SYSTEM PROMPT ===\n\n"
        "=== USER PROMPT / BRIEF SENT TO THE AGENT ===\n"
        f"{prompt}\n"
        "=== END USER PROMPT ===\n\n"
        "=== AGENT RESPONSE ===\n"
        f"{response}\n"
        "=== END AGENT RESPONSE ===\n\n"
        "=== DETERMINISTIC PRE-CHECK RESULT (already verified — do NOT "
        "re-score these facts as strengths or weaknesses) ===\n"
        f"{precheck_reason}\n"
        "=== END PRE-CHECK RESULT ===\n\n"
        "=== GRADING RUBRIC (what YOU should focus on) ===\n"
        f"{rubric}\n"
        "=== END GRADING RUBRIC ===\n\n"
        "Score strictly against the rubric above. Do not penalize or reward "
        "anything the pre-check result already covers — focus only on what "
        "the rubric asks you to assess. Each strength/weakness should name a "
        "specific page/data-point/detail, not a vague generality."
    )


async def grade_run(
    scenario,
    result,
    precheck_reason: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    threshold: int | None = None,
) -> JudgeVerdict:
    """Grade ``result.response`` against ``scenario``'s rubric.

    Never raises: any exception (network, parse failure) is caught and
    returned as an errored ``JudgeVerdict`` instead.
    """
    effective_threshold = DEFAULT_JUDGE_THRESHOLD if threshold is None else threshold
    resolved_model_id = "unknown"
    try:
        from agents.factory import _compose_system_prompt, AgentContext
        from agents.loader import load_agent_spec
        from app.agents.model_factory import build_model, model_identifier

        spec = load_agent_spec(scenario.agent_id)
        system_prompt = _compose_system_prompt(
            spec, AgentContext(user_request=scenario.prompt), no_tools=True
        )

        judge_model = build_model(model, provider=provider)
        # Captured immediately after the model is BUILT (not after a
        # successful grade) — the actual resolved model id (e.g. from
        # settings.MISTRAL_MODEL_ID's default, when `model=` wasn't passed
        # explicitly), not just whatever `model`/`provider` args the caller
        # passed. Recorded even if the ainvoke below fails, so an errored
        # verdict still says which model was attempted.
        resolved_model_id = model_identifier(judge_model)
        structured_judge = judge_model.with_structured_output(_JudgeStructuredOutput)

        rubric_prompt = build_rubric_prompt(
            system_prompt=system_prompt,
            prompt=scenario.prompt,
            response=result.response,
            rubric=scenario.rubric,
            precheck_reason=precheck_reason,
        )
        parsed: _JudgeStructuredOutput = await structured_judge.ainvoke(rubric_prompt)

        return JudgeVerdict(
            score=parsed.score,
            passed=parsed.score >= effective_threshold,
            rationale=parsed.rationale,
            strengths=list(parsed.strengths),
            weaknesses=list(parsed.weaknesses),
            resolved_model_id=resolved_model_id,
        )
    except Exception as exc:  # noqa: BLE001 - judge failures must never propagate
        return JudgeVerdict(
            score=0,
            passed=False,
            rationale="",
            strengths=[],
            weaknesses=[],
            resolved_model_id=resolved_model_id,
            errored=True,
            error_reason=str(exc),
        )
