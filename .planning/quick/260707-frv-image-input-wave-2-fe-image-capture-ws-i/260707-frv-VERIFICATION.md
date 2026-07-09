---
phase: quick-260707-frv
status: passed
verified_by: orchestrator (independent backend + FE gate re-run — executor report treated as a claim)
date: 2026-07-07
---

# Verification — quick-260707-frv (Image Input Wave 2 — FE capture + WS ingress + ingest caps + vision guard)

**Status: passed.** Every must-have independently re-verified against ground truth by the orchestrator. Wave 2 of 3. The feature is still DORMANT at the agent level (no workflow opts in until Wave 3).

## Independent evidence (orchestrator re-ran)
- **Backend: 138 passed / 0 failed** — 5 characterization goldens byte/event-identical (`SNAPSHOT_UPDATE` unset), `test_context_message_oracle` green, `test_registry_capabilities` green (drift-guard **65** unchanged), `test_model_catalog` green **incl. `test_single_source_grep`** (the additive `ModelEntry.vision` bool adds NO model-id literal), plus the 2 new suites: `test_image_ingress_validation` (16 — caps reject bad-mime/oversized/`>20`/aggregate-over + accept valid; vision-guard reject) and `test_image_ws_ingress` (6 — `images` on `run_pipeline` → `execute(images=)`; **D3** no base64 in `WorkflowRun.input`/title; `IMAGE_INPUT_ENABLED=False` → images not passed; vision-guard reject → `execute` not called).
- **lint-imports:** `4 kept / 0 broken`.
- **FE:** `npx tsc --noEmit` clean — **zero errors in any Wave-2-touched file** (`IdeaInputPage`, `dashboard/page`, `templates/page` ×2, `DashboardLayout`, `useWorkflow`); `npx vitest run` = **4 passed** (`IdeaInputPage.imageInput` + `useWorkflow.imagePayload`).

## Scope / invariant audit
- **4 atomic commits, trailer-free:** `655561a8`, `bfc761de`, `ce7ee941`, `6ca97627`; branch `new-workflow-engine`; nothing pushed.
- **Scope (13 files, no forbidden surface):** `model_catalog.py`, `websocket.py`, `config.py`, `test_model_catalog.py`, 2 new backend test files (`test_image_ingress_validation.py`, `test_image_ws_ingress.py`), `IdeaInputPage.tsx`, `ppt/prototype templates/page.tsx`, `dashboard/page.tsx`, `DashboardLayout.tsx`, 2 new FE test files. **NO** `engine.py`, **NO** `manifest/compiler/plan.py`, **NO** Alembic migration (head unchanged), **NO** `workflow.yaml`, **NO** `AGENT.md`.
- **DORMANT (agent level):** no `input_providers:` in any manifest; no `injects:[images]` in any AGENT.md ⇒ `_compose_input_blocks` returns `[]` for every agent ⇒ goldens byte-identical BY CONSTRUCTION. Images now flow to `ectx.run_images` but no agent consumes them until Wave 3.
- **D3:** images ride the `run_pipeline` payload out-of-band; `attachedImages` is a SEPARATE FE state from `attachedFileContents` (which is inlined into the brief at `:347-350`); `WorkflowRun.input` stays the text brief with no base64 (tested). **D5:** no new WS event type. No migration.
- **Vision guard:** `ModelEntry.vision` (all 5 catalog entries = True) + `_validate_images` rejects when the effective run-level model set (`{session preferred_model OR BEDROCK_INFERENCE_PROFILE_ID} ∪ model_overrides.values()`) is not all vision-capable catalog entries — closes the raw-config non-vision escape hatch. `invalid_image_input` error, never a silent drop.

## Pre-existing reds — untouched by construction
Wave 2 did NOT modify `manifest.py`/`compiler.py`/`plan.py` (those were Wave 1), so the 2 pre-existing branch reds (`test_clarify_defaults_match_engine` ×7, `test_display_name` ×2) are unchanged. No new divergence.

## Carry-forward
Wave 2 of 3. **Wave 3** = opt in `prototype-specify` (`input_providers: [run_images]` on the `prototype` manifest + `injects: [images]` on the spec-writer AGENT.md) + a live Bedrock run proving the spec-writer receives the diagram, plus the middleware/checkpointer proof gate (IMAGE-INPUT §12 F2/F3). See `.planning/IMAGE-INPUT-PLAN.md`.
