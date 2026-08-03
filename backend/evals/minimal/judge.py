"""Score one response against a rubric with a judge model. The only module
that spends tokens.

Per-dimension sub-scores via a STATIC structured-output schema — never built
dynamically from the rubric's dimension ids, so an edited rubric can't
silently produce an all-zero run. Ported from `_source/judge.py`: the call
and `_unpack_reply` retry handling. Left behind: severity-pricing caps,
`consistency_cap`, and the pinned-provider preflight — this judge trusts
`build_model` to resolve whatever provider the rubric names and reports the
model's own 0-100 score verbatim.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import app.agents.model_factory
from pydantic import BaseModel, Field, model_validator

# A judge call that hits a provider rate limit is retried with exponential
# backoff + jitter. Bounded and rate-limit-ONLY: any other failure is a
# verdict-shaped fact worth surfacing as an errored verdict, not retried.
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_PATTERN = re.compile(r"(?i)rate.?limit|\b429\b|too many requests")

# A reply that parsed cleanly but covered only SOME of the rubric's
# dimensions is re-asked, naming what it skipped. Bounded: a judge that
# cannot cover the rubric in three tries is a rubric/model mismatch worth
# surfacing as an errored row, not something to keep paying for.
INCOMPLETE_RETRIES = 2
_RETRY_NOTE = (
    "YOUR PREVIOUS REPLY WAS INCOMPLETE. It omitted these dimension ids: {missing}. "
    "Return EVERY dimension listed above in one reply — including the ones you already "
    "covered — using each id verbatim. Do not stop early; a partial reply is discarded "
    "in full and the work is wasted."
)


# SEVERITY PRICING. What a finding COSTS its dimension, in points off 100.
#
# Exists because the judge reliably finds real defects and just as reliably
# refuses to deduct for them: run 260731-112251-prototype_micro listed a
# dangling `#/product/{id}` route, an unbacked "real-time" claim, and absent
# responsive behaviour — then scored those dimensions 100/100/95/90. Two
# rounds of prompt-tuning (anchor rewrites, then removing anchors entirely)
# moved the total the WRONG way, 94.0 -> 97.25.
#
# So the arithmetic moves out of the judge's hands: it reports findings and
# tags each one's severity (which it already wanted to do — it kept emitting
# `{"finding": ..., "severity": ...}` dicts unprompted), and Python prices
# them. Judging what is wrong is a language task; converting that into a
# number is not, and this is the one place a model should not be trusted.
SEVERITY_COST = {"blocking": 45, "major": 18, "minor": 4}
DEFAULT_SEVERITY = "minor"

# Severity travels as a TEXT PREFIX ("blocking: the spec references ..."),
# not as a nested object, and this is load-bearing rather than stylistic.
#
# `dimensions` is a plain array with no minItems (the schema is static by
# design — see JudgeOutput — so it cannot carry a per-rubric minimum), which
# means returning ONE dimension is fully schema-valid. While each dimension
# entry was cheap (flat lists of strings) the judge filled them all in: runs
# 260731-110817/111644/112251 returned 3/3, 4/4, 4/4. Nesting a
# `Finding{text, severity}` object inside each entry made them expensive, and
# the judge started satisfying the outer array MINIMALLY — one dimension,
# every time, through two retries (runs 260731-113247 at 7 dimensions and
# 260731-121449 at 5, so dimension count was never the driver).
#
# Flattening restores the proven shape and keeps the severity signal.
_SEVERITY_PREFIX = re.compile(r"^\s*\**\s*(blocking|major|minor)\s*\**\s*[:\-—]\s*", re.I)


def split_severity(text: str) -> tuple[str, str]:
    """`"major: no empty state"` -> `("major", "no empty state")`.

    An untagged or unrecognised finding still costs DEFAULT_SEVERITY — a
    mistagged defect should be priced, never silently free.
    """
    match = _SEVERITY_PREFIX.match(text or "")
    if match:
        return match.group(1).lower(), (text[match.end():] or "").strip()
    return DEFAULT_SEVERITY, (text or "").strip()


def severity_cost(severity: str) -> int:
    return SEVERITY_COST.get(severity, SEVERITY_COST[DEFAULT_SEVERITY])


class DimensionScore(BaseModel):
    """One dimension's verdict, keyed by id — never by list position.

    `score` is the judge's OWN number. It is recorded but not necessarily
    used: a severity-priced rubric derives the real score from `weaknesses`
    instead, and keeping both makes the leniency gap visible rather than
    silently discarded.
    """

    id: str = Field(description="The dimension id, exactly as given in the rubric.")
    score: int = Field(ge=0, le=100, description="0-100 for THIS dimension.")
    evidence: str = Field(description="Specific text quoted from this response.")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Each defect prefixed with its severity: 'blocking: ...', "
                     "'major: ...' or 'minor: ...'. The prefix is required.",
    )

    def findings(self) -> list[dict]:
        """This dimension's weaknesses, split into text + severity + cost."""
        out = []
        for weakness in self.weaknesses:
            severity, text = split_severity(weakness)
            out.append({"text": text, "severity": severity, "cost": severity_cost(severity)})
        return out

    def priced(self) -> int:
        """100 minus what this dimension's own findings cost. Floored at 0."""
        return max(0, 100 - sum(f["cost"] for f in self.findings()))


class JudgeOutput(BaseModel):
    """The judge's structured reply.

    The dimension list is STATIC — never rebuilt from the rubric's ids — so
    an edited rubric can't silently produce an all-zero run. The cost is that
    the schema cannot carry a per-rubric `minItems`, so the completeness
    requirement has to live in the field description and be enforced after
    the fact by `_check_dimension_ids`.
    """

    dimensions: list[DimensionScore] = Field(
        description="One entry for EVERY dimension id listed in the rubric — a partial "
                     "list is discarded in full and the work is wasted.",
    )
    rationale: str = Field(default="")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _lift_narrative(cls, data: Any) -> Any:
        """Recover top-level narrative fields a judge nested inside `dimensions`,
        and normalise every strengths/weaknesses entry's shape.

        Small models routinely put rationale/strengths/weaknesses on each
        dimension entry (losing a whole run's scores over where the prose
        landed is worse than concatenating it), and shape each entry as
        `{"description"/"finding": "...", "tag"/"severity": "..."}` instead of
        the declared shape — Pydantic rejects that outright, which used to
        drop the entire row. Normalising here, before field validation runs,
        keeps the row AND preserves any severity the judge volunteered.
        """
        if not isinstance(data, dict):
            return data
        if isinstance(data.get("strengths"), list):
            data["strengths"] = [_to_text(item) for item in data["strengths"]]
        if isinstance(data.get("weaknesses"), list):
            data["weaknesses"] = [_to_text(item) for item in data["weaknesses"]]
        dimensions = data.get("dimensions")
        if not isinstance(dimensions, list):
            return data
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            if isinstance(dimension.get("strengths"), list):
                dimension["strengths"] = [_to_text(i) for i in dimension["strengths"]]
            if isinstance(dimension.get("weaknesses"), list):
                dimension["weaknesses"] = [_to_weakness(i) for i in dimension["weaknesses"]]
        for key in ("rationale", "strengths", "weaknesses"):
            if data.get(key):
                continue
            nested = _collect_nested(dimensions, key)
            if nested:
                data[key] = " ".join(nested) if key == "rationale" else nested
        return data


# Common keys a judge puts prose under when it nests a dict instead of a
# bare string in a strengths/weaknesses list.
_TEXT_KEYS = ("description", "finding", "text", "issue", "detail", "note", "summary")
_SEVERITY_KEYS = ("severity", "tag", "level", "impact")


def _to_text(item: Any) -> str:
    """One strengths/weaknesses list entry, coerced to a plain string."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in _TEXT_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def _to_weakness(item: Any) -> str:
    """One weakness entry, normalised to the flat `"severity: text"` form.

    The judge sometimes ignores the prefix convention and emits a dict
    (`{"finding": ..., "severity": ...}`) anyway — that severity is kept and
    folded into the prefix rather than discarded. A string that already
    carries a prefix passes through untouched.
    """
    if isinstance(item, dict):
        text = _to_text(item)
        severity = next(
            (str(item[k]).strip().lower() for k in _SEVERITY_KEYS
             if isinstance(item.get(k), str) and item[k].strip()),
            None,
        )
        if severity and not _SEVERITY_PREFIX.match(text):
            return f"{severity}: {text}"
        return text
    return _to_text(item)


def _collect_nested(dimensions: list, key: str) -> list[str]:
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
    """Judge result. Carries no total — score.py's `aggregate` owns that.

    Two parallel sub-score maps, deliberately: `sub_scores` is what the judge
    said, `sub_scores_priced` is what its own findings cost under
    SEVERITY_COST. Keeping both is what makes the leniency gap measurable
    instead of a thing you have to take on faith — see `findings`, which
    holds the priced items themselves.
    """

    sub_scores: dict[str, int] = field(default_factory=dict)
    sub_scores_priced: dict[str, int] = field(default_factory=dict)
    findings: dict[str, list[dict]] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    resolved_model_id: str = "unknown"
    tokens_in: int = 0
    tokens_out: int = 0
    errored: bool = False
    error_reason: str | None = None


_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
JUDGE_PROMPT_TEMPLATE = (_PROMPT_DIR / "judge_prompt.md").read_text(encoding="utf-8")
ADVISE_PROMPT_TEMPLATE = (_PROMPT_DIR / "advise_prompt.md").read_text(encoding="utf-8")



class Suggestion(BaseModel):
    """ONE piece of advice: what to change, how strongly, where it belongs, why."""

    action: str = Field(
        description="Either 'add' (a new instruction for the prompt) or 'remove' "
                     "(an instruction already in the prompt that causes the weakness).",
    )
    description: str = Field(
        description="The instruction itself, as one self-contained sentence that could "
                     "be pasted into the prompt as-is. For 'remove', quote the existing wording.",
    )
    advisory_score: int = Field(
        ge=0, le=100,
        description="How strongly this is advised: 0 = optional (MAY), 100 = mandatory "
                     "(MUST). Judge it by what the observed weakness actually costs.",
    )
    category: str = Field(
        description="Which rubric dimension id this serves, verbatim from the list given.",
    )
    reason: str = Field(
        default="",
        description="Which observed weakness this addresses, in one line. Name the "
                     "evidence, not the intent.",
    )


class AdviceOutput(BaseModel):
    """The advisor's structured reply: ONE flat list.

    Not `add`/`remove` as separate arrays — the action is a field on each
    item, so every suggestion carries its own four facts and the caller never
    has to merge two lists that could disagree. This is also the flattest
    shape the schema can take: one top-level array of flat objects. Two
    levels of nesting is what made the judge return a single element and
    stop (see SEVERITY_COST), and that failure is silent.
    """

    advice: list[Suggestion] = Field(
        default_factory=list,
        description="Every suggested prompt change, each tagged with its own action.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_entries(cls, data: Any) -> Any:
        """Accept a bare string, and accept the older `add`/`remove` shape.

        The advisor does what the judge did: it returns a plain list of quoted
        prompt lines rather than objects, and strict validation drops the whole
        call (run 260731-140047, analyze). A string carries the description;
        the missing score defaults to 0 (MAY) so an unscored suggestion cannot
        outrank a scored one, and the category falls back to `uncategorised`
        so it still clusters somewhere visible instead of vanishing.

        Split `add`/`remove` keys are folded in too, since the model has been
        shown that shape before and may still reach for it.
        """
        if not isinstance(data, dict):
            return data

        def one(item: Any, action: str) -> dict:
            if isinstance(item, str):
                return {"action": action, "description": item, "advisory_score": 0,
                        "category": "uncategorised", "reason": ""}
            if isinstance(item, dict):
                return {**item, "action": str(item.get("action") or action)}
            return item

        merged = [one(i, "add") for i in (data.get("advice") or []) if i]
        for legacy in ("add", "remove"):
            merged += [one(i, legacy) for i in (data.get(legacy) or []) if i]
        data["advice"] = merged
        data.pop("add", None)
        data.pop("remove", None)
        return data


@dataclass
class Advice:
    """Structured prompt edits. Never raises — same R-09 contract as `judge`."""

    advice: list[dict] = field(default_factory=list)
    text: str = ""          # kept for older stored advice; no longer produced
    resolved_model_id: str = "unknown"
    tokens_in: int = 0
    tokens_out: int = 0
    errored: bool = False
    error_reason: str | None = None


async def advise(
    *, system_prompt: str, weaknesses: list[str], strengths: list[str], judge_config: dict,
    categories: list[str] | None = None, on_call=None,
) -> Advice:
    """One model call: given the judge's already-clustered weaknesses/
    strengths and the agent's REAL current system prompt, propose the
    smallest edit that fixes the weaknesses without breaking the strengths.
    Uses the same provider the rubric's judge is pinned to — one cost model,
    not a second provider to configure."""
    judge_model = _resolve_judge_model(judge_config)
    resolved_model_id = app.agents.model_factory.model_identifier(judge_model)
    try:
        prompt = ADVISE_PROMPT_TEMPLATE.format(
            system_prompt=system_prompt,
            weaknesses="\n".join(f"- {w}" for w in weaknesses) or "(none reported)",
            strengths="\n".join(f"- {s}" for s in strengths) or "(none reported)",
            categories=", ".join(categories or []) or "(no dimension list supplied)",
        )
        structured = judge_model.with_structured_output(AdviceOutput, include_raw=True)
        reply = await _invoke_with_rate_limit_retry(structured, prompt)
        parsed, parse_error, tokens_in, tokens_out = _unpack_reply(reply)
        if on_call:
            on_call({"kind": "advise", "attempt": 0, "model": resolved_model_id,
                      "prompt": prompt, "raw": _raw_snapshot(reply),
                      "parse_error": parse_error, "tokens_in": tokens_in, "tokens_out": tokens_out})
        if parse_error is not None or parsed is None:
            return Advice(resolved_model_id=resolved_model_id, tokens_in=tokens_in,
                           tokens_out=tokens_out, errored=True,
                           error_reason=parse_error or "advisor returned no parsable output")
        return Advice(
            advice=[_suggestion(x) for x in parsed.advice],
            resolved_model_id=resolved_model_id,
            tokens_in=tokens_in, tokens_out=tokens_out,
        )
    except Exception as exc:  # noqa: BLE001 - advice failures must never propagate
        if on_call:
            on_call({"kind": "advise", "attempt": 0, "model": resolved_model_id,
                      "prompt": locals().get("prompt", ""), "error": str(exc)})
        return Advice(resolved_model_id=resolved_model_id, errored=True, error_reason=str(exc))


def _suggestion(item: Suggestion) -> dict:
    """One suggestion, with its category normalised for clustering.

    Free-text categories fragment ("Data", "data", " data ") and a cluster
    that splits on capitalisation counts the same problem twice.
    """
    action = item.action.strip().lower()
    return {
        "action": action if action in ("add", "remove") else "add",
        "description": item.description.strip(),
        "advisory_score": int(item.advisory_score),
        "category": item.category.strip().lower().replace(" ", "_") or "uncategorised",
        "reason": item.reason.strip(),
    }


def build_judge_prompt(*, system_prompt: str, prompt: str, response: str, rubric: dict) -> str:
    """Fill `prompts/judge_prompt.md` from the rubric's dimensions and anchors.

    The template is a real file, not a mirror — this IS the prompt that gets
    sent, so reading it on disk always matches what actually ran.

    `anchors` is optional and carries its OWN section header, so a rubric
    without them (specify — see its comments) emits nothing at all rather
    than an empty section or a paragraph explaining the absence. Explaining
    it cost ~60 tokens on every call to say "ignore this".
    """
    dimensions = "\n".join(
        f"- {d['id']} (weight {d.get('weight')}): {' '.join(str(d.get('description', '')).split())}"
        for d in rubric.get("dimensions", [])
    )
    anchor_map = rubric.get("anchors") or {}
    anchor_lines = "\n".join(
        f"- {band}: {' '.join(str(anchor_map[band]).split())}"
        for band in sorted(anchor_map, key=lambda k: int(k), reverse=True)
    )
    anchors = f"\n=== SCORE ANCHORS ===\n{anchor_lines}\n=== END ===\n" if anchor_lines else ""
    return JUDGE_PROMPT_TEMPLATE.format(
        system_prompt=system_prompt, prompt=prompt, response=response,
        rubric_text=rubric.get("rubric", ""), dimensions=dimensions, anchors=anchors,
    )


def _resolve_judge_model(judge_config: dict):
    """Build the judge model. No pinned-provider preflight — trust `build_model`."""
    provider = judge_config.get("provider")
    model = judge_config.get("model")
    if provider is None:
        return app.agents.model_factory.build_model(model)
    return app.agents.model_factory.build_model(model, provider=provider)


async def _invoke_with_rate_limit_retry(structured_judge, judge_prompt: str):
    """Invoke the judge, retrying ONLY on provider rate limits, with backoff."""
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return await structured_judge.ainvoke(judge_prompt)
        except Exception as exc:  # noqa: BLE001 - only the rate-limit shape is retried
            if attempt >= RATE_LIMIT_RETRIES or not RATE_LIMIT_PATTERN.search(str(exc)):
                raise
            await asyncio.sleep((2**attempt) + random.uniform(0, 1))
    raise RuntimeError("unreachable")  # pragma: no cover


def _raw_snapshot(reply: Any) -> dict:
    """What the model literally sent back, for the call log.

    With `include_raw=True` the structured payload usually arrives in the raw
    message's `tool_calls`, not its `content` — logging only `content` would
    have shown an empty string for every judge call and proved nothing.
    """
    raw = reply.get("raw") if isinstance(reply, dict) else reply
    return {
        "content": getattr(raw, "content", "") or "",
        "tool_calls": getattr(raw, "tool_calls", None) or [],
    }


async def _invoke_logged(structured_judge, prompt: str, on_call, **meta):
    """Invoke the judge and log the call — prompt, raw reply, tokens, error.

    Logs on the failure path too: a call that raised or failed to parse is
    exactly the one worth reading afterwards.
    """
    try:
        reply = await _invoke_with_rate_limit_retry(structured_judge, prompt)
    except Exception as exc:
        if on_call:
            on_call({**meta, "prompt": prompt, "error": str(exc)})
        raise
    parsed, parse_error, tokens_in, tokens_out = _unpack_reply(reply)
    if on_call:
        on_call({
            **meta, "prompt": prompt, "raw": _raw_snapshot(reply),
            "parse_error": parse_error, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "dimensions_returned": [d.id for d in parsed.dimensions] if parsed is not None else [],
        })
    return parsed, parse_error, tokens_in, tokens_out


def _unpack_reply(reply: Any) -> tuple[Any, str | None, int, int]:
    """Split a structured-output reply into parsed, parse error, and token counts."""
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


async def judge(
    response: str, *, rubric: dict, system_prompt: str = "", prompt: str = "",
    on_call=None,
) -> JudgeVerdict:
    """Grade one response against a rubric. NEVER raises — R-09: a malformed
    reply costs this one row, not the stage. A dimension-id mismatch (e.g. a
    missing dimension) returns an errored verdict naming it; the caller drops
    the row and the stage completes.

    `on_call(record)` receives every model call made here — including retries
    and failures — so the raw exchange can be read back later instead of
    reconstructed from the error string.
    """
    judge_model = _resolve_judge_model(rubric.get("judge") or {})
    resolved_model_id = app.agents.model_factory.model_identifier(judge_model)
    tokens_in = tokens_out = 0
    try:
        structured_judge = judge_model.with_structured_output(JudgeOutput, include_raw=True)
        judge_prompt = build_judge_prompt(
            system_prompt=system_prompt, prompt=prompt, response=response, rubric=rubric,
        )
        parsed, parse_error, tokens_in, tokens_out = await _invoke_logged(
            structured_judge, judge_prompt, on_call, kind="judge", attempt=0,
            model=resolved_model_id,
        )

        def errored(reason: str) -> JudgeVerdict:
            return JudgeVerdict(
                resolved_model_id=resolved_model_id, tokens_in=tokens_in,
                tokens_out=tokens_out, errored=True, error_reason=reason,
            )

        expected_ids = [d["id"] for d in rubric.get("dimensions", [])]

        # An INCOMPLETE dimension set is retried, unlike a malformed one.
        # Observed in run 260731-113247-prototype_smoke: asked for 7
        # dimensions, mistral-large returned 1 (`data_realism`) and stopped —
        # neither a truncation (5.4k-token prompt, 32k output ceiling) nor a
        # parse failure, just the model quitting early on a long task. That
        # cost the whole row with no second attempt, while a rate limit got
        # four. Re-asking names the dimensions it skipped, which is a far
        # stronger prompt than the original generic instruction.
        for attempt in range(INCOMPLETE_RETRIES + 1):
            if parse_error is not None:
                return errored(parse_error)
            if parsed is None:
                return errored("judge returned no parsable structured output")
            returned_ids = [d.id for d in parsed.dimensions]
            mismatch = _check_dimension_ids(returned_ids, expected_ids)
            if mismatch is None:
                break
            if attempt >= INCOMPLETE_RETRIES or not set(expected_ids) - set(returned_ids):
                return errored(mismatch)  # unexpected-ids-only never improves on a re-ask
            missing = sorted(set(expected_ids) - set(returned_ids))
            parsed, parse_error, retry_in, retry_out = await _invoke_logged(
                structured_judge, f"{judge_prompt}\n\n{_RETRY_NOTE.format(missing=missing)}",
                on_call, kind="judge-retry", attempt=attempt + 1,
                model=resolved_model_id, missing=missing,
            )
            # Accumulate, never overwrite: a retried row really did cost both calls.
            tokens_in += retry_in
            tokens_out += retry_out

        # Per-dimension findings flatten into `weaknesses` for display, so a
        # rubric that prices findings still surfaces the same prose the
        # narrative-only path did (the report and the advisor both read it).
        dimension_findings = {d.id: d.findings() for d in parsed.dimensions}
        flattened = [f["text"] for items in dimension_findings.values() for f in items]
        return JudgeVerdict(
            sub_scores={d.id: d.score for d in parsed.dimensions},
            sub_scores_priced={d.id: d.priced() for d in parsed.dimensions},
            findings=dimension_findings,
            evidence={d.id: d.evidence for d in parsed.dimensions},
            rationale=parsed.rationale,
            strengths=list(parsed.strengths),
            weaknesses=list(parsed.weaknesses) or flattened,
            resolved_model_id=resolved_model_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    except Exception as exc:  # noqa: BLE001 - judge failures must never propagate
        return JudgeVerdict(
            resolved_model_id=resolved_model_id, tokens_in=tokens_in,
            tokens_out=tokens_out, errored=True, error_reason=str(exc),
        )
