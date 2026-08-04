"""The five commands. Parsing and printing only — every fact printed here is
read straight off a stored artifact or computed by `score.py`; nothing is
blended (R-03).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import yaml

from evals.minimal import checks, judge, report, score, store
from evals.minimal import run as run_module

HERE = Path(__file__).resolve().parent


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
    # let the config's own `provider:` through (configs/ten_aws.yaml pins
    # bedrock). Passing it explicitly still overrides the config.
    p_run.add_argument("--provider", default=run_module.UNSET,
                        help="dispatch provider: mistral | bedrock (aws) | anthropic. "
                             f"Default: the config's `provider:`, else {run_module.DEFAULT_PROVIDER}")
    p_run.set_defaults(handler=_cmd_run)

    p_score = sub.add_parser("score", help="re-judge stored responses")
    p_score.add_argument("run_id")
    p_score.add_argument("--stage")
    p_score.add_argument("--advise", action="store_true",
                          help="one extra model call proposing a prompt edit from the weaknesses")
    # The rubric pins the judge (rubrics/*.yaml: provider mistral, model
    # mistral-large-latest). These override it for ONE invocation, so a second
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

    p_report = sub.add_parser("report", help="rebuild .runs/report.html")
    p_report.set_defaults(handler=_cmd_report)

    p_advice = sub.add_parser(
        "advice", help="pool every run's advice into prompts/advices.json")
    p_advice.add_argument("--out", default=None,
                           help="output path (default evals/minimal/prompts/advices.json)")
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
            _load_rubric(stage), args.judge_provider, args.judge_model)
        rows = store.read_phase(args.run_id, "run", stage)
        checks_ok = _checks_ok(args.run_id, stage)
        on_call = _call_logger(args.run_id, stage)
        payload = asyncio.run(_judge_rows(
            rows, rubric, checks_ok, on_call, args.concurrency,
            upstream=_upstream_files(args.run_id, stage, rubric.get("upstream")),
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
    agents_cfg = config.get("agents") or {}
    files: dict[tuple, dict[str, str]] = {}
    for prior in config.get("order") or []:
        if prior == stage:
            break
        spec = agents_cfg.get(prior) or {}
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


def _cmd_report(_args: argparse.Namespace) -> int:
    print(report.build_report())
    return 0


def _cmd_advice(args: argparse.Namespace) -> int:
    print(report.export_advice(args.out))
    return 0


def _load_rubric(stage: str) -> dict:
    path = HERE / "rubrics" / f"{stage}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
