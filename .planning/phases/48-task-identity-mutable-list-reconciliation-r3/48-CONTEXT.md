# Phase 48: Task Identity & Mutable-List Reconciliation [R3] - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Source:** POR Ingest Express Path (`.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §5.1/§5.2/§6-R3/§8 Q2+Q3 — DECIDED: automatic reconciliation; versioned `task_list` artifact, no new table)

<domain>
## Phase Boundary

Upgrade task identity from POSITIONAL (Phase 46's `str(task_num)`/`worker_index`) to CONTENT-ADDRESSED (`task_key`), and make the task list safely user-editable with FULLY AUTOMATIC reconciliation on resume and on re-run-after-edit. Three requirements: RESUME-14 (the namespaced `task_key`), RESUME-15 (task list = versioned `task_list` artifact edited via the EXISTING gate-Edit mechanism), RESUME-16 (automatic skip/run/exclude reconciliation).

OUT of scope (hard fences): any new table or REST surface for tasks (the edit path IS the gate-Edit action; a richer FE task editor is future work, NOT this phase); uploads (47, done); gate re-arm / KAN-88 red (49); resume-from-failed endpoint (50); FE changes of any kind; deleting/mutating any `artifact_refs` row (immutability absolute — exclusion is READ-side only).

</domain>

<decisions>
## Implementation Decisions

### RESUME-14 — the task_key (LOCKED)
- `task_key = sha256(upstream_context_hash · normalized_task_content · occurrence_ordinal)`:
  - `upstream_context_hash` — derived from the SORTED upstream `content_hash`es the step consumed, reusing the existing `input_hash` discipline/machinery (`engine.py` `_compute_step_input_hash` region ~:5639-5733) — do NOT invent a second upstream-hashing scheme (INV-12); factor/reuse.
  - `normalized_task_content` — the task's own text (title+body as parsed), whitespace-normalized deterministically.
  - `occurrence_ordinal` — 0-based count of PRIOR tasks with identical normalized content in the same list (duplicate-text safety; the 12-06 WR-05 duplicate-guard precedent).
  - Hash discipline: sorted inputs, NO timestamp/uuid — cross-restart stable (register Pitfall 1).
- Going forward, task-granular writes carry the `task_key` in the EXISTING `task_id` slots (`artifact_refs.task_id` via the capture seam; `subagent_runs.task_id` via the 46-01 stamping) — no schema change (the columns are free String). **Backward compatibility (LOCKED fail-safe):** durable rows written under Phase-46 positional ids remain readable; reconciliation that cannot confidently map a legacy positional row to a current task treats it as NOT-completed (fail-safe = re-run, never skip-wrongly). No data migration of old rows.
- `worker_index` stays positional (audit-only, unchanged).

### RESUME-15 — the versioned task list + the edit path (LOCKED, Q3)
- The task list stays the `task_list` artifact. User edits ride the EXISTING gate-Edit mechanism (`_apply_declared_gate_edit`, KAN-98; `edited_content` via `POST /{id}/gate` ONLY — WR-03): an edit mints a NEW `task_list` version with `derived_from` lineage to the prior version; old versions kept forever; `max(version)` wins on every read (`_latest_typed_content` F5 discipline). NO new table (the 12-era "no new step-status table" lock), NO new endpoint, NO FE work.
- This phase's RESUME-15 work is therefore mostly VERIFICATION + gap-closure of the existing path for the task_list kind specifically: prove an edited task_list version is what the strategy re-parses (max-version), prove lineage is stamped, and close any gap found (e.g. if the gate-Edit write path misses `derived_from` on this kind — fix in place).

### RESUME-16 — automatic reconciliation (LOCKED, Q2)
On resume OR re-run-after-edit (redo / update_specs / gate-Edit), the KERNEL reconciles the CURRENT (max-version) task list against completed `task_key`s — extending the Phase-46 cursor computation (`_compute_resume_completed_task_ids`), not forking it (INV-12):
- key present + completed → **skip**, re-materialize its artifacts (46-03 machinery), inject as prior context.
- key present + not completed (new task, edited text, or rotated upstream hash) → **run**.
- completed key absent from the current list (deleted/replaced) → **orphan**: excluded from context injection and from assembly — READ-side only, rows never deleted.
- Spec/upstream edit rotates `upstream_context_hash` → affected keys rotate → auto-re-run, NO confirm prompt (Q2: fully automatic).
- **Cumulative vs independent flows (LOCKED distinction — falls out of the substrate):**
  - `task_loop` (cumulative single-file builds — each task EDITS the same evolving file): deleting or editing task k invalidates k and EVERYTHING AFTER it (the file state after task k embeds k's work). Reconciliation resumes from the last unaffected per-task version — re-materialize the deliverable's version as of the last common-prefix completed task (the per-task `html_file` versions from the capture seam make this exact), then run the remaining current-list tasks from there. The common-prefix rule: skip the longest prefix of the current list whose keys match completed keys IN ORDER; everything after the first divergence re-runs.
  - `wave_scheduler`/fan-out (independent per-task outputs merged later): per-key reconciliation exactly (skip completed, run new/edited, exclude orphaned fragments from the merge set).
- Fail-safe direction everywhere: ambiguity → run (never skip); orphan-exclusion ambiguity → keep-in-assembly is NOT allowed for confidently-orphaned keys, but an unmappable legacy row simply re-runs its task (which supersedes it naturally via versioning).

### Guardrails (LOCKED — POR §7 + standing)
- INV-1/SC-001: key computation + reconciliation key on generic parsed content/hashes/strategy — zero workflow/agent-name literals; the ROADMAP SC4 proof: a SYNTHETIC non-prototype task workflow exercises the full reconcile path with zero engine edits (the sc001 fixture idiom).
- INV-2 · INV-3 (goldens 10/10, `SNAPSHOT_UPDATE` unset — key computation/reconciliation DORMANT on non-resume, non-edited runs; the positional→key change in what gets WRITTEN to `task_id` must be proven golden-neutral: goldens never read task_id values, but PROVE it) · INV-5 · INV-12 (extend the 46 cursor + the existing input_hash machinery + gate-Edit — no parallel implementations) · INV-13.
- Phase 45/46/47 shipped behavior stays green (their tests are the regression floor); KAN-88 red untouched; pre-existing fails untouched; lint-imports 4/0.
- No migration. No new WS events. No FE changes.

### Execution constraints (LOCKED — standing)
- feat/ui-2 only · NO trailers · NEVER push · NEVER `git stash` · python3.11 no venv · ABSOLUTE cd to backend/ (stray backend/backend exists) · targeted pytest only · NO live Bedrock in executors · sequential.

### Claude's Discretion
- Where the key computation lives (a small pure module in the kernel resume tier vs functions beside `_compute_step_input_hash`) — one home, reused by capture-write, cursor, and reconciler.
- The exact common-prefix implementation for cumulative flows and how "the deliverable version as of task k" is selected (the per-task version rows make several correct selections possible — pick the simplest provable one).
- Whether wave task `t.id` values become task_keys at parse time (json_tasks ids are author-chosen — the key can wrap/namespace them) — keep `build_waves`' duplicate-id guard semantics intact.
- Plan decomposition (likely 2-3 plans: key module + write-path switch · reconciler task_loop/cumulative · reconciler wave/independent + SC-001 synthetic proof).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` — POR §5.1/§5.2/§6-R3/§7/§8 Q2-Q3. READ FULLY.
- `.planning/ROADMAP.md` — "### Phase 48" block (4 success criteria) + v3.0 header.
- `.planning/REQUIREMENTS.md` — RESUME-14/15/16.
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 12 (D-10..D-12 input_hash discipline + Pitfall 1; WR-05 duplicate-id guard; the "no new step-status table" lock), Phase 23 (redo: task_list v1→v2 `derived_from` lineage, `_latest_typed_content` max-version F5, `_apply_declared_gate_edit` WR-04, KAN-98), Phase 44 (WR-03: `edited_content` rides `/gate` only), Phase 27 (update_specs — the spec-edit flow whose rotation this phase must honor).
- Phase 45/46/47 folders — the shipped completeness fix, cursor (`_compute_resume_completed_task_ids`), capture seam, re-materialization (46-03), and their SUMMARYs/VERIFICATIONs (fresh anchors).
- Code: `backend/agents/execution_engine/engine.py` (`_compute_step_input_hash` region, `_compute_resume_completed_task_ids`, `_first_incomplete_step` task_loop branch, `_rematerialize_artifacts_to_disk`, `_apply_declared_gate_edit`, `_latest_typed_content`), `backend/agents/execution_engine/kernel_services.py` (`persist_task_html` capture — where task_id values are written), `backend/agents/capabilities/strategies/task_loop.py` + `wave_scheduler.py` (parse + skip sites), `backend/agents/capabilities/task_parsers/heading_tasks.py` + `json_tasks.py` (normalization inputs), `backend/agents/execution_engine/fanout.py` (worker task_id threading), `backend/agents/authz.py`.
- Tests: `test_restart_resume.py` (the resume harness + Phase 45/46 cases), `test_per_task_capture.py`, `test_wave_scheduler.py`, `test_json_tasks.py`, `test_redo_gate_safety.py` (gate-edit adjacency — must stay green), the 5 characterization files, banned patterns, lint.

</canonical_refs>

<specifics>
## Specific Ideas

- The Phase-23 redo already produces task_list v2-supersedes-v1 with lineage — the reconciler's "current list" read is exactly `_latest_typed_content`-style max-version selection; reuse it.
- The fix-loop re-persists under the same task identity (46-02) — with keys, that becomes "same task_key re-versioned"; the distinct-key counting from Phase 45/46 carries over unchanged.
- `update_specs` (Phase 27) re-runs specify→plan→analyze producing a NEW plan/task_list — after this phase, resuming/continuing past an update_specs cycle should automatically re-run only what the new list demands (the rotation does this); add a test proving update_specs + reconcile compose.
- SC-001 synthetic proof: clone the sc001_task_loop fixture idiom — a non-prototype manifest + tasks, drive: complete 2 of 4 → edit the list (delete one completed, edit one pending, add one) → resume → assert exactly the right set re-runs and the orphan is excluded from context/assembly.

</specifics>

<deferred>
## Deferred Ideas

- FE task-list editor UI (drag/add/delete pre-launch or mid-gate) — future; the mechanism (gate-Edit → new version) is what this phase makes safe.
- Cascade-invalidation via `derived_from` lineage graphs beyond the upstream-hash rotation — the hash rotation covers the decided Q2 semantics; finer-grained lineage invalidation is future.
- Live-Bedrock edit→resume proof — milestone-end pass.

</deferred>

---

*Phase: 48-task-identity-mutable-list-reconciliation-r3*
*Context gathered: 2026-07-19 via POR Ingest Express Path (Q2 automatic + Q3 versioned-artifact DECIDED)*
