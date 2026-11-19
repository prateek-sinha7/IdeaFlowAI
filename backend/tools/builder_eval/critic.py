"""Offline critic for builder eval runs (never part of a production turn).

:func:`compute_facts` derives what code can know about a manifest: each working
prompt's length and missing standard sections, ungated irreversible steps (the
platform's own ``irreversible_gate`` check), loop caps, placeholder instructions.
:func:`score` sends those facts, the slot table, the manifest (long prompts cut) and,
for a scripted run, the defaults run's shape to the critic prompt
(``prompts/critic.v1.md``, rubric ``critic-rubric.md``) and returns validated scores.

Operator-run from ``builder_eval_live.py --critic``; it calls a paid model.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = ["DIMENSIONS", "CriticResult", "chunks", "compute_facts", "score"]

_HERE: Final = Path(__file__).resolve().parent
_PROMPT: Final = (_HERE / "prompts" / "critic.v1.md").read_text(encoding="utf-8")
_RUBRIC: Final = (_HERE / "critic-rubric.md").read_text(encoding="utf-8")
_SECTIONS: Final = (
    "WHAT YOU RECEIVE",
    "WHAT YOU NEVER DO",
    "IF INPUT IS MISSING",
    "OUTPUT",
    "CHECK BEFORE YOU REPLY",
    "HOW TO DELIVER",
)
# One critic call carries at most this many manifest characters; larger manifests are split by step.
_MAX_CHARS: Final = 240_000
_PLACEHOLDER_RE: Final = re.compile(r"\[(?:[A-Z][a-z]+)(?: [A-Za-z]+){0,3}\]")
DIMENSIONS: Final = (
    "requirement_coverage",
    "missing_input_behaviour",
    "irreversible_gates",
    "loop_caps",
    "prompt_depth",
    "assumptions_echoed",
    "no_placeholders",
    "answers_changed_manifest",
)


class _Score(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int | None = Field(default=None, ge=1, le=5)
    reason: str = Field(min_length=1, max_length=400)


class _Scores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_coverage: _Score
    missing_input_behaviour: _Score
    irreversible_gates: _Score
    loop_caps: _Score
    prompt_depth: _Score
    assumptions_echoed: _Score
    no_placeholders: _Score
    answers_changed_manifest: _Score


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scores: _Scores


class CriticResult(BaseModel):
    """What the critic returned, plus the facts it was given and its token use."""

    scores: dict[str, dict[str, Any]]
    facts: dict[str, Any]
    usage: list[dict[str, Any]]
    status: Literal["ok", "invalid"]


def _flatten(steps: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps or []:
        if isinstance(step, dict):
            out.append(step)
            out += _flatten((step.get("subagents") or {}).get("steps"))
    return out


def _is_decision(step: Mapping[str, Any]) -> bool:
    return "conditional" in (step.get("gates") or []) or "route_decision" in (
        step.get("produces") or []
    )


def compute_facts(
    manifest: Mapping[str, Any], *, reply: str, assumptions: Sequence[str]
) -> dict[str, Any]:
    """Facts code can establish about a manifest; the critic may not contradict them."""
    from app.agents.workflow_builder import irreversible_gate

    steps = _flatten(manifest.get("steps"))
    prompts = []
    placeholders = []
    for step in steps:
        prompt = step.get("prompt")
        if not isinstance(prompt, str):
            continue
        working = not _is_decision(step)
        prompts.append(
            {
                "step": step.get("instance_id"),
                "working": working,
                "chars": len(prompt),
                "missing_sections": [s for s in _SECTIONS if s not in prompt]
                if working
                else [],
            }
        )
        placeholders += [
            f"{step.get('instance_id')}: {m}"
            for m in _PLACEHOLDER_RE.findall(prompt)[:3]
        ]
    loops = [
        {
            "step": s.get("instance_id"),
            "loop_max_iterations": (s.get("route") or {}).get("loop_max_iterations"),
        }
        for s in steps
        if (s.get("route") or {}).get("outcomes")
        and "conditional" in (s.get("gates") or [])
    ]
    lowered = reply.lower()
    return {
        "prompts": prompts,
        "irreversible_gate_issues": [
            i.message for i in irreversible_gate.check(manifest)
        ],
        "routes": loops,
        "placeholder_like_text": placeholders,
        "deliverable": manifest.get("deliverable"),
        "reply_has_assumptions_block": "**assumptions**" in lowered,
        "assumptions": list(assumptions),
    }


def chunks(
    manifest: Mapping[str, Any], max_chars: int | None = None
) -> list[dict[str, Any]]:
    """The manifest in one piece, or split by root steps so each piece fits ``max_chars``.

    Prompts are never cut: a step larger than the limit is a piece on its own.
    """
    limit = _MAX_CHARS if max_chars is None else max_chars
    whole = dict(manifest)
    if len(json.dumps(whole, ensure_ascii=False)) <= limit:
        return [whole]
    pieces: list[dict[str, Any]] = []
    group: list[Any] = []
    for step in manifest.get("steps") or []:
        trial = {**whole, "steps": [*group, step]}
        if group and len(json.dumps(trial, ensure_ascii=False)) > limit:
            pieces.append({**whole, "steps": group})
            group = [step]
        else:
            group.append(step)
    if group:
        pieces.append({**whole, "steps": group})
    return pieces


def _aggregate(results: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Per dimension: the lowest score over the pieces, with that piece's reason."""
    if len(results) == 1:
        return results[0]
    merged: dict[str, dict[str, Any]] = {}
    for key in DIMENSIONS:
        scored = [(r[key], i) for i, r in enumerate(results) if key in r]
        numeric = [(s, i) for s, i in scored if s.get("score") is not None]
        pick, index = (
            min(numeric, key=lambda si: si[0]["score"]) if numeric else scored[0]
        )
        merged[key] = {
            "score": pick.get("score"),
            "reason": f"[part {index + 1}/{len(results)}] {pick['reason']}",
        }
    return merged


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(b.get("text", ""))
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


async def score(  # noqa: PLR0913 - every input is named
    manifest: Mapping[str, Any],
    *,
    slots: Mapping[str, Any],
    reply: str,
    assumptions: Sequence[str],
    model_id: str,
    defaults_run: Mapping[str, Any] | None = None,
) -> CriticResult:
    """Score one manifest. One retry on an invalid reply; then ``status: invalid``."""
    from app.agents.model_factory import build_model

    facts = compute_facts(manifest, reply=reply, assumptions=assumptions)
    pieces = chunks(manifest)
    facts["prompt_chars_sent"] = [
        {"step": s.get("instance_id"), "chars": len(s["prompt"])}
        for piece in pieces
        for s in _flatten(piece.get("steps"))
        if isinstance(s.get("prompt"), str)
    ]
    facts["critic_parts"] = len(pieces)
    model = await asyncio.to_thread(build_model, model_id, effort=None)
    usage: list[dict[str, Any]] = []
    results: list[dict[str, dict[str, Any]]] = []
    for number, piece in enumerate(pieces, start=1):
        part = (
            ""
            if len(pieces) == 1
            else (
                f"\n<part>This is part {number} of {len(pieces)} of the manifest (whole steps, prompts "
                "complete). Score only what this part shows; facts cover the whole manifest.</part>"
            )
        )
        prompt_sections = [
            f"<rubric>\n{_RUBRIC}\n</rubric>",
            f"<facts>\n{json.dumps(facts, indent=1)}\n</facts>",
            f"<slot_table>\n{json.dumps(slots, indent=1, ensure_ascii=False)}\n</slot_table>",
            f"<manifest>\n{json.dumps(piece, indent=1, ensure_ascii=False)}\n</manifest>{part}",
        ]
        if defaults_run is not None:
            prompt_sections.append(
                f"<defaults_run>\n{json.dumps(defaults_run, indent=1, ensure_ascii=False)}\n</defaults_run>"
            )
        scored = await _score_once(model, model_id, "\n\n".join(prompt_sections), usage)
        if scored is None:
            return CriticResult(scores={}, facts=facts, usage=usage, status="invalid")
        results.append(scored)
    scores = _aggregate(results)
    if facts["irreversible_gate_issues"]:
        scores["irreversible_gates"] = {
            "score": 1,
            "reason": "code fact: " + facts["irreversible_gate_issues"][0][:200],
        }
    if defaults_run is None:
        scores["answers_changed_manifest"] = {
            "score": None,
            "reason": "defaults run: not applicable",
        }
    return CriticResult(scores=scores, facts=facts, usage=usage, status="ok")


async def _score_once(
    model: Any, model_id: str, content: str, usage: list[dict[str, Any]]
) -> dict[str, dict[str, Any]] | None:
    """One critic call with one retry on an invalid reply; ``None`` when both fail."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from agents.capabilities.token_usage import usage_from_metadata

    messages: list[Any] = [
        SystemMessage(content=_PROMPT),
        HumanMessage(content=content),
    ]
    for _attempt in range(2):
        reply_msg = await model.ainvoke(messages)
        usage.append(
            dict(
                usage_from_metadata(
                    getattr(reply_msg, "usage_metadata", None), model_id
                )
            )
        )
        text = (
            _text(reply_msg.content)
            .strip()
            .removeprefix("```json")
            .removesuffix("```")
            .strip()
        )
        try:
            parsed = _Reply.model_validate(json.loads(text))
        except (ValueError, ValidationError) as exc:
            messages += [
                AIMessage(content=text),
                HumanMessage(
                    content=f"Invalid: {str(exc)[:800]}. Reply with the JSON only."
                ),
            ]
            continue
        return {k: v.model_dump() for k, v in parsed.scores}
    return None
