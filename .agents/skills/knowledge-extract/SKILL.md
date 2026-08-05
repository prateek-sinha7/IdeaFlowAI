---
name: knowledge-extract
description: "Build or top up the .knowledge/ card store from the .planning/ registers. Use after new fixes land in FIX-REGISTER.md, when check.py reports unextracted entries, or to rebuild the store from scratch. Never modifies the registers."
argument-hint: "[fixes|issues|phases] [--only ID,ID] [--force]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
---

# Knowledge Extract

## Objective

Turn register entries into cards. **Mechanical, not interpretive** — every field is
derived from structure already present in the register. Nothing is invented; where
the register has no detail for an entry, the card says so rather than padding.

The registers are **read-only inputs**. This skill never writes to `.planning/`.

## Workflow

### 1. Find out what is missing

```bash
python3 scripts/knowledge/check.py
```

The `cards vs registers` line names the unextracted ids. That is the work-list.

### 2. Extract

`extract.py` covers the three registers. Everything else in `.planning/` — QA bug
logs, TEST-REGISTER, REQUIREMENTS, narrative docs, `quick/` and `phases/` work
folders — is handled by `migrate.py all`, which uses the same card format.

```bash
python3 scripts/knowledge/extract.py fixes                    # top up — skips existing
python3 scripts/knowledge/extract.py fixes --only FIX-158,FIX-159
python3 scripts/knowledge/extract.py issues
python3 scripts/knowledge/extract.py phases
python3 scripts/knowledge/migrate.py all       # bugs, tests, reqs, docs, tasks
```

Existing cards are **skipped** unless `--force`. That is deliberate: it makes
top-up the default and protects hand-refined summaries.

`--force` rebuilds everything from the register. It is safe *only* because
`.knowledge/overrides.json` is re-applied on top — see below.

### 3. Rebuild the index

```bash
python3 scripts/knowledge/build_index.py
python3 scripts/knowledge/check.py
```

### 4. Review the new summaries — the part that actually matters

The `summary:` line is the only thing `ctx.py` searches and the only thing an agent
sees before deciding whether to open a card. If retrieval is poor, **the summaries
are wrong** — fix them, not the search.

Read the new cards' summaries and check each one:

- **Symptom + cause, not a title.** "reconnect banner fires after cancel because
  React state lags the reader loop", not "fix reconnect bug".
- **The words someone would actually type.** The observable symptom ("yellow
  banner", "stop button dead") beats the internal identifier.
- **One sentence, ≤ 240 chars, never truncated mid-clause.**

To correct one, add it to `.knowledge/overrides.json`:

```json
{ "FIX-158": { "summary": "…", "area": ["sse"], "produces": ["ADR-0007"] } }
```

Overrides are re-applied after every extraction, so they survive `--force`. Keep the
file small — if you are overriding many cards, fix the extractor instead.

## Things this skill already handles, and must keep handling

- **Reused ids.** 14 ids in the register cover two unrelated fixes each. They are
  split into `FIX-007` / `FIX-007b`, each carrying `collision_of:` and pointing at
  the same `source:` anchor. Never merge them back — a card whose header describes
  one fix and whose body describes another is worse than no card.
- **Entries with no table row.** `FIX-128` and `FIX-129` exist only as detail
  sections. They are real fixes; their headers are derived from the section.
- **Partial paths.** The register abbreviates (`types/index.ts`). Paths whose first
  segment is not a real top-level directory are dropped, so the orphan report shows
  genuinely deleted files rather than parsing noise.

## Never

- Never edit a register to make extraction easier. If parsing fails, fix the parser
  and report the malformed entry.
- Never invent a `files:`, `date:` or cause that the register does not state.
- Never write an ADR here. Decisions come from `knowledge-consolidate`, with review.
