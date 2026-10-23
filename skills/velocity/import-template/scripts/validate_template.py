#!/usr/bin/env python3
"""Validate an imported template folder against what VelocityAI actually reads.

Run with the BACKEND venv so the real loader and frame finder are used:

    backend/.venv/bin/python validate_template.py <template-dir> [--json]

<template-dir> is ``<od-root>/design-templates/<id>``. The od-root is derived
from it, so a scratch copy of skills/opendesign validates the same way.

Checks (E = error, fails the run; W = warning; I = info):
  * folder id is kebab-case; SKILL.md frontmatter parses with the loader
  * required fields: name, description, triggers (>=3), od.mode prototype|deck,
    od.platform, od.scenario, od.preview.entry=example.html,
    od.design_system.requires (bool), od.example_prompt, od.inputs, od.outputs
  * craft names exist in craft/; body sections the pipelines rely on
  * example.html: present, size vs the 120k prompt cap, no runtime leftovers
    (support.js, DCLogic, __bundler, x-dc, React), external URLs only for fonts,
    :root role variables the design system can override, hex outside :root
  * prototype: template_kit finds a frame (content area + >=2 nav items);
    >=2 section.pattern[data-pattern]; every nav data-go has a pattern
  * deck: >=3 section.slide, keyboard navigation script, no assets/ references
  * referenced assets/... files exist; no build leftovers in the folder
  * the real od_loader lists it in the right gallery with has_preview, and
    the gallery tab it lands in (same rules as the frontend)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROTO_BUCKETS = {
    "Design": ["design", "personal", "creator", "education"],
    "Marketing": ["marketing", "sale", "sales"],
    "Operations": ["operations", "operation", "live", "live-artifacts"],
    "Engineering": ["engineering", "healthcare", "video"],
    "Product": ["product", "orbit"],
    "Finance & HR": ["finance", "hr"],
}
ROLE_VARS = ["--bg", "--surface", "--fg", "--muted", "--border", "--accent"]
LEFTOVERS = re.compile(r"support\.js|extends DCLogic|__bundler|<x-dc\b|\bx-dc\s*\{|React\.createElement|ReactDOM|data-snap-|__CONTENT__|#dc-root|\bsc-host\b|\bsc-interp\b|@keyframes\s+sc-")
SCRATCH = re.compile(r"/private/tmp/|/tmp/|scratchpad|/Users/[^/\s]+/|tests/[\w-]+/")
PROTO_SECTIONS = ["what this", "chrome", "how the example is organised", "screen patterns", "interactions", "hard rules"]
DECK_SECTIONS = ["what this", "workflow", "slide", "hard rules"]


def proto_bucket(scenario: str | None) -> str:
    s = (scenario or "").lower()
    for tab, vals in PROTO_BUCKETS.items():
        if s in vals:
            return tab
    return "Other (only under All)"


def deck_bucket(name: str, scenario: str | None) -> str:
    n, s = name.lower(), (scenario or "").lower()
    if any(k in n for k in ("pitch", "investor", "ib-pitch", "fundrais")):
        return "Pitch Deck"
    if any(k in n for k in ("tech", "code", "terminal", "engineering")):
        return "Tech"
    if any(k in n for k in ("editorial", "magazine", "kami", "guizang")):
        return "Editorial"
    if any(k in n for k in ("weekly", "report", "quarterly", "course", "training")):
        return "Business"
    if any(k in n for k in ("minimal", "simple", "clean", "dir-key")):
        return "Minimal"
    if s in ("design", "creative", "artistic", "creator") or any(k in n for k in ("replit", "open-design", "landing")):
        return "Creative"
    return "All only (no tab)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("template_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--describe", action="store_true", help="also print what each pattern contains (headings, buttons, list sizes) to base the SKILL.md on")
    ap.add_argument("--draft", metavar="KIND", choices=["prototype", "deck"], help="describe a draft folder (example.html only, anywhere, no SKILL.md yet) and exit")
    args = ap.parse_args()
    tdir = Path(args.template_dir).resolve()
    if args.draft:
        return describe_draft(tdir, args.draft)
    od_root = tdir.parent.parent
    repo = Path(__file__).resolve().parents[4]
    os.environ["OD_ROOT"] = str(od_root)
    sys.path.insert(0, str(repo / "backend"))

    E: list[str] = []
    W: list[str] = []
    I: list[str] = []

    if tdir.parent.name != "design-templates":
        E.append(f"{tdir} is not inside a design-templates/ folder")
    tid = tdir.name
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", tid):
        E.append(f"folder id '{tid}' is not kebab-case")
    skill = tdir / "SKILL.md"
    if not skill.is_file():
        E.append("SKILL.md missing -- the loader skips the folder")
        return report(E, W, I, args.json)

    from app.services import od_loader  # noqa: E402  (OD_ROOT set above)

    fm, body = od_loader._parse_frontmatter(skill.read_text(encoding="utf-8"))
    if not fm:
        E.append("SKILL.md frontmatter missing or not valid YAML")
        return report(E, W, I, args.json)
    od = fm.get("od") or {}
    mode = od.get("mode")
    shape = od.get("shape")
    thin = shape == "thin"
    if shape not in (None, "full", "thin"):
        E.append(f"od.shape is {shape!r}; use thin (one finished screen) or omit it")
    if thin and mode != "prototype":
        E.append("od.shape: thin is for prototypes only")
    name = str(fm.get("name") or "")
    if not name:
        E.append("name missing")
    if not od_loader._flatten_description(fm.get("description")):
        E.append("description missing")
    trig = fm.get("triggers") or []
    if not isinstance(trig, list) or len(trig) < 3:
        E.append("triggers must be a list of at least 3 phrases (gallery search)")
    if mode not in ("prototype", "deck"):
        E.append(f"od.mode is {mode!r}; must be 'prototype' or 'deck' or the template is in no gallery")
    if "category" in fm:
        W.append("top-level 'category' is read by nothing; the tab comes from od.scenario (prototype) or the name (deck)")
    scenario = od.get("scenario")
    if mode == "prototype":
        if od.get("platform") not in ("desktop", "mobile"):
            W.append(f"od.platform is {od.get('platform')!r}; use desktop or mobile")
        tab = proto_bucket(scenario)
        (W if tab.startswith("Other") else I).append(f"prototype gallery tab: {tab} (od.scenario={scenario!r})")
    elif mode == "deck":
        tab = deck_bucket(name, scenario)
        (W if tab.startswith("All only") else I).append(f"deck gallery tab: {tab} (decided by the name {name!r})")
        if not scenario:
            W.append("od.scenario missing")
    prev = (od.get("preview") or {}).get("entry")
    if prev != "example.html":
        W.append(f"od.preview.entry is {prev!r}; the app always serves example.html -- set it to example.html")
    ds = od.get("design_system")
    if not isinstance(ds, dict) or not isinstance(ds.get("requires"), bool):
        E.append("od.design_system.requires must be true or false")
    elif mode == "deck" and ds.get("requires") is False:
        I.append("deck with design_system.requires: false -- the design-system picker is hidden for it")
    if not (od.get("example_prompt") or fm.get("example_prompt")):
        W.append("od.example_prompt missing (prefills the brief)")
    if not od.get("inputs"):
        W.append("od.inputs missing")
    if not (od.get("outputs") or {}).get("primary"):
        W.append("od.outputs.primary missing")
    craft = (od.get("craft") or {}).get("requires") or []
    known = {p.stem for p in (od_root / "craft").glob("*.md")} - {"README"}
    for c in craft:
        if c not in known:
            E.append(f"od.craft.requires '{c}' is not in craft/ (silently dropped)")

    low = body.lower()
    heads = [h.strip().lower() for h in re.findall(r"^#{2,3}\s+(.+)$", body, re.M)]
    need = PROTO_SECTIONS if mode == "prototype" else DECK_SECTIONS
    for s in need:
        if not any(s in h for h in heads):
            W.append(f"SKILL.md body has no section matching '{s}'")
    if len(body.strip()) < 800:
        W.append("SKILL.md body is very short; builders follow it as their instructions")
    if "<artifact" in low:
        W.append("SKILL.md body mentions an <artifact> wrapper; the file contract is example.html")

    ex = tdir / "example.html"
    if not ex.is_file():
        E.append("example.html missing -- the template is hidden from the gallery")
    else:
        html = ex.read_text(encoding="utf-8", errors="replace")
        n = len(html)
        if n > 120_000:
            W.append(f"example.html is {n:,} chars; the prompt copy is cut at 120,000 (sandbox copy is full)")
        else:
            I.append(f"example.html {n:,} chars (cap 120,000)")
        for m in LEFTOVERS.finditer(html):
            E.append(f"runtime leftover in example.html: {m.group(0)!r}")
            break
        urls = sorted(set(re.findall(r"https?://[^\s\"')>]+", html)))
        ext = [u for u in urls if not re.search(r"fonts\.(googleapis|gstatic)\.com|w3\.org", u)]
        if ext:
            W.append(f"{len(ext)} external URL(s) besides fonts: {ext[:5]}")
        if re.search(r"<script[^>]+src=[\"']https?://", html, re.I):
            E.append("example.html loads a remote <script>")
        if re.search(r"url\(\s*['\"]?data:font", html):
            W.append("embedded data: fonts -- use a Google Fonts @import instead (size)")
        roots = " ".join(re.findall(r":root\s*\{([^}]*)\}", html))
        missing = [v for v in ROLE_VARS if not re.search(re.escape(v) + r"\s*:", roots)]
        if missing:
            W.append(f":root does not declare {missing}; the design system cannot re-theme those roles")
        try:
            from agents.capabilities.assemble_step import TEMPLATE_THEME_VARS

            declared = set(re.findall(r"(--[\w-]+)\s*:", html))
            hit = sorted(k for k, names in TEMPLATE_THEME_VARS.items() if declared & set(names))
            I.append(f"theme keys the design system can override: {len(hit)}/{len(TEMPLATE_THEME_VARS)} {hit}")
        except Exception as exc:  # pragma: no cover
            W.append(f"could not import TEMPLATE_THEME_VARS: {exc}")
        style_text = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I)) + "\n".join(re.findall(r'style="([^"]*)"', html))
        outside = re.sub(r":root\s*\{[^}]*\}", "", style_text)
        hex_out = len(re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", outside))
        I.append(f"hex literals outside :root: {hex_out}")
        root_vals = dict(re.findall(r"(--(?:bg|surface|fg|muted|border|accent))\s*:\s*(#[0-9a-fA-F]{6})\b", roots))
        leaked = sorted({k for k, v in root_vals.items() if re.search(re.escape(v) + r"\b", outside, re.I)})
        if leaked:
            W.append(f"role colours written as literals outside :root (the design system cannot re-theme them): {leaked}")
        rv = {k: v.lower() for k, v in root_vals.items()}
        dup = sorted(k for k in ("--surface", "--muted", "--border") if rv.get(k) and rv.get(k) in (rv.get("--fg"), rv.get("--bg")) and not (k == "--surface" and rv.get(k) == rv.get("--bg")))
        if dup:
            W.append(f"role check: {dup} share a value with --fg/--bg -- probably a wrong role pick")
        if not re.search(r"--accent-on\s*:", roots):
            W.append(":root does not declare --accent-on (text on accent buttons)")
        styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I)
        for i, st in enumerate(styles):
            if st.count("/*") != st.count("*/"):
                E.append(f"<style> block {i + 1}: unbalanced CSS comments -- everything after the open comment is ignored")
            depth = 0
            for ch in re.sub(r"/\*.*?\*/", "", st, flags=re.S):
                depth += ch == "{"
                depth -= ch == "}"
                if depth < 0:
                    break
            if depth != 0:
                E.append(f"<style> block {i + 1}: unbalanced braces")
        all_css = "\n".join(styles)
        body_html = html.split("<body", 1)[-1]
        used = set()
        for cl in re.findall(r'class="([^"]*)"', re.sub(r"<script\b.*?</script>", "", body_html, flags=re.S)):
            used.update(cl.split())
        gen = sorted(c for c in used if re.fullmatch(r"[a-z]{2,3}-[0-9a-z]{1,3}", c))
        defined = set(re.findall(r"\.([\w-]+)", all_css))
        undefined = [c for c in gen if c not in defined]
        if undefined:
            E.append(f"{len(undefined)} shared classes are used but have no CSS rule (lost styling): {undefined[:8]}")
        if len(re.findall(r"<main\b", body_html)) > 1:
            W.append("more than one <main>: template_kit uses the first as the content area")
        if "data-screen-label" in html:
            W.append("data-screen-label attributes left from the export")
        if SCRATCH.search(html):
            E.append(f"example.html contains a local/scratch path: {SCRATCH.search(html).group(0)!r}")
        fonts_import = len(re.findall(r"@import\s+url\(['\"]?https://fonts\.googleapis", html)) + len(re.findall(r"<link[^>]+fonts\.googleapis", html))
        I.append(f"font imports: {fonts_import}")
        if not fonts_import and re.search(r"--font-(body|display)\s*:\s*['\"]?(?!system-ui|-apple|ui-|sans-serif|serif)[A-Z]", roots):
            W.append("fonts are named in :root but nothing loads them (no Google Fonts @import/<link>)")
        if re.search(r"never put colou?r", low) and hex_out:
            W.append(f"SKILL.md says never put colour literals outside :root, but example.html has {hex_out}: reword the rule or fix the file")
        if SCRATCH.search(body):
            E.append(f"SKILL.md contains a local/scratch path: {SCRATCH.search(body).group(0)!r}")
        for a in sorted(set(re.findall(r"""(?:src|href)=["'](assets/[^"']+)["']""", html))):
            if not (tdir / a).is_file():
                E.append(f"example.html references missing {a}")
        if mode == "prototype":
            from agents.capabilities.template_kit import _BODY_RE, _find_frame, _SCRIPT_RE

            bm = _BODY_RE.search(html)
            frame = _find_frame(_SCRIPT_RE.sub("", bm.group(1) if bm else html))
            if frame is None:
                E.append("template_kit finds no frame (needs <main> or a content class, and >=2 nav items before it with a nav-item class)")
            else:
                j = lambda v: v if isinstance(v, str) else " ".join(v)  # noqa: E731
                I.append(f"frame: content <{frame.content_tag} class='{j(frame.content_classes)}'>, nav items <{frame.item_tag} class='{j(frame.item_classes)}'>, active class {frame.active_class!r}")
            from agents.capabilities.template_kit import TEMPLATE_DIR, load_template_kit

            def _read(rel: str) -> str | None:
                f = tdir / rel[len(TEMPLATE_DIR) + 1:]
                return f.read_text(encoding="utf-8") if f.is_file() else None

            try:
                kit = load_template_kit(_read)
                if kit is None:
                    E.append("template_kit.load_template_kit returned None")
                else:
                    I.append(f"template_kit: {len(kit.css_blocks)} css blocks, {len(kit.classes)} classes, {len(kit.variables)} variables, font links {len(getattr(kit, 'font_links', []) or [])}")
            except Exception as exc:
                E.append(f"template_kit.load_template_kit crashed: {exc}")
            markup = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
            pats = re.findall(r"data-pattern=\"([^\"]+)\"", markup)
            if thin:
                if len(set(pats)) != 1:
                    E.append(f"thin template needs exactly 1 section.pattern, found {len(set(pats))}")
                else:
                    I.append(f"thin template, 1 pattern: {sorted(set(pats))}")
                if re.search(r"<script\b", html, re.I):
                    E.append("thin template must have no <script>; the sidebar items are plain")
                if re.search(r"""\sstyle\s*=\s*["']""", markup):
                    E.append("thin template must not use inline style= attributes; use classes")
                if len(re.findall(r'class="[^"]*\bnav-item\b', markup)) < 2:
                    E.append("thin template needs at least 2 .nav-item entries (the frame)")
            elif len(set(pats)) < 2:
                E.append(f"only {len(set(pats))} section.pattern[data-pattern]; one per screen is required")
            else:
                I.append(f"{len(set(pats))} patterns: {sorted(set(pats))}")
            for g in sorted(set(re.findall(r"data-go=\"([^\"]+)\"", markup))):
                if g not in pats:
                    W.append(f"nav data-go='{g}' has no matching pattern")
            if not re.search(r"<!--\s*PATTERN\s", html):
                W.append("patterns have no <!-- PATTERN id - purpose --> comments")
            todo = re.findall(r"<!--\s*PATTERN\s+([\w-]+)\s+-\s+TODO", html)
            if todo:
                E.append(f"{len(todo)} pattern purpose(s) not written yet (step 4.1: say what the user does there): {todo[:10]}")
            secs = dict(re.findall(r'<section[^>]*data-pattern="([^"]+)"[^>]*>(.*?)(?=<!--\s*PATTERN|<section[^>]*data-pattern=|</main>)', markup, re.S))
            texts = {k: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v)).strip() for k, v in secs.items()}
            import difflib

            keys = sorted(texts)
            for a_i, a in enumerate(keys):
                for b in keys[a_i + 1:]:
                    ta, tb = texts[a], texts[b]
                    if len(ta) > 200 and abs(len(ta) - len(tb)) < 0.05 * len(ta) and difflib.SequenceMatcher(None, ta[:3000], tb[:3000]).quick_ratio() > 0.97 and difflib.SequenceMatcher(None, ta[:3000], tb[:3000]).ratio() > 0.97:
                        W.append(f"patterns '{a}' and '{b}' are near-duplicates -- one probably did not capture its own state")
            sp = body.split("## Screen patterns", 1)
            if len(sp) == 2:
                table_ids = set(re.findall(r"^\|\s*`([^`]+)`", sp[1].split("\n## ", 1)[0], re.M))
                if table_ids:
                    absent = sorted(table_ids - set(pats))
                    undoc = sorted(set(pats) - table_ids)
                    if absent:
                        W.append(f"SKILL.md Screen patterns lists ids not in example.html: {absent}")
                    if undoc:
                        W.append(f"patterns in example.html missing from the SKILL.md Screen patterns table: {undoc}")
            # shortcut hints must match the preview runtime: Alt+N = the N-th nav item, N <= 9
            nav_items = re.findall(r'<(?:button|a)\b[^>]*data-go="([^"]+)"[^>]*>(.*?)</(?:button|a)>', markup, re.S)
            for pos, (g, inner) in enumerate(nav_items, 1):
                hint = re.search(r">\s*(?:Alt|⌥)\s*\+?\s*(\d+)\s*<", inner)
                if hint and int(hint.group(1)) != pos:
                    W.append(f"nav '{g}' shows shortcut Alt {hint.group(1)} but Alt+{pos} reaches it")
                if hint and pos > 9:
                    W.append(f"nav '{g}' shows a shortcut but only Alt+1..9 exist")
            # a trimmed list under a heading that still states the full count
            for k, v in secs.items():
                for tm in re.finditer(r"<!--\s*trimmed: (\d+) more", v):
                    pass
                if "<!-- trimmed:" in v or "<!--trimmed:" in v:
                    heads = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h[1-5][^>]*>(.*?)</h[1-5]>", v, re.S)]
                    nums = [h.strip() for h in heads if re.search(r"\d", h)]
                    if nums:
                        I.append(f"pattern '{k}' was trimmed; check these headings still tell the truth: {nums[:4]}")
            cut = [m.group(1) for m in re.finditer(r'<section[^>]*data-pattern="([^"]+)"', html) if m.start() > 120_000]
            if cut:
                W.append(f"{len(cut)} pattern(s) start after char 120,000, so builders never see them in the prompt: {cut}")
            if args.describe:
                for k, v in secs.items():
                    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", v, re.S)][:6]
                    btns = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b)).strip() for b in re.findall(r"<button[^>]*>(.*?)</button>", v, re.S)]
                    btns = [b for b in btns if b][:10]
                    I.append(f"describe {k}: headings={heads} buttons={btns} rows={len(re.findall(r'<tr', v))} items={len(re.findall(r'<li', v))} inputs={len(re.findall(r'<(?:input|select|textarea)', v))} chars={len(v)}")
        if mode == "deck":
            slides = len(re.findall(r"<section[^>]+class=\"[^\"]*\bslide\b", html))
            if not slides and "<deck-stage" in html:
                slides = len(re.findall(r"<section\b", html.split("<deck-stage", 1)[1]))
                W.append("legacy <deck-stage> deck; imports produce div.deck > section.slide")
            if slides < 3:
                E.append(f"{slides} section.slide found; a deck needs one <section class=\"slide\"> per slide")
            else:
                I.append(f"{slides} slides")
            if args.describe:
                for n, (tag, sv) in enumerate(re.findall(r'(<section[^>]*class="[^"]*\bslide\b[^"]*"[^>]*>)(.*?)</section>', html, re.S), 1):
                    lab = (re.search(r'data-label="([^"]*)"', tag) or [None, ""])[1]
                    heads = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip() for h in re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", sv, re.S)][:3]
                    I.append(f"describe slide {n} '{lab}': headings={heads} items={len(re.findall(r'<li', sv))} cells={len(re.findall(r'<t[dh]', sv))} chars={len(sv)}")
            if not re.search(r"ArrowRight|keydown", html):
                E.append("no keyboard navigation script (the composer copies it verbatim)")
            if re.search(r"""src=["']assets/""", html):
                W.append("deck example.html loads assets/... -- the deck gallery has no assets route, so the live preview 404s")

    for junk in ("snapshot-report.json", "shots", "node_modules", "captures.json", ".DS_Store"):
        if (tdir / junk).exists():
            E.append(f"build leftover in template folder: {junk}")

    od_loader._all_templates.cache_clear()
    listed = od_loader.list_prototype_templates() if mode == "prototype" else od_loader.list_ppt_templates()
    hit = next((t for t in listed if t["id"] == tid), None)
    if hit is None:
        E.append(f"od_loader does not list '{tid}' in the {mode} gallery")
    else:
        if not hit.get("has_preview"):
            E.append("od_loader reports has_preview=false")
        I.append(f"od_loader lists '{tid}' as {hit['name']!r} (mode={hit['mode']}, scenario={hit.get('scenario')})")
        files = od_loader.get_template_files(tid)
        I.append(f"files seeded to runs: {sorted(files)}")
    return report(E, W, I, args.json)


def describe_draft(d: Path, kind: str) -> int:
    """Per-pattern / per-slide summary of a draft example.html, before SKILL.md exists."""
    html = (d / "example.html").read_text(encoding="utf-8", errors="replace") if (d / "example.html").is_file() else (d.read_text(encoding="utf-8") if d.is_file() else "")
    if not html:
        print(f"no example.html in {d}")
        return 2
    markup = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    txt = lambda v: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v)).strip()  # noqa: E731
    if kind == "deck":
        blocks = [((re.search(r'data-label="([^"]*)"', t) or [None, "?"])[1], v) for t, v in re.findall(r'(<section[^>]*class="[^"]*\bslide\b[^"]*"[^>]*>)(.*?)</section>', markup, re.S)]
    else:
        blocks = re.findall(r'<section[^>]*data-pattern="([^"]+)"[^>]*>(.*?)(?=<!--\s*PATTERN|<section[^>]*data-pattern=|</main>)', markup, re.S)
    for k, v in blocks:
        heads = [txt(h) for h in re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", v, re.S)][:6]
        btns = [b for b in (txt(b) for b in re.findall(r"<button[^>]*>(.*?)</button>", v, re.S)) if b][:12]
        print(f"{k}: headings={heads} buttons={btns} rows={len(re.findall(r'<tr', v))} items={len(re.findall(r'<li', v))} "
              f"inputs={len(re.findall(r'<(?:input|select|textarea)', v))} trimmed_runs={v.count('trimmed:')} chars={len(v)}")
    print(f"{len(blocks)} {'slides' if kind == 'deck' else 'patterns'}, example.html {len(html):,} chars")
    # cheap checks a draft can already fail
    warns = []
    if len(html) > 120_000:
        cut = [m.group(1) for m in re.finditer(r'<section[^>]*data-pattern="([^"]+)"', html) if m.start() > 120_000]
        warns.append(f"{len(html):,} chars > 120,000; {len(cut)} pattern(s) past the prompt window: {cut}")
    ids = set(re.findall(r'data-pattern="([^"]+)"', markup))
    for u in sorted(set(re.findall(r'data-under="([^"]*)"', markup))):
        if u not in ids:
            warns.append(f"data-under=\"{u}\" is not a pattern id")
    m = LEFTOVERS.search(html)
    if m:
        warns.append(f"runtime leftover: {m.group(0)!r}")
    if kind != "deck" and not re.search(r":root\s*\{[^}]*--accent\s*:", html):
        warns.append(":root has no --accent")
    for w in warns:
        print(f"[W] {w}")
    print(f"RESULT: DRAFT ({len(warns)} warnings)")
    return 0


def report(E: list[str], W: list[str], I: list[str], as_json: bool) -> int:
    E, W, I = (list(dict.fromkeys(x)) for x in (E, W, I))
    if as_json:
        print(json.dumps({"ok": not E, "errors": E, "warnings": W, "info": I}, indent=2))
    else:
        for tag, rows in (("E", E), ("W", W), ("I", I)):
            for r in rows:
                print(f"[{tag}] {r}")
        print("RESULT:", "PASS" if not E else f"FAIL ({len(E)} errors)", f"- {len(W)} warnings")
    return 0 if not E else 1


if __name__ == "__main__":
    sys.exit(main())
