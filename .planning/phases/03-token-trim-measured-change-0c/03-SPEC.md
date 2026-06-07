# Phase 3: Token-Trim (measured change) [0C] — Specification

**Created:** 2026-06-07
**Ambiguity score:** 0.12 (gate: ≤ 0.20)
**Requirements:** 7 locked

## Goal

Wire the dead `_extract_html_skeleton` helper as build-task-2+ context compaction — replacing the full current-HTML block (up to 120k chars) in the `prototype-build` sub-agent prompt with a ~1–3k char skeleton — and prove a **≥50% reduction** in the task-2+ prompt input while holding **semantic parity** (same pages/routes, equal-or-better validation pass), not byte-identity.

## Background

`_extract_html_skeleton` (`backend/agents/execution_engine/engine.py:2616-2679`) is fully built but **never called** — ledger item **L13** (`☐` pending). It distills the full prototype HTML into a compact summary: `:root` design-token values, the `routes` map, the filled-vs-empty `data-page` section IDs, the chrome type, and total size (~1–3k chars vs 50k+).

The prototype per-task build loop (`_run_build_task_loop`, `engine.py:1478+`) runs one isolated sub-agent per task; after each task it reads `prototype.html` back into `accumulated_outputs["prototype-build"]`. `_build_context_message` (`engine.py:2511-2536`) already trims *some* tokens for build-task-2+ (`is_build_task_2_plus` — skips the DS body, template body, example.html, layouts/checklist) **but still injects the FULL current HTML** via the `--- CURRENT HTML (modify this …) ---` block (truncated at 120k). That full-HTML pass is the O(n²) prompt growth the skeleton was designed to kill.

This is the **one sanctioned non-byte-identical change** in the migration (INV-3 exception): altering the build prompt legitimately changes generated text, so the phase is gated on the **semantic** event snapshot + a **measured token delta** rather than deliverable byte-identity. `od_prototype` is an alias of `prototype` (`registry._OD_ALIAS_BASE`) and runs the same `prototype-build` path, so the change applies to both automatically.

Gating infrastructure already exists: characterization tests (deliverable byte snapshot + `_normalize`d semantic event snapshot in `backend/tests/agents/characterization/`), driven fully offline via `_scripted_model._drive`, which already runs a **2-task** prototype build (Task 1: HTML shell, Task 2: fill dashboard).

## Requirements

1. **Skeleton wired (COMPACT-01 / L13)**: `_extract_html_skeleton` is invoked on the build-task-2+ context path, replacing the full-HTML block.
   - Current: `_extract_html_skeleton` is defined but never called; `_build_context_message` injects the full current HTML (truncated 120k) for every build task, including tasks 2+.
   - Target: For `is_build_task_2_plus`, the `--- CURRENT HTML … ---` block is replaced by `_extract_html_skeleton(current_html)` output. Task 1 (HTML shell) is unchanged — it has no prior HTML.
   - Acceptance: A unit test on `_build_context_message` for a task-2 `prototype-build` context shows the skeleton markers present (`:root tokens`, `Pages already built`/`Pages still empty`, `Chrome:`, `Total HTML so far`) and the full `--- CURRENT HTML (modify this` block **absent**; an invocation/AST check confirms `_extract_html_skeleton` is reachable on the task-2+ branch.

2. **Deterministic token-reduction gate (COMPACT-03 / threshold)**: build-task-2+ input is ≥50% smaller.
   - Current: No measurement exists; the full HTML (up to 120k chars) is passed on every build task.
   - Target: A deterministic, fully-offline test compares the build-task-2+ context-message size produced with the skeleton vs the prior full-HTML behavior, on a representative multi-page HTML, and asserts ≥50% reduction.
   - Acceptance: A CI test passes asserting `len(compacted_task2_message) <= 0.5 * len(fullhtml_task2_message)` (chars, as an input-token proxy) for a ≥2-page prototype HTML; runs with no DB/Bedrock/API key.

3. **Real-run token-delta evidence (COMPACT-03 / measurement)**: a real multi-task build's token/cost delta is recorded.
   - Current: No recorded evidence of real-world token/cost savings from compaction.
   - Target: A real (live-model) prototype run of the multi-task build, before vs after compaction, has its accumulated input-token (and/or cost) delta recorded in the phase SUMMARY as evidence. This is live/manual evidence, **not** a CI gate (the CI gate is Requirement 2).
   - Acceptance: `03-*-SUMMARY.md` contains a concrete token/cost delta figure from a real multi-task build showing a reduction, with the reproduction command/live-test name documented.

4. **Semantic snapshot parity (COMPACT-02)**: the semantic event snapshot holds for prototype and od_prototype.
   - Current: Semantic event snapshots are green at the post-0B baseline (full-HTML prompts).
   - Target: After wiring, the `_normalize`d semantic event snapshots for `prototype` and `od_prototype` remain green — same event types, order, required data keys, and final-result shape; `seq` contiguous.
   - Acceptance: `test_prototype_event_snapshot` and `test_od_prototype_event_snapshot` pass with **no golden edit**; `assert_seq_contiguous` holds.

5. **Deliverable re-baseline (COMPACT-02 / sanctioned INV-3 exception)**: prototype + od_prototype byte-goldens re-recorded; all other pipelines byte-identical.
   - Current: `prototype.html` / `od_prototype.html` deliverable byte-goldens reflect full-HTML-prompt output.
   - Target: The prototype and od_prototype deliverable byte-goldens are re-recorded (via `SNAPSHOT_UPDATE=1`) to reflect compacted-prompt output, and the change is documented in the commit/SUMMARY as the sanctioned 0C exception. No other pipeline's deliverable golden changes.
   - Acceptance: Deliverable byte-snapshot tests for prototype/od_prototype pass against re-recorded goldens; `prototype_revision`, `od_ppt`, and `app_builder` (code-gen) deliverable goldens are unchanged (`git diff` touches only the two prototype goldens).

6. **Pages/routes + validation parity assertion (COMPACT-02)**: same pages/routes, equal-or-better validation.
   - Current: No dedicated assertion that the compacted build yields the same page/route set or an equal-or-better validation pass.
   - Target: A test asserts the page/route set produced under compaction equals the pre-compaction set, and the validation pass (static_check + render_check) is equal-or-better — no new validation failures introduced by compaction.
   - Acceptance: A test confirms the produced `data-page` ID set and `routes` map keys are identical before/after wiring, and the validation-pass event outcome/count is equal-or-better (zero net-new validation failures).

7. **read_file access preserved (HTML-access decision)**: the build agent can read the full HTML on demand.
   - Current: The build agent sees the full HTML inline in the prompt; `prototype-build` has native fs read tools but the prompt directs it to the inline HTML.
   - Target: With the inline full HTML removed for task 2+, the build sub-agent retains `read_file` access to `prototype.html` in the run sandbox, and the skeleton/prompt instructs it to read the file before editing when it needs full detail.
   - Acceptance: The `prototype-build` agent retains fs read tools on the task-2+ path (no tool-set change); the task-2+ context contains an explicit "read `prototype.html` for full detail before editing" instruction; a test confirms `read_file` remains available to the build sub-agent.

## Boundaries

**In scope:**
- Replace the full `--- CURRENT HTML … ---` block with `_extract_html_skeleton(current_html)` on the `is_build_task_2_plus` branch of `_build_context_message`.
- Leave task 1 (HTML shell) and all non-build agents unchanged.
- Add a deterministic offline CI test asserting ≥50% task-2+ prompt-input reduction (Requirement 2).
- Record a real-run token/cost delta in the phase SUMMARY (Requirement 3, live evidence).
- Re-baseline the prototype + od_prototype deliverable byte-goldens (the sanctioned change).
- Keep the prototype + od_prototype semantic event snapshots green.
- Add a dedicated pages/routes + validation-pass parity assertion.
- Ensure/keep `read_file` access to `prototype.html` on the task-2+ path + a read-before-edit instruction.
- Applies to both `prototype` and `od_prototype` (same `prototype-build` path via the od alias).

**Out of scope:**
- Registering `html_skeleton` as a `CompactionStrategy` capability — that is Phase 7 / PARITY-04 (re-express 0C behind the capability, behavior-preserving vs 0C).
- Deleting the inline `_extract_html_skeleton` or flipping ledger row **L13** to `☑` — L13's deletion gate (grep `_extract_html_skeleton` → 0) fires in Phase 7 (`0C→2`); 0C only *wires* it, so L13 stays `☐`.
- Manifests, compiler, typed artifacts, persistence, model policy — later phases (4+).
- Any change to `prototype_revision`, `ppt`/`od_ppt`, or code-gen deliverable bytes — those must stay byte-identical.
- Additional compaction tiers (Tier#2+) or compacting any non-build agent's prompt.
- Changing the 120k truncation constant or task-1 behavior (task 1 has no prior HTML to compact).

## Constraints

- **INV-3 sanctioned exception**: this is the only phase permitted to change a deterministic deliverable's bytes; it is gated on the **semantic** snapshot + measured token delta, never byte-identity. Every other migration phase remains byte-identical-where-deterministic.
- **Measurement is the gate; the real delta is evidence**: the falsifiable CI gate is the deterministic prompt-size test (Requirement 2, offline). The real-run token/cost delta (Requirement 3) is recorded as live evidence and is not required to run in CI.
- **Reduction floor = 50%** of the task-2+ context-message size (chars, input-token proxy), measured on a ≥2-page prototype HTML.
- **Ledger discipline**: L13 must remain `☐` after this phase (the inline helper still exists; it is now *called*, not deleted). The Phase-1 migration-ledger ratchet test must stay green — the `_extract_html_skeleton` grep pattern is **not** enforced until Phase 7.
- **Dead-code gate stays green**: once wired, `_extract_html_skeleton` is no longer dead; vulture (`min_confidence=80`) does not flag it as a method, so no allow-list change is required (and none must be added).
- **Offline determinism**: all gating tests run via `_scripted_model._drive` / direct `_build_context_message` calls — no DB, Bedrock, or API key.
- Tech stack unchanged: Python · the existing `deepagents` runtime · the existing characterization harness.

## Acceptance Criteria

- [ ] `_extract_html_skeleton` is invoked on the build-task-2+ context path; the full `--- CURRENT HTML (modify this` block is absent for task 2+ and the skeleton markers are present.
- [ ] A deterministic offline test asserts the compacted build-task-2+ context message is ≤ 50% of the full-HTML version's size on a ≥2-page HTML.
- [ ] The phase SUMMARY records a real multi-task build's token/cost delta (a measured reduction) with a documented reproduction.
- [ ] `prototype` and `od_prototype` semantic event snapshots pass with no golden edits; `seq` contiguous.
- [ ] `prototype` + `od_prototype` deliverable byte-goldens are re-recorded; `prototype_revision`/`od_ppt`/`app_builder` deliverable goldens are unchanged.
- [ ] A test asserts identical `data-page` ID set + `routes` keys and equal-or-better validation pass (zero net-new failures) before/after compaction.
- [ ] The build sub-agent retains `read_file` access to `prototype.html` on the task-2+ path and the context instructs read-before-edit.
- [ ] Migration ledger row **L13** remains `☐`; the Phase-1 ledger ratchet test stays green.

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                        |
|--------------------|-------|------|--------|--------------------------------------------------------------|
| Goal Clarity       | 0.92  | 0.75 | ✓      | Wire skeleton for task 2+, replace full HTML; ≥50% reduction |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Inline wiring now; capability/L13-delete is Phase 7          |
| Constraint Clarity | 0.85  | 0.65 | ✓      | ≥50% floor, deterministic CI gate, read_file access, INV-3   |
| Acceptance Criteria| 0.88  | 0.70 | ✓      | CI test + real delta + re-baseline + pages/routes assertion  |
| **Ambiguity**      | 0.12  | ≤0.20| ✓      | Gate passed after round 1                                    |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective              | Question summary                                  | Decision locked                                                              |
|-------|--------------------------|---------------------------------------------------|-----------------------------------------------------------------------------|
| 0     | Researcher (scout)       | What exists today re: token-trim?                 | `_extract_html_skeleton` dead (L13); full HTML still injected task-2+        |
| 1     | Failure Analyst          | What's the falsifiable token-delta measurement?   | Both: deterministic CI prompt-size test (gate) + real-run delta in SUMMARY   |
| 1     | Failure Analyst          | Pass/fail floor for "demonstrated" reduction?     | ≥50% smaller build-task-2+ context message                                  |
| 1     | Boundary Keeper          | How is semantic/validation parity enforced?       | Re-baseline deliverable + hold semantic snapshot + assert pages/routes      |
| 1     | Boundary Keeper          | How does the agent get full HTML once removed?    | `read_file` prototype.html from sandbox on demand (read-before-edit)         |

---

*Phase: 03-token-trim-measured-change-0c*
*Spec created: 2026-06-07*
*Next step: /gsd-discuss-phase 3 — implementation decisions (where to inject the skeleton, test placement, real-run harness)*
