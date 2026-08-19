# velocity: prime

(Re)build `.knowledge/CONTEXT.md`, the compacted context pack used to orient
quickly without reading all ~469 cards. Cheap to call — the first step
short-circuits when nothing has changed.

Preconditions: `.knowledge/state.yaml`, `.knowledge/INDEX.md`,
`.knowledge/ARCHITECTURE.md` exist.

Leaves behind: `.knowledge/CONTEXT.md` (only if it was rebuilt).

## Procedure

1. Check freshness. If `.knowledge/CONTEXT.md` exists, read its frontmatter
   `built_from_commit`. Read `.knowledge/state.yaml`'s `last_sync_commit`.

   Those two agreeing proves only that CONTEXT.md matches the last SYNC —
   not that either matches reality. Both can be stale together, and then
   this check happily reports "current" while serving an out-of-date pack.
   So run the real check instead: **the status command** (`cli.md`).

   - Any row STALE → rebuild, regardless of what the two commits say.
   - **`ID scheme conformance` STALE → fix the IDs BEFORE rebuilding.**
     Section 3's "ID families" are derived by stripping the type code off
     each id, so a malformed id yields a malformed family: 359 doubled-prefix
     cards produce ~48 junk entries (`REQ-REQ-TEST(30)`, `REQ-REQ-RESUME(18)`)
     instead of collapsing into their real families. Rebuilding first bakes
     that noise into the very section meant to be a concise routing aid, and
     nothing downstream flags it. Run
     **the ID linter** (`cli.md`) first and report what it
     says; only rebuild once the row is clean, or say plainly in your report
     that section 3 is known-degraded and why.
   - All rows OK **and** the two commits agree → report "CONTEXT.md is
     current as of <commit>" and stop.

   `status.py` compares against HEAD and against the files actually on disk,
   which is what "fresh" has to mean. See `cli.md`.

2. Otherwise, rebuild `.knowledge/CONTEXT.md` from scratch with this
   frontmatter:
   ```yaml
   ---
   built_from_commit: <state.yaml.last_sync_commit>
   built_at: <today, ISO date>
   cards_indexed: <count of cards folded into section 2>
   modules_indexed: <count of modules folded into section 3>
   ---
   ```

3. Section 1 — "What Velocity is". Hand-authored constant in the script,
   condensed from `.knowledge/ARCHITECTURE.md`'s opening. Update it by hand
   only when that file's opening genuinely changes.

4. Section 2 — "Invariants and boundaries". Hand-authored constant, in
   three tiers: **Always** (the rules that hold everywhere — kernel stays
   workflow-agnostic, capabilities resolve through the registry, migrations
   additive only, real `deepagents` mandatory), **Ask first** (SC-001, the
   `Workspace`/`RuntimeEnvironment` port, enabling local exec), **Never**
   (edit below an architecture card's marker or hand-edit a generated file,
   renumber/reuse/delete a card ID, run any git write).

   This is the highest-value-per-token section: it is the non-obvious
   knowledge an agent cannot infer from reading code.

5. Section 3 — "Card store". Derived. A type/total/open table over the four
   live types (`adr`, `fix`, `issue`, `bug`), the `adr` cards listed
   individually because a decision record is load-bearing and there are few,
   and a pointer to `INDEX.md`. **Never list individual cards of any other
   type** — `INDEX.md` is one read away and holds all 469.

6. Section 4 — "Module map". Derived. One line per module:
   `- [<MOD-id>](architecture/<MOD-id>.md) — <path> — <N> files — <Purpose
   gloss>`. All 36 modules, always. This is the routing table and the point
   of the whole pack.

7. Section 5 — "Retrieval protocol". Hand-authored. It must open with the
   index-first rule and state it in the strongest terms:

   **NEVER read or grep `cards/*.md` or `architecture/*.md` in bulk.** Read
   `INDEX.md` first, match the query semantically against its one-line
   `compact_summary` entries, and open ONLY the handful of cards that
   matched. Same for architecture: pick the one module from the map, open
   only that card.

   This is the whole reason `compact_summary` was backfilled onto all 469
   cards — the index is designed to answer "which cards matter" without
   opening any of them. An agent that sweeps the directory defeats the
   design and blows out its own context window.

   Then the shorter notes: resolving a known card ID by glob, symptom ->
   module via `applies_to`, the divider contract, and IDs being permanent.

   Keep this minimal. The pack carries **state**; the skills carry
   **method**. Procedure duplicated here drifts out of sync with the skill
   files — that is exactly how the divider contract came to be documented
   backwards in an earlier build.

   **Do NOT add a code tree / directory overview.** It was removed
   deliberately: the ETH Zurich study found directory overviews do not
   accelerate file discovery and do increase wasted exploration, and the
   `git ls-files` version we shipped listed `scripts/knowledge/`, which is
   tracked in git but deleted from the working tree. The module map routes
   better. See `specs/013-cardex/reports/2026-08-16-context-pack-research.md`.

8. Budget: target **~3000 tokens (~12,000 chars)**. Treat 4000 tokens as the
   hard ceiling. The last build landed at 12,222 chars.

   CONTEXT.md is a NAVIGATION pack, not a data dump. It tells the reader what
   exists and where to look. It must never reproduce data that is one
   file-read away — `INDEX.md` already holds all 469 cards.

   Section allocation, from the last good build:

   | Section | chars |
   |---|---|
   | 1. What Velocity is | 1,200 |
   | 2. Invariants and boundaries | 1,150 |
   | 3. Card store | 1,000 |
   | 4. Module map | 7,550 |
   | 5. Navigating | 1,100 |

   Section 4 is ~62% of the pack and that is correct — the module map is the
   routing table, and it is the only section that scales with the
   architecture rather than with card volume.

   If a rebuild overruns: section 3 must never list individual cards (only
   `adr`, since there is one). Shorten section 4's Purpose gloss last, and
   never below 90 chars — at 40 it truncates mid-clause ("is a one-shot…")
   and becomes useless. Never sacrifice sections 1, 2 or 5.

9. Run **the cards-only rebuild** to do all of the above — you run it, not
   the user. `cli.md` in this directory holds every command by name. Use
   **the full rebuild** instead if module structure changed (a new package, a
   moved file); prefer the cards-only form when only cards changed,
   since the architecture stage rescans the whole codebase and takes ~1-2
   min. The mechanical sections are derived; only sections 1 and 5 are
   editorial template constants inside the script. Do not hand-write
   `CONTEXT.md` — it is rebuilt on every sync.
