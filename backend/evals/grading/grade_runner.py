"""CLI entry point: parse args, pick a track, print the summary, set exit code.

The only module that bootstraps sys.path, and the only one that prints. Holds no
grading logic — it dispatches to model_grader, code_grader or compare and formats
what comes back.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import textwrap
import webbrowser
from pathlib import Path

import frontmatter

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import app.core.config  # noqa: E402

from evals.grading import (  # noqa: E402
    artifacts,
    calibrate,
    compare,
    config,
    markdown_report,
    render,
)
from evals.grading.code import code_grader  # noqa: E402
from evals.grading.model import (  # noqa: E402
    judge,
    model_grader,
    prompt_advisor,
    prompt_edits,
)

# Column layouts, so a width change is one edit and the two tables stay aligned
# with each other down the page. `(header, width, align)`; FLEXIBLE trails.
# Plain words, not internals: "dispatch" and "judge" are what the code calls
# these; "runs" and "graded" are what they mean to someone reading the output.
PLAN_COLUMNS = [
    ("step", 20, "<"), ("briefs", 7, ">"), ("runs", 6, ">"), ("graded", 8, ">"),
    ("", render.FLEXIBLE, "<"),
]
DIMENSION_COLUMNS = [
    ("dimension", 26, "<"), ("n", 4, ">"), ("mean", 8, ">"), ("median", 8, ">"),
    ("stddev", 8, ">"), ("min", 7, ">"), ("max", 7, ">"),
]
RESULT_COLUMNS = [
    ("step", 20, "<"), ("briefs", 7, ">"), ("graded", 8, ">"), ("well-formed", 13, ">"),
    ("caught", 8, ">"), ("score", 7, ">"), ("spread", 8, ">"), ("distinct", 10, ">"),
    ("verdict", render.FLEXIBLE, "<"),
]

JUDGE_CREDENTIAL_ENV = (
    "ANTHROPIC_API_KEY",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_PROFILE",
    "MISTRAL_API_KEY",
)

# Distinguishable so a script can tell "you typed it wrong" from "the run said no".
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BASELINE_FAIL = 3
EXIT_JUDGE_PREFLIGHT = 4
EXIT_NO_CREDENTIALS = 5
EXIT_RUN_FAILED = 6
# apply-advice only. 9 and 10 differ on purpose: an edit that cannot be applied
# aborts everything, because the other edits may depend on text it would have
# changed; a refused frontmatter edit is skipped and the rest still apply,
# because it was never going to touch the body.
EXIT_EDIT_FAILED = 9
EXIT_ALL_REFUSED = 10

# `backend/agents/prompts/` — the live prompts. Module-level so a test can point
# it somewhere harmless; nothing else in this package writes outside `.runs/`.
AGENTS_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agents" / "prompts"

# Every run-config key a CLI flag can override, and the section it belongs to.
# `--provider/--model` are the AGENT UNDER TEST; `--judge-*` are the GRADER.
TOP_LEVEL_FLAGS = ("workflow", "dataset", "agents", "from_run", "rows", "limit")
AGENT_FLAGS = {"provider": "provider", "model": "model"}
JUDGE_FLAGS = {"judge_provider": "provider", "judge_model": "model", "judge_threshold": "threshold"}


def has_judge_credentials() -> bool:
    """True if any provider credential resolves — checked before spending."""
    return any(os.environ.get(name) for name in JUDGE_CREDENTIAL_ENV)


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface: model / code / report / compare, plus --config.

    --provider/--model target the AGENT UNDER TEST; --judge-* target the grader
    only. They are strictly separate axes and must never be conflated.
    """
    parser = argparse.ArgumentParser(
        prog="grade_runner",
        description="Grade a workflow's agents. Every model command is LIVE and spends tokens.",
    )
    _add_model_flags(parser, suppress=False)
    subparsers = parser.add_subparsers(dest="command")

    _add_model_parser(subparsers)
    _add_code_parser(subparsers)
    _add_rejudge_parser(subparsers)
    _add_advise_parser(subparsers)
    _add_apply_advice_parser(subparsers)
    _add_revert_parser(subparsers)
    _add_calibrate_parser(subparsers)
    _add_report_parser(subparsers)
    _add_compare_parser(subparsers)
    _add_dashboard_parser(subparsers)
    return parser


def _add_model_flags(parser, *, suppress: bool) -> None:
    """Add every model-track flag to a parser.

    Given to BOTH the top-level parser and the `model` subcommand, so the short
    `--config <path>` form is exactly as previewable as the long one. On the
    subcommand the defaults are SUPPRESSed, which leaves a flag given before the
    subcommand intact instead of overwriting it with a default.
    """
    value = argparse.SUPPRESS if suppress else None
    flag = argparse.SUPPRESS if suppress else False
    parser.add_argument("--config", metavar="PATH", default=value,
                        help="run config YAML with every setting")
    parser.add_argument("--agents", default=value,
                        help="'all' or a comma-separated list of agent ids")
    parser.add_argument("--from-run", dest="from_run", metavar="ID", default=value,
                        help="extend this run folder")
    parser.add_argument("--replace", action="store_true", default=flag,
                        help="supersede a stage's artifacts")
    parser.add_argument("--rows", default=value, help="comma-separated row ids")
    parser.add_argument("--limit", type=int, default=value, help="first N rows only")
    parser.add_argument("--no-judge", dest="no_judge", action="store_true", default=flag,
                        help="precheck only")
    parser.add_argument("--no-code", dest="no_code", action="store_true", default=flag,
                        help="skip the automatic post-run code checks")
    parser.add_argument("--no-advise", dest="no_advise", action="store_true", default=flag,
                        help="skip the automatic post-run prompt advice (one model call per stage)")
    parser.add_argument("--propagate-negative", dest="propagate_negative",
                        action="store_true", default=flag,
                        help="let expect:fail rows flow through the whole chain "
                             "(generated and prechecked at every stage, never judged)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=flag,
                        help="print the plan and stop, no model calls")
    parser.add_argument("--concurrency", type=int, default=value,
                        help="rows in flight within a stage")
    parser.add_argument("--dataset", default=value,
                        help="dataset path, relative to the workflow folder")
    parser.add_argument("--provider", default=value, help="AGENT UNDER TEST provider")
    parser.add_argument("--model", default=value, help="AGENT UNDER TEST model id")
    parser.add_argument("--judge-provider", dest="judge_provider", default=value,
                        help="GRADER provider")
    parser.add_argument("--judge-model", dest="judge_model", default=value, help="GRADER model id")
    parser.add_argument("--judge-threshold", dest="judge_threshold", type=float, default=value,
                        help="GRADER pass mark")


def _add_model_parser(subparsers) -> None:
    """The live model track: dispatch each stage's rows and judge the responses."""
    model = subparsers.add_parser("model", help="run the model track (LIVE)")
    model.add_argument("workflow", nargs="?", help="workflow id, e.g. prototype")
    _add_model_flags(model, suppress=True)


def _add_code_parser(subparsers) -> None:
    """The free code track: deterministic checks over an existing run folder."""
    code = subparsers.add_parser("code", help="run the code track over a run folder (free)")
    code.add_argument("workflow", help="workflow id, e.g. prototype")
    code.add_argument("--from-run", dest="from_run", metavar="ID", required=True)
    code.add_argument("--no-render", dest="no_render", action="store_true",
                      help="skip the headless-Chromium render + nav checks")
    code.add_argument("--no-interactions", dest="no_interactions", action="store_true",
                      help="skip the button/filter interaction sweep")


def _add_rejudge_parser(subparsers) -> None:
    """Re-judge a run's stored responses: judge tokens only, no agent dispatch."""
    parser = subparsers.add_parser(
        "rejudge", help="re-score a run's stored outputs with the judge (judge tokens only)"
    )
    parser.add_argument("dataset_run_id")
    parser.add_argument("--workflow", default=config.DEFAULTS["workflow"])
    parser.add_argument("--agents", default=None,
                        help="comma-separated agent ids (default: every captured stage)")
    parser.add_argument("--concurrency", type=int, default=None,
                        help="rows in flight (default: the run's own setting)")
    parser.add_argument("--judge-provider", dest="judge_provider", default=None)
    parser.add_argument("--judge-model", dest="judge_model", default=None)
    parser.add_argument("--judge-threshold", dest="judge_threshold", type=float, default=None)


def _add_advise_parser(subparsers) -> None:
    """Ingest a run's reports and propose prompt deltas — one model call per stage."""
    parser = subparsers.add_parser(
        "advise", help="propose prompt edits from a run's evidence (one model call per stage)"
    )
    parser.add_argument("dataset_run_id")
    parser.add_argument("--workflow", default=config.DEFAULTS["workflow"])
    parser.add_argument("--agents", default=None,
                        help="comma-separated agent ids (default: every graded stage)")
    parser.add_argument("--judge-provider", dest="judge_provider", default=None)
    parser.add_argument("--judge-model", dest="judge_model", default=None)


def _add_apply_advice_parser(subparsers) -> None:
    """Apply a run's advice to the agent's AGENT.md. Free — no model call."""
    parser = subparsers.add_parser(
        "apply-advice",
        help="apply a run's prompt advice to AGENT.md, archiving the old body (free)",
    )
    parser.add_argument("dataset_run_id")
    parser.add_argument("--agent", required=True, help="the agent whose prompt to edit")
    parser.add_argument("--workflow", default=config.DEFAULTS["workflow"])


def _add_revert_parser(subparsers) -> None:
    """Undo the last apply-advice by restoring the newest archived body. Free."""
    parser = subparsers.add_parser(
        "revert", help="restore an agent's previous prompt from its newest archive (free)"
    )
    parser.add_argument("agent")
    parser.add_argument("--workflow", default=config.DEFAULTS["workflow"])


def _add_calibrate_parser(subparsers) -> None:
    """Prove the scale still ranks known-good above known-bad (LIVE judge calls)."""
    parser = subparsers.add_parser(
        "calibrate",
        help="grade the golden + fail fixtures and assert the scale is not inverted (LIVE)",
    )
    parser.add_argument("--workflow", default=config.DEFAULTS["workflow"])


def _add_report_parser(subparsers) -> None:
    """Read one run folder back: aggregates, weaknesses, worst rows. Free."""
    report = subparsers.add_parser("report", help="print one run's results (free)")
    report.add_argument("dataset_run_id")
    report.add_argument("--workflow", default=config.DEFAULTS["workflow"])
    report.add_argument("--worst", type=int, metavar="N", help="also print the N lowest rows")


def _add_dashboard_parser(subparsers) -> None:
    """Render every run folder as one browsable static site. Free, no model."""
    dashboard = subparsers.add_parser(
        "dashboard", help="rebuild the HTML dashboard over every run (free)"
    )
    dashboard.add_argument("--workflow", default=config.DEFAULTS["workflow"])
    dashboard.add_argument(
        "--force", action="store_true", help="re-render every run, ignoring the mtime skip"
    )
    dashboard.add_argument(
        "--export", metavar="RUN_ID", help="also write that run's single-file export"
    )
    dashboard.add_argument(
        "--open", dest="open_browser", action="store_true",
        help="open the dashboard in the default browser when it is built",
    )


def _add_compare_parser(subparsers) -> None:
    """Delta two runs, or group every run of one agent by prompt version. Free."""
    compare_parser = subparsers.add_parser("compare", help="compare runs (free)")
    compare_parser.add_argument("first", nargs="?", help="run-a, or the workflow with --by-prompt")
    compare_parser.add_argument("second", nargs="?", help="run-b, or the agent with --by-prompt")
    compare_parser.add_argument(
        "--by-prompt", dest="by_prompt", action="store_true", help="group runs by prompt version"
    )
    compare_parser.add_argument("--workflow", default=config.DEFAULTS["workflow"])
    compare_parser.add_argument("--agent", help="which stage to compare (default: the first found)")


# ── argument translation ──────────────────────────────────────────────────


def _flag(args, name):
    """One optional flag's value, absent on the subcommands that never define it."""
    return getattr(args, name, None)


def _split(value):
    """`a,b` -> ['a', 'b']; None stays None so it is not treated as an override."""
    if value is None:
        return None
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _parse_agents(value):
    """`all` stays the string; anything else becomes an explicit agent list."""
    if value is None:
        return None
    return "all" if value.strip() == "all" else _split(value)


def _section(mapping: dict, args) -> dict:
    """One nested run-config section, holding only the flags actually passed."""
    values = {}
    for flag, key in mapping.items():
        value = _flag(args, flag)
        if value is not None:
            values[key] = value
    return values


def cli_overrides(args) -> dict:
    """Every CLI flag that was actually passed, in run-config shape.

    Only passed flags are included: an unset flag must not be recorded as an
    override of the config file it never contradicted.
    """
    overrides: dict = {}
    for name in TOP_LEVEL_FLAGS:
        value = _flag(args, name)
        if name == "agents":
            value = _parse_agents(value)
        elif name == "rows":
            value = _split(value)
        if value is not None:
            overrides[name] = value

    under_test = _section(AGENT_FLAGS, args)
    if under_test:
        overrides["agent_under_test"] = under_test
    grader = _section(JUDGE_FLAGS, args)
    if grader:
        overrides["judge"] = grader

    options = {}
    if _flag(args, "concurrency") is not None:
        options["concurrency"] = args.concurrency
    if _flag(args, "no_judge"):
        options["no_judge"] = True
    if _flag(args, "no_code"):
        options["code_grading"] = False
    if _flag(args, "no_advise"):
        options["advise"] = False
    if _flag(args, "propagate_negative"):
        options["propagate_negative"] = True
    if options:
        overrides["options"] = options
    return overrides


# ── judge preflight ───────────────────────────────────────────────────────


def configured_providers() -> tuple[list[str], list[str]]:
    """Which judge providers this machine can actually reach, and which it cannot."""
    settings = app.core.config.settings
    bedrock_id = settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID
    available = {
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "bedrock": bool(bedrock_id and settings.AWS_REGION and not settings.ANTHROPIC_API_KEY),
        "mistral": bool(settings.MISTRAL_API_KEY),
    }
    labels = {"bedrock": f"bedrock ({bedrock_id})" if bedrock_id else "bedrock"}
    configured = [labels.get(name, name) for name, ok in available.items() if ok]
    missing = [name for name, ok in available.items() if not ok]
    return configured, missing


def preflight_judge(plan: dict) -> str | None:
    """Resolve every stage's judge BEFORE the first dispatch; message on failure.

    `judge.resolve_judge_model` hard-fails on a provider build_model cannot
    honour. Left until grade time that failure lands after every agent dispatch
    has already been paid for, so it is asserted here, for free, instead.
    """
    for stage in plan.get("stages") or []:
        if not stage.get("judge_calls"):
            continue
        try:
            judge.resolve_judge_model(stage.get("judge") or {})
        except Exception as error:  # noqa: BLE001 - any judge build failure must stop the run
            return _preflight_message(stage, error)
    return None


def _preflight_message(stage: dict, error: Exception) -> str:
    """The actionable failure: what is pinned, what broke, what IS configured."""
    judge_config = stage.get("judge") or {}
    configured, missing = configured_providers()
    return "\n".join(
        [
            f"judge preflight FAILED for stage '{stage['agent_id']}' — "
            "nothing was dispatched and nothing was spent.",
            "",
            f"  pinned judge     provider={judge_config.get('provider')!r} "
            f"model={judge_config.get('model')!r} threshold={judge_config.get('threshold')!r}",
            f"  problem          {error}",
            f"  configured here  {', '.join(configured) or 'none'}",
            f"  not configured   {', '.join(missing) or 'none'}",
            "",
            "  Fix it one of two ways:",
            "    - set the missing credential for the pinned provider, or",
            "    - grade with a provider that is configured, e.g.",
            "        --judge-provider mistral --judge-model <model-id>",
            "      (--judge-* moves the GRADER only; the agent under test is unchanged)",
        ]
    )


# ── printing: the model track ─────────────────────────────────────────────


def _print_rule(title: str, width: int = 88) -> None:
    """Print a titled rule — where this module turns render's string into output."""
    print(render.rule(title, width))


def print_dry_run(plan: dict) -> None:
    """The resolved plan as `plan` shows it — nothing is dispatched after this."""
    print_plan_header(plan, title="plan")


def print_plan_header(plan: dict, *, title: str = "grading") -> None:
    """State the blast radius: identity, models, every stage, and the spend.

    Live runs and `plan` print the SAME thing, deliberately — a preview whose
    shape differs from the real run is not a preview. Stages that will not run
    are listed rather than counted, because "why did stage 4 produce nothing"
    is the question this table exists to answer before you ask it.
    """
    stages = plan["stages"]
    models = stages[0] if stages else {}
    _print_rule(title, 88)
    print(f"  run        {plan['run_id']}  ·  {plan['workflow']}  ·  {plan['dataset_run_id']}")
    print(
        f"  models     {render.model_label(models.get('model_under_test'))}"
        f"  does the work  ·  {render.model_label(models.get('judge'))}  grades it"
    )
    print(f"  briefs     {plan['dataset_id']}  ·  {render.plural(plan['row_count'], 'brief')}")
    print("")
    rows = [
        [stage["agent_id"], stage["rows"], stage["dispatches"], stage["judge_calls"],
         _stage_note(stage, models)]
        for stage in stages
    ]
    rows += [
        [stage["agent_id"], render.DASH, render.DASH, render.DASH,
         stage.get("reason") or f"not run ({stage['declared_status']})"]
        for stage in plan["not_run"]
    ]
    for line in render.table(PLAN_COLUMNS, rows):
        print(line)
    _print_annotations(stages)
    print(f"\n  cost       {_estimate_line(plan)}")


def _print_annotations(stages: list) -> None:
    """Explain the table, splitting what is BY DESIGN from what wants attention.

    A negative-test row being withheld downstream is the eval working; listing
    it under `notes` put expected behaviour in the place reserved for problems,
    and a block that always has something in it stops being read.
    """
    by_design: dict[str, int] = {}
    attention: list[str] = []
    for stage in stages:
        if stage.get("note"):
            attention.append(f"{stage['agent_id']} — {stage['note']}")
        for skipped in stage["skipped"]:
            if skipped.get("by_design"):
                by_design[skipped["row_id"]] = by_design.get(skipped["row_id"], 0) + 1
            else:
                attention.append(
                    f"{stage['agent_id']} — {skipped['row_id']}: {skipped['reason']}"
                )

    if by_design:
        print("")
    for row_id, count in by_design.items():
        print(_wrapped_note(
            f"'{row_id}' is a deliberately bad brief. It is sent to the first step to "
            f"check the agent pushes back on it, then held there — so it never reaches "
            f"the {render.plural(count, 'step')} after it. That is why the first "
            f"step above runs more briefs than the rest."
        ))
    if attention:
        print("\n  notes")
        for text in attention:
            print(_wrapped_note(text))


def _wrapped_note(text: str) -> str:
    """One note, wrapped and indented — never truncated mid-sentence.

    The clause that says what to do about a note is routinely past column 80.
    """
    return textwrap.fill(text, width=86, initial_indent="    ", subsequent_indent="      ")


def _stage_note(stage: dict, first: dict) -> str:
    """`ready`, or this stage's own models when they differ from the header's.

    Rubrics pin their judge per agent, so one stage can resolve a different
    model than the rest. Saying so only when it happens keeps the common case
    quiet without ever hiding a mixed-model run.
    """
    same_agent = stage.get("model_under_test") == first.get("model_under_test")
    same_judge = stage.get("judge") == first.get("judge")
    if same_agent and same_judge:
        return "will run"
    return f"{render.model_label(stage['model_under_test'])} → {render.model_label(stage['judge'])}"


def _estimate_line(plan: dict) -> str:
    """`N agent + M judge = T model calls` — the number that costs money."""
    estimate = plan["dispatch_estimate"]
    advice = estimate.get("advice_calls") or 0
    advice_part = f" + {advice} to advise on the prompts" if advice else ""
    return (
        f"{estimate['agent_calls']} AI calls to do the work + "
        f"{estimate['judge_calls']} to grade it{advice_part} "
        f"= {render.plural(estimate['total'], 'AI call')} in total"
    )




def print_overrides(run_config) -> None:
    """State every CLI flag that diverged from the config file it was given."""
    if not run_config.overrides:
        return
    print("  overrides (this run is NOT reproducible from its config file alone):")
    for name, values in sorted(run_config.overrides.items()):
        print(f"    {name}: {values['config']!r} -> {values['cli']!r}")


def print_progress(event: dict) -> None:
    """Print one live progress line so a long run is never silently quiet.

    Rows run concurrently, so a row's start and finish do not always adjoin —
    each line carries the row id and its position to stay readable when they
    interleave. Flushed every line: without it, output is buffered when piped
    and the run looks hung for minutes.
    """
    kind = event.get("event")
    if kind == "stage_start":
        _print_rule(f"{event['agent_id']}  ·  {render.plural(event['rows'], 'row')}")
    elif kind == "row_phase" and event["phase"] in ("generating", "judging"):
        # Only the two phases that take real time are printed. Precheck is
        # sub-millisecond, and its result already shows up in the done line.
        print(f"  ⋯ {_position(event)} {event['row_id']:<24}{event['phase']}…", flush=True)
    elif kind == "row_done":
        print(_row_line(event), flush=True)
    elif kind == "phase_start":
        _print_phase_start(event)
    elif kind == "phase_done":
        _print_phase_done(event)
    elif kind == "advice_stage_start":
        # The advisor runs one stage at a time and each is a full model call;
        # without this the terminal sits blank between the code checks and the
        # results table.
        print(f"  ⋯ {event.get('agent_id', ''):<24}advising…", flush=True)
    elif kind == "advice_stage_done":
        print(_advice_line(event), flush=True)


# What each post-model phase is called on screen, and the one line explaining
# what it is about to do. Both phases were previously silent — the code checks
# for minutes while a browser ran, the advisor while it called a model.
PHASE_TITLES = {
    "code": (
        "code checks",
        "static analysis + a real browser: every nav link clicked, every visible "
        "button and filter exercised",
    ),
    "advice": (
        "prompt advice",
        "one model call per phase, reading its judge weaknesses and code findings "
        "to propose a prompt delta",
    ),
}


def _print_phase_start(event: dict) -> None:
    """Announce a post-model phase before it runs, naming what it will cover."""
    phase = str(event.get("phase") or "")
    title, explanation = PHASE_TITLES.get(phase, (phase, ""))
    agent_ids = event.get("agent_ids") or []
    _print_rule(f"{title}  ·  {render.plural(len(agent_ids), 'phase')}")
    if explanation:
        print(_wrapped_note(explanation))
    if event.get("phase") == "code":
        # The code grader has no per-stage callback, so this is the only chance
        # to say WHICH stages are being checked before the wait starts.
        print(f"  ⋯ checking {', '.join(agent_ids)}…", flush=True)


def _print_phase_done(event: dict) -> None:
    """Close a post-model phase — the code track's results land here in one go."""
    if event.get("phase") != "code":
        return
    result = event.get("result") or {}
    if result.get("status") == "errored":
        print(_wrapped_note(f"✖  did not run: {result.get('reason')}"), flush=True)
        return
    for stage in result.get("stages") or []:
        print(
            f"  ✔ {stage['agent_id']:<24}"
            f"{render.score(stage.get('average_code_score')):>6}   "
            f"rows ok {stage.get('rows_ok')} / {stage.get('rows_checked')}",
            flush=True,
        )


def _advice_line(event: dict) -> str:
    """One advised phase: what it proposed, or why it produced nothing."""
    agent_id = event.get("agent_id", "")
    if event.get("status") == "errored":
        return f"  ✖ {agent_id:<24}ERROR {render.truncate(event.get('error_reason'), 40)}"
    tokens = (event.get("tokens_in") or 0) + (event.get("tokens_out") or 0)
    return (
        f"  ✔ {agent_id:<24}"
        f"{event.get('edits', 0)} edit(s) · {event.get('deviations', 0)} deviation(s)"
        f"   {render.tokens(tokens)} tokens"
    )


def _position(event: dict) -> str:
    """`n/N` padded, so interleaved concurrent rows stay in one column."""
    return f"{event['index']}/{event['total']}".ljust(6)


def _row_line(event: dict) -> str:
    """One finished row: glyph, id, score, token split, and any exception.

    The glyph carries the verdict so the common case needs no words: ✔ graded,
    ✖ something failed, · dispatched but deliberately not judged.
    """
    glyph, note = _row_verdict(event)
    score = render.score(event.get("score"))
    line = f"  {glyph} {_position(event)} {event['row_id']:<24}{score:>6}   {_row_tokens(event)}"
    return f"{line}   {note}".rstrip() if note else line.rstrip()



def _row_verdict(event: dict) -> tuple[str, str]:
    """The row's glyph and the short note explaining it, empty when unremarkable."""
    if event.get("skipped"):
        return "·", f"skipped — {event.get('skip_reason')}"
    if event.get("errored"):
        return "✖", f"ERROR {render.truncate(event.get('error_reason'), 40)}"
    if event.get("judge_errored"):
        # The row cost agent AND judge tokens and produced no score. Saying only
        # "precheck pass" here is what made a dead judge look like a healthy run.
        return "✖", f"JUDGE FAILED {render.truncate(event.get('judge_error_reason'), 34)}"
    if event.get("precheck_passed") is False:
        return "✖", "precheck FAIL"
    if event.get("score") is None:
        return "·", "not judged"
    return "✔", ""


def _row_tokens(event: dict) -> str:
    """`agent 6.2k · judge 6.5k` — the two halves are billed differently."""
    agent = event.get("agent_tokens") or 0
    judge_tokens = event.get("judge_tokens") or 0
    if not agent and not judge_tokens:
        return "".ljust(24)  # keep the note column aligned on an errored row
    parts = [f"agent {render.tokens(agent)}"]
    if judge_tokens:
        parts.append(f"judge {render.tokens(judge_tokens)}")
    return " · ".join(parts).ljust(24)




def print_run_result(result: dict) -> None:
    """Print the closing summary: per-stage headlines, spend, and where to read more.

    Deliberately short. The dimension tables, the per-row sub-scores and the
    judge's full narrative all go to REPORT.md — printing them here buried the
    two numbers that decide what you do next.
    """
    summary = result["summary"]
    stages = [
        stage for stage in summary["stages"] if stage.get("status") not in (None, "not_run")
    ]
    _print_rule("results", 88)
    _print_stage_table(stages, result)
    _print_verdict_key(stages)
    _print_signals(stages)
    _print_warnings(stages)
    _print_code_grades(result)
    _print_advice(result)
    _print_grade(result)
    _print_spend(result)
    print(f"  status     {summary['status']}")
    if result.get("report_path"):
        print(f"\n  Full details — every score, weakness and quote — are in:\n  {result['report_path']}")


def _print_stage_table(stages: list, result: dict) -> None:
    """One line per stage — the shape that makes a 5-stage workflow readable.

    Every column answers a different question: did it produce well-formed
    output (precheck), was the negative test caught (negative), how good was it
    (avg), and can the number be trusted at all (stddev, distinct).
    """
    rows = []
    for stage in stages:
        counts = _stage_counts(stage, result)
        rows.append([
            stage["agent_id"],
            counts.get("rows", render.DASH),
            counts.get("judged", 0),
            render.number(stage.get("precheck_pass_rate")),
            render.negative(stage.get("negative_rows_correct")),
            render.score(stage.get("average_all")),
            render.score(stage.get("stddev")),
            stage.get("distinct_score_count", 0),
            stage.get("baseline_verdict"),
        ])
    for line in render.table(RESULT_COLUMNS, rows):
        print(line)


def _print_verdict_key(stages: list) -> None:
    """Spell out REFUSED — it is a defined term that reads like a failure."""
    if not any(stage.get("baseline_verdict") == "REFUSED" for stage in stages):
        return
    print(_wrapped_note(
        "REFUSED means no pass/fail was given, because there is no trusted earlier run "
        "to compare against yet. Every score above is still real."
    ))


def _print_signals(stages: list) -> None:
    """Show a verdict a stage produced that nothing downstream acts on.

    prototype-analyze decides whether the spec is fit to build. In production a
    human reads that at a gate; here there is no human, so the run proceeds
    regardless. Printing it is the minimum — the alternative is spending tokens
    on an opinion and then discarding it.
    """
    for stage in stages:
        signals = stage.get("signals") or {}
        if not signals:
            continue
        counts = ", ".join(f"{count}× {value}" for value, count in signals["counts"].items())
        print(f"\n  {stage['agent_id']} says: {counts}")
        if signals.get("alert_rows"):
            print(_wrapped_note(
                f"{render.plural(len(signals['alert_rows']), 'brief')} judged NOT ready "
                f"to build ({', '.join(signals['alert_rows'])}) — and the run built anyway. "
                f"Nothing downstream reads this verdict; in production a human does, at a gate."
            ))


def _print_warnings(stages: list) -> None:
    """Every stage's warnings under the table, wrapped rather than truncated.

    A warning exists to be acted on, and the sentence saying what to do about
    one is never inside its first 60 characters.
    """
    for stage in stages:
        for warning in stage.get("warnings") or []:
            print("")
            print(
                textwrap.fill(
                    f"{stage['agent_id']} — {warning}",
                    width=86,
                    initial_indent="  ⚠  ",
                    subsequent_indent="     ",
                )
            )


def _stage_counts(stage: dict, result: dict) -> dict:
    """This stage's row counts, off the score the run already computed."""
    for entry in result.get("stages") or []:
        if entry.get("agent_id") == stage.get("agent_id"):
            return (entry.get("score") or {}).get("counts") or {}
    return {}


def _print_code_grades(result: dict) -> None:
    """The automatic post-run code checks, one line per HTML stage.

    One line, not a table: the full findings are in reports/code_report.md and
    the blended columns are in the top report — this is just the heads-up that
    the free track ran and what it thought.
    """
    code = result.get("code") or {}
    stages = code.get("stages") or []
    if not stages:
        # A failure is said out loud: a silently absent code column reads as
        # "the checks passed with nothing to say", which is the opposite.
        if code.get("status") == "errored":
            print(_wrapped_note(f"⚠  code checks did not run: {code.get('reason')}"))
        return
    parts = [
        f"{stage['agent_id']} {render.score(stage.get('average_code_score'))}"
        for stage in stages
    ]
    print(f"\n  code       {'  ·  '.join(parts)}   (deterministic checks, free)")


def _print_advice(result: dict) -> None:
    """The automatic prompt advice, one line per advised stage.

    Same rule as the code checks: a failure is said out loud rather than
    leaving an absent line to read as "nothing to suggest".
    """
    advice = result.get("advice") or {}
    stages = advice.get("stages") or []
    if not stages:
        if advice.get("status") == "errored":
            print(_wrapped_note(f"⚠  prompt advice did not run: {advice.get('reason')}"))
        return
    parts = []
    for stage in stages:
        if stage.get("errored"):
            parts.append(f"{stage['agent_id']} FAILED")
        else:
            parts.append(f"{stage['agent_id']} {stage.get('edits', 0)} edit(s)")
    print(f"\n  advice     {'  ·  '.join(parts)}   (proposals, in reports/)")


def _print_grade(result: dict) -> None:
    """The run's headline: blended score and letter grade, same as report.md."""
    run_dir = result.get("run_dir")
    if not run_dir:
        return
    try:
        overall = markdown_report.compute_overall(Path(run_dir))
    except Exception:  # noqa: BLE001 - the grade is derived, never load-bearing
        return
    if overall is None:
        return
    failed = overall["failed_cells"]
    note = f"  ·  {failed} cell(s) failed outright" if failed else ""
    print(f"\n  grade      {overall['grade']}  ·  {overall['score']:.1f} / 100{note}")


def _print_spend(result: dict) -> None:
    """The whole run's token spend, split agent vs judge — they cost differently."""
    agent = judge_tokens = 0
    for stage in result.get("stages") or []:
        tokens = (stage.get("score") or {}).get("tokens") or {}
        agent += (tokens.get("agent") or {}).get("total", 0)
        judge_tokens += (tokens.get("judge") or {}).get("total", 0)
    if not agent and not judge_tokens:
        return
    print(
        f"\n  AI usage   {render.tokens(agent + judge_tokens)} tokens"
        f"  ·  {render.tokens(agent)} doing the work"
        f"  ·  {render.tokens(judge_tokens)} grading it"
    )




def _baseline_failures(result: dict) -> list[str]:
    """Every stage whose committed baseline came back FAIL."""
    stages = result["summary"]["stages"]
    return [stage["agent_id"] for stage in stages if stage.get("baseline_verdict") == "FAIL"]


# ── printing: report ──────────────────────────────────────────────────────


def print_stage_report(score: dict, grades: list[dict], worst: int | None) -> None:
    """Print one stage's aggregates, recurring weaknesses and worst rows.

    Styled like the run summary on purpose: `report` is the command you are
    told to run after every eval, so it should not look like a different tool.
    """
    scores = score.get("scores") or {}
    counts = score.get("counts") or {}
    # The agent id, not the artifact token: `prototype_specify` is a filename,
    # `prototype-specify` is what the workflow and every doc call the stage.
    stage_name = score.get("agent_id") or str(score.get("agent_token") or "stage").replace("_", "-")
    _print_rule(stage_name)
    print(
        f"  rows       {counts.get('rows', render.DASH)} · "
        f"{counts.get('judged', 0)} judged · "
        f"precheck {render.number(score.get('precheck_pass_rate'))}"
    )
    print(
        f"  score      avg {render.score(scores.get('average_all'))} · "
        f"avg(passed) {render.score(scores.get('average_precheck_passed'))} · "
        f"stddev {render.score(scores.get('stddev'))}"
    )
    _print_tokens(score.get("tokens") or {})
    # Warnings first: they say whether the numbers ABOVE can be trusted at all,
    # and printing them under `baseline` read as baseline failures.
    for warning in score.get("warnings") or []:
        print(_wrapped_note(f"⚠  {warning}"))
    baseline = score.get("baseline") or {}
    print(f"  baseline   {baseline.get('verdict', 'n/a')}")
    for failure in baseline.get("failures") or []:
        print(_wrapped_note(failure))

    _print_dimensions(score.get("dimensions") or {})
    _print_weaknesses(score.get("recurring_weaknesses") or [])
    if worst:
        _print_worst(score.get("results") or [], grades, worst)


def _print_tokens(tokens: dict) -> None:
    """The stage's spend, split agent vs judge — the two halves cost differently."""
    if not tokens:
        return
    agent = tokens.get("agent") or {}
    judge_tokens = tokens.get("judge") or {}
    line = f"  tokens     {render.tokens(tokens.get('total', 0))} total"
    if agent or judge_tokens:
        line += (
            f"  ·  agent {render.tokens(agent.get('total', 0))}"
            f"  ·  judge {render.tokens(judge_tokens.get('total', 0))}"
        )
    print(line)


def _print_dimensions(dimensions: dict) -> None:
    """Per-dimension aggregates — which paragraph of the AGENT.md to rewrite."""
    if not dimensions:
        return
    print("")
    rows = [
        [
            name, stats.get("count", 0),
            render.score(stats.get("mean")), render.score(stats.get("median")),
            render.score(stats.get("stddev")),
            render.score(stats.get("min")), render.score(stats.get("max")),
        ]
        for name, stats in dimensions.items()
    ]
    for line in render.table(DIMENSION_COLUMNS, rows):
        print(line)


def _print_weaknesses(weaknesses: list[dict]) -> None:
    """The clustered judge criticisms, ranked — the prompt-fix shortlist."""
    if not weaknesses:
        return
    print("\n  recurring weaknesses")
    for cluster in weaknesses:
        row_ids = cluster.get("row_ids") or []
        print(_wrapped_note(f"{render.plural(len(row_ids), 'row')}  {cluster.get('evidence', '')}"))
        print(_wrapped_note(f"        {', '.join(str(row) for row in row_ids)}"))


def _print_worst(results: list[dict], grades: list[dict], worst: int) -> None:
    """The lowest-scoring rows, with the judge's own reasoning for each."""
    by_id = {grade.get("row_id") or grade.get("scenario_id"): grade for grade in grades}
    scored = [row for row in results if row.get("score") is not None]
    ranked = sorted(scored, key=lambda row: row["score"])[:worst]
    if not ranked:
        return
    print("")
    print(f"  worst {len(ranked)} rows")
    for row in ranked:
        grade = by_id.get(row["row_id"], {})
        print(f"    {render.number(row['score']):>7}  {row['row_id']}  precheck={row.get('precheck_passed')}")
        if grade.get("rationale"):
            print(f"             rationale: {grade['rationale']}")
        for weakness in grade.get("weaknesses") or []:
            print(f"             weakness:  {weakness}")
        for name, quote in (grade.get("evidence") or {}).items():
            print(f"             evidence:  {name}: {quote}")


# ── printing: compare ─────────────────────────────────────────────────────


def print_comparison(report: dict) -> None:
    """Print the deltas, labelled with the noise guard's own verdict.

    The verdict string is printed verbatim: a printing layer that decided for
    itself what counts as an improvement would defeat the guard entirely.
    """
    noise = report["noise"]
    _print_rule("compare")
    print(f"  baseline   {report['baseline']['run_id']}")
    if noise["band"]:
        band = noise["band"]
        print(
            f"  noise      \u00b1{band['threshold']:.2f} on {compare.HEADLINE_METRIC} "
            f"(stddev {band['stddev']:.2f} over {band['samples']} samples)"
        )
    else:
        print(f"  noise      {noise['verdict']}")
        print(_wrapped_note(noise["reason"]))

    for comparison in report["comparisons"]:
        print(f"\n  {comparison['run_id']} vs {comparison['against']}  \u2014  "
              f"{comparison['verdict']}")
        _print_deltas("metric", comparison["aggregates"])
        _print_deltas("dimension", comparison["dimensions"])
        _print_row_deltas(comparison)


# Metrics that are RATES, not scores: a rate reads better as 1.00 than as 1.
RATE_METRICS = frozenset({"precheck_pass_rate"})


def _print_deltas(label: str, entries: dict) -> None:
    """One before/after/delta table, each line carrying its own verdict."""
    if not entries:
        return
    print("")
    columns = [
        (label, 26, "<"), ("before", 9, ">"), ("after", 9, ">"), ("delta", 9, ">"),
        ("verdict", render.FLEXIBLE, "<"),
    ]
    rows = []
    for name, entry in entries.items():
        show = render.number if name in RATE_METRICS else render.score
        rows.append(
            [name, show(entry["before"]), show(entry["after"]), show(entry["delta"]),
             entry["verdict"]]
        )
    for line in render.table(columns, rows):
        print(line)


def _print_row_deltas(comparison: dict) -> None:
    """Per-row moves plus the rows that flipped precheck or crossed the threshold."""
    moved = [row for row in comparison["rows"] if row["delta"]]
    if moved:
        print("")
        columns = [
            ("row", 26, "<"), ("before", 9, ">"), ("after", 9, ">"), ("delta", 9, ">"),
        ]
        for line in render.table(columns, [
            [row["row_id"], render.score(row["before"]), render.score(row["after"]),
             render.score(row["delta"])]
            for row in moved
        ]):
            print(line)
    for row in comparison["precheck_flips"]:
        print(f"    precheck {row['precheck_flip']}: {row['row_id']}")
    for row in comparison["threshold_crossings"]:
        print(f"    threshold {row['threshold_cross']}: {row['row_id']}")
    for row_id in comparison["only_in_baseline"]:
        print(f"    only in {comparison['against']}: {row_id}")
    for row_id in comparison["only_in_run"]:
        print(f"    only in {comparison['run_id']}: {row_id}")


def print_prompt_groups(grouped: dict) -> None:
    """Print every prompt version chronologically, with its met/not-met flag."""
    print(f"  baseline prompt {grouped['baseline']}  target average {render.number(grouped['target'])}")
    print("")
    print(f"  {'prompt hash':<24}{'first seen':<22}{'runs':>5}{'average':>9}{'precheck':>10}  target")
    for prompt_hash in grouped["order"]:
        group = grouped["groups"][prompt_hash]
        print(
            f"  {str(prompt_hash)[:22]:<24}{group['first_seen'][:20]:<22}{group['total_runs']:>5}"
            f"{render.number(group['average_score']):>9}{render.number(group['precheck_pass_rate']):>10}"
            f"  {group['target_met']}"
        )


# ── run-folder reading ────────────────────────────────────────────────────


def _runs_root(workflow: dict) -> Path:
    """The `.runs/` folder of a workflow, whether or not it exists yet.

    Delegates to artifacts, which owns every run path. Recomputing it here is
    what made `report` and `compare` look under the workflow folder after runs
    moved to the grading root — they could not find a single real run.
    """
    return artifacts.runs_root(Path(workflow["workflow_dir"]))


def _existing_run_folder(dataset_run_id: str, workflow: dict) -> Path:
    """An existing run folder — never minting one just to read a report from it."""
    run_dir = _runs_root(workflow) / dataset_run_id
    if not run_dir.is_dir():
        raise ValueError(f"no run folder '{dataset_run_id}' under {_runs_root(workflow)}")
    return run_dir


def _stage_tokens(workflow: dict) -> list[str]:
    """Every stage's artifact token, in workflow order."""
    return [stage["agent_id"].replace("-", "_") for stage in workflow["stages"]]


def _graded_tokens(run_dir: Path, workflow: dict) -> list[str]:
    """The stages that actually produced a score artifact in this run folder."""
    return [
        token
        for token in _stage_tokens(workflow)
        if artifacts.artifact_path(run_dir, token, "score").exists()
    ]


def _read_artifact(run_dir: Path, token: str, kind: str):
    """One artifact, or an empty list when this run never wrote that kind."""
    try:
        return artifacts.read_stage_artifact(run_dir, token, kind)
    except FileNotFoundError:
        return []


def _run_payload(run_dir: Path, token: str) -> dict:
    """One run in the shape compare.py reads: identity, hashes and its summary."""
    score = artifacts.read_stage_artifact(run_dir, token, "score")
    hashes = score.get("hashes") or score.get("config_hashes") or {}
    runs = _read_artifact(run_dir, token, "run")
    prompt_hashes = [row.get("system_prompt_hash") for row in runs if row.get("system_prompt_hash")]
    return {
        "dataset_run_id": score.get("dataset_run_id") or run_dir.name,
        "timestamp": score.get("finished_at") or score.get("started_at") or "",
        "config_hash": hashes.get("config_hash"),
        "system_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
        "summary": score,
    }


def _all_run_payloads(workflow: dict, token: str) -> list[dict]:
    """Every run folder of this workflow that graded the given stage."""
    root = _runs_root(workflow)
    if not root.is_dir():
        return []
    payloads = []
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if artifacts.artifact_path(run_dir, token, "score").exists():
            payloads.append(_run_payload(run_dir, token))
    return payloads


def _resolve_token(run_dir: Path, workflow: dict, agent: str | None) -> str:
    """The stage to read: the named one, or the first that was actually graded."""
    if agent:
        return agent.replace("-", "_")
    graded = _graded_tokens(run_dir, workflow)
    if not graded:
        raise ValueError(f"run folder '{run_dir.name}' contains no graded stage")
    return graded[0]


# ── the tracks ────────────────────────────────────────────────────────────


def run_model_track(args) -> int:
    """Plan the run, preflight the judge, then dispatch — in that order.

    The plan is composed first because it costs nothing and states the blast
    radius, and because the judge it reports is the one the run would really
    use — rubric pin plus run-config override.
    """
    run_config = config.load_run_config(_config_path(args), cli_overrides(args))
    if run_config.track == "code":
        return run_code_track(run_config.workflow, run_config.from_run)

    dry_run = bool(_flag(args, "dry_run"))
    plan = asyncio.run(model_grader.run_workflow(run_config, dry_run=True))
    if dry_run:
        print_dry_run(plan)
        print_overrides(run_config)
        print("\n  This was a preview only — nothing ran and nothing was spent.")
        return EXIT_OK
    print_plan_header(plan)
    print_overrides(run_config)

    if not run_config.options["no_judge"]:
        failure = preflight_judge(plan)
        if failure:
            print(failure, file=sys.stderr)
            return EXIT_JUDGE_PREFLIGHT
    if not has_judge_credentials():
        print(
            "no provider credential is set — looked for "
            f"{', '.join(JUDGE_CREDENTIAL_ENV)}",
            file=sys.stderr,
        )
        return EXIT_NO_CREDENTIALS

    result = asyncio.run(
        model_grader.run_workflow(
            run_config,
            replace=bool(_flag(args, "replace")),
            on_event=print_progress,
            # The id the plan header just printed, so the run folder IS the run
            # the user was shown. Re-minting it here drifted the two apart by
            # the seconds the judge preflight took.
            dataset_run_id=plan["dataset_run_id"],
        )
    )
    print_run_result(result)
    status = result["summary"]["status"]
    if status != "completed":
        print(f"\nrun did not complete: status {status}", file=sys.stderr)
        return EXIT_RUN_FAILED
    dead_judge = _stage_with_dead_judge(result)
    if dead_judge:
        print(
            f"\njudge produced no usable verdict for ANY row of '{dead_judge}' — "
            "the agent tokens were spent and nothing was graded",
            file=sys.stderr,
        )
        return EXIT_RUN_FAILED
    failed = _baseline_failures(result)
    if failed:
        print(f"\nbaseline FAIL: {', '.join(failed)}", file=sys.stderr)
        return EXIT_BASELINE_FAIL
    return EXIT_OK


def _stage_with_dead_judge(result: dict) -> str | None:
    """The first stage whose judge was asked and failed on every single row.

    Distinct from `no_judge`, where the judge was never asked: there the counts
    are empty because nobody paid for them. Here they are empty because the
    grading half of the run is broken, which must not exit 0.
    """
    for stage in result.get("stages") or []:
        counts = (stage.get("score") or {}).get("counts") or {}
        errored = counts.get("judge_errored") or 0
        if errored and not counts.get("judged"):
            return stage["agent_id"]
    return None


def run_code_track(
    workflow_name: str,
    dataset_run_id: str | None,
    *,
    render_pages: bool = True,
    interactions: bool = True,
) -> int:
    """Run the free deterministic checks over an existing run folder."""
    if not dataset_run_id:
        raise ValueError("the code track needs --from-run <dataset_run_id> to read")
    workflow = config.load_workflow(workflow_name)
    run_dir = _existing_run_folder(dataset_run_id, workflow)
    result = code_grader.grade_run_folder(
        dataset_run_id,
        workflow_dir=Path(workflow["workflow_dir"]),
        render=render_pages,
        interactions=interactions,
    )
    _print_rule("code track")
    print(f"  run        {result['dataset_run_id']}  ·  status {result['status']}")
    if result.get("reason"):
        print(_wrapped_note(result["reason"]))
    for stage in result["stages"]:
        print(
            f"\n  {stage['agent_id']}  ·  {stage['deliverable_file']}"
            f"  ·  code score {render.score(stage.get('average_code_score'))}"
            f"  ·  rows ok {stage['rows_ok']} / {stage['rows_checked']}"
        )
        if stage.get("reason"):
            print(_wrapped_note(stage["reason"]))
        for row_id, finding in stage["findings"].items():
            problems = _code_row_problems(finding)
            if problems:
                print(f"    {row_id} ({render.score(finding.get('code_score'))}): "
                      f"{'; '.join(problems[:4])}")
    # Fold the findings into the reports/ set so the blended columns appear.
    if result["stages"]:
        try:
            top = markdown_report.write_report(run_dir)
            print(f"\n  report     {top.parent / markdown_report.CODE_REPORT_NAME}")
            print(f"  scores     {top}  (code + combined columns updated)")
        except Exception as error:  # noqa: BLE001 - rendering is never load-bearing
            print(f"\n  report     not written: {error}", file=sys.stderr)
    return EXIT_OK


def _code_row_problems(finding: dict) -> list[str]:
    """One row's findings flattened to short strings for the terminal."""
    problems = list(finding.get("issues") or [])
    rendered = finding.get("render") or {}
    problems += [render.truncate(e, 60) for e in rendered.get("console_errors") or []]
    problems += [render.truncate(e, 60) for e in rendered.get("page_errors") or []]
    problems += [
        f"dead nav {nav.get('href')}"
        for nav in rendered.get("nav_results") or []
        if not nav.get("ok")
    ]
    problems += [render.truncate(e, 60) for e in rendered.get("coverage_errors") or []]
    interactions = finding.get("interactions") or {}
    problems += [
        f"{failure.get('action')} {failure.get('target')} failed"
        for failure in interactions.get("failures") or []
    ]
    return problems


def run_rejudge_track(args) -> int:
    """Re-judge one run folder's stored responses — judge tokens only.

    Not a separate pipeline: it is `run_workflow` on the run's OWN resolved
    config with the generation step answered from the captured artifacts, so
    scoring, run_summary and the reports/ set are produced by exactly the code
    a live run uses — regenerated in place, never duplicated.
    """
    workflow = config.load_workflow(args.workflow)
    run_dir = _existing_run_folder(args.dataset_run_id, workflow)

    overrides: dict = {
        "from_run": args.dataset_run_id,
        # A folder judged with `no_judge` is exactly what a rejudge exists to fix.
        "options": {"no_judge": False},
    }
    agents = _split(args.agents)
    if agents:
        overrides["agents"] = agents
    if _flag(args, "concurrency") is not None:
        overrides["options"]["concurrency"] = args.concurrency
    judge_overrides = _section(JUDGE_FLAGS, args)
    if judge_overrides:
        overrides["judge"] = judge_overrides
    run_config = config.load_run_config(run_dir / "grade_config.resolved.yaml", overrides)

    _print_rule("rejudge", 88)
    print(f"  run        {args.dataset_run_id}  ·  {run_config.workflow}")
    print("  mode       stored responses re-scored — no agent is dispatched; "
          "judge tokens are the only spend")

    failure = _preflight_rejudge(run_config, workflow)
    if failure:
        print(failure, file=sys.stderr)
        return EXIT_JUDGE_PREFLIGHT
    if not has_judge_credentials():
        print(
            "no provider credential is set — looked for "
            f"{', '.join(JUDGE_CREDENTIAL_ENV)}",
            file=sys.stderr,
        )
        return EXIT_NO_CREDENTIALS

    result = asyncio.run(
        model_grader.run_workflow(run_config, rejudge=True, on_event=print_progress)
    )
    print_run_result(result)
    status = result["summary"]["status"]
    if status != "completed":
        print(f"\nrejudge did not complete: status {status}", file=sys.stderr)
        return EXIT_RUN_FAILED
    dead_judge = _stage_with_dead_judge(result)
    if dead_judge:
        print(
            f"\njudge produced no usable verdict for ANY row of '{dead_judge}' — "
            "nothing was re-graded",
            file=sys.stderr,
        )
        return EXIT_RUN_FAILED

    # Regenerate reports/ from the artifacts we just rewrote. Without this the
    # terminal shows the new grade while reports/report.md still holds the old
    # one — the run folder disagreeing with itself, and the file is what gets
    # read later. Done before the baseline verdict, so a FAIL still leaves the
    # reports describing what was actually scored. The code track already does
    # this; rejudge did not.
    try:
        top = markdown_report.write_report(run_dir)
        print(f"\n  report     {top}  (regenerated from the new scores)")
    except Exception as error:  # noqa: BLE001 - rendering is never load-bearing
        print(f"\n  report     not written: {error}", file=sys.stderr)

    failed = _baseline_failures(result)
    if failed:
        print(f"\nbaseline FAIL: {', '.join(failed)}", file=sys.stderr)
        return EXIT_BASELINE_FAIL
    return EXIT_OK


def _preflight_rejudge(run_config, workflow: dict) -> str | None:
    """Resolve every rejudged stage's judge BEFORE touching the artifacts.

    A misconfigured judge inside the run would be caught per-row by the guarded
    loop and written out as errored rows — superseding a real verdict with
    garbage. Asserted here, for free, instead.
    """
    workflow_dir = Path(workflow["workflow_dir"])
    cli_judge = {key: value for key, value in run_config.judge.items() if value is not None}
    for stage in workflow["stages"]:
        if run_config.agents != "all" and stage["agent_id"] not in run_config.agents:
            continue
        try:
            rubric = config.load_rubric(workflow_dir, stage["agent_id"])
        except ValueError:
            continue  # a stage with no rubric is not judged, so nothing to preflight
        merged = {**(rubric.get("judge") or {}), **cli_judge}
        try:
            judge.resolve_judge_model(merged)
        except Exception as error:  # noqa: BLE001 - any judge build failure must stop the run
            return _preflight_message({"agent_id": stage["agent_id"], "judge": merged}, error)
    return None


def run_advise_track(args) -> int:
    """Ingest a run's evidence and write per-agent prompt advice — LIVE."""
    if not has_judge_credentials():
        print(
            "no provider credential is set — looked for "
            f"{', '.join(JUDGE_CREDENTIAL_ENV)}",
            file=sys.stderr,
        )
        return EXIT_NO_CREDENTIALS
    try:
        result = asyncio.run(
            prompt_advisor.advise_run(
                args.dataset_run_id,
                workflow_name=args.workflow,
                agents=_split(args.agents),
                judge_overrides=_section(JUDGE_FLAGS, args),
            )
        )
    except judge.JudgeConfigurationError as error:
        print(f"judge preflight FAILED — nothing was spent: {error}", file=sys.stderr)
        return EXIT_JUDGE_PREFLIGHT

    _print_rule("advise")
    print(f"  run        {result['dataset_run_id']}")
    errored = False
    tokens = 0
    for stage in result["stages"]:
        tokens += (stage.get("tokens_in") or 0) + (stage.get("tokens_out") or 0)
        if stage.get("errored"):
            errored = True
            print(f"  ✖ {stage['agent_id']:<24}ERROR {render.truncate(stage.get('error_reason'), 50)}")
        else:
            print(
                f"  ✔ {stage['agent_id']:<24}"
                f"{stage.get('edits', 0)} edit(s), {stage.get('deviations', 0)} deviation(s)"
                f"   {stage.get('advice_path')}"
            )
    print(f"\n  AI usage   {render.tokens(tokens)} tokens")
    return EXIT_RUN_FAILED if errored else EXIT_OK


def _agent_dir(agent_id: str) -> Path:
    """The agent's prompt folder — raises if there is no such agent."""
    agent_dir = AGENTS_PROMPTS_DIR / agent_id
    if not (agent_dir / "AGENT.md").is_file():
        raise ValueError(f"no AGENT.md for agent '{agent_id}' under {AGENTS_PROMPTS_DIR}")
    return agent_dir


def _archive_names(agent_dir: Path) -> list[str]:
    """Existing `AGENT.vN.md` filenames in an agent folder."""
    return sorted(path.name for path in agent_dir.glob("AGENT.v*.md"))


def run_apply_advice(args) -> int:
    """Apply the advisor's edits to an agent's prompt, archiving the old body.

    Order matters: the new body is computed entirely in memory first, so a failed
    edit writes nothing; then the archive is written BEFORE AGENT.md, so an
    interruption between the two leaves the previous body recoverable. The
    reverse order has a window in which both copies are gone.

    Costs nothing — the advice was written by a run that already happened.
    """
    workflow = config.load_workflow(args.workflow)
    try:
        run_dir = _existing_run_folder(args.dataset_run_id, workflow)
        agent_dir = _agent_dir(args.agent)
        advice = artifacts.read_advice_json(run_dir, prompt_advisor._token(args.agent))
    except (ValueError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE

    edits = advice.get("edits") or []
    agent_file = agent_dir / "AGENT.md"
    original = agent_file.read_text(encoding="utf-8")

    try:
        frontmatter_block, body = prompt_edits.split_agent_file(original)
        new_body, refused = prompt_edits.apply_edits(frontmatter_block, body, edits)
    except (prompt_edits.PromptFileError, prompt_edits.EditError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_EDIT_FAILED

    _print_rule("apply-advice")
    if edits and len(refused) == len(edits):
        print(prompt_edits.render_diff(edits, refused))
        print("\n  every proposed edit targets the frontmatter — nothing applied", file=sys.stderr)
        return EXIT_ALL_REFUSED

    archive = agent_dir / prompt_edits.archive_name(
        prompt_edits.next_archive_number(_archive_names(agent_dir))
    )
    archive.write_text(body, encoding="utf-8")
    agent_file.write_text(frontmatter_block + new_body, encoding="utf-8")

    written_prefix, _ = prompt_edits.split_agent_file(
        agent_file.read_text(encoding="utf-8")
    )
    if written_prefix != frontmatter_block:
        print(
            f"error: frontmatter changed on write — the old body is safe in {archive.name}",
            file=sys.stderr,
        )
        return EXIT_EDIT_FAILED

    fields = len(frontmatter.loads(original).metadata)
    print(f"  saved old body  -> {archive}")
    print(f"  applied {len(edits) - len(refused)} edit(s) -> {agent_file}\n")
    print(prompt_edits.render_diff(edits, refused))
    print(f"\n  frontmatter unchanged ({fields} fields)")
    print(f"\n  revert with:  ./evals/grading/grade.sh revert {args.agent}")
    return EXIT_OK


def run_revert(args) -> int:
    """Restore the most recent archived body; repeated calls walk back.

    The current body is NOT re-archived — revert is an undo, not another edit.
    Re-archiving would grow the archive list while walking backwards through it,
    and the next revert would restore what was just reverted away from.
    """
    try:
        agent_dir = _agent_dir(args.agent)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE

    names = _archive_names(agent_dir)
    if not names:
        print(
            f"error: no archived prompt for '{args.agent}' — nothing to revert to",
            file=sys.stderr,
        )
        return EXIT_USAGE

    latest = agent_dir / prompt_edits.archive_name(
        prompt_edits.next_archive_number(names) - 1
    )
    archived_body = latest.read_text(encoding="utf-8")
    if not archived_body.strip():
        print(
            f"error: {latest.name} is empty — restoring it would leave an AGENT.md the "
            "loader rejects. Delete it if it is leftover scaffolding",
            file=sys.stderr,
        )
        return EXIT_USAGE

    agent_file = agent_dir / "AGENT.md"
    frontmatter_block, _ = prompt_edits.split_agent_file(
        agent_file.read_text(encoding="utf-8")
    )
    agent_file.write_text(frontmatter_block + archived_body, encoding="utf-8")
    latest.unlink()

    _print_rule("revert")
    print(f"  restored   {latest.name} -> {agent_file}")
    remaining = _archive_names(agent_dir)
    print(f"  archives   {len(remaining)} remaining")
    return EXIT_OK


def run_report(args) -> int:
    """Print one run folder's per-dimension aggregates and recurring weaknesses."""
    workflow = config.load_workflow(args.workflow)
    run_dir = _existing_run_folder(args.dataset_run_id, workflow)
    tokens = _graded_tokens(run_dir, workflow)
    if not tokens:
        raise ValueError(f"run folder '{args.dataset_run_id}' contains no graded stage")

    _print_rule("report")
    print(f"  run        {args.dataset_run_id}")
    print(f"  folder     {run_dir}")
    for token in tokens:
        score = artifacts.read_stage_artifact(run_dir, token, "score")
        print_stage_report(score, _read_artifact(run_dir, token, "grade"), args.worst)
    # Regenerated every time, so an old run folder picks up report improvements
    # without anyone having to re-spend its tokens. A folder too old or too
    # partial to render still gets the printed report above — the markdown is a
    # convenience and must never be the reason `report` fails.
    try:
        print(f"\nmarkdown        {markdown_report.write_report(run_dir)}")
    except Exception as error:  # noqa: BLE001 - rendering is never load-bearing
        print(f"\nmarkdown        not written: {error}", file=sys.stderr)
    return EXIT_OK


def run_compare(args) -> int:
    """Compare two runs, or group every run of one agent by prompt version."""
    if args.by_prompt:
        return _run_by_prompt(args)
    if not args.first or not args.second:
        raise ValueError("compare needs two run ids: compare <run-a> <run-b>")

    workflow = config.load_workflow(args.workflow)
    payloads = []
    for dataset_run_id in (args.first, args.second):
        run_dir = _existing_run_folder(dataset_run_id, workflow)
        payloads.append(_run_payload(run_dir, _resolve_token(run_dir, workflow, args.agent)))
    print_comparison(compare.compare_runs(payloads))
    return EXIT_OK


def _run_by_prompt(args) -> int:
    """Every run of one agent, grouped by the prompt version that produced it."""
    # Accept either form: `compare --by-prompt <workflow> <agent>` positionally,
    # or the --workflow/--agent flags the `history` shortcut passes. Reading only
    # the positionals made `grade.sh history <agent>` fail on its own arguments.
    workflow_name = args.first or args.workflow
    agent = args.second or args.agent
    if not workflow_name or not agent:
        raise ValueError(
            "compare --by-prompt needs a workflow and an agent: "
            "`compare --by-prompt <workflow> <agent>` or `--workflow W --agent A`"
        )
    workflow = config.load_workflow(workflow_name)
    token = agent.replace("-", "_")
    payloads = _all_run_payloads(workflow, token)
    if not payloads:
        raise ValueError(f"no run folder under {_runs_root(workflow)} graded '{agent}'")
    print(f"prompt versions  {workflow_name} / {agent}  ({len(payloads)} runs)")
    print_prompt_groups(compare.group_by_prompt(payloads))
    return EXIT_OK


def run_dashboard(args) -> int:
    """Rebuild the one evals report over every run folder. Free — no model, no dispatch.

    Errors surface here, unlike the automatic rebuild that runs at the end of a
    grading pass: this command exists to be told when something is wrong.
    """
    from evals.grading.site import builder, export as site_export

    workflow = config.load_workflow(args.workflow)
    runs_root = _runs_root(workflow).parent  # `.runs/`, across every workflow

    _print_rule("dashboard")
    if not runs_root.is_dir():
        print(f"  no runs yet under {runs_root}")
        return EXIT_OK

    result = builder.build(runs_root, force=args.force)
    print(f"  {result.line()}")
    for failure in result.errors:
        print(f"  unreadable  {failure}", file=sys.stderr)
    print(f"  data        {result.data}")
    print(f"  report      {result.report}")

    if args.export:
        run_dir = _existing_run_folder(args.export, workflow)
        print(f"  export      {site_export.export_run(run_dir)}")

    if args.open_browser and result.report is not None:
        webbrowser.open(result.report.resolve().as_uri())
    return EXIT_OK


def _config_path(args) -> Path | None:
    """The --config path, wherever on the command line it was given."""
    value = _flag(args, "config")
    return Path(value) if value else None


def _dispatch(args) -> int:
    """Route one parsed command to its track."""
    if args.command == "calibrate":
        return calibrate.run_calibration(args.workflow)
    if args.command == "report":
        return run_report(args)
    if args.command == "compare":
        return run_compare(args)
    if args.command == "dashboard":
        return run_dashboard(args)
    if args.command == "rejudge":
        return run_rejudge_track(args)
    if args.command == "advise":
        return run_advise_track(args)
    if args.command == "apply-advice":
        return run_apply_advice(args)
    if args.command == "revert":
        return run_revert(args)
    if args.command == "code":
        return run_code_track(
            args.workflow,
            args.from_run,
            render_pages=not args.no_render,
            interactions=not args.no_interactions,
        )
    return run_model_track(args)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Non-zero exit when a stage fails its baseline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None and not _flag(args, "config"):
        parser.print_help()
        return EXIT_USAGE
    try:
        return _dispatch(args)
    except (ValueError, FileExistsError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
