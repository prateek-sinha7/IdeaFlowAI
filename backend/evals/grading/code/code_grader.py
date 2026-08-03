"""Code-track grading: deterministic checks over the built HTML deliverables.

Reads the HTML from a model-track run folder and reuses the runtime's own
checkers, so grading measures exactly what the pipeline enforces — then goes
one step further than the runtime does: an interaction sweep that clicks the
buttons and types into the filters a user actually would. No judge model is
ever involved; the only cost is a few seconds of headless Chromium per row.
Must never import judge.py — the cheap checks stay independent of the
expensive ones.

Each graded row gets a deterministic `code_score` (0-100, see
`compute_code_score`) so the code track produces a number comparable across
runs, not just a list of findings. The score is written into the stage's
`<token>_code_findings.json`, where the markdown reports blend it next to the
judge's score.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import app.agents.render_check
import app.agents.static_check

from evals.grading import artifacts

# Both HTML-producing stages are graded: build writes the first prototype.html,
# validate writes the fixed one — the file a user would actually receive.
GRADED_STAGES = (
    {"agent_id": "prototype-build", "token": "prototype_build", "file": "prototype.html"},
    {"agent_id": "prototype-validate", "token": "prototype_validate", "file": "prototype.final.html"},
)
FINDINGS_KIND = "code_findings"

# How each finding kind moves the 0-100 code score. Flat, documented penalties:
# an explainable number beats a clever one, and these mirror how severe each
# failure is to a user (an uncaught exception outranks a lint-ish warning).
PENALTIES = {
    "static_issue": 15,
    "static_warning": 3,
    "console_error": 10,
    "page_error": 15,
    "dead_nav": 10,
    "coverage_error": 20,
    "interaction_failure": 10,
}

# How much of a blended score the code track contributes where both tracks
# graded a row. The judge stays the majority voice — it reads intent — while
# the code score anchors it to what verifiably works in a browser.
CODE_WEIGHT = 0.3

# THE CEILING BAND. Averaging alone let a verifiably broken page survive on the
# judge's opinion: code 0 with a judge score of 90 blended to 63 — a D. And in
# the middle of the range, a page with three dead navs (code 70) graded 92 by the
# judge landed at 85, a solid B for navigation that is a third broken.
#
# A floor gate ("bound the cell only when code < 40") was considered and
# rejected: `prototype_build_validate.check` already fails a row on
# `not static_check(...).ok` and the rubric sets `skip_on_precheck_failure`, so a
# structurally broken document never reaches the judge and the gate would be dead
# code. The band binds across the whole range instead.
#
# It is a `min`, so it can only ever LOWER a value — at code 100 the ceiling is
# 115 and it never binds, which is why a clean run's arithmetic is unchanged.
CODE_BAND = 15


def blended_score(judge_score, code_score):
    """`0.7 * judge + 0.3 * code`, capped at `code + 15`.

    Or whichever score exists when only one track graded the row — with one
    track there is nothing to bound against.
    """
    if judge_score is None:
        return code_score
    if code_score is None:
        return judge_score
    blended = (1 - CODE_WEIGHT) * float(judge_score) + CODE_WEIGHT * float(code_score)
    return min(blended, float(code_score) + CODE_BAND)


# Interaction sweep bounds — enough to exercise a prototype's controls without
# turning one pathological page into a minute-long crawl.
MAX_CLICKS = 12
MAX_INPUTS = 5
INPUT_PROBE_TEXT = "test"


def grade_run_folder(
    dataset_run_id: str,
    *,
    workflow_dir: Path,
    render: bool = True,
    interactions: bool = True,
    only: list[str] | None = None,
) -> dict:
    """Run the deterministic checks over every graded stage's HTML in one run.

    Reads each row's HTML from the same run folder the model track produced,
    keyed by the stable row id, so a finding traces back to the brief that
    produced it. Writes one `<token>_code_findings.json` per stage, alongside
    the model track's artifacts, where the reports read them back.

    `only` restricts grading to the named agent ids — the model track's
    auto-call uses it to grade just the stages whose HTML this run produced.
    """
    run_dir = artifacts.run_folder(dataset_run_id, workflow_dir=Path(workflow_dir))
    stages = []
    for stage in GRADED_STAGES:
        if only is not None and stage["agent_id"] not in only:
            continue
        result = _grade_stage(
            run_dir, stage, dataset_run_id, render=render, interactions=interactions
        )
        if result is not None:
            stages.append(result)

    if not stages:
        return {
            "dataset_run_id": dataset_run_id,
            "status": "nothing_to_grade",
            "reason": (
                "this run folder has no HTML-producing stage "
                f"({', '.join(s['agent_id'] for s in GRADED_STAGES)}), so there is "
                "nothing to check. Run a config whose `agents` include one "
                "(`grade.sh full`), or point --from-run at a run that did."
            ),
            "stages": [],
        }
    return {"dataset_run_id": dataset_run_id, "status": "graded", "stages": stages}


def _grade_stage(
    run_dir: Path, stage: dict, dataset_run_id: str, *, render: bool, interactions: bool
) -> dict | None:
    """Grade one stage's rows, or None when that stage never ran."""
    try:
        runs = artifacts.read_stage_artifact(run_dir, stage["token"], "run")
    except FileNotFoundError:
        return None

    result = {
        "dataset_run_id": dataset_run_id,
        "agent_id": stage["agent_id"],
        "deliverable_file": stage["file"],
        "render": render,
        "interactions": interactions,
        "status": "graded",
        "missing": [],
        "rows_checked": 0,
        "rows_ok": 0,
        "average_code_score": None,
        "findings": {},
    }

    for row in runs:
        row_id = _row_id(row)
        if row.get("errored") or row.get("skip_reason") or row.get("expect") == "fail":
            continue
        html = row.get("response") or ""
        if not html.strip():
            result["missing"].append(row_id)
            continue
        finding = check_html(html)
        if render:
            finding["render"] = _render_findings(html)
        if interactions:
            finding["interactions"] = _interaction_findings(html)
        finding["code_score"] = compute_code_score(finding)
        result["findings"][row_id] = finding
        result["rows_checked"] += 1
        result["rows_ok"] += int(finding["ok"])
        _write_check_log(run_dir, stage, row_id, finding)

    if not result["findings"]:
        result["status"] = "nothing_to_grade"
        result["reason"] = (
            f"the {stage['agent_id']} stage ran but no row returned a {stage['file']} body"
        )
        return result

    scores = [finding["code_score"] for finding in result["findings"].values()]
    result["average_code_score"] = sum(scores) / len(scores)
    _write_findings(run_dir, stage["token"], result)
    return result


def compute_code_score(finding: dict) -> float:
    """Deterministic 0-100 score for one document's findings.

    Starts at 100 and subtracts a flat, named penalty per finding (see
    PENALTIES), floored at 0. A skipped check (Chromium absent) subtracts
    nothing — the score is a lower bound on brokenness, never a guess.
    """
    score = 100.0
    score -= PENALTIES["static_issue"] * len(finding.get("issues") or [])
    score -= PENALTIES["static_warning"] * len(finding.get("warnings") or [])

    rendered = finding.get("render") or {}
    if rendered.get("available"):
        score -= PENALTIES["console_error"] * len(rendered.get("console_errors") or [])
        score -= PENALTIES["page_error"] * len(rendered.get("page_errors") or [])
        score -= PENALTIES["dead_nav"] * sum(
            1 for nav in rendered.get("nav_results") or [] if not nav.get("ok")
        )
        score -= PENALTIES["coverage_error"] * len(rendered.get("coverage_errors") or [])

    interactions = finding.get("interactions") or {}
    if interactions.get("available"):
        score -= PENALTIES["interaction_failure"] * len(interactions.get("failures") or [])
    return max(0.0, min(100.0, score))


def check_html(html: str) -> dict:
    """Structural verdict for one document, via the runtime's static_check."""
    checked = app.agents.static_check.static_check(html)
    return {
        "ok": checked.ok,
        "issues": list(checked.issues),
        "warnings": list(checked.warnings),
        "summary": checked.summary(),
        "inventory": {
            "sections": list(checked.sections),
            "nav_hrefs": list(checked.nav_hrefs),
            "route_ids": list(checked.route_ids),
            "note": checked.note,
        },
    }


def _row_id(row: dict) -> str:
    """The stable row id, under either the current or the committed-run key."""
    return row.get("row_id") or row.get("scenario_id") or "unknown"


def _render_findings(html: str) -> dict:
    """Headless-render verdict for one document; a skip when Chromium is absent.

    Includes the per-route nav results — render_check clicks every discovered
    nav target and reports which section actually activated, which is the
    "does navigation work" evidence the code report exists to show.
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "prototype.html"
        path.write_text(html, encoding="utf-8")
        rendered = asyncio.run(app.agents.render_check.render_check(path))
    return {
        "ok": rendered.ok,
        "available": rendered.available,
        "console_errors": list(rendered.console_errors),
        "page_errors": list(rendered.page_errors),
        "nav_results": [
            {
                "href": nav.href,
                "expected": nav.expected,
                "activated": nav.activated,
                "ok": nav.ok,
            }
            for nav in rendered.nav_results
        ],
        "coverage_errors": list(rendered.coverage_errors),
        "summary": rendered.summary(),
    }


def _interaction_findings(html: str) -> dict:
    """Exercise the page's controls the way a user would; a skip without Chromium.

    Clicks up to MAX_CLICKS buttons and types into up to MAX_INPUTS text/search
    fields (dispatching real input events so filter handlers fire). Any console
    error or uncaught exception raised BY an action is attributed to it — the
    class of breakage a load-time render check cannot see.
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "prototype.html"
        path.write_text(html, encoding="utf-8")
        return asyncio.run(_interaction_check(path))


async def _interaction_check(path: Path) -> dict:
    """The Playwright interaction sweep over one file. Never raises."""
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001 - an absent browser is a skip, not an error
        return {"available": False, "note": f"Playwright unavailable: {exc}"}

    actions: list[dict] = []
    failures: list[dict] = []
    errors: list[str] = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(args=["--no-sandbox"])
        except Exception as exc:  # noqa: BLE001 - browser binary absent -> skip
            return {"available": False, "note": f"Chromium unavailable: {exc}"}
        try:
            page = await browser.new_page()
            page.on(
                "console",
                lambda m: errors.append(m.text) if m.type == "error" else None,
            )
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(path.as_uri(), wait_until="networkidle", timeout=15000)
            errors.clear()  # load-time errors belong to render_check, not to an action

            await _sweep_clicks(page, actions, failures, errors)
            await _sweep_inputs(page, actions, failures, errors)
        except Exception as exc:  # noqa: BLE001 - the sweep must never fail the grade
            failures.append({"action": "sweep", "target": str(path.name), "errors": [str(exc)]})
        finally:
            await browser.close()

    return {
        "available": True,
        "ok": not failures,
        "actions": actions,
        "failures": failures,
    }


async def _sweep_clicks(page, actions: list, failures: list, errors: list) -> None:
    """Click each distinct VISIBLE button-like control once, watching for errors.

    Visibility is the eligibility test: an SPA keeps every inactive page's
    controls in the DOM but hidden, and a hidden button timing out under a
    click is the sweep's limitation, not the prototype's bug.
    """
    handles = await page.query_selector_all("button, [role='button'], .btn")
    visible = [handle for handle in handles if await _is_visible(handle)]
    for handle in visible[:MAX_CLICKS]:
        label = await _control_label(handle)
        await _perform(
            page, actions, failures, errors,
            action="click", target=label, handle=handle,
            doing=lambda h=handle: h.click(timeout=2000),
        )


async def _sweep_inputs(page, actions: list, failures: list, errors: list) -> None:
    """Type into each visible text/search field, firing the events filters bind to."""
    handles = await page.query_selector_all(
        "input[type='text'], input[type='search'], input:not([type])"
    )
    visible = [handle for handle in handles if await _is_visible(handle)]
    for handle in visible[:MAX_INPUTS]:
        label = await _control_label(handle)

        async def typing(h=handle):
            await h.fill(INPUT_PROBE_TEXT, timeout=2000)
            await h.dispatch_event("input")
            await h.dispatch_event("change")

        await _perform(
            page, actions, failures, errors,
            action="type", target=label, handle=handle, doing=typing,
        )


async def _is_visible(handle) -> bool:
    """Whether a control can actually be interacted with right now."""
    try:
        return await handle.is_visible()
    except Exception:  # noqa: BLE001 - a detached handle is not interactable
        return False


async def _perform(page, actions: list, failures: list, errors: list, *, action, target, handle, doing):
    """Run one probe, settle briefly, and attribute any new error to it.

    The eligibility snapshot races the app: an earlier click can navigate the
    SPA and hide a control that was visible when enumerated. So visibility is
    re-checked at act time, and a control that has legitimately gone hidden is
    skipped — only a control that is STILL visible and cannot be acted on is a
    finding.
    """
    if not await _is_visible(handle):
        return
    before = len(errors)
    outcome = {"action": action, "target": target}
    try:
        await doing()
        await page.wait_for_timeout(50)
    except Exception as exc:  # noqa: BLE001 - a dead control is a finding, not a crash
        if not await _is_visible(handle):
            return  # hidden mid-action by the app's own navigation — not a defect
        outcome["errors"] = [f"{type(exc).__name__}: {exc}"]
        failures.append(outcome)
        return
    new_errors = errors[before:]
    if new_errors:
        outcome["errors"] = list(new_errors)
        failures.append(outcome)
    else:
        actions.append(outcome)


async def _control_label(handle) -> str:
    """A short human-readable name for a control — what the report will print."""
    try:
        text = (await handle.inner_text() or "").strip()
    except Exception:  # noqa: BLE001 - a detached handle still deserves a name
        text = ""
    if text:
        return " ".join(text.split())[:60]
    try:
        for attribute in ("id", "name", "placeholder", "aria-label"):
            value = await handle.get_attribute(attribute)
            if value:
                return f"[{attribute}={value}]"[:60]
    except Exception:  # noqa: BLE001
        pass
    return "(unlabelled)"


def _write_check_log(run_dir: Path, stage: dict, row_id: str, finding: dict) -> None:
    """One row's check transcript: every probe performed and its outcome.

    Lives in `logs/<row_id>/<token>_code_checks.log`, beside that row's dispatch
    transcripts, because "what was actually exercised" is evidence the findings
    JSON buries: a row with zero failures reads identically whether ten controls
    were clicked or none were discoverable. Never fails the grade over a log.
    """
    try:
        path = artifacts.log_path(run_dir, f"{stage['token']}_code_checks", row_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(_check_log_lines(stage, row_id, finding)) + "\n",
                        encoding="utf-8")
    except OSError:
        pass


def _check_log_lines(stage: dict, row_id: str, finding: dict) -> list[str]:
    """The transcript's lines — one per check, outcome first."""
    lines = [
        f"code checks: {stage['agent_id']} / {row_id} ({stage['file']})",
        f"code score: {finding.get('code_score')}",
        "",
        f"[static] {'ok' if finding.get('ok') else 'FAILED'} — {finding.get('summary', '')}",
    ]
    lines += [f"  issue: {issue}" for issue in finding.get("issues") or []]
    lines += [f"  warning: {warning}" for warning in finding.get("warnings") or []]

    rendered = finding.get("render") or {}
    if not rendered:
        lines.append("\n[render] not run")
    elif not rendered.get("available"):
        lines.append(f"\n[render] skipped — {rendered.get('summary', 'browser unavailable')}")
    else:
        lines.append(
            f"\n[render] {len(rendered.get('console_errors') or [])} console error(s), "
            f"{len(rendered.get('page_errors') or [])} uncaught exception(s)"
        )
        lines += [f"  console error: {error}" for error in rendered.get("console_errors") or []]
        lines += [f"  uncaught: {error}" for error in rendered.get("page_errors") or []]
        for nav in rendered.get("nav_results") or []:
            outcome = "ok" if nav.get("ok") else "DEAD"
            lines.append(
                f"  nav {nav.get('href')} → expected '{nav.get('expected')}', "
                f"activated '{nav.get('activated')}'  {outcome}"
            )
        lines += [f"  coverage: {error}" for error in rendered.get("coverage_errors") or []]

    interactions = finding.get("interactions") or {}
    if not interactions:
        lines.append("\n[interactions] not run")
    elif not interactions.get("available"):
        lines.append(f"\n[interactions] skipped — {interactions.get('note', 'browser unavailable')}")
    else:
        actions = interactions.get("actions") or []
        failures = interactions.get("failures") or []
        lines.append(
            f"\n[interactions] {len(actions) + len(failures)} exercised, {len(failures)} failed"
        )
        lines += [f"  {probe.get('action')} '{probe.get('target')}'  ok" for probe in actions]
        lines += [
            f"  {probe.get('action')} '{probe.get('target')}'  FAILED: "
            + "; ".join(probe.get("errors") or [])
            for probe in failures
        ]
    return lines


def read_findings(run_dir: Path, agent_token: str) -> dict | None:
    """One stage's stored code findings, or None when the code track never ran."""
    path = artifacts.artifact_path(run_dir, agent_token, FINDINGS_KIND)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_findings(run_dir: Path, agent_token: str, result: dict) -> None:
    """Write the findings into the model track's own artifacts folder."""
    path = artifacts.artifact_path(run_dir, agent_token, FINDINGS_KIND)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
