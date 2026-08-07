# Plan — Project Knowledge Cards + Thin Context Layer

## Context

**The problem.** `.planning/` holds 3.26 MB of hand-maintained registers. `IMPLEMENTATION-REGISTER.md` alone is 982 KB; `FIX-REGISTER.md` is 344 KB and grows 2–3 entries a day. Three skills auto-inject them wholesale — `velocity-analyze/SKILL.md:54,66,77`, `velocity-fix/SKILL.md:40,190`, `velocity-feature/SKILL.md:193` — so `/velocity-analyze` loads **~1.39 MB (~350 K tokens) before reading a line of source**, under an explicit "do not truncate or skim" instruction.

**Why it costs so much.** The registers mix four kinds of knowledge with different lifecycles: durable *rules* (~20), unbounded *history* (127 fixes / 49 issues / 26 phases), *current state*, and *specs*. Because they share a file, reading any of it means reading all of it. Per-task relevant fraction is under 2%.

**The outcome.** One-time extraction into small per-record cards with machine-readable headers; a generated index and rules file that are the only things loaded by default; a query script that returns the 2–4 relevant cards. Target: **~350 K tokens → ~10 K default + ~10 K fetched.**

**Hard constraints (from the user).**
1. **Create new files only.** No existing register, skill, or doc is modified in Phase 1–4. Everything lands under one new folder; deleting that folder is a complete undo.
2. Existing registers remain the source of truth until explicitly cut over.
3. **Isolated worktree, branched from `dev`. No commits.** Must not disturb the parallel session working in the main checkout.

---

## Isolation

All work happens in a **separate git worktree** — its own directory, own branch, own index. The main checkout at `/Users/bilala/Developer/Projects/VELOCITY-AI` (currently on `feature/diagrams-and-api-fixes`) is never touched, so the parallel session is unaffected: different files on disk, no branch switch, no staged changes, no stash.

```
git worktree add ../VELOCITY-AI-knowledge -b knowledge/cards dev
```

- Branch `knowledge/cards`, based on `dev`. Creating a branch ref does not affect any checkout.
- **Nothing is committed.** All output stays as untracked files in the worktree. Review with `git status` there; nothing enters history until you say so.
- Teardown: `git worktree remove ../VELOCITY-AI-knowledge --force` and `git branch -D knowledge/cards`. Complete undo.

### Source-content caveat — must be handled

`dev` carries **older registers** than your current branch:

| Register | on `dev` | on `feature/diagrams-and-api-fixes` |
|---|---:|---:|
| `FIX-REGISTER.md` | 214,506 B | **344,266 B** |
| `IMPLEMENTATION-REGISTER.md` | 611,543 B | **981,824 B** |
| `ISSUES-REGISTER.md` | 48,166 B | **62,697 B** |

Extracting from the worktree's own files would silently drop ~40% of the fix history. **Resolution:** the worktree is *based* on `dev` as asked, but extraction reads the newest register content out of git rather than the working files:

```bash
git show feature/diagrams-and-api-fixes:.planning/FIX-REGISTER.md
```

Each card's `source:` field then records **branch + path + anchor**, so provenance stays exact. Phase 1 pins this ref once and `check.py` verifies every card's source ref resolves. If you'd rather branch from `feature/diagrams-and-api-fixes` instead, say so and this caveat disappears entirely.

---

## Decision: do we use a graph?

**Yes — a 200-line link map. No graph database, no embeddings.**

The links already exist inside each card's header (`files:`, `relates:`, `produces:`, `supersedes:`). A script walks the headers and writes `links.json`. That *is* the graph. Neo4j/Graphiti buys bi-temporal reasoning we don't need — supersession is one field, and the corpus is ~200 nodes, not 200 K.

**The valuable part is the join to the code graph you already have.** `ba-ready` builds `.apex/.ua/native/graph.json` (imports edges between files). The knowledge cards carry `files:` paths. **File paths are the join key** — no shared database needed:

```
ctx --for frontend/hooks/useRunStream.ts
  → knowledge graph: which rules/fixes/issues touch this file
  → ba-ready graph:  what imports it, blast radius
```

That answers "what do I need to know before I touch this, and what breaks if I do" from two cheap indexes. Revisit a real graph DB only if the corpus passes ~2,000 cards.

---

## Folder structure

Everything new lives in one self-contained root:

```
.knowledge/
├── INDEX.md                 # GENERATED. ~200 one-line entries. Loaded every session.
├── RULES.md                 # GENERATED. All accepted decisions, one line each. Loaded every session.
├── decisions/               # the durable rules — MADR-style, YAML frontmatter
│   ├── ADR-0001-terminal-events-mark-non-reconnecting.md
│   └── ...                                            (~20 expected)
├── fixes/
│   ├── FIX-122.md                                     (127 expected)
│   └── ...
├── issues/
│   └── ISS-015.md                                     (~49 expected)
├── phases/
│   └── PHASE-15.md          # thin pointer card → existing _register-parts/ file. No content copied.
├── schema.md                # the frontmatter contract, human + agent readable
└── .cache/                  # derived, git-ignored
    ├── index.json           # structured mirror of INDEX.md
    ├── links.json           # the graph: file→cards, card→cards, rule→cards
    └── stamp.json           # freshness keys (see Re-sync)

scripts/knowledge/
├── build_index.py           # cards → INDEX.md, RULES.md, .cache/*   (pure script, no LLM)
├── ctx.py                   # the query layer
└── check.py                 # staleness + orphan detection
```

Nothing under `.planning/`, `docs/`, `specs/`, or any existing skill is touched.

**Note on convention:** ADR tooling (log4brains, adr-log, ADG) expects `docs/adr/NNNN-*.md`. We're not adopting that tooling, and keeping everything under one deletable root is worth more than tool compatibility. If that changes later, `docs/adr` becomes a symlink.

---

## Card format

Two shapes. Both are markdown with YAML frontmatter — the frontmatter is what makes the index generatable.

### Fix / issue card (history)

```yaml
---
id: FIX-122
type: fix                      # fix | issue
date: 2026-07-27
status: done                   # open | done | deferred | monitoring | wontfix
area: [sse, frontend]
files:
  - frontend/hooks/useRunStream.ts
  - frontend/app/dashboard/page.tsx
summary: >-
  Reconnect banner fired after cancel because React state updates lag the
  async stream reader loop; fixed by setting the non-reconnect ref synchronously.
source: .planning/FIX-REGISTER.md#fix-122      # provenance — pointer only, never edited
produces: [ADR-0031]                            # rule this fix established, if any
relates: [FIX-121, ISS-015, PHASE-44]
---

<full original prose, verbatim from the register>
```

`summary:` is the index line. `source:` is the audit trail back to the untouched original.

### Decision card (rule)

Body follows **MADR 4.0**; the header carries a **Y-statement** (one-sentence decision format from the ADR community) because that single line is what gets loaded into every session.

```yaml
---
id: ADR-0031
type: decision
status: accepted               # proposed | accepted | superseded | deprecated
date: 2026-07-27
area: [sse]
y: >-
  In the context of SSE terminal events, facing spurious reconnect banners,
  we decided to mark the connection non-reconnecting synchronously inside the
  frame dispatcher, to achieve a quiet disconnect, accepting that detachRun
  stays only as additive insurance.
files: [frontend/hooks/useRunStream.ts]
enforced_by: [frontend/e2e/ts-f.sse.spec.ts]   # optional — a test that fails if violated
supersedes: []
derived_from: [BUG-015, FIX-121, FIX-122]
---

## Context and Problem Statement
## Considered Options
## Decision Outcome
### Consequences
### Confirmation
```

**Why the split matters:** FIX-122's full write-up is ~2,300 words of race-condition tracing — history, load on demand. What it *established* — "terminal events mark the connection non-reconnecting" — is ~40 tokens and belongs in context permanently. Roughly 1 in 5 fixes yields a rule.

---

## How context is built (three tiers, `ba-ready` pattern)

```
  .planning/*.md            immutable sources — NEVER modified, NEVER read wholesale
        │
        │  EXTRACT   (LLM, batched, one-time + incremental)
        ▼
  .knowledge/**/*.md        cards — durable, git-committed, human-editable
        │
        │  INDEX     (pure Python, no LLM, ~2 seconds)
        ▼
  .knowledge/.cache/*.json  structured index + link graph
        │
        │  RENDER
        ▼
  INDEX.md + RULES.md       the session prime
```

| Tier | Artifact | Size | Read into context? |
|---|---|---|---|
| 1 | `.planning/` registers, card bodies | 3.26 MB / ~1 MB | **Never wholesale** |
| 2 | `.cache/index.json`, `links.json` | ~200 KB | Only by `ctx.py` |
| 3 | `RULES.md` + `INDEX.md` | **~10 KB** | **Yes — every session** |

Budget for tier 3: ~20 rules × ~45 tokens ≈ 900, plus ~200 index lines × ~35 tokens ≈ 7 K. **Under 10 K tokens for total awareness of the entire project history.** Then 2–4 cards fetched on demand (~8 K).

This mirrors what `ba-ready` already does for code structure (`graph.json` → `pack.json` → `context-pack.md`), applied to history instead. It also matches the event-sourcing pattern from the research: an immutable log plus cheap materialized projections that agents query instead of replaying.

---

## The thin wrapper — `ctx.py`

Reads `.cache/*.json` only. Returns card *references*, never bodies — the agent decides what to open.

```bash
$ ctx "reconnect banner"
ADR-0031  rule   accepted  [sse]           terminal events mark connection non-reconnecting
FIX-122   fix    done      [sse,frontend]  reconnect banner fired after cancel; React state lag
ISS-015   issue  fixed     [sse]           stream_attached{live:false} did not suppress reconnect

$ ctx --for frontend/hooks/useRunStream.ts     # everything touching this file
$ ctx --rules sse                              # rules in force for an area
$ ctx --show FIX-122                           # print one card body
$ ctx --check                                  # freshness + orphans
```

Backed by ripgrep over frontmatter plus `links.json` lookups. **No SQLite, no embeddings.** At ~200 cards that's milliseconds. If the corpus passes ~1,000 cards, swap the backend for SQLite FTS5 behind the same CLI — that's the pattern CodeGraph and memweave converged on, and no card changes.

---

## Re-sync and staleness

Three independent drifts. All are *detected and reported*, never silently tolerated — a confident stale map is worse than no map.

**1. Cards vs registers** (someone appends to `FIX-REGISTER.md` the old way)
`stamp.json` stores each source register's sha1 + size + mtime and the highest ID extracted. `ctx --check` reports `FIX-REGISTER.md: 3 entries newer than last extraction (FIX-128..130)`. Fix: run the extract skill on the delta only.

**2. Index vs cards** (a card was added or hand-edited)
Cheap — the index is a pure function of the card frontmatter. Hash the concatenated frontmatter blocks into `stamp.json`; mismatch triggers a rebuild. Takes seconds, no LLM. Run on demand, or via a git `pre-commit` hook once trusted.

**3. Cards vs code** (the dangerous one — a card names a file that was renamed or deleted)
`check.py` validates every `files:` path exists. Reports orphans explicitly rather than letting a card assert something about a file that's gone. Same discipline as `ba-ready`'s blind-spot reporting.

**Growth after the one-time build:** each new fix writes **one card**. The index regenerates in seconds. **No re-extraction, ever.** That is what "build it once" means here.

**Consolidation (episodic → semantic).** Per phase or monthly, a skill reads the fix cards added since the last run and asks: *did any of these establish a rule?* Proposed ADRs go to you for approval. This is the mechanism that keeps `RULES.md` complete without keeping it noisy — and it's the one loop that must not be automated blindly.

---

## Skills

Four new skills, no existing skill modified in Phases 1–4.

| Skill | Job | LLM? | When |
|---|---|---|---|
| **`knowledge-extract`** | Read one source shard → emit cards. Idempotent, refuses to overwrite an existing card without `--force`. Never writes to `.planning/`. | Yes | One-time build; then only for deltas |
| **`knowledge-index`** | Run `build_index.py`; regenerate `INDEX.md`, `RULES.md`, `.cache/*`. Report what changed. | No | After any card change |
| **`knowledge-prime`** | The `ba-ready` analogue for history. Check staleness, read `RULES.md` + `INDEX.md`, report 5–10 lines. Once per session; refuses to re-read if already primed. | No | Session start |
| **`knowledge-consolidate`** | Review recent fix cards, propose ADRs for rules they established. Output goes to you for approval. | Yes | Per phase / monthly |

**Phase 5 (separate approval):** rewrite `velocity-fix` / `velocity-feature` / `velocity-analyze` to (a) drop the three auto-include directives, (b) call `ctx`, (c) write a card *in addition to* the register append. Deliberately last — nothing existing changes until the new path is proven. Note these skills exist in **three byte-identical trees** (`.agents/`, `.claude/`, `.kiro/`), so that step is a 3× edit and should also fix the duplication.

---

## Execution phases

| # | Phase | Output | Notes |
|---|---|---|---|
| 1 | Schema + scaffolding | `.knowledge/schema.md`, empty tree, `build_index.py`, `ctx.py`, `check.py` | No content yet. Verify the pipeline on 3 hand-written cards |
| 2 | Pilot extraction | ~10 fix cards + the 2–3 ADRs they yield, from the SSE cluster | **Review gate.** Confirm the card shape is right before committing to 200 |
| 3 | Full extraction | 127 fix + ~49 issue + 26 phase pointer cards; ~20 ADRs | Batched per shard. Sources untouched |
| 4 | Prime + query proven | `knowledge-prime` working; measured token comparison | Still nothing existing modified |
| 5 | Cutover *(separate approval)* | velocity-* skills use `ctx`; auto-includes removed | The only phase that edits existing files |

**Quick win available immediately and independent of all of this:** deleting the three auto-include directives is a ~10-minute change worth most of the token savings on its own. Worth doing in isolation if you want relief before the build lands.

---

## Verification

**Pipeline correctness (Phase 1)**
```bash
python3 scripts/knowledge/build_index.py .        # → INDEX.md, RULES.md, .cache/*
python3 scripts/knowledge/check.py                # → 0 orphans, 0 stale, exit 0
python3 scripts/knowledge/ctx.py "reconnect"      # → returns the seeded cards
```

**Extraction fidelity (Phase 2 gate — the one that matters)**
- Every card's `source:` resolves to a real anchor in the untouched register.
- Spot-check 3 cards against their originals: no invented facts, prose preserved verbatim.
- `git status` shows **only additions** — no modification to any file under `.planning/`.
- Each proposed ADR traces to a real "locked decision" or root-cause conclusion, not a summary of one.

**Token measurement (Phase 4 — prove the premise)**
- Measure `RULES.md` + `INDEX.md` combined. **Fail the phase if over 15 K tokens.**
- Run one real past fix both ways — old path vs `prime` + `ctx` + open matched cards. Record both totals. Target ≥ 85% reduction.

**Retrieval quality (Phase 4 — the real test)**
- Take 10 fixes from the register. For each, feed only its symptom to `ctx`. **Did the right card surface in the top 5?** Below 8/10, the `summary:` fields are too vague — fix the extraction prompt, not the retrieval backend.

**Regression safety**
- `.planning/` sha1s unchanged from the start of the work.
- Deleting `.knowledge/` and `scripts/knowledge/` restores the repo exactly.

**Isolation (check at every phase)**
- `git status` in the worktree shows **untracked files only** — no modifications, nothing staged, no commits.
- `git worktree list` shows the main checkout still on `feature/diagrams-and-api-fixes` at its original sha.
- Nothing is written outside `../VELOCITY-AI-knowledge/`.

---

## Appendix — research basis

Standards: **MADR 4.0** (frontmatter → generatable index), **Y-statements** (one-line decisions), ISO/IEC/IEEE 42010 App. A (decision log), and the community position that fixes belong in a ledger, not in ADRs — only decision-bearing ones get promoted. Retrieval: files+grep is sufficient under ~500 records; SQLite FTS5 is the proven next rung (CodeGraph, memweave, agent-memory-mcp). Architecture: just-in-time context loading over preloading; three-tier progressive disclosure (~80 tokens/record discovery); event-sourced log + materialized projections (arXiv 2606.23752); episodic→semantic consolidation. Tools surveyed but not adopted: log4brains, adr-log, git-adr, ADG (`adr/ad-guidance-tool` — ADR→enforceable `.rule` tests + MCP, worth revisiting for `enforced_by:`), mcp-adr-analysis-server, Basic Memory, cognee, Graphiti/Zep, Repomix.

Full annotated source list with links was delivered in the prior research report in this session.

---
---

# AS BUILT — 2026-07-31

Delta between the approved plan above and what actually shipped. Where the two
disagree, this section is authoritative.

## Result

| | Planned | Actual |
|---|---|---|
| Cards | ~200 | **241** (168 fix, 49 issue, 23 phase, 1 decision) |
| Prime (`RULES.md` + `INDEX.md`) | ≤ 15 K tokens | **12.5 K** |
| Typical fix working set | ≥ 85% reduction | **96.4%** — 383 K → 13.7 K tokens (28×) |
| Retrieval gate | ≥ 8/10 in top-5 | **10/10, all rank 1** |

## Changed from the plan

**Branch base.** `dev` was rebased mid-build and is now *ahead* of
`feature/diagrams-and-api-fixes` (151 fix rows vs 125). The planned cross-branch
`git show` workaround was dropped: `sources.json` pins `content_ref: dev` and the
worktree reads its own files.

**Extraction is mechanical, not LLM.** The register's 8-column table is regular
enough to derive every field from. `extract.py` is deterministic and re-runnable;
no model is in the loop, so there is nothing to hallucinate. `knowledge-consolidate`
is the only skill that reasons, and its output is reviewed.

**`.knowledge/overrides.json` was added** (not in the plan). Hand-written summaries
and `produces:` links were destroyed by the first `--force` re-extraction. Overrides
are re-applied after every extract, so the store stays rebuildable without losing
hand work.

**`scripts/knowledge/extract.py` was added** as a fifth script.

## Findings that forced design changes

**14 register ids are reused for two unrelated fixes each** — `FIX-007` is both a
Windows `ModuleNotFoundError` crash and an audit-hooks feature. Merging them
produced cards whose header described one fix and whose body described another, and
this was the direct cause of both retrieval-gate misses. Colliding entries are now
split into `FIX-007` / `FIX-007b`, each carrying `collision_of:` and pointing at the
same register anchor. **The suffix exists only in the card store** — the register is
untouched, so cite `source:` when writing back.

Affected: FIX-001, 002, 003, 004, 005, 007, 021, 039, 040, 041, 042, 049, 050, 144.

**Two fixes have no table row.** `FIX-128` and `FIX-129` exist only as detail
sections and were silently dropped by the first pass. Their headers are now derived
from the section itself.

**Only ~1/3 of fixes have a detail section.** The rest are table rows only. Those
cards say so explicitly rather than padding.

**6 referenced paths no longer exist**, most notably
`backend/app/api/websocket.py` across 8 fixes — real history from the websocket→SSE
migration. Reported as warnings, never silently dropped.

**`useRunStream.test.ts` has a coverage gap.** It covers BUG-015 (non-live attach)
but nothing drives `pipeline_cancelled`/`pipeline_failed` through the dispatcher —
so the regression FIX-122 fixed would not be caught today. Recorded in ADR-0001's
Confirmation section rather than claiming coverage.

## Full migration (added after the plan, at user request)

Everything in `.planning/` is now carried, so deletion decisions can be made later
against a complete store. **1064 / 1064 files covered**, 2 excluded by design
(`STATE.md` — session state, not durable knowledge; `config.json` — tooling config).

`scripts/knowledge/migrate.py` handles what `extract.py` does not, in two modes:

- **Entry extraction** where a file has addressable entries — 28 QA bug cards,
  49 test-register sections, 40 requirement sections. The card carries the entry.
- **Pointer cards** for narrative documents and work folders — 67 docs, 111 task
  folders. Summary plus path; **content is never copied**. `.planning/phases/` alone
  is 13 MB.

**Two-tier index, so the prime stays cheap.** 536 cards would be ~35 K tokens if all
listed. Primary types (decision/fix/issue/phase) stay in `INDEX.md` — always loaded,
still **12.5 K**. Secondary types (bug/test/req/doc/task) go to `CATALOG.md` — 32 KB,
loaded on demand. `ctx.py` searches both identically, so nothing is unreachable.

`check.py` now has a permanent **coverage check**: any file under `.planning/` that is
neither carried by a card nor on the documented exclusion list is reported as a gap.

## Superseded — coverage before the full migration

Covered: `FIX-REGISTER.md` (168 cards), `ISSUES-REGISTER.md` (49),
`IMPLEMENTATION-REGISTER.md` (23 phase pointers), `ROADMAP.md` invariants
(`INVARIANTS.md`, hand-written).

**Not covered:** the three QA bug logs (30 entries, ~251 KB) · `TEST-REGISTER.md`
(214 assertions) · `REQUIREMENTS.md` (126 ids) · `.planning/quick/` (65 folders) ·
`.planning/phases/` (46 folders, 13 MB) · `live-verification/` · `v2.0-evidence/`.
`STATE.md` is excluded by design. **Absence from the index is not evidence of
absence** — the prime skill says so explicitly.

## Enforcement (added at user request)

Instructions alone do not stop an agent reading a register. `PreToolUse` supports
`updatedInput`, so `scripts/knowledge/register_read_gate.py` **redirects** a Read of
a register to a ~2 KB surface file (`.knowledge/surface/`, generated by
`build_surface.py`) rather than denying it — a denial teaches an agent to route
around the gate, a redirect teaches it where to look. Bash `cat`/`sed` dumps are
denied outright; `grep`/`wc` stay allowed. Hooks run inside subagents, so the
fresh-context gap is covered. See `.knowledge/ENFORCEMENT.md`.

**The auto-includes remain the binding constraint.** Until Phase 5 removes them,
`/velocity-analyze` still costs ~383 K tokens no matter what the hook does.

## Single-file store (added at user request)

536 card files felt like the same sprawl. Measured first: the file count costs
**zero tokens** — nothing is read until opened, and the prime is 51 KB either way.
The real waste was **870 KB of prose copied verbatim** from `.planning/` into 334
cards, against only 177 KB of headers, which are the only part anything reads.

So the consolidation was not to merge files but to stop copying bodies:

| | Before | After |
|---|---|---|
| Files | 536 | **1** (`records.jsonl`) |
| Size | 1116 KB | **197 KB** (82% smaller) |
| Bodies | copied | resolved from `source` on demand — all 334 verified |

JSONL rather than one big markdown file on purpose: a markdown store re-creates the
original problem, where anything that opens it gets everything. JSONL is
line-addressable and diffs one line per change. `compact.py --restore` regenerates
per-card files; `--materialize` inlines bodies if `.planning/` is ever deleted.

Two defects this surfaced and fixed:
- **Pointer cards outranked real answers.** 292 migrated doc/task cards match on
  title words while carrying no detail. Added a type prior so decisions and fixes
  rank above pointers.
- **Quoted queries matched nothing.** `ctx.py "reconnect banner"` arrives as one
  argv entry and was scored as a single literal — while every doc tells you to
  quote. Terms are now split on whitespace. Retrieval: **10/10 across 536 cards**.

## Still open

- **Phase 5 (cutover) not started**, as planned — it needs separate approval. The
  three auto-include directives in `velocity-analyze` / `velocity-fix` /
  `velocity-feature` are untouched, so nothing currently uses this store
  automatically. Until then it is opt-in via `/knowledge-prime`.
- **Only one ADR exists.** `knowledge-consolidate` has not been run over the full
  corpus; expect roughly 20–30 rules from 168 fixes.
- **Issue cards still have almost no `files:`.** Mining paths from the evidence prose
  recovered only 2 of 49 — the register rarely names full paths. `ctx --for <path>`
  effectively does not reach issues; they are text-searchable only.
- **`INVARIANTS.md` is hand-maintained**, unlike INDEX/RULES, so it can drift from
  ROADMAP. INV-4/6/10/11 have no definition anywhere and were left out rather than
  guessed. The register's invariants column is ~95% boilerplate, so a citation is
  weak evidence a fix truly touched that invariant.
- **Nothing is committed.** All output is untracked on branch `knowledge/cards`.
- **Skill placement.** `.claude/` is gitignored in this repo (`.gitignore:47`), so the
  skills are mirrored into `.agents/skills/` — which is *not* ignored and will travel
  with the branch. Note `.agents/` does not exist on `dev` at all; on the feature
  branch it is the source tree that `.claude/` and `.kiro/` copy from. Reconcile that
  during cutover.
