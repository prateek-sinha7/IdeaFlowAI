#!/usr/bin/env python3
"""Turn register entries into cards. Reads the registers; never writes to them.

Mechanical only — every field is derived from structure that is already in the
register. Nothing is invented. Where the register has no detail section for an
entry, the card body says so plainly rather than padding.

    python3 scripts/knowledge/extract.py fixes  [--only FIX-122,FIX-121] [--force]
    python3 scripts/knowledge/extract.py issues [--force]
    python3 scripts/knowledge/extract.py phases [--force]

Existing cards are never overwritten without --force, so hand-refined summaries
survive a re-run.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import knowledge_dir, read_json, repo_root  # type: ignore[import-not-found]  # noqa: E402

SUMMARY_MAX = 240

# Domain tags keyed off words that actually appear in these registers. Kept
# deliberately short: a wrong tag is worse than a missing one, because `--rules
# <area>` is trusted to be complete.
AREA_KEYWORDS = {
    "sse": ("sse", "stream_attached", "reconnect", "eventsource", "pipeline_cancelled"),
    "resume": ("resume", "resumption", "checkpoint"),
    "workflow": ("workflow", "manifest", "compiler", "wave", "fan-out", "fanout"),
    "agents": ("agent", "prompt", "revision-agent"),
    "evals": ("eval", "grading", "rubric", "judge"),
    "auth": ("auth", "login", "token", "session"),
    "artifacts": ("artifact", "deliverable", "download"),
    "runtime": ("execution engine", "executioncontext", "runtime", "scheduler"),
}

PATH_AREAS = {
    "frontend": "frontend",
    "backend": "backend",
    "infra": "infra",
    "scripts": "tooling",
    "docs": "docs",
}


def clean(cell: str) -> str:
    """Register cells carry markdown noise that would pollute the index line."""
    s = cell.strip()
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = s.replace("<br>", " ").replace("<br/>", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_TOP_DIRS: set[str] | None = None


def top_dirs(root: Path) -> set[str]:
    """Real top-level directories, used to reject partial paths.

    Registers often abbreviate (`types/index.ts`, `gates/validation`). Keeping
    those would fill the orphan report with noise and bury the paths that are
    genuinely deleted — which are the ones worth knowing about.
    """
    global _TOP_DIRS
    if _TOP_DIRS is None:
        _TOP_DIRS = {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".git")}
    return _TOP_DIRS


def split_paths(cell: str, root: Path | None = None) -> list[str]:
    allowed = top_dirs(root) if root else None
    out = []
    for part in re.split(r"[,\n]", cell):
        p = clean(part).strip("` ")
        if not p or " " in p or "/" not in p:
            continue
        p = p.lstrip("./")
        if not re.match(r"^[\w./@-]+$", p):
            continue
        if allowed is not None and p.split("/")[0] not in allowed:
            continue
        out.append(p)
    return list(dict.fromkeys(out))


# Register rows sometimes contain a literal `|` inside prose, which shifts every
# cell after it. That put whole paragraphs into `status` and `area`, and a facet is
# worthless if its values are free text. Both fields are now closed vocabularies:
# anything unrecognised is dropped rather than propagated.
STATUS_VOCAB = {
    "done", "open", "fixed", "closed", "deferred", "monitoring", "wontfix",
    "shipped", "resolved", "accepted", "proposed", "superseded", "deprecated",
    "partial", "blocked",
}
STATUS_ALIAS = {"fixed": "done", "closed": "done", "resolved": "done"}
AREA_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}$")


def normalize_status(raw: str, default: str = "done") -> tuple[str, str]:
    """Return (status, detail). Detail preserves the original when it was not clean."""
    s = clean(raw).lower().strip(" .*_")
    head = re.split(r"[\s(,/;]", s)[0] if s else ""
    if head in STATUS_VOCAB:
        canon = STATUS_ALIAS.get(head, head)
        return canon, (raw.strip() if len(s) > len(head) + 2 else "")
    return default, (raw.strip()[:200] if s else "")


def normalize_areas(areas: list[str]) -> list[str]:
    """Keep slug-shaped tags only — no paths, code fragments or sentences."""
    out = []
    for a in areas:
        tag = clean(a).lower().strip()
        if AREA_RE.match(tag) and tag not in out:
            out.append(tag)
    return out


def parse_invariants(cell: str) -> list[str]:
    r"""Expand the register's slash shorthand: `INV-1/3/12/SC-001` is four ids.

    A plain `INV-\d+` scan silently keeps only INV-1 and SC-001 here, which made
    the invariant cross-reference look like boilerplate when it is not.
    """
    out: list[str] = []
    for m in re.finditer(r"\b(INV|SC)-(\d+(?:/\d+)*)", cell):
        for num in m.group(2).split("/"):
            out.append(f"{m.group(1)}-{num}")
    return list(dict.fromkeys(out))


def derive_area(files: list[str], text: str) -> list[str]:
    areas: list[str] = []
    for f in files:
        top = f.split("/")[0]
        if top in PATH_AREAS and PATH_AREAS[top] not in areas:
            areas.append(PATH_AREAS[top])
    low = text.lower()
    for tag, words in AREA_KEYWORDS.items():
        if any(w in low for w in words) and tag not in areas:
            areas.append(tag)
    return areas


def first_sentence(text: str, limit: int) -> str:
    """Trim to `limit`, always on a clause or word boundary — never mid-word.

    Truncating inside a word or an open bracket produces summaries that read as
    corrupt, and the index line is the one thing a reader has to trust.
    """
    text = text.strip()
    if len(text) <= limit:
        return text.rstrip(" .;,—-")
    cut = text[:limit]
    for sep in (". ", "; ", " — ", " → ", ", "):
        i = cut.rfind(sep)
        if i > limit * 0.45:
            return cut[:i].rstrip(" .;,—-")
    trimmed = cut.rsplit(" ", 1)[0].rstrip(" .;,—-")
    # never leave an unbalanced opening bracket dangling
    if trimmed.count("(") > trimmed.count(")"):
        trimmed = trimmed[: trimmed.rfind("(")].rstrip(" .;,—-")
    return trimmed


TICKET_RE = re.compile(r"^\s*((?:KAN|DEF|CWF)-[\d.-]+)\b\s*(?:\([^)]*\))?\s*[:\-—]?\s*", re.I)
ENUM_NOISE = re.compile(
    r"^\s*(?:(?:two|three|four|five|several|multiple)\s+bugs?\s*[:\-—]?\s*)?"
    r"(?:\(\d\)|bug\s*\d[^:—-]*[:\-—]|[A-Z]\d\s*[:\-—])\s*",
    re.I,
)


def split_ticket(text: str) -> tuple[str, str]:
    """Pull a leading tracker id out of the description into its own field.

    `KAN-137: PPT revision chain fires but…` costs ~10 chars of every index line
    and reads as noise. As a field it stays searchable and stops competing with
    the symptom for space.
    """
    m = TICKET_RE.match(text)
    if not m:
        return "", text
    rest = text[m.end() :]
    # "KAN-137 follow-up: X" would otherwise leave the line opening on "follow-up:".
    # The link itself is preserved in `relates:`, so the connective adds nothing.
    rest = re.sub(r"^\s*(?:follow[-\s]?up|part\s*\d+|cont(?:inued)?)\s*[:\-—]?\s*", "", rest, flags=re.I)
    return m.group(1).upper(), rest


def make_summary(description: str, cause: str) -> str:
    """Symptom first; cause appended only when there is room for it.

    The register's Description column is usually already a symptom-plus-cause
    sentence. Blindly concatenating the Root Cause column on top produced 230-char
    summaries that truncated mid-clause, so the cause is now a fallback for thin
    descriptions rather than a default suffix.
    """
    desc = first_sentence(clean(description), SUMMARY_MAX)
    if len(desc) >= 120 or " — " in desc:
        return desc

    why = clean(cause)
    why = re.sub(r"^(root cause|cause)\s*[:\-—]\s*", "", why, flags=re.I)
    why = ENUM_NOISE.sub("", why)
    room = SUMMARY_MAX - len(desc) - 3
    if room < 40:
        return desc
    why = first_sentence(why, room)
    return f"{desc} — {why}" if why else desc


def yaml_block(key: str, values: list[str], indent: str = "  ") -> list[str]:
    if not values:
        return []
    return [f"{key}:"] + [f"{indent}- {v}" for v in values]


def folded(key: str, text: str) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 84:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return [f"{key}: >-"] + [f"  {ln}" for ln in lines]


# --------------------------------------------------------------------------- fixes


ROW_RE = re.compile(r"^\|\s*(FIX-\d+|ISS-\d+)\s*\|")


def parse_rows(text: str, prefix: str) -> dict[str, list[list[str]]]:
    rows: dict[str, list[list[str]]] = defaultdict(list)
    for line in text.splitlines():
        if not ROW_RE.match(line):
            continue
        cells = [c for c in line.split("|")][1:-1]
        cid = cells[0].strip()
        if cid.startswith(prefix):
            rows[cid].append(cells)
    return rows


def parse_details(text: str, prefix: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    pattern = re.compile(rf"(?ms)^### ({prefix}-\d+)\b.*?(?=^### |^## |\Z)")
    for m in pattern.finditer(text):
        out[m.group(1)].append(m.group(0).rstrip())
    return out


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower()[:120], b.lower()[:120]).ratio()


def partition_rows(cid: str, rows: list[list[str]], details: list[str]):
    """Split a reused id into one card per genuinely distinct fix.

    The register reuses 14 ids for two unrelated fixes each (e.g. FIX-007 is both
    a Windows ModuleNotFoundError crash and an audit-hooks feature). Merging them
    into one card produces a header describing one fix and a body describing
    another — worse than useless, because it reads as authoritative.

    Rows that are near-identical are true duplicates and stay merged. Rows that
    describe different work get their own card, suffixed b/c/... . The register
    itself is never renumbered; the suffix exists only in the card store.
    """
    groups: list[list[list[str]]] = []
    for row in rows:
        desc = clean(row[2]) if len(row) > 2 else ""
        for g in groups:
            if similar(clean(g[0][2]) if len(g[0]) > 2 else "", desc) >= 0.5:
                g.append(row)
                break
        else:
            groups.append([row])

    # Attach each detail section to the group whose description it matches.
    assigned: dict[int, list[str]] = defaultdict(list)
    for det in details:
        h = re.search(rf"^### {cid}\s*[—-]\s*(.+)$", det, re.M)
        head = clean(h.group(1)) if h else ""
        best, best_score = 0, -1.0
        for i, g in enumerate(groups):
            s = similar(clean(g[0][2]) if len(g[0]) > 2 else "", head)
            if s > best_score:
                best, best_score = i, s
        assigned[best].append(det)

    # The group that owns a detail section keeps the unsuffixed id.
    order = sorted(range(len(groups)), key=lambda i: (not assigned[i], -len(groups[i])))
    out = []
    for rank, gi in enumerate(order):
        suffix = "" if rank == 0 else chr(ord("a") + rank)
        out.append((f"{cid}{suffix}", groups[gi], assigned[gi], len(groups) > 1))
    return out


def build_fix_card(
    cid: str,
    rows: list[list[str]],
    details: list[str],
    register: str,
    root: Path,
    collision_of: str = "",
) -> str:
    # Prefer the richest row; keep the others verbatim in the body.
    row = max(rows, key=lambda r: sum(len(c) for c in r))
    date = clean(row[1]) if len(row) > 1 else ""
    desc = row[2] if len(row) > 2 else ""
    cause = row[3] if len(row) > 3 else ""
    files = split_paths(row[4], root) if len(row) > 4 else []
    phase = clean(row[5]) if len(row) > 5 else ""
    invariants = parse_invariants(row[6]) if len(row) > 6 else []
    status, status_detail = normalize_status(row[7] if len(row) > 7 else "", "done")

    relates = [r for r in re.findall(r"((?:FIX|ISS|BUG)-\d+)", phase) if r != cid]
    ticket, desc = split_ticket(clean(desc))
    summary = make_summary(desc, cause)
    areas = normalize_areas(derive_area(files, f"{desc} {cause} {phase}"))

    fm = ["---", f"id: {cid}", "type: fix"]
    if date:
        fm.append(f"date: {date}")
    fm.append(f"status: {status}")
    if areas:
        fm.append(f"area: [{', '.join(areas)}]")
    fm += yaml_block("files", files)
    fm += folded("summary", summary)
    fm.append(f"source: {register}#{collision_of.lower() or cid.lower()}")
    if collision_of:
        fm.append(f"collision_of: {collision_of}")
    if ticket:
        fm.append(f"ticket: {ticket}")
    if status_detail:
        fm.append(f'status_detail: "{status_detail[:180]}"')
    if invariants:
        fm.append(f"invariants: [{', '.join(dict.fromkeys(invariants))}]")
    if relates:
        fm.append(f"relates: [{', '.join(dict.fromkeys(relates))}]")
    if len(rows) > 1:
        fm.append(f"duplicate_rows: {len(rows)}")
    fm.append("---")

    body = [f"# {cid}", ""]
    if collision_of:
        body += [
            f"> **Reused id.** The register uses `{collision_of}` for more than one unrelated",
            f"> fix. This card is one of them; the suffix exists only here, so that one card",
            f"> means one fix. The register itself is unchanged — see `source:`.",
            "",
        ]
    if phase:
        body += [f"**Phase / trigger:** {phase}", ""]

    if details:
        body += ["<!-- verbatim from the register -->", ""]
        body.append("\n\n---\n\n".join(details))
    else:
        body += [
            "> No detail section exists in the register for this entry — only the",
            "> summary-table row below. Nothing has been invented to fill the gap.",
            "",
            "## Description",
            "",
            clean(desc) or "_(empty)_",
            "",
            "## Root cause",
            "",
            clean(cause) or "_(empty)_",
        ]
        if files:
            body += ["", "## Files changed", ""] + [f"- `{f}`" for f in files]

    if len(rows) > 1:
        body += [
            "",
            "---",
            "",
            f"## Duplicate register rows ({len(rows)})",
            "",
            f"`{cid}` appears {len(rows)} times in the register's summary table. All rows are",
            "preserved verbatim below; the richest one populated this card's header.",
            "",
        ]
        for i, r in enumerate(rows, 1):
            body += [f"{i}. " + " | ".join(clean(c) for c in r), ""]

    return "\n".join(fm) + "\n\n" + "\n".join(body).rstrip() + "\n"


def build_detail_only_card(cid: str, details: list[str], register: str, root: Path) -> str:
    """Some fixes have a write-up but no summary-table row.

    They are real fixes and would otherwise vanish entirely, so the header is
    derived from the detail section itself rather than the table.
    """
    text = "\n\n---\n\n".join(details)
    head = re.search(rf"^### {cid}\s*[—-]\s*(.+)$", text, re.M)
    summary = first_sentence(clean(head.group(1)), SUMMARY_MAX) if head else cid
    dm = re.search(r"\*\*Date:\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text)
    files = split_paths(" , ".join(re.findall(r"`([\w./@-]+\.[a-z]{2,4})`", text)), root)
    invariants = parse_invariants(text)
    relates = [r for r in dict.fromkeys(re.findall(r"((?:FIX|ISS|BUG)-\d+)", text)) if r != cid]

    fm = ["---", f"id: {cid}", "type: fix"]
    if dm:
        fm.append(f"date: {dm.group(1)}")
    fm.append("status: done")
    areas = derive_area(files, summary + " " + text[:2000])
    if areas:
        fm.append(f"area: [{', '.join(areas)}]")
    fm += yaml_block("files", files[:8])
    fm += folded("summary", summary)
    fm.append(f"source: {register}#{cid.lower()}")
    if invariants:
        fm.append(f"invariants: [{', '.join(invariants)}]")
    if relates:
        fm.append(f"relates: [{', '.join(relates[:6])}]")
    fm.append("no_table_row: true")
    fm.append("---")

    body = [
        f"# {cid}",
        "",
        "> This entry has **no row in the register's summary table** — only the detail",
        "> section below. Header fields were derived from that section.",
        "",
        text,
    ]
    return "\n".join(fm) + "\n\n" + "\n".join(body).rstrip() + "\n"


def apply_overrides(content: str, cid: str, overrides: dict) -> str:
    """Re-apply hand-authored frontmatter on top of a mechanically built card.

    Extraction is meant to be re-runnable. Without this, every `--force` would
    silently destroy hand-written summaries and the `produces:` links that
    connect a fix to the decision it established.
    """
    patch = overrides.get(cid)
    if not patch:
        return content
    lines = content.splitlines()
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")

    head, i = [], 1
    while i < end:
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", lines[i])
        key = m.group(1) if m else None
        block = [lines[i]]
        i += 1
        while i < end and (lines[i][:1] in (" ", "\t") or lines[i].lstrip().startswith("- ")):
            block.append(lines[i])
            i += 1
        if key not in patch:
            head.extend(block)

    for key, val in patch.items():
        if isinstance(val, list):
            head.append(f"{key}: [{', '.join(str(v) for v in val)}]")
        elif isinstance(val, str) and len(val) > 70:
            head.extend(folded(key, val))
        else:
            head.append(f"{key}: {val}")

    return "\n".join(["---", *head, "---", *lines[end + 1 :]]) + "\n"


def build_issue_card(cid: str, rows: list[list[str]], register: str, root: Path) -> str:
    # | ID | Sev | Tag | Status | Title | Source / Evidence |
    row = max(rows, key=lambda r: sum(len(c) for c in r))
    sev = clean(row[1]) if len(row) > 1 else ""
    tag = clean(row[2]) if len(row) > 2 else ""
    raw_status = clean(row[3]) if len(row) > 3 else ""
    title = row[4] if len(row) > 4 else ""
    evidence = row[5] if len(row) > 5 else ""

    status, status_detail = normalize_status(raw_status, "open")

    relates = [r for r in re.findall(r"((?:FIX|ISS|BUG)-\d+)", f"{title} {evidence}") if r != cid]
    summary = make_summary(title, evidence)
    # The issues register has no Files column, so every issue card was landing with
    # `files: []` and could never be reached by `ctx --for <path>`. Mine the paths
    # out of the prose instead.
    files = split_paths(
        " , ".join(re.findall(r"`?([\w./@-]+/[\w./@-]+\.[a-z]{2,4})`?", f"{title} {evidence}")),
        root,
    )
    areas = normalize_areas(derive_area(files, f"{title} {evidence} {tag}") + [tag])

    fm = ["---", f"id: {cid}", "type: issue", f"status: {status}"]
    if areas:
        fm.append(f"area: [{', '.join(areas)}]")
    fm += yaml_block("files", files)
    fm += folded("summary", summary)
    fm.append(f"source: {register}#{cid.lower()}")
    if sev:
        fm.append(f"severity: {sev}")
    if status_detail:
        fm.append(f'status_detail: "{status_detail[:180]}"')
    if relates:
        fm.append(f"relates: [{', '.join(dict.fromkeys(relates))}]")
    if len(rows) > 1:
        fm.append(f"duplicate_rows: {len(rows)}")
    fm.append("---")

    body = [f"# {cid}", "", "## Title", "", clean(title) or "_(empty)_", ""]
    body += ["## Source / evidence", "", clean(evidence) or "_(none recorded)_"]
    if len(rows) > 1:
        body += ["", f"## Duplicate register rows ({len(rows)})", ""]
        for i, r in enumerate(rows, 1):
            body += [f"{i}. " + " | ".join(clean(c) for c in r), ""]
    return "\n".join(fm) + "\n\n" + "\n".join(body).rstrip() + "\n"


def build_phase_card(shard: Path, register: str) -> tuple[str, str] | None:
    """Phases stay in their existing shard; the card is a pointer, not a copy."""
    m = re.match(r"^(\d+)-(.+)\.md$", shard.name)
    if not m:
        return None
    num, slug = m.group(1), m.group(2)
    cid = f"PHASE-{num}"
    text = shard.read_text(encoding="utf-8", errors="replace")
    heading = next(
        (ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("# ")),
        slug.replace("-", " "),
    )
    size_kb = len(text.encode()) / 1024
    summary = first_sentence(clean(heading), SUMMARY_MAX)
    fm = [
        "---",
        f"id: {cid}",
        "type: phase",
        "status: done",
    ]
    fm += folded("summary", summary)
    fm.append(f"source: {register}")
    fm.append(f"shard: .planning/_register-parts/{shard.name}")
    fm.append("---")
    body = [
        f"# {cid} — {heading}",
        "",
        f"Pointer card. The content lives in its existing shard ({size_kb:.0f} KB) and is",
        "deliberately **not** copied here:",
        "",
        f"    .planning/_register-parts/{shard.name}",
        "",
        "Read that file when this phase is the one you are working in. The shard carries",
        "the phase's goal, plan table, capabilities added, deleted-do-not-resurrect list,",
        "locked decisions, verification and gotchas.",
    ]
    return cid, "\n".join(fm) + "\n\n" + "\n".join(body) + "\n"


# ----------------------------------------------------------------------------- main


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="extract.py")
    ap.add_argument("kind", choices=("fixes", "issues", "phases"))
    ap.add_argument("--only", help="comma-separated ids to extract")
    ap.add_argument("--force", action="store_true", help="overwrite existing cards")
    ap.add_argument("--root")
    args = ap.parse_args(argv[1:])

    root = Path(args.root).resolve() if args.root else repo_root()
    kdir = knowledge_dir(root)
    cfg = read_json(kdir / "sources.json", {})
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    written, skipped = 0, 0

    if args.kind == "phases":
        register = ".planning/IMPLEMENTATION-REGISTER.md"
        outdir = kdir / "cards"
        outdir.mkdir(parents=True, exist_ok=True)
        shards = sorted((root / ".planning/_register-parts").glob("*.md"))
        for shard in shards:
            built = build_phase_card(shard, register)
            if not built:
                continue
            cid, content = built
            if only and cid not in only:
                continue
            path = outdir / f"{cid}.md"
            if path.exists() and not args.force:
                skipped += 1
                continue
            path.write_text(content, encoding="utf-8")
            written += 1
    else:
        prefix = "FIX" if args.kind == "fixes" else "ISS"
        register = (
            ".planning/FIX-REGISTER.md" if prefix == "FIX" else ".planning/ISSUES-REGISTER.md"
        )
        if register not in (cfg.get("registers") or {}):
            print(f"warning: {register} not listed in sources.json", file=sys.stderr)
        text = (root / register).read_text(encoding="utf-8")
        rows = parse_rows(text, prefix)
        details = parse_details(text, prefix)
        outdir = kdir / "cards"
        outdir.mkdir(parents=True, exist_ok=True)

        overrides = read_json(kdir / "overrides.json", {}) or {}
        collisions: set[str] = set()
        # detail-only entries are real fixes too — include them, never drop them
        all_ids = set(rows) | (set(details) if prefix == "FIX" else set())

        for cid in sorted(all_ids, key=lambda s: int(s.split("-")[1])):
            if only and cid not in only:
                continue
            path = outdir / f"{cid}.md"
            if path.exists() and not args.force:
                skipped += 1
                continue
            if prefix == "ISS":
                content = build_issue_card(cid, rows[cid], register, root)
            elif cid in rows:
                parts = partition_rows(cid, rows[cid], details.get(cid, []))
                for part_id, prows, pdets, is_collision in parts:
                    ppath = outdir / f"{part_id}.md"
                    if ppath.exists() and not args.force:
                        skipped += 1
                        continue
                    c = build_fix_card(
                        part_id, prows, pdets, register, root,
                        collision_of=cid if is_collision else "",
                    )
                    ppath.write_text(apply_overrides(c, part_id, overrides), encoding="utf-8")
                    written += 1
                    if is_collision:
                        collisions.add(cid)
                continue
            else:
                content = build_detail_only_card(cid, details[cid], register, root)
            path.write_text(apply_overrides(content, cid, overrides), encoding="utf-8")
            written += 1

        if collisions:
            print(f"note: {len(collisions)} reused ids split into separate cards "
                  f"({', '.join(sorted(collisions))}) — register left unchanged")

        orphans = sorted(set(details) - set(rows))
        if orphans:
            print(f"note: {len(orphans)} entries had a detail section but no table row "
                  f"({', '.join(orphans)}) — cards built from the detail section")

    print(f"{args.kind}: wrote {written}, skipped {skipped} (existing; use --force to replace)")
    print("next: python3 scripts/knowledge/build_index.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
