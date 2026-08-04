"""The commands. Parsing and printing only — every fact printed here is read
straight off a stored artifact or computed by `score.py`; nothing is blended
(R-03).

`all` is the one you normally run (via `./eval.sh`): dispatch, then check and
score each stage that just ran, rebuilding the report as it goes. The
individual commands underneath it stay usable on their own, which is what
makes a stage re-judgeable without re-dispatching it.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from evals.minimal import checks, judge, report, score, store, workflow
from evals.minimal import run as run_module


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    return args.handler(args)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="eval")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="dispatch a config's dataset — the only command that spends")
    p_run.add_argument("config")
    p_run.add_argument("--stage")
    p_run.add_argument("--from", dest="from_run")
    p_run.add_argument("--into", help="append this stage to an EXISTING run id, seeding from its prior stage")
    p_run.add_argument("--repeats", type=int, default=1)
    p_run.add_argument("--model", help="dispatch model id (default: settings.MISTRAL_MODEL_ID, "
                                        "currently mistral-small-latest). e.g. mistral-large-latest")
    # Default is the UNSET sentinel, not DEFAULT_PROVIDER: an omitted flag must
    # let the config's own `provider:` through (prototype_smoke_bedrock.yaml
    # pins bedrock). Passing it explicitly still overrides the config.
    p_run.add_argument("--provider", default=run_module.UNSET,
                        help="dispatch provider: mistral | bedrock (aws) | anthropic. "
                             f"Default: the config's `provider:`, else {run_module.DEFAULT_PROVIDER}")
    p_run.set_defaults(handler=_cmd_run)

    p_chain = sub.add_parser(
        "chain", help="dispatch a config stage by stage into one run (no judging)")
    p_chain.add_argument("config")
    p_chain.add_argument("--stage", help="just this stage")
    p_chain.add_argument("--into", help="append to an EXISTING run id — how you resume")
    p_chain.add_argument("--repeats", type=int, default=1)
    p_chain.add_argument("--model")
    p_chain.add_argument("--provider", default=run_module.UNSET)
    p_chain.set_defaults(handler=_cmd_chain)

    p_judge = sub.add_parser(
        "judge", help="check + score + report a stored run, by folder name")
    p_judge.add_argument("run_id", help="a run id, or a path to its folder")
    p_judge.add_argument("--stage", help="just this stage")
    p_judge.add_argument("--advise", action="store_true")
    p_judge.add_argument("--judge-provider")
    p_judge.add_argument("--judge-model")
    p_judge.add_argument("--concurrency", type=int, default=1)
    p_judge.set_defaults(handler=_cmd_judge)

    p_score = sub.add_parser("score", help="re-judge stored responses")
    p_score.add_argument("run_id")
    p_score.add_argument("--stage")
    p_score.add_argument("--advise", action="store_true",
                          help="one extra model call proposing a prompt edit from the weaknesses")
    # The rubric pins the judge (workflows/<id>/rubrics/*.yaml: provider
    # mistral, model mistral-large-latest). These override it for ONE invocation, so a second
    # opinion never means editing — and then remembering to unedit — a rubric.
    p_score.add_argument("--judge-provider",
                          help="override the rubric's judge provider: mistral | bedrock (aws) | "
                               "anthropic. Alone, it also clears the rubric's judge model, since "
                               "a Mistral model id is not a Bedrock one")
    p_score.add_argument("--judge-model",
                          help="override the rubric's judge model id (e.g. "
                               "eu.anthropic.claude-sonnet-4-5-20250929-v1:0). Default with "
                               "--judge-provider bedrock: settings.BEDROCK_INFERENCE_PROFILE_ID")
    p_score.add_argument("--concurrency", type=int, default=1,
                          help="judge N rows at once (default 1 = sequential). Mistral does not "
                                "publish free-tier limits; check your console before raising this")
    p_score.set_defaults(handler=_cmd_score)

    p_checks = sub.add_parser("checks", help="deterministic checks only")
    p_checks.add_argument("target", help="an HTML file, or a stored run id")
    p_checks.add_argument("--stage")
    p_checks.set_defaults(handler=_cmd_checks)

    p_compare = sub.add_parser("compare", help="noise-guarded delta")
    p_compare.add_argument("a", help="run_id or run_id:stage")
    p_compare.add_argument("b", help="run_id or run_id:stage")
    p_compare.set_defaults(handler=_cmd_compare)

    p_clone = sub.add_parser(
        "clone", help="copy a run's artifacts into a new run id, minus the judge verdicts")
    p_clone.add_argument("run_id")
    p_clone.add_argument("--label", default="rejudge",
                          help="appended to the new run id (default: rejudge). Use something "
                               "that names the second opinion, e.g. `awsjudge`")
    p_clone.set_defaults(handler=_cmd_clone)

    p_workflows = sub.add_parser(
        "workflows", help="list workflows and validate their wiring — free, no dispatch")
    p_workflows.add_argument("workflow_id", nargs="?",
                              help="just this one (default: every workflow on disk)")
    p_workflows.set_defaults(handler=_cmd_workflows)

    p_report = sub.add_parser("report", help="rebuild .runs/report.html")
    p_report.set_defaults(handler=_cmd_report)

    p_advice = sub.add_parser(
        "advice", help="pool every run's advice into prompts/advices.json")
    p_advice.add_argument("--out", default=None,
                           help="output path (default evals/minimal/prompts/advices.json)")
    p_advice.add_argument("--summary", action="store_true",
                           help="also print the per-stage table. The stale-advice warning "
                                "prints either way — it is a fact about the file just written")
    p_advice.set_defaults(handler=_cmd_advice)

    return parser.parse_args(argv)


def _cmd_run(args: argparse.Namespace) -> int:
    run_id = run_module.run(
        args.config, stage=args.stage, from_run=args.from_run, into=args.into,
        repeats=args.repeats, model=args.model, provider=args.provider,
    )
    print(run_id)
    for stage in [args.stage] if args.stage else store.list_phases(run_id):
        print(_stage_line(run_id, stage))
    return 0


def _cmd_chain(args: argparse.Namespace) -> int:
    """Dispatch a config's stages, ONE INVOCATION PER STAGE, into one run.

    Judging is deliberately not here — that is `judge`, against a run id. The
    two halves fail for different reasons and cost different money, and
    welding them together meant a rate limit in `build` threw away the right
    to judge the three stages that had already succeeded.

    Per-stage dispatch also makes the chain resumable at the exact point it
    stopped: every stage lands in the same run folder via `--into`, so a
    failed `build` is retried with `--stage build --into <run_id>` and the
    upstream stages are reused rather than re-bought. A prototype `build` is
    168k-288k input tokens and `validate` up to 2.5M — re-dispatching them
    because an unrelated stage failed is the single most expensive mistake
    this harness can make.
    """
    resolved = workflow.resolve_config(args.config)
    stages = [args.stage] if args.stage else list(resolved["order"])
    run_id = args.into

    for index, stage in enumerate(stages, start=1):
        _progress(f"==> dispatch ({index}/{len(stages)}): {stage}")
        run_id = run_module.run(
            args.config, stage=stage, into=run_id, from_run=run_id,
            repeats=args.repeats, model=args.model, provider=args.provider,
        )
        if index == 1:
            # Early, and to stderr as well as the final stdout line: a later
            # stage can fail, and without the id printed here the completed
            # work is stranded in a folder you have to go hunting for.
            _progress(f"==> run id: {run_id}")
        print(_stage_line(run_id, stage))
        report.build_report()

        rows = store.read_phase(run_id, "run", stage)
        if rows and all(row.get("errored") for row in rows):
            reason = rows[0].get("error_reason") or "errored"
            _progress(f"==> STOPPED at {stage}: {reason}")
            _progress(f"==> {index - 1}/{len(stages)} stage(s) completed and stored. Resume with:")
            _progress(f"      evals/minimal/eval.sh {args.config} --stage {stage} --into {run_id}")
            _progress(f"    then judge what you have:")
            _progress(f"      evals/minimal/judge.sh {run_id}")
            print(run_id)
            return 1

    _progress(f"==> dispatched: {run_id}")
    _progress(f"==> judge it with: evals/minimal/judge.sh {run_id}")
    print(run_id)
    return 0


def _cmd_judge(args: argparse.Namespace) -> int:
    """Check + score + report a STORED run, named by its folder.

    Takes a run id (or a path to the run folder — the basename is used), so
    judging never needs the config, the dataset, or a re-dispatch. Every stage
    already on disk is fair game, including stages from a chain that stopped
    early.
    """
    run_id = Path(str(args.run_id).rstrip("/")).name
    if not (store.RUNS_ROOT / run_id).is_dir():
        print(f"no run folder at {store.RUNS_ROOT / run_id}", file=sys.stderr)
        print(f"available: {', '.join(store.list_runs()[:8])}…", file=sys.stderr)
        return 1

    stages = [args.stage] if args.stage else store.list_phases(run_id)
    if not stages:
        print(f"{run_id} has no dispatched stages to judge", file=sys.stderr)
        return 1

    for index, stage in enumerate(stages, start=1):
        _progress(f"==> checks ({index}/{len(stages)}): {stage} — deterministic, free")
        _cmd_checks(argparse.Namespace(target=run_id, stage=stage))
        report.build_report()
        _progress(f"==> judge ({index}/{len(stages)}): {stage} — verifying evidence, then judging"
                  f"{' + advising' if args.advise else ''}")
        code = _cmd_score(argparse.Namespace(
            run_id=run_id, stage=stage, advise=args.advise,
            judge_provider=args.judge_provider, judge_model=args.judge_model,
            concurrency=args.concurrency,
        ))
        report.build_report()
        # STOP on a failed evidence check. Judging on would spend real tokens
        # producing numbers whose meaning is already in question, and the run
        # is stored — re-judging after fixing the wiring costs no dispatch.
        if code != 0:
            _progress(f"==> STOPPED at {stage}: upstream evidence check failed. "
                      f"Nothing further was judged.")
            return code

    errored = [
        f"{stage}: {row.get('error_reason') or 'errored'}"
        for stage in stages
        for row in store.read_phase(run_id, "run", stage)
        if row.get("errored")
    ]
    for line in errored:
        _progress(f"==> note: {line}")
    _progress(f"==> judged: {run_id} — open evals/minimal/report.html")
    return 0


def _progress(message: str) -> None:
    """Progress to stderr — stdout stays the run id and the stage lines, so
    `RUN_ID=$(...)` keeps working."""
    print(message, file=sys.stderr, flush=True)


def _cmd_clone(args: argparse.Namespace) -> int:
    new_run_id = store.clone_run(args.run_id, label=args.label)
    print(new_run_id)
    return 0


def _same_provider(a: str | None, b: str | None) -> bool:
    """`aws` and `bedrock` name one provider; everything else compares plainly."""
    alias = {"aws": "bedrock"}
    return alias.get(a or "", a) == alias.get(b or "", b)


def _with_judge_override(rubric: dict, provider: str | None, model: str | None) -> dict:
    """Apply --judge-provider/--judge-model over the rubric's `judge:` block.

    The model is cleared ONLY when the provider actually CHANGES. Clearing it
    unconditionally silently downgraded a same-provider rejudge: the rubric
    pins mistral-LARGE, `--judge-provider mistral` blanked it, and build_model
    fell back to settings.MISTRAL_MODEL_ID (mistral-SMALL) — a weaker, more
    capacity-constrained judge that scored a whole run without saying so (run
    260803-155330). Across providers the clear is still required: a Mistral
    model id handed to Bedrock fails, naming a model nobody chose.
    """
    if not provider and not model:
        return rubric
    judge_config = dict(rubric.get("judge") or {})
    if provider and _same_provider(provider, judge_config.get("provider")):
        judge_config["provider"] = provider
    elif provider:
        judge_config["provider"] = provider
        judge_config["model"] = None
    if model:
        judge_config["model"] = model
    return {**rubric, "judge": judge_config}


def _cmd_score(args: argparse.Namespace) -> int:
    for stage in [args.stage] if args.stage else store.list_phases(args.run_id):
        rubric = _with_judge_override(
            _load_rubric(args.run_id, stage), args.judge_provider, args.judge_model)
        rows = store.read_phase(args.run_id, "run", stage)
        checks_ok = _checks_ok(args.run_id, stage)
        on_call = _call_logger(args.run_id, stage)
        upstream = _upstream_files(args.run_id, stage, rubric.get("upstream"))
        # BEFORE SPENDING ANYTHING. A judge with no evidence does not fail —
        # it scores the missing artifact as the artifact's fault and returns a
        # plausible number, which is how four stages were judged blind for
        # weeks without anyone noticing. So the evidence is verified first and
        # the stage is REFUSED if it is not there.
        if problems := _verify_upstream(args.run_id, stage, rubric, upstream, rows):
            for problem in problems:
                print(f"UPSTREAM FAILED  {problem}")
            print(f"\nRefusing to judge {stage!r}: the rubric's evidence is not present, and a "
                  f"judge that cannot see it will still return a score.\nNothing was spent. "
                  f"Fix the workflow's `seed_as`/`deliverable` names or the rubric's `upstream:` "
                  f"list, then re-run `score` (no re-dispatch needed).")
            return 2
        payload = asyncio.run(_judge_rows(
            rows, rubric, checks_ok, on_call, args.concurrency, upstream=upstream,
        ))
        if args.advise:
            # Advice is a BONUS on top of a verdict already paid for. Letting
            # it raise discarded that verdict — the write below never ran — so
            # a judged stage cost full price and stored nothing. Hit for real
            # when `_advise`'s `read_config` raised FileNotFoundError.
            try:
                payload["advice"] = asyncio.run(
                    _advise(args.run_id, stage, payload, rubric, on_call))
            except Exception as exc:  # noqa: BLE001 - never lose a paid verdict to a bonus call
                payload["advice"] = {"text": "", "note": f"advice skipped: {exc}"}
        store.write_phase(args.run_id, "judge", stage, payload)
        print(_stage_line(args.run_id, stage))
    return 0


def _call_logger(run_id: str, stage: str):
    """An `on_call` sink that appends each raw LLM exchange to the run folder.

    Row id is stamped in by `_judge_rows`, which is the only caller that
    knows which row a given call belongs to.
    """
    def sink(record: dict) -> None:
        store.log_call(run_id, stage, {"stage": stage, **record})
    return sink


async def _advise(run_id: str, stage: str, payload: dict, rubric: dict, on_call=None) -> dict:
    """One extra model call per stage: cluster this stage's weaknesses/
    strengths (exact-text, most-cited first — same rule the report's
    Advice card uses) and ask for a proposed edit to the agent's REAL
    current prompt. Never raises; an errored call just leaves no advice."""
    weaknesses = _tally(r["weaknesses"] for r in payload["results"])
    strengths = _tally(r["strengths"] for r in payload["results"])
    if not weaknesses:
        return {"text": "", "note": "no weaknesses to advise on"}
    agent_id = store.read_config(run_id)["agents"][stage]["agent_id"]
    system_prompt = run_module.compose_agent_prompt(agent_id)
    result = await judge.advise(
        system_prompt=system_prompt, weaknesses=weaknesses, strengths=strengths,
        judge_config=rubric.get("judge") or {}, on_call=on_call,
        # The rubric's own dimension ids ARE the category vocabulary — advice
        # then clusters against the axes the stage is actually scored on,
        # instead of whatever noun the model reached for.
        categories=[d["id"] for d in rubric.get("dimensions", [])],
    )
    return {
        "advice": result.advice,
        "errored": result.errored, "error_reason": result.error_reason,
        "tokens_in": result.tokens_in, "tokens_out": result.tokens_out,
    }


def _tally(lists) -> list[str]:
    """Distinct strings across rows, most-cited first — de-duplicated so the
    advisor sees each real point once, not once per row that mentioned it."""
    counts: dict[str, int] = {}
    for items in lists:
        for text in items:
            counts[text] = counts.get(text, 0) + 1
    return [text for text, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


def _upstream_files(
    run_id: str, stage: str, allow: list[str] | None = None,
) -> dict[tuple, dict[str, str]]:
    """Every PRIOR stage's output for this run, keyed (row_id, repeat), under
    the filename that stage was seeded into the sandbox as.

    Mirrors `run._canonical_seeds` + the `upstream_artifacts` snapshot the
    dispatcher uses, so the judge sees what the agent saw. A stage names its
    seeded file with `seed_as` (specify -> spec.md); build has no `seed_as`,
    only `deliverable: prototype.html`, and reaches validate through the
    sandbox snapshot — hence `seed_as or deliverable`. Miss that and validate,
    the one stage whose rubric is explicitly a diff, gets no prior artifact.

    Deliberately rebuilt from each prior stage's stored `response` rather than
    from the run row's own `artifacts` snapshot: that snapshot is taken AFTER
    the stage runs, so validate's copy of `prototype.html` is validate's own
    output, not the pre-repair build it was asked to fix. Diffing a file
    against itself is exactly the blindness this function exists to remove.

    `allow` is the rubric's `upstream:` list — the filenames some dimension of
    THAT rubric actually reads. Omitted means every prior stage, which is
    correct but wasteful: unscoped, validate carried `tasks.md` + `analysis.md`
    (37k chars) that no validate dimension consults, and its judge prompt hit
    252k chars. Evidence a rubric cannot use is not neutral — it is context the
    judge must still read before it can score.
    """
    allowed = set(allow) if allow else None
    config = store.read_config(run_id)
    files: dict[tuple, dict[str, str]] = {}
    for prior in config.get("order") or []:
        if prior == stage:
            break
        spec = workflow.stage_def(config, prior)
        path = spec.get("seed_as") or spec.get("deliverable")
        if not path or (allowed is not None and str(path) not in allowed):
            continue
        try:
            prior_rows = store.read_phase(run_id, "run", prior)
        except FileNotFoundError:
            continue
        for row in prior_rows:
            text = row.get("response") or ""
            if text and not row.get("errored"):
                files.setdefault((row["row_id"], row.get("repeat", 0)), {})[str(path)] = text
    return files


def _verify_upstream(
    run_id: str, stage: str, rubric: dict, upstream: dict[tuple, dict[str, str]],
    rows: list[dict],
) -> list[str]:
    """Prove the judge will actually receive this rubric's declared evidence.

    Free, and it runs before every judged stage. Three things are checked per
    row, and each one has failed for real at some point:

    1. PRESENT — every filename in the rubric's `upstream:` is there and
       non-empty. A missing one is the original blindness bug.
    2. PROVENANCE — the bytes match the stored output of the stage that
       actually produces that filename. This is the guarantee that a repair
       stage is diffed against its INPUT: rebuilt from a post-run sandbox
       snapshot instead, validate's copy of `prototype.html` would be
       validate's own output and the diff would compare a file with itself.
    3. Whether the stage changed its input at all — reported as a note, not a
       failure. A validator that returns its input byte-identical is a
       legitimate outcome only if the input was already clean, and it is
       exactly the case a lenient judge scores 100 without comment.

    Returns a list of problems; empty means the stage is safe to judge.
    """
    declared = list(rubric.get("upstream") or [])
    if not declared:
        print(f"{stage}   upstream OK — none declared (first stage; the brief is its evidence)")
        return []

    config = store.read_config(run_id)
    producer = _producer_of(config, stage)
    problems: list[str] = []
    for row in rows:
        if row.get("errored"):
            continue
        key = (row["row_id"], row.get("repeat", 0))
        files = (upstream or {}).get(key) or {}
        missing = [name for name in declared if not (files.get(name) or "").strip()]
        if missing:
            problems.append(
                f"{stage}/{row['row_id']}: rubric declares upstream {declared}, but "
                f"{missing} missing or empty (present: {sorted(files) or 'nothing'})")
            continue
        parts, notes = [], []
        for name in declared:
            source_stage = producer.get(name)
            source_text = _stage_response(run_id, source_stage, key) if source_stage else None
            if source_text is None or source_text != files[name]:
                problems.append(
                    f"{stage}/{row['row_id']}: upstream {name!r} does not match the stored "
                    f"output of {source_stage!r} — the judge would be reading something other "
                    f"than what that stage produced")
                continue
            parts.append(f"{name} ({len(files[name]):,} chars, from {source_stage})")
            if files[name] == (row.get("response") or ""):
                notes.append(f"{name} is byte-identical to this stage's own output — "
                             f"it changed nothing")
        if parts:
            print(f"{stage}   upstream OK — {row['row_id']}: {', '.join(parts)}")
        for note in notes:
            print(f"{stage}   note — {row['row_id']}: {note}")
    return problems


def _producer_of(config: dict, stage: str) -> dict[str, str]:
    """Filename -> the stage that produces it, for stages BEFORE `stage`.

    Later stages win, which is what makes `prototype.html` resolve to `build`
    when judging `validate`: both declare that deliverable, and the one the
    validate judge must diff against is the last one written before it.
    """
    produced: dict[str, str] = {}
    for prior in config.get("order") or []:
        if prior == stage:
            break
        spec = workflow.stage_def(config, prior)
        name = spec.get("seed_as") or spec.get("deliverable")
        if name:
            produced[str(name)] = prior
    return produced


def _stage_response(run_id: str, stage: str, key: tuple) -> str | None:
    """One stage's stored response for one (row_id, repeat), or None."""
    try:
        rows = store.read_phase(run_id, "run", stage)
    except FileNotFoundError:
        return None
    for row in rows:
        if (row["row_id"], row.get("repeat", 0)) == key:
            return row.get("response") or ""
    return None


async def _judge_rows(
    rows: list[dict], rubric: dict, checks_ok: dict[str, bool], on_call=None,
    concurrency: int = 1, upstream: dict[tuple, dict[str, str]] | None = None,
) -> dict:
    """Judge every non-errored row. A malformed reply drops that ROW from
    `results` (R-09) but records WHY in `errors` — a dropped row used to
    vanish with no trace, making "never scored" indistinguishable from
    "scored, every row failed" once you're reading it back from disk.

    The judge score is the judge's alone — NOT blended with the deterministic
    checks (R-03). A row whose checks failed carries `checks_failed: true` as
    a fact beside its score, and `_stage_line` prints both, but the number
    itself is never overwritten.

    This used to force such a row to 0. That was wrong for three reasons, all
    visible in run 260731-124717: it deleted the content signal (a prototype
    with one malformed ternary scored identically to one full of filler); it
    made `compare`/`noise_band` useless across broken runs, since every zero
    has the same value and no variance, so progress toward a fix could not be
    measured while the gate was closed; and the fact it was protecting was
    never lost anyway — the `checks` column already read 0.0 right next to it.
    Read the two columns together: "judge 82.0  checks 0.0" is the honest
    statement that the content is reasonable and the page does not run.

    `concurrency` bounds how many rows are judged at once. Rows are
    independent — nothing in a verdict depends on another row — so this is a
    pure wall-clock win, capped by the provider's rate limit rather than by
    anything here. Results keep DATASET order regardless of completion order
    (`gather` preserves it), so a concurrent run and a sequential one produce
    byte-identical `judge.json`. Default 1: Mistral does not publish its
    free-tier limits, and a silently-parallel default could turn a working
    expensive run into a 429 storm.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def judge_one(row: dict) -> tuple[str, dict]:
        if row.get("errored"):
            return "error", {"row_id": row["row_id"], "reason": "dispatch errored, never judged"}
        row_log = (lambda rec, _row=row["row_id"]: on_call({"row_id": _row, **rec})) if on_call else None
        async with semaphore:
            verdict = await judge.judge(
                row["response"], rubric=rubric, prompt=row.get("prompt", ""),
                upstream=(upstream or {}).get((row["row_id"], row.get("repeat", 0))),
                on_call=row_log,
            )
        if verdict.errored:
            return "error", {"row_id": row["row_id"], "reason": verdict.error_reason}
        # Recorded as a FACT beside the score, never folded into it.
        row_checks_failed = checks_ok.get(row["row_id"]) is False
        # `scoring: severity_priced` derives the score from what the judge's
        # own findings COST, not from the number it volunteered — see
        # judge.SEVERITY_COST for why. Both are always stored so the gap
        # between them stays visible.
        priced = (rubric.get("scoring") == "severity_priced") and bool(verdict.sub_scores_priced)
        sub_scores = verdict.sub_scores_priced if priced else verdict.sub_scores
        return "result", {
            "row_id": row["row_id"],
            "score": _weighted_total(sub_scores, rubric),
            # WHICH judge produced this number. Without it, two runs over
            # byte-identical artifacts are distinguishable only by a folder
            # name anyone can mistype.
            "judge_model": verdict.resolved_model_id,
            "checks_failed": row_checks_failed,
            "scoring": "severity_priced" if priced else "judge_self_reported",
            "sub_scores": sub_scores,
            "sub_scores_judge_self": verdict.sub_scores if priced else {},
            "findings": verdict.findings,
            "rationale": verdict.rationale,
            "strengths": verdict.strengths,
            "weaknesses": verdict.weaknesses,
            "tokens_in": verdict.tokens_in,
            "tokens_out": verdict.tokens_out,
        }

    outcomes = await asyncio.gather(*(judge_one(row) for row in rows))
    return {
        "results": [payload for kind, payload in outcomes if kind == "result"],
        "errors": [payload for kind, payload in outcomes if kind == "error"],
        # The judge ASKED for, recorded even when every row errored — the one
        # case where no row carries `judge_model` and the stage would
        # otherwise look unjudged rather than judged-and-rate-limited.
        "judge_requested": {k: (rubric.get("judge") or {}).get(k) for k in ("provider", "model")},
    }


def _checks_ok(run_id: str, stage: str) -> dict[str, bool]:
    """Row id -> checks passed, from this stage's already-stored `score.json`
    (checks must run before score for this to have data; absent entirely
    just means "unknown" — a judge score is never overridden on a guess).
    Combines static + render exactly as `checks.check_run`'s own `rows_ok`
    rollup does, so this is the SAME predicate applied per row, not a
    second implementation of it."""
    try:
        findings = store.read_phase(run_id, "score", stage).get("findings", {})
    except FileNotFoundError:
        return {}
    return {
        row_id: bool(f.get("ok")) and bool((f.get("render") or {}).get("ok", True))
        for row_id, f in findings.items()
    }


def _weighted_total(sub_scores: dict[str, int], rubric: dict) -> float:
    weights = {d["id"]: d.get("weight", 0) for d in rubric.get("dimensions", [])}
    total_weight = sum(weights.get(name, 0) for name in sub_scores) or 1
    return sum(sub_scores[name] * weights.get(name, 0) for name in sub_scores) / total_weight


def _cmd_checks(args: argparse.Namespace) -> int:
    path = Path(args.target)
    if path.is_file():
        finding = checks.check_html(path.read_text(encoding="utf-8"))
        print(f"ok={finding['ok']}  issues={len(finding['issues'])}  warnings={len(finding['warnings'])}")
        return 0
    run_id = args.target
    for stage in [args.stage] if args.stage else store.list_phases(run_id):
        result = checks.check_run(run_id, stage)
        store.write_phase(run_id, "score", stage, result)
        print(_stage_line(run_id, stage))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    result = score.compare(_load_comparable(args.a), _load_comparable(args.b))
    if "error" in result:
        print(result["error"])
        return 1
    print(result["comparisons"][0]["verdict"])
    return 0


def _load_comparable(spec: str) -> dict:
    """A `run_id` or `run_id:stage` into the `{aggregate: ...}` shape `score.compare` reads."""
    run_id, _, stage = spec.partition(":")
    if not stage:
        stages = store.list_phases(run_id)
        if len(stages) != 1:
            raise ValueError(f"{run_id} has stages {stages} — specify run_id:stage")
        stage = stages[0]
    rows = store.read_phase(run_id, "judge", stage).get("results", [])
    config = store.read_config(run_id)
    prompt_hash = rows[0].get("system_prompt_hash") if rows else None
    return {
        "run_id": f"{run_id}:{stage}",
        "config_hash": _hash(config),
        "system_prompt_hash": prompt_hash,
        "aggregate": score.aggregate(rows),
    }


def _cmd_workflows(args: argparse.Namespace) -> int:
    """Print each workflow's wiring and check it holds together.

    The point of a config-only workflow is that adding one needs no Python —
    which also means nothing type-checks it until a dispatch is already
    running and already spending. This is that check, for free: every stage
    has an agent the loader can actually load, a rubric, and either a
    `seed_as` or a `deliverable`; every `checks:` names a real checker; and
    every rubric's `upstream:` names a file some earlier stage produces.

    Returns non-zero if anything is broken, so it can gate a run.
    """
    import agents.loader

    problems: list[str] = []
    for workflow_id in ([args.workflow_id] if args.workflow_id else workflow.list_workflows()):
        definition = workflow.load_workflow(workflow_id)
        order = definition.get("order") or []
        print(f"\n{workflow_id}  ({len(order)} stages: {', '.join(order)})")
        produced: set[str] = set()
        for stage in order:
            stage_def = workflow.stage_def(definition, stage)
            agent_id = stage_def.get("agent_id")
            artifact = stage_def.get("seed_as") or stage_def.get("deliverable")
            checker = stage_def.get("checks") or "(inferred)"
            try:
                agents.loader.load_agent_spec(agent_id)
                agent_note = ""
            except Exception as exc:  # noqa: BLE001 - report every problem, never stop at the first
                agent_note = "  ← UNKNOWN AGENT"
                problems.append(f"{workflow_id}/{stage}: cannot load agent {agent_id!r} ({exc})")
            print(f"  {stage:<10} {str(agent_id):<24} -> {str(artifact):<20} checks={checker}{agent_note}")
            if not artifact:
                problems.append(f"{workflow_id}/{stage}: declares neither seed_as nor deliverable")
            if stage_def.get("checks") not in (None, "none") \
                    and stage_def["checks"] not in checks.CHECKERS:
                problems.append(
                    f"{workflow_id}/{stage}: unknown checker {stage_def['checks']!r} "
                    f"(known: {sorted(checks.CHECKERS)} or 'none')")
            try:
                rubric = workflow.load_rubric(definition, stage)
            except FileNotFoundError as exc:
                problems.append(f"{workflow_id}/{stage}: {exc}")
            else:
                for name in rubric.get("upstream") or []:
                    if name not in produced:
                        problems.append(
                            f"{workflow_id}/{stage}: rubric wants upstream {name!r}, which no "
                            f"earlier stage produces (produced so far: {sorted(produced) or 'nothing'})")
            if artifact:
                produced.add(str(artifact))
    for problem in problems:
        print(f"\nPROBLEM  {problem}")
    return 1 if problems else 0


def _cmd_report(_args: argparse.Namespace) -> int:
    print(report.build_report())
    return 0


def _cmd_advice(args: argparse.Namespace) -> int:
    """Pool every stored run's advisor output into one file, and say when a
    bucket has gone stale.

    Free — reads what is already on disk, makes no model call, and rebuilds
    from scratch rather than appending, so archived or deleted runs drop out
    instead of lingering.

    The mixed-hash warning is not optional output. Advice is a criticism of a
    SPECIFIC prompt body: once a stage shows more than one
    `system_prompt_hash`, its bucket mixes suggestions about text that still
    exists with suggestions about text that was replaced, and nothing
    downstream can tell them apart. That is a correctness warning about the
    file just written, so it always prints.
    """
    path = report.export_advice(args.out)
    print(path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for workflow_id, entry in sorted(payload.get("workflows", {}).items()):
        if args.summary:
            print(f"\n{workflow_id}: {entry['unique']} unique / {entry['total']} total "
                  f"({len(payload.get('runs', []))} runs)")
        for stage, facts in entry.get("stages", {}).items():
            if args.summary:
                categories = ", ".join(
                    f"{name}={c['unique']}" for name, c in facts["categories"].items())
                print(f"  {stage:<9} {str(facts.get('agent_id')):<24} "
                      f"unique={facts['unique']:<4} {categories}")
            hashes = facts.get("system_prompt_hashes") or []
            if len(hashes) > 1:
                print(f"\nWARNING  {workflow_id}/{stage} ({facts.get('agent_id')}) mixes advice "
                      f"from {len(hashes)} prompt versions.\n"
                      "         Suggestions collected against a replaced prompt body describe\n"
                      "         text that no longer exists. Split by `system_prompt_hashes`\n"
                      "         before applying.")
    return 0


def _load_rubric(run_id: str, stage: str) -> dict:
    """This stage's rubric, resolved through the WORKFLOW the run recorded.

    Not a global `rubrics/<stage>.yaml`: stage names are eval-local labels, so
    `prototype` and `ppt` both have a `validate` stage and a flat lookup would
    grade one with the other's rubric — silently, and with a plausible number.
    """
    return workflow.load_rubric(store.read_config(run_id), stage)


def _hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _stage_line(run_id: str, stage: str) -> str:
    """`build   judge 91.1 (n=2)   checks 40.7 (n=3)   completed 2/5` — three
    unsynthesised facts, read straight from whatever is stored. Never a blend.

    A stage with any failing check also gets a trailing `GATE: FAILED`. That
    is the safety the old score-zeroing was really after — a broken
    deliverable must be impossible to miss — but stated as its own verdict
    instead of by corrupting the judge number next to it.
    """
    parts = [stage, _judge_fact(run_id, stage), _checks_fact(run_id, stage),
              _completed_fact(run_id, stage), _gate_fact(run_id, stage)]
    return "   ".join(p for p in parts if p)


def _gate_fact(run_id: str, stage: str) -> str:
    """`GATE: FAILED (static)` — naming WHICH check failed, and the first reason.

    "FAILED" alone sent you back to the JSON every time. It also hid the most
    important distinction there is here: `render` actually loaded the page in
    Chromium, `static` only linted the source against a convention, so a
    static-only failure can sit on a page that works perfectly.
    """
    try:
        result = store.read_phase(run_id, "score", stage)
    except FileNotFoundError:
        return ""
    checked = result.get("rows_checked", 0)
    if not checked or not (checked - result.get("rows_ok", 0)):
        return ""
    reasons = result.get("reasons") or []
    detail = f" — {reasons[0]}" if reasons else ""
    more = f" (+{len(reasons) - 1} more)" if len(reasons) > 1 else ""
    return f"GATE: FAILED [render]{detail}{more}"


def _judge_fact(run_id: str, stage: str) -> str:
    try:
        payload = store.read_phase(run_id, "judge", stage)
    except FileNotFoundError:
        return "judge -- (n=0)"
    agg = score.aggregate(payload.get("results", []))
    if agg["mean"] is None:
        errors = payload.get("errors") or []
        return f"judge -- (n=0, {len(errors)} errored)" if errors else "judge -- (n=0)"
    return f"judge {agg['mean']:.1f} (n={agg['n']})"


def _checks_fact(run_id: str, stage: str) -> str:
    try:
        result = store.read_phase(run_id, "score", stage)
    except FileNotFoundError:
        return "checks -- (n=0)"
    if result.get("skipped"):
        return "checks n/a"   # prose stage — nothing here is HTML to check
    checked = result.get("rows_checked", 0)
    ok = result.get("rows_ok", 0)
    pct = (ok / checked * 100) if checked else 0.0
    # Static lint noted but never gating — see checks.check_run.
    advisories = result.get("advisories") or []
    note = f"  (static: {len(advisories)} advisory)" if advisories else ""
    return f"checks {pct:.1f} (n={checked}){note}"


def _completed_fact(run_id: str, stage: str) -> str:
    try:
        rows = store.read_phase(run_id, "run", stage)
    except FileNotFoundError:
        return "completed 0/0"
    completed = sum(1 for row in rows if not row.get("errored"))
    return f"completed {completed}/{len(rows)}"


if __name__ == "__main__":
    sys.exit(main())
