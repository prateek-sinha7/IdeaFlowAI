"""Deterministic checks over built HTML deliverables. Free — no model call.

Reuses the runtime's own validators (`app.agents.static_check`,
`app.agents.render_check`) so a check measures exactly what production enforces,
never a reimplementation of it. Must never import `judge.py` — the cheap checks
stay independent of the expensive one.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import app.agents.render_check
import app.agents.static_check

from evals.minimal import store


def check_html(html: str) -> dict:
    """Structural + render verdict for one HTML document.

    `check` runs `static_check` (stdlib, no browser) and `render_check` (headless
    Chromium; degrades to `available: False` when Chromium is absent) and returns
    both under one dict, keyed the same way `_source/code_grader.py` did.
    """
    checked = app.agents.static_check.static_check(html)
    finding = {
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
    finding["render"] = _render_findings(html)
    return finding


def check_run(run_id: str, stage: str) -> dict:
    """Check every stored row's `response` for one `(run_id, stage)`.

    ONLY for stages whose config declares an HTML deliverable. specify / plan
    / analyze emit prose, and HTML-checking prose is not a weak signal, it is
    a wrong one: in run 260731-131245 the plan was failed for "no active page:
    expected one <section data-page> with class='is-active'" because it quotes
    `section data-page="{id}"` once, as the TEMPLATE it is instructing the
    build agent to write. specify and analyze passed the same check only
    because they happen not to mention that string — luck, not validation.

    A skipped stage reports `rows_checked: 0` so it reads as "not applicable"
    rather than as a pass, which would be its own lie.
    """
    if not _has_html_deliverable(run_id, stage):
        return {"run_id": run_id, "stage": stage, "rows_checked": 0, "rows_ok": 0,
                "findings": {}, "skipped": "stage has no HTML deliverable"}
    rows = store.read_phase(run_id, "run", stage)
    findings: dict[str, dict] = {}
    rows_checked = 0
    rows_ok = 0
    rows_static_ok = 0
    rows_render_ok = 0
    reasons: list[str] = []
    advisories: list[str] = []
    for row in rows:
        row_id = row.get("row_id") or "unknown"
        html = row.get("response") or ""
        if not html.strip():
            # Counted as checked-and-failed, not skipped. It used to `continue`
            # before incrementing, so a stage whose every dispatch errored
            # reported `rows_checked: 0` -> "checks 0.0 (n=0)", which reads as
            # a 0% pass rate rather than "there was nothing to check". Seen
            # when all five stages 401'd (run 260731-135513).
            findings[row_id] = {"ok": False, "issues": ["empty response"], "warnings": [],
                                 "summary": "no response body", "inventory": {},
                                 "render": {"ok": False, "available": False, "console_errors": [],
                                             "page_errors": [], "nav_results": [],
                                             "coverage_errors": [], "summary": "not rendered — empty response"}}
            rows_checked += 1
            reasons.append(f"{row_id}: empty response — nothing was produced to check")
            continue
        finding = check_html(html)
        findings[row_id] = finding
        rows_checked += 1
        static_ok = bool(finding["ok"])
        render_ok = bool((finding.get("render") or {}).get("ok", True))
        rows_static_ok += int(static_ok)
        rows_render_ok += int(render_ok)
        # THE GATE IS RENDER. It loaded the page in Chromium and walked every
        # nav link, so it reports what the thing actually does. `static` lints
        # the SOURCE against one router convention and fails valid
        # alternatives: run 260731-133221 raised 8 static issues including
        # "the hash router will not reach it" on a page where render found
        # 0/5 nav links dead — the router resolves sections by querySelector
        # and never consults the routes map the lint expects.
        #
        # Static findings are still reported, and still worth reading: in that
        # same run one of the 8 was real (`skuDetail: 'sku'` pointed at a
        # section that does not exist, so that page was genuinely
        # unreachable). They are advisory, not a gate — a lint that fails
        # working output makes the pass rate mean nothing.
        rows_ok += int(render_ok)
        if not render_ok:
            summary = (finding.get("render") or {}).get("summary") or "render failed"
            reasons.append(f"{row_id}: render — {summary}")
        if not static_ok:
            advisories += [f"{row_id}: {issue}" for issue in (finding.get("issues") or [])]
    return {
        "run_id": run_id,
        "stage": stage,
        "rows_checked": rows_checked,
        "rows_ok": rows_ok,
        # Split out, because the two say different things and only one of
        # them ran the page. `render` is ground truth — headless Chromium
        # actually loaded it and walked every nav link. `static` is a
        # CONVENTION lint over the source, so it can fail on a page that
        # demonstrably works (run 260731-133221: 8 static issues, render OK,
        # 0/5 nav links dead, because the router resolves pages by
        # querySelector rather than through the routes map the lint expects).
        # Collapsing them into one number hid which had actually failed.
        "rows_static_ok": rows_static_ok,
        "rows_render_ok": rows_render_ok,
        "reasons": reasons,          # render failures — these fail the gate
        "advisories": advisories,    # static lint — reported, never gating
        "findings": findings,
    }


def _has_html_deliverable(run_id: str, stage: str) -> bool:
    """Does this stage's config name an HTML file as its deliverable?

    The run's own config snapshot is the source of truth — the same field
    `run.py` reads back from the sandbox — so this can never disagree with
    what was actually produced. An unreadable config means check nothing
    rather than check wrongly.
    """
    try:
        deliverable = (store.read_config(run_id)["agents"][stage] or {}).get("deliverable")
    except (FileNotFoundError, KeyError, TypeError):
        return False
    return bool(deliverable) and str(deliverable).lower().endswith((".html", ".htm"))


def _render_findings(html: str) -> dict:
    """Headless-render verdict for one document; a skip when Chromium is absent."""
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
