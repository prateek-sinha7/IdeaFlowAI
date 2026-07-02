# Revision Families & Run-Inputs Surfacing — Plan of Record

**Date:** 2026-07-02 · **Branch:** `new-workflow-engine` · **Status:** APPROVED — execution via GSD (A → B → C; D parked)
**Driver:** three user-reported platform gaps: (1) revision runs are disconnected from the workflow they revise; (2) the original user prompt/brief is invisible after launch; (3) clarify Q&A is not visible anywhere after answering.
**Investigation:** own digging + 3 parallel deep-dive agents (backend revision architecture, FE surfaces, brief/clarify data flow), every load-bearing claim re-verified against source. All file:line anchors below are verified as of this date.

---

## §0 Executive summary

All three gaps are **read-surface gaps, not storage gaps**. The data model already holds everything needed:
`WorkflowRun.parent_run_id` (indexed self-FK), `WorkflowRun.input` (verbatim untruncated brief, NOT NULL), per-round `kind="clarifications"` ArtifactRefs, `derived_from` artifact lineage, and the never-consumed `GET /api/runs/{id}/artifacts` endpoint.

The fix is three workstreams — **zero migrations, zero kernel/engine edits, zero new WS event types**:

- **A (backend read surface):** ownership-harden the parent-link ingress (IDOR fix), expose `parent_run_id` + server-computed `root_run_id`, add `GET /api/runs/{id}/family`, add a `kind` filter to the artifacts endpoint.
- **B (revision families FE):** universal lineage sending, reliable `contentSourceRunId`, history family grouping, version timeline in detail view, live version chip, base-version Files section.
- **C (run-inputs surfacing FE):** StartingPointCard + ClarificationsCard in Thinking, `prompt.md` + `clarifications.md` rows in Files, artifacts fetcher, live clarify retention, shared `parseRunInput` lib.
- **D (parked, separate decision):** retire FE content-inlining for revisions (server-side parent seeding). Explicit INV-3 fence: `prototype_revision` is a characterization golden — its mechanism is untouchable in D.

---

## §1 Root causes (verified)

### Gap 1 — Revision disconnect
- `parent_run_id` set reliably only by `run_revision` (`app/api/websocket.py:2247-2253`). The inline path links it **type-agnostically** when the FE sends `source_workflow_run_id` (`websocket.py:730` ingress, `:1685-1695` FK-check) — but only the live prototype revise handler sends it (`frontend/src/components/layout/DashboardLayout.tsx:520`). user_stories/app_builder/ppt-fallback revisions and **all history-launched revisions** (`DashboardLayout.tsx:1251-1286`) send nothing → orphan runs.
- `WorkflowRunResponse` (`app/api/runs.py:88-110`) omits `parent_run_id`; **no family/children endpoint exists** (list filters only `type`/`status`, `runs.py:116-144`).
- Artifact lineage is correct: the revised ref is written **under the revision run** with `derived_from=original.id`, `workspace_id=original.workspace_id`, `visibility="workspace"` (`engine.py:4646-4675`). FR-014 chain lookup is parent-run-scoped: exact kind → `deliverable` → `summary` (`engine.py:4475-4500`). `ArtifactRef.version` is per `(run_id, kind)` (`agents/authz.py:171-184`) — restarts at v1 per run, so cross-run versions must be synthesized from the run chain.
- Both revision paths write their own contiguous `run_events` and get a terminal `kind="deliverable"` ref (`engine.py:2204-2229`); the revision run holds BOTH the exact-kind ref and the deliverable ref intentionally.
- FE: history renders flat "(Revised)" siblings (`WorkflowHistory.tsx:84-97` TYPE_META); live revisions swap content with no version affordance; `currentWorkflowRunId` is a fragile type+status heuristic (`DashboardLayout.tsx:447-449`, incl. a `prototype_revision_revision` never-match). `parent_run_id` is write-only in the FE (sent at `:464`, never read back — absent from `types/index.ts:273-305`).
- `WorkflowRun.source_run_id` (`app/models/workflow.py:60`) is a **dead column** — never written, never read. Lineage = `parent_run_id` exclusively.
- Deleting a parent nulls children's `parent_run_id` (`runs.py:334`) — orphans become standalone.

### Gap 2 — Brief invisible
- `WorkflowRun.input` stores the verbatim full brief with no truncation (`websocket.py:671` → `:1706`); revision runs via `run_revision` store the clean instruction (`websocket.py:2257`); inline revisions store the composed `=== EXISTING … === / === REVISION REQUEST === …` blob.
- The API returns `input` on list + get (`runs.py:95`), but **no FE surface renders it**: FilesTab has no brief row (`components/results/FilesTab.tsx`); AgentThinkingTab has no starting-point card; the live dashboard does not retain the submitted message in any state (`app/dashboard/page.tsx:1284-1302` passes it through and drops it). Only `title[:60]` (`websocket.py:1703`, later LLM-overwritten) leaks a fragment.
- `planning_context` IS persisted as an artifact (`engine.py:2359-2368`) but carries only a `BRIEF_MAX_CHARS`-capped `user_request` copy (`smart_planner.py:399-401`) — `run.input` is the canonical full copy.
- Per-agent composed prompts ARE durable: the `agent_input` event (`engine.py:2633-2646`, in run_events) and `agent_outputs[].input_prompt` (`websocket.py:1832-1833`).

### Gap 3 — Clarify Q&A invisible
- Fully persisted twice: (a) per-round `kind="clarifications"` ArtifactRefs — content = JSON list of `{question_id, question_text, impact_level, answer, round}` (`clarify_engine.py:790-828`, `force_db_version=True`, DB-only via a throwaway graph); (b) `questionnaire_ready`/`questionnaire_complete` events durably in `run_events` (clarify events are yielded through `execute()`'s single stamped sink, `engine.py:1621-1633` + `:824-838`).
- `_persist_qa` fires once per answered round (`clarify_engine.py:286`); no-questions → early return, no row (`:247-250`); no auto-timeout path exists (Human_Gate waits indefinitely); "skip all & run" still persists that round's submitted answers first.
- `GET /api/runs/{id}/artifacts` (`runs.py:669-716`, node shape `:590-608` — note: **no `created_at` on nodes**) has **zero FE consumers** (`lib/api.ts` has no artifacts fetcher).
- FE wipes Q&A on submit (`DashboardLayout.tsx:1033-1050` clears `questionnaireQuestions`; QuestionnairePanel local state dies on unmount). `PipelineRunState` has no clarifications field (`types/index.ts:497-528`).

---

## §2 Design decisions (locked) & rejected alternatives

| # | Decision | Rejected alternative — why |
|---|----------|---------------------------|
| D1 | **Keep the child-run model; unify at the read/UX layer** as a "workflow family" (chain of runs linked by `parent_run_id`) | Folding revisions into the parent run — fights the state machine terminals, seq counter, checkpointer threads, Phase-14 terminal-status fidelity. A terminal run stays terminal. |
| D2 | **Version = 1-based chronological index within the family** (`created_at` ASC; root is earliest by construction). Branching-safe: members carry `parent_run_id` so the UI shows "revises v{n}" badges | Depth-based indexing (two branches both "v2" — confusing); repurposing `artifact_refs.version` (per `(run_id, kind)` by design). |
| D3 | **Brief single-sourced in `run.input`** — surfacing only, no new storage | A run-start `kind="brief"` artifact — INV-12 dual storage; for `run_revision`, `execute()` receives the composed internal context, not the user's input, so an engine-side write would persist plumbing. |
| D4 | **Clarifications single-sourced in the existing refs** — surfacing via the existing artifacts endpoint + live FE retention | New tables/columns/events — redundant. |
| D5 | **Zero new WS event types** | New events enter the golden event multiset — the one confirmed INV-3 tripwire (goldens = deliverable bytes + normalized event multiset ONLY; run-row/DB/API fields are NOT golden-tracked; harness drives the engine directly, never websocket). |
| D6 | **Ownership keyed on `user_id`** for all new checks/walks (the Phase-13 CR-01 precedent — never the nullable backfilled `owner_id`) | — |
| D7 | **`root_run_id` computed server-side** and returned on list+get; FE groups by a plain field | Client-side family grouping — pagination-split families group wrongly; lineage logic would live in two places. |
| D8 | **`kind` filter param on the artifacts endpoint** for precise fetches | `include=content` over the whole tree just to read a 2 KB Q&A — wasteful over-fetch. |
| D9 | `source_run_id` stays dead — do not repurpose | Dual lineage columns. Separate cleanup-migration decision later. |

## §3 Security corrections (non-optional, part of Workstream A)

The existing `source_workflow_run_id` ingress check (`websocket.py:1685-1695`) and the `run_revision` row-creation check (`websocket.py:2247-2253`) verify the parent row **exists**, not that the caller **owns** it. Engine-level `assert_owns` already protects content reads — but a foreign `parent_run_id` ROW linkage would let the new family walk leak foreign run metadata. Therefore:

1. **Both ingress sites link `parent_run_id` only when the parent exists AND `WorkflowRun.user_id == current user`.** Dispatch behavior unchanged (engine `assert_owns` at `engine.py:4455` stays the content gate).
2. **Every step of any family/root walk filters `user_id == current_user.id`** — a non-owned/missing parent terminates the chain (root = last owned ancestor). 404-not-403 posture throughout.

---

## §4 Workstream A — backend read surface (app-layer only: `app/api/runs.py` + `app/api/websocket.py`)

**Scope fence:** ZERO edits under `backend/agents/`, ZERO migrations, ZERO new WS events, ZERO FE.

1. **Ownership hardening** at both parent-link ingress sites (§3).
2. **`WorkflowRunResponse` additive fields** (list `:116` + get `:263`):
   - `parent_run_id: Optional[str]` — verbatim column.
   - `root_run_id: str` — owned-walk terminal (standalone run → own id; foreign/missing parent terminates the walk). Implementation freedom: memoized in-Python walk with batched parent fetches OR recursive CTE — must be correct on SQLite (tests) and Postgres (prod); a ≤100-row page with mostly-NULL parents must not regress list latency.
3. **NEW `GET /api/runs/{id}/family`** — owner-scoped (`user_id`), cross-owner/missing → 404. Resolve root (owned walk + cycle guard via visited set), collect ALL owned runs whose chain-root == root, return:
   `{root_id, members: [{id, type, title, status, revision_index, parent_run_id, created_at, completed_at}]}` ordered `created_at` ASC, `revision_index` = 1-based position.
4. **`kind` query param on `GET /api/runs/{id}/artifacts`** — filters refs by exact kind BEFORE tree-building; composes with `include=content`; no param → byte-identical current behavior; unknown kind → empty list (not 422).

**Tests (backend/tests/unit/):** family chain order; revision-of-revision depth; branching (two children of one root); orphan-after-parent-delete = own root; IDOR 404; foreign-parent-in-chain terminates walk; ingress hardening both sites (foreign source id → NOT linked; owned → linked; run_revision dispatch behavior unchanged); `parent_run_id`/`root_run_id` present on list+get; kind filter (filtered tree + no-param parity + unknown-kind empty).

**Gates:** 5 characterization goldens byte/event-identical (`SNAPSHOT_UPDATE` unset, targeted suite — full pytest hangs offline) · `/opt/homebrew/bin/lint-imports` 4 kept / 0 broken · new tests green (`python3.11`, no venv).

## §5 Workstream B — revision families FE

1. **`contentSourceRunId`** state in DashboardLayout: the run id that produced the on-screen content — set from `pipeline_complete.data.pipeline_run_id` (live) and `fullRun.id` (reopen). **Replaces** the `currentWorkflowRunId` heuristic everywhere (`:447-449`), incl. the `run_revision` `parent_run_id` field (`:464`).
2. **Universal linkage:** all four inline revise handlers (`:454-533`) pass `{source_workflow_run_id: contentSourceRunId}` as `startPipeline`'s existing 6th context arg (`useWorkflow.ts:34-102`, `Object.assign(payload, context)`). History `onRevise*` callbacks (`WorkflowHistory.tsx:39-42`) gain the run id: `(instruction, content, sourceRunId)`; handlers at `:1251-1286` thread it identically.
3. **History list:** group rows by `root_run_id` (plain field from A) — one card per family root, "v{N}" pill + latest status dot; expandable version rows (v-chips, timestamps, status dots from existing STATUS_COLOR maps, "↳ revises v{n}" microcopy).
4. **History detail:** version timeline fed by `/family` — chips row above the tab bar (active filled, siblings ghost, status dots); switching loads that run (`getWorkflow`) into the SAME detail surface (Preview/Files/Thinking/Audit switch together, existing motion.div transition). Revision versions show "↳ Revises v{n-1} — '{instruction preview}'".
5. **Live version chip:** compact "v{n} ▾" pill in the preview header beside Copy/Collapse once the current content belongs to a family (fetch `/family` when `contentSourceRunId` resolves / after a revision completes); dropdown lists versions; older selection → read-only amber banner "Viewing v{k} — Back to latest →"; on revision complete the pill ticks with a subtle pulse.
6. **Files tab of a revision version:** collapsed "From v{n-1}" section, lazy-fetching the parent run's files via `getWorkflow(parentId)`.
7. **New fetcher:** `getRunFamily(token, id)` in `lib/api.ts`; FE `WorkflowRun` type + `normalizeWorkflowRun` gain `parentRunId`/`rootRunId`.

**Gates:** `tsc --noEmit` clean · vitest (grouping, timeline switch, chip, linkage payload includes source id) · goldens untouched (FE-only) · optional mocked Playwright spec.

## §6 Workstream C — run-inputs surfacing FE

1. **Shared parser `lib/runInput.ts`** — `parseRunInput(input) → {brief, attachments[], revisionInstruction?, existingArtifactBlock?, chainContext?, preferences?}`. Single home for ALL FE-owned marker families (replaces the duplicated `safeCleanBrief` logic at `DashboardLayout.tsx:909-925`/`:993-1001`):
   - `=== Attached: {name} === … === End: {name} ===` (`IdeaInputPage.tsx:542-554`)
   - `=== EXISTING {X} === … === END {X} ===` + `=== REVISION REQUEST === … === END REQUEST ===` (inline revisions)
   - `=== CONTEXT FROM PREVIOUS PIPELINE ({type}) ===` (chaining)
   - `=== USER PREFERENCES ===` (legacy questionnaire fallback)
   - Format-tolerant: clean instruction-only input (post-D) passes through unchanged; legacy blobs decompose correctly (formats stable since Phase 3).
2. **Live retention:** `submittedBrief` captured in the `onStartPipeline` wrapper (`page.tsx:1284-1302`), reset per run. Reopen/history use `fullRun.input` / `selectedRun.input`.
3. **Thinking tab — `StartingPointCard`** rendered BEFORE PlannerCard (insertion slot `AgentThinkingTab.tsx:620`), props-driven (renders on reopen where `pipelineState` is absent): typed brief line-clamped with Show-more; attachment chips ("📎 {name} — {n} chars", expandable); revision variant = instruction primary + "Original brief (v1)" expander (root id from `/family`, lazy `getWorkflow`).
4. **Thinking tab — `ClarificationsCard`** after PlannerCard: per-round groups, Q medium-weight, A filled line, impact badges (existing clarify-amber convention). Timeline narrative: Starting point → Planner → Clarifications → Agents → Complete.
5. **Clarify types + retention:** `ClarifyRound = {round, qa: [{question_id, question_text, impact_level, answer}]}`; `PipelineRunState.clarifications?: ClarifyRound[]`. In `handleQuestionnaireSubmit` (`DashboardLayout.tsx:1033`) fold `questionnaireQuestions` + `responses` into run-scoped state BEFORE clearing; reset on `pipeline_start`. The ClarificationsCard appears the moment answers are submitted (answers visibly land, never vanish).
6. **Reopen source:** new fetcher `getRunArtifacts(token, id, {kind, includeContent})` → `GET /api/runs/{id}/artifacts?kind=clarifications&include=content`; parse JSON rounds. Fetched on history-detail open + dashboard reopen.
7. **Files tab:** new "Run input" section (same section idiom as "Agent outputs"), reusing the exact FileItem row: `prompt.md` (parsed brief; raw downloadable) + `clarifications.md` (rendered Q&A markdown; only when rounds exist). Fully type-agnostic — no workflow-name branch.
8. Both mounts thread the new props: live `PreviewPanel.tsx:632/644`, history `WorkflowHistory.tsx:709/715`.

**Gates:** `tsc` clean · vitest (parser families incl. legacy blobs, StartingPointCard variants, ClarificationsCard, Files rows, retention survives panel unmount) · goldens untouched.

## §7 Brief semantics per launch path (the parseRunInput contract)

| Path | `run.input` contains | User sees |
|---|---|---|
| Normal run | Typed brief + `=== Attached: … ===` blocks | Brief clean; attachments as collapsed chips; `prompt.md` full structured |
| `run_revision` (ppt/od_ppt) | Clean instruction (`websocket.py:2257`) | "Revision request" + v{n} badge + "Original brief (v1)" expander |
| Inline revision | Composed `=== EXISTING X === / === REVISION REQUEST ===` blob | Instruction primary; base content collapsed ("Base content (v{n-1})"); real base one click away via timeline |
| Chained run | Brief + `=== CONTEXT FROM PREVIOUS PIPELINE ===` | Brief primary; chain context collapsed chip |
| Legacy runs | Same formats (stable since Phase 3) | Parser works retroactively, zero backfill |
| Post-Phase-D | Instruction-only | Pass-through unchanged |

## §8 UI/UX contract (reuse-first — the Phase 20/21/22 UI-SPEC discipline)

- **No new visual language**: every node names its existing analog (PlannerCard idiom for the two new Thinking cards; FileItem row for Files rows; existing badge/pill/STATUS_COLOR/motion patterns for chips/timeline/expansion). Net-new styling is a defect.
- **A11y:** version switcher = `radiogroup` with aria-labels + keyboard nav; focus managed on version switch; icon-only controls carry `aria-label`.
- Phases B and C each start with `/gsd-ui-phase` generating a UI-SPEC.md and end with `/gsd-ui-review` (6-pillar audit).

## §9 Workstream D — parked (separate decision; do NOT start without one)

Retire FE content-inlining for `user_stories_revision`/`app_builder_revision`/ppt-fallback: `previous_run` provider resolves the parent deliverable from `artifact_refs` via `parent_run_id` (the FR-014 pattern), FE sends instruction-only, delete the od_ppt inline fallback (`DashboardLayout.tsx:475-489`). Kills the 40k/60k truncation; makes `run.input` a clean instruction everywhere; retires the `===` marker convention.
**Fences:** `prototype_revision` is a characterization golden with pinned `context_message` bytes (`previous_run.py:85-88` extraction) — untouchable without a deliberate re-baseline decision; D scopes to the non-golden revision types only. Capability-layer work (not kernel) with its own verified phase.

## §10 Invariants audit

- **INV-3:** zero engine edits (A–C touch no `backend/agents/` file); zero new events; goldens assert deliverable bytes + normalized event multiset only and drive the engine directly (verified — no artifact/DB/run-row assertions anywhere in the harness). Battery still RUN as proof each workstream.
- **SC-001/INV-1:** kernel untouched; family logic keys on `parent_run_id` + the generic `_revision` suffix idiom; FE additions type-agnostic.
- **INV-12:** no dual storage (brief only in `run.input`; clarifications only in refs). Net-negative duplication: heuristic replaced by `contentSourceRunId`; three FE parser copies → one lib.
- **Q3:** zero migrations — every column/table exists.
- **Ports & Adapters:** app-layer + FE only → `lint-imports` 4/0 by construction.
- **Known debts consciously carried through A–C** (pre-existing, each with retirement line): FE content-inlining + truncation (→ D); `===` marker convention parsed FE+BE (→ D retires; C consolidates FE side); PPT dual revision path (→ D deletes fallback); dead `source_run_id` (→ separate cleanup decision).

## §11 Edge cases & limitations

- Deleted parent → children's `parent_run_id` nulled (existing) → own family roots; `/family` handles gracefully.
- Legacy revision runs with NULL parent → standalone families; **no backfill possible** (linkage never captured) — honest.
- Branched families (revise v1 twice) → chronological v-numbers + "revises v{n}" badges carry the structure.
- Artifacts endpoint nodes have no `created_at` — clarify rounds order by the content's `round` field (sufficient); optional additive node field later if needed.
- Clarify rounds exist only when clarify actually ran (gate `CLARIFY_REQUIRED` + user answered) — a `PROCEED` run correctly shows nothing.

## §12 GSD execution shape

| Order | Entry | Vehicle |
|---|---|---|
| 1 | **A — backend read surface** | `/gsd-quick --validate` (this doc §3+§4 is the spec) |
| 2 | **B — revision families FE** | Full GSD phase: `/gsd-ui-phase` UI-SPEC → plan → execute → `/gsd-ui-review` |
| 3 | **C — run-inputs surfacing FE** | Full GSD phase, same treatment, after B (shares tab surfaces) |
| — | **D** | Not queued; requires a separate decision |

Sequencing is strict: B consumes A's API fields; C reuses B's version context in the tabs.
