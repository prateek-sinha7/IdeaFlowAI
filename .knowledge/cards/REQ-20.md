---
id: REQ-20
type: req
status: done
area: [workflow, agents, artifacts]
summary: >-
  Uploads & Multimodal (Phase 30)
source: .planning/REQUIREMENTS.md#uploads-multimodal-phase-30
---

### Uploads & Multimodal (Phase 30)

- [x] **UPLD-01**: `POST /api/runs/{id}/files` (multipart, two-layer owner check → 404) persisting bytes under the run's `RunSandbox` — **DONE 30-01** (owner-scoped, capped, traversal-proof; docs land under reserved `.uploads/` + extract-text sidecar + manifest; deliverable-excluded, INV-3 dormant)
- [~] **UPLD-02**: `run_images` provider live end-to-end (WS ingress → engine → `HumanMessage` content blocks) incl. per-turn images — **run-entry path LANDED 2026-07-07 pre-milestone** (IMAGE-INPUT-PLAN waves `edw`/`frv`/`gvq`, offline-proven for `prototype`; validation caps + vision guard included); **per-turn carrier LANDED 30-03 (2026-07-08)** — images on the Phase-29 `POST /api/runs/{id}/messages` path → `apply_turn_images` → `ectx.pending_turn_images` → engine `_drain_turn_images` → `run_images` → `_compose_input_blocks` blocks; cap-validated by the shared `_validate_images`; ND-10 payload-transient (retained:false, no bytes), INV-3 dormant, offline-proven (39 green + 15 goldens byte-identical); **remaining: live Bedrock proof (Phase 34/LIVE-02) + the DEF-30-03-1 live in-process ectx delivery handle (== DEF-29-09-1)**
- [x] **UPLD-03**: Documents extract-to-sticky-context AND land in the sandbox for agent `read_file`; `context_provider:uploaded_files` registered; uploaded context present in every subsequent `agent_input`
- [~] **UPLD-04**: Launch-time attachments (incl. images, client-resized) ride `run_pipeline` — **image attachments LANDED 2026-07-07 pre-milestone** (FE picker + base64 + preview chips on 3 surfaces → `run_pipeline` `images`); remaining: client-side resize, paste/drag-drop (Phase 31 UI)
