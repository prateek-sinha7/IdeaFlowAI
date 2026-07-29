"""model_graded/cli.py — the `graded`/`report` subcommands.

The only module in this branch that imports driver.py, precheck.py,
judge.py, AND report.py together (Component Boundaries) — it's the one
place that knows the full dispatch -> precheck -> (judge) -> (report) shape.

Invoked via ``evals/model_graded/model-graded.sh graded ...`` / ``model-graded.sh
report ...`` — never a bare Python entry point a human is expected to recall
on its own, matching every other script in ``evals/hybrid/``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from evals.model_graded import report as report_mod  # noqa: E402
from evals.model_graded.driver import run_graded_scenario_once  # noqa: E402
from evals.model_graded.judge import grade_run  # noqa: E402
from evals.model_graded.precheck import run_precheck  # noqa: E402
from evals.model_graded.scenario_discovery import (  # noqa: E402
    discover_all_scenarios,
    find_dataset_scenarios,
)


def _has_judge_credentials() -> bool:
    from app.core.config import settings

    import os

    return bool(
        settings.ANTHROPIC_API_KEY
        or settings.AWS_BEARER_TOKEN_BEDROCK
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
        or settings.MISTRAL_API_KEY
    )


def _has_provider_credentials(provider: str) -> bool:
    from app.core.config import settings

    if provider == "mistral":
        return bool(settings.MISTRAL_API_KEY)
    return True  # unrecognized/None provider — let build_model's own error surface


def _next_agent_id(agent_id: str) -> str | None:
    """The agent immediately after ``agent_id`` in ITS pipeline (by real
    ``agents/registry.py`` order — never hardcoded), or ``None`` if
    ``agent_id`` is unknown or is already the pipeline's last step.
    """
    from agents.registry import get_agent_by_id, get_pipeline_agents

    spec = get_agent_by_id(agent_id)
    if spec is None:
        return None
    pipeline = get_pipeline_agents(spec.pipeline_type)
    ids = [s.id for s in pipeline]
    if agent_id not in ids:
        return None
    idx = ids.index(agent_id)
    return ids[idx + 1] if idx + 1 < len(ids) else None


def _combined_precheck(scenario, response: str) -> tuple[bool, str]:
    """The generic precheck AND (if declared) the scenario's custom hook —
    both must pass. Independent checks, combined result (design.md's
    Component Boundaries: precheck.py knows nothing about custom hooks;
    this function is what combines them)."""
    generic_passed, generic_reason = run_precheck(response, scenario.precheck_config)
    if scenario.precheck_module is None:
        return generic_passed, generic_reason
    custom_passed, custom_reason = scenario.precheck_module(response)
    passed = generic_passed and custom_passed
    reason = f"generic: {generic_reason} | custom: {custom_reason}"
    return passed, reason


def _system_prompt_path(agent_id: str) -> str:
    # AgentSpec doesn't carry its own source path, so this follows the
    # documented AGENT.md convention directly (backend/CLAUDE.md "Adding an
    # Agent" — folder name == agent_id).
    return str(_BACKEND / "agents" / "prompts" / agent_id / "AGENT.md")


def _build_run_entry(
    scenario, result, *, run_id: str, provider: str | None, model: str | None
) -> tuple[dict, bool | None, str]:
    """Builds ONE run.json-shaped entry dict for a dispatch (errored or not)
    — pure, no I/O. Returns ``(entry, precheck_passed, precheck_reason)``;
    ``precheck_passed`` is ``None``/reason is ``"errored: ..."`` when the
    dispatch itself errored (nothing to precheck)."""
    system_prompt_path = _system_prompt_path(scenario.agent_id)
    if result.errored:
        precheck_passed, precheck_reason = None, f"errored: {result.error_reason}"
    else:
        precheck_passed, precheck_reason = _combined_precheck(scenario, result.response)

    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id,
        "scenario_id": scenario.id,
        "agent_id": scenario.agent_id,
        "provider": provider,
        "model": model,
        "resolved_model_id": result.resolved_model_id,
        "system_prompt_path": system_prompt_path,
        "system_prompt_hash": report_mod.compute_system_prompt_hash(system_prompt_path),
        "prompt": scenario.prompt,
        "response": result.response,
        "precheck_passed": precheck_passed,
        "precheck_reason": precheck_reason,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
    }
    return entry, precheck_passed, precheck_reason


async def _build_grade_entry(
    scenario,
    result,
    precheck_reason: str,
    *,
    run_id: str,
    judge_provider: str | None,
    judge_model: str | None,
    judge_threshold: int | None,
) -> dict:
    """Grades one dispatch and returns ONE grade.json-shaped entry dict —
    pure aside from the judge call itself, no file I/O."""
    verdict = await grade_run(
        scenario,
        result,
        precheck_reason,
        provider=judge_provider,
        model=judge_model,
        threshold=judge_threshold,
    )
    return {
        "run_id": run_id,
        "judge_provider": judge_provider,
        "judge_model": judge_model,
        "judge_resolved_model_id": verdict.resolved_model_id,
        "judge_threshold": judge_threshold,
        "score": verdict.score,
        "passed": verdict.passed,
        "rationale": verdict.rationale,
        "strengths": verdict.strengths,
        "weaknesses": verdict.weaknesses,
        "errored": verdict.errored,
        "error_reason": verdict.error_reason,
    }


async def _run_one_graded(
    scenario,
    *,
    provider: str | None,
    model: str | None,
    judge: bool,
    judge_provider: str | None,
    judge_model: str | None,
    judge_threshold: int | None,
) -> dict:
    """Runs the driver + combined precheck, optionally the judge. Writes
    ``run.json`` into the run's OWN log folder (always — it's the readable
    record of what was asked/answered, independent of grading) and, when
    ``--judge`` is set, ``grade.json`` alongside it. Returns a small summary
    dict for CLI printing.

    ``provider``/``model`` override the AGENT UNDER TEST's model (distinct
    from ``judge_provider``/``judge_model``, which only ever affect the
    judge call) — driver.run_graded_scenario_once has always accepted these,
    this is just the CLI wiring to reach them."""
    result = await run_graded_scenario_once(scenario, provider=provider, model=model)
    run_dir = Path(result.run_dir)
    run_id = result.run_id

    if result.errored:
        return {
            "run_id": run_id,
            "errored": True,
            "error_reason": result.error_reason,
            "precheck_passed": None,
            "judge_score": None,
        }

    entry, precheck_passed, precheck_reason = _build_run_entry(
        scenario, result, run_id=run_id, provider=provider, model=model
    )
    report_mod.write_run(run_dir, entry)

    summary = {
        "run_id": run_id,
        "errored": False,
        "precheck_passed": precheck_passed,
        "precheck_reason": precheck_reason,
        "judge_score": None,
    }

    if not judge:
        return summary

    grade_entry = await _build_grade_entry(
        scenario,
        result,
        precheck_reason,
        run_id=run_id,
        judge_provider=judge_provider,
        judge_model=judge_model,
        judge_threshold=judge_threshold,
    )
    summary["judge_score"] = grade_entry["score"]
    summary["judge_passed"] = grade_entry["passed"]
    summary["judge_errored"] = grade_entry["errored"]

    report_mod.write_grade(run_dir, grade_entry)
    return summary


def _cmd_graded(args: argparse.Namespace) -> int:
    scenarios = discover_all_scenarios()
    if args.scenario_id not in scenarios:
        print(
            f"Unknown scenario '{args.scenario_id}' (known: {sorted(scenarios)})",
            file=sys.stderr,
        )
        return 1
    scenario = scenarios[args.scenario_id]

    if args.provider and not _has_provider_credentials(args.provider):
        print(
            f"--provider {args.provider!r} was requested but its credential "
            f"is not set — failing before dispatching to the agent under test.",
            file=sys.stderr,
        )
        return 1

    if args.judge and not _has_judge_credentials():
        print(
            "--judge requested but no usable judge credential resolves "
            "(ANTHROPIC_API_KEY / Bedrock / MISTRAL_API_KEY) — "
            "failing before spending any tokens on the run itself.",
            file=sys.stderr,
        )
        return 1

    passed = 0
    judge_passed = 0
    errored = 0
    n = args.samples

    for i in range(1, n + 1):
        outcome = asyncio.run(
            _run_one_graded(
                scenario,
                provider=args.provider,
                model=args.model,
                judge=args.judge,
                judge_provider=args.judge_provider,
                judge_model=args.judge_model,
                judge_threshold=args.judge_threshold,
            )
        )
        if outcome["errored"]:
            errored += 1
            print(f"  [{i}/{n}] ERROR — {outcome['error_reason']}")
            continue
        status = "PASS" if outcome["precheck_passed"] else "MISS"
        if outcome["precheck_passed"]:
            passed += 1
        line = f"  [{i}/{n}] precheck={status}"
        if args.judge:
            line += f" judge_score={outcome['judge_score']}"
            if outcome.get("judge_passed"):
                judge_passed += 1
        print(line)

    scored = n - errored
    print(f"\nprecheck pass rate: {passed}/{scored if scored else 0}")
    if args.judge:
        print(f"judge pass rate: {judge_passed}/{scored if scored else 0}")
    return 0


async def _run_one_for_dataset(
    scenario,
    *,
    run_dir: Path,
    provider: str | None,
    model: str | None,
    judge: bool,
    judge_provider: str | None,
    judge_model: str | None,
    judge_threshold: int | None,
) -> tuple[dict, dict | None]:
    """Runs one dataset item's dispatch + combined precheck, optionally the
    judge — builds the run/grade entry DICTS but writes NOTHING to disk
    (the caller collects every item's entries and writes them as ONE array
    each, into ONE run folder, at the end). Mirrors ``_run_one_graded``'s
    logic exactly, minus the per-scenario file writes.

    ``run_dir`` is the ONE shared folder for the whole dataset invocation —
    passed straight through to the driver so every item's transcript lands
    in it too (as ``log-<scenario_id>.txt``) instead of each dispatch
    getting its own fresh folder."""
    result = await run_graded_scenario_once(
        scenario,
        provider=provider,
        model=model,
        run_dir=run_dir,
        log_filename=f"log-{scenario.id}.txt",
    )
    run_id = result.run_id

    run_entry, _precheck_passed, precheck_reason = _build_run_entry(
        scenario, result, run_id=run_id, provider=provider, model=model
    )

    if result.errored or not judge:
        grade_entry = None
        if result.errored and judge:
            # Still one grade.json entry per dataset item (even a skipped
            # one) — errored dispatches never reach the judge, but the
            # array stays aligned 1:1 with run.json / the dataset.
            grade_entry = {
                "run_id": run_id,
                "judge_provider": judge_provider,
                "judge_model": judge_model,
                "judge_resolved_model_id": "unknown",
                "judge_threshold": judge_threshold,
                "score": None,
                "passed": False,
                "rationale": f"skipped — dispatch errored: {result.error_reason}",
                "strengths": [],
                "weaknesses": [],
                "errored": True,
                "error_reason": result.error_reason,
            }
        return run_entry, grade_entry

    grade_entry = await _build_grade_entry(
        scenario,
        result,
        precheck_reason,
        run_id=run_id,
        judge_provider=judge_provider,
        judge_model=judge_model,
        judge_threshold=judge_threshold,
    )
    return run_entry, grade_entry


def _cmd_dataset(args: argparse.Namespace) -> int:
    """Runs EVERY scenario in one dataset file (``<dataset_name>.json``,
    default ``dataset.json``, paired with the agent's ``_template.yaml``) as
    ONE run: a single log folder gets ONE ``run.json`` (a JSON array, one
    entry per dataset item), ONE ``grade.json`` (same shape, when
    ``--judge`` is set), and ONE ``score.json`` with the per-item scores +
    the average — all living together, rather than a separate run folder
    per dataset item. Complements ``graded <scenario-id>``, which runs a
    single scenario.
    """
    try:
        dataset_scenarios = sorted(
            find_dataset_scenarios(args.agent_id, args.dataset_name), key=lambda s: s.id
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.provider and not _has_provider_credentials(args.provider):
        print(
            f"--provider {args.provider!r} was requested but its credential "
            f"is not set — failing before dispatching to the agent under test.",
            file=sys.stderr,
        )
        return 1

    if args.judge and not _has_judge_credentials():
        print(
            "--judge requested but no usable judge credential resolves "
            "(ANTHROPIC_API_KEY / Bedrock / MISTRAL_API_KEY) — "
            "failing before spending any tokens on the run itself.",
            file=sys.stderr,
        )
        return 1

    n = len(dataset_scenarios)
    run_id = f"{time.strftime('%y%m%d%H%M%S', time.gmtime())}-{args.dataset_name}-{args.agent_id}"
    run_dir = report_mod.DEFAULT_LOGS_ROOT / run_id

    run_entries: list[dict] = []
    grade_entries: list[dict] = []
    industry_by_scenario_id: dict[str, str | None] = {s.id: s.industry for s in dataset_scenarios}

    for i, scenario in enumerate(dataset_scenarios, 1):
        run_entry, grade_entry = asyncio.run(
            _run_one_for_dataset(
                scenario,
                run_dir=run_dir,
                provider=args.provider,
                model=args.model,
                judge=args.judge,
                judge_provider=args.judge_provider,
                judge_model=args.judge_model,
                judge_threshold=args.judge_threshold,
            )
        )
        run_entries.append(run_entry)
        if grade_entry is not None:
            grade_entries.append(grade_entry)

        errored = run_entry["precheck_passed"] is None and run_entry["precheck_reason"].startswith(
            "errored:"
        )
        if errored:
            print(f"  [{i}/{n}] {scenario.id}: ERROR — {run_entry['precheck_reason']}")
        else:
            status = "PASS" if run_entry["precheck_passed"] else "MISS"
            line = f"  [{i}/{n}] {scenario.id}: precheck={status}"
            if args.judge and grade_entry is not None:
                line += f" judge_score={grade_entry['score']}"
            print(line)

    report_mod.write_batch_run(run_dir, run_entries)
    if args.judge:
        report_mod.write_batch_grade(run_dir, grade_entries)

    scored = [g["score"] for g in grade_entries if g.get("score") is not None]
    average_score = sum(scored) / len(scored) if scored else None
    precheck_evaluated = [r for r in run_entries if r["precheck_passed"] is not None]
    precheck_passed = sum(1 for r in precheck_evaluated if r["precheck_passed"])

    score_summary = {
        "run_id": run_id,
        "agent_id": args.agent_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenario_count": n,
        "precheck_pass_rate": precheck_passed / len(precheck_evaluated) if precheck_evaluated else None,
        "average_judge_score": average_score,
        "results": [
            {
                "scenario_id": r["scenario_id"],
                "run_id": r["run_id"],
                "precheck_passed": r["precheck_passed"],
                "judge_score": next(
                    (g["score"] for g in grade_entries if g["run_id"] == r["run_id"]), None
                ),
            }
            for r in run_entries
        ],
    }
    report_mod.write_score(run_dir, score_summary)

    # NEXT-STAGE dataset.json: one {id, industry, prompt} entry per
    # non-errored item, where "prompt" is THIS stage's own response — the
    # exact shape load_dataset_scenarios expects, so it can be paired with
    # the next pipeline agent's _template.yaml with zero reformatting
    # (e.g. prototype-specify's output becomes prototype-plan's input).
    next_dataset_entries = [
        {
            "id": r["scenario_id"],
            "industry": industry_by_scenario_id.get(r["scenario_id"]),
            "prompt": r["response"],
        }
        for r in run_entries
        if not (r["precheck_passed"] is None and r["precheck_reason"].startswith("errored:"))
    ]
    next_agent_id = _next_agent_id(args.agent_id)
    if next_dataset_entries:
        report_mod.write_dataset(run_dir, next_dataset_entries)

    print(f"\nran {n} scenario(s) for agent '{args.agent_id}' as one run: {run_id}")
    print(
        f"precheck pass rate: {precheck_passed}/{len(precheck_evaluated) if precheck_evaluated else 0}"
    )
    if args.judge:
        print(f"average judge score: {average_score}")
    written = f"{run_dir}/run.json" + (" + grade.json" if args.judge else "") + " + score.json"
    if next_dataset_entries:
        written += " + dataset.json"
        next_note = (
            f" for next agent '{next_agent_id}'"
            if next_agent_id
            else " (no known next agent in the pipeline — still written for manual use)"
        )
        print(f"next-stage dataset.json written{next_note}: {len(next_dataset_entries)} entries")
    print(f"written to: {written}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    entries = report_mod.load_run_entries()
    if args.worst is not None:
        for entry in report_mod.worst(entries, args.worst):
            print(f"--- {entry['run_id']} (score={entry['judge_score']}) ---")
            print(
                f"agent model: {entry.get('resolved_model_id')}  "
                f"judge model: {entry.get('judge_resolved_model_id')}"
            )
            print(f"prompt: {entry['prompt'][:200]}")
            for weakness in entry.get("judge_weaknesses") or []:
                print(f"  weakness: {weakness}")
            for strength in entry.get("judge_strengths") or []:
                print(f"  strength: {strength}")
            print(f"rationale: {entry['judge_rationale']}")
            print(f"full run: {entry['run_dir']}/run.json + grade.json")
            print()
        return 0

    group_by = args.by or "agent_id"
    summary = report_mod.summarize(entries, group_by=group_by, last_n=args.last, target=args.target)
    print(f"total graded runs: {summary['total']}")
    print(f"precheck pass rate: {summary['precheck_pass_rate']}")
    print(f"judge pass rate: {summary['judge_pass_rate']}")
    print(f"avg judge score: {summary['avg_judge_score']}")
    for key, group in summary["groups"].items():
        line = f"  {group_by}={key}: avg_score={group['avg_judge_score']} n={group['total']}"
        if "target_met" in group:
            line += f" [{'TARGET MET' if group['target_met'] else 'TARGET NOT MET'}]"
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model_graded")
    sub = parser.add_subparsers(dest="command", required=True)

    graded = sub.add_parser("graded")
    graded.add_argument("scenario_id")
    graded.add_argument(
        "--provider",
        default=None,
        help="Override the AGENT UNDER TEST's provider (e.g. 'mistral'). "
        "Distinct from --judge-provider, which only affects grading.",
    )
    graded.add_argument("--model", default=None, help="Override the agent under test's model id.")
    graded.add_argument("--judge", action="store_true")
    graded.add_argument("--samples", type=int, default=1)
    graded.add_argument("--judge-provider", default=None)
    graded.add_argument("--judge-model", default=None)
    graded.add_argument("--judge-threshold", type=int, default=None)
    graded.set_defaults(func=_cmd_graded)

    dataset = sub.add_parser("dataset")
    dataset.add_argument("agent_id")
    dataset.add_argument(
        "dataset_name",
        nargs="?",
        default="dataset",
        help="Dataset file basename (without .json) under the agent's scenarios/ folder — "
        "defaults to 'dataset' (dataset.json). Pass e.g. 'dataset_small' to load "
        "scenarios/dataset_small.json instead.",
    )
    dataset.add_argument(
        "--provider",
        default=None,
        help="Override the AGENT UNDER TEST's provider (e.g. 'mistral'). "
        "Distinct from --judge-provider, which only affects grading.",
    )
    dataset.add_argument("--model", default=None, help="Override the agent under test's model id.")
    dataset.add_argument("--judge", action="store_true")
    dataset.add_argument("--judge-provider", default=None)
    dataset.add_argument("--judge-model", default=None)
    dataset.add_argument("--judge-threshold", type=int, default=None)
    dataset.set_defaults(func=_cmd_dataset)

    report_cmd = sub.add_parser("report")
    report_cmd.add_argument("--last", type=int, default=None)
    report_cmd.add_argument("--worst", type=int, default=None)
    report_cmd.add_argument("--by", default=None)
    report_cmd.add_argument("--target", type=int, default=None)
    report_cmd.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
