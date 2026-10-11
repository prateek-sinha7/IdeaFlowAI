#!/usr/bin/env python3
"""Regenerate EVIDENCE.md — an index of every screenshot under evidence/.

Ids are STABLE: once a path has an EV-id it keeps it forever. New files get the
next free id. Re-run this any time; it is idempotent.

    python3 tools/evidence_index.py
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
INDEX = ROOT / "EVIDENCE.md"
EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


# ponytail: ids persisted by re-parsing our own output; a sidecar json would be
# one more file to keep in sync. Move to a sidecar if EVIDENCE.md ever gets
# hand-edited in the id column.
def load_existing_ids():
    if not INDEX.exists():
        return {}, 0
    ids = {}
    top = 0
    for m in re.finditer(r"`(EV-(\d{4}))`.*?\(evidence/([^)]+)\)", INDEX.read_text()):
        ids["evidence/" + m.group(3)] = m.group(1)
        top = max(top, int(m.group(2)))
    return ids, top


def bug_id_for(rel: Path) -> str:
    """Bug id from the containing directory, else from the filename."""
    parts = [p for p in rel.parts[1:-1] if p != "_scratch"]
    if parts:
        cand = parts[0]
        if re.fullmatch(r"qa-[a-z]{2}-\d{3}", cand, re.I):
            return cand.upper()
    m = re.search(r"(qa-[a-z]{2}-\d{3})", rel.name, re.I)
    return m.group(1).upper() if m else "—"


def describe(name: str) -> str:
    """Human description from the filename, minus ordering/phase noise."""
    stem = Path(name).stem
    stem = re.sub(r"^\d{2,3}-", "", stem)
    stem = re.sub(r"^(validate|analyze|test|fix|verify)-", "", stem, flags=re.I)
    stem = re.sub(r"(qa-[a-z]{2}-\d{3})-?", "", stem, flags=re.I)
    return (
        stem.replace("-", " ").replace("_", " ").strip()
        or "(no description in filename)"
    )


def phase_of(name: str) -> str:
    m = re.search(r"\b(validate|analyze|test|fix|verify)\b", name, re.I)
    if m:
        return m.group(1).lower()
    if re.search(r"after[-_]fix|reverify|re-verify", name, re.I):
        return "verify"
    return "—"


def ledger_map():
    """{BUG-ID: (status, title)} from LEDGER.md, so a verdict sits beside its shots."""
    led = ROOT / "LEDGER.md"
    if not led.exists():
        return {}
    out = {}
    for line in led.read_text().splitlines():
        if not line.startswith("| [QA-"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 7:
            continue
        m = re.search(r"\[(QA-[A-Z]{2}-\d{3})\]", cells[1])
        if m:
            out[m.group(1)] = (cells[2], cells[5])
    return out


def git_date(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return "uncommitted"


def main():
    if not EVIDENCE.exists():
        print("no evidence/ directory; nothing to index")
        return
    ids, top = load_existing_ids()
    ledger = ledger_map()
    files = sorted(p for p in EVIDENCE.rglob("*") if p.suffix.lower() in EXTS)

    rows = []
    for p in files:
        rel = p.relative_to(ROOT)
        key = str(rel)
        if key not in ids:
            top += 1
            ids[key] = f"EV-{top:04d}"
        rows.append(
            (
                ids[key],
                bug_id_for(rel),
                phase_of(p.name),
                describe(p.name),
                rel,
                p.stat().st_size // 1024,
                git_date(rel),
            )
        )

    rows.sort(key=lambda r: (r[1], str(r[4])))

    out = [
        "# EVIDENCE",
        "",
        "Every screenshot the bug line has produced, with a stable id so it can be cited.",
        "",
        "**Regenerate with `python3 tools/evidence_index.py`.** It is idempotent and ids never",
        "change once assigned — cite an `EV-` id anywhere and it keeps pointing at the same shot.",
        "",
        "The **Open** column opens the file in VS Code. The **File** column is a plain relative",
        "link, so it also works on GitHub and in any markdown previewer.",
        "",
        "Naming convention for new shots (see `.claude/agents/2-validator.md`):",
        "",
        "```",
        "evidence/<bug-id-lowercase>/<NN>-<phase>-attempt<N>-<what-is-on-screen>.png",
        "```",
        "",
        "Zero-padded sequence FIRST so a bug's folder sorts into the true order of events.",
        "Describe what is on screen, not the conclusion. Never leave real evidence in",
        "`_scratch/` or in `/tmp/bughunt-lane*-out/`.",
        "",
        "---",
        "",
        f"{len(rows)} screenshots.",
        "",
        "| Id | Bug | Status | Phase | What it shows | File | Open | Added |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for ev, bug, phase, desc, rel, kb, date in rows:
        bug_cell = f"[{bug}](BUGS.md#{bug.lower()})" if bug != "—" else "—"
        status, title = ledger.get(bug, ("—", ""))
        if bug != "—" and title:
            bug_cell = f"[{bug}](BUGS.md#{bug.lower()})<br><sub>{title[:60]}</sub>"
        scratch = " ⚠️`_scratch`" if "_scratch" in str(rel) else ""
        unattributed = " ⚠️**unattributed**" if bug == "—" else ""
        out.append(
            f"| `{ev}` | {bug_cell} | {status} | {phase} | {desc}{scratch}{unattributed} | "
            f"[`{rel.name}`]({rel}) | [open](vscode://file/{ROOT}/{rel}) | {date} |"
        )

    unattr = sum(1 for r in rows if r[1] == "—")
    scratch_n = sum(1 for r in rows if "_scratch" in str(r[4]))
    out += [
        "",
        "## Warnings",
        "",
        f"- **{unattr} screenshots are unattributed** — they sit in legacy `evidence/<page-slug>/`",
        "  folders from the old naming rule, so no bug id can be derived and nobody can tell which",
        "  bug they back. Not guessed at deliberately: a wrong attribution is worse than a visible",
        "  gap. Ask before mapping them.",
        f"- **{scratch_n} sit under `_scratch/`** — they back a verdict but are easy to miss.",
        "",
    ]
    INDEX.write_text("\n".join(out))
    print(
        f"wrote {INDEX.relative_to(ROOT)}: {len(rows)} screenshots, ids up to EV-{top:04d}"
    )


if __name__ == "__main__":
    main()
