---
phase: 30-uploads-multimodal-a2
plan: 05
subsystem: docs/implementation-register
tags: [register-first, image-input, multimodal, ND-10, docs-only]
requires:
  - "The already-landed image-input cluster (waves edw/frv/gvq): run_images provider, _validate_images ingress caps, prototype opt-in, FE picker, 7 tests"
provides:
  - "IMPLEMENTATION-REGISTER.md image-input cluster section (index-not-source) + Phase 30 nav-table row"
  - "ND-10 / LOCK-E payload-transient disposition recorded (no durable image storage)"
affects:
  - ".planning/IMPLEMENTATION-REGISTER.md"
tech-stack:
  added: []
  patterns: [register-first-discipline, index-not-source]
key-files:
  created: []
  modified:
    - ".planning/IMPLEMENTATION-REGISTER.md"
decisions:
  - "Recorded as a Phase 30 cluster section (waves edw/frv/gvq landed pre-Phase-30), appended after Phase 27, with a Phase-navigation table row for consistency"
  - "ND-10/LOCK-E payload-transient disposition documented as a do-not-resurrect lock so future multimodal work does not re-plan durable image storage"
metrics:
  duration: ~10 min
  completed: 2026-07-08
requirements: [UPLD-02, UPLD-04]
---

# Phase 30 Plan 05: Image-Input Cluster Register Entry Summary

Closed the register-first gap: indexed the already-landed image-input cluster (waves `edw`/`frv`/`gvq`) in `IMPLEMENTATION-REGISTER.md` — the `run_images` input_provider, the `_validate_images` ingress caps + vision guard, the prototype `input_providers:[run_images]` + `injects:[images]` opt-in, the FE picker/preview + out-of-band `images` payload, the 7 offline tests, and the ND-10/LOCK-E payload-transient disposition — all code-free pointers verified against the tree.

## What Was Built

A single docs-only, additive edit to `.planning/IMPLEMENTATION-REGISTER.md`:

1. **Phase-navigation table row** (after the Phase 27 row) for the Phase 30 image-input cluster, pointing at `30-05-{PLAN,SUMMARY}.md`.
2. **New cluster section** appended after Phase 27:
   - Capability `input_provider:run_images` → `backend/agents/capabilities/input_providers/run_images.py` (`RunImagesProvider`, `name="run_images"`, `async def load`) + registry lockstep in `backend/agents/capabilities/registry.py` (`@register` decorator, `_KNOWN` membership tuple, `discover()` import tuple) + the drift-guard count history incl. the KAN-73 `audit_logger` drift.
   - Ingress caps + vision guard → `_validate_images` in `backend/app/api/websocket.py` (mime allow-list `{png,jpeg,webp,gif}`, `~3.75 MB`/image, ≤20 images, `~8 MB` aggregate, vision-model guard, `IMAGE_INPUT_ENABLED` flag), validated pre-mint on both the WS `run_pipeline` path and `POST /api/runs` (`run_commands.py`). Engine seams: `_normalize_run_images`, `_dispatch_payload` (split-transport), `_compose_input_blocks` (per-agent `injects:[images]` gate) in `engine.py`.
   - Workflow opt-in → `prototype/workflow.yaml` `input_providers:[run_images]` + `prototype-specify/AGENT.md` `injects:[images]` (dormant-by-default; no other workflow opts in — SC-001).
   - FE → `IdeaInputPage.tsx` picker/preview + out-of-band `images` payload also on `dashboard/page.tsx`, `workflow/prototype/templates/page.tsx`, `workflow/ppt/templates/page.tsx`, threaded through `useWorkflow.ts` (base64 never inlined into the brief, D3).
   - The 7 tests (5 BE + 2 FE), each by exact path.
   - Locked disposition: D-07 payload-transient + **ND-10/LOCK-E** — images do NOT survive reopen/replay; the "image not retained" placeholder is the disposition, NOT durable image storage.
   - Cross-reference to Phase 30's remaining scope (30-01 files endpoint, 30-02 `uploaded_files` provider, 30-03 per-turn carrier, 30-04 client resize + reopen placeholder).

## Verification

- **Plan grep gate:** `grep -c "run_images\|_validate_images\|image-input\|ND-10\|payload-transient" .planning/IMPLEMENTATION-REGISTER.md` → **15 hits** (≥4 required). PASS.
- **File-existence pre-check (index-not-source discipline):** every source/test path cited in the entry was verified present in the tree before writing — `run_images.py`, `registry.py`, `websocket.py` (`_validate_images`, `IMAGE_INPUT_ENABLED`), `run_commands.py`, engine seams (`_normalize_run_images`, `_dispatch_payload`, `_compose_input_blocks`), `prototype/workflow.yaml` (`input_providers:[run_images]`), `prototype-specify/AGENT.md` (`injects:[images]`), the 5 backend + 2 frontend tests, and the 3 FE launch surfaces.
- No pytest / lint-imports run — docs-only plan (full suite hangs offline; not applicable here).

## Deviations from Plan

None — plan executed exactly as written. The plan pre-stated the "65-count reconciliation" as prose; the entry records the drift-guard count history + KAN-73 `audit_logger` drift generically (pointer to `registry.py`) rather than pinning a specific integer, staying within index-not-source discipline and avoiding a claim not directly asserted by a single line in the tree.

## Known Stubs

None. This is a documentation index entry; no code, no data source, no UI.

## Self-Check: PASSED

- `.planning/IMPLEMENTATION-REGISTER.md` modified — FOUND (grep gate 15 hits).
- `.planning/phases/30-uploads-multimodal-a2/30-05-SUMMARY.md` — FOUND (this file).
- Register entry committed atomically: `7ba2f791` (`docs(30-05): register the image-input cluster ...`).
