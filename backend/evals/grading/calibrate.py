"""Prove the grading scale still ranks known-good above known-bad.

The inversion this exists to catch went unnoticed for weeks: a hand-verified
golden artifact scored 85.15 while broken output scored in the 90s, because
nothing ever compared the two ends of the scale to each other. `golden/README.md`
states the golden set's purpose exactly — "if the judge gives the golden 89 and a
broken run 91, the rubric, not the agent, is what needs fixing" — and this is the
command that checks it instead of hoping someone reads a report.

Reads COMMITTED files only (`golden/*` and `golden/calibration/fail/*`), never
`.runs/`: run folders are gitignored and disposable, which is why the fixtures
were extracted out of one in the first place.

Dispatch is deliberately not involved. Calibration grades documents that already
exist on disk, so there is no agent to run — but every other stage of the real
pipeline is the real one: the same rubric loader, the same precheck (generic gate
plus each stage's `validate:` hook), the same judge, and the same code track.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from evals.grading import config
from evals.grading.code import code_grader
from evals.grading.model import judge, precheck, scoring

# Which file stands in for each stage's output. `prototype-validate` re-reads the
# build's HTML because a flawless build needs no fixes — the same equivalence
# golden/README.md documents.
STAGE_FILES = (
    ("prototype-specify", "spec.md"),
    ("prototype-plan", "tasks.md"),
    ("prototype-analyze", "analysis.md"),
    ("prototype-build", "prototype.html"),
    ("prototype-validate", "prototype.html"),
)

# Folders under golden/ that are not briefs.
NOT_A_BRIEF = {"calibration"}

# THE INVARIANTS. Deliberately a wide separation: the point is not to certify a
# precise number but to make an INVERSION impossible to miss. A fixture band is
# read from that fixture's own verdict JSON, so a fixture states its own contract.
GOLDEN_MIN = 90.0
MIN_SEPARATION = 25.0
# Above this share of dimensions falling back to untagged `major`, severity is
# mostly fiction and the run is scoring by a different rule than the documented one.
MAX_FALLBACK_RATE = 0.20

EXIT_OK = 0
EXIT_INVARIANT_FAILED = 1
EXIT_USAGE = 2


class FixtureError(RuntimeError):
    """A fixture is missing, altered, or self-contradictory — never a soft warning."""


def golden_dir(workflow_dir: Path) -> Path:
    """The committed golden tree for one workflow."""
    return Path(workflow_dir) / "golden"


def calibration_dir(workflow_dir: Path) -> Path:
    """The committed fixture store: the two ends of the scale, frozen."""
    return golden_dir(workflow_dir) / "calibration"


def golden_briefs(workflow_dir: Path) -> list[str]:
    """Every committed golden brief, in a stable order."""
    root = golden_dir(workflow_dir)
    if not root.is_dir():
        raise FixtureError(f"no golden tree at {root}")
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name not in NOT_A_BRIEF
    )


def fail_fixtures(workflow_dir: Path) -> list[dict]:
    """The known-bad fixtures with their recorded contracts, hash-verified.

    A drifted fixture is a HARD error, not a warning: either the file was edited
    or `static_check` changed underneath it, and both need a human before any
    number computed from it means anything.
    """
    folder = calibration_dir(workflow_dir) / "fail"
    if not folder.is_dir():
        raise FixtureError(
            f"no fail fixtures at {folder} — calibration needs a known-bad end of "
            "the scale, not just a known-good one"
        )

    fixtures = []
    for verdict_path in sorted(folder.glob("*.verdict.json")):
        meta = json.loads(verdict_path.read_text(encoding="utf-8"))
        html_path = verdict_path.with_suffix("").with_suffix(".html")
        if not html_path.exists():
            raise FixtureError(f"{verdict_path.name} describes a missing {html_path.name}")
        html = html_path.read_text(encoding="utf-8")
        actual = hashlib.sha256(html.encode("utf-8")).hexdigest()
        if meta.get("sha256") and actual != meta["sha256"]:
            raise FixtureError(
                f"{html_path.name} no longer matches its recorded sha256 "
                f"({actual[:12]}… vs {meta['sha256'][:12]}…). Either the fixture was "
                "edited or the checkers changed under it — re-freeze it deliberately."
            )
        fixtures.append({"name": meta["name"], "html": html, "meta": meta})
    if not fixtures:
        raise FixtureError(f"no *.verdict.json fixtures found in {folder}")
    return fixtures


def brief_prompts(workflow_dir: Path) -> dict[str, str]:
    """Every dataset row's prompt, keyed by row id, across every dataset."""
    prompts: dict[str, str] = {}
    for dataset in sorted((Path(workflow_dir) / "datasets").glob("*.json")):
        payload = json.loads(dataset.read_text(encoding="utf-8"))
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        for row in rows or []:
            if row.get("id") and row.get("prompt"):
                prompts.setdefault(row["id"], row["prompt"])
    return prompts


# A judge that returns the wrong SHAPE (a missing dimension id, an unparsable
# reply) is usually nondeterminism, not a permanent fault — observed live on the
# very first calibration run, where mistral-large returned 2 of 3 dimensions for
# prototype-analyze. Retrying costs one call; not retrying costs the sweep.
# Rate limits are already retried inside judge.grade; this is the layer above.
JUDGE_SHAPE_RETRIES = 2


async def _judge_with_retry(grade_fn, text: str, **kwargs):
    """Ask the judge again when it answers in an unusable shape."""
    verdict = await grade_fn(text, **kwargs)
    for _ in range(JUDGE_SHAPE_RETRIES):
        if not verdict.errored:
            return verdict
        verdict = await grade_fn(text, **kwargs)
    return verdict


def _code_score(html: str) -> float:
    """The full deterministic verdict for one document: static + render + clicks."""
    finding = code_grader.check_html(html)
    finding["render"] = code_grader._render_findings(html)
    finding["interactions"] = code_grader._interaction_findings(html)
    return code_grader.compute_code_score(finding)


async def grade_document(
    text: str,
    *,
    agent_id: str,
    workflow_dir: Path,
    prompt: str,
    with_code: bool,
    grade_fn=None,
    code_score_fn=None,
) -> dict:
    """Precheck, judge and (for HTML) code-check one document — the real path.

    A precheck failure short-circuits exactly as the pipeline does
    (`skip_on_precheck_failure`): the judge never sees a structurally broken
    document, which is why the code track, not the judge, is what catches it.
    """
    rubric = config.load_rubric(Path(workflow_dir), agent_id)
    passed, reason = precheck.run(
        text, rubric["precheck"], hook=rubric.get("validate_hook")
    )

    code_score = None
    if with_code:
        # OFF-THREAD: the render and interaction sweeps drive Playwright through
        # `asyncio.run`, which cannot be called from inside a running loop — and
        # this coroutine is always inside one. A thread gives them their own.
        code_score = await asyncio.to_thread(code_score_fn or _code_score, text)

    if not passed:
        return {
            "agent_id": agent_id,
            "precheck_passed": False,
            "precheck_reason": reason,
            "judge_score": None,
            "code_score": code_score,
            # A row the pipeline would refuse to carry forward scores zero: a
            # chain that stops producing is a failing run, not a missing sample.
            "effective": 0.0,
            "findings": {},
            "dimensions": 0,
            "fallbacks": 0,
        }

    grade_fn = grade_fn or judge.grade
    verdict = await _judge_with_retry(
        grade_fn,
        text,
        rubric=rubric,
        system_prompt=f"(calibration) {agent_id}",
        prompt=prompt,
        precheck_reason=reason,
    )
    if verdict.errored:
        # NOT fatal to the sweep. A calibration is ~32 judge calls; aborting on
        # the third of them throws away every verdict already paid for and tells
        # you nothing about the scale. The failure is recorded, the sweep
        # continues, and check_invariants fails the RUN at the end — so the
        # result is still "cannot certify", just without burning the evidence.
        return {
            "agent_id": agent_id,
            "precheck_passed": True,
            "precheck_reason": reason,
            "judge_score": None,
            "code_score": code_score,
            "effective": None,
            "judge_error": verdict.error_reason,
            "findings": {},
            "dimensions": 0,
            "fallbacks": 0,
        }

    judge_score = scoring.weighted_total(verdict.sub_scores, rubric["dimensions"])
    return {
        "agent_id": agent_id,
        "precheck_passed": True,
        "precheck_reason": reason,
        "judge_score": judge_score,
        "code_score": code_score,
        "effective": float(code_grader.blended_score(judge_score, code_score)),
        "findings": verdict.dimension_findings,
        "dimensions": len(verdict.sub_scores),
        "fallbacks": verdict.severity_fallbacks,
    }


async def grade_golden_brief(
    brief: str, *, workflow_dir: Path, prompt: str, grade_fn=None, code_score_fn=None
) -> dict:
    """Grade one golden brief across all five stages."""
    folder = golden_dir(workflow_dir) / brief
    stages = []
    for agent_id, filename in STAGE_FILES:
        path = folder / filename
        if not path.exists():
            raise FixtureError(f"golden brief {brief!r} is missing {filename}")
        stages.append(
            await grade_document(
                path.read_text(encoding="utf-8"),
                agent_id=agent_id,
                workflow_dir=workflow_dir,
                prompt=prompt,
                with_code=filename.endswith(".html"),
                grade_fn=grade_fn,
                code_score_fn=code_score_fn,
            )
        )
    graded = [s for s in stages if s["effective"] is not None]
    # An ungradable stage is excluded from the mean rather than counted as zero:
    # a judge that failed to answer says nothing about the artifact, and scoring
    # it zero would blame the golden for the judge's outage. The stage is still
    # reported, and check_invariants refuses to certify the run because of it.
    overall = sum(s["effective"] for s in graded) / len(graded) if graded else 0.0
    return {"name": brief, "kind": "golden", "overall": overall, "stages": stages}


async def grade_fail_fixture(
    fixture: dict, *, workflow_dir: Path, prompts: dict[str, str], grade_fn=None,
    code_score_fn=None,
) -> dict:
    """Grade one known-bad fixture as a build-stage deliverable."""
    meta = fixture["meta"]
    brief = meta.get("brief", "clinic_scheduler")
    stage = await grade_document(
        fixture["html"],
        agent_id="prototype-build",
        workflow_dir=workflow_dir,
        prompt=prompts.get(brief, "(no dataset brief)"),
        with_code=True,
        grade_fn=grade_fn,
        code_score_fn=code_score_fn,
    )
    band = meta.get("expected_band") or {}
    return {
        "name": fixture["name"],
        "kind": "fail",
        "overall": stage["effective"] if stage["effective"] is not None else 0.0,
        "stages": [stage],
        "max_allowed": float(band.get("overall_max", 50)),
        "code_score_min": band.get("code_score_min"),
    }


def check_invariants(results: list[dict]) -> list[str]:
    """Every way the scale can be wrong, each named with its numbers."""
    golden = [r for r in results if r["kind"] == "golden"]
    failing = [r for r in results if r["kind"] == "fail"]
    problems: list[str] = []

    # A scale cannot be certified from stages the judge never graded — but say so
    # WITH the rest of the report, not by aborting halfway through it.
    for result in results:
        for stage in result["stages"]:
            if stage.get("judge_error"):
                problems.append(
                    f"{result['name']} / {stage['agent_id']}: the judge returned no usable "
                    f"verdict after {JUDGE_SHAPE_RETRIES + 1} attempts — {stage['judge_error']}"
                )

    for result in golden:
        if result["overall"] < GOLDEN_MIN:
            worst = min(
                (s for s in result["stages"] if s["effective"] is not None),
                key=lambda s: s["effective"],
                default={"agent_id": "(none graded)", "effective": 0.0, "findings": {}},
            )
            problems.append(
                f"golden {result['name']} scored {result['overall']:.2f} < {GOLDEN_MIN} "
                f"— weakest stage {worst['agent_id']} at {worst['effective']:.2f}"
                + _blame(worst)
            )

    for result in failing:
        if result["overall"] > result["max_allowed"]:
            problems.append(
                f"fail fixture {result['name']} scored {result['overall']:.2f} > "
                f"{result['max_allowed']:.2f} — the scale is not catching it"
            )
        minimum = result.get("code_score_min")
        actual = result["stages"][0].get("code_score")
        if minimum is not None and actual is not None and actual < minimum:
            problems.append(
                f"fail fixture {result['name']} has code_score {actual} < {minimum}: it "
                "has become a STRUCTURAL fixture and no longer tests the judgement half"
            )

    if golden and failing:
        separation = min(r["overall"] for r in golden) - max(r["overall"] for r in failing)
        if separation < MIN_SEPARATION:
            problems.append(
                f"separation {separation:.2f} < {MIN_SEPARATION}: known-good and "
                "known-bad are too close for any threshold between them to mean anything"
            )
    return problems


def _blame(stage: dict) -> str:
    """Name the finding that cost a stage the most, so a failure is actionable."""
    for dimension, findings in (stage.get("findings") or {}).items():
        for finding in findings:
            if finding.get("severity") in ("blocking", "major"):
                return (
                    f"; {dimension} carries a {finding['severity']} finding: "
                    f"{finding['detail'][:120]}"
                )
    return ""


def fallback_rate(results: list[dict]) -> tuple[int, int]:
    """(dimensions that fell back to untagged `major`, dimensions judged)."""
    fallbacks = sum(s["fallbacks"] for r in results for s in r["stages"])
    dimensions = sum(s["dimensions"] for r in results for s in r["stages"])
    return fallbacks, dimensions


def baseline_block(results: list[dict]) -> str:
    """A paste-ready `baseline:` block derived from the OBSERVED golden ceiling.

    Printed rather than written: re-pinning is a deliberate act, and a command
    that silently rewrote the thresholds it just validated would be marking its
    own homework.
    """
    golden = [r for r in results if r["kind"] == "golden"]
    if not golden:
        return ""
    ceiling = min(r["overall"] for r in golden)
    floor = max(0, int(ceiling) - 20)
    return (
        "baseline:\n"
        "  min_precheck_pass_rate: 1.0\n"
        f"  min_average_score: {floor}    # ~20 below the observed golden ceiling "
        f"({ceiling:.2f})\n"
        "  min_negative_correct: 1.0\n"
        "  min_distinct_scores: 3\n"
        "  max_expected_stddev: null\n"
    )


def run_calibration(
    workflow_name: str, *, grade_fn=None, code_score_fn=None, echo=print
) -> int:
    """Grade both ends of the scale and assert the invariants between them."""
    workflow = config.load_workflow(workflow_name)
    workflow_dir = Path(workflow["workflow_dir"])

    fixtures = fail_fixtures(workflow_dir)          # hash-verified before anything runs
    briefs = golden_briefs(workflow_dir)
    prompts = brief_prompts(workflow_dir)

    missing = [brief for brief in briefs if brief not in prompts]
    if missing:
        # Named, never silently skipped: a brief dropped from the sweep would
        # read as full coverage in the table below.
        echo(f"  NOTE  no dataset brief for {', '.join(missing)} — graded with a stub prompt")

    async def _run() -> list[dict]:
        results = []
        for brief in briefs:
            results.append(
                await grade_golden_brief(
                    brief,
                    workflow_dir=workflow_dir,
                    prompt=prompts.get(brief, f"Build a prototype for {brief}."),
                    grade_fn=grade_fn,
                    code_score_fn=code_score_fn,
                )
            )
        for fixture in fixtures:
            results.append(
                await grade_fail_fixture(
                    fixture, workflow_dir=workflow_dir, prompts=prompts,
                    grade_fn=grade_fn, code_score_fn=code_score_fn,
                )
            )
        return results

    results = asyncio.run(_run())
    problems = check_invariants(results)
    _print_report(results, problems, echo)
    return EXIT_INVARIANT_FAILED if problems else EXIT_OK


def _print_report(results: list[dict], problems: list[str], echo) -> None:
    """The whole calibration on one screen, failures first."""
    echo("")
    echo("  calibration — does the scale still rank known-good above known-bad?")
    echo("")
    echo(f"  {'fixture':<26}{'kind':<9}{'overall':>9}   stages")
    for result in results:
        stages = " ".join(
            "  ?" if s["effective"] is None else f"{s['effective']:.0f}"
            for s in result["stages"]
        )
        echo(f"  {result['name']:<26}{result['kind']:<9}{result['overall']:>9.2f}   {stages}")

    golden = [r for r in results if r["kind"] == "golden"]
    failing = [r for r in results if r["kind"] == "fail"]
    echo("")
    if golden:
        echo(f"  golden ceiling   {min(r['overall'] for r in golden):.2f} (worst brief) "
             f"· threshold >= {GOLDEN_MIN}")
    if golden and failing:
        separation = min(r["overall"] for r in golden) - max(r["overall"] for r in failing)
        echo(f"  separation       {separation:.2f} · threshold >= {MIN_SEPARATION}")

    fallbacks, dimensions = fallback_rate(results)
    if dimensions:
        rate = fallbacks / dimensions
        note = "  <-- severity is mostly inferred, not reported" if rate > MAX_FALLBACK_RATE else ""
        echo(f"  severity tagged  {dimensions - fallbacks}/{dimensions} dimensions{note}")

    echo("")
    if problems:
        echo("  FAILED")
        for problem in problems:
            echo(f"    - {problem}")
    else:
        echo("  PASSED — every invariant holds.")
        echo("")
        echo("  Re-pin each rubric's baseline with:")
        echo("")
        for line in baseline_block(results).splitlines():
            echo(f"    {line}")
