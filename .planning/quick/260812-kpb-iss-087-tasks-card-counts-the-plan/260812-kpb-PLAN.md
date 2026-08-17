---
phase: quick-260812-kpb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/results/artifactPreview.tsx
  - frontend/src/components/results/AgentDetailPanel.tsx
  - frontend/src/components/results/AgentThinkingTab.tsx
  - frontend/src/components/results/AgentDetailPanel.artifactCards.test.tsx
  - frontend/src/components/results/AgentDetailPanel.tasksCardPlan.test.tsx
autonomous: true
requirements: [ISS-087]
must_haves:
  truths:
    - "The settled tasks card counts the PLAN on screen: `taskCount` and `tasks` come from parsing the selected `<tasks>` body, never from the build agent's completed-task stream."
    - "Exactly ONE new parser exists: `parseTasks`, EXTRACTED from `TasksPreview` in artifactPreview.tsx. `TasksPreview` consumes it. No third inline copy."
    - "frontend/src/hooks/useWorkflow.ts is NOT modified — its line-anchored `protoPlannedTasks` regex stays as-is (feeds ConstructionBlock); the duplicate is FILED as INV-12 debt."
    - "protoCompletedTasks/protoCompletedTaskCount are removed from ArtifactCardData + AgentDetailPanelProps + the AgentThinkingTab threading — no dead prop is left behind."
    - "The build's completed tasks remain on screen via construction.tasks (AgentThinkingTab.tsx:195-202) — no information is lost, it just stops being labelled 'planned'."
    - "Goldens stay 10 passed and 0 golden files move; lint-imports stays 4 kept / 0 broken."
  artifacts:
    - path: "frontend/src/components/results/artifactPreview.tsx"
      provides: "Exported parseTasks — the single `## Task N:` parse for the preview AND the card"
      contains: "export function parseTasks"
    - path: "frontend/src/components/results/AgentDetailPanel.tsx"
      provides: "deriveArtifactCardModel deriving tasks/taskCount from the artifact body"
      contains: "parseTasks(agent.output"
    - path: "frontend/src/components/results/AgentDetailPanel.tasksCardPlan.test.tsx"
      provides: "New RED-first proofs: plan-size count, version switching (run 6e38b9a7), title repaint (run 5ecb990f), deliver-twice idempotence"
  key_links:
    - from: "frontend/src/components/results/AgentDetailPanel.tsx (deriveArtifactCardModel)"
      to: "frontend/src/components/results/artifactPreview.tsx (parseTasks)"
      via: "shared extracted parser (INV-12 — one implementation)"
      pattern: "parseTasks"
---

<objective>
Make the settled "Task plan · N planned" card count the PLAN it is labelled for (ISS-087, owner
decision D1 — LOCKED).

**Purpose:** the card is fed `protoCompletedTasks` / `protoCompletedTaskCount`
(`AgentDetailPanel.tsx:137-140`) — the BUILD agent's `task_progress` completed-task stream
(`useWorkflow.ts:971-995`). A card labelled "planned" therefore renders the number **completed**.
That is a category error with two visible consequences, both measured against `backend/dev.db`:

1. **Wrong at the latest version, with no picker involved.** Run `d5dbc9f2`: the plan holds
   **7** tasks; `task_progress` reached `completed_count` 6; the card renders **"6 planned"**
   with 6 rows.
2. **Wrong under the version picker (ISS-087 as filed).** Run `6e38b9a7`: plan v1 = 10 tasks,
   v2 = 11. Selecting v1 keeps showing **11** with v2's rows, because the rows never came from
   the artifact at all.

The row's own premise — "low impact, one version on most runs" — is false: `prototype-plan` has
6 run-groups in `dev.db` and **5 are multi-version**.
</objective>

## Decision (LOCKED — owner D1)

Show the **plan's** size. Parse the selected `<tasks>` body.

**Do NOT write a parser.** Two already ship. Extract the parsing half of `TasksPreview`
(`artifactPreview.tsx:112-129`) into an exported `parseTasks`, mirroring exactly how
`parseSpecSections` / `parseSpecOverview` were extracted from `SpecPreview` (same file, `:45-78`).

**Do NOT re-point `useWorkflow.ts`.** Its `protoPlannedTasks` regex is line-anchored (`^…$` + `m`)
and tolerates `\s*:`; `artifactPreview`'s is neither. It feeds `protoPlannedTasks` →
`ConstructionBlock` via `AgentThinkingTab.tsx:195-202`. Switch the CARD only; FILE the duplicate.

## Tasks

### Task 1 — extract `parseTasks` (artifactPreview.tsx)

Lift the parse out of `TasksPreview` into an exported `parseTasks(content)` placed beside
`parseSpecSections`/`parseSpecOverview`. `TasksPreview` calls it. Byte-identical regexes — this
is a move, not a rewrite.

### Task 2 — derive the card from the artifact (AgentDetailPanel.tsx)

`deriveArtifactCardModel` (`:127-161`) derives `tasks`/`taskCount`/`showTasks` from
`parseTasks(agent.output)`. `agent` here is already `displayed` (`:752`), i.e. the version on
screen, so the card follows the picker for free.

Delete the now-unused `protoCompletedTasks`/`protoCompletedTaskCount` from `ArtifactCardData`
(`:76-80`), `AgentDetailPanelProps` (`:730-731`), the destructure (`:741`) and the call site
(`:773`), plus the caller's threading (`AgentThinkingTab.tsx:207-208`). `dagEdges` stays — the
handoff still needs it.

### Task 3 — reconcile the 3 pinned 42-09 tests + add the new proofs

`AgentDetailPanel.artifactCards.test.tsx:42-55`, `:57-67`, `:173-188` pin the OLD behaviour.
Rewrite them against the approved new behaviour with fixtures that actually exercise it.
NEVER delete, NEVER loosen, NEVER `.skip`.

New suite `AgentDetailPanel.tasksCardPlan.test.tsx`, every case seen RED first:
- two-task body + a 5-element completed list → `taskCount === 2`;
- panel-level v1 = 10 / v2 = 11 reproducing run `6e38b9a7`, incl. `Back to latest`;
- same-count/different-titles reproducing run `5ecb990f` (a count-only assert would pass wrongly);
- deliver the frames TWICE and assert the number is unchanged.

## Out of scope — FILE, do not fold

- The duplicate `<tasks>` parser in `useWorkflow.ts` (named INV-12 debt).
- The validation badge / `ValidationResultCard`: `gate_passed` and `validator_result` have ZERO
  producers in the backend, so `validationPassed === true` is structurally unreachable. Report
  the verdict and file it; do not version-thread a field nothing populates.
- `dagEdges` — NOT a defect. A DAG handoff edge is constant within a run.

## Verification

- vitest from `frontend/` (cwd-sensitive), each new case RED before GREEN.
- Real-data replay of runs `d5dbc9f2`, `6e38b9a7`, `5ecb990f` from `backend/dev.db` (read-only).
- Goldens 10 passed + 15 golden hashes unchanged; `lint-imports` from `backend/` 4 kept / 0 broken.
- `tsc --noEmit` stays at its 2 pre-existing errors.
