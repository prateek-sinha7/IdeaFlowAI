---
phase: 260707-gvq
plan: 01
subsystem: workflows / prompts (data-only opt-in)
tags: [image-input, input_provider, run_images, prototype, opt-in, SC-001, INV-3, dormant-when-empty, wave-3]
wave: "3 of 3"
requires:
  - "260707-edw Wave-1 backend spine: run_images capability + _compose_input_blocks gate + manifest/compiler/plan input_providers surface"
  - "Wave-2 carrier normalization + ingest caps (_normalize_run_images)"
provides:
  - "prototype workflow opted into the run_images input_provider (input_providers: [run_images])"
  - "prototype-specify (order-1 spec-writer) opted into image content-blocks (injects:[…, images])"
  - "end-to-end opt-in delivery proof via the REAL compiled plan + REAL loaded specs"
affects:
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/prompts/prototype-specify/AGENT.md
tech_stack_added: []
key_files_created:
  - backend/tests/agents/test_prototype_image_optin.py
key_files_modified:
  - backend/agents/workflows/prototype/workflow.yaml
  - backend/agents/prompts/prototype-specify/AGENT.md
decisions:
  - "DATA-ONLY opt-in (SC-001): a workflow consumes a registered capability by declaration alone — manifest input_providers + AGENT.md injects — with ZERO kernel/engine/capability .py edit."
  - "Dormant-when-empty is the golden-safety mechanism: with no image on the carrier, run_images.load returns [] -> _compose_input_blocks returns [] -> bare-str dispatch -> goldens byte/event-identical (SNAPSHOT_UPDATE unset, NO re-baseline)."
  - "Opted the order-1 spec-writer only (highest-value consumer); downstream agents stay non-opted, re-proving the per-agent-local gate (T-gvq-02 no cross-agent leak)."
  - "TDD RED captured by reverting the opt-in files to HEAD~1: the 2 declaration pins + delivery arm fail while the dormant prototype-plan control stays green."
metrics:
  duration_min: 6
  tasks: 2
  files: 3
  completed: 2026-07-07
---

# Phase 260707-gvq Plan 01: Image Input Wave 3 — Opt In prototype-specify (OFFLINE) Summary

Flip the `prototype` workflow's image-input capability from DORMANT (Wave 1) to ON for the
order-1 spec-writer (`prototype-specify`) with TWO data-only declaration edits, proven to (a)
stay byte/event-identical when no image is attached (the load-bearing golden-safety gate) and
(b) deliver exactly one base64 image content-block when an image IS present — with zero kernel
edit (SC-001). Wave 3 of 3; the feature is now ON for `prototype`, pending the deferred live
confirmation.

## What Was Built

**Task 1 (T3.1a + T3.1b + T3.2) — data-only opt-in + golden-safety dormancy** (commit `6f41e0a9`)
- `agents/workflows/prototype/workflow.yaml`: NEW top-level `input_providers: [run_images]`
  (sibling of `context_providers: [opendesign]`, NOT per-step). The key is already in
  `manifest._ALLOWED_TOP_KEYS` → parses → compiles (`compiler`) →
  `CompiledWorkflow.input_providers` (`plan.py`) → `ectx.compiled_input_providers`. No
  parser/compiler edit.
- `agents/prompts/prototype-specify/AGENT.md`: appended `- images` to `injects` → effective
  `[template, design_system, images]`. Verified inert in BOTH prompt paths (factory
  `_compose_injection` fires only on template/design_system/craft; the opendesign provider
  gates on design_system/template only) → system prompt + context_message UNCHANGED; only the
  engine `_compose_input_blocks` gate (`"images" ∈ set(spec.injects) ∪ set(step.injects)`)
  flips TRUE.

**Task 2 (T3.3, TDD) — opt-in delivery wiring test** (commit `f13b4dbc`)
- NEW `tests/agents/test_prototype_image_optin.py` — 2 declaration pins + 2 behavioral arms
  driven off the REAL compiled plan + REAL loaded specs (mirrors `test_image_input_wiring.py`):
  - pin A: `compile_for_run("prototype").input_providers == ["run_images"]`.
  - pin B: `"images" in load_agent_spec("prototype-specify").injects`.
  - DELIVERS: populated `ectx.run_images` + the real `prototype-specify` spec →
    `_compose_input_blocks` returns EXACTLY one `{type:image,source_type:base64,mime_type,data}`
    block.
  - DORMANT control: the real `prototype-plan` spec (no `images` inject), same `ectx` → `[]`
    (per-agent-local gate holds; re-proves T-gvq-02 no cross-agent leak).

## HARD-GATE Evidence

| Gate | Result |
|------|--------|
| **1. Goldens + oracle byte/event-identical** (SNAPSHOT_UPDATE UNSET) | **PASS — 20 passed.** All 5 characterization files (`prototype`, `od_prototype`, `prototype_revision`, `od_ppt`, `app_builder`) + `test_context_message_oracle` ran together = 20 passed, byte/event-identical with **NO `SNAPSHOT_UPDATE`**. This is the key proof the opt-in is DORMANT-WHEN-EMPTY: the golden harness passes no images → `run_images==[]` → `_compose_input_blocks` returns `[]` → bare-str dispatch; `image_count` never emitted; `_compose_injection` ignores `images`. |
| **2. manifest / registry / loader** | **PASS on the critical assertions.** `test_registry_capabilities` + `test_loader_new_fields` = **102 passed** (drift-guard `len(_KNOWN)==65`; loader accepts `images` verbatim). `test_manifest` minus the 2 known reds = **24 passed** (manifest parses/compiles `input_providers`). The 2 pre-existing `test_display_name[dotnet_to_azure\|custom]` reds stay identically red (NOT fixed). |
| **3. lint-imports** | **PASS — 4 kept, 0 broken** (run from `backend/`). |
| **4. wiring test** | **PASS — 4 passed.** Both declaration pins + the delivery arm (one base64 image block off the real `prototype-specify` spec) + the dormant `prototype-plan → []` control. |
| **5. INV-1 grep / SC-001** | **PASS — 0, unchanged from HEAD.** `grep -rnE 'pipeline_type ==\|spec\.id ==' agents/execution_engine/engine.py` = 0 before and after (no workflow-name/id branch added). |

## SC-001 / No-Kernel-Edit Confirmation

- `git diff --name-only HEAD~2 HEAD` = exactly 3 files: `workflow.yaml` (data), `AGENT.md`
  (data), `test_prototype_image_optin.py` (new test). **ZERO `.py`** under
  `execution_engine/`, `capabilities/`, `factory.py`, `loader.py`, or
  `workflows/{manifest,compiler,plan}.py`.
- **NO `SNAPSHOT_UPDATE`** at any point; **NO migration**; **NO commit trailer**;
  branch `new-workflow-engine` (never main, nothing pushed).

## TDD Gate Compliance

Genuine RED captured before GREEN: reverting the two opt-in files to `HEAD~1` and re-running
the wiring test yields **3 failed** (both declaration pins + the delivery arm) with the dormant
`prototype-plan → []` control still **1 passed** — proving the test truly detects the opt-in and
the control is not a false positive. Files restored to the opted-in HEAD; final run 4 passed.
(Note: the test was committed after the data opt-in for atomic per-task commits; the RED/GREEN
contrast is intrinsic to the file — 3 pins/delivery flip on the opt-in, the control is invariant.)

## Deviations from Plan

None affecting scope. Deviation from the plan's *expectation* (not its instructions): gate 2's
`test_factory_injects.py` surfaced 5 reds the plan did not anticipate. Per `<key_facts>` that
suite uses synthetic `_Spec` dataclasses (never the real `prototype-specify` spec), so it cannot
be caused by this edit — **proven pre-existing via `git stash`** (identical 5 failed / 6 passed
on clean HEAD with the gvq edits removed). Logged to `deferred-items.md`; NOT fixed (Scope
Boundary). No test-pin update was needed (the plan's conditional T3.2 pin-update did not apply —
no test pins the real `prototype-specify` injects).

## Out-of-Scope Pre-existing Reds (NOT fixed — see deferred-items.md)

- `tests/unit/test_factory_injects.py` — 5 (`test_full_injection_order`,
  `test_full_system_prompt_role_last`, `test_brief_analyst_no_craft`,
  `test_template_missing_raises`, `test_no_od_context_raises_for_template`); composition /
  `TemplateMissingError` drift, proven pre-existing via stash.
- `tests/agents/test_manifest.py::test_display_name_*[dotnet_to_azure\|custom]` — 2, the
  plan-anticipated display_name/launchable catalog reds.

## DEFERRED live-verification (do NOT run offline)

**LIVE Bedrock proof** — the `prototype-specify` spec-writer actually receives/reads the attached
diagram — **+ the middleware/checkpointer image-payload gate** (IMAGE-INPUT §12 F2/F3,
retry/replay amplification) are DEFERRED to a user-driven run; the orchestrator produces the
runbook (defer-live-verification-to-milestone-end convention, T-gvq-03 accept-deferred). No live
Bedrock run was attempted in this offline wave.

## Wave Status

**Wave 3 of 3.** Waves 1 (backend spine, dormant) + 2 (carrier normalization + ingest caps)
shipped and verified. The image-input feature is now **ON for the `prototype` workflow** (order-1
spec-writer consumes user-supplied images), pending the deferred live confirmation above.

## Commits (no trailer)

| Task | Commit | Subject |
|------|--------|---------|
| 1 | `6f41e0a9` | feat(agents): opt prototype into run_images input_provider (260707-gvq T3.1a/T3.1b) |
| 2 | `f13b4dbc` | test(agents): prove prototype image-input opt-in delivers via real plan+specs (260707-gvq T3.3) |

Branch `new-workflow-engine`; nothing pushed; no commit trailer.

## Self-Check: PASSED
- Files exist: `backend/agents/workflows/prototype/workflow.yaml`,
  `backend/agents/prompts/prototype-specify/AGENT.md`,
  `backend/tests/agents/test_prototype_image_optin.py` — all present.
- Commits exist: `6f41e0a9`, `f13b4dbc` — both in `git log`.
