# 015 — Dispatch guide: which agent, what to tell it, in what order

A reference for driving `tasks.md` by hand via the Agent tool — no automation runs on its own.
Each entry below tells you (or me, when you say "go") which `subagent_type` to use, which
`model`, and the exact dispatch prompt. Agents read `tasks.md` themselves for the full spec
(file path, description, acceptance criteria) — this guide never duplicates that text, only
tells you how to invoke it, so there is one source of truth, not two drifting copies.

**Model note**: `tasks.md` labels 12 tasks `[sonnet]` and all 7 validators `[sonnet]`. This
overrides your standing haiku-only subagent rule (CLAUDE.md §7) — an explicit, scoped exception
you confirmed for this spec's execution only. Pass `model` exactly as shown below.

**Agent type note**: three project-local roles in `.claude/agents/` are the base for everything
below — `junior-engineer` (haiku, mechanical/fully-specified tasks), `senior-engineer` (sonnet,
multi-file/judgment tasks), and `qa-engineer` (haiku by default, has no Write/Edit tool access —
it can only judge, never fix). Validators use `qa-engineer` with an explicit `model: sonnet`
override: `tasks.md` pre-classifies all 7 validators as needing sonnet-level judgment, and your
CLAUDE.md's own exception clause allows overriding a subagent's default model when a task list
already makes that classification — this is that case, not an ad hoc upgrade.

---

## The sequencing (same structure as `tasks.md`'s graph, restated as a dispatch order)

```
Foundation (T1→T2→T3, sequential — same file)
  → V1
  → Core Routing (T4→T5→T6, then T7→T8→T11 chain ∥ T9 ∥ T10)
  → V2 — HARD GATE. Do not dispatch anything below until this passes.
    → Lane A (T12∥T13∥T14, then T15→T16) → V3   ┐
    → Lane B (T17∥T18, then T19→T20→T21) → V4    │  these 4 lanes are
    → Lane C (T22→T23→T24)              → V5     │  independent — dispatch
    → Lane D (T25∥T26, then T27→T28)    → V6     ┘  all 4 in ONE message
      → V7 (needs V3+V4+V5+V6's results) — HARD GATE
        → Ledger sync (one agent, updates tasks.md — must run alone, last)
          → T29 (you — quickstart.md in a real browser)
```

**Parallel dispatch = one message, multiple `Agent` tool-use blocks.** Sequential = wait for the
result before sending the next. Everything marked `∥` above can go in the same message.

---

## Foundation

| Task | Agent | Model | Prompt |
|---|---|---|---|
| T1 | `junior-engineer` | `haiku` | "Execute task T1 from `specs/015-frontend-routing/tasks.md`. Read that file's T1 entry (Task list + Task detail section) for the full file path, description, and acceptance criteria before starting. Also read `specs/015-frontend-routing/contracts/route-map.md`, which T1 is built from. Report back which AC items you verified and how." |
| T2 | `junior-engineer` | `haiku` | Same pattern for T2 — **dispatch after T1 completes**, same file. |
| T3 | `junior-engineer` | `haiku` | Same pattern for T3 — **dispatch after T2 completes**. |

**Then V1** — see [Validators](#validators) below, guarding T1–T3.

---

## Core Routing (gated by V1; V2 is a hard gate on everything after)

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T4 | `senior-engineer` | `sonnet` | Docs-only (`data-model.md`) — dispatch first, no code dependency |
| T5 | `senior-engineer` | `sonnet` | After T4 |
| T6 | `senior-engineer` | `sonnet` | After T5 |
| T7 | `senior-engineer` | `sonnet` | After T6 |
| T8 | `senior-engineer` | `sonnet` | **After T7 — same file, do not parallelize** (this was a bug in the original graph, now fixed) |
| T9 | `senior-engineer` | `sonnet` | Parallel with the T7→T8→T11 chain and with T10 — different file (`DashboardLayout.tsx`) |
| T10 | `junior-engineer` | `haiku` | Parallel with the T7 chain and with T9 — different file (`page.tsx` root) |
| T11 | `senior-engineer` | `sonnet` | After T7 (needs its run-fetch state); can run after T7 even while T8 is still going, if you want finer-grained parallelism — simplest is after the whole T7→T8 chain |

Dispatch prompt pattern for each: *"Execute task T\<N\> from `specs/015-frontend-routing/tasks.md`. Read that file's T\<N\> entry for the full spec. Also read `data-model.md`'s Route → Screen table for the MainView mapping context. Report back which AC items you verified and how, and list every file you touched."*

**Then V2** — hard gate, guards T4–T11. **Do not dispatch any lane below until V2 passes.**

---

## Lanes A–D (dispatch all 4 in one message once V2 passes)

### Lane A — Shareable views → V3

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T12 | `junior-engineer` | `haiku` | Parallel with T13, T14 |
| T13 | `junior-engineer` | `haiku` | Parallel with T12, T14 |
| T14 | `junior-engineer` | `haiku` | Parallel with T12, T13 |
| T15 | `senior-engineer` | `sonnet` | After T12–T14 |
| T16 | `junior-engineer` | `haiku` | After T15 — same file |

### Lane B — Edges & boundaries → V4

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T17 | `junior-engineer` | `haiku` | Parallel with T18 |
| T18 | `junior-engineer` | `haiku` | Parallel with T17 |
| T19 | `junior-engineer` | `haiku` | After T17/T18 |
| T20 | `junior-engineer` | `haiku` | After T19 (visual pairing) |
| T21 | `junior-engineer` | `haiku` | After T19/T20 |

### Lane C — Access & session → V5

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T22 | `senior-engineer` | `sonnet` | First in this lane |
| T23 | `junior-engineer` | `haiku` | After T22 |
| T24 | `senior-engineer` | `sonnet` | After T22 (adjacent `lib/api.ts` logic — keep sequential) |

### Lane D — Completion & observability → V6

| Task | Agent | Model | Sequencing |
|---|---|---|---|
| T25 | `senior-engineer` | `sonnet` | Parallel with T26 |
| T26 | `junior-engineer` | `haiku` | Parallel with T25 |
| T27 | `junior-engineer` | `haiku` | After T25/T26 |
| T28 | `senior-engineer` | `sonnet` | After T27 (needs `screenLabel`) |

Same dispatch prompt pattern as above, per task.

**Then V3, V4, V5, V6** — each guards its own lane, can run as soon as that lane's tasks finish (don't wait for the other 3 lanes).

---

## Validators

One dispatch pattern for all 7. **A validator only judges — instruct it explicitly not to fix anything it finds wrong.**

> *"You are validator V\<N\> for `specs/015-frontend-routing`. Read `tasks.md`'s V\<N\> entry for exactly which tasks you guard and the full PASS criteria list — do not judge from memory. Actually inspect the code and run the verification commands `tasks.md` names (`npx tsc --noEmit`, `npm test -- <file>`, the `grep` checks) rather than trusting any task's self-report. Do NOT fix anything you find wrong — only report PASS or FAIL with specifics: which criterion failed, on which task, with evidence. If everything passes, say so explicitly with a one-line evidence note per criterion."*

**On FAIL**: re-dispatch only the named failed task(s) (same agent/model as their original dispatch), then re-run the same validator prompt. Repeat up to 2 retries. If still failing, stop and bring it to the user rather than proceeding — V2 and V7 are hard gates; V1/V3/V4/V5/V6 gate only their own group, but an unresolved failure there should still be surfaced to V7, not silently dropped.

| Validator | Agent | Model | Guards |
|---|---|---|---|
| V1 | `qa-engineer` | `sonnet` (override) | T1, T2, T3 |
| V2 | `qa-engineer` | `sonnet` (override) | T4–T11 — **hard gate** |
| V3 | `qa-engineer` | `sonnet` (override) | T12–T16 |
| V4 | `qa-engineer` | `sonnet` (override) | T17–T21 |
| V5 | `qa-engineer` | `sonnet` (override) | T22–T24 |
| V6 | `qa-engineer` | `sonnet` (override) | T25–T28 |
| V7 | `qa-engineer` | `sonnet` (override) | V3, V4, V5, V6 results — **hard gate**, full FR/SC sweep against `spec.md` |

---

## Ledger sync (last — one agent, alone, after V7)

Dispatch **after** V7, and **not in parallel with anything** (it's the only step that edits
`tasks.md`, so a concurrent edit from anywhere else would corrupt it).

> *"Update `specs/015-frontend-routing/tasks.md` to reflect the workflow run just completed. Read the file first. Update: (1) the Task ledger table's Status column and Evidence notes for every task and validator, (2) the top overview mermaid graph's classDef membership (move ids between todo/done/error), (3) the detailed 'Execution graph — LIVE STATUS' graph's node-text prefixes and classDef lines the same way, (4) the 'Status as of...' summary line's counts. Do not change any task's description or AC text — status representations only. Do not check a task's `- [ ]` box unless its status is done AND its guarding validator passed."*

Agent: `senior-engineer`, model `sonnet` (needs to keep 3 separate representations — table, two graphs — consistent, which is judgment work, not mechanical find-replace).

---

## After all of the above

**T29 is yours** — run `specs/015-frontend-routing/quickstart.md` in a real browser. No agent
substitutes for this; it's the only signal that actually closes the spec.
