# velocity: book-keeping

Record the work so the next session doesn't re-investigate.

Called at the end of `analyze` and `fix`, and directly when the user wants
something recorded. Diagnosis, fixing and testing are NOT in scope here —
this starts the moment the code is green and ends when every record is
consistent.

**Why this exists.** The registers are the reason a diagnosis is ever cheap.
When a defect is recorded with its root cause and `file:line`, the next
session reads a card instead of spending hours re-deriving it. An
unregistered fix silently converts future work into re-investigation.

Preconditions: the work is code-complete and its tests are green (or
explicitly N/A with a reason).

Leaves behind: a card in `.knowledge/cards/`, a regenerated `INDEX.md` +
`state.yaml`, and optionally an edited `architecture/MOD-*.md`.

> **Legacy check — do this first.** If `legacy-registrars.md` exists in this
> skill directory, read its §3a now: `.planning/` holds IDs that appear
> nowhere else, so it adds two READ sources to Step 1's ID allocation and one
> row to the Step 5 gate. That is its entire effect on this procedure.
> **It adds no write step.** `.planning/` is a frozen archive — the card is
> the record, and no register row is ever appended. If that file is not there,
> the cut-over is done and you can ignore any mention of registers you find
> elsewhere.

## Step 0 — Local facts (verified 2026-08-16; re-verify, don't trust)

| Claim you may have seen | Reality here | Check with |
|---|---|---|
| `uv run --no-sync pytest` | `backend/.venv` does NOT exist. `uv run --no-sync` does not fail loudly — it creates an empty CPython venv, skips the dependency install, dies on the first import, and leaves a stray venv shadowing the working interpreter. Use `python3.11 -m pytest` from `backend/`. | `ls -d backend/.venv` |
| `lint-imports` figures | Must be run from `backend/` — its config lives in `backend/pyproject.toml`. From the repo root it prints "Could not read any configuration" and exits, which LOOKS like a pass. Re-measure. | `cd backend && /opt/homebrew/bin/lint-imports` |
| Migration head `0026` | **`0030`** (`0030_workflow_runs_user_created_index.py`) | `ls backend/alembic/versions/ \| sort \| tail -1` |
| "Goldens are clean" | Not stable. A red golden is NOT automatically your regression — re-measure at the pre-change commit and compare failing ids. | re-run at the pre-change commit |
| Playwright live on `:8002` | backend runs on **`:8010`** locally | `lsof -nP -iTCP:8010 -sTCP:LISTEN` |
| where cards live | `.knowledge/cards/{YYYYMMDD}[-{HHMM}]-{ID}.md`; the index is `.knowledge/INDEX.md`. Generators are in `tools/`, not `scripts/`. | `ls .knowledge/` |

Full `pytest` hangs offline (Chromium/Bedrock/Postgres-gated). Always use
targeted selections.

## Step 1 — Allocate the ID (the collision trap)

Do NOT take "highest card + 1". IDs get burned in commit messages before any
card is written, so **the card store lags reality**.

Take the max across **every source**, not just the obvious one:

```sh
# FIX — card store, then both git passes
grep -oE "FIX-[0-9]+" .knowledge/INDEX.md       | sed 's/FIX-//' | sort -n | tail -1
git log --all --oneline | grep -oE "FIX-[0-9]+" | sed 's/FIX-//' | sort -n | tail -1
# origin/dev may not exist (fresh clone, worktree, no remote). Check FIRST --
# a raw `git log origin/dev` failure prints to stderr, does NOT match the
# grep, and so returns empty: a broken command is indistinguishable from
# "no IDs found", which silently under-counts and hands you a COLLIDING id.
git rev-parse --verify -q origin/dev >/dev/null \
  && git log --oneline origin/dev -60 | grep -oE "FIX-[0-9]+" | sed 's/FIX-//' | sort -n | tail -1 \
  || echo "origin/dev does not resolve here — skipping this source (say so in your report)"

# ISS
ls .knowledge/cards/*-ISS-*.md | grep -oE 'ISS-[0-9]+' | sed 's/ISS-//' | sort -n | tail -1
git log --all --oneline | grep -oE "ISS-[0-9]+"    | sed 's/ISS-//' | sort -n | tail -1

# TEST — same sources
```

**Next ID = max across all of them, plus 1.** Use `git log --all`, not just
the current branch — an id can be burned on a branch you are not on. Do NOT
fill gaps: if 055 is free between used ids, filling it makes the series
unreadable. Take the next id above everything.

Match the ID as a whole word (`\bFIX-25\b`) so `FIX-25` never matches
`FIX-250`.

If `legacy-registrars.md` is present, it adds further sources here — see its
§3a. Otherwise the sources above are complete.

### Picking the prefix

The prefix is a **domain family, not the uppercase type name**. There is no
`REQUIREMENT-` card in the corpus.

| type | prefixes in use |
|---|---|
| `adr` | `ADR` — technical decisions. None exist yet; you may be writing the first. |
| `bug` | `BUG` (also `CWF`, `DEF`) |
| `fix` | `FIX` |
| `issue` | `ISS` |

**These four are the whole schema.** `requirement`, `phase` and `doc` are
retired — do not create one. `QUICK`/`PH` prefixes are retired with them: a
quick task or phase that is worth recording gets a normal `fix` card written
by hand, never an auto-imported pointer.

Match the padding the family already uses — `FIX-258` (3 digits), `ISS-147`
(3 digits), `ADR-0001` (4 digits). Do not impose a different width on a family
that already has one.

Derive `kind` from `type`: `adr` is `state`; `fix`, `bug` and `issue` are
`event`.

## Step 2 — Write the test-coverage block

Produce this verbatim. It is pasted into the card body, and the card is the
only place these counts live. **Every number must come from a run you actually
observed.**

```
TEST COVERAGE — FIX-<NNN>
Unit tests:        <N> in backend/tests/<path>            → ALL GREEN
Integration tests: <N> in backend/tests/integration/...   → ALL GREEN (or N/A + why)
Frontend tests:    <N> in frontend/src/...                → ALL GREEN (or N/A + why)
Goldens:           <N> failed / <N> passed — IDENTICAL to the pre-change commit <sha>
lint-imports:      <N> kept / <N> broken — IDENTICAL to <sha>
Regression guards:
  - <test name>: <what it proves>
```

Baseline honestly. If a suite is red, re-measure it at the pre-change commit
(a detached worktree is the cheapest way) and record both numbers with the
SHA. **"Pre-existing" is a claim that needs evidence, not a label.**

If the user runs the tests rather than you, record what they reported and
say so — do not present their numbers as your own observation.

## Step 3 — Record every deferred finding as its own card

Anything found-but-NOT-fixed gets its own `issue` card in the same pass, with
`status: open` and a `[[wikilink]]` from the card describing the work it came
out of.

A finding that lives only in a session transcript is a finding you will pay
to rediscover. This is the step people skip, and skipping it is why the same
defect gets investigated twice.

## Step 4 — Build the knowledge card

1. Write `.knowledge/cards/{YYYYMMDD}-{HHMM}-{ID}.md` using the template
   (you are authoring now, so you HAVE a real time -- always include HHMM;
   the date-only form exists only for migrated cards whose authoring time
   was unrecoverable, never for a new card)
   below. Paste the Step 2 coverage block into the body.
2. Fill `applies_to` accurately — only the phases/modules/globs/requirements
   genuinely touched, derived from files you actually read or changed. Module
   ids come from `.knowledge/architecture/modules.json`.
3. Declare cross-references in the `## Related` block, which sits in the
   BODY directly under the frontmatter — **not** in frontmatter, where
   nothing reads them and the graph would be silently lost:

   ```markdown
   <!-- RELATED -->

   ## Related

   **Depends on:** [FIX-034](20260704-1815-FIX-034.md)

   **Referenced by:** [ISS-030](20260704-1046-ISS-030.md)

   <!-- /RELATED -->
   ```

   You may write a bare id (`**Depends on:** FIX-034`) and let the rebuild
   render the link — it resolves the id to the current filename. Also add the
   reciprocal entry to the `**Referenced by:**` line of every card you point
   at; nothing infers the reverse edge for you.
4. Regenerate the derived artifacts by running **the cards-only rebuild**
   (`cli.md` in this directory holds every command by name — you run it, not
   the user). Use **the full rebuild** instead if the change also moved
   module structure. Never
   hand-append a line to `INDEX.md` — it is derived over ~469 cards and a
   hand-placed line is silently dropped on the next regeneration.

### If the module's shape changed

Edit ONLY the three hand-authored sections (`## Purpose`, `## Shape`,
`## Why this shape`) in `.knowledge/architecture/MOD-<slug>.md`. They sit
above the line beginning `<!-- AUTO-GENERATED BELOW THIS LINE` (match the
prefix — the line continues with a regeneration note). Everything from that
marker down — and the frontmatter — is rewritten by
**the architecture rebuild** (`cli.md`; `--only <MOD-id>` scopes it), so
hand-edits there are lost. Keep prose edits surgical: change only what is now
inaccurate.

### Other parts have their own skills — use them

- Context pack rebuild -> `prime.md`. Do not hand-write `CONTEXT.md`.
- Root-cause investigation -> `analyze.md`. Do not re-derive it here.
- Applying a fix + blast radius -> `fix.md`.

## Step 5 — Closing gate

Every line must be ticked from something you ran or read, not assumed:

- [ ] ID allocated from the max across card store + `git log --all` + `origin/dev`
- [ ] Every deferred/unfixed finding has its own `issue` card
- [ ] `compact_summary` written, and it does NOT restate the title
- [ ] `author` set to your git identity
- [ ] **the cards-only rebuild** run (`cli.md`).
      **A non-zero exit does not by itself fail this item.** The `validate`
      stage runs last, after `index` and `context` have already written, and
      it fails on ANY broken link in `.knowledge/` — including ones that
      predate your card. What matters is whether YOUR card landed. Check the
      reported links: if none name your card or the docs it points at, the
      item is satisfied — note the pre-existing breakages in your report and
      move on. If any broken link is yours, fix it and re-run.
- [ ] The card resolves: `ls .knowledge/cards/*-<ID>.md` returns exactly one file
- [ ] `grep -c "<ID>" .knowledge/INDEX.md` returns 1
- [ ] **Findable by symptom**: `grep -i "<symptom in the user's own words>" .knowledge/INDEX.md` returns the new card's line
- [ ] Goldens + lint-imports recorded with the baseline SHA they were compared against

The findability check is the real test, and note it runs against `INDEX.md`,
not the card files — that is the retrieval path a future agent will actually
use, and the whole point of `compact_summary`. If your card is not findable
from its one index line, the summary is wrong; fix the summary, not the
search. Someone looking for this later knows the symptom, not the ID.

If `legacy-registrars.md` is present, add its §3c row to this gate.

## Git

Do NOT run `git commit`, `git add`, `git push`, or any branch operation. The
user handles all git themselves, including how docs and code are split across
commits. Report what changed and leave it staged-free.

## Card frontmatter template

```yaml
---
id: <PREFIX>-<NNN>            # e.g. FIX-258 — permanent, never reused or renumbered
type: fix|bug|issue|adr
kind: state|event
title: <short human-readable title>
status: active                # active|closed|resolved|superseded|done, per type conventions
applies_to:
  phases: []                  # phase ids this card is scoped to
  modules: []                 # module ids from architecture/modules.json
  globs: []                   # file globs this card's claims cover
  requirements: []            # requirement card ids this satisfies/relates to
locked_constraints: []        # invariants this card asserts must hold
verification:                 # always an object, never null — every card uses this shape
  type: test                  # test|manual
  status: pending             # pending|passed|failed|optional
  test_files: []              # the tests that prove this card's claim
compact_summary: '<one sentence, 20-200 chars — ALWAYS single-quoted, see below>'
last_updated: <YYYY-MM-DD>
author: '<Name> <<email>>'   # see the note below — do NOT invent an address
---

<body: what happened, root cause with file:line, the Step 2 coverage block,
[[wikilinks]] to related cards>
```

## Filling `author`

```sh
git config user.name; git config user.email
```

Either can be unset — a fresh checkout, a CI box, a container. `git config`
prints nothing, which yields a malformed `author: 'Name <>'`. Judge it by the
OUTPUT being empty, not by the exit code — an unset key exits 1, but a key
that is present and set to an empty string also prints nothing and exits 0.

If the email is missing, **ask the user for it. Never invent an address**, and
never leave the brackets empty: `author` is provenance, and a fabricated or
blank one is worse than a delayed card. If the user is unavailable, set
`author: 'unknown'` and say so in your report — `unknown` is an honest value
the corpus already uses (see `author_source`), a guessed address is not.

## Writing `compact_summary`

This is the line `INDEX.md` and the context pack show. It is what someone
scans to decide whether to open the card, so it does the retrieval work.

- **Always wrap the value in single quotes.** `compact_summary: 'text here'`.
  An unquoted summary containing a colon-space (`id: X`, `cause: Y`) is read
  by YAML as a nested mapping and `build_index.py` dies with a raw
  `yaml.scanner.ScannerError`, aborting the whole rebuild. A colon is a
  natural thing to write in a summary, so quote unconditionally rather than
  deciding case by case. Inside single quotes, escape a literal apostrophe by
  doubling it: `wasn''t`.
- One sentence, 20-200 characters, no newlines.
- **Must not restate the title** — the title is already displayed beside it.
  If the title states the symptom, the summary carries the ROOT CAUSE, the
  RESOLUTION, or the MECHANISM.
- Never open with "This card…", "This fix…", "A requirement that…".
- By type: `fix`/`bug` — what was actually wrong and what changed.
  `issue` — what is broken plus its disposition. `adr` — the decision and what
  it locks in.
- Name real symbols, files and tables. Banned filler: "improves",
  "enhances", "various", "several issues", "better handling".

All 469 existing cards follow this. `tools/knowledge/apply_summaries.py` can apply
staged batches and validates length, type and opening phrasing.

## Corrections

Never rewrite an existing card's meaning in place. If a prior card's
conclusion is wrong or superseded, write a NEW card describing the
correction, set the old card's `status` to `superseded`, and link the new
card to it from the `**Depends on:**` line of its `## Related` block.

## Anti-patterns

- **Registering before green.** A row claiming tests pass, written before
  they ran.
- **"Pre-existing" without a SHA.** Re-baseline at the pre-change commit or
  don't claim it.
- **Prose in the register.** The register grows by one row; detail belongs
  in the card.
- **Silent deferrals.** Found-but-not-fixed with no `ISS-NNN` is how
  defects get rediscovered.
- **Copying a stale command.** This repo has no venv and no
  `scripts/knowledge/`. Check Step 0.
- **Hand-editing a derived file.** `INDEX.md`, `state.yaml`, `modules.json`,
  and everything below an architecture card's divider are generated.
