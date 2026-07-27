# Fix Plan — Prompt Improvement Track (`prototype-revision-agent`)

Companion to `PLAN.md` (the eval-first structural fix, still Phase 3 /
parked pending go-ahead). This document tracks the **separate, complementary**
prompt-tuning track: lowering the revision agent's own real-model miss rate,
measured via `./run-eval.sh benchmark s1|s2|example1|both|all [N]` (see
`README.md`).

**Relationship to the structural fix**: prompting reduces *how often* a miss
happens; it cannot *guarantee* zero misses (the model stays probabilistic),
and it can never flip the offline `test_scenarios.py` S1/S2 `xfail` markers
(those run against a scripted model, deaf to prompt changes). Whatever miss
rate survives prompt tuning still needs the Phase-3 downstream check to be
caught before reaching a user. These two tracks both matter and are tracked
separately; this file is the prompt-only track.

**Status of everything below: plan only.** No `AGENT.md` edit has been
applied yet, and no post-fix re-benchmark has been run. All pass rates below
are the pre-fix baseline.

---

## Track A — S2: routes-map not kept in sync

### Evidence

| Scenario | N | Pass rate | Failure signature |
|---|---|---|---|
| S1 (Save button actually wired) | 13 (single + `benchmark` runs across two sessions) | 13/13 (100%) | none observed |
| S2 (Reports page reachable from sidebar) | 10 (two separate `benchmark s2 5` samples) | 8/10 (80%) | **both** misses: `"no 'reports' entry in the routes map"` |

Command: `./run-eval.sh benchmark s1|s2 <N>` — real tokens, ~40–130K per
sample on this fixture (no outliers here, unlike Track B).

The same failure signature reproduced identically in two independent
sessions (`260727151520-live-s2-d2b9125a` matches the first session's miss
verbatim) — strong evidence this is a consistent, fixable pattern rather than
noise.

### Root cause

This fixture's router dispatches off `location.hash` directly — the `routes`
object literal is **not read by the dispatch logic**, it's a
source-of-truth/documentation artifact only. A passing run's own narration
confirms the model notices this: *"Wire it into the routes (though the
current router doesn't use an explicit routes map for routing, it just reads
the hash)."* On runs where the model treats "doesn't affect runtime
behavior" as "lower priority," it skips updating the `routes` map — which
the eval's checker (correctly, matching what `static_check` looks for in
production) still requires.

`AGENT.md` currently covers the routes-map requirement, but only in the
context of "if you add a navigating button/link" — it never states the map
must be kept in sync *independent of* whether the router's dispatch logic
actually reads it, and the "new page" pattern (section + routes entry + nav
link, all three) is implied across two bullets rather than stated as one
explicit checklist.

### Proposed `AGENT.md` changes (not applied)

Both go in the **"CRITICAL: make the change actually WORK"** section —
minimal, targeted, nothing touching the S1-side wiring guidance (already
100% across 13 live runs; don't disturb what works):

1. **Routes-map sync is unconditional.** Add: *"Update the `routes`
   map/object even if the router's dispatch logic doesn't read it directly —
   it is still checked as a source-of-truth artifact; an unsynced `routes`
   entry is treated as a real defect, not a cosmetic one."*

2. **Explicit 3-item "new reachable page" checklist.** Add: *"Adding a new
   page reachable from navigation requires ALL THREE, every time: (1) the
   `<section data-page="...">` with real content, (2) an entry in the
   `routes` map, (3) a nav link/button pointing at it. Before finishing,
   re-read the file and verify all three exist for every new page you
   added — treat a missing routes entry as a failure exactly like a missing
   section or a dead link."*

---

## Track B — example1: whole-document duplication

Wired into the eval suite as the `example1` live scenario (`live_driver.py`,
`./run-eval.sh live-example1` / `benchmark example1 [N]`). Real fixture: a
1,885-line "SAS Viya IAM" prototype where the ENTIRE document is duplicated
end-to-end (every `<section data-page="...">` appears twice, each copy
already holding real content); the user's actual complaint ("pages seem
blank, only menus show") is the symptom of a broken client-side page-switcher
picking the wrong copy, not literally empty markup. The checker
(`_example1_pages_have_real_content`) requires each of 5 known pages to
appear EXACTLY ONCE with substantive content.

### Evidence — 2 usable runs, both in `tests/evals/logs/`

(3 earlier runs — `live-example1-1d9b5271` (0 tool calls, pre-dates the
`error`-event fix), `live-example1-b0c55c92` (aborted mid-session, no
`output/`), `live-example1-a563082c` (AWS `AccessDeniedException`, infra
only) — carried no model-attempt signal and were deleted from `logs/` rather
than kept as dead weight.)

| Run | Outcome | Tool calls | Tokens (in/out) | What happened |
|---|---|---|---|---|
| `live-example1-1bac45b3` | MISS | 15 | 345,074 / 10,734 | Full root-cause writeup: `logs/live-example1-1bac45b3/report.md`. Model diagnosed correctly, `write_file` failed (create-only), pivoted to `edit_file`, but removed only the 2-line **seam** — the ~900-line duplicate body was never touched. Verification only re-read near the boundary. False "all 5 pages fixed" summary reported. |
| `260727144722-live-example1-5bb95f21` | MISS | 87 | 8,113,113 / 35,217 | Same `write_file`-fails-then-`edit_file` opening (call #24). This time the model *did* grind through the duplicate body — 18 large `edit_file` calls (old_string 2,000–8,000 chars each) interleaved with small seam cleanups — and got 4 of 5 pages clean. Still finished with `audit` duplicated, declared victory ("PERFECT!!! The file is FINALLY completely clean"), and spent **8.1M input tokens** doing it. |

No new runs since these two — this remains the current evidence, not
refreshed by re-running anything.

Two independently-reproduced, non-infra failures (`1bac45b3`, `5bb95f21`) —
different exact shape each time (one under-edits and declares success early,
the other over-iterates, still misses one page, and is enormously expensive)
— but they share the same two root causes.

### Root cause 1 — `write_file`'s create-only failure recurs every run

Confirmed in **both** real runs (`1bac45b3` call #9, `5bb95f21` call #24):
the model's first instinct for "the whole file is wrong" is `write_file`
with a clean rewrite. It always fails — `deepagents`' `FilesystemBackend`
refuses to overwrite an existing file (confirmed from the installed library
source, not inferred) — and the model has to rediscover this by trial and
error, every single time, before falling back to `edit_file`. This is a pure
prompt gap: `AGENT.md` currently *recommends* `write_file` for exactly this
case ("sweeping changes where editing piece-by-piece would be harder")
without mentioning it will not work on an existing file.

### Root cause 2 — `edit_file`'s exact-match contract forces an inefficient, error-prone removal strategy

Because `edit_file` requires `old_string` to literally contain the text
being removed, deleting a ~1,700-line duplicate block means either (a) one
`edit_file` call whose `old_string` is the entire duplicate block verbatim,
or (b) many sequential calls chipping away at it. Neither run did (a)
cleanly:

- `1bac45b3` did the smallest possible edit (the 2-line seam) and then
  **stopped**, verifying only the boundary — under-editing.
- `5bb95f21` iterated through ~18 large removal edits, each preceded by a
  fresh read to find the next matchable chunk — this is what drove the
  token cost to 8.1M (repeated large reads + large edit payloads, each
  echoed back in the tool result) — and it *still* finished with one page
  (`audit`) not fully deduplicated, because the incremental, boundary-by-
  boundary approach has no built-in way to confirm total coverage.

The common failure mode across both: the model's own narration ("PERFECT!!!
completely clean", "all 5 pages fixed") is driven by how the *edit progress
felt*, not by a structural check against the fixture's actual invariant
(each `data-page` id appears exactly once) — the same "confident narration ≠
correctness" pattern as Track A, manifesting on a much larger, more
expensive defect shape.

### Proposed `AGENT.md` changes (not applied)

All three are targeted additions to the existing **"CRITICAL: make the
change actually WORK"** / tool-description sections — no rewrite:

1. **Document `write_file`'s create-only behavior explicitly**, next to its
   current description: *"`write_file` FAILS if the file already exists — it
   will NOT overwrite `prototype.html`, which always already exists in a
   revision run. Never attempt `write_file` on it; use `edit_file`
   instead."* Removes the wasted turn (and the model's own confusion) that
   happened identically in both real runs.

2. **Give explicit strategy for whole-document duplication specifically**
   (the defect shape behind both misses): *"If you find the document is
   duplicated end-to-end (check: does the file contain more than one
   `<!doctype html>` / `<html lang=` / opening `<body>`?), do not remove it
   in many small incremental edits — that is slow, expensive, and easy to
   leave partially done. Instead: read the full file once, identify the
   exact point where the legitimate document ends and the duplicate begins,
   and remove the ENTIRE duplicate span in a single `edit_file` call (verbatim
   `old_string` copied from what you just read, `new_string` empty)."*

3. **Replace the boundary-only verification with a structural count check**:
   *"Before declaring a duplication fix complete, grep/search the file for
   `data-page="` and confirm each page id you expect appears exactly once.
   A file that 'ends cleanly' or 'looks right near the edit site' is NOT
   sufficient evidence — duplicate content earlier or later in a
   multi-thousand-line file will not show up in a boundary-only re-read."*
   A stronger, cheaper version of `report.md`'s original verification
   recommendation (broad re-read) — a targeted grep for the exact invariant
   the checker itself enforces, rather than "read more."

---

## Verification plan (not yet run — costs real tokens)

Both tracks touch the same file (`agents/prompts/prototype-revision-agent/AGENT.md`),
so apply and verify together:

1. Apply all 5 additions above (2 from Track A, 3 from Track B).
2. Re-run `./run-eval.sh live-example1` a few single-shot times first (cheap
   sanity check that the model's opening move changes — no more `write_file`
   failure), then `./run-eval.sh benchmark example1 5` for a real pass-rate
   read. Budget for materially lower cost per run if fix B-2 lands (no more
   8M-token outliers) but still expect this to remain the most expensive
   scenario in the suite by far.
3. `./run-eval.sh benchmark s2 10` (match/exceed the N=10 combined baseline)
   — compare against the 8/10 (80%) baseline.
4. `./run-eval.sh benchmark s1 5` — confirm no regression (shared prompt
   sections).
5. Record before/after pass rate + token cost in this file once run.
6. Confirm the offline suite (`./run-eval.sh`) is unaffected — it's
   prompt-blind by design (scripted model), so this should be a no-op check,
   not a real gate on this change.

**Waiting on go-ahead before spending tokens on step 2 onward.**
