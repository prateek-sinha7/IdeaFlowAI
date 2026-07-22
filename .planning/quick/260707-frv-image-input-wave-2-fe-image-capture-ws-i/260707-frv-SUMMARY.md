---
phase: 260707-frv
plan: 01
subsystem: execution-engine / api / frontend
tags: [image-input, ingress, vision-guard, ingest-caps, D3, dormant, INV-3, SC-001]
wave: "2 of 3"
requires:
  - "ExecutionContext.run_images carrier + execute(images=) (Wave 1, 260707-edw)"
provides:
  - "ModelEntry.vision field (+ vision=True on all 5 catalog entries)"
  - "IMAGE_INPUT_ENABLED feature flag (default True)"
  - "_validate_images ingress caps + vision guard (+ invalid_image_input error code)"
  - "WS run_pipeline `images` ingress param -> engine.execute(images=)"
  - "FE attachedImages capture + `images` extraParams payload (3 pickers + dashboard threading)"
affects:
  - backend/agents/capabilities/model_catalog.py
  - backend/app/core/config.py
  - backend/app/api/websocket.py
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/app/workflow/prototype/templates/page.tsx
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
key_files_created:
  - backend/tests/unit/test_image_ingress_validation.py
  - backend/tests/unit/test_image_ws_ingress.py
  - frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx
  - frontend/src/hooks/useWorkflow.imagePayload.test.ts
key_files_modified:
  - backend/agents/capabilities/model_catalog.py
  - backend/app/core/config.py
  - backend/app/api/websocket.py
  - backend/tests/agents/test_model_catalog.py
  - frontend/src/components/workflow/IdeaInputPage.tsx
  - frontend/src/app/workflow/ppt/templates/page.tsx
  - frontend/src/app/workflow/prototype/templates/page.tsx
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
decisions:
  - "images ride OUT-OF-BAND on the existing run_pipeline WS payload (D5 — no new event type); base64 NEVER enters WorkflowRun.input/title/brief (D3)."
  - "attachedImages is a SEPARATE FE state from attachedFileContents (which is inlined into the brief) — one ~340KB image base64 ~= the whole ATTACH_MAX_CHARS cap."
  - "Vision guard rejects unless EVERY effective run-level model (session preferred_model | default | override targets) is a ModelCatalog entry with vision=True — closes the raw-config escape hatch (T-frv-02)."
  - "Feature is DORMANT at the agent level (no input_providers: on any workflow.yaml, no injects:[images] on any AGENT.md) — Wave 3 owns the opt-in; goldens byte/event-identical BY CONSTRUCTION."
metrics:
  duration_min: 12
  tasks: 4
  files: 13
  completed: 2026-07-07
---

# Phase 260707-frv Plan 01: Image Input Wave 2 — FE Capture + WS Ingress + Caps + Vision Guard Summary

Wired the FE to capture images and the WS `run_pipeline` handler to carry them
(cap- + vision-validated) into the Wave-1 carrier (`execute(images=)` →
`ExecutionContext.run_images`), with an `IMAGE_INPUT_ENABLED` flag, ingest caps,
a run-level vision guard, and the D3 out-of-band guarantee (base64 never enters
the brief / `WorkflowRun.input`). Feature stays DORMANT at the agent level, so
the 5 characterization goldens stay byte/event-identical. **Wave 2 of 3.**

## What Was Built

**Task 1 — `ModelEntry.vision` + `IMAGE_INPUT_ENABLED` + `_validate_images`** (commit `655561a8`)
- `model_catalog.py`: `vision: bool` field on `ModelEntry` (after `pricing`) + `vision=True`
  on all 5 entries; no new model-id literal (single-source-grep stays green).
- `config.py`: `IMAGE_INPUT_ENABLED: bool = True` (clean off-switch).
- `websocket.py`: module-level caps (`_IMAGE_ALLOWED_MIMES` {png,jpeg,webp,gif},
  `_IMAGE_MAX_BYTES_PER_IMAGE`=3.75 MB, `_IMAGE_MAX_COUNT`=20, `_IMAGE_MAX_AGGREGATE_BYTES`=8 MB)
  + `_validate_images(images, *, effective_model_ids=None) -> str | None` mirroring
  `_validate_model_overrides` (str|None contract, lazy kernel-pure catalog import for the
  vision guard). Order: list → dict entries with string mime/data → mime allow-list →
  per-image raw ≤ 3.75 MB → count ≤ 20 → aggregate raw ≤ 8 MB → vision guard.
- Tests: `test_model_catalog.py` extended (`vision` in `_FIELDS`, `entry.vision is True`);
  new `test_image_ingress_validation.py` (16 cases — every `<behavior>` bullet).

**Task 2 — WS `run_pipeline` images ingress → `execute(images=)` + D3** (commit `bfc761de`)
- run_pipeline handler reads `images = message_data.get("images") or []` (mirrors `selections`)
  and threads it into `_handle_workflow_execution(images=...)` (new `images: list | None = None` param).
- Image-ingress gate placed AFTER the selections re-validation, BEFORE WorkflowRun creation:
  `if settings.IMAGE_INPUT_ENABLED and images:` computes `effective_model_ids =
  {preferred_model | BEDROCK_INFERENCE_PROFILE_ID} ∪ {str override targets}`, calls
  `_validate_images`, emits `code="invalid_image_input"` + `return` on violation, else
  `validated_images = images`. Flag OFF or no images → `validated_images = []` (byte-identical).
- `engine.execute(... images=validated_images ...)` beside `od_context`. `content`,
  `WorkflowRun.input`, `title` UNTOUCHED (D3).
- New `test_image_ws_ingress.py` (6 cases) reusing the offline WS harness: images-reach-execute,
  D3 (no base64 in run.input/title), flag-off→images=[], no-images→images=[], bad-mime reject,
  non-vision-model reject (both reject arms assert execute NEVER called).

**Task 3 — FE IdeaInputPage capture + `images` extraParams** (commit `ce7ee941`)
- `attachedImages` state (separate from `attachedFileContents`); picker `accept` gains the 4
  image mimes; `isImageFile` branch (mime allow-list + filename fallback) reads `readAsDataURL`,
  strips the `data:<mime>;base64,` prefix, and `setAttachedImages(...)` — NEVER
  `setAttachedFileContents`. Image chip row with per-index remove. `handleRun` includes
  `...(hasImages ? { images: attachedImages } : {})` and extends the extraParams guard.
- New `IdeaInputPage.imageInput.test.tsx` (capture→extraParams.images, brief has no base64;
  image-less→extraParams undefined) + `useWorkflow.imagePayload.test.ts` (Object.assign merge
  lands `images`, message base64-free; no-context→no images key).

**Task 4 — FE sibling pickers + dashboard threading** (commit `6ca97627`)
- ppt + prototype templates pages: `attachedImages` state, `accept` + `isImageFile` branch +
  image chip row (identical to Task 3); draft `sessionStorage.setItem` stashes
  `...(attachedImages.length > 0 ? { images: attachedImages } : {})`.
- `dashboard/page.tsx`: `images?` on all 8 pending-param / draft-typed shapes; `images: draft.images`
  in all 4 readers.
- `DashboardLayout.tsx`: `images?` on both pending-param prop shapes; both extraParams builders
  add `...(pending.images && pending.images.length > 0 ? { images: pending.images } : {})`.

## HARD-GATE Evidence

| Gate | Result |
|------|--------|
| **1. 5 characterization goldens + oracle byte/event-identical** (SNAPSHOT_UPDATE unset) | **PASS** — prototype, od_prototype, prototype_revision, od_ppt, app_builder + context_message_oracle + registry ran together = **108 passed**. Wave 2 does not touch the golden execute() path; `ModelEntry.vision` is additive. |
| **2. lint-imports** | **PASS** — `4 kept, 0 broken` (app→kernel `ModelCatalog` import stays clean). |
| **3. model_catalog + registry** | **PASS** — `test_model_catalog.py` green incl. `test_single_source_grep` (vision field adds NO model-id literal) + the new vision assertions; `test_registry_capabilities.py` green (drift-guard 65 unchanged — Wave 2 adds no capability). |
| **4. Backend NEW suites** | **PASS** — `test_image_ingress_validation.py` (16) + `test_image_ws_ingress.py` (6) = **22 passed**. Caps (bad-mime / oversized / >20 / aggregate-over / valid-accept); `images` on run_pipeline reaches `execute(images=)`; D3 (no base64 in run.input/title); `IMAGE_INPUT_ENABLED=False`→`images=[]`; vision-guard reject on non-vision/non-catalog model (execute never called). |
| **5. FE tsc-identity + vitest** | **PASS** — `npx tsc --noEmit` reports **0 errors** (zero NEW vs the known pre-existing set → identity satisfied). `vitest run` affected specs = **10 passed** (IdeaInputPage.imageInput 2, useWorkflow.imagePayload 2, src/components/layout 6). |

## DORMANT + D3 Confirmation

- **DORMANT (agent level):** `grep 'input_providers:' agents/workflows --include workflow.yaml` → **0** (the 4 hits are Wave-1 Python declaration-surface fields in `plan.py`/`manifest.py`, not yaml declarations). `injects:` + `images` in any `AGENT.md` → **0**. Therefore `_compose_input_blocks` returns `[]` for every agent → goldens byte/event-identical BY CONSTRUCTION.
- **D3 (out-of-band):** `grep -nE 'images=validated_images' app/api/websocket.py` → matches ONLY the `engine.execute` call (line 1992); no `images`/base64 assignment into either `WorkflowRun(...)` (lines 1877, 2425), `content`, or `title`. The `test_d3_no_base64_in_run_input` integration test asserts the persisted `WorkflowRun.input == brief` with the base64 marker absent from `input` and `title`. FE: `attachedImages` is a separate state; `finalMessage` (brief) is unchanged.
- **D5:** no new WS event type — images ride the existing `run_pipeline` message.
- **No migration:** alembic head stays **0023** (transient carrier, no new table/column).

## Deviations from Plan

None — plan executed exactly as written. Rules 1–3 not triggered.

## Pre-existing Branch Reds (NOT touched — leave identically red)

Per the plan + Wave-1 SUMMARY, these are standing pre-existing branch reds unrelated to this
work; no file they cover was modified here:
- `test_manifest_parity.py::test_clarify_defaults_match_engine[*]` (7)
- `test_manifest.py::test_display_name_*` (2)

**Wave 2 of 3.** Wave 3 = manifest opt-in (`input_providers:` on a workflow.yaml +
`injects:[images]` on an AGENT.md) + live multimodal proof.

## Commits (no trailer)

| Task | Commit | Subject |
|------|--------|---------|
| 1 | `655561a8` | feat(engine): ModelEntry.vision + IMAGE_INPUT_ENABLED + _validate_images ingress caps/vision guard (260707-frv T1) |
| 2 | `bfc761de` | feat(engine): run_pipeline images ingress -> execute(images=) with flag/caps/vision guard + D3 (260707-frv T2) |
| 3 | `ce7ee941` | feat(engine): FE IdeaInputPage image capture + images extraParams payload (260707-frv T3) |
| 4 | `6ca97627` | feat(engine): FE sibling pickers + dashboard image threading (260707-frv T4) |

Branch `new-workflow-engine`; nothing pushed; no commit trailer.

## Self-Check: PASSED
- Files exist: `test_image_ingress_validation.py`, `test_image_ws_ingress.py`,
  `IdeaInputPage.imageInput.test.tsx`, `useWorkflow.imagePayload.test.ts` — all present.
- Commits exist: `655561a8`, `bfc761de`, `ce7ee941`, `6ca97627` — all in `git log`.
