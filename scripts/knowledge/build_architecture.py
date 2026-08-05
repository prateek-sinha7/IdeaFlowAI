#!/usr/bin/env python3
"""Generate .knowledge/surface/ARCHITECTURE.md — where the project is, and what holds it.

    python3 scripts/knowledge/build_architecture.py

Called automatically from build_index.py.

This is the one surface file about the *present*: which milestone is open, which
phase is current, which boundaries are enforced, and which decisions are in force.
Everything else in the store is history.

Every section is derived from a checkable source, and the file says which:

    stage        .planning/STATE.md frontmatter + Current Position  (~1 KB of 180 KB)
    boundaries   backend/pyproject.toml [tool.importlinter] contracts
    components   real directories on disk, counted against card `area:` tags
    decisions    the decision cards
    invariants   .knowledge/INVARIANTS.md

Nothing here is hand-written prose about how the system works. An architecture doc
that is not generated is a doc that is wrong six weeks later, and the whole point of
this store is that a stale map is worse than no map. Where a source cannot answer,
the file says so rather than guessing — the gaps are the most useful part.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import load_all, repo_root, surface_dir  # type: ignore[import-not-found]  # noqa: E402

# Directories that are real architectural components, in dependency order: the web
# layer calls the kernel, the kernel calls capabilities, nothing calls back up.
COMPONENTS = [
    ("backend/app/api", "HTTP + SSE surface — the only caller of the kernel"),
    ("backend/app/services", "application services"),
    ("backend/app/models", "persistence — additive migrations only"),
    ("backend/agents/execution_engine", "the execution kernel"),
    ("backend/agents/workflows", "workflow manifests — data, not code paths"),
    ("backend/agents/capabilities", "capability adapters"),
    ("backend/agents/runtime", "runtime services"),
    ("backend/agents/artifact_store", "artifact persistence"),
    ("backend/agents/guardrails", "policy enforcement"),
    ("frontend/src/app", "Next.js routes"),
    ("frontend/src/components", "UI components"),
    ("frontend/src/hooks", "client state + stream handling"),
]


# ------------------------------------------------------------------ current stage


def _state_frontmatter(text: str) -> tuple[dict, str]:
    """Parse STATE.md's frontmatter, which nests one level under `progress:`.

    Deliberately not `cards.parse_frontmatter`. That parser rejects nesting on
    purpose — the card schema is flat, and accepting a nested block there would let
    a malformed card through. STATE.md is not a card and has its own shape, so it
    gets its own eight-line reader rather than a loosened shared one.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head, body = text[3:end], text[end + 4:]

    fm: dict = {}
    parent: str | None = None
    for raw in head.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw[:1] in (" ", "\t")
        m = re.match(r"\s*([\w.-]+)\s*:\s*(.*)$", raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if indented and parent:
            target = fm.setdefault(parent, {})
            if isinstance(target, dict):
                target[key] = int(val) if val.lstrip("-").isdigit() else val
            continue
        parent = key if val == "" else None
        fm[key] = {} if val == "" else val
    return fm, body


def read_stage(root: Path) -> tuple[dict, list[str]]:
    """Milestone + position from STATE.md, without loading its 180 KB of metrics.

    STATE.md is excluded from the card store on purpose — it changes every session,
    so carrying it as a card would mean a card that is always stale. Reading its
    frontmatter at build time is the right treatment: current by construction.
    """
    p = root / ".planning" / "STATE.md"
    if not p.is_file():
        return {}, ["`.planning/STATE.md` not found — no stage information."]

    text = p.read_text(encoding="utf-8", errors="replace")
    try:
        fm, body = _state_frontmatter(text)
    except Exception as e:  # a malformed STATE.md must not break the build
        return {}, [f"`.planning/STATE.md` frontmatter did not parse — {e}"]
    if not fm:
        return {}, ["`.planning/STATE.md` has no frontmatter — no stage information."]

    # "## Current Position" is the only body section worth carrying; the rest is a
    # per-phase metrics table that grows without bound.
    position: list[str] = []
    m = re.search(r"(?m)^## Current Position\s*$", body)
    if m:
        tail = body[m.end():]
        nxt = re.search(r"(?m)^## ", tail)
        block = tail[: nxt.start()] if nxt else tail
        position = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]

    return {"fm": fm, "position": position}, []


def stage_lines(stage: dict) -> list[str]:
    fm = stage.get("fm") or {}
    if not fm:
        return ["_No stage information available._"]

    prog = fm.get("progress") or {}
    out = [
        "| | |",
        "|---|---|",
        f"| **Milestone** | `{fm.get('milestone', '?')}` {fm.get('milestone_name', '')} |",
        f"| **Status** | `{fm.get('status', '?')}` |",
    ]
    if isinstance(prog, dict) and prog:
        out.append(
            f"| **Phases** | {prog.get('completed_phases', '?')}/{prog.get('total_phases', '?')} "
            f"complete · {prog.get('completed_plans', '?')}/{prog.get('total_plans', '?')} plans "
            f"· {prog.get('percent', '?')}% |"
        )
    out.append(f"| **Last updated** | {str(fm.get('last_updated', '?'))[:10]} |")

    pos = stage.get("position") or []
    if pos:
        out += ["", "**Current position**", ""]
        out += [f"- {ln.lstrip('- ')}" for ln in pos]
    return out


# ------------------------------------------------------------- enforced boundaries


def read_contracts(root: Path) -> tuple[list[dict], list[str]]:
    """The import-linter contracts — the only architecture claims CI can falsify.

    Parsed by hand rather than with tomllib so that commented-out scaffold contracts
    stay excluded: a contract that is commented out is not enforcing anything, and
    listing it would overstate what is actually guaranteed.
    """
    p = root / "backend" / "pyproject.toml"
    if not p.is_file():
        return [], ["`backend/pyproject.toml` not found — boundaries unknown."]

    lines = p.read_text(encoding="utf-8").splitlines()
    contracts: list[dict] = []
    cur: dict | None = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            continue
        if line == "[[tool.importlinter.contracts]]":
            cur = {}
            contracts.append(cur)
            continue
        if cur is None or not line or line.startswith("["):
            if line.startswith("[") and line != "[[tool.importlinter.contracts]]":
                cur = None
            continue
        m = re.match(r'(\w+)\s*=\s*(.+)$', line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("["):
            cur[key] = re.findall(r'"([^"]+)"', val)
        else:
            cur[key] = val.strip('"')

    warn = [] if contracts else ["No active import-linter contracts found."]
    return contracts, warn


def contract_lines(contracts: list[dict]) -> list[str]:
    if not contracts:
        return ["_No enforced boundaries found._"]
    out = ["| boundary | source | must not import |", "|---|---|---|"]
    for c in contracts:
        src = ", ".join(f"`{s}`" for s in c.get("source_modules", [])) or "—"
        bad = ", ".join(f"`{s}`" for s in c.get("forbidden_modules", [])) or "—"
        out.append(f"| {c.get('name', '?')} | {src} | {bad} |")
    return out


# ------------------------------------------------------------------- component map


def component_lines(root: Path, cards) -> list[str]:
    """Real directories, with how much history each has accumulated.

    The card count is `files:` hits, not `area:` hits. Area is a hand-applied tag and
    a card tagged `frontend` routinely touches backend files; the file paths are the
    only join that is actually true.
    """
    hits: Counter[str] = Counter()
    for c in cards:
        for f in c.fm.get("files") or []:
            for comp, _ in COMPONENTS:
                if str(f).startswith(comp):
                    hits[comp] += 1
                    break

    out = ["| component | what it is | cards | on disk |", "|---|---|---:|---|"]
    for comp, desc in COMPONENTS:
        p = root / comp
        if not p.is_dir():
            out.append(f"| `{comp}` | {desc} | {hits[comp]} | **missing** |")
            continue
        n = sum(1 for q in p.rglob("*") if q.is_file() and q.suffix in (".py", ".ts", ".tsx"))
        out.append(f"| `{comp}` | {desc} | {hits[comp]} | {n} files |")
    return out


def workflow_lines(root: Path) -> list[str]:
    """Workflows are data. Listing them is listing what the engine can run today."""
    d = root / "backend" / "agents" / "workflows"
    if not d.is_dir():
        return ["_`backend/agents/workflows` not found._"]
    names = sorted(
        q.name for q in d.iterdir()
        if q.is_dir() and not q.name.startswith("_") and not q.name.startswith(".")
    )
    if not names:
        return ["_No workflow packages found._"]
    return [
        f"**{len(names)} workflows** registered — " + ", ".join(f"`{n}`" for n in names),
        "",
        "Per SC-001 these are pure data: adding one is a manifest plus an AGENT.md, "
        "with no engine edit and no new pipeline name.",
    ]


# ------------------------------------------------------------------------- decisions


def decision_lines(cards) -> list[str]:
    ds = sorted((c for c in cards if c.type == "decision"), key=lambda c: c.id)
    if not ds:
        return ["_No decision cards yet._"]
    out = ["| ADR | status | area | decision |", "|---|---|---|---|"]
    for c in ds:
        y = str(c.fm.get("y") or c.summary or "").replace("\n", " ").strip()
        if len(y) > 150:
            y = y[:147].rsplit(" ", 1)[0] + "…"
        area = ", ".join(c.area) or "—"
        out.append(f"| `{c.id}` | {c.fm.get('status', '?')} | {area} | {y} |")
    return out


# ------------------------------------------------------------------------------ main


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else repo_root()
    sdir = surface_dir(root)
    sdir.mkdir(parents=True, exist_ok=True)

    cards = load_all(root)
    stage, stage_warn = read_stage(root)
    contracts, contract_warn = read_contracts(root)
    warnings = stage_warn + contract_warn

    decisions = [c for c in cards if c.type == "decision"]
    areas = Counter(a for c in cards for a in c.area)

    lines = [
        "<!-- GENERATED by scripts/knowledge/build_architecture.py — do not edit. -->",
        "",
        "# Current state",
        "",
        "Where the project is right now, and what constrains a change to it. Every "
        "other file in this store is history; this one is the present.",
        "",
        "## Stage",
        "",
        *stage_lines(stage),
        "",
        "## Enforced boundaries",
        "",
        "These are checked by `import-linter` in CI, which makes them the only "
        "architecture claims here that cannot silently drift. Breaking one fails the "
        "build.",
        "",
        *contract_lines(contracts),
        "",
        "## Components",
        "",
        *component_lines(root, cards),
        "",
        *workflow_lines(root),
        "",
        "## Decisions in force",
        "",
        *decision_lines(cards),
        "",
        f"Full text: `ctx.py --show <ID>`. Rules by area: `ctx.py --rules <area>`. "
        f"Areas carrying history: "
        + ", ".join(f"`{a}` ({n})" for a, n in areas.most_common(8))
        + ".",
        "",
        "## Constraints that bind every phase",
        "",
        "10 invariants + SC-001, in `.knowledge/INVARIANTS.md` (~700 tokens). Read it "
        "before designing anything; `INV-1`, `INV-8`, `INV-13` and `SC-001` are the "
        "ones most often broken by an obvious-looking change.",
        "",
        "## What this file does not know",
        "",
    ]

    gaps = list(warnings)
    if len(decisions) < 5:
        gaps.append(
            f"Only {len(decisions)} decision card{'s' if len(decisions) != 1 else ''} exists "
            f"against {sum(1 for c in cards if c.type in ('fix', 'bug'))} fixes and bugs. "
            "Most rules this project actually follows are still implicit in fix prose — "
            "run `knowledge-consolidate` to promote them."
        )
    gaps += [
        "Runtime topology (what is deployed where) is not derived — see "
        "`docs/SIMPLE_AWS_DEPLOYMENT.md`.",
        "The component table counts files and card hits. It does not verify that a "
        "component still does what its description says.",
    ]
    lines += [f"- {g}" for g in gaps]

    out = sdir / "ARCHITECTURE.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"surface: ARCHITECTURE.md {out.stat().st_size / 1024:.1f} KB "
        f"({len(contracts)} contracts, {len(decisions)} decisions, {len(gaps)} gaps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
