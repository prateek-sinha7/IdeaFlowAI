# 014 — Dispatch guide: which agent, what to tell it, in what order

A reference for driving `tasks.md` by hand via the Agent tool — no automation runs on its own
(a separate `workflow.js` exists for automated execution; this guide is for manual dispatch,
same as `015-frontend-routing/dispatch-guide.md`). Each entry below tells you (or me, when you
say "go") which `subagent_type` to use, which `model`, and the exact dispatch prompt. Agents
read `tasks.md` themselves for the full spec (file path, description, acceptance criteria) —
this guide never duplicates that text, only tells you how to invoke it, so there is one source
of truth, not two drifting copies.

**Model note**: `tasks.md` labels most tasks `[sonnet]` (all of Phase 3 without exception, per
RISK-02) and every validator `[sonnet]`. This overrides the standing haiku-only subagent rule
in `~/.claude/CLAUDE.md` §7 — an explicit, scoped exception added to that file for exactly this
case (a task list that pre-classifies which items need Sonnet-level judgment). Pass `model`
exactly as shown below.

**Agent type note**: same three project-local roles as 015 — `junior-engineer` (haiku,
mechanical/fully-specified tasks), `senior-engineer` (sonnet, multi-file/judgment tasks), and
`qa-engineer` (haiku by default, has no Write/Edit tool access — it can only judge, never fix).
Validators use `qa-engineer` with an explicit `model: sonnet` override: `tasks.md`
pre-classifies all 6 validators as needing sonnet-level judgment, which is exactly the case the
CLAUDE.md exception clause covers.

**Highest-risk phase note**: Phase 3 (T12–T26 + V3) is the dispatch-loop conversion in
`engine.py` — plan.md's RISK-02 calls it the single highest-risk code change in this spec. Every
task in it is `senior-engineer`/`sonnet`, no exceptions, regardless of how small an individual
task looks. Don't downgrade any Phase 3 task to `junior-engineer` even if it reads as mechanical
in isolation — the risk is in the file, not the diff size.

---

## The sequencing (same structure as `tasks.md`'s graphs, restated as a dispatch order)

```
Front A — Compiler (T1∥T2 → T3 → T4∥T5 → T6) → V1 ┐
Front B — Context  (T7∥T11 → T8∥T9 → T10)    → V2 │  A and B are FULLY independent —
                                                    │  dispatch both fronts' first waves
                                                    │  in ONE message at hour zero
Front C — Frontend types (T34, after V1 only) ─────┘

  V1 + V2 both done
    → Phase 3 (T12∥T16∥T17∥T20 → T13∥T15 → T14∥T19∥T21 → T18 → T22 HARD GATE
               → T23∥T24∥T25∥T26) → V3 — HARD GATE, nothing below starts until this passes
        → Phase 4 (T27∥T30 → T28∥T31 → T29 → T32∥T33) → V4
            → (Front C continues) V5 → T35∥T36 → V6
              → Ledger sync (one agent, updates tasks.md — must run alone, last)
```

**Parallel dispatch = one message, multiple `Agent` tool-use blocks.** Sequential = wait for the
result before sending the next. Everything marked `∥` above can go in the same message.

**Two genuinely independent fronts at hour zero**: unlike 015 (which has one linear Foundation →
Core Routing chain before anything forks), 014's Phase 1 (compiler) and Phase 2 (context) touch
disjoint files and share no dependency — `tasks.md`'s cross-phase schedule calls this out
explicitly. Open both in the same first message rather than finishing Phase 1 before starting
Phase 2.

---

## Front A — Compiler (Phase 1, T1–T6 → V1)

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T1 | `junior-engineer` | `haiku` | Parallel with T2 — different file (`plan.py`) |
| T2 | `junior-engineer` | `haiku` | Parallel with T1 — different file (`compiler.py`) |
| T3 | `senior-engineer` | `sonnet` | After T1 AND T2 both done |
| T4 | `senior-engineer` | `sonnet` | After T3 — parallel with T5 possible (different functions, same file: `compiler.py`); serialize if you'd rather avoid any merge risk |
| T5 | `senior-engineer` | `sonnet` | After T3 — parallel with T4, same caveat |
| T6 | `senior-engineer` | `sonnet` | After T5 (extends T5's function) — T4 can already be done by this point |

Dispatch prompt pattern for each: *"Execute task T\<N\> from `specs/014-conditional-gates/tasks.md`.
Read that file's task-list entry for T\<N\> for the full file path, description, and any prior
tasks it builds on. Also read `specs/014-conditional-gates/contracts/manifest-route-schema.md`,
which the compiler work (T1–T6) is built from. Report back exactly what you changed, in which
file(s), and confirm any acceptance criteria the task entry names."*

**Then V1** — see [Validators](#validators) below, guarding T1–T6.

---

## Front B — Context (Phase 2, T7–T11 → V2)

**Dispatch T7 and T11 in the SAME message as Front A's T1/T2** — T11 has zero dependencies
(`tasks.md` calls it "the single most schedulable task in the whole plan") and T7 only needs a
different file (`context.py`) to be free, which it always is at hour zero.

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T7 | `junior-engineer` | `haiku` | Parallel with T11 — different concerns entirely |
| T11 | `senior-engineer` | `sonnet` | Parallel with T7 — pure read-and-report against `kernel_services.py`, no code dependency on anything |
| T8 | `junior-engineer` | `haiku` | After T7 — parallel with T9 |
| T9 | `senior-engineer` | `sonnet` | After T7 — parallel with T8, different concern (design note vs. test file) |
| T10 | `junior-engineer` | `haiku` | After T9 (needs its propagation design settled) |

Dispatch prompt pattern: *"Execute task T\<N\> from `specs/014-conditional-gates/tasks.md`. Read
that file's task-list entry for T\<N\> for the full spec. If the entry references a prior task's
output (e.g. T9's propagation design, T11's UNKNOWN-2 verdict), that prior task has already
completed — read its report if you need the specifics, don't re-derive it. Report back exactly
what you changed/found and confirm any acceptance criteria named."*

**Then V2** — guards T7–T11. V1 and V2 can run in parallel with each other (different files,
independent groups) — dispatch both once their respective fronts finish.

---

## Phase 3 — Dispatch loop conversion (T12–T26 → V3) — HARD GATE, everyone waits here

**Do not dispatch anything in this phase until BOTH V1 and V2 have passed.** Everything after
V3 (Phase 4, and Front C's remaining tasks) waits on V3, not just on this phase's own tasks —
`tasks.md` is explicit that this is the highest-risk phase and nothing proceeds past a red T22.

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T12 | `senior-engineer` | `sonnet` | Parallel with T16, T17, T20 — four independent roots, dispatch together in one message |
| T16 | `senior-engineer` | `sonnet` | Parallel with T12, T17, T20 — `gates/base.py`, untouched by anything else in this wave |
| T17 | `junior-engineer` | `haiku` | Parallel with T12, T16, T20 — `registry.py` + `gates/__init__.py` |
| T20 | `senior-engineer` | `sonnet` | Parallel with T12, T16, T17 — a different method (`_deliverable_filename_override`) from the dispatch loop entirely; only needs Front A's T6 |
| T13 | `senior-engineer` | `sonnet` | After T12 — parallel with T15 |
| T15 | `senior-engineer` | `sonnet` | After T16 AND T17 — parallel with T13, different file (new `conditional.py`) |
| T14 | `senior-engineer` | `sonnet` | After T13 AND T15 — parallel with T19, T21 (same file `engine.py`, different regions; serialize if you'd rather avoid merge risk) |
| T19 | `senior-engineer` | `sonnet` | After T13 — parallel with T14, T21 |
| T21 | `senior-engineer` | `sonnet` | After T13 — parallel with T14, T19 |
| T18 | `senior-engineer` | `sonnet` | After T14 (needs its arm to exist before adding the cap check) |
| **T22** | `senior-engineer` | `sonnet` | **HARD GATE** — after every task above (T13, T14, T15, T18, T19, T20, T21). Nothing in this phase proceeds past a red T22. |
| T23 | `senior-engineer` | `sonnet` | After T22 — parallel with T24, T25, T26 |
| T24 | `senior-engineer` | `sonnet` | After T22 — parallel with T23, T25, T26 |
| T25 | `senior-engineer` | `sonnet` | After T22 — parallel with T23, T24, T26 |
| T26 | `senior-engineer` | `sonnet` | After T22 — parallel with T23, T24, T25 |

Dispatch prompt pattern: *"Execute task T\<N\> from `specs/014-conditional-gates/tasks.md`. Read
that file's task-list entry for T\<N\> in full — this is Phase 3, the highest-risk phase in this
spec (RISK-02), so read the whole entry carefully, including any line-number caveats about
searching for the actual current location rather than trusting a cited line. If the entry
references a prior task's output (e.g. T14's stub for T15's gate class, T13's characterization
result), that prior task has already completed — read its report for specifics. Report back the
exact diff you made and confirm any acceptance criteria named, including running any
characterization/verification command the entry names."*

**T22 gets its own explicit prompt**, since it's a hard gate, not a normal task: *"Execute task
T22 from `specs/014-conditional-gates/tasks.md` — this is a HARD GATE, not a normal task. Run
the FULL characterization suite (confirmed current by T12) now that T13, T14, T15, T18, T19,
T20, T21 have all landed. Report byte-identical PASS/FAIL as the first line of your report. If
anything drifted, name exactly which characterization case and what the diff is — do not guess
which task caused it."*

**Then V3** — hard gate, guards the whole phase (T12–T26). **Do not dispatch Phase 4 or Front
C's remaining tasks (T35, T36, V6) until V3 passes.**

---

## Phase 4 — Cross-workflow triggering (T27–T33 → V4)

Dispatch only after V3 passes.

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T27 | `senior-engineer` | `sonnet` | Parallel with T30 |
| T30 | `junior-engineer` | `haiku` | Parallel with T27 — disjoint file (`state_machine.py`), no dependency on the extraction work |
| T28 | `senior-engineer` | `sonnet` | After T27 — parallel with T31 |
| T31 | `senior-engineer` | `sonnet` | After T30 — parallel with T28, different file |
| T29 | `senior-engineer` | `sonnet` | After T28 (needs its delegate to call, and unwires Phase 3's T14 stub) |
| T32 | `senior-engineer` | `sonnet` | After T29 — parallel with T33 |
| T33 | `senior-engineer` | `sonnet` | After T29 — parallel with T32, different concern (regression test vs. SSE emit) |

Dispatch prompt pattern: *"Execute task T\<N\> from `specs/014-conditional-gates/tasks.md`. Read
that file's task-list entry for T\<N\> for the full spec. This phase depends on Phase 3's T14
stub (the `trigger == workflow` arm) already existing — it does, Phase 3 is complete. If the
entry references a prior Phase 4 task's output (e.g. T28's delegate, T27's extracted core),
that task has already completed — read its report for the exact function name/signature. Report
back the exact diff you made and confirm any acceptance criteria named."*

**Then V4** — guards T27–T33.

---

## Front C — Frontend (T34 after V1; T35/T36/V6 after V3)

**T34 can dispatch as soon as V1 passes** — it only needs Front A's `RouteSpec` field names
locked, not the whole compiler phase's validator, and definitely not Phase 3/4.

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T34 | `junior-engineer` | `haiku` | After V1 (Front A) — independent of Front B, Phase 3, Phase 4 |
| T35 | `senior-engineer` | `sonnet` | After V5 AND after Phase 3's V3 has passed — parallel with T36, same file (`CanvasNode.tsx`), different concerns |
| T36 | `senior-engineer` | `sonnet` | After V5 AND after V3 — parallel with T35, same caveat |
| T37 | `senior-engineer` | `sonnet` | After T34 — independent of V5/T35/T36, can dispatch as soon as T34 lands |
| T38 | `senior-engineer` | `sonnet` | After T34 for its historical-case path; its live-case path additionally needs Phase 4's T32 (`pipeline_diverted` event) — build and dispatch after T34, note in the prompt that live-case testing waits on Phase 4 |

Dispatch prompt pattern: *"Execute task T\<N\> from `specs/014-conditional-gates/tasks.md`. Read
that file's task-list entry for T\<N\> for the full spec. Also read
`specs/014-conditional-gates/contracts/sse-pipeline-diverted.md` if the entry references the
live/historical run-history split. Report back the exact diff you made, which file(s) you
touched or identified, and confirm any acceptance criteria named."*

**Then V5** — guards T34's type contract (backend↔frontend). **T35 and T36 wait on V5, not just
T34** — a wrong shape there wastes the canvas work built against it.

**Then V6** — after T35, T36, T37, T38 all done. Also requires Phase 3's V3 to have passed
(T35/T36 can't be dispatched before then per the table above), so in practice V6 is always the
last validator to run.

---

## Validators

One dispatch pattern for all 6. **A validator only judges — instruct it explicitly not to fix
anything it finds wrong.**

> *"You are validator V\<N\> for `specs/014-conditional-gates`. Read `tasks.md`'s task-list entry
> for V\<N\> for exactly which tasks you guard (its `**Guards**:` line) and the full PASS-criteria
> list (`**PASS requires all of**:`) — do not judge from memory. Actually inspect the code and run
> the verification commands `tasks.md`/`quickstart.md` name (the compile-and-print-leaves script,
> `pytest`, the characterization suite, `tsc --noEmit`, the scripted-model harness runs) rather
> than trusting any task's self-report. Do NOT fix anything you find wrong — only report PASS or
> FAIL with specifics: which criterion failed, on which task, with evidence. If everything passes,
> say so explicitly with a one-line evidence note per criterion."*

**On FAIL**: re-dispatch only the named failed task(s) (same agent/model as their original
dispatch), then re-run the same validator prompt. Repeat up to 2 retries (matching the fix-loop
bound already used in `workflow.js`). If still failing after 2 retries, stop and bring it to the
user rather than proceeding — V1/V2 gate their own fronts, V3 and (implicitly, via T35/T36's
dependency on it) V5 are hard gates nothing downstream should silently route around.

| Validator | Agent | Model | Guards |
|---|---|---|---|
| V1 | `qa-engineer` | `sonnet` (override) | T1–T6 |
| V2 | `qa-engineer` | `sonnet` (override) | T7–T11 |
| V3 | `qa-engineer` | `sonnet` (override) | T12–T26 — **hard gate**, nothing in Phase 4 or the rest of Front C dispatches until this passes |
| V4 | `qa-engineer` | `sonnet` (override) | T27–T33 |
| V5 | `qa-engineer` | `sonnet` (override) | T34 (type contract vs. Front A's T1) — T35/T36 wait on this specifically |
| V6 | `qa-engineer` | `sonnet` (override) | T35, T36, T37, T38 — full AC-07/AC-08 sweep against `spec.md` |

---

## Ledger sync (last — one agent, alone, after V6)

Dispatch **after** V6, and **not in parallel with anything** (it's the only step that edits
`tasks.md`, so a concurrent edit from anywhere else would corrupt it).

> *"Update `specs/014-conditional-gates/tasks.md` to reflect the workflow run just completed.
> Read the file first. Update: (1) the Task ledger table's Status column and Evidence notes for
> every task and validator, (2) the top overview mermaid graph's classDef membership (move ids
> between `task`/`running`/`done`/`error` — never touch node shapes, classDefs, or edges, per the
> STATUS-SYNC section's own rules), (3) each of the five per-phase 'Dependency graphs' section's
> node-text prefixes (⬜/🔄/✅/❌) and that phase's `**Status: N/M done.**` line, (4) the 'Overall
> status as of...' summary line's counts. Do not change any task's description or acceptance
> criteria text — status representations only. Do not check a task's `- [ ]` box unless its
> status is done AND its guarding validator passed."*

Agent: `senior-engineer`, model `sonnet` (needs to keep the ledger table, the top diagram, and
five separate per-phase diagrams all consistent at once, which is judgment work, not mechanical
find-replace — matches `tasks.md`'s own STATUS-SYNC section, which is explicitly `[haiku]` for a
*single* status flip but this is a full-run reconciliation across many nodes at once).

---

## After all of the above

There is no separate user-owned task in `014-conditional-gates` the way 015's T29 (a manual
browser pass) exists — `quickstart.md`'s phase-by-phase verification commands are already
folded into V1–V6's PASS criteria above. Once V6 passes and the ledger sync completes, spec 014
is fully executed per its own acceptance criteria (AC-01 through AC-11 in `spec.md`).

**One thing worth a manual look anyway**: Phase 5's canvas work (T35, T36) only covers the
route-target editor and the external-pipeline node kind — `CanvasView.tsx`'s graph-layout
conversion (loop-back curves, the connect-to-node gesture) is explicitly deferred in `tasks.md`
as needing its own separate scoping pass (RISK-05), and is not dispatched by anything in this
guide. If you want that built, it needs its own planning pass first, not a dispatch from here.
