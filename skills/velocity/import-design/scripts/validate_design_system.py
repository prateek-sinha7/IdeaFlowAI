#!/usr/bin/env python3
"""Validate a design-system folder against the schema and what VelocityAI reads.

Run with the BACKEND venv so the real loader is used:

    backend/.venv/bin/python validate_design_system.py <od-root>/design-systems/<id> [--json]

Checks (E = error, W = warning, I = info):
  DESIGN.md   first line "# Design System Inspired by <Name>"; "> Category: X"
              then a "> blurb" line (both parsed by od_loader); the nine long-form
              sections in order; at least 4 distinct hex values (picker swatches);
              colour and font names stated; no YAML frontmatter
  tokens.css  every schema token declared in the first :root; no unknown names
              except BRAND_EXTENSIONS[<id>] / prefixes; no empty values; every
              var(--x) used resolves; A1 values are concrete (not var())
  components.html  :root identical to tokens.css (same names, same values);
              no hex/rgb literals outside :root blocks; a font <link> when the
              stacks name a web font; no external scripts
  loader      od_loader lists the id with the expected name/category and
              has_preview; get_design_system_files returns tokens.css +
              components.html; the category is an existing picker tab (or a new one)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ds_schema import load_schema, od_root_from, root_decls  # noqa: E402

SECTIONS = [
    "1. Visual Theme & Atmosphere",
    "2. Color Palette & Roles",
    "3. Typography Rules",
    "4. Component Stylings",
    "5. Layout Principles",
    "6. Depth & Elevation",
    "7. Do's and Don'ts",
    "8. Responsive Behavior",
    "9. Agent Prompt Guide",
]
SCRATCH = re.compile(r"/private/tmp/|/tmp/|scratchpad|/Users/[^/\s]+/|tests/[\w-]+/|source\.json|site\.json|mapping\.json")
THEME_MUST = ["--bg", "--surface", "--surface-warm", "--fg", "--fg-2", "--muted", "--meta", "--border", "--border-soft",
              "--accent", "--accent-on", "--accent-hover", "--accent-active", "--success", "--warn", "--danger"]
SYSTEM_FONTS = re.compile(r"^(system-ui|-apple-system|blinkmacsystemfont|segoe ui|helvetica|helvetica neue|arial|verdana|georgia|times|times new roman|ui-[a-z-]+|sans-serif|serif|monospace|menlo|monaco|consolas|courier new|sf mono|sf pro.*)$", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ds_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--source", help="W/source.json or W/site.json: warn on source colours missing from DESIGN.md")
    a = ap.parse_args()
    d = Path(a.ds_dir).resolve()
    od_root = od_root_from(d)
    repo = Path(__file__).resolve().parents[4]
    os.environ["OD_ROOT"] = str(od_root)
    sys.path.insert(0, str(repo / "backend"))
    E: list[str] = []
    W: list[str] = []
    I: list[str] = []
    did = d.name
    if d.parent.name != "design-systems":
        E.append(f"{d} is not inside design-systems/")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", did):
        E.append(f"folder id '{did}' is not kebab-case")
    if did.startswith("_"):
        E.append("folders starting with _ are skipped by the loader")

    md_p = d / "DESIGN.md"
    name = category = None
    md = sec2 = ""
    if not md_p.is_file():
        E.append("DESIGN.md missing -- the loader skips the folder")
    else:
        md = md_p.read_text(encoding="utf-8")
        if SCRATCH.search(md):
            E.append(f"DESIGN.md contains a local/scratch path: {SCRATCH.search(md).group(0)!r}")
        lines = md.splitlines()
        if md.startswith("---"):
            E.append("DESIGN.md starts with YAML frontmatter; the loader expects '# Name' first")
        h1 = next((l for l in lines if l.startswith("# ")), None)
        if not h1 or lines[0] != h1:
            E.append("first line must be the H1 '# Design System Inspired by <Name>'")
        elif not h1.startswith("# Design System Inspired by "):
            W.append("H1 does not use the 'Design System Inspired by <Name>' convention used by 150 of 151 systems (the picker shows the H1 as written)")
        name = h1[2:].strip() if h1 else None
        cat_i = next((i for i, l in enumerate(lines) if re.match(r"^>\s*Category:\s*\S", l)), None)
        if cat_i is None:
            E.append("no '> Category: X' line (the picker would file it under 'Uncategorised')")
        else:
            category = re.sub(r"^>\s*Category:\s*", "", lines[cat_i]).strip()
            if cat_i > 3:
                W.append("'> Category:' should be the line right after the H1 (blank line allowed)")
            if not (cat_i + 1 < len(lines) and lines[cat_i + 1].startswith(">") and len(lines[cat_i + 1]) > 10):
                E.append("the line after '> Category:' must be a '> one-line description'")
        heads = re.findall(r"^## (.+)$", md, re.M)
        missing = [s for s in SECTIONS if s not in heads]
        if missing:
            E.append(f"DESIGN.md missing sections: {missing}")
        elif [h for h in heads if h in SECTIONS] != SECTIONS:
            W.append("DESIGN.md sections are out of order")
        hexes = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", md)}
        if len(hexes) < 4:
            E.append(f"DESIGN.md has {len(hexes)} distinct hex colours; the picker swatches need several")
        sec2 = md.split("## 2.", 1)[1].split("\n## ", 1)[0] if "## 2." in md else ""
        if len(re.findall(r"#[0-9a-fA-F]{6}\b", sec2)) < 5:
            W.append("section 2 lists fewer than 5 hex values with roles")
        sec3 = md.split("## 3.", 1)[1].split("\n## ", 1)[0] if "## 3." in md else ""
        if not re.search(r"font|typeface|family", sec3, re.I):
            W.append("section 3 does not name the font families")
        if "token from style foundations" in md.lower():
            E.append("DESIGN.md contains boilerplate placeholders ('Token from style foundations')")
        I.append(f"DESIGN.md: name {name!r}, category {category!r}, {len(lines)} lines, {len(hexes)} distinct hex colours")

    schema = load_schema(od_root)
    names = [t["name"] for t in schema["tokens"]]
    allowed = set(schema["extensions"].get(did, []))
    tok_p = d / "tokens.css"
    comp_p = d / "components.html"
    tok = {}
    families: set[str] = set()
    if not tok_p.is_file():
        W.append("tokens.css missing (prototype_v2 uses it as the exact colour source)")
    else:
        css = tok_p.read_text(encoding="utf-8")
        tok = root_decls(css)
        miss = [n for n in names if n not in tok]
        if miss:
            E.append(f"tokens.css :root lacks {len(miss)} schema tokens: {miss}")
        unknown = [n for n in tok if n not in names and n not in allowed and not any(n.startswith(p) for p in schema["prefixes"])]
        if unknown:
            E.append(f"tokens.css declares names outside the schema and not in BRAND_EXTENSIONS['{did}']: {unknown}")
        empty = [n for n, v in tok.items() if not v.strip()]
        if empty:
            E.append(f"empty values: {empty}")
        code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        every = set(re.findall(r"(--[\w-]+)\s*:", code))
        dangling = sorted({r for r in re.findall(r"var\((--[\w-]+)", code)} - every)
        if dangling:
            E.append(f"var() references with no declaration: {dangling}")
        a1 = [t["name"] for t in schema["tokens"] if t["layer"] == "A1-identity"]
        aliased = [n for n in a1 if tok.get(n, "").startswith("var(")]
        if aliased:
            W.append(f"A1-identity tokens should be concrete values, not aliases: {aliased}")
        I.append(f"tokens.css :root {len(tok)} declarations ({len(tok) - len([n for n in tok if n in names])} extensions)")
        px = lambda v: float(m.group(1)) * (16 if m.group(2) == "rem" else 1) if (m := re.fullmatch(r"([\d.]+)(px|rem)", v.strip())) else None  # noqa: E731
        off = [f"{n}={tok[n]}" for n in tok if (mm := re.fullmatch(r"--space-(\d+)", n)) and px(tok[n]) is not None and px(tok[n]) != int(mm.group(1)) * 4]
        if off:
            W.append(f"--space-N means N*4px (schema tiers); these differ: {off} -- map the source scale by px value, not by position")
        scale = [(n, px(tok[n])) for n in ["--text-xs", "--text-sm", "--text-base", "--text-lg", "--text-xl", "--text-2xl", "--text-3xl", "--text-4xl"] if n in tok and px(tok[n]) is not None]
        if any(b[1] <= a[1] for a, b in zip(scale, scale[1:])):
            W.append(f"type scale is not strictly increasing: {scale}")
        radii = [(n, px(tok[n])) for n in ["--radius-sm", "--radius-md", "--radius-lg"] if n in tok and px(tok[n]) is not None]
        if any(b[1] < a[1] for a, b in zip(radii, radii[1:])):
            W.append(f"radius scale decreases: {radii}")
        comp = [n for n in ("--focus-ring", "--elev-ring", "--elev-raised") if re.search(r"#[0-9a-fA-F]{3,8}\b", tok.get(n, ""))]
        if comp:
            W.append(f"{comp} use literal hex -- compose them from var(--accent/--border/--fg) so themes re-resolve them")
        clean_css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        themes = {sel.strip(): dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)) for sel, body in re.findall(r"([^{}]*\[data-[^{}]+)\{([^}]*)\}", clean_css)}
        for sel, decls in themes.items():
            ext_tints = [n for n in tok if n not in names and re.search(r"-(bg|tint|soft|fill)$|^--(info|success|warn|danger)", n)]
            lacking = [n for n in THEME_MUST + ext_tints if n not in decls]
            if lacking and not re.search(r"density", sel):
                W.append(f"theme {sel} keeps light values for {lacking} -- override every surface/fg/border/semantic/accent-state token")
        if SCRATCH.search(css):
            E.append(f"tokens.css contains a local/scratch path: {SCRATCH.search(css).group(0)!r}")
        if md_p.is_file():
            md_hex = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", sec2)}
            tok_hex = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", css)}
            gaps_m = re.search(r"#{2,4}\s*Known gaps(.*?)(?=\n#{1,3} |\Z)", md, re.S | re.I)
            gaps_txt = gaps_m.group(1).lower() if gaps_m else ""
            untok = sorted(md_hex - tok_hex)
            unexplained = [h for h in untok if h not in gaps_txt]
            if unexplained:
                W.append(f"{len(unexplained)} section-2 colours are neither in tokens.css nor listed under 'Known gaps': {unexplained}")
            if untok and not unexplained:
                I.append(f"{len(untok)} section-2 colours are documented as Known gaps: {untok}")
    if not comp_p.is_file():
        W.append("components.html missing (the picker builds a fallback preview from DESIGN.md)")
    else:
        ch = comp_p.read_text(encoding="utf-8")
        c_root = root_decls(ch)
        if tok:
            diff = sorted(set(tok.items()) ^ set(c_root.items()))
            if diff:
                E.append(f"components.html :root differs from tokens.css ({len(diff)} declarations), e.g. {diff[:4]}")
        rest = re.sub(r"(?:^|[\s}]):root\s*\{[^}]*\}", "", re.sub(r"/\*.*?\*/", "", ch, flags=re.S))
        rest = re.sub(r"\[data-[^\]]+\]\s*\{[^}]*\}", "", rest)
        lits = re.findall(r"(?<![&\w])#[0-9a-fA-F]{3,8}\b(?![\w-])|rgba?\([^)]*\)", re.sub(r"<[^>]+href=\"[^\"]*\"", "", rest))
        declared_c = set(re.findall(r"(--[\w-]+)\s*:", ch))
        undeclared = sorted({v for v in re.findall(r"var\((--[\w-]+)", re.sub(r"/\*.*?\*/", "", ch, flags=re.S))} - declared_c)
        if undeclared:
            E.append(f"components.html uses var() names it never declares (they render as nothing): {undeclared}")
        if lits:
            W.append(f"{len(lits)} colour literal(s) outside :root in components.html, e.g. {lits[:4]}")
        if re.search(r"<script[^>]+src=[\"']https?://", ch):
            E.append("components.html loads a remote script")
        if tok:
            c_clean = re.sub(r"/\*.*?\*/", "", ch, flags=re.S)
            c_themes = {sel.strip(): dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)) for sel, body in re.findall(r"([^{}]*\[data-[^{}]+)\{([^}]*)\}", c_clean) if "--" in body}
            t_themes = {sel.strip(): dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)) for sel, body in re.findall(r"([^{}]*\[data-[^{}]+)\{([^}]*)\}", re.sub(r"/\*.*?\*/", "", tok_p.read_text(encoding="utf-8"), flags=re.S))}
            for sel in t_themes:
                if sel not in c_themes:
                    W.append(f"theme {sel} is in tokens.css but not pasted into components.html")
        if tok and families and "fonts.googleapis.com" not in ch and "@font-face" not in ch:
            W.append(f"fonts {sorted(families)} are named but components.html loads none")

    if a.source and md_p.is_file():
        try:
            src = json.loads(Path(a.source).read_text())
            src_hex = {c["hex"] for c in src.get("colors", []) if isinstance(c, dict) and c.get("count", 2) >= 2} if isinstance(src.get("colors"), list) else set()
            if not src_hex and isinstance(src.get("colors"), dict):
                src_hex = {x["v"] for k in ("background", "text") for x in src["colors"].get(k, [])[:6]}
            md_all = md.lower()
            # every --text-* must be a size the source uses, unless its tokens.css note says authored
            sizes = set()
            for r in src.get("type_roles", []) or []:
                for v in (r.get("font-size", ""), r.get("font", "")):
                    sizes.update(float(x) * (16 if u == "rem" else 1) for x, u in re.findall(r"([\d.]+)(px|rem)\b", v))
            for vs in (src.get("variables") or {}).values():
                for k, v in vs.items():
                    if re.search(r"fs|font-size|text|size", k):
                        sizes.update(float(x) * (16 if u == "rem" else 1) for x, u in re.findall(r"([\d.]+)(px|rem)\b", v))
            t2 = src.get("type") or {}
            for x in t2.get("sizes", []) if isinstance(t2, dict) else []:
                m2 = re.match(r"([\d.]+)px", str(x.get("v", "")))
                if m2:
                    sizes.add(float(m2.group(1)))
            if sizes and tok_p.is_file():
                for line in tok_p.read_text(encoding="utf-8").splitlines():
                    tm = re.match(r"\s*(--text-\w+)\s*:\s*([\d.]+)px", line)
                    if tm and float(tm.group(2)) not in sizes and "authored" not in line.lower():
                        W.append(f"{tm.group(1)} = {tm.group(2)}px is not a size the source uses -- use a source size, or mark the token note 'authored'")
            # dark blocks that re-declare shadows need elevation overrides in the theme block
            for sel, decls in (src.get("theme_overrides") or {}).items():
                if any(re.search(r"shadow|elev", k) for k in decls) and tok_p.is_file():
                    body = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", tok_p.read_text(encoding="utf-8"))
                    if body and "--elev-raised" not in body.group(1):
                        W.append(f"the source's {sel} re-declares shadows, but the theme block has no --elev-raised / --elev-ring override")
            lost = sorted(h for h in src_hex if h.lower() not in md_all)
            if lost:
                W.append(f"{len(lost)} colours used in the source are not mentioned in DESIGN.md (tokenise them or list them under Known gaps): {lost[:20]}")
        except (OSError, ValueError, KeyError) as exc:
            W.append(f"--source could not be read: {exc}")

    from app.services import od_loader  # noqa: E402

    od_loader._all_design_systems.cache_clear()
    hit = next((s for s in od_loader.list_design_systems() if s["id"] == did), None)
    if hit is None:
        E.append(f"od_loader does not list '{did}'")
    else:
        I.append(f"od_loader lists '{did}': name={hit.get('name')!r} category={hit.get('category')!r} has_preview={hit.get('has_preview')}")
        if comp_p.is_file() and not hit.get("has_preview"):
            E.append("has_preview is false although components.html exists")
        if category and hit.get("category") != category:
            E.append(f"loader category {hit.get('category')!r} != DESIGN.md category {category!r}")
        files = od_loader.get_design_system_files(did)
        I.append(f"files seeded to runs: {sorted(files)}")
        cats = {s.get("category") for s in od_loader.list_design_systems() if s["id"] != did}
        h1s = {}
        for other in (od_root / "design-systems").glob("*/DESIGN.md"):
            if other.parent.name != did:
                ot = other.read_text(encoding="utf-8", errors="replace")
                cm = re.search(r"^>\s*Category:\s*(.+?)\s*$", ot, re.M)
                if cm:
                    cats.add(cm.group(1))
                hm = re.search(r"^# (.+)$", ot, re.M)
                if hm:
                    h1s[hm.group(1).strip()] = other.parent.name
        if name and name in h1s:
            W.append(f"another system ({h1s[name]}) has the same H1 {name!r}: the picker would show two identical names")
        cats = sorted(c for c in cats if c)
        if category and category not in cats:
            W.append(f"no other system uses category {category!r}: it is a picker tab of its own. Existing: {cats}")
    if a.json:
        print(json.dumps({"ok": not E, "errors": E, "warnings": W, "info": I}, indent=2))
    else:
        for tag, rows in (("E", E), ("W", W), ("I", I)):
            for r in rows:
                print(f"[{tag}] {r}")
        print("RESULT:", "PASS" if not E else f"FAIL ({len(E)} errors)", f"- {len(W)} warnings")
    return 0 if not E else 1


if __name__ == "__main__":
    sys.exit(main())
