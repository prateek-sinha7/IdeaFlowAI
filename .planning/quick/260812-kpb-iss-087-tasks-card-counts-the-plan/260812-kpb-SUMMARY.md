---
phase: quick-260812-kpb
plan: 01
status: complete
requirements: [ISS-087]
branch: bugfix/spec-revision-context-loss
base_commit: 1f79ae64
files_changed: 5
tasks_completed: 3
completed: 2026-08-12
---

# quick-260812-kpb — "Task plan · N planned" now counts the plan (ISS-087)

**One-liner:** The settled tasks card reads the `<tasks>` artifact on screen instead of the build
agent's completed-task stream, which fixes both the version-picker defect ISS-087 was filed for
AND a previously-unfiled defect at the latest version — verified against three real runs in
`backend/dev.db` through the shipped code.

## What was wrong

`deriveArtifactCardModel` derived the card's rows and count from `protoCompletedTasks` /
`protoCompletedTaskCount` — the BUILD agent's `task_progress` stream (`useWorkflow.ts:966-995`).
A card labelled **"N planned"** was therefore rendering the number **completed**. Two consequences,
both measured against `backend/dev.db` (read-only) BEFORE the change:

| Run | Plan (latest) | Card rendered | Defect |
|---|---:|---:|---|
| `d5dbc9f2` | **7** | **6 planned** | wrong at LATEST, no picker involved — unfiled until now |
| `6e38b9a7` | 11 (v2) / 10 (v1) | 11 always | ISS-087 as filed: selecting v1 could not move it |
| `5ecb990f` | 8 / 8, titles differ | 8, v2's titles | rows never came from the artifact at all |

The register row's premise was also false: `prototype-plan` has 6 run-groups in `dev.db` and
**5 are multi-version**, so the picker is visible on most prototype runs, not a rarity.

## The change (owner decision D1 — LOCKED)

**Task 1 — `parseTasks` EXTRACTED, not written** (`artifactPreview.tsx:80-104`). The parsing half
of `TasksPreview` was lifted verbatim (byte-identical regexes) into an exported `parseTasks`,
placed beside `parseSpecSections`/`parseSpecOverview` and mirroring exactly how those were
extracted from `SpecPreview`. `TasksPreview` now calls it; its degrade path re-strips the wrapper
exactly as `SpecPreview`'s does. **No third parser was created** — an inline copy inside
`deriveArtifactCardModel` would have been a straight INV-12 violation.

**Task 2 — the card reads the artifact** (`AgentDetailPanel.tsx:134-143`). `tasks`/`taskCount`/
`showTasks` now come from `parseTasks(agent.output)`. Because `agent` here is already `displayed`
(`:753`, the version on screen), the card follows the version picker for free — no second
threading was added on top of FIX-226's.

The now-dead `protoCompletedTasks`/`protoCompletedTaskCount` were removed from `ArtifactCardData`,
`AgentDetailPanelProps`, the destructure, the call site and the single caller
(`AgentThinkingTab.tsx:207-208`) rather than left as inert props. **Nothing is lost from the
screen**: the build's completed tasks still reach the ConstructionBlock via `construction.tasks`
(`AgentThinkingTab.tsx:195-202`), where "completed" is what the label actually claims.

**`useWorkflow.ts` was NOT touched** — deliberately. Its `protoPlannedTasks` regex
(`useWorkflow.ts:1020`) is line-anchored and tolerates `\s*:`, so it is NOT equivalent to the
extracted one, and it feeds `ConstructionBlock`. Filed as named INV-12 debt instead.

## Tests — every new case seen RED first

Seven cases were run against the UNMODIFIED source (sources reverted to HEAD with the final test
files in place) and **all seven observed RED**, then all green after:

| Case | RED message observed |
|---|---|
| counts the tasks in the artifact body, not the build's completed tasks | `expected false to be true` (no card at all) |
| reads the plan after task_progress delivered TWICE | `expected +0 to be 7` |
| selecting v1 repaints rows + count (run `6e38b9a7`) | `Unable to find … /11 planned/` |
| repaints TITLES at equal counts (run `5ecb990f`) | `Unable to find … /8 planned/` |
| *(reconciled)* selects the tasks card and counts the `<tasks>` body | `expected false to be true` |
| *(reconciled)* single_shot shows its plan; empty body → no card | `expected false to be true` |
| *(reconciled)* renders the tasks card + handoff | `Unable to find … /3 planned/` |

The three reconciled cases are the 42-09 pins at `artifactCards.test.tsx:42-55`, `:57-67`,
`:173-188`. None was deleted, skipped or loosened. Two encode owner-approved behaviour changes
(the count becomes the plan's size; a `single_shot` `<tasks>` agent now shows its plan); the
conditional-degrade guarantee the second one existed to protect is preserved, re-pointed at a
`<tasks>` body containing no task rows.

The deliver-twice case uses the ONE existing reducer driver (`__fixtures__/reducerHarness.ts`)
rather than a hand-rolled replay, and asserts the accumulator still reads 6 while the card reads 7
— the two numbers are different quantities, and only one of them is the plan.

## Verification

- **Real data, shipped code, rendered DOM** (free — read-only DB, no run launched): every
  `prototype-plan` artifact version of all three runs was fed through the actual `parseTasks` +
  `deriveArtifactCardModel`, and the latest version was rendered through `AgentDetailPanel`.
  `d5dbc9f2` DOM now reads **"7 planned"** (was 6). `6e38b9a7` v1 → **10**, v2 → **11**, with v1's
  task 4 "Transaction Wizard Page (Steps 1–2)" present only in v1. `5ecb990f` → **8 / 8** with the
  task-4 titles differing ("Intake Wizard (…)" vs "Intake Wizard Page (…)").
- **Browser (mocked Playwright)**: `e2e/tests/ts-n.review-gate.spec.ts` **8 passed / 1 skipped**,
  including `TS-N-02 preview mode: tasks render via the TasksPreview list` — a real browser proof
  that the parser extraction is behaviour-preserving on the gate path.
- Goldens **10 passed**, **0 of 15 golden files moved** (sha256 before/after identical).
- `lint-imports` from `backend/` — **4 kept / 0 broken**.
- `src/components/results` — 12 failed / 112 passed; the failing **ID set is identical** to the
  pre-change baseline (10 `AuditTab` + 2 `FilesTab`, both pre-existing).
- `tsc --noEmit` — still exactly **2** pre-existing errors; no third.
- Reducer specs 65 passed; `AgentThinkingTab` + `StepsDrilldown` 14 passed; `ResultCard`
  1 failed / 12 passed (ISS-114, pre-existing, untouched).

## Filed, not folded

- `useWorkflow.ts:1020` — the second `## Task N:` parser (named INV-12 debt).
- The validation badge — **DEAD, not merely un-versioned**. `gate_passed` has **zero** producers
  anywhere in the backend and `validator_result` zero outside a docstring, so
  `validationPassed === true` is structurally unreachable and the green "Passed" branch cannot
  render; `checksIssueCount` is always 0, so the amber chip always reads "Review". No honest
  affordance was built for a surface that carries no version-specific information.
- `useRunStateStore.ts:395-403` — `validator_result`/`gate_passed`/`gate_blocked` are absent from
  `pipelineFrameTypes` and dropped by the `:405` early return, so even the reachable
  `gate_blocked` path cannot rehydrate on a run reopened from history. Confirmed, not suspected.
- `dagEdges` — **closed as NOT a defect**: a DAG handoff edge is a property of the run and is
  constant within it.
