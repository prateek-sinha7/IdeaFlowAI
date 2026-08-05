#!/usr/bin/env python3
"""Migrate the rest of .planning/ into cards, so nothing is invisible.

`extract.py` handles the three registers. This covers everything else:

    bugs   QA bug logs (SSE / RESUME / CUSTOM-WORKFLOW)   → one card per BUG/CWF id
    tests  TEST-REGISTER.md                               → one card per section
    reqs   REQUIREMENTS.md                                → one card per section
    docs   narrative .md files under .planning/           → one pointer card each
    tasks  .planning/quick/* and .planning/phases/*       → one pointer card each

Two different treatments, on purpose:

- **Entry extraction** where a file has structured, addressable entries. The card
  carries the entry.
- **Pointer cards** where the file is a narrative document. The card carries a
  summary and the path; **the content is never copied**. `.planning/phases/` alone
  is 13 MB — duplicating it would defeat the point.

Nothing is ever written to .planning/.

    python3 scripts/knowledge/migrate.py all [--force]
    python3 scripts/knowledge/migrate.py docs
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import knowledge_dir, repo_root  # type: ignore[import-not-found]  # noqa: E402
from extract import (  # type: ignore[import-not-found]  # noqa: E402
    SUMMARY_MAX,
    clean,
    derive_area,
    first_sentence,
    folded,
    normalize_areas,
    normalize_status,
    split_paths,
)

# Registers handled by extract.py, plus files that are state rather than knowledge.
SKIP_DOCS = {
    "FIX-REGISTER.md",
    "ISSUES-REGISTER.md",
    "IMPLEMENTATION-REGISTER.md",
    "TEST-REGISTER.md",
    "REQUIREMENTS.md",
    "SSE-QA-BUG-LOG.md",
    "RESUME-QA-BUG-LOG.md",
    "CUSTOM-WORKFLOW-QA-BUG-LOG.md",
    "STATE.md",
}

BUG_LOGS = {
    ".planning/SSE-QA-BUG-LOG.md": r"(?ms)^#{2,3} ((?:BUG|CWF)-[\w.]+)\s*[—-]\s*(.*?)$",
    ".planning/RESUME-QA-BUG-LOG.md": r"(?ms)^#{2,3} ((?:BUG|CWF)-[\w.]+)\s*[—-]\s*(.*?)$",
    ".planning/CUSTOM-WORKFLOW-QA-BUG-LOG.md": r"(?ms)^#{2,3} ((?:BUG|CWF)-[\w.]+)\s*[—-]\s*(.*?)$",
}

SEV_RE = re.compile(r"\[([^\]]*(?:critical|major|minor|blocker|🔴|🟠|🟡)[^\]]*)\]", re.I)
STATUS_RE = re.compile(r"\[([^\]]*(?:FIXED|OPEN|WONTFIX|DEFERRED|CLOSED)[^\]]*)\]", re.I)


def slug(text: str, n: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:n].rstrip("-") or "untitled"


def write(path: Path, content: str, force: bool, counters: dict) -> None:
    if path.exists() and not force:
        counters["skipped"] += 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    counters["written"] += 1


def head(fm: list[str], summary: str, source: str, extra: list[str] | None = None) -> str:
    fm += folded("summary", summary)
    fm.append(f"source: {source}")
    fm += extra or []
    fm.append("---")
    return "\n".join(fm)


# ------------------------------------------------------------------------------ bugs


def do_bugs(root: Path, kdir: Path, force: bool, counters: dict) -> None:
    for rel, pattern in BUG_LOGS.items():
        f = root / rel
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        heads = list(re.finditer(pattern, text))
        for i, m in enumerate(heads):
            bid, title = m.group(1), m.group(2)
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            body = text[m.start() : end].rstrip()
            # Template/schema stanzas are documentation of the format, not bugs.
            if "NNN" in bid or "xx" in bid.lower():
                continue
            sev = SEV_RE.search(title)
            st = STATUS_RE.search(title)
            title_clean = clean(re.sub(r"\[[^\]]*\]", "", title))
            status = "open"
            if st:
                low = st.group(1).lower()
                status = next(
                    (k for k in ("fixed", "wontfix", "deferred", "closed", "open") if k in low),
                    "open",
                )
                status = "done" if status in ("fixed", "closed") else status
            files = split_paths(" , ".join(re.findall(r"`([\w./@-]+/[\w./@-]+\.[a-z]{2,4})`", body)), root)
            areas = normalize_areas(derive_area(files, title_clean + " " + body[:1500]))
            # ids repeat across logs (BUG-001 exists in more than one campaign)
            camp = f.stem.replace("-QA-BUG-LOG", "").lower()
            cid = f"{bid}-{camp}" if len(BUG_LOGS) > 1 else bid

            fm = ["---", f"id: {cid}", "type: bug", f"status: {status}"]
            if areas:
                fm.append(f"area: [{', '.join(areas)}]")
            if files:
                fm += ["files:"] + [f"  - {p}" for p in files[:8]]
            extra = [f"campaign: {camp}"]
            if sev:
                extra.append(f'severity: "{clean(sev.group(1))}"')
            content = head(fm, first_sentence(title_clean, SUMMARY_MAX), f"{rel}#{bid.lower()}", extra)
            write(kdir / "cards" / f"{cid}.md", content + "\n\n" + body + "\n", force, counters)


# ------------------------------------------------------------- sectioned documents


def sectioned(root: Path, kdir: Path, rel: str, typ: str, prefix: str, outdir: str,
              force: bool, counters: dict) -> None:
    """One card per `###` section of a large structured document."""
    f = root / rel
    if not f.is_file():
        return
    text = f.read_text(encoding="utf-8", errors="replace")
    heads = list(re.finditer(r"(?m)^### +(.+?)\s*$", text))
    for i, m in enumerate(heads):
        title = clean(re.sub(r"\*\*|`", "", m.group(1)))
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.start() : end].rstrip()
        num = re.match(r"^([\d.]+)", title)
        cid = f"{prefix}-{(num.group(1).rstrip('.') if num else str(i + 1)).replace('.', '-')}"
        ids = list(dict.fromkeys(re.findall(r"\b((?:BE|UI|TS)-[A-Z0-9-]{2,})\b", body)))
        files = split_paths(" , ".join(re.findall(r"`([\w./@-]+/[\w./@-]+\.[a-z]{2,4})`", body)), root)
        fm = ["---", f"id: {cid}", f"type: {typ}", "status: done"]
        areas = normalize_areas(derive_area(files, title + " " + body[:1500]))
        if areas:
            fm.append(f"area: [{', '.join(areas)}]")
        if files:
            fm += ["files:"] + [f"  - {p}" for p in files[:8]]
        extra = []
        if ids:
            extra.append(f"covers: [{', '.join(ids[:20])}]")
            if len(ids) > 20:
                extra.append(f"covers_total: {len(ids)}")
        content = head(fm, first_sentence(title, SUMMARY_MAX), f"{rel}#{slug(title)}", extra)
        write(Path(kdir / "cards" / f"{cid}.md"), content + "\n\n" + body + "\n", force, counters)


# -------------------------------------------------------------------- pointer cards


def summarize_doc(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return clean(s[2:])
    for line in text.splitlines():
        s = clean(line)
        if s and not s.startswith(("#", "|", ">", "-", "*", "<!--")) and len(s) > 25:
            return s
    return fallback


def pointer(root: Path, kdir: Path, target: Path, cid: str, typ: str, outdir: str,
            force: bool, counters: dict, note: str) -> None:
    rel = target.relative_to(root).as_posix()
    if target.is_dir():
        members = sorted(p for p in target.rglob("*") if p.is_file())
        size = sum(p.stat().st_size for p in members)
        seed = ""
        for p in members:
            if p.suffix == ".md":
                seed = summarize_doc(p.read_text(encoding="utf-8", errors="replace")[:4000], "")
                if seed:
                    break
        summary = seed or target.name.replace("-", " ")
        detail = f"{len(members)} files, {size / 1024:.0f} KB"
    else:
        text = target.read_text(encoding="utf-8", errors="replace")
        summary = summarize_doc(text[:6000], target.stem.replace("-", " "))
        detail = f"{target.stat().st_size / 1024:.0f} KB"

    fm = ["---", f"id: {cid}", f"type: {typ}", "status: done"]
    areas = normalize_areas(derive_area([], summary))
    if areas:
        fm.append(f"area: [{', '.join(areas)}]")
    content = head(fm, first_sentence(clean(summary), SUMMARY_MAX), rel, [f"size: {detail}"])
    body = [
        f"# {cid}",
        "",
        f"Pointer card — content is **not** copied. It lives at:",
        "",
        f"    {rel}",
        "",
        f"({detail}) {note}",
    ]
    write(kdir / "cards" / f"{cid}.md", content + "\n\n" + "\n".join(body) + "\n", force, counters)


def do_docs(root: Path, kdir: Path, force: bool, counters: dict) -> None:
    seen: set[str] = set()
    for target in sorted((root / ".planning").glob("*.md")):
        if target.name in SKIP_DOCS:
            continue
        cid = f"DOC-{slug(target.stem)}"
        seen.add(cid)
        pointer(root, kdir, target, cid, "doc", "docs", force, counters,
                "Read it only when this topic is the task at hand.")
    for sub in ("live-verification", "v2.0-evidence", "ui-reviews", "debug"):
        d = root / ".planning" / sub
        if not d.is_dir():
            continue
        # Immediate children only: a nested fixture directory becomes one folder
        # pointer rather than a card per file. Every extension is included —
        # restricting to .md/.json left html and yaml fixtures invisible.
        for target in sorted(d.iterdir()):
            if target.name.startswith("."):
                continue
            cid = f"DOC-{slug(sub + '-' + target.stem)}"
            if cid in seen:
                continue
            seen.add(cid)
            pointer(root, kdir, target, cid, "doc", "docs", force, counters, "Evidence artifact.")


def do_tasks(root: Path, kdir: Path, force: bool, counters: dict) -> None:
    for sub, prefix in (("quick", "QUICK"), ("phases", "PH")):
        d = root / ".planning" / sub
        if not d.is_dir():
            continue
        for target in sorted(p for p in d.iterdir() if p.is_dir()):
            cid = f"{prefix}-{slug(target.name)}"
            pointer(root, kdir, target, cid, "task", "tasks", force, counters,
                    "Work folder: plan, summary and verification for one unit of work.")


# ----------------------------------------------------------------------------- main


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="migrate.py")
    ap.add_argument("kind", choices=("all", "bugs", "tests", "reqs", "docs", "tasks"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--root")
    args = ap.parse_args(argv[1:])

    root = Path(args.root).resolve() if args.root else repo_root()
    kdir = knowledge_dir(root)
    counters = {"written": 0, "skipped": 0}
    kinds = ("bugs", "tests", "reqs", "docs", "tasks") if args.kind == "all" else (args.kind,)

    for kind in kinds:
        before = dict(counters)
        if kind == "bugs":
            do_bugs(root, kdir, args.force, counters)
        elif kind == "tests":
            sectioned(root, kdir, ".planning/TEST-REGISTER.md", "test", "TEST", "tests",
                      args.force, counters)
        elif kind == "reqs":
            sectioned(root, kdir, ".planning/REQUIREMENTS.md", "req", "REQ", "requirements",
                      args.force, counters)
        elif kind == "docs":
            do_docs(root, kdir, args.force, counters)
        elif kind == "tasks":
            do_tasks(root, kdir, args.force, counters)
        print(f"  {kind:<6} +{counters['written'] - before['written']} written, "
              f"{counters['skipped'] - before['skipped']} skipped")

    print(f"total: {counters['written']} written, {counters['skipped']} skipped")
    print("next: python3 scripts/knowledge/build_index.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
