# ISSUES — sandbox-git-versioning spec vs. implementation

> **Scope:** `.kiro/specs/sandbox-git-versioning` (v1) and
> `.kiro/specs/sandbox-git-versioning-v2` (v2) versus
> `specs/019-sandbox-git-versioning/spec.md` (original canonical spec).
>
> **Commits analysed:**
> - `24f1127` — `feat(sandbox): git-backed run versioning and run chaining` (v1 implementation)
> - `e7305f9` — `feat: implement sandbox-git-versioning-v2 spec (102 tasks)` (v2 implementation)
> - `2d54f5d` — `chore: update Alembic head to 0046 in steering, remove scratch files`
> - `77046158` / `8e156580` — post-v2 follow-on commits (velocity-design skill only)
>
> Each issue below describes what the original spec required, what was found
> (or not found) in the implementation commits, and the severity.

---

## ISSUE-001 — Two partial gaps in the release-gate review remain unresolved

**Severity:** HIGH (release-blocking per the spec itself)

**Spec reference:** `sandbox-git-versioning-v2/gap-closure-review.md` §"Pre-Release
Action Items"; v2 Requirement 17 AC 19 ("An unreviewed row blocks release").

The `gap-closure-review.md` file committed in `e7305f9` explicitly records two
**PARTIAL** gaps:

- **SGV2-GAP-005 (PARTIAL):** The mixed-deploy detection integration between the
  `LaunchWizard` / `DashboardLayout` chain path and the `incompatible_backend`
  reason code surfacing has no dedicated test. The gap-closure document states:
  > "Add one `LaunchWizard.test.tsx` test case that mocks the backend returning no
  > `run_id` for a chain launch when `source_workflow_run_id` is present, asserts
  > `incompatible_backend` is surfaced, and confirms no run is silently started
  > without provenance."

- **SGV2-GAP-017 (PARTIAL):** The chain-source picker list composition showing a
  non-chainable source as unavailable with its `non_chainable_reason` code is
  implemented in `LaunchWizard.tsx` but not independently tested. The gap-closure
  document states:
  > "Add one `LaunchWizard.test.tsx` case seeding a non-chainable source
  > (`payload_chainable: false`) and asserting it renders as unavailable with
  > `non_chainable_reason`; confirm the continue button is disabled until the
  > warning is acknowledged."

Both items are called out in the review as RECOMMENDED before release. Neither
was addressed in any subsequent commit after `e7305f9`. The two post-v2 commits
(`8e156580`, `77046158`) only touch the `velocity-design` skill and the prototype
workflow — the `LaunchWizard.test.tsx` file was not modified.

**What is missing:** Two `LaunchWizard.test.tsx` test cases.

---

## ISSUE-002 — v1 task marker "all checked" does not reflect actual implementation correctness

**Severity:** HIGH (design contract)

**Spec reference:** Original spec `specs/019-sandbox-git-versioning/spec.md` §2
Decisions; v2 Requirement 1 AC 3.

All tasks in `.kiro/specs/sandbox-git-versioning/tasks.md` are marked `[x]`
(complete), yet the v2 spec's own introduction explicitly documents that five
defects existed after v1 shipped:

| Defect | v1 task that claimed to fix it |
|--------|-------------------------------|
| D1: `_find_chain_root` walks `source_run_id` (wrong edge) | Task 5.1 — "Walk parent_run_id to chain root" |
| D2: `RunSandbox` carries one id; run log collides across revisions | Task 5.7 — "Rename run log … to per-run paths" |
| D3: `_fire_post_run` runs before Step 5 (optimistic tag/payload) | Task 3.2 / 6.3 — post_run finalizer |
| D4: `.chain/` is gitignored and in no commit | Task 3.3 — ".chain/{run_id}/ writer" |
| D5: `pre_commit` fires with `payload=""` — scan cannot block | Task 4.4 — "Add pre_commit and post_commit" |

All five tasks are marked checked in v1. The v2 spec explicitly states these
were verified defects in the post-v1 source. This means the v1 implementation
shipped with the checkboxes set but the acceptance criteria not behaviorally
satisfied. This is a systemic verification gap — checkboxes were used as evidence
of completion (which v2 Requirement 1 AC 3 explicitly prohibits).

**What is missing:** A behavioral-test baseline capturing passing/failing state
before v1 was merged. This was required by v2 Task 1.4 but the baseline tests
(`test_defect_characterization_v2.py`) were only added in `e7305f9`, after the
defects were already in the codebase.

---

## ISSUE-003 — Seam 2 removal is incomplete: prompt migration not finished

**Severity:** HIGH

**Spec reference:** Original spec §2 "Q4 in full", FR-046–FR-049; v1 Requirement 30;
v2 Requirement 13; v1 Task 9 "Seam 2 removal and per-workflow prompt migration".

The original spec decision Q4 required removal of both prompt injection seams,
with every built-in workflow migrated off the default policy before Seam 2's code
is deleted. v1 Task 9.5 states: "Delete Seam 2 code once the last workflow is off
the default policy."

In `e7305f9`, only **6 AGENT.md files were modified** out of the 94 the spec
identifies as requiring rewrite (`backend/agents/prompts/domain-analyst/AGENT.md`,
`dotnet-inventory`, `material-analyzer`, `mulesoft-inventory`, `ppt-brief-analyst`,
`prototype-specify`). The 94-file rewrite requirement comes from the original spec's
"Start here" header: *"backend/agents/prompts/\*/AGENT.md (94 files)"*.

The `_compose_context_message` seam-2 code remains in `engine.py` — deletion
requires all 94 workflows migrated first. v1 Task 9.5's trigger condition
("delete after the last workflow is off the default policy") is not met.

**What is missing:**
- ~88 AGENT.md files not migrated to the new prompt policy.
- Seam 2 code (`_compose_context_message` block assembly) not deleted.
- v1 Task 9.1's requirement to "re-derive each workflow's characterization test
  deliberately" has only been done for migrated workflows; the rest remain on
  the old policy.

---

## ISSUE-004 — `WorkflowRun.root_run_id` optional column not implemented

**Severity:** MEDIUM

**Spec reference:** Original spec FR-001 ("A materialised `root_run_id` column is a
later optimisation"); v1 design §Data Models `WorkflowRun.root_run_id`
(`Optional; one additive nullable column if walk is measured to be slow`);
v2 Requirement 16 AC 5 explicitly marks "A DB cache of refs or tags" as
out of scope, but `root_run_id` is a *resolver cache*, not a ref cache.

The v1 design document explicitly lists `root_run_id` as an optional
performance column. Neither `24f1127` nor `e7305f9` adds a migration for
`root_run_id`. The v2 tasks.md `1.5` out-of-scope list does not name
`root_run_id` — only "A DB cache of refs or tags". This means the performance
trade-off decision was never made explicitly: the column was deferred without a
recorded measurement showing the walk is fast enough to not need caching.

**What is missing:** Either a measurement confirming the `parent_run_id` walk
is acceptably fast at production chain depths, or the additive migration for
`root_run_id` as an optimization. The omission should be explicitly recorded as
a decision rather than left as an implicit gap.

---

## ISSUE-005 — Disk growth instrumentation missing from v2 commit

**Severity:** MEDIUM

**Spec reference:** Original spec FR-041 ("instrument and measure per-terminal-run:
sandbox size, .git size, chain depth"); v1 Requirement 35; v1 Task 4.7
("Add git gc --auto on post_run and instrument disk growth per terminal run").

v1 Task 4.7 is marked `[x]` and v1 Task 10.5 ("Verify disk growth
instrumentation is live") is also marked `[x]`. However, in `e7305f9` — the v2
commit — neither `backend/app/core/config.py` additions nor the finalizer
changes include identifiable disk-growth metric emission. The `e7305f9` diff
shows `backend/app/core/config.py` with 11 added lines (settings additions), but
no dedicated disk-growth observability file or test is present in the diff.

The `git gc --auto` call is present (the v2 finalizer 12-step sequence step 12
includes it), but the per-terminal-run metrics recording (sandbox on-disk size,
`.git` directory size, chain depth) required by v1 Requirement 35 AC 2 is not
confirmed by any test file in the `e7305f9` diff. `test_finalizer_v2.py` (1957
lines) is the primary finalizer test but covers correctness, not metrics
emission.

**What is missing:** Observable metrics (or structured log entries) for
sandbox size, `.git` size, and chain depth per completed run, plus a test or
verification confirming the instrumentation is live.

---

## ISSUE-006 — `LaunchWizard.test.tsx` only minimally updated for v2

**Severity:** MEDIUM

**Spec reference:** v2 Requirement 21; v2 Task 11.9 (7 lines diff shows only a
7-line change to `frontend/src/components/workflow/LaunchWizard.test.tsx`).

The v2 diff for `LaunchWizard.test.tsx` shows only **7 lines changed** (`7 +-`).
v2 Task 11.9 requires a comprehensive set of frontend tests including:
- Source-list composition for all five terminal statuses plus a non-chainable
  source
- Non-success warning accessible and acknowledged
- No internal ref string in rendered output
- Both the PARTIAL gap tests from ISSUE-001

A 7-line diff is consistent with adding one or two small assertions but does
not reflect the full test coverage the v2 spec requires for this file.

**What is missing:** Full LaunchWizard test coverage for the chain-source picker
(five terminal statuses, non-chainable source, mixed-deploy cases).

---

## ISSUE-007 — `GAPS.md` committed to repo root from v1 commit, never cleaned up

**Severity:** LOW

**Spec reference:** `24f1127` diff shows `GAPS.md` (865 lines) added to the
repository root. v2 `tasks.md` Task 1.5 notes that the v2 spec was authored
after reviewing `GAPS.md`.

The `GAPS.md` file in the repo root is the handoff document between v1 and v2.
After v2 was implemented, this file has no operational purpose — all gaps it
records are addressed in the v2 spec. It is not a spec file, not a migration
ledger, and not part of `.planning/`. Leaving it at the repo root risks it being
treated as authoritative when it is superseded by
`sandbox-git-versioning-v2/requirements.md`.

**What is missing:** Either removal of `GAPS.md` from the repo root (moved to
`specs/019-sandbox-git-versioning/reports/` if historical reference is needed),
or a header marking it explicitly superseded by v2.

---

## ISSUE-008 — Steering file head was 0037, corrected to 0041 in v1 but v2 requires 0046

**Severity:** LOW (already partially addressed)

**Spec reference:** v1 Task 1's note "Alembic head before this spec is 0037";
v2 Task 1.2 "Confirm the head is 0041"; v2 Task 1.3 "Correct the stale Alembic
head in `.kiro/steering/project-index.md`"; commit `2d54f5d` "update Alembic
head to 0046 in steering".

The `2d54f5d` commit updates the steering file to head 0046 after `e7305f9`
added migrations 0042–0046. This is correct. However, the update came as a
**separate commit after the implementation**, not atomically with the migrations.
The project-index steering file was therefore stale (showing 0041) between
`e7305f9` and `2d54f5d`.

v2 Task 1.3 explicitly requires the correction happen as part of the spec
implementation, not as a follow-up.

**What is missing:** This is resolved by `2d54f5d`, but the process gap means
any session between those two commits would have read a wrong head number. The
task dependency graph (Task 1.3 in wave 0) required this to land before any
migration work.

---

## ISSUE-009 — v1 tasks reference wrong Alembic head throughout

**Severity:** LOW (documentation)

**Spec reference:** v1 `tasks.md` Notes section: "Alembic head before this spec
is 0037"; v2 Task 1.2 explicitly corrects this: "Confirm the head is **0041**,
not 0037".

The v1 tasks file (`.kiro/specs/sandbox-git-versioning/tasks.md`) notes section
says "Alembic head before this spec is 0037 — verify with `cd backend && alembic
heads` before task 6.2". This was already wrong when v1 was authored — the
actual head was 0041 (migration `0041_add_git_tag_to_workflow_run.py`, which the
v1 commit `24f1127` itself adds). The note predates the v1 migration that bumps
the head, creating a circular inconsistency in the document.

**What is missing:** The v1 tasks.md note should read "Alembic head before this
spec is 0040 (verify with alembic heads before task 6.2); task 6.2 adds 0041".

---

## ISSUE-010 — v1 `Step.outputs` / `Step.replaces` implementation vs. spec

**Severity:** MEDIUM

**Spec reference:** Original spec `v1 design §Compiler (L6)`: "plan.py and
compiler.py new outputs and replaces step fields — Declared output surface for
engine-side deletion reconciliation; opt-in per step"; v1 Requirement 33;
v1 Task 4.6 "Add outputs and replaces step fields to plan.py and compiler.py".

v1 Task 4.6 is marked `[x]` and `plan.py` shows 17 lines added in `24f1127`.
However, the v2 spec explicitly retains this requirement as a **Retain** row
("v1 Requirement 33 — stale-output declaration and name-free kernel remain
binding") and adds the clarification: "The flat payload does NOT become a
`replaces` target. The `.chain/` allowlist reconciliation in Requirement 4 AC 9
is a separate mechanism and must not be conflated with it."

The v2 design normative map (Component Map, L7 execution kernel) lists
`plan.py` `Step.outputs`/`Step.replaces` as a **no-change surface** — it is
retained from v1 exactly as defined. This means any v1 implementation that
conflated `.chain/` allowlist with `replaces` logic would be wrong, but the
separation is confirmed correct in the implementation by the explicit v2 note.

**What is confirmed:** `Step.outputs` and `Step.replaces` are present (added in
`24f1127`). The `.chain/` flat payload reconciliation is a separate mechanism in
`build_flat_payload`. This is correctly implemented.

**Residual gap:** No test in either v1 or v2 specifically asserts
that a step declaring `replaces: true` correctly removes tracked paths *not*
written this pass, exercising the `changed_since(spawn_point)` path. The v1
test file `test_phase2_git_versioning.py` covers git operations but the
`replaces`-specific reconciliation path is not tested in the `e7305f9` diff.

---

## ISSUE-011 — `AgentThinkingTab.tsx` / `AgentDetailPanel.tsx` repoint incomplete in v2

**Severity:** MEDIUM

**Spec reference:** v2 design §L2 run surface, `AgentDetailPanel.tsx` row:
"Repointed at system prompt plus targeted retry payload after Seam 2 removal";
v1 Task 8.6; v2 Task 10.6.

v2 Task 10.6 ("Update the prompt viewer") is marked `[x]`. The `e7305f9` diff
shows `AgentDetailPanel.tsx` with 46 lines changed. However, this repointing
is only fully meaningful once Seam 2 is removed — per ISSUE-003, Seam 2 code is
still present in `engine.py`. The panel currently shows an updated view, but for
workflows still on the default policy the human message context remains the full
15-block assembly, making the "targeted control payload" display misleading for
those workflows.

**What is missing:** The prompt viewer fix is correct in isolation, but its
correctness is contingent on each workflow completing Seam 2 migration (ISSUE-003).
The panel will show near-empty context for migrated workflows and the full
assembly for unmigrated ones, with no visual distinction between those two
states.

---

## ISSUE-012 — `WorkflowHistory.tsx` changed in both commits but not required by original spec

**Severity:** LOW (potential scope creep)

**Spec reference:** Original spec §13 component map; v1 design §Frontend run
surface (L2); v2 design §L1.

Neither the original spec, the v1 component map, nor the v2 normative component
map lists `WorkflowHistory.tsx` as a touched surface. Both `24f1127` (5 lines)
and `e7305f9` (114 lines) modify this file. The v2 change is significant —
114 lines — which suggests substantive functionality was added outside the
declared scope.

The v2 design's component map is normative (v2 Requirement 1 AC 5): "A required
change outside it updates the map first." No update to the normative map names
`WorkflowHistory.tsx`.

**What is missing:** Either an update to the v2 normative component map
recording `WorkflowHistory.tsx` and the requirement it addresses, or
confirmation that the 114-line change is purely additive display logic
that does not require a new map entry. This should be reviewed to confirm
no behavioral requirement is hidden in an undeclared surface.

---

## ISSUE-013 — `deep_agent_runner.py` changed in v2 but not in the normative component map

**Severity:** MEDIUM

**Spec reference:** v2 design component map (L7 execution kernel, L8 runtime and
workspace); v2 Requirement 1 AC 5.

`e7305f9` modifies `backend/app/agents/deep_agent_runner.py` with 198 lines
changed. This file does not appear in either the v1 design component map or the
v2 normative component map. The v2 map is the normative authority for every
touched production surface.

**What is missing:** A map entry for `deep_agent_runner.py` stating what changed
and which requirement owns it. Without this, the 198-line change cannot be
reviewed against the spec's acceptance criteria.

---

## ISSUE-014 — `StepsOverviewSpine.tsx` changed in v2 but not in the normative component map

**Severity:** LOW

**Spec reference:** Same as ISSUE-013.

`e7305f9` shows `frontend/src/components/results/StepsOverviewSpine.tsx` with
12 lines changed. This component is not in the v1 or v2 component maps.

**What is missing:** Same as ISSUE-013 — a map entry or explicit confirmation
that the change is a trivial display fix driven by an existing spec surface.

---

## ISSUE-015 — `RunChatLane.tsx` changed in v2 but not in the normative component map

**Severity:** LOW

**Spec reference:** Same as ISSUE-013.

`e7305f9` shows `frontend/src/components/chat/RunChatLane.tsx` with 19 lines
changed. The original spec's component list names `RunChatLane` as one that
"Absorbed `AgentProgressPanel.tsx`" (per the invariants `AgentProgressPanel.tsx`
entry) but does not name it as a surface touched by the git-versioning spec.

**What is missing:** Map entry or confirmation.

---

## ISSUE-016 — `PreviewPanel.tsx` live defect fix from v2 Req 9 not traced to the original spec

**Severity:** MEDIUM

**Spec reference:** v2 design §L2 run surface, `RunHeader.tsx VersionMenu` row:
"Fix the live defect: it passes a tag name to `onSelectVersion`, but
`PreviewPanel.handleSelectVersion` treats it as a run id → `findIndex` returns
-1 and `getWorkflow('v2')` fails into a `console.warn`."

`e7305f9` shows `PreviewPanel.tsx` with 25 lines changed. This is a live defect
fix (v2 Requirement 9 AC 1–3). The original `specs/019-sandbox-git-versioning`
spec does not name this defect — it was found during the v1 implementation gap
audit. The fix is included in `e7305f9` correctly.

**What is missing (traceability only):** The fix is implemented but it
originates from a bug discovered post-v1 and is not traceable to a requirement
in the original spec. The `.planning/ISSUES-REGISTER.md` should carry an
`ISS-###` entry for this pre-existing defect so it can be tracked independently
of the spec.

---

## ISSUE-017 — `Badge.tsx` / `Badge.degraded.test.tsx` added but not in the component map

**Severity:** LOW

**Spec reference:** v2 design §L2 — degraded-run status treatment; v2 Task 11.5.

`e7305f9` shows `frontend/src/components/ui/Badge.tsx` (30 lines changed) and a
new `Badge.degraded.test.tsx` (80 lines). These are legitimate deliverables of
the degraded-run visual treatment (v2 Requirement 20 AC 5), but the component
map lists the degraded treatment as a change to `RunHeader.tsx` / family chip,
not a standalone `Badge.tsx` change. The badge change is the mechanism, but it
is not a named component in the map.

**What is missing:** The v2 normative map should name `Badge.tsx` under the
degraded-status requirement, or a note confirming the badge change is the
implementation of the unnamed "distinct non-color indicator" requirement.

---

## ISSUE-018 — `LaneRunHeader.tsx` changed and tested but not in the component map

**Severity:** LOW

**Spec reference:** Same normative map rule.

`e7305f9` shows `frontend/src/components/chat/LaneRunHeader.tsx` (6 lines) and
a new `LaneRunHeader.test.tsx` (18 lines). Not named in either component map.

---

## ISSUE-019 — v1 spec states `PLANNER.md` write must move; implementation correctness unverified

**Severity:** MEDIUM

**Spec reference:** Original spec "engine.py:2221 PLANNER.md write — Must run
AFTER clarify rounds merge at :2339"; v1 Requirement 30; v1 Task 9.4
"Move PLANNER.md write to after clarify rounds merge".

v1 Task 9.4 is marked `[x]`. The `engine.py` diff in `24f1127` shows 791 lines
added, which includes seam changes. However, there is no dedicated test in the
v1 or v2 test suite that specifically asserts the PLANNER.md write ordering
relative to clarify-round merging. The v2 `test_prompt_ledger_v2.py` (1141
lines) covers ledger rows but does not name the PLANNER.md ordering assertion
as a distinct test case.

**What is missing:** A test asserting that after a clarify gate fires and
returns, `PLANNER.md` contains the merged clarification answers — not the
pre-clarify plan content.

---

## ISSUE-020 — `run_commands.py` v1 `source_run_id` write requirement conflicts with v2

**Severity:** HIGH (correctness)

**Spec reference:** Original spec FR-020 / v1 Requirement 22 AC 1: "`WorkflowRun.source_run_id` SHALL be written when launching a chained run"; v2 Requirement 2 (V2-Q1): "`source_run_id` is a read-only workflow-chaining edge and never changes physical sandbox identity."

The v1 spec required writing `source_run_id` for the first time (v1 Task 7.2,
`24f1127`). This is correct. The v2 spec narrows the contract: `source_run_id`
is **never** followed for sandbox resolution, and `_find_chain_root` in `engine.py`
walking `source_run_id` was named Defect D1.

The `e7305f9` diff deletes `_find_chain_root` and replaces it with
`resolve_revision_root` (walks `parent_run_id` only). The v2 Tasks 3.1 and 3.2
are both marked `[x]`.

**Residual gap:** v2 Task 3.2 requires deleting `engine.py _find_chain_root`
**and** `run_files.py _resolve_chain_root` **and** folding
`run_commands.py _revision_chain_root_id` into the canonical resolver. The
`e7305f9` diff shows `run_commands.py` with 1172 lines changed, which
is consistent with this work. However, there is no explicit test asserting that
zero calls to a `source_run_id`-based walk remain in the codebase after the
change. The `test_sandbox_identity_v2.py` tests the resolver outcomes but does
not assert the deletion of the old walkers. A grep-level static check was
required (v2 Task 3.2 says "Delete the duplicate walks") but this was not
automated into a test.

---

## ISSUE-021 — Windows `flock` silent no-op not addressed for the family lock

**Severity:** HIGH (correctness on Windows CI)

**Spec reference:** v2 design §L4, `run_files.py _manifest_lock`:
"Note: `fcntl is None` on Windows makes it a silent no-op, so the family lock
must not be built on the same mechanism"; v2 Task 3.9.

v2 Task 3.9 explicitly flags this: "The only cross-process lock in the codebase
today is a POSIX `flock` that silently no-ops on Windows — the family lock needs
a mechanism that holds on both platforms and cannot reuse it."

The `e7305f9` diff adds `backend/app/agents/sandbox.py` with 1391 lines. The
family lock implementation is here, but without reading the implementation in
detail it cannot be confirmed from the diff alone that the lock uses a
platform-safe mechanism. The system information shows this workspace runs on
**Windows (win32)**, making this a live concern for local development and Windows
CI agents.

**What is missing:** Explicit verification (test or CI assertion) that the
`FamilyLock` mechanism works correctly on Windows, not just on POSIX systems.
The `test_family_lock.py` (1227 lines) tests lock semantics but may rely on
subprocess behavior that differs between platforms.

---

## ISSUE-022 — `conversation_history/` reserved path present in gitignore but absent from spec

**Severity:** LOW

**Spec reference:** v2 Requirement 18, `RESERVED_PATHS` definition; v2 Task 2.1.

The v2 `local.py` `_GITIGNORE_PATHS` contains `conversation_history/` — the v2
design notes this as "the proof of drift" (the one entry not in the original
eight). The v2 Tasks 2.1 and 2.2 require deriving every enforcement point from
the `RESERVED_PATHS` registry, which includes `conversation_history/` as a
10th path (the original spec named only 8, v2 names 9 + `.chain-legacy/`).

The original spec `specs/019-sandbox-git-versioning/spec.md` does not mention
`conversation_history/` anywhere. This path was added to `.gitignore` at some
point between the original spec authoring and v1 implementation, creating an
undocumented reserved path.

**What is missing:** A record (in the migration ledger or the original spec
reports) of when `conversation_history/` was added and which feature owns it.
The reserved-path registry is the single source of truth, but the ninth path
has no originating requirement.

---

## ISSUE-023 — `test_phase3_cutover_verify.py` and `test_phase7_seam2_removal.py` are stubs

**Severity:** MEDIUM

**Spec reference:** v1 Task 5.11 (Phase 3 tests); v1 Task 9.6 (Phase 7 tests).

The `e7305f9` diff shows:
- `test_phase3_cutover_verify.py` — **18 lines** (stub)
- `test_phase7_seam2_removal.py` — **34 lines changed** (partial update)

These are extremely small files for the scope of requirements they cover.
`test_phase3_cutover_verify.py` (18 lines) is a nearly-empty file for what was
supposed to be Phase 3's full acceptance test suite (v1 Task 5.11 lists 6
distinct test assertions). The `test_phase7_seam2_removal.py` at 34 changed
lines is far below the scope needed to cover v2 Task 10.8's 30-ledger-row
prompt test matrix.

The comprehensive v2 test files (`test_prompt_ledger_v2.py` 1141 lines,
`test_retry_recipients_v2.py` 738 lines) exist and may cover the same ground.
But the v1 phase-named files remain as stubs that could mislead reviewers into
thinking phase 3 / phase 7 acceptance tests are satisfied by those files alone.

**What is missing:** Either the v1 phase test stubs should be deleted (tests
absorbed into the v2 files) or expanded to their required scope. Stubs with 18
lines marked `[x]` violate v2 Requirement 1 AC 3.

---

## ISSUE-024 — `test_rollback_safety.py` exists (851 lines) but rollback scenario not in original spec

**Severity:** LOW (documentation gap)

**Spec reference:** v2 Requirement 17 AC 18 (rollback safety); v2 Task 12.6.

The `e7305f9` diff includes `test_rollback_safety.py` (851 lines). The original
spec `specs/019-sandbox-git-versioning/spec.md` has no rollback requirement.
The v2 spec adds rollback safety as Requirement 17 AC 18 — this is a v2-only
requirement, not present in v1 or the original spec.

This is correctly implemented in v2. It is noted here because the original spec
`specs/019-sandbox-git-versioning` should be updated (or have a linked addendum)
acknowledging that v2 introduced new requirements not in the original spec, so
future maintainers understand the scope evolution.

---

## Summary Table

| # | Title | Severity | Status |
|---|-------|----------|--------|
| 001 | Two partial release-gate gaps unresolved (`SGV2-GAP-005`, `SGV2-GAP-017`) | HIGH | Open |
| 002 | v1 checkboxes set without behavioral verification — five defects shipped | HIGH | Root cause known; v2 addresses |
| 003 | Seam 2 removal incomplete — ~88 AGENT.md files unmigrated, seam code not deleted | HIGH | Open |
| 004 | `root_run_id` optional column not implemented and no recorded decision | MEDIUM | Open / deferred |
| 005 | Disk-growth instrumentation (`test_phase4.py` v1 Task 4.7) not confirmed live in v2 | MEDIUM | Open |
| 006 | `LaunchWizard.test.tsx` only 7 lines changed vs. full v2 coverage requirement | MEDIUM | Open |
| 007 | `GAPS.md` left at repo root after v2 superseded it | LOW | Open |
| 008 | Steering file head updated in a separate commit, not atomically with migrations | LOW | Resolved by `2d54f5d` |
| 009 | v1 tasks.md Alembic head note is internally inconsistent | LOW | Documentation |
| 010 | `Step.replaces` reconciliation path not specifically tested | MEDIUM | Open |
| 011 | Prompt viewer fix meaningful only after full Seam 2 migration | MEDIUM | Open (blocked by #003) |
| 012 | `WorkflowHistory.tsx` 114-line change outside normative component map | LOW | Open |
| 013 | `deep_agent_runner.py` 198-line change outside normative component map | MEDIUM | Open |
| 014 | `StepsOverviewSpine.tsx` change outside normative component map | LOW | Open |
| 015 | `RunChatLane.tsx` change outside normative component map | LOW | Open |
| 016 | `PreviewPanel.tsx` live defect fix not in original spec / ISSUES-REGISTER | MEDIUM | Open |
| 017 | `Badge.tsx` change not in normative component map | LOW | Open |
| 018 | `LaneRunHeader.tsx` change not in normative component map | LOW | Open |
| 019 | `PLANNER.md` write ordering after clarify merge has no dedicated test | MEDIUM | Open |
| 020 | No automated assertion that `source_run_id`-based sandbox walks are fully removed | MEDIUM | Open |
| 021 | Family lock platform safety on Windows not explicitly verified by tests | HIGH | Open |
| 022 | `conversation_history/` reserved path undocumented in original spec | LOW | Open |
| 023 | `test_phase3_cutover_verify.py` (18 lines) and `test_phase7_seam2_removal.py` are stubs | MEDIUM | Open |
| 024 | `test_rollback_safety.py` tests v2-only requirement not in original spec | LOW | Documentation |
