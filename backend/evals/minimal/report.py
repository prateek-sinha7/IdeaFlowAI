"""One `report.html`, at the package root (not buried in the gitignored
`.runs/`). Reads only stored JSON via `store`; imports `score.aggregate`
rather than recomputing anything — this stays the ONLY place a run's numbers
get computed (R-06's spirit: two implementations of the same arithmetic is
its own bug class).

Everything else — the three "pages" (runs index, run detail, stage detail),
sorting, filtering, artifact previews — is `report.js` + `report.css`,
static assets loaded via `<link>`/`<script src>` (not `fetch()`, which
`file://` blocks): this module's whole job is gathering that data and
embedding it inline so the page still opens by double-click. A run that
fails to read degrades to a warning entry, never an exception (R-06).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from evals.minimal import score, store

HERE = Path(__file__).resolve().parent
REPORT_PATH = HERE / "report.html"

_EMPTY_STAGE = {
    "judge": None, "judge_errors": [], "checks": None, "completed": 0, "total": 0, "rows": [],
    "advice": None,
}


def build_report(output_path: str | Path | None = None) -> Path:
    """Regenerate the report from whatever is on disk right now."""
    warnings: list[str] = []
    run_ids = store.list_runs()
    runs = [r for r in (_summarize_run(run_id, warnings) for run_id in run_ids) if r]

    path = Path(output_path) if output_path else REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(_page({
        "warnings": warnings, "runs": runs, "generated_at": generated_at,
        "summary": _overall(runs), "advice": _advice_index(runs),
    }), encoding="utf-8")
    return path


def export_advice(output_path: str | Path | None = None) -> Path:
    """Every run's advice, folded into ONE json: workflow -> stage -> category.

    Same clustering the report's Advise tab shows (`_advice_index`), plus the
    two facts that view has no room for and that decide whether a suggestion
    is still actionable:

    `agent_id` — which agent the advice is FOR. The stage name is the eval's
    label ("build"); the agent id is what you actually edit
    (`prototype-build`). A file keyed only by stage cannot be applied without
    that lookup, and the mapping is per-config, not global.

    `system_prompt_hashes` — which prompt the advice was generated AGAINST.
    Advice is a criticism of a specific prompt body. Promote a v2 and every
    suggestion collected against v1 is describing text that no longer exists;
    without the hash there is no way to tell stale advice from live advice,
    and the pool silently accumulates both. More than one hash in this list
    means the bucket MIXES advice across prompt versions — treat it as
    unsorted until you split it.
    """
    warnings: list[str] = []
    run_ids = store.list_runs()
    runs = [r for r in (_summarize_run(run_id, warnings) for run_id in run_ids) if r]
    index = _advice_index(runs)

    # Lands next to the versioned prompts it is meant to be applied TO, so the
    # advice and the `.vN.md` drafts it argues about sit in one directory.
    path = Path(output_path) if output_path else HERE / "prompts" / "advices.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "runs": [r["run_id"] for r in runs],
        "workflows": index,
    }, indent=2), encoding="utf-8")
    return path


def _overall(runs: list[dict]) -> dict:
    """Everything the dashboard's tiles and charts show, counted ONCE here.

    `report.js` renders these; it never derives them. Severity counts in
    particular have to live on this side — they are the only place the
    harness says how BAD the findings were rather than how many, and a second
    tally in JS could disagree with the priced score computed from the same
    findings.
    """
    pipelines: set[str] = set()
    severity = {"blocking": 0, "major": 0, "minor": 0}
    gate = {"passed": 0, "failed": 0}
    tokens_by_stage: dict[str, int] = {}
    divergence: list[dict] = []

    for run in runs:
        if run.get("dataset_id"):
            pipelines.add(run["dataset_id"])
        for stage, facts in run["stages"].items():
            checks = facts.get("checks")
            if checks and checks.get("n"):
                gate["failed" if checks["pct"] < 100.0 else "passed"] += 1
            for row in facts.get("rows", []):
                verdict = row.get("judge") or {}
                for items in (verdict.get("findings") or {}).values():
                    for finding in items:
                        key = finding.get("severity", "minor")
                        severity[key] = severity.get(key, 0) + 1
                tokens_by_stage[stage] = (
                    tokens_by_stage.get(stage, 0)
                    + int(verdict.get("tokens_in") or 0) + int(verdict.get("tokens_out") or 0)
                )
            # The gap this harness exists to expose: content the judge liked
            # sitting on a deliverable that does not run. Only meaningful
            # where BOTH numbers exist.
            judge = facts.get("judge")
            if judge and judge.get("mean") is not None and checks and checks.get("n"):
                divergence.append({
                    "run_id": run["run_id"], "stage": stage,
                    "judge": judge["mean"], "checks": checks["pct"],
                    "gap": judge["mean"] - checks["pct"],
                })
    divergence.sort(key=lambda d: -d["gap"])
    return {
        "pipelines": sorted(pipelines),
        "severity": severity,
        "severity_total": sum(severity.values()),
        "gate": gate,
        "tokens_by_stage": tokens_by_stage,
        "divergence": divergence[:8],
    }


def _advice_index(runs: list[dict]) -> dict:
    """Advisor output, folded workflow -> stage -> CATEGORY -> suggestions.

    Clustering is on `category` (a rubric dimension id), not on the text.
    The advisor used to return prose, and prose never collapses — 29 stored
    proposals deduped to 29, so the "seen 3x" signal that makes this view
    worth having never fired. Categories are a closed vocabulary handed to
    the advisor, so the same underlying gap lands in the same bucket however
    it happens to be worded.

    `advisory_score` is the advisor's own 0-100 (0 = MAY, 100 = MUST); the
    bucket carries the max, since one MUST in a category outranks several
    MAYs. Identical descriptions still collapse, with `count` naming how
    many runs asked for it.
    """
    index: dict[str, dict] = {}
    for run in runs:
        workflow = run.get("workflow") or "unknown"
        for stage, facts in run["stages"].items():
            payload = facts.get("advice") or {}
            # One flat list now; `add`/`remove` are read too so advice stored
            # under the older split shape still appears in the history.
            items = list(payload.get("advice") or [])
            for legacy in ("add", "remove"):
                items += [{**i, "action": i.get("action", legacy)}
                           for i in (payload.get(legacy) or []) if isinstance(i, dict)]
            for item in items:
                if not isinstance(item, dict) or not item.get("description"):
                    continue
                category = item.get("category") or "uncategorised"
                bucket = (
                    index.setdefault(workflow, {"stages": {}})
                    ["stages"].setdefault(stage, {"categories": {}})
                    ["categories"].setdefault(category, {})
                )
                action = item.get("action") or "add"
                key = (action, " ".join(str(item["description"]).split()))
                entry = bucket.setdefault(key, {
                    "action": action, "description": item["description"],
                    "advisory_score": 0, "reasons": [], "runs": [],
                })
                entry["advisory_score"] = max(
                    entry["advisory_score"], int(item.get("advisory_score") or 0)
                )
                reason = (item.get("reason") or "").strip()
                if reason and reason not in entry["reasons"]:
                    entry["reasons"].append(reason)
                entry["runs"].append(run["run_id"])
            # Pre-structured advice (one prose blob) still shows, under its
            # own bucket, rather than vanishing from the history.
            if payload.get("text"):
                bucket = (
                    index.setdefault(workflow, {"stages": {}})
                    ["stages"].setdefault(stage, {"categories": {}})
                    ["categories"].setdefault("prose (pre-structured)", {})
                )
                key = ("add", " ".join(payload["text"].split()))
                entry = bucket.setdefault(key, {
                    "action": "add", "description": payload["text"],
                    "advisory_score": 0, "reasons": [], "runs": [],
                })
                entry["runs"].append(run["run_id"])

    out: dict[str, dict] = {}
    for workflow, wf in sorted(index.items()):
        stages = {}
        for stage, st in sorted(wf["stages"].items()):
            provenance = _advice_provenance(runs, workflow, stage)
            by_run = provenance.pop("hash_by_run")
            live = provenance.get("current_prompt_hash")
            categories = {}
            for category, bucket in sorted(st["categories"].items()):
                entries = sorted(
                    ({**e, "count": len(e["runs"]),
                      "prompt_state": _prompt_state(e["runs"], by_run, live)}
                     for e in bucket.values()),
                    # OPEN advice first, SUPERSEDED last. A suggestion written
                    # against a prompt body that has since been replaced was
                    # either applied or made moot by whatever replaced it —
                    # either way it is not work remaining, and sorting it
                    # among the live items is what makes a pool of 115 read as
                    # 115 open problems when most of it may be history.
                    key=lambda e: (_STATE_RANK.get(e["prompt_state"], 9),
                                    -e["advisory_score"], -e["count"]),
                )
                categories[category] = {
                    "entries": entries,
                    "unique": len(entries),
                    "total": sum(e["count"] for e in entries),
                    "max_score": max((e["advisory_score"] for e in entries), default=0),
                }
            stages[stage] = {
                "categories": categories,
                "unique": sum(c["unique"] for c in categories.values()),
                "total": sum(c["total"] for c in categories.values()),
                "open": sum(
                    1 for c in categories.values() for e in c["entries"]
                    if e["prompt_state"] == "current"
                ),
                **provenance,
            }
        out[workflow] = {
            "stages": stages,
            "unique": sum(s["unique"] for s in stages.values()),
            "total": sum(s["total"] for s in stages.values()),
        }
    return out


def _advice_provenance(runs: list[dict], workflow: str, stage: str) -> dict:
    """Which agent a stage's advice is FOR, and which prompt it was written AGAINST.

    Both facts decide whether a suggestion is still actionable, and neither is
    derivable from the advice text:

    `agent_id` — the stage name is the eval's label ("build"); the agent id is
    what you actually edit (`prototype-build`). The mapping is per-config, not
    global, so it is read from each run's own config snapshot.

    `system_prompt_hashes` — advice is a criticism of a SPECIFIC prompt body.
    Promote a v2 and every suggestion collected against v1 describes text that
    no longer exists. More than one hash here means the bucket MIXES advice
    across prompt versions and cannot be applied as a unit — which is not
    hypothetical: run 260731-153332 was dispatched under a `prototype-specify`
    override while the other seven ran canonical, and nothing in the advice
    text itself gave any hint of it.
    """
    agent_id = None
    hashes: list[str] = []
    contributing: list[str] = []
    by_run: dict[str, str] = {}
    for run in runs:
        if (run.get("workflow") or "unknown") != workflow or stage not in run["stages"]:
            continue
        contributing.append(run["run_id"])
        try:
            config = store.read_config(run["run_id"])
            agent_id = ((config.get("agents") or {}).get(stage) or {}).get("agent_id") or agent_id
        except (FileNotFoundError, KeyError, TypeError):
            pass
        # From the RUN phase, not the summarized rows — `_summarize_stage`
        # drops `system_prompt_hash` when it folds rows together with the
        # judge verdict, so reading it there silently yields nothing.
        for row in store.read_phase(run["run_id"], "run", stage):
            digest = row.get("system_prompt_hash") if isinstance(row, dict) else None
            if digest:
                by_run.setdefault(run["run_id"], digest)
                if digest not in hashes:
                    hashes.append(digest)
    return {
        "agent_id": agent_id, "system_prompt_hashes": hashes, "runs": contributing,
        "current_prompt_hash": _live_prompt_hash(agent_id),
        "hash_by_run": by_run,
    }


_STATE_RANK = {"current": 0, "unknown": 1, "superseded": 2}


def _prompt_state(run_ids: list[str], by_run: dict[str, str], live: str | None) -> str:
    """Is this suggestion still about the prompt that is running today?

    `current`    — at least one run it came from used the live prompt body.
    `superseded` — every such run used a prompt body that has since changed.
    `unknown`    — no hash recorded (seeded rows, or a pre-hash run).

    This is inference, not bookkeeping: nothing records that you APPLIED a
    suggestion. What it records is that the prompt moved on, which is the
    only durable evidence available and is right for the two cases that
    matter — you applied the advice, or you rewrote past it.
    """
    if live is None:
        return "unknown"
    seen = {by_run.get(run_id) for run_id in run_ids} - {None}
    if not seen:
        return "unknown"
    return "current" if live in seen else "superseded"


def _live_prompt_hash(agent_id: str | None) -> str | None:
    """Hash of the prompt this agent would dispatch with RIGHT NOW.

    Composed through the same path a dispatch uses, so an active prompt
    override is reflected — the point is to compare stored advice against
    what is actually live, not against what is canonical on disk.
    """
    if not agent_id:
        return None
    try:
        from evals.minimal import run as run_module
        return run_module._hash_prompt(run_module.compose_agent_prompt(agent_id))
    except Exception:  # noqa: BLE001 - provenance must never break the report
        return None


def _all_phases(run_id: str) -> list[str]:
    """Every phase this run has data for, in ANY of the three files.

    `store.list_phases` only reads `run.json`'s own keys — a phase judged or
    checked under a name `run.json` never had (a re-scored typo, a manually
    re-run stage) would exist in `judge.json`/`score.json` but never appear
    here otherwise. Union all three so nothing with real data goes invisible.
    """
    phases: set[str] = set()
    for kind in ("run", "judge", "score"):
        phases |= store.read_all(run_id, kind).keys()
    return sorted(phases)


def _summarize_run(run_id: str, warnings: list[str]) -> dict | None:
    """One run's per-stage facts, or None (with a warning) if the run itself
    can't be listed. A single malformed STAGE degrades only that stage (its
    own warning, an empty stage entry) — one stale phase must never hide an
    otherwise-good run (R-06's blast radius is the stage, not the run)."""
    try:
        stages = _all_phases(run_id)
    except Exception as exc:  # noqa: BLE001 - R-06: a bad run degrades, never crashes the report
        warnings.append(f"{run_id}: could not be read ({exc})")
        return None

    per_stage = {}
    for stage in stages:
        try:
            per_stage[stage] = _summarize_stage(run_id, stage)
        except Exception as exc:  # noqa: BLE001 - see docstring: stage-scoped, not run-scoped
            warnings.append(f"{run_id}/{stage}: could not be read ({exc})")
            per_stage[stage] = _EMPTY_STAGE
    try:
        config = store.read_config(run_id)
    except (FileNotFoundError, AttributeError):
        config = {}
    return {
        "run_id": run_id,
        "dataset_id": config.get("dataset_id"),
        "workflow": _workflow_of(config),
        "stages": per_stage,
        "totals": _run_totals(per_stage),
    }


def _workflow_of(config: dict) -> str | None:
    """Which agent pipeline this run exercised, from its own config snapshot.

    Taken from the agent ids (`prototype-specify` -> `prototype`), which is
    where production's `pipeline_type` lives too, rather than from the
    dataset name — a dataset can be pointed at any pipeline, so its name is
    a label, not a fact. Mixed prefixes report as-is rather than picking one.
    """
    prefixes = {
        str(defn.get("agent_id", "")).split("-")[0]
        for defn in (config.get("agents") or {}).values()
        if defn and defn.get("agent_id")
    }
    prefixes.discard("")
    if not prefixes:
        return None
    return "+".join(sorted(prefixes))


def _run_totals(per_stage: dict) -> dict:
    """This run's across-stage rollup — the footer row on the run page and the
    per-run row on the index, from ONE computation.

    `report.js` was averaging these itself in `runStats`, which is the second
    implementation of an arithmetic Python already owns — exactly the bug
    class the module docstring says this file exists to avoid. Computed here,
    via `score.aggregate`, so the index and the run page can never disagree.

    Stages that were never judged/checked are EXCLUDED rather than counted as
    zero: a mean over "no verdict" is not a verdict.
    """
    judged = [s["judge"]["mean"] for s in per_stage.values()
              if s.get("judge") and s["judge"].get("mean") is not None]
    checked = [s["checks"]["pct"] for s in per_stage.values() if s.get("checks")]
    gate_failed = sum(
        1 for s in per_stage.values()
        if s.get("checks") and s["checks"].get("n") and s["checks"]["pct"] < 100.0
    )
    return {
        "judge_mean": score.aggregate([{"score": v} for v in judged])["mean"],
        "judge_stages": len(judged),
        "checks_mean": score.aggregate([{"score": v} for v in checked])["mean"],
        "checks_stages": len(checked),
        "stages": len(per_stage),
        "completed": sum(s.get("completed", 0) for s in per_stage.values()),
        "total": sum(s.get("total", 0) for s in per_stage.values()),
        "gate_failed": gate_failed,
    }


def _summarize_stage(run_id: str, stage: str) -> dict:
    """One stage's facts, rows folded together with their judge verdict and
    checks summary so report.js never has to join three arrays client-side."""
    rows_raw, judge_by_row, judge_errors, checks_by_row, checks_summary, advice = _read_stage(run_id, stage)
    judge_agg = score.aggregate(list(judge_by_row.values())) if judge_by_row else None

    inherited_names = _inherited_names(run_id, stage)
    rows = [
        {
            "row_id": row["row_id"],
            "origin": row.get("origin", "unknown"),
            "errored": bool(row.get("errored")),
            "response": row.get("response") or "",
            # Split, because `artifacts` is a snapshot of the WHOLE sandbox and
            # the sandbox is shared across the chain: once upstream output is
            # seeded as spec.md/tasks.md/analysis.md, every later stage's
            # snapshot contains them too. Rendering that list unfiltered put
            # three other phases' documents at the bottom of every stage page.
            "artifacts": {k: v for k, v in (row.get("artifacts") or {}).items()
                          if k not in inherited_names},
            "inherited": sorted(set(row.get("artifacts") or {}) & inherited_names),
            "judge": _row_judge(judge_by_row.get(row["row_id"])),
            "checks_summary": (checks_by_row.get(row["row_id"]) or {}).get("summary"),
        }
        for row in rows_raw
    ]
    return {
        # The stage's own artifact as a path relative to report.html, so it
        # opens in a real browser tab (a relative href works from file://,
        # unlike fetch()). The iframe preview is sandboxed and scaled down;
        # a 35KB prototype needs a full window to actually be looked at.
        "artifact_href": _artifact_href(run_id, stage),
        "judge": judge_agg,
        "judge_errors": judge_errors,
        "checks": checks_summary,
        "completed": sum(1 for row in rows_raw if not row.get("errored")),
        "total": len(rows_raw),
        "rows": rows,
        "advice": advice,
    }


def _inherited_names(run_id: str, stage: str) -> set[str]:
    """Filenames this stage was SEEDED with, not ones it produced.

    Read from the run's own config: every `seed_as` belonging to a stage
    earlier in `order`. Config-driven rather than pattern-matched on the
    filename, so a config that seeds different paths stays correct.
    """
    try:
        config = store.read_config(run_id)
        order = config["order"]
        agents = config["agents"]
    except (FileNotFoundError, KeyError, TypeError):
        return set()
    if stage not in order:
        return set()
    return {
        (agents.get(prior) or {}).get("seed_as")
        for prior in order[:order.index(stage)]
    } - {None}


def _artifact_href(run_id: str, stage: str) -> str | None:
    """`.runs/<run>/artifacts/<stage>.<ext>` if that file exists, else None.

    Probed on disk rather than derived from the config: `run.py` picks the
    extension from the RESPONSE (`_artifact_ext`), so a stage that was
    supposed to emit HTML but returned prose has a `.md` here, and guessing
    would produce a dead link.
    """
    folder = store.run_dir(run_id) / "artifacts"
    for ext in ("html", "md"):
        candidate = folder / f"{stage}.{ext}"
        if candidate.exists():
            return f".runs/{run_id}/artifacts/{stage}.{ext}"
    return None


def _read_stage(
    run_id: str, stage: str,
) -> tuple[list[dict], dict[str, dict], list[dict], dict[str, dict], dict | None, dict | None]:
    """Every stored artifact for one stage, tolerating any of the three being absent."""
    rows_raw: list[dict] = []
    judge_by_row: dict[str, dict] = {}
    judge_errors: list[dict] = []
    checks_by_row: dict[str, dict] = {}
    checks_summary: dict | None = None
    advice: dict | None = None
    try:
        rows_raw = store.read_phase(run_id, "run", stage)
    except FileNotFoundError:
        pass
    try:
        judge_payload = store.read_phase(run_id, "judge", stage)
        judge_results, judge_errors = _judge_results(judge_payload)
        judge_by_row = {row["row_id"]: row for row in judge_results}
        if isinstance(judge_payload, dict):
            advice = judge_payload.get("advice")
    except FileNotFoundError:
        pass
    try:
        score_payload = store.read_phase(run_id, "score", stage) or {}
        checks_by_row = score_payload.get("findings", {})
        # The AUTHORITATIVE rows_ok/rows_checked — checks.py's own rollup,
        # which combines static AND render — never re-derived from `findings`
        # here. Two implementations of the same count is exactly the bug
        # class this harness exists to catch (R-06's spirit).
        rows_checked = score_payload.get("rows_checked", 0)
        # A stage with no HTML deliverable was never checked — report nothing
        # rather than 0.0, which would read as a failure it never had.
        checks_summary = None if score_payload.get("skipped") else {
            "pct": (score_payload.get("rows_ok", 0) / rows_checked * 100) if rows_checked else 0.0,
            "n": rows_checked,
            # Which half failed, and why — `render` ran the page, `static`
            # only linted it, and the report must not imply they are equal.
            "static_ok": score_payload.get("rows_static_ok", rows_checked),
            "render_ok": score_payload.get("rows_render_ok", rows_checked),
            "reasons": score_payload.get("reasons") or [],
            "advisories": score_payload.get("advisories") or [],
        }
    except FileNotFoundError:
        pass
    return rows_raw, judge_by_row, judge_errors, checks_by_row, checks_summary, advice


def _judge_results(payload) -> tuple[list[dict], list[dict]]:
    """`(results, errors)` from either judge.json shape — the pre-fix bare
    list of results, or the current `{results, errors}` dict."""
    if isinstance(payload, dict):
        return payload.get("results", []), payload.get("errors", [])
    if isinstance(payload, list):
        return payload, []
    return [], []


def _row_judge(judge_row: dict | None) -> dict | None:
    if not judge_row:
        return None
    return {
        "score": judge_row.get("score", 0),
        "checks_failed": bool(judge_row.get("checks_failed")),
        "sub_scores": judge_row.get("sub_scores") or {},
        # Per-dimension findings, each already carrying its severity + cost —
        # what the dashboard's severity chart counts.
        "findings": judge_row.get("findings") or {},
        "rationale": judge_row.get("rationale") or "",
        "strengths": judge_row.get("strengths") or [],
        "weaknesses": judge_row.get("weaknesses") or [],
        "tokens_in": judge_row.get("tokens_in", 0),
        "tokens_out": judge_row.get("tokens_out", 0),
    }


def _page(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minimal Eval Report</title>
<link rel="stylesheet" href="report.css">
<script>
(function () {{
  try {{
    var saved = localStorage.getItem('eval-report-theme');
    if (saved) {{ document.documentElement.setAttribute('data-theme', saved); }}
  }} catch (e) {{ /* private mode: fall back to prefers-color-scheme */ }}
}})();
</script>
</head><body>
<header class="top"><div class="inner">
  <a href="#/" class="brand"><span class="dot"></span>Eval Report</a>
  <nav class="tabs"><a href="#/" data-tab="runs">Runs</a><a href="#/advise" data-tab="advise">Advice</a></nav>
  <div class="spacer"></div>
  <button class="ghost" id="theme-toggle" type="button" aria-label="toggle theme">🌙</button>
</div></header>
<div class="wrap">
  <div id="app"></div>
  <footer class="report-footer">
    <span>{len(data['runs'])} run(s) on disk</span>
    <span>generated {data.get('generated_at', '')}</span>
  </footer>
</div>
<script>window.REPORT_DATA = {payload};</script>
<script src="report.js"></script>
</body></html>
"""
