"""Summary tables for builder eval run sets (operator-run, never CI).

A run set is a folder of request folders, each holding the harness's
``turn<N>.json`` records. :func:`summarize` reduces one set to the measures the
flag-flip exit criteria use; :func:`render` prints several sets side by side.

Usage (from ``backend/``)::

    uv run python -m tools.builder_eval.report SET_FOLDER [SET_FOLDER ...] [--expect-build R3]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

__all__ = ["main", "render", "spend", "summarize"]

# Records written before the harness stored a model id ran on this model.
_LEGACY_MODEL: Final = "eu.anthropic.claude-sonnet-5-5"
_DIMENSIONS: Final = (
    "requirement_coverage",
    "missing_input_behaviour",
    "irreversible_gates",
    "loop_caps",
    "prompt_depth",
    "assumptions_echoed",
    "no_placeholders",
    "answers_changed_manifest",
)


def _records(folder: Path) -> dict[str, list[dict[str, Any]]]:
    """``{request id: [turn records in order]}`` for every request folder in ``folder``."""
    sessions: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(folder.glob("*/turn*.json")):
        if path.name.endswith((".workflow.json", ".critic.json")):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        sessions.setdefault(path.parent.name, []).append(record)
    for turns in sessions.values():
        turns.sort(key=lambda r: r["turn"])
    return sessions


def _count(usage: dict[str, Any], key: str) -> int:
    return int(usage.get(key) or usage.get(f"{key}_tokens") or 0)


def spend(records: Sequence[dict[str, Any]]) -> float:
    """Dollar cost of the turns and their critic calls, each at its own model's catalog rates.

    Uses the platform's ``estimate_cost_usd``; a record without a model id is priced
    at the Sonnet 5.5 rates the early runs used.
    """
    from agents.capabilities.model_pricing import estimate_cost_usd

    total = 0.0
    for record in records:
        model = record.get("model_id") or _LEGACY_MODEL
        critic_model = record.get("critic_model") or model
        pairs = [(model, record.get("usage") or {})] + [
            (critic_model, u) for u in record.get("critic_usage") or []
        ]
        for model_id, usage in pairs:
            total += estimate_cost_usd(
                model_id,
                _count(usage, "input"),
                _count(usage, "output"),
                _count(usage, "cache_read"),
                _count(usage, "cache_write"),
            )
    return total


def summarize(
    folder: Path, expect_build: frozenset[str] = frozenset({"R3"})
) -> dict[str, Any]:
    """The exit-criteria measures for one run set.

    A session with an ``infra_failure`` (a transient network error that survived the
    harness's retries) is left out of every measure and counted on its own.
    """
    every = _records(folder)
    infra = sorted(
        i for i, turns in every.items() if any(t.get("infra_failure") for t in turns)
    )
    sessions = {i: turns for i, turns in every.items() if i not in infra}
    ask_ids = [i for i in sessions if i not in expect_build]
    build_ids = [i for i in sessions if i in expect_build]
    first = {i: turns[0] for i, turns in sessions.items()}
    asked_first = [
        i
        for i in ask_ids
        if not first[i]["draft_accepted"] and first[i].get("intake_questions")
    ]
    built_class_ok = [
        i
        for i in build_ids
        if not first[i].get("intake_questions")
        and first[i]["draft_accepted"]
        and not (first[i].get("manifest_shape") or {}).get("intake_step")
    ]
    questions = [q for i in sessions for q in first[i].get("intake_questions") or []]
    asked_sessions = [i for i in sessions if first[i].get("intake_questions")]
    last = {i: turns[-1] for i, turns in sessions.items()}
    built = [r for r in last.values() if r["draft_accepted"]]
    sources: Counter[str] = Counter()
    for r in last.values():
        sources.update(r.get("intake_source_counts") or {})
    irreversible = [
        s
        for r in built
        for s in (r.get("manifest_shape") or {}).get("irreversible_steps") or []
    ]
    all_turns = [t for turns in sessions.values() for t in turns]
    fallback = [
        t
        for t in all_turns
        if t.get("intake_enabled")
        and t["turn"] == 1
        and "intake" not in str(t.get("prompt_version") or "")
    ]
    critic = [r for r in built if r.get("critic_status") == "ok"]
    dims = {}
    for d in _DIMENSIONS:
        values = [
            r["critic_scores"].get(d)
            for r in critic
            if r["critic_scores"].get(d) is not None
        ]
        dims[d] = (sum(values) / len(values)) if values else None
    passing = [
        r
        for r in critic
        if all(v is None or v >= 4 for v in r["critic_scores"].values())
    ]
    where_what = [
        i for i in sessions if first[i].get("approval_question_form") == "where_what"
    ]
    where_without_write = [
        i
        for i in where_what
        if last[i].get("irreversible_action_after_intake") is False
    ]
    repairs = sum(int(r.get("intake_repairs_total") or 0) for r in last.values())
    calls = sum(
        1
        for t in all_turns
        if t.get("intake_enabled") and "intake" in str(t.get("prompt_version") or "")
    )
    return {
        "sessions": len(sessions),
        "effort": sorted(
            {str(t.get("intake_effort")) for t in all_turns if t.get("intake_enabled")}
        ),
        "asked_first": (len(asked_first), len(ask_ids)),
        "build_class_ok": (len(built_class_ok), len(build_ids)),
        "questions_per_asking_session": (len(questions) / len(asked_sessions))
        if asked_sessions
        else 0.0,
        "blocking_vs_important": (
            sum(q["criticality"] == "blocking" for q in questions),
            sum(q["criticality"] == "important" for q in questions),
        ),
        "feasibility_notes": sum(
            len(first[i].get("intake_feasibility_notes") or []) for i in sessions
        ),
        "sources_after_handoff": dict(sources),
        "repairs": repairs,
        "retries": sum(int(r.get("intake_retries_total") or 0) for r in last.values()),
        "repair_rate": (repairs / calls) if calls else 0.0,
        "fallback": (
            len(fallback),
            sum(1 for t in all_turns if t.get("intake_enabled") and t["turn"] == 1),
        ),
        "gate_rejections": sum(int(t.get("gate_rejections") or 0) for t in all_turns),
        "irreversible_rejections": sum(
            int(t.get("irreversible_gate_rejections") or 0) for t in all_turns
        ),
        "fact_propagation_rejections": _rule_count(all_turns, "fact_propagation"),
        "placeholder_rejections": _rule_count(all_turns, "placeholder"),
        "redo_accepted_after_brief_check": sum(
            1
            for t in all_turns
            if t.get("draft_accepted")
            and any(
                r in rules
                for rules in t.get("gate_rejection_rules") or []
                for r in ("irreversible_gate", "fact_propagation", "placeholder")
            )
        ),
        "infra_failures": (len(infra), len(every)),
        "infra_failure_ids": infra,
        "transient_retries": sum(
            len(t.get("transient_retries") or [])
            for turns in every.values()
            for t in turns
        ),
        "valid": (
            sum(r.get("validator_verdict") == "VALID" for r in built),
            len(built),
        ),
        "built": (len(built), len(sessions)),
        "steps_avg": (
            sum((r.get("manifest_shape") or {}).get("root_steps", 0) for r in built)
            / len(built)
        )
        if built
        else 0.0,
        "intake_steps": sum(
            bool((r.get("manifest_shape") or {}).get("intake_step")) for r in built
        ),
        "irreversible_gated": (
            sum(bool(s.get("gated")) for s in irreversible),
            len(irreversible),
        ),
        "shape_diffs": {
            i: r.get("shape_diff_vs_defaults")
            for i, r in last.items()
            if r.get("shape_diff_vs_defaults")
        },
        "critic_mean": dims,
        "critic_distribution": {
            d: dict(
                sorted(
                    Counter(r["critic_scores"].get(d) for r in critic).items(),
                    key=lambda kv: str(kv[0]),
                )
            )
            for d in _DIMENSIONS
        },
        "critic_pass": (len(passing), len(critic)),
        "approval_where_without_write": (len(where_without_write), len(where_what)),
        "approval_where_without_write_ids": where_without_write,
        "spend": round(spend(all_turns), 2),
    }


def _rule_count(turns: Sequence[dict[str, Any]], rule: str) -> int:
    """Server_Gate rejections that named ``rule``."""
    return sum(
        rule in rules for t in turns for rules in t.get("gate_rejection_rules") or []
    )


def _fmt(value: Any, key: str = "") -> str:
    if key == "blocking_vs_important" and isinstance(value, tuple):
        return f"{value[0]} blocking / {value[1]} important"
    if isinstance(value, tuple) and len(value) == 2:
        a, b = value
        return f"{a}/{b}" + (f" ({100 * a / b:.0f}%)" if b else "")
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return (
            ", ".join(
                f"{k} {(f'{v:.2f}' if isinstance(v, float) else v)}"
                for k, v in value.items()
                if v is not None
            )
            or "-"
        )
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "-"
    return str(value)


def render(sets: dict[str, dict[str, Any]]) -> str:
    """A Markdown table with one column per run set."""
    names = list(sets)
    skip = ("shape_diffs", "critic_mean", "critic_distribution")
    keys = [k for k in next(iter(sets.values())) if k not in skip]
    lines = ["| Measure | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [
        f"| {k} | " + " | ".join(_fmt(sets[n][k], k) for n in names) + " |"
        for k in keys
    ]
    for d in _DIMENSIONS:
        lines.append(
            f"| critic {d} | "
            + " | ".join(
                f"{_fmt(sets[n]['critic_mean'].get(d))} [{_fmt(sets[n]['critic_distribution'].get(d) or {})}]"
                for n in names
            )
            + " |"
        )
    for n in names:
        for request, diff in sets[n]["shape_diffs"].items():
            lines.append(
                f"| shape diff {n}/{request} | {diff} |" + " |" * (len(names) - 1)
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument(
        "--expect-build",
        nargs="*",
        default=["R3"],
        help="request ids that must build with no questions",
    )
    args = parser.parse_args(argv)
    expect = frozenset(args.expect_build)
    sets = {}
    for p in args.folders:
        name = f"{p.parent.name}/{p.name}"
        if name in sets:  # same effort/variant from another run: add the run folder
            name = f"{p.parent.parent.name}/{name}"
        sets[name] = summarize(p, expect)
    print(render(sets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
