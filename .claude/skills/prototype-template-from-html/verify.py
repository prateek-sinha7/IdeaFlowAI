#!/usr/bin/env python3.11
"""Verify an od_prototype design template against the full runtime contract.

    python3.11 .claude/skills/prototype-template-from-html/verify.py <template-id>

Every check here exists because something silently broke: a folder dropped for a missing
SKILL.md, a seed cut mid-router at 6,000 chars, a detail endpoint 500 from list-of-string
inputs, a deliverable lost to an `index.html` instruction, a design system that could not
reskin 121 hardcoded hex values.

Exit 0 = all pass. Exit 1 = at least one FAIL (WARN never fails the run).
"""
from __future__ import annotations

import asyncio
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
TEMPLATES = REPO / "skills" / "opendesign" / "design-templates"

# The engine imports assume backend/ is the working root.
sys.path.insert(0, str(BACKEND))

_results: list[tuple[str, str, str]] = []  # (status, label, detail)


def ok(label: str, detail: str = "") -> None:
    _results.append(("PASS", label, detail))


def bad(label: str, detail: str = "") -> None:
    _results.append(("FAIL", label, detail))


def warn(label: str, detail: str = "") -> None:
    _results.append(("WARN", label, detail))


def check(cond: bool, label: str, detail: str = "") -> bool:
    (ok if cond else bad)(label, detail)
    return cond


SCENARIO_TAB = {
    "design": "Design", "personal": "Design", "creator": "Design", "education": "Design",
    "marketing": "Marketing", "sale": "Marketing", "sales": "Marketing",
    "operations": "Operations", "operation": "Operations", "live": "Operations",
    "live-artifacts": "Operations",
    "engineering": "Engineering", "healthcare": "Engineering", "video": "Engineering",
    "product": "Product", "orbit": "Product",
    "finance": "Finance & HR", "hr": "Finance & HR",
}


def main(tid: str) -> int:
    folder = TEMPLATES / tid
    if not folder.is_dir():
        print(f"No such template folder: {folder}")
        return 1

    from app.services import od_loader
    from app.api.prototype_templates import TemplateListItem, TemplateDetail
    from app.agents.static_check import static_check
    from app.agents.render_check import render_check
    from agents.execution_engine.od_context import (
        EXAMPLE_MAX_CHARS,
        get_example_html,
        get_template_injection_parts,
        load_prototype_context,
    )

    od_loader._all_templates.cache_clear()  # never trust a warm cache

    # ---- files -----------------------------------------------------------
    skill = folder / "SKILL.md"
    example = folder / "example.html"
    seed = folder / "assets" / "template.html"
    refs = sorted((folder / "references").glob("*.md")) if (folder / "references").is_dir() else []

    check(skill.is_file(), "SKILL.md present", "without it the folder is silently dropped")
    check(example.is_file(), "example.html present", "sets has_preview; the visual reference")
    if not check(seed.is_file(), "assets/template.html (TEMPLATE SEED) present",
                 "without it build task 2+ gets NO template material"):
        pass

    # ---- loader ----------------------------------------------------------
    listing = od_loader.list_prototype_templates()
    row = next((t for t in listing if t["id"] == tid), None)
    if not check(row is not None, "appears in list_prototype_templates()",
                 f"{len(listing)} prototype templates loaded"):
        return report()

    check(row.get("mode") == "prototype", "od.mode == 'prototype'", repr(row.get("mode")))
    scen = row.get("scenario")
    tab = SCENARIO_TAB.get(scen or "", "Other")
    check(tab != "Other", f"od.scenario '{scen}' maps to a gallery tab", f"-> {tab}")
    check(bool(row.get("has_preview")), "has_preview (example.html found)")

    # ---- API response models (the known 500 trap) ------------------------
    try:
        TemplateListItem(**{k: v for k, v in row.items() if k in TemplateListItem.model_fields})
        ok("TemplateListItem validates")
    except Exception as exc:
        bad("TemplateListItem validates", str(exc)[:160])

    full = od_loader.get_template(tid) or {}
    try:
        TemplateDetail(**{k: v for k, v in full.items() if k in TemplateDetail.model_fields})
        ok("TemplateDetail validates", "GET /api/prototype/templates/{id} will not 500")
    except Exception as exc:
        bad("TemplateDetail validates",
            f"detail endpoint 500s — od.inputs must be a LIST OF MAPPINGS. {str(exc)[:120]}")

    inputs = full.get("inputs")
    if isinstance(inputs, list) and inputs:
        check(all(isinstance(i, dict) for i in inputs), "od.inputs is a list of mappings",
              "list-of-strings 500s the detail endpoint")

    # ---- craft rules -----------------------------------------------------
    want = list(row.get("craft_required") or [])
    if want:
        got = od_loader.get_craft_rules(want)
        got_keys = set(got) if isinstance(got, dict) else set()
        missing = [n for n in want if n not in got_keys]
        check(not missing, "all craft rules resolve", f"missing: {missing}" if missing else str(want))

    # ---- size caps (all silent truncation) -------------------------------
    ex_txt = get_example_html(tid) or ""
    check(0 < len(ex_txt) < EXAMPLE_MAX_CHARS, "example.html under its cap",
          f"{len(ex_txt)} / {EXAMPLE_MAX_CHARS}")

    seed_txt = od_loader.get_template_seed(tid) or ""
    if seed_txt:
        check(len(seed_txt) <= 6000, "seed under the 6,000 cap",
              f"{len(seed_txt)} / 6000 — truncation cuts MID-FILE, losing the router at the tail")
    for r in refs:
        body = r.read_text(encoding="utf-8")
        check(len(body) <= 4000, f"reference {r.name} under the 4,000 cap", f"{len(body)} / 4000")

    parts = get_template_injection_parts(tid)
    check(not any("...[truncated]" in p for p in parts), "no injection part is truncated")
    seed_parts = [p for p in parts if "TEMPLATE SEED" in p]
    check(bool(seed_parts), "seed survives the build-task-2+ filter",
          "task 2+ keeps only parts containing 'TEMPLATE SEED'")
    if seed_parts:
        b = seed_parts[0]
        for needle, what in [("const routes", "routes map"),
                             ("function handleRouteChange", "handleRouteChange"),
                             ("</html>", "closing </html>")]:
            check(needle in b, f"seed still contains the {what} after the cut")

    # ---- launch path -----------------------------------------------------
    ds = od_loader.list_design_systems()
    if ds:
        try:
            ctx = load_prototype_context(tid, ds[0]["id"])
            check(bool(ctx.get("template_body")), "load_prototype_context() resolves",
                  f"template_body {len(ctx['template_body'])} chars")
        except Exception as exc:
            bad("load_prototype_context() resolves", str(exc)[:160])

    # ---- deliverable-name trap ------------------------------------------
    body_txt = full.get("body", "") or ""
    check("index.html" not in body_txt, "SKILL.md body does not say index.html",
          "the deliverable is prototype.html; an index.html instruction empties it")
    outputs = (full.get("outputs") or {}).get("primary")
    if outputs:
        check(outputs == "prototype.html", "od.outputs.primary == prototype.html", repr(outputs))

    # ---- HTML contract ---------------------------------------------------
    for label, path in [("example.html", example), ("seed", seed)]:
        if not path.is_file():
            continue
        html = path.read_text(encoding="utf-8")
        r = static_check(html)
        check(r.ok, f"static_check({label})", "; ".join(r.issues)[:200] if r.issues else "issues []")
        if r.warnings:
            warn(f"static_check({label}) warnings", f"{len(r.warnings)} (orphan sections are advisory)")

        rr = asyncio.run(render_check(str(path.resolve())))  # ABSOLUTE — as_uri() throws otherwise
        if not rr.available:
            warn(f"render_check({label})", "browser unavailable — skipped")
        else:
            detail = (f"console={len(rr.console_errors)} page={len(rr.page_errors)} "
                      f"navs={len(rr.nav_results)} coverage={len(rr.coverage_errors)}")
            check(rr.ok, f"render_check({label})", detail)

        # self-containment + tokens
        check(not re.search(r"https?://", html), f"{label}: no external http(s) refs")
        check(not re.search(r"<link\b", html), f"{label}: no <link> tags")
        check(not re.search(r"<script[^>]+\bsrc=", html), f"{label}: no external <script src>")
        if ":root{" in html or ":root {" in html:
            i0 = html.index(":root")
            i1 = html.index("}", i0)
            outside = re.findall(r"#[0-9a-fA-F]{3,8}\b", html[:i0] + html[i1:])
            check(not outside, f"{label}: no raw hex outside :root",
                  f"{len(outside)} found — a design system cannot reskin those")
        else:
            bad(f"{label}: has a :root token block")
        check(not re.search(r"(?:stroke|fill)=\"var\(", html),
              f"{label}: no var() inside SVG stroke=/fill=", "invalid in a presentation attribute")

    return report()


def report() -> int:
    width = max(len(l) for _, l, _ in _results) + 2
    fails = 0
    print()
    for status, label, detail in _results:
        if status == "FAIL":
            fails += 1
        mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "WARN": " warn "}[status]
        print(f"[{mark}] {label:<{width}} {detail}")
    warns = sum(1 for s, _, _ in _results if s == "WARN")
    print(f"\n{len(_results) - fails - warns} passed, {fails} failed, {warns} warnings")
    if fails:
        print("\nFAILED — do not claim the template is done.")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
