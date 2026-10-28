#!/usr/bin/env python3
"""Inventory a design-system SOURCE that is on disk and write source.json.

Usage:
    python3 read_source.py <input> --out <dir>

<input> is any of:
  * a Claude Design design-system export folder (readme.md, SKILL.md,
    tokens/*.css, styles.css, components/**, guidelines/*.html, ui_kits/**,
    _ds_manifest.json ...)
  * the `_ds/<id>/` folder inside a Claude Design prototype export
  * a prototype export folder that CONTAINS `_ds/<id>/` (the first one is used)
  * a .zip of any of these (extracted into <out>/src)
  * a single markdown / text spec (design-system.md, a DESIGN.md, brand notes)
  * a single .css file of tokens

source.json holds:
  kind, root, docs (markdown/text files to read in full, largest first),
  variables  {selector: {--name: value}}  every custom property per selector
             (":root" and theme selectors such as [data-theme="ops-dark"]),
  manifest_tokens  (from _ds_manifest.json: name, value, kind, definedIn),
  themes, fonts {families, google_imports}, breakpoints, colors (hex
  histogram), components (names), guideline_pages, warnings.
Read-only on the input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

VAR_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
VAR_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
GOOGLE_RE = re.compile(r"https://fonts\.googleapis\.com/[^\s\"')]+")
FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
FONT_SHORT_RE = re.compile(r"(?<![\w-])font\s*:\s*([^;]+)(?:;|$)", re.I)
MEDIA_RE = re.compile(r"@media[^{]*\((?:min|max)-width\s*:\s*(\d+)px\)", re.I)


def norm_hex(h: str) -> str:
    h = h.lower()
    return "#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    src = Path(a.input).expanduser().resolve()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    if not src.exists():
        print(json.dumps({"error": f"not found: {src}"}))
        return 2
    if src.is_file() and src.suffix.lower() == ".zip":
        dest = out / "src"
        dest.mkdir(exist_ok=True)
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    continue
                z.extract(n, dest)
        kids = [p for p in dest.iterdir() if not p.name.startswith(("__MACOSX", "."))]
        src = kids[0] if len(kids) == 1 and kids[0].is_dir() else dest

    root = src
    kind = "folder"
    if src.is_dir():
        ds = sorted(p for p in src.glob("_ds/*") if p.is_dir())
        if ds and not (src / "tokens").is_dir():
            root = ds[0]
            kind = "prototype-export-ds"
            if len(ds) > 1:
                warnings.append(f"{len(ds)} _ds folders; used {ds[0].name}")
        if (root / "_ds_manifest.json").is_file() or (root / "tokens").is_dir():
            kind = "claude-design-export" if kind == "folder" else kind
    else:
        kind = {".md": "markdown", ".txt": "markdown", ".css": "css"}.get(src.suffix.lower(), "file")

    files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file() and "node_modules" not in p.parts]
    css_files = [p for p in files if p.suffix == ".css"]
    docs = sorted(
        (p for p in files if p.suffix.lower() in (".md", ".txt") and p.stat().st_size > 200),
        key=lambda p: -p.stat().st_size,
    )

    variables: dict[str, dict[str, str]] = {}
    css_texts: list[tuple[str, str]] = []
    colors: Counter[str] = Counter()
    families: Counter[str] = Counter()
    google: set[str] = set()
    bps: Counter[int] = Counter()
    type_roles: list[dict] = []
    hex_context: dict[str, list[str]] = {}
    md_fonts: Counter[str] = Counter()
    suggested_name = ""
    for p in [p for p in files if p.suffix.lower() in (".md", ".txt")]:
        t = p.read_text(encoding="utf-8", errors="replace")
        if not suggested_name:
            h1 = re.search(r"^#\s+(.+)$", t, re.M)
            if h1:
                suggested_name = re.split(r"\s+[—–-]\s+|:", h1.group(1))[0].replace("Design System", "").strip(" #*")
        for block in re.findall(r"```(?:css|scss)?\s*\n(.*?)```", t, re.S):
            if "{" in block and "--" in block:
                css_texts.append((str(p) + " (fenced block)", block))
        for line in t.splitlines():
            for h in HEX_RE.findall(line):
                hex_context.setdefault(norm_hex(h), [])
                if len(hex_context[norm_hex(h)]) < 2:
                    hex_context[norm_hex(h)].append(re.sub(r"\s+", " ", line.strip())[:140])
        for f in re.findall(r"(?:`|\*\*)([A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+){0,2})(?:`|\*\*)", t):
            if re.search(r"Sans|Serif|Mono|Grotesk|Display|Text|Montserrat|Inter|Roboto|Lato|Poppins|Helvetica|Arial|Georgia|Playfair|Merriweather|Nunito|Raleway|Oswald|Source|Noto|IBM Plex|Work|Manrope|DM|Space|Outfit|Figtree|Rubik|Karla|Barlow", f):
                md_fonts[f] += 1
    for p in css_files:
        css_texts.append((str(p), p.read_text(encoding="utf-8", errors="replace")))
    for label, t in css_texts:
        clean = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        for bm in VAR_BLOCK_RE.finditer(clean):
            sel = " ".join(bm.group(1).split()).split("}")[-1].strip()
            decls = bm.group(2)
            for vm in VAR_RE.finditer(decls):
                variables.setdefault(sel, {})[vm.group(1)] = " ".join(vm.group(2).split())
            role = {}
            fm = FONT_SHORT_RE.search(decls)
            if fm:
                role.update({"font": " ".join(fm.group(1).split())})
            for k in ("font-size", "font-weight", "line-height", "letter-spacing", "text-transform", "font-family"):
                m = re.search(rf"(?<![\w-]){k}\s*:\s*([^;]+)(?:;|$)", decls)
                if m:
                    role[k] = " ".join(m.group(1).split())
            if role and not sel.startswith(":root") and len(sel) < 80:
                type_roles.append({"selector": sel, **role, "from": Path(label.split(" (")[0]).name})
    for p in [p for p in files if p.suffix in (".html", ".md")]:
        t = p.read_text(encoding="utf-8", errors="replace")
        google.update(GOOGLE_RE.findall(t))
        for m in MEDIA_RE.finditer(t):
            bps[int(m.group(1))] += 1
        if p.suffix == ".md":
            colors.update(norm_hex(h) for h in HEX_RE.findall(t))
    for label, t in css_texts:
        google.update(GOOGLE_RE.findall(t))
        clean = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        colors.update(norm_hex(h) for h in HEX_RE.findall(clean))
        for fm in FAMILY_RE.finditer(clean):
            first = fm.group(1).split(",")[0].strip().strip("'\"")
            if first and not first.startswith("var("):
                families[first] += 1
    for vs in variables.values():
        for k, v in vs.items():
            if "font" in k and not v.startswith("var("):
                first = v.split(",")[0].strip().strip("'\"")
                if first:
                    families[first] += 1

    manifest = {}
    mpath = root / "_ds_manifest.json" if root.is_dir() else None
    if mpath and mpath.is_file():
        try:
            manifest = json.loads(mpath.read_text())
        except json.JSONDecodeError:
            warnings.append("_ds_manifest.json is not valid JSON")
    theme_sels = [t if isinstance(t, str) else t.get("selector", str(t)) for t in manifest.get("themes", [])] or [
        s for s in variables if s != ":root" and "[" in s
    ]
    # colour themes vs density modes (density stays prose in DESIGN.md)
    themes = [{"selector": t, "kind": "density" if "density" in t else "color"} for t in theme_sels]
    theme_overrides = {t: variables.get(t, {}) for t in theme_sels if "density" not in t}
    components = [c.get("name") for c in manifest.get("components", []) if isinstance(c, dict)]
    if not components and root.is_dir():
        components = sorted({p.stem for p in root.glob("components/**/*.jsx")})
    guideline_pages = sorted(str(p) for p in root.glob("guidelines/*.html")) if root.is_dir() else []
    if kind == "markdown" and not variables:
        warnings.append("no CSS variables: all values come from the prose -- read the doc in full")
    for f, n in md_fonts.most_common(6):
        families[f] += n

    report = {
        "kind": kind,
        "input": str(Path(a.input).resolve()),
        "root": str(root),
        "docs": [{"path": str(p), "bytes": p.stat().st_size} for p in docs],
        "css_files": [str(p) for p in css_files],
        "variables": variables,
        "manifest_tokens": manifest.get("tokens", []),
        "brand_fonts": manifest.get("brandFonts", []),
        "themes": themes,
        "theme_overrides": theme_overrides,
        "fonts": {"families": [f for f, _ in families.most_common(12)], "google_imports": sorted(google)},
        "breakpoints": sorted(bps),
        "colors": [{"hex": h, "count": n} for h, n in colors.most_common(40)],
        "components": components,
        "type_roles": sorted(type_roles, key=lambda r: (0 if "typograph" in r["from"] else 1))[:100],
        "hex_context": {h: hex_context[h] for h in list(hex_context)[:60]},
        "suggested_name": suggested_name,
        "guideline_pages": guideline_pages,
        "warnings": warnings,
    }
    (out / "source.json").write_text(json.dumps(report, indent=2))
    summary = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in report.items()}
    summary["fonts"] = report["fonts"]
    summary["themes"] = [f"{t['selector']} ({t['kind']})" for t in themes]
    summary["docs"] = [d["path"] for d in report["docs"][:6]]
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
