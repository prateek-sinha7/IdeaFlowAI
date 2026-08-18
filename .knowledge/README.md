# `.knowledge/` — what this is and how it works

A structured, machine-maintained record of what this codebase **is**, what
**happened** to it, and **why it is shaped the way it is** — kept honest by
signatures and a pre-commit hook rather than by discipline.

The problem it solves: documentation rots silently. A function gets renamed and
every document naming the old one is now wrong, with nothing anywhere
disagreeing. This system's whole design goal is that **staleness is detected,
not hoped against**.

---

## The shape of it

```
.knowledge/
├── cards/                482 event cards — what happened
├── architecture/
│   ├── DOMAIN-*.md        14 — hand-authored SYSTEM CONCERNS  ← the diagrams live here
│   ├── MOD-*.md           36 — one per FOLDER, generated
│   ├── files/**.md       789 — one per source file, generated
│   └── modules.json           machine-readable import graph
├── INDEX.md                   one line per card (retrieval goes through this)
├── ARCHITECTURE.md            the overview + every domain diagram, inlined
├── CONTEXT.md                 compacted context pack for fast priming
├── state.yaml                 last sync commit, corpus counts
└── .stage/                    delta approval queue (absent = nothing pending)
```

Three of those are **derived** and must never be hand-edited: `INDEX.md`,
`CONTEXT.md`, `state.yaml`. Two are **partly** derived — see the marker
contract below.

---

## Part 1 — Cards (`cards/`)

482 cards recording things that happened. Filename is
`{YYYYMMDD}[-{HHMM}]-{ID}.md`; the time is present only when a real authoring
commit supplied one — a fabricated time is worse than an absent one, and
`validate_links.py` rejects times in the future.

**Four types, and no others:**

| Type | Count | Kind | What it records |
|---|---|---|---|
| `fix` | 266 | event | a defect that was fixed |
| `issue` | 162 | event | an open or resolved problem |
| `bug` | 42 | event | a defect as reported |
| `adr` | 12 | state | a technical decision and its rationale |

`requirement`, `phase` and `doc` were **retired**. Every card of those types was
a generated stub whose body only pointed into `.planning/`, so they were deleted
rather than migrated — a card that says "go read this other file" costs tokens
and carries nothing.

**Frontmatter:** `id`, `type`, `kind`, `title`, `status`,
`applies_to{phases,modules,globs,requirements}`, `locked_constraints`,
`verification`, `compact_summary`, `last_updated`, `author`.

**IDs are permanent.** `{TYPE_CODE}[-{SUBTYPE}]-{rest}` where TYPE_CODE is
`FIX|BUG|ISS|ADR` — e.g. `FIX-233`, `ISS-147`, `BUG-012-sse`. A card is never
renumbered and never deleted. Corrections happen by **supersession**: write a
new card, link it, set the old one's `status` to `superseded`. Never rewrite a
trusted card's meaning in place.

**Cross-references live in the body**, in a `## Related` block directly under
the frontmatter:

```markdown
<!-- RELATED -->
## Related

**Depends on:** [FIX-034](20260704-1815-FIX-034.md)
**Referenced by:** [ISS-098](20260705-0912-ISS-098.md)
<!-- /RELATED -->
```

They are ordinary markdown links, so they are clickable in any editor. They
used to live in frontmatter, where nothing was ever clickable because YAML is
not a rendering context.

The ID is the stable key and the filename is not (it carries a datetime), so
`build_index.py` **re-resolves every target on each rebuild** — rename a card
and the links pointing at it follow. A reference that resolves to no card is
left as bare text rather than dropped, so `validate_links.py` reports it
instead of it vanishing silently.

---

## Part 2 — Architecture: three tiers, on purpose

This is the part worth understanding, because the tiers answer different
questions and have opposite economics.

```
DOMAIN-*.md    14   hand-authored   "how does the execution kernel work"
                                    overlapping cover, declared by globs
                                    ★ diagrams live here and nowhere else
     │ members: globs resolve to files
     ▼
MOD-*.md       36   generated       "what is in backend/agents"
                                    a partition — one file, one module
     │ file list
     ▼
files/**.md   789   generated       "what does THIS file depend on"
```

### Why both DOMAIN and MOD exist

A **module is a folder**, derived by `pydeps` and `dependency-cruiser`. It is
free, it is a fact, and it can never be wrong. It also cannot answer "how does
the kernel work" — the kernel is a third of one directory, and "how a run
resumes" is spread across four.

A **domain is a system concern**, declared by hand. It is judgement, it costs a
model run to write, and it can be wrong.

They are also different **data structures**, which is the decisive reason
neither replaces the other:

| | MOD | DOMAIN |
|---|---|---|
| structure | partition — every file in exactly one | overlapping cover |
| membership | decided by directory | declared as globs |
| `models/run_event.py` | in `MOD-backend-app-models`, only | in durable-state **and** run-streaming |
| derived? | yes, always correct | no, needs maintaining |
| diagrams | **none, by design** | one `## Shape` + one `## In practice` |

`build_architecture.py` asserts the partition (`Files assigned: 789/789`) and
aborts if a file matches no module root. Domains are a cover, so a file
belonging to **no** domain is reported as a coverage gap, not an error.

### DOMAIN card shape

```markdown
---
id: DOMAIN-agent-runtime
type: architecture-domain
kind: state
title: Agent runtime — model selection and the deepagents adapter
members:                      ← DECLARED BY HAND. The only human-owned field.
- backend/app/agents/deep_agent_runner.py
- backend/agents/capabilities/runtimes/*.py
member_count: 9               ← resolved from the globs
modules_spanned: [...]
watched_files: 17             ← members ∪ files the prose names
code_signature: 4e0fc402e971  ← files + symbols + modules + external deps
symbols_signature: 8f50b7a15  ← files + symbols ONLY (computable without pydeps)
prose_signature: 4e0fc402e971 ← what the prose was written against
---

<!-- AUTO-GENERATED BELOW THIS LINE — regenerated by build_architecture.py -->
### Members (9 files across 2 modules)
### Imported by, from outside this domain (44)
### Imports, from outside this domain (11)
### External
<!-- /AUTO-GENERATED -->

## Purpose          what it owns, and where it ends
## Shape            the load-bearing fact + an 8–12 node flowchart  ← inlined into ARCHITECTURE.md
## In practice      a sequenceDiagram + a numbered end-to-end trace
## Why this shape   rationale, anchored in invariant IDs and CI gates
```

`## In practice` is the section that makes a card usable. It traces one journey
**from the true entry point** — the HTTP route and the frontend call that
issued it — through to what the caller gets back, naming real functions in real
call order. Its sequence diagram uses **no participant aliases** and labels
every arrow `file.py::symbol`, because an agent reading the raw markdown must
be able to grep any identifier straight to its definition.

### Diagrams live in exactly two places

`DOMAIN-*.md` and `ARCHITECTURE.md`. **MOD cards carry none** — they used to,
and 16 were stripped, because a MOD diagram and a DOMAIN diagram describe
overlapping code with nothing keeping them in sync, and MOD cards have no
`prose_signature` so theirs rotted invisibly.

Only the `## Shape` diagram is lifted into `ARCHITECTURE.md`; the detailed
`## In practice` trace stays in the card, so the overview stays readable beside
thirteen siblings.

**Never use a mermaid keyword as a node id** — `graph`, `flowchart`,
`subgraph`, `end`, `class`, `classDef`, `click`, `style`, `linkStyle`,
`direction`, `default`, `href`, `call`, `callback`. It is a parse error and the
card renders as a red box. The trap is that the natural id is often the
reserved one: `graph.py` invites `graph["graph.py"]`. Prefix it —
`artifact_graph["artifacts/graph.py"]`. `build_architecture.py` lints for this.

---

## Part 3 — How staleness is detected

Three hashes, each answering a different question.

| Field | Covers | Answers |
|---|---|---|
| `code_signature` | watched files + symbols + modules spanned + external deps | has anything under this card moved? |
| `symbols_signature` | watched files + symbols **only** | did anything a diagram could *draw* change? |
| `prose_signature` | — | which `code_signature` was the prose written against? |

**`prose_signature != code_signature` → the card is stale.**

`symbols_signature` exists because it is computable **from disk alone in
milliseconds** — no `pydeps`, no `dependency-cruiser`. That matters twice:

- `--needs-rebuild` only notices files *added or removed*, so an edited symbol
  never triggered the 40-second rebuild, so `code_signature` never moved, so a
  rename was never noticed. This closes that hole.
- It is the refresh **gate**: a reworded docstring moves no symbol and must not
  cost a model run. Without it, a comment edit re-authors a whole card — the
  fastest way to get a hook disabled.

### The watch set — how a file maps to a domain

Two independent routes, unioned:

```
members: globs in frontmatter    →  fnmatch against the 789 tracked files
prose naming file.py::symbol     →  basename match
                    ↓ union
                watch set
```

So `DOMAIN-agent-runtime` has **9 members but 17 watched files**. `engine.py`
is not a member — it belongs to the kernel — but the card describes it, so the
card is answerable for it. **A card declares what it is answerable for by
talking about it.**

If a basename is ambiguous (there are two `registry.py`), the reference is
**reported and dropped**, never guessed. Write more of the path to disambiguate:
`capabilities/registry.py::discover`.

### What it deliberately does NOT catch

A call rewired *inside* an existing function body. That needed call-graph
walking, which was built and then removed as over-precision: the response to
any trigger is "re-read the changed files and update the card", and a model
re-reads the whole file regardless. Fine detection only pays when the repair is
fine.

---

## Part 4 — The `/velocity` skill: seven verbs

```
status        what the knowledge base holds and what is stale (cheap, read-only)
analyze       find the root cause of a bug or symptom
fix           analyze, propose, and apply a fix
sync          reconcile the knowledge base with recent commits
prime         (re)build the compacted context pack
book-keeping  record a card or architecture update
diagrams      re-author stale DOMAIN cards and their diagrams
```

**These seven are the complete set. No others, no synonyms.** (`bookkeeping` is
a spelling of `book-keeping`, not an eighth verb.) An undocumented verb that
appears to work is worse than one that prints the menu, because it hides which
procedure actually ran.

Each verb is a file in `skills/velocity/`, which is the canonical copy;
`.claude/skills/velocity/` and `.kiro/skills/velocity/` are `rsync -a --delete`
mirrors. `cli.md` is the authority on tooling. Regenerating derived artifacts is
**not** a verb — it is the closing step of `sync`, `prime` and `book-keeping`.

`diagrams` is the manual fallback for the pre-commit hook, and it ships with the
prompt the hook itself uses — `skills/velocity/prompts/architecture-domain-update.md`.
One file, two access paths, so the manual and automatic routes cannot diverge.

---

## Part 5 — The scripts

All under `tools/knowledge/`. None of them run git; the user handles that.

| Script | Job |
|---|---|
| `build_architecture.py` | the big one — modules, domains, file cards, `ARCHITECTURE.md`, signatures, the refresh loop |
| `build_index.py` | `INDEX.md`, `state.yaml`, and the `## Related` block in every card |
| `build_context.py` | `CONTEXT.md`, the compacted context pack |
| `validate_links.py` | the validation stage: markdown links, card cross-refs, **and card filenames** |
| `status.py` | read-only freshness report |
| `rebuild_knowledge.py` | runs the stages in dependency order and asserts that order |
| `apply_summaries.py` | applies staged summary proposals |
| `normalize_card_ids.py` | a sanctioned one-time ID migration — not for fixing one card |

**Rebuild order is load-bearing** and `rebuild_knowledge.py` asserts it:

```
architecture  →  index  →  context  →  validate
```

Validate must be last, and after architecture — otherwise it validates a tree
that is about to change.

### `build_architecture.py` flags

| Flag | Cost | Does |
|---|---|---|
| *(none)* | ~40s | full rebuild: pydeps + dependency-cruiser, all cards, gallery, module map |
| `--needs-rebuild` | ~0.2s | exit 0 if no source file was added or removed. Lets a hook skip the 40s scan |
| `--affected [FILE…]` | ms | which DOMAIN cards a changeset touches. No args = staged files. Exit 1 if any |
| `--explain [CARD…] --since REV` | ms | **which symbols moved**, not just that a hash differs |
| `--stale-prose` | ms | cards whose prose is older than their code |
| `--refresh-affected [FILE…]` | minutes | the full loop: gate → headless claude → rebuild → gallery → stamp |
| `--stamp CARD` | ms | `prose_signature = code_signature`, after re-authoring |
| `--max-refresh N` | — | cap on cards re-authored in one run (default 3) |
| `--check` | ~40s | report only, write nothing |
| `--only MOD-x` | ~40s | restrict which files are *written*. Does **not** shorten the run |

`--explain` is the one to reach for when a hash mismatch is unexplained. It
diffs symbols against `HEAD` — the previous state is already in git, so nothing
extra is stored:

```
DOMAIN-order-storage   (2 watched files, vs HEAD)
  symbols_signature c5a7c99b7492 -> 5900eca056db
    + backend/app/core/config.py::lookup_config
    - backend/app/core/config.py::get_config
```

A `-` paired with a `+` in one file is a rename, and every place the prose names
the old symbol is now wrong.

### Two safety rules the code enforces

**Nothing overwrites prose it cannot regenerate.** `read_hand_authored()`
raises rather than returning the placeholder whenever it cannot confidently
locate the human-written section — damaged frontmatter, a missing closing `---`.
The file is skipped and reported, never rewritten.

**Only one `unlink()` exists**, and it only removes a per-file card whose source
is gone. It raises if the target is a `MOD-*.md` or `DOMAIN-*.md`, so a widened
glob can never delete hand-authored analysis.

### Idempotence

Every generator writes **only when substantive content differs**. Volatile
fields (`sync_commit`, `last_synced`, `generated_at`) are excluded from the
comparison, because they record when the scan ran rather than what it found.
Without that, all 800+ architecture files churned on every commit and the hooks
reported "files were modified" every time.

---

## Part 6 — The pre-commit hook

**One hook, three phases.** It logs every step, and `verbose: true` is set so
pre-commit shows that output even when the hook passes — by default it hides a
passing hook entirely, which would make the logging pointless.

```yaml
- id: knowledge
  name: knowledge base (architecture -> domains -> index)
  entry: python3 tools/knowledge/rebuild_knowledge.py --hook
  language: system
  always_run: true
  pass_filenames: false
  verbose: true
```

This was three hooks — `knowledge-architecture`, `knowledge-domains`,
`knowledge-sync`. They had to run in a fixed order, shared a `git add`, and each
printed its own unlabelled block, so a developer watching a commit saw three
disconnected stanzas with no way to tell which had done anything. The ordering
constraint also lived in YAML, where nothing enforced it, and getting it wrong
failed **intermittently**: a commit deleting a source file failed twice and
passed on the third attempt as the hooks converged.

Now the order, the logging and the exit code live in one place —
`rebuild_knowledge.py --hook` — which already owned the stage sequence and
asserts it.

### What you see on a commit

```
──────────────────────────────────────────────────────────────────
knowledge base — keeping .knowledge/ in step with this commit
──────────────────────────────────────────────────────────────────

[1/3] architecture
  architecture current: 789 source files, no additions or removals
  nothing added or removed — skipped the 40s scan

[2/3] domain cards
  14 domain card(s) known; 2 changed file(s) staged
  1 changed file(s) affect no domain card

[3/3] index, context, links
  index  (build_index.py)
  cards indexed: 482
  by_type: {'adr': 12, 'bug': 42, 'fix': 266, 'issue': 162} sum=482
  context  (build_context.py)
  validate  (validate_links.py)
  Total local links checked: 12451
  Resolved: 12451
  Broken: 0
──────────────────────────────────────────────────────────────────
knowledge base up to date; regenerated files staged into this commit
──────────────────────────────────────────────────────────────────
```

### Phase 1 — architecture

```
build_architecture.py --needs-rebuild   ~0.2s, a pure glob
   exit 0 → nothing added or removed, stop here
   exit 1 → build_architecture.py       ~40s, pydeps + dependency-cruiser
            git add .knowledge/architecture .knowledge/ARCHITECTURE.md
```

Two-step on purpose: the cheap glob decides whether the expensive extractor run
is warranted at all. **Cannot fail the commit** — a failed regeneration is
reported and the commit proceeds.

### Phase 2 — domain cards (the only phase that calls a model)

```
staged files
     ↓  file intersection: members globs ∪ files the prose names   ms
  candidate cards
     ↓  symbols_signature: stored vs live                          ms, DECIDES
  cards whose shape actually moved
     ↓  headless claude, incremental, one card at a time
  rebuild → re-inline diagrams into ARCHITECTURE.md → stamp
```

The symbol gate is what makes this affordable. A reworded docstring moves no
symbol, so it prints `unchanged shape, skipping` and no model runs. Without it a
comment edit would re-author a whole card — the fastest way to get a hook
disabled.

**It never blocks.** Every one of these exits 0 and prints a handoff:

- no `claude` on PATH (a teammate on another editor, or a GUI commit with a
  minimal PATH)
- a timeout
- a run that fails
- a run that exits 0 having written nothing — a session-limit refusal does
  exactly this, and one did, so `_validate_domain_card()` checks the artifact
  rather than the exit code
- more cards affected than `--max-refresh` (default 3) — `capabilities/registry.py`
  legitimately touches 11 of 14 domains, and eleven model runs inside a commit
  is not a side effect anyone should get by surprise

```
  These cards are now stale. To bring them up to date, run:

      /velocity diagrams DOMAIN-agent-runtime DOMAIN-workspace-isolation

  Your commit is NOT blocked.
```

### Phase 3 — index, context, links

```
rebuild_knowledge.py --skip-architecture     ~1.6s
   index → context → validate
   git add INDEX.md state.yaml CONTEXT.md cards/
```

**The only phase that can fail the commit**, and it should: `INDEX.md`,
`CONTEXT.md` and the `## Related` blocks are pure derivatives with exactly one
correct value, and a broken link means a card nobody will find. On failure:

```
──────────────────────────────────────────────────────────────────
COMMIT BLOCKED: a derived artifact could not be rebuilt.
Read the output above — a broken link or unparseable frontmatter
is a real failure, not churn. Re-running will not fix it.
──────────────────────────────────────────────────────────────────
```

### Why `always_run: true`

pre-commit passes a hook the files that **exist**. A commit whose only change is
a **deleted** card matches no `files:` pattern, so the hook is skipped —
precisely when the index most needs regenerating, because it still advertises a
card that is gone. That shipped a broken `INDEX.md` in commit `07394989`.

Everything the hook does is idempotent and writes only when content actually
differs, so running it on every commit costs almost nothing and cannot be
dodged.

### Opting out

```bash
SKIP=knowledge git commit -m "…"
```

One name now, where the old config needed three.

---

## Part 7 — Setup

```bash
pip install pre-commit
pre-commit install          # per clone — cloning installs nothing
```

Requirements for the architecture stage:

- **`pydeps`** importable by the interpreter the hook uses (Python import graph)
- **`dependency-cruiser`** — already a frontend devDependency (TS/JS graph)
- **`claude`** CLI — optional. Without it, phase 2 degrades to a handoff
  message pointing at `/velocity diagrams`. Nothing blocks.

**The interpreter trap:** a GUI-launched commit does not source a login shell,
so the hook inherits a minimal PATH and may get Xcode's `python3` instead of
yours — which cannot `import pydeps`. `build_architecture.py` resolves an
interpreter that can. The same minimal PATH is why `claude` may be missing from
a hook that works fine in your terminal.

**The hook is not CI.** It keeps derived artifacts in step with the commit that
changes them. It does not prove the tree is correct.

---

## Part 8 — The marker contract

Four generated regions. **Never hand-edit inside them** — the next run
overwrites your change.

| Marker | File | Holds |
|---|---|---|
| `<!-- AUTO-GENERATED BELOW THIS LINE` … `<!-- /AUTO-GENERATED -->` | every MOD / DOMAIN / file card | file lists, import rollups |
| `<!-- RELATED -->` … `<!-- /RELATED -->` | every card in `cards/` | the cross-reference graph |
| `<!-- DOMAIN-DIAGRAMS -->` … `<!-- /DOMAIN-DIAGRAMS -->` | `ARCHITECTURE.md` | every domain's `## Shape` diagram |
| `<!-- MODULE-MAP -->` … `<!-- /MODULE-MAP -->` | `ARCHITECTURE.md` | module tables and counts |

The generated block sits **above** the prose in architecture cards, and the
split is on the marker, never on `---` — `---` is also an ordinary horizontal
rule, and splitting on the first one silently truncated everything after it.

The module map is generated rather than written because it is pure derivation.
While hand-maintained it drifted to claiming "549 tracked source files" against
a real 789, and nobody noticed: a number in prose looks equally authoritative
whether or not it is true.

---

## Part 9 — `.planning/` is a read-only fallback

`.knowledge/` is the source of truth. `.planning/` is kept **only** for history
the cards do not carry — five legacy registers plus per-phase narrative.

- Look in `.knowledge/` first, always.
- **Never write to `.planning/`.** It is a frozen archive.
- If any part of an answer came from it, **say so** and name the file. The two
  can disagree, and `.planning/` is the older, unmaintained one.
- The registers are large — `grep` them, never read one whole.

---

## Part 10 — Typical workflows

**"Is anything stale?"**
```bash
python3 tools/knowledge/build_architecture.py --stale-prose
python3 tools/knowledge/status.py
```

**"I changed some code — what does it affect?"**
```bash
python3 tools/knowledge/build_architecture.py --affected
python3 tools/knowledge/build_architecture.py --explain     # which symbols moved
```

**"Bring the docs up to date."**
```
/velocity diagrams DOMAIN-agent-runtime
```
or let the hook do it on commit.

**"I added a new subsystem and want a domain for it."**
Write a `DOMAIN-<slug>.md` with `members:` globs and placeholder prose, then
`/velocity diagrams DOMAIN-<slug>`. Nothing else registers it — the glob
`DOMAIN-*.md` is the registry.

**"Verify everything."**
```bash
python3 tools/knowledge/rebuild_knowledge.py    # architecture → index → context → validate
```

---

## Known gaps

Recorded rather than hidden:

- **Ambiguous basenames go untracked.** Several cards name `registry.py` and
  friends; two files share that basename, so the reference is dropped from the
  watch set and those cards will not flag when that file changes. Fix by writing
  more of the path in the prose.
- **Domain coverage is partial** — 160 of 789 files are in a domain. Excluding
  tests that is ~37%. Uncovered: seven capability families, much of
  `backend/app/api`, and the frontend components.
- **A call rewired inside a function body** moves no symbol and is not detected.
- **`ARCHITECTURE.md`'s prose** — "What Velocity is", "Design seams" — carries no
  signature and is not tracked. Only the two generated regions are.
