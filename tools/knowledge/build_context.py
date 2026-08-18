#!/usr/bin/env python3
"""Build .knowledge/CONTEXT.md, the compacted navigation pack.

Procedure and section contract: skills/velocity/prime.md
Run: python3 tools/knowledge/build_context.py

CONTEXT.md is a NAVIGATION pack, not a data dump: it tells an agent what
exists and where to look, not what the data says. Anything reachable in one
file-read (the full card list in INDEX.md, per-module detail in the
architecture cards) is not reproduced here.

Sections 3, 4 are derived directly from .knowledge/cards/*.md frontmatter,
.knowledge/architecture/modules.json, .knowledge/architecture/MOD-*.md
(`## Purpose` sections only), and .knowledge/state.yaml.
Sections 3/4 deliberately do NOT read .knowledge/INDEX.md, which is built by
a separate tool and may be mid-rewrite.
Sections 1, 2 and 5 are hand-authored template constants below (editorial
content that cannot be derived mechanically) and are kept in sync with
.knowledge/ARCHITECTURE.md by hand when that file's opening changes.
"""
import datetime
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE = ROOT / ".knowledge"
CARDS_DIR = KNOWLEDGE / "cards"
ARCH_DIR = KNOWLEDGE / "architecture"
OUT_PATH = KNOWLEDGE / "CONTEXT.md"

CLOSED_STATUSES = {"done", "closed", "resolved", "superseded"}

# ---------------------------------------------------------------------------
# Section 1 — hand-authored, condensed from ARCHITECTURE.md's opening.
# ---------------------------------------------------------------------------
SECTION_1 = """## 1. What Velocity is

Velocity (internally **Flowin**) is a **workflow-agnostic agent execution
runtime**. A workflow is described by a declarative, file-backed manifest. A
thin compiler (no DSL) turns that manifest into a typed `CompiledWorkflow` /
`ExecutionPlan`. A small kernel executes the plan and knows no workflow by
name — there is no `if pipeline_type == "prototype"` anywhere in it.
Everything that makes a workflow powerful (execution strategies, validators,
deliverable resolvers, context providers, gates, merge strategies, task
parsers, worker agents, runtimes, skills, hooks, tools, MCP servers,
integrations) is a **registered capability** a manifest opts into by
declaration.

**SC-001 (the load-bearing invariant):** A brand-new custom workflow can
replicate the built-in `prototype` workflow using a manifest and an
`AGENT.md` alone — with zero engine edits. If everything else here is
negotiable, this is not.

```
manifest -> WorkflowCompiler (no DSL) -> CompiledWorkflow/ExecutionPlan
    -> Kernel (backend/agents) -> CapabilityRegistry.resolve(kind, name)
    -> Workspace/RuntimeEnvironment (local today; ECS is a swap)
FastAPI (backend/app/api) <-> SSE/WS <-> frontend (Next.js)
```
"""

# ---------------------------------------------------------------------------
# Section 2 — hand-authored invariants/boundaries (Always/Ask first/Never).
# ---------------------------------------------------------------------------
SECTION_2 = """## 2. Invariants and boundaries

**Always**
- The kernel stays workflow-agnostic — no `if pipeline_type == ...` /
  `if spec.id == ...` branch anywhere in it (INV-1).
- Every capability is resolved through `CapabilityRegistry.resolve(kind,
  name)` behind a Protocol port.
- Database migrations are additive only.
- Import the real LangChain `deepagents` library (INV-13) — a hand-rolled or
  vendored deep-agent runtime is banned and CI-gated.

**Ask first**
- Anything that would violate SC-001 (a new workflow must be expressible as
  manifest + `AGENT.md` with zero engine edits).
- Changes to the `Workspace`/`RuntimeEnvironment` port, which an
  import-linter contract locks shut to keep the ECS swap possible.
- Enabling local exec, which is off by default and sits behind the
  `security` + `approval` gates.

**Never**
- Edit below an architecture card's `<!-- AUTO-GENERATED BELOW THIS LINE`
  marker, or hand-edit `INDEX.md` / `state.yaml` / `modules.json` — all are
  generated.
- Renumber, reuse or delete a card ID — corrections supersede.
- Run `git commit` / `git add` / `git push` or any branch operation — the
  user handles all git.
"""

# ---------------------------------------------------------------------------
# Section 5 — hand-authored usage note.
# ---------------------------------------------------------------------------
SECTION_5 = """## 5. Retrieval protocol

**NEVER read or grep `cards/*.md` or `architecture/*.md` in bulk.** That is
951 + 36 files; it blows out the context window and buries the answer. The
index exists so you never have to. Reading whole directories is the single
worst thing you can do in this knowledge base.

Always go index-first:

1. **Read [INDEX.md](INDEX.md)** — one file, one line per card:
   `- [ID](cards/<file>.md) — <compact_summary>`. Every card's summary states
   its root cause, resolution, or mechanism, so the index alone is usually
   enough to tell which cards matter.
2. **Match the user's query against those summary lines** — semantically, not
   by exact keyword. A symptom is rarely worded the way the card is. Shortlist
   the handful of plausible IDs.
3. **Open ONLY those candidate cards**, by following the link on the matched
   line. Typically 2-5 files. If the shortlist is empty, re-read the index
   with a broader reading of the symptom before widening anything else.
4. **For architecture**, do the same: start from the module map in section 4,
   pick the ONE module that owns the behaviour, and open only that
   `MOD-*.md`. Never sweep the directory.

- **Resolve a known card ID**: glob `.knowledge/cards/*-<ID>.md`. Files are
  named `{YYYYMMDD}[-{HHMM}]-{ID}.md`, so the ID is a suffix, not a prefix.
  (Some cards are date-only — their authoring time was not recoverable.)
- **Symptom -> module**: use the index (steps 1-3), then read the matched
  card's `applies_to.modules` / `applies_to.globs` and look that module up in
  section 4. Do not grep the corpus for the glob.
- **Architecture card divider contract**: in each `MOD-*.md`, the YAML
  frontmatter and everything from the `<!-- AUTO-GENERATED BELOW THIS LINE`
  marker downward is machine-generated and rewritten by
  `tools/knowledge/build_architecture.py`; `## Purpose` / `## Shape` / `## Why this
  shape`, above that marker, are hand-authored and preserved across
  regeneration.
- **IDs are permanent.** Corrections supersede rather than edit: a new card
  is filed pointing at the old ID, whose status then changes — the old ID
  and content stay intact as a historical record.
"""


def head_commit() -> str:
    """Current HEAD sha, or "" outside a git checkout."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


class MissingInput(RuntimeError):
    """A prerequisite artifact this stage reads has not been generated yet."""


def load_state():
    """`state.yaml` as a dict.

    `state.yaml` is PRODUCED by `build_index.py`, not by this script, so on a
    tree that has never been built it simply does not exist. That is an
    ordering mistake with a one-line fix, but it used to surface as a raw
    `FileNotFoundError` traceback naming a path -- leaving the reader to work
    out which of eight scripts creates it. Everything else in this pipeline
    fails with an instruction; this did not.
    """
    path = KNOWLEDGE / "state.yaml"
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise MissingInput(
            f"{path.relative_to(ROOT)} does not exist yet.\n"
            f"  It is generated by build_index.py, which must run BEFORE this "
            f"stage.\n"
            f"  Fix: python3 tools/knowledge/rebuild_knowledge.py\n"
            f"  (or run tools/knowledge/build_index.py first, then re-run this.)"
        ) from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MissingInput(
            f"{path.relative_to(ROOT)} is not valid YAML "
            f"({exc.__class__.__name__}).\n"
            f"  It is generated -- do not hand-edit it.\n"
            f"  Fix: python3 tools/knowledge/build_index.py"
        ) from None
    if not isinstance(data, dict):
        raise MissingInput(
            f"{path.relative_to(ROOT)} did not parse to a mapping.\n"
            f"  Fix: python3 tools/knowledge/build_index.py"
        )
    return data


def load_modules():
    """The module list from `modules.json`.

    Produced by `build_architecture.py`, not by this script -- so like
    `state.yaml` it is simply absent on a tree that has never been built. Same
    failure, same fix, same message shape: name the file, name the producer,
    give the command.
    """
    path = ARCH_DIR / "modules.json"
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise MissingInput(
            f"{path.relative_to(ROOT)} does not exist yet.\n"
            f"  It is generated by build_architecture.py, which must run "
            f"BEFORE this stage.\n"
            f"  Fix: python3 tools/knowledge/rebuild_knowledge.py"
        ) from None
    try:
        return json.loads(text)["modules"]
    except (ValueError, KeyError) as exc:
        raise MissingInput(
            f"{path.relative_to(ROOT)} is unreadable "
            f"({exc.__class__.__name__}) -- it is generated, do not hand-edit "
            f"it.\n  Fix: python3 tools/knowledge/build_architecture.py"
        ) from None


def load_cards():
    """List of frontmatter dicts, one per card, plus its filename."""
    cards, skipped = [], []
    for path in sorted(CARDS_DIR.glob("*.md")):
        # Strip the BOM from `text` ITSELF, not just for the check below.
        # `utf-8` leaves a BOM in the string, and everything after this point
        # indexes by fixed offset (`text[3:end]`, `find("\n---", 3)`) -- so
        # testing a stripped copy while slicing the unstripped original puts
        # every offset one character out, yaml.safe_load raises, and the card
        # is dropped from the pack while build_index still lists it in
        # INDEX.md. The two loaders must agree on what a card is.
        text = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
        if not text.startswith("---"):
            skipped.append(path.name)
            continue
        end = text.find("\n---", 3)
        if end == -1:
            skipped.append(path.name)
            continue
        try:
            fm = yaml.safe_load(text[3:end])
        except yaml.YAMLError:
            skipped.append(path.name)
            continue
        if isinstance(fm, dict) and "id" in fm:
            fm["_filename"] = path.name
            cards.append(fm)
        else:
            skipped.append(path.name)
    # Say what was dropped. Silently omitting a card from the context pack
    # produces a pack that looks complete and is not -- and this stage used to
    # skip the very files build_index.py crashed on, so the two disagreed
    # about what a card is with nobody reporting it.
    if skipped:
        print(f"not cards (no parseable frontmatter, skipped): {len(skipped)}")
        for name in skipped[:5]:
            print(f"  - {name}")
    return cards


FAMILY_RE = re.compile(r"^(.*?)-(\d+)$")


def build_section_3(cards):
    lines = ["## 3. Card store", ""]

    by_type = defaultdict(list)
    for fm in cards:
        by_type[fm.get("type", "?")].append(fm)

    total_cards = len(cards)

    lines.append("| type | total | open/active |")
    lines.append("|---|---|---|")
    type_order = ["adr", "fix", "issue", "bug"]
    for typ in type_order:
        entries = by_type.get(typ, [])
        open_n = sum(
            1 for fm in entries
            if (fm.get("status") or "").lower() not in CLOSED_STATUSES
        )
        lines.append(f"| {typ} | {len(entries)} | {open_n} |")
    lines.append("")


    # adr — the only type listed individually (single card, load-bearing).
    adr_entries = by_type.get("adr", [])
    lines.append(f"**adr ({len(adr_entries)}):**")
    for fm in adr_entries:
        cid = fm.get("id")
        title = fm.get("title", cid)
        lines.append(f"- [{cid}](cards/{fm['_filename']}) — {title}")
    lines.append("")

    lines.append(
        "Start every card lookup at [INDEX.md](INDEX.md) — one line per card, "
        "each carrying a `compact_summary` that states the root cause or "
        "resolution. Match the query against those lines, then open only the "
        "handful of cards that matched. Never read or grep `cards/*.md` in "
        "bulk (see section 5)."
    )
    lines.append("")

    return "\n".join(lines).rstrip() + "\n", total_cards


MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def flatten_links(text):
    """[`engine.py`](../../backend/...) -> `engine.py`.

    Module prose carries markdown links to source files, written relative to
    `.knowledge/architecture/`. This gloss lands in `.knowledge/CONTEXT.md`,
    one directory up, where the same `../../` prefix points outside the repo.
    The 90-char truncate() below can also cut a link in half, leaving an
    unclosed `](`. Both put broken links into a file that is otherwise pure
    navigation, so the gloss keeps the link TEXT and drops the target.
    """
    return MD_LINK.sub(r"\1", text)


def truncate(text, limit):
    """Truncate at a word boundary <= limit chars, with an ellipsis."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:—-") + "…"


def build_section_4():
    lines = ["## 4. Module map", ""]
    modules = load_modules()
    count = 0
    for mod in modules:
        mod_id = mod["id"]
        mod_path = mod.get("path", "")
        file_count = mod.get("file_count", "?")

        mod_card = ARCH_DIR / f"{mod_id}.md"
        purpose = ""
        if mod_card.exists():
            text = mod_card.read_text()
            end = text.find("\n---", 3)
            body = text[end + 4:] if end != -1 else text
            m = re.search(r"## Purpose\s*\n\n(.+?)(?:\n\n|\Z)", body, re.S)
            if m:
                purpose = flatten_links(m.group(1).strip())

        # 40 chars cut every gloss mid-clause ("is a one-shot..."), which is
        # worse than no gloss at all. 90 costs ~1.8k chars across 36 modules
        # and still leaves the pack well inside budget.
        gloss = truncate(purpose, 90) if purpose else "not yet authored"
        unit = "file" if file_count == 1 else "files"
        lines.append(
            f"- [{mod_id}](architecture/{mod_id}.md) — {mod_path} — "
            f"{file_count} {unit} — {gloss}"
        )
        count += 1

    lines.append("")
    return "\n".join(lines).rstrip() + "\n", count


def main():
    state = load_state()
    cards = load_cards()

    # Reuse the existing pack's date. `built_at` records when the pack was
    # generated, but a fresh wall-clock value makes CONTEXT.md differ from
    # itself with byte-identical content -- so any hook that regenerates it
    # reports a modification on every commit. The write below only lands when
    # something else actually changed, and it stamps a new date then.
    prior_built_at = ""
    if OUT_PATH.exists():
        m_ba = re.search(
            r"^built_at:\s*(\S+)", OUT_PATH.read_text(encoding="utf-8"), re.M
        )
        if m_ba:
            prior_built_at = m_ba.group(1)
    built_at = prior_built_at or datetime.date.today().isoformat()

    sec3, cards_indexed = build_section_3(cards)
    sec4, modules_indexed = build_section_4()

    frontmatter = (
        "---\n"
        # `built_at` is carried over from the existing pack when nothing else
        # changed. A fresh wall-clock date on every run made CONTEXT.md differ
        # from itself with identical content, so any hook that regenerates it
        # reported a modification on every commit.
        # HEAD, not state['last_sync_commit']. The two are no longer the same
        # thing: the sync watermark is deliberately frozen until `sync` runs,
        # so reading it here stamped every rebuild with a commit the pack was
        # not built from -- and `status` then reported the pack stale forever.
        # This field means "the commit whose content this pack reflects".
        f"built_from_commit: {head_commit()}\n"
        f"built_at: {built_at}\n"
        f"cards_indexed: {cards_indexed}\n"
        f"modules_indexed: {modules_indexed}\n"
        "---\n"
    )

    body = "\n".join([
        frontmatter,
        "# Velocity — Context Pack",
        "",
        SECTION_1.rstrip(),
        "",
        SECTION_2.rstrip(),
        "",
        sec3,
        sec4,
        SECTION_5.rstrip(),
        "",
    ])

    if OUT_PATH.exists():
        prior = OUT_PATH.read_text(encoding="utf-8")
        if prior.replace(f"built_at: {built_at}", "") == body.replace(f"built_at: {built_at}", ""):
            print(f"Wrote {OUT_PATH} (unchanged)")
            return
    OUT_PATH.write_text(body)

    approx_tokens = len(body) // 4
    print(f"Wrote {OUT_PATH} ({len(body)} chars, ~{approx_tokens} tokens)")
    print(f"cards_indexed={cards_indexed} modules_indexed={modules_indexed}")

    by_type = defaultdict(list)
    for fm in cards:
        by_type[fm.get("type", "?")].append(fm)
    for typ in ("adr", "issue", "bug", "fix"):
        entries = by_type.get(typ, [])
        open_n = sum(
            1 for fm in entries
            if (fm.get("status") or "").lower() not in CLOSED_STATUSES
        )
        print(f"  {typ}: {len(entries)} total, {open_n} open/active")


if __name__ == "__main__":
    # A missing prerequisite is a usage error, not a crash. Print the
    # instruction and exit non-zero -- no traceback, because the stack tells
    # the reader nothing they can act on.
    try:
        main()
    except MissingInput as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
