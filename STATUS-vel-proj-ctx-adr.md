# STATUS — vel-proj-context-adr

Branch: `feat/project-architecture-adr`
Last updated: 2026-08-14

## What this branch is doing

Replacing `.knowledge/` + `.planning/` with a single `.searchable/` system:
Markdown cards (decisions + auto-generated architecture) indexed into a
Chroma vector store for semantic search, instead of two separate ad-hoc
folders with no unified index.

## Done

1. **Migration** — extracted 1500 cards total into `.searchable/cards/` and
   `.searchable/architecture/`:
   - 1 ADR, 42 bug, 377 fix, 161 issue, 23 phase, 282 requirement, 65 doc
     (decision cards)
   - 549 architecture cards (259 backend via `pydeps`, 290 frontend via
     `dependency-cruiser`), one per source file, verified 1:1 file mapping
   - Built `.searchable/build_index.py` → Chroma collection `knowledge_cards`
     (`.searchable/chroma.db`, gitignored — regenerate, don't commit)

2. **Gap found + fixed: architecture cards had no actual content.**
   Auto-generated cards were pure `pydeps`/`dependency-cruiser` import-graph
   dumps — what a file connects to, nothing about what it *is* or *why* it's
   shaped that way. Enriched the top 50 hub modules (ranked by import
   fan-in + fan-out) with a hand-authored `## Purpose` / `## Shape` /
   `## Why this shape` section, grounded in actually reading each source
   file — inserted above a `---` divider, auto-generated dependency data
   preserved below it untouched. `schema.md` documents the divider contract
   so a future regeneration script only replaces below the line.
   - **499 architecture cards remain dependency-only** (not enriched) —
     by design, per the schema.md policy: enrich lazily/on-demand going
     forward rather than all at once.

3. **Gap found + fixed: DB/card data-quality bugs.**
   - Chroma index was stale after the enrichment edits (built before, not
     after) — rebuilt via `build_index.py`.
   - 65 cards were mistagged `type: architecture` (that type is meant to be
     exclusive to the 549 auto-generated per-file cards) — they were
     actually pointer cards to `.planning/*` docs. Retyped to a new
     `type: doc`, documented in `schema.md`.
   - Those 65 pointer cards referenced `.planning/*` paths, which would
     have gone dead once `.planning/` is deleted. Copied the actual 65
     files/dirs (~1.35MB) into `.searchable/docs/`, repointed every card at
     the new self-contained location.
   - `manifest.json` corrected to match true counts (was previously
     internally inconsistent: `architecture: 614` vs. 549 actual files).

## Known, deliberately left alone

- **168 cards** (mostly fix/bug/issue cards) contain inline prose citations
  like *"investigation agent — read `.planning/IMPLEMENTATION-REGISTER.md`"*.
  These are audit-trail mentions, not structured pointer cards — left as-is.
  They'll read as unresolvable paths once `.planning/` is deleted, but are
  historical citations (like a commit hash), not live links. Not fixed yet
  — needs a decision (see Next steps).

## Next steps (open decisions, in rough priority order)

1. **168 dangling `.planning/` prose citations** — decide: leave as
   historical citations, or rewrite/migrate.
2. **`.knowledge/` + `.planning/` deletion** — `.searchable/` should now be
   safe to stand alone (pointer-card dependency on `.planning/` removed).
   Still needs a final review pass before deleting the old folders.
3. **Remaining 499 architecture cards** — currently dependency-only per
   design. Revisit if more than the top-50 hub modules turn out to need the
   Purpose/Shape/Why layer.
4. No regeneration script exists yet for architecture cards (the original
   `pydeps`/`dependency-cruiser` extraction was a one-time run, not saved
   as a reusable script) — `sync_commit`/`last_synced` fields will go stale
   as the codebase changes. Needs a real regen script if `.searchable/` is
   meant to stay current, respecting the Purpose/Shape preservation
   contract in `schema.md`.
