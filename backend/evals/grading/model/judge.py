"""Score one response against a rubric with a judge model.

Per-dimension sub-scores via a STATIC structured-output schema. Never builds the
Pydantic model dynamically from dimension ids: `le=weight` would bake weights
into the schema, so a weight edit would silently produce an all-zero run.
"""

from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import app.agents.model_factory
import app.core.config
from pydantic import BaseModel, Field, field_validator, model_validator

# build_model only branches on this one; every other value is silently ignored
# and falls through the implicit ANTHROPIC -> Bedrock -> mistral chain.
HONOURED_PROVIDERS = ("mistral",)

# A judge call that hits a provider rate limit is retried this many times with
# exponential backoff + jitter. Bounded and rate-limit-ONLY: any other failure
# is a verdict-shaped fact worth surfacing, but a 429 is the harness asking the
# API for 10 verdicts at once — retrying is the correct behaviour, and without
# it a whole stage's grades silently die on a transient limit.
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_PATTERN = re.compile(r"(?i)rate.?limit|\b429\b|too many requests")

# SEVERITY PRICING — what a dimension's own findings cost it.
#
# This REPLACES a table that capped on the COUNT of reported weaknesses
# (1 -> 84, 2 -> 74, 3+ -> 64). Counting was the wrong operation. Measured on the
# golden run frozen at `model/workflows/prototype/golden/calibration/top/
# mission_control.verdict.json`: a hand-verified artifact scoring 100 on the code
# track had 11 of its 15 dimensions capped, dropping the run from a judge-reported
# mean of 94.51 to a recorded 85.15 — and not one of those caps was triggered by a
# defect. They were triggered by sentences like "node labels are 11.5px where body
# text is 14px". The mechanism also ran backwards: a judge reporting nothing kept
# 98 while a judge noting one cosmetic detail was cut to 84, so the harness
# penalised thoroughness and was blind to a judge that simply missed the breakage.
#
# Pricing is monotonic and reads what the finding SAYS. The one deliberate cliff
# is `blocking`, because "a reviewer would refuse to ship this" is categorical
# rather than quantitative. Broken output is now caught by two independent
# defences instead: this cap reads the judge's own words, and the code track's
# ceiling band (code_grader.CODE_BAND) reads the browser.
BLOCKING_CAP = 45     # any blocking finding makes the dimension a failing one
SEVERE_PENALTY = 8    # per blocking OR major finding
MINOR_PENALTY = 1     # per minor finding
MINOR_FLOOR = 4       # most a dimension can lose to nits, however many there are


def price_findings(reported: int, findings: list) -> tuple[int, dict]:
    """Score one dimension from what the judge reported and what it found.

    Pure: no I/O, no model, no clock — so it is table-testable, and a change to
    the constants above is replayable over stored grades without a re-run.

    The blocking cap is applied AFTER the penalties, so severity still
    accumulates underneath it and two blocking findings price below one.
    """
    severities = [getattr(finding, "severity", "major") for finding in findings]
    blocking = severities.count("blocking")
    severe = blocking + severities.count("major")
    minor = severities.count("minor")

    severe_penalty = SEVERE_PENALTY * severe
    minor_penalty = min(MINOR_FLOOR, MINOR_PENALTY * minor)
    score = reported - severe_penalty - minor_penalty
    if blocking:
        score = min(score, BLOCKING_CAP)

    return max(0, min(100, int(score))), {
        "blocking": blocking,
        "severe": severe,
        "minor": minor,
        "severe_penalty": severe_penalty,
        "minor_penalty": minor_penalty,
        "blocking_cap_applied": bool(blocking),
    }


class JudgeConfigurationError(RuntimeError):
    """A pinned judge provider that build_model cannot honour, or has no credential."""


# SEVERITY VOCABULARY. These three words are the contract between the prompt and
# the schema: the prompt defines them (see SEVERITY_GUIDANCE) and this Literal
# enforces them. They must not drift apart — a severity the judge uses but the
# schema rejects costs a verdict, and one the schema accepts but the prompt never
# defines is scored on an invented meaning.
Severity = Literal["blocking", "major", "minor"]

SEVERITY_GUIDANCE = (
    "- blocking: a reviewer would refuse to ship this. Something is missing, "
    "wrong, or broken enough that the artifact fails its purpose.\n"
    "- major: a real gap a reviewer would require fixed, but the artifact still "
    "functions.\n"
    "- minor: a nit, a preference, a 'could also have'. Not a defect."
)


class Finding(BaseModel):
    """One thing the judge found wrong with a dimension, and how bad it is.

    Severity is the field whose ABSENCE caused this model to exist: scoring used
    to key on how MANY weaknesses a dimension carried, so "the detail page is
    empty" and "the labels are 11.5px" cost the same. Recording it per finding
    is what lets the score follow the seriousness rather than the count.
    """

    severity: Severity = Field(description="blocking, major or minor — see the prompt.")
    detail: str = Field(description="One self-contained sentence naming the problem.")

    @field_validator("detail")
    @classmethod
    def _require_text(cls, value: str) -> str:
        """A finding with no text can be neither priced nor audited."""
        text = value.strip()
        if not text:
            raise ValueError("a finding needs a non-empty detail")
        return text


class DimensionScore(BaseModel):
    """One dimension's score, keyed by id — never by list position."""

    id: str = Field(description="The dimension id, exactly as given in the rubric.")
    score: int = Field(ge=0, le=100, description="0-100 for THIS dimension.")
    evidence: str = Field(description="Specific text quoted from this response.")

    @field_validator("evidence", mode="before")
    @classmethod
    def _join_evidence(cls, value):
        """Accept a LIST of quotes, not just one.

        A judge citing three separate places in a 16k-character HTML file is
        doing its job well. Requiring exactly one string threw away the entire
        verdict — scores included — over how the quotes were packaged.
        """
        if isinstance(value, (list, tuple)):
            return " · ".join(str(item).strip() for item in value if str(item).strip())
        return value

    strengths: list[str] = Field(
        default_factory=list, description="What this dimension did well, if anything."
    )
    weaknesses: list[str] = Field(
        default_factory=list, description="What this dimension did poorly, if anything."
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description=(
            "Every problem you found in THIS dimension, each tagged with its "
            "severity. Prefer this over `weaknesses`."
        ),
    )

    # Set when this dimension's findings were recovered from a legacy
    # `weaknesses` list rather than reported with severities. Counted per run so
    # a judge that quietly stopped tagging is visible, not inferred.
    severity_fallback: bool = Field(default=False, exclude=True)

    @model_validator(mode="after")
    def _reconcile_findings_and_weaknesses(self) -> "DimensionScore":
        """Make the two shapes agree, in whichever direction the judge answered.

        Three cases, and none may cost a verdict already paid for:

        - findings only → mirror them into `weaknesses`, which the score
          aggregator, both report renderers and the cross-row clustering read.
        - `weaknesses` only → lift each into a `major` finding. Untagged is
          strict but not fatal: it costs points and can never force a fail, so a
          judge that never heard of severity degrades rather than crashing.
        - both → trust `findings` and leave `weaknesses` alone. The judge
          answered properly; counting the same complaint twice would price it
          twice.
        """
        if self.findings and not self.weaknesses:
            self.weaknesses = [finding.detail for finding in self.findings]
        elif self.weaknesses and not self.findings:
            self.findings = [
                Finding(severity="major", detail=text)
                for text in self.weaknesses
                if str(text).strip()
            ]
            self.severity_fallback = bool(self.findings)
        return self


class JudgeOutput(BaseModel):
    """The judge's structured reply. Weights are applied later, in scoring.py.

    The three narrative fields default rather than being required: a judge that
    nests them per-dimension instead of at the top level used to fail validation
    and discard scores it had already paid for. `_lift_narrative` recovers them.
    """

    dimensions: list[DimensionScore]
    rationale: str = Field(
        default="", description="Overall justification for the scores, across all dimensions."
    )
    strengths: list[str] = Field(
        default_factory=list, description="Overall strengths of the response, as a flat list."
    )
    weaknesses: list[str] = Field(
        default_factory=list, description="Overall weaknesses of the response, as a flat list."
    )

    @model_validator(mode="before")
    @classmethod
    def _lift_narrative(cls, data: Any) -> Any:
        """Recover top-level narrative fields a judge nested inside `dimensions`.

        Small models routinely put rationale/strengths/weaknesses on each
        dimension entry. Losing a whole run's scores over where the prose landed
        is worse than concatenating it, so lift and de-duplicate it here.
        """
        if not isinstance(data, dict):
            return data
        dimensions = data.get("dimensions")
        if not isinstance(dimensions, list):
            return data
        for key in ("rationale", "strengths", "weaknesses"):
            if data.get(key):
                continue
            nested = _collect_nested(dimensions, key)
            if nested:
                data[key] = " ".join(nested) if key == "rationale" else nested
        return data


def _collect_nested(dimensions: list, key: str) -> list[str]:
    """Every string stored under `key` across dimension entries, order-preserved."""
    found: list[str] = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        value = dimension.get(key)
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and item.strip() and item not in found:
                found.append(item.strip())
    return found


@dataclass
class JudgeVerdict:
    """Judge result. Carries no total and no `passed` — scoring.py owns both."""

    sub_scores: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    # Per-dimension weaknesses as the judge reported them, and the caps that
    # were applied because of them — kept so a capped score stays auditable.
    dimension_weaknesses: dict[str, list[str]] = field(default_factory=dict)
    # The same findings WITH their severities, verbatim. Persisting them is what
    # makes a reduced score auditable, and what lets a future pricing change be
    # recomputed over stored grades instead of requiring a re-run — the same
    # reason weights are applied in scoring.py rather than baked into the schema.
    dimension_findings: dict[str, list[dict]] = field(default_factory=dict)
    # How many dimensions answered in the legacy untagged shape. A run where most
    # findings defaulted to `major` is scoring by a different rule than the one
    # documented, and must be able to say so.
    severity_fallbacks: int = 0
    score_caps: dict[str, dict] = field(default_factory=dict)
    resolved_model_id: str = "unknown"
    # Reported even on an errored verdict: a judge call that failed to parse
    # still spent tokens, and a cost report that hides them under-states spend.
    tokens_in: int = 0
    tokens_out: int = 0
    errored: bool = False
    error_reason: str | None = None


def _format_dimensions(dimensions: list[dict]) -> str:
    """Render each dimension as `id (weight N): description` for the prompt."""
    lines = []
    for dimension in dimensions:
        description = " ".join(str(dimension.get("description", "")).split())
        lines.append(f"- {dimension['id']} (weight {dimension.get('weight')}): {description}")
    return "\n".join(lines)


def _format_anchors(anchors: dict) -> str:
    """Render the 0-100 score anchors, highest band first."""
    lines = []
    for band in sorted(anchors, key=lambda key: int(key), reverse=True):
        text = " ".join(str(anchors[band]).split())
        lines.append(f"- {band}: {text}")
    return "\n".join(lines)


def build_judge_prompt(
    *, system_prompt: str, prompt: str, response: str, rubric: dict, precheck_reason: str
) -> str:
    """Assemble the judge prompt from the rubric, dimensions and anchors.

    Includes the agent's REAL composed system prompt (passed in from dispatch,
    not re-composed) and fences off the precheck result as already-verified so
    the judge does not re-score it.
    """
    dimensions = _format_dimensions(rubric.get("dimensions", []))
    anchors = _format_anchors(rubric.get("anchors", {}))
    return (
        "You are grading an AI agent's response as part of an automated eval "
        "suite. Score EACH rubric dimension separately from 0 to 100 and "
        "return each one as its own entry, with specific evidence quoted from "
        "this response. Do not return a single overall number — the weighted "
        "total is computed from your sub-scores.\n\n"
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
        f"{rubric.get('rubric', '')}\n"
        "=== END GRADING RUBRIC ===\n\n"
        "=== DIMENSIONS (score every one, using its id EXACTLY as written) ===\n"
        f"{dimensions}\n"
        "=== END DIMENSIONS ===\n\n"
        "=== SCORE ANCHORS (the 0-100 scale, applied to every dimension) ===\n"
        f"{anchors}\n"
        "=== END SCORE ANCHORS ===\n\n"
        "=== SCORING DISCIPLINE (how findings become numbers) ===\n"
        "Work findings-first: for each dimension, hunt for problems BEFORE "
        "choosing a number, then price every finding into the score. A "
        "'substantive weakness' is anything a reviewer would require fixed "
        "before shipping; a stylistic preference is a nit.\n"
        "Report every problem you find as a FINDING on that dimension, and tag "
        "each one with its severity:\n"
        f"{SEVERITY_GUIDANCE}\n"
        "Tag honestly in both directions: calling a nit `major` punishes good "
        "work, and calling a real gap `minor` hides it. If you would not raise "
        "it in a review, it is `minor`.\n"
        "- Your findings are PRICED IN CODE after you answer: each blocking or "
        "major finding costs the dimension 8 points, each minor costs 1 (never "
        "more than 4 in total), and any blocking finding caps the dimension at "
        "45. So report everything you find — a nit tagged `minor` barely moves "
        "the number, and hiding a real gap to protect a score defeats the eval.\n"
        "- Score the dimension on the anchors, for the quality you actually "
        "see. Do NOT pre-deduct for the findings you are about to list; that "
        "would charge for them twice.\n"
        "- 70 is the NORMAL score for competent work with real gaps; 50 is "
        "mediocre but usable, not failing.\n"
        "- Do not cluster on multiples of 5. Distinct quality must produce "
        "distinct numbers; use the full integer scale.\n"
        "=== END SCORING DISCIPLINE ===\n\n"
        "Return exactly one entry per dimension listed above — no more, no "
        "fewer — and use the dimension id verbatim. The `weight` is applied "
        "afterwards in Python, so score every dimension on the full 0-100 "
        "scale. Each piece of evidence should name a specific page, data "
        "point or detail from THIS response, not a vague generality.\n\n"
        "Then, at the TOP LEVEL of your reply — NOT inside the dimension "
        "entries — also return `rationale` (one paragraph justifying the scores "
        "overall), `strengths` (a flat list of strings) and `weaknesses` (a flat "
        "list of strings). The weaknesses are clustered across rows to decide "
        "which part of the agent's prompt to rewrite, so make each one a "
        "specific, self-contained criticism."
    )


def _assert_provider_is_honoured(provider: str) -> None:
    """Raise unless the pinned provider is one build_model actually resolves to."""
    settings = app.core.config.settings
    if provider == "mistral":
        if not settings.MISTRAL_API_KEY:
            raise JudgeConfigurationError(
                "judge provider 'mistral' is pinned but MISTRAL_API_KEY is not set."
            )
        return
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise JudgeConfigurationError(
                "judge provider 'anthropic' is pinned but build_model does not honour it — "
                "it falls through the implicit chain, and ANTHROPIC_API_KEY is not set, so "
                "the judge would silently resolve to a different provider."
            )
        return
    if provider == "bedrock":
        bedrock_configured = bool(
            (settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID)
            and settings.AWS_REGION
        )
        if settings.ANTHROPIC_API_KEY or not bedrock_configured:
            raise JudgeConfigurationError(
                "judge provider 'bedrock' is pinned but build_model does not honour it — "
                "the implicit chain would resolve to a different provider (ANTHROPIC_API_KEY "
                "is set, or no Bedrock model id + AWS_REGION is configured)."
            )
        return
    raise JudgeConfigurationError(
        f"unknown judge provider {provider!r}; build_model resolves only "
        "'mistral', 'anthropic' or 'bedrock'."
    )


def resolve_judge_model(judge_config: dict):
    """Build the judge model, HARD-FAILING on a misconfigured provider.

    build_model only honours provider "mistral"; "anthropic" and "bedrock"
    are silently ignored and fall through the implicit chain. A pinned
    provider that cannot be honoured must raise here, not degrade to an errored
    verdict — 12 rows of score 0 look like a catastrophic model regression.
    """
    provider = judge_config.get("provider")
    model = judge_config.get("model")
    if provider is None:
        return app.agents.model_factory.build_model(model)
    _assert_provider_is_honoured(provider)
    if provider in HONOURED_PROVIDERS:
        return app.agents.model_factory.build_model(model, provider=provider)
    return app.agents.model_factory.build_model(model)


def _capped_sub_scores(dimensions: list) -> tuple[dict[str, int], dict[str, dict]]:
    """Price every dimension from the findings the judge reported for it.

    Records an entry for EVERY dimension, not only reduced ones: an absent entry
    used to be indistinguishable from "not recorded", so a score that lost
    nothing looked the same as one nobody priced. Each entry carries the
    reported score, the final score, the per-severity breakdown and the findings
    themselves, so the arithmetic is fully reconstructible from the artifact.
    """
    sub_scores: dict[str, int] = {}
    score_caps: dict[str, dict] = {}
    for dimension in dimensions:
        findings = list(getattr(dimension, "findings", []) or [])
        final, breakdown = price_findings(dimension.score, findings)
        sub_scores[dimension.id] = final
        score_caps[dimension.id] = {
            "reported": dimension.score,
            "final": final,
            **breakdown,
            "findings": [{"severity": f.severity, "detail": f.detail} for f in findings],
        }
    return sub_scores, score_caps


async def _invoke_with_rate_limit_retry(structured_judge, judge_prompt: str):
    """Invoke the judge, retrying ONLY on provider rate limits, with backoff."""
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return await structured_judge.ainvoke(judge_prompt)
        except Exception as exc:  # noqa: BLE001 - only the rate-limit shape is retried
            if attempt >= RATE_LIMIT_RETRIES or not RATE_LIMIT_PATTERN.search(str(exc)):
                raise
            await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
    raise RuntimeError("unreachable")  # pragma: no cover


def _unpack_reply(reply: Any) -> tuple[Any, str | None, int, int]:
    """Split a structured-output reply into parsed, parse error, and token counts.

    `include_raw=True` yields a `{raw, parsed, parsing_error}` dict; a fake or an
    older wrapper returns the parsed object directly. Both are accepted so the
    token capture never becomes the reason a verdict is lost.
    """
    if not isinstance(reply, dict):
        return reply, None, 0, 0
    parsed = reply.get("parsed")
    error = reply.get("parsing_error")
    usage = getattr(reply.get("raw"), "usage_metadata", None) or {}
    return (
        parsed,
        None if error is None else str(error),
        int(usage.get("input_tokens") or 0),
        int(usage.get("output_tokens") or 0),
    )


def _check_dimension_ids(returned: list[str], expected: list[str]) -> str | None:
    """Return an error reason naming unexpected/missing ids, or None if they match."""
    unexpected = sorted(set(returned) - set(expected))
    missing = sorted(set(expected) - set(returned))
    if not unexpected and not missing:
        return None
    parts = []
    if missing:
        parts.append(f"missing dimension ids {missing}")
    if unexpected:
        parts.append(f"unexpected dimension ids {unexpected}")
    return f"judge returned {' and '.join(parts)}; rubric dimensions are {sorted(expected)}"


async def grade(
    response: str, *, rubric: dict, system_prompt: str, prompt: str, precheck_reason: str
) -> JudgeVerdict:
    """Grade one response, returning per-dimension sub-scores.

    Validates that the returned dimension ids match the rubric's exactly and
    keys by id, never index — ordering is not guaranteed. An id mismatch is a
    precise errored verdict. Never raises: the caller always gets a verdict.
    """
    # Deliberately OUTSIDE the try: a misconfigured judge is a hard failure, not
    # a row of score 0 that reads as a model regression.
    judge_model = resolve_judge_model(rubric.get("judge") or {})
    resolved_model_id = app.agents.model_factory.model_identifier(judge_model)
    tokens_in = tokens_out = 0
    try:
        structured_judge = judge_model.with_structured_output(JudgeOutput, include_raw=True)
        judge_prompt = build_judge_prompt(
            system_prompt=system_prompt,
            prompt=prompt,
            response=response,
            rubric=rubric,
            precheck_reason=precheck_reason,
        )
        reply = await _invoke_with_rate_limit_retry(structured_judge, judge_prompt)
        parsed, parse_error, tokens_in, tokens_out = _unpack_reply(reply)

        def errored(reason: str) -> JudgeVerdict:
            """An errored verdict that still carries this call's token cost."""
            return JudgeVerdict(
                resolved_model_id=resolved_model_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                errored=True,
                error_reason=reason,
            )

        if parse_error is not None:
            return errored(parse_error)
        if parsed is None:
            return errored("judge returned no parsable structured output")

        expected_ids = [dimension["id"] for dimension in rubric.get("dimensions", [])]
        returned_ids = [dimension.id for dimension in parsed.dimensions]
        mismatch = _check_dimension_ids(returned_ids, expected_ids)
        if mismatch is not None:
            return errored(mismatch)

        sub_scores, score_caps = _capped_sub_scores(parsed.dimensions)
        return JudgeVerdict(
            sub_scores=sub_scores,
            evidence={d.id: d.evidence for d in parsed.dimensions},
            rationale=parsed.rationale,
            strengths=list(parsed.strengths),
            weaknesses=list(parsed.weaknesses),
            dimension_weaknesses={
                d.id: list(d.weaknesses) for d in parsed.dimensions if d.weaknesses
            },
            dimension_findings={
                d.id: [{"severity": f.severity, "detail": f.detail} for f in d.findings]
                for d in parsed.dimensions
                if d.findings
            },
            severity_fallbacks=sum(1 for d in parsed.dimensions if d.severity_fallback),
            score_caps=score_caps,
            resolved_model_id=resolved_model_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    except Exception as exc:  # noqa: BLE001 - judge failures must never propagate
        return JudgeVerdict(
            resolved_model_id=resolved_model_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            errored=True,
            error_reason=str(exc),
        )
