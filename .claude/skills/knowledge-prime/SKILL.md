---
name: knowledge-prime
description: "Load the project's rules and history index once per session, cheaply, from the pre-built card store (.knowledge/). Use at the start of any fix, feature, or review — and whenever you would otherwise reach for .planning/FIX-REGISTER.md, ISSUES-REGISTER.md or IMPLEMENTATION-REGISTER.md. Also use for 'has this broken before', 'what rule applies here', 'what do I need to know before touching this file'."
argument-hint: "[file path or topic]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# Knowledge Prime

## Objective

Hold the project's accumulated rules and history in context for **~12 K tokens**,
instead of the ~350 K it costs to read the registers. Same information reach,
about 3% of the price.

Three tiers, and only the third is ever read by default:

| Tier | Artifact | Size | Read? |
|---|---|---|---|
| `.planning/**` | all sources | ~18 MB | **Never** wholesale |
| `.knowledge/cards/*.md` | 532 cards, one flat folder | ~750 KB | Only via `--show` |
| `.knowledge/surface/index.json` | filterable entries + facets | ~200 KB | Only by tools |
| `.knowledge/surface/CATALOG.md` | bugs, tests, reqs, docs, tasks | ~32 KB | On demand |
| `surface/ARCHITECTURE.md` | current state — stage, boundaries, ADRs | ~4 KB | **Yes, first** |
| `INVARIANTS.md` + `surface/RULES.md` + `surface/INDEX.md` | the session prime | ~48 KB | **Yes** |

## Workflow

### 1. Check freshness first

```bash
python3 scripts/knowledge/check.py
```

Exit `0` clean · `1` warnings · `2` broken.

- **2 (broken)** — say so and stop. Do not fall back to reading a register whole;
  that is the exact cost this exists to avoid. Fix the store first.
- **1 (warnings)** — usable. Note which warning, because it changes what you can
  trust: unextracted register entries mean recent work is *missing* from the index,
  and a missing `files:` path means that card's claim can no longer be verified.
- **0** — proceed silently.

### 2. Read the prime

`Read` these four, in this order:

```
.knowledge/surface/ARCHITECTURE.md  # WHERE WE ARE — milestone, phase, boundaries, ADRs
.knowledge/INVARIANTS.md            # project-wide constraints — bind every phase
.knowledge/surface/RULES.md         # decisions in force — constrain what you may write
.knowledge/surface/INDEX.md         # one line per fix / issue / phase
```

`ARCHITECTURE.md` comes first because it is the only one about the **present**: the
milestone in flight, the phase position, the four boundaries `import-linter` enforces
in CI, the 18 registered workflows, and the ADRs in force. The other three are
history and constraints. Read it before proposing any plan — a plan that ignores the
open milestone is the expensive kind of wrong.

Do **not** read `.cache/*.json`, and do not read card bodies yet.

### 3. Query for the task at hand

```bash
python3 scripts/knowledge/ctx.py "<symptom words>"        # search
python3 scripts/knowledge/ctx.py --for <path>             # rules + history for a file
python3 scripts/knowledge/ctx.py --rules <area>           # rules in force for an area
python3 scripts/knowledge/ctx.py --show FIX-122           # open one card
```

Open **only** the cards that come back — typically two to four. If a phase card
matches, read its shard under `.planning/_register-parts/`, never the whole
implementation register.

Before editing a file, run `--for <path>`. That is the cheapest way to find the
rule you are about to break.

To filter rather than search, `.knowledge/surface/index.json` carries every entry
plus `facets` (type / status / area with counts), so a tool can offer filters
without scanning all 532 entries.

### 4. Report briefly

Five to ten lines, no more:
- the milestone and phase currently open, from `ARCHITECTURE.md`
- how many rules and cards are loaded
- anything the freshness check flagged, named explicitly
- the cards that matter for this task, and the rule that constrains it

Do not echo `INDEX.md` back at the user. They can read it; the point is that *you*
now hold it.

### 5. Once per session

If this skill already ran in this conversation, do **not** re-read the prime. Say
"already primed" and go straight to the question. Re-running `check.py` is free;
re-reading the prime is not.

## What the store is, and what it is not

- **It is** a map of what was decided, what broke before, and where. Use it to
  decide *what to read*, then read that.
- **It is not** evidence about current behaviour. Cards describe the code as it was
  when the entry was written. When a card and the source disagree, **the source
  wins** and the card is stale — say so.

Four specific limits — the last two are reported by `check.py`:

- **Issue cards have almost no `files:`.** The issues register has no files column,
  so only 2 of 49 issues are reachable by `--for <path>`. Search issues by text.
- **All of `.planning/` is carried (1064/1064 files), but at two depths.** Fixes,
  issues, decisions and phases are in `INDEX.md` — always loaded. Bugs, tests,
  requirements, documents and work folders are in `CATALOG.md` — **not** loaded by
  default, but fully searchable via `ctx.py`. If `INDEX.md` has no answer, search
  before concluding nothing exists.
- **Pointer cards do not contain their content.** `doc` and `task` cards carry a
  summary and a path; `.planning/phases/` alone is 13 MB and is never copied. Follow
  the `source:` path to read one.
- **Deleted paths.** Some cards name files that no longer exist —
  `backend/app/api/websocket.py` is referenced by seven fixes and is gone. Those
  cards are history, not guidance.
- **Reused ids.** The register reuses 14 ids for two unrelated fixes each. Those are
  split here into `FIX-007` / `FIX-007b`; the suffix exists only in the card store,
  so cite the `source:` anchor when writing back to the register.

## Never

- Never read `IMPLEMENTATION-REGISTER.md`, `FIX-REGISTER.md` or
  `ISSUES-REGISTER.md` in full. If the index cannot answer it, open the specific
  card, then the specific shard.
- Never write to `.planning/`. This skill is read-only.
