#!/usr/bin/env python3
"""Classify an HTML prototype export and pick the file to render.

Usage:
    python3 inspect_export.py <input> [--work <dir>]

<input> is any of:
  * a Claude Design project folder (``*.dc.html`` + ``support.js`` + ``_ds/``)
  * a Claude Design bundled page (``<script type="__bundler/manifest">``) -- the
    "standalone" / ``prototype.html`` export, which renders fully offline
  * a ``.zip`` of either (extracted into --work, default a temp dir)
  * a plain HTML file (Claude chat artifact, hand-written deck, any page)

Prints one JSON report to stdout:
  {
    "input", "source_kind", "entry", "candidates", "ds_dirs", "uploads",
    "kind": "deck" | "prototype" | "document",
    "signals": {...}, "external_urls": [...], "fonts": [...], "title",
    "needs_network": bool, "warnings": [...]
  }

The script only reads. It never writes outside --work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

BUNDLE_RE = re.compile(r'<script[^>]+type="__bundler/manifest"', re.I)
BUNDLE_TEMPLATE_RE = re.compile(
    r'<script[^>]+type="__bundler/template"[^>]*>(.*?)</script>', re.S | re.I
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
URL_RE = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']|@import\s+(?:url\()?["']?(https?://[^"')\s]+)""", re.I)
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
GOOGLE_FAMILY_RE = re.compile(r"family=([^&:\"')]+)", re.I)

DECK_SIGNALS = {
    "deck_stage": re.compile(r"<deck-stage|deck-stage\.js|component-from-global-scope=\"deck-stage\"", re.I),
    "slide_ids": re.compile(r"data-om-slide-id", re.I),
    "section_slide": re.compile(r"<section[^>]+class=\"[^\"]*\bslide\b", re.I),
    "fixed_canvas": re.compile(r"1920\s*(?:px)?\s*[x×*,]\s*1080|width:\s*1920px|aspect-ratio:\s*16\s*/\s*9", re.I),
    "slide_keys": re.compile(r"ArrowRight|PageDown|slidechange", re.I),
    "reveal": re.compile(r"reveal\.js|class=\"reveal\"", re.I),
}
APP_SIGNALS = {
    "nav": re.compile(r"<nav\b|role=\"navigation\"|<aside\b", re.I),
    "main": re.compile(r"<main\b|class=\"[^\"]*\b(?:main|content|app-main|workspace)\b", re.I),
    "screens": re.compile(r"\bSCREENS\b|data-screen|data-pattern|screen\s*:", re.I),
    "forms": re.compile(r"<input\b|<select\b|<textarea\b|TextField|Checkbox", re.I),
    "app_shell": re.compile(r"height:\s*100vh|data-density|BrandBar|sidebar", re.I),
    "state_logic": re.compile(r"extends DCLogic|useState|setState|addEventListener\(\s*['\"]click", re.I),
}
DOC_SIGNALS = {
    "print_page": re.compile(r"@page\b|@media\s+print", re.I),
    "long_prose": re.compile(r"(?:<p\b[^>]*>[^<]{200,}){5,}", re.I | re.S),
    "no_script": re.compile(r"^(?!.*<script).*$", re.S | re.I),
}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def bundle_template(text: str) -> str | None:
    """Decoded page inside a Claude Design bundled export (JSON string)."""
    m = BUNDLE_TEMPLATE_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return m.group(1)


def classify(text: str) -> tuple[str, dict]:
    sig = {
        "deck": {k: len(r.findall(text)) for k, r in DECK_SIGNALS.items()},
        "app": {k: len(r.findall(text)) for k, r in APP_SIGNALS.items()},
        "document": {k: len(r.findall(text)) for k, r in DOC_SIGNALS.items() if k != "no_script"},
    }
    sig["document"]["has_script"] = int("<script" in text.lower())
    d = sig["deck"]
    deck_score = 3 * (d["deck_stage"] > 0) + 3 * (d["slide_ids"] > 0) + 2 * (d["section_slide"] >= 3) + (d["fixed_canvas"] > 0) + (d["slide_keys"] > 0) + 3 * (d["reveal"] > 0)
    a = sig["app"]
    app_score = sum(1 for v in a.values() if v) + (a["nav"] > 0 and a["main"] > 0)
    doc = sig["document"]
    doc_score = 2 * (doc["print_page"] > 0) + (doc["long_prose"] > 0) + (not doc["has_script"]) + (a["nav"] == 0) + (a["forms"] == 0)
    sig["scores"] = {"deck": deck_score, "prototype": app_score, "document": doc_score}
    if deck_score >= 3:
        return "deck", sig
    if doc_score >= 4 and app_score <= 3:
        return "document", sig
    return "prototype", sig


def fonts_in(text: str) -> list[str]:
    fams: set[str] = set()
    for m in FONT_FAMILY_RE.finditer(text):
        first = m.group(1).split(",")[0].strip().strip("'\"")
        if first and not first.startswith("var(") and len(first) < 60:
            fams.add(first)
    for m in GOOGLE_FAMILY_RE.finditer(text):
        fams.add(m.group(1).replace("+", " ").split(":")[0])
    return sorted(fams)


def external_urls(text: str) -> list[str]:
    out = set()
    for m in URL_RE.finditer(text):
        u = m.group(1) or m.group(2)
        if u and "w3.org" not in u:
            out.add(u)
    return sorted(out)


SCREENS_RE = re.compile(r"\b(?:const|let|var)\s+SCREENS\s*=\s*(\[[\s\S]*?\]);", re.M)
ROLES_RE = re.compile(r"\b(?:const|let|var)\s+ROLES\s*=\s*([\[{][\s\S]*?[\]}]);", re.M)
STATE_RE = re.compile(r"\bstate\s*=\s*\{([\s\S]{0,1500}?)\};", re.M)


def _balanced(text: str, start: int) -> str:
    """The bracketed literal ([...] or {...}) starting at text[start]."""
    open_c = text[start]
    close_c = {"[": "]", "{": "}"}[open_c]
    depth, i, q = 0, start, None
    while i < len(text):
        c = text[i]
        if q:
            if c == "\\":
                i += 1
            elif c == q:
                q = None
        elif c in "'\"`":
            q = c
        elif c in "[{":
            depth += c == open_c or c in "[{"
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return text[start:]


def _top_keys(obj_lit: str) -> list[str]:
    """Keys at depth 1 of an object literal."""
    keys, depth, i, q = [], 0, 0, None
    while i < len(obj_lit):
        c = obj_lit[i]
        if q:
            if c == "\\":
                i += 1
            elif c == q:
                q = None
        elif c in "'\"`":
            if depth == 1:
                m = re.match(r"(['\"])([\w-]+)\1\s*:", obj_lit[i:])
                if m:
                    keys.append(m.group(2))
                    i += m.end()
                    continue
            q = c
        elif c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
        elif depth == 1:
            m = re.match(r"([A-Za-z_$][\w$]*)\s*:", obj_lit[i:])
            if m and (i == 0 or not re.match(r"[\w$]", obj_lit[i - 1])):
                keys.append(m.group(1))
                i += m.end()
                continue
        i += 1
    return list(dict.fromkeys(keys))


def logic_summary(text: str) -> dict:
    """What the Claude Design logic script declares: screens, roles, state keys, sc-if branches."""
    out: dict = {"screens_declared": None, "screens": [], "roles": [], "state_keys": [], "branches": []}
    m = re.search(r"\b(?:const|let|var)\s+SCREENS\s*=\s*\[", text)
    if m:
        lit = _balanced(text, m.end() - 1)
        nested = re.search(r"\[\s*\[|\[\s*\{", lit)
        ids = re.findall(r"[\[{]\s*(?:id\s*:\s*)?['\"]([\w-]+)['\"]", lit[1:]) if nested else re.findall(r"['\"]([\w-]+)['\"]", lit)
        out["screens"] = list(dict.fromkeys(ids))
        out["screens_declared"] = len(out["screens"])
    r = re.search(r"\b(?:const|let|var)\s+ROLES\s*=\s*([\[{])", text)
    if r:
        lit = _balanced(text, r.end() - 1)
        if lit.startswith("{"):
            out["roles"] = _top_keys(lit)
        else:
            out["roles"] = list(dict.fromkeys(re.findall(r"\{\s*(?:id|key|role)\s*:\s*['\"]([\w-]+)['\"]", lit)))
        out["roles_snippet"] = lit[:4000]
    st = re.search(r"\bstate\s*=\s*\{", text)
    if st:
        out["state_keys"] = _top_keys(_balanced(text, st.end() - 1))[:80]
    # every conditional branch in the template: each is a screen, a state or a variant
    out["branches"] = list(dict.fromkeys(re.findall(r"<sc-if\s+value=\"\{\{\s*([^}]+?)\s*\}\}\"", text)))[:120]
    out["branches_count"] = len(out["branches"])
    return out


def ds_dirs_of(base: Path) -> list[str]:
    return sorted(str(p) for p in base.glob("_ds/*") if p.is_dir())


def brand_hints(title: str, text: str, ds_dirs: list[str]) -> dict:
    words = re.findall(r"\b[A-Z][A-Za-z]{2,}\b", title)
    ds = [Path(d).name.split("-")[0] for d in ds_dirs]
    caps = re.findall(r">\s*([A-Z]{4,})\s*<", text)
    return {"title_words": words, "design_system": ds, "wordmarks": sorted(set(caps))[:5]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--work", help="extraction dir, used only for .zip input")
    ap.add_argument("--od", help="opendesign root, to look for templates that already contain this export")
    args = ap.parse_args()
    src = Path(args.input).expanduser().resolve()
    warnings: list[str] = []
    if not src.exists():
        print(json.dumps({"error": f"not found: {src}"}))
        return 2

    root = src
    if src.is_file() and src.suffix.lower() == ".zip":
        work = Path(args.work or tempfile.mkdtemp(prefix="import-template-")).resolve()
        work.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    warnings.append(f"skipped unsafe zip member {n}")
                    continue
                z.extract(n, work)
        root = work
        kids = [p for p in work.iterdir() if not p.name.startswith(("__MACOSX", "."))]
        if len(kids) == 1 and kids[0].is_dir():
            root = kids[0]

    candidates: list[dict] = []
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob("*.htm*") if "_ds" not in p.parts and "node_modules" not in p.parts and "velocity-build" not in p.parts
    )
    seen_hashes: set[str] = set()
    for p in files:
        digest = hashlib.sha1(p.read_bytes()).hexdigest()
        if digest in seen_hashes:
            warnings.append(f"skipped {p.name}: byte-identical to another candidate")
            continue
        seen_hashes.add(digest)
        t = read(p)
        kind = "bundle" if BUNDLE_RE.search(t) else ("dc" if p.name.endswith(".dc.html") or "<x-dc" in t else "html")
        candidates.append({"path": str(p), "format": kind, "bytes": p.stat().st_size, "mtime": p.stat().st_mtime})

    if not candidates:
        print(json.dumps({"error": "no .html file in input", "input": str(src)}))
        return 2

    # Prefer the offline bundle, then the newest .dc.html (v2 over v1), then html.
    order = {"bundle": 0, "dc": 1, "html": 2}
    candidates.sort(key=lambda c: (order[c["format"]], -c["mtime"]))
    entry = candidates[0]
    if len(candidates) > 1:
        names = ", ".join(f"{Path(c['path']).name} ({c['format']}, {c['bytes'] // 1024} KB)" for c in candidates)
        warnings.append(
            f"{len(candidates)} candidate files: {names}. Picked {Path(entry['path']).name}. "
            "ASK the user which version is final (screen counts per file are in 'versions')"
        )
    versions = []
    for c in candidates:
        t = read(Path(c["path"]))
        body = (bundle_template(t) or t) if c["format"] == "bundle" else t
        versions.append({"file": Path(c["path"]).name, "format": c["format"], **logic_summary(body)})

    text = read(Path(entry["path"]))
    analysed = text
    if entry["format"] == "bundle":
        inner = bundle_template(text)
        if inner:
            analysed = inner
        else:
            warnings.append("bundle template could not be decoded; signals are from the wrapper only")
    # For a .dc.html the logic script holds SCREENS etc. -- analyse it too.
    kind, signals = classify(analysed)
    title_m = TITLE_RE.search(analysed)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    if title in ("Bundled Page", ""):
        title = Path(entry["path"]).stem.replace(".dc", "").replace("(standalone)", "").strip()
        if title.lower() in ("prototype", "index", "example", "standalone", "") and root.is_dir():
            title = root.name

    base = root if root.is_dir() else root.parent
    logic = logic_summary(analysed)
    if logic.get("screens_declared") is None and entry["format"] == "bundle":
        # the bundle's logic is the same as the newest .dc.html next to it
        for v in versions:
            if v.get("screens_declared"):
                logic = {k: v[k] for k in v if k not in ("file", "format")}
                break
    siblings = []
    if Path(entry["path"]).is_file():
        for m in re.finditer(r"""(?:src|href)=["'](?!https?:|data:|#|mailto:)([^"']+\.(?:js|css|png|jpe?g|svg|webp|woff2?))["']""", analysed):
            siblings.append({"ref": m.group(1), "exists": (Path(entry["path"]).parent / m.group(1)).is_file()})
    if siblings:
        warnings.append(f"entry references {len(siblings)} local file(s): {[s['ref'] for s in siblings][:6]} -- capture inlines what renders; decks must not keep assets/")
    deck_stage = bool(re.search(r"<deck-stage|deck-stage\.js", analysed))
    brand = brand_hints(title, analysed, ds_dirs_of(base))
    similar = []
    if args.od:
        tdir = Path(args.od) / "design-templates"
        needle = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        # fingerprint = distinctive sample-data codes (booking refs, flight numbers, ids): they survive a rebuild
        codes = lambda t: set(re.findall(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{5,8}\b", t))  # noqa: E731
        src_codes = codes(analysed)
        for ex in sorted(tdir.glob("*/example.html")):
            full = ex.read_text(encoding="utf-8", errors="replace")
            tm = TITLE_RE.search(full[:4000])
            t2 = re.sub(r"[^a-z0-9]+", " ", (tm.group(1) if tm else "").lower()).strip()
            ex_codes = codes(full)
            overlap = len(src_codes & ex_codes) / max(1, min(len(src_codes), len(ex_codes))) if len(src_codes) >= 5 and len(ex_codes) >= 5 else 0
            if (needle and t2 and (needle in t2 or t2 in needle)) or overlap > 0.4:
                similar.append({"id": ex.parent.name, "title": t2, "shared_data_codes": round(overlap, 2)})
        if similar:
            warnings.append(f"possible duplicates (same title or same sample data): {[x['id'] for x in similar]} -- ask whether this is a duplicate")
    ds_dirs = ds_dirs_of(base)
    uploads = sorted(str(p) for p in base.glob("uploads/*")) if (base / "uploads").is_dir() else []
    urls = external_urls(analysed)
    needs_network = entry["format"] == "dc" or any("unpkg.com" in u or "cdn" in u for u in urls)
    if entry["format"] == "dc":
        warnings.append(".dc.html needs network (React from unpkg, fonts from Google); prefer a standalone bundle if the user has one")

    print(json.dumps({
        "input": str(src),
        "root": str(root),
        "source_kind": {"bundle": "claude-design-bundle", "dc": "claude-design-project", "html": "html"}[entry["format"]],
        "entry": entry["path"],
        "candidates": candidates,
        "kind": kind,
        "signals": signals,
        "title": title,
        "fonts": fonts_in(analysed),
        "external_urls": urls,
        "needs_network": needs_network,
        "ds_dirs": ds_dirs,
        "logic": logic,
        "versions": versions,
        "siblings": siblings,
        "deck_stage": deck_stage,
        "brand_hints": brand,
        "similar_templates": similar,
        "uploads": uploads,
        "warnings": warnings,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
