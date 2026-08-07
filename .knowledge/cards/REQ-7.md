---
id: REQ-7
type: req
status: done
area: [sse, workflow, artifacts]
summary: >-
  Prototype as Manifest — Parity Proof (Phase 2)
source: .planning/REQUIREMENTS.md#prototype-as-manifest-parity-proof-phase-2
---

### Prototype as Manifest — Parity Proof (Phase 2)

- [x] **PARITY-01**: Implement `single_shot` + `task_loop` execution strategies (Q8/L7)
- [x] **PARITY-02**: Implement `single_file` / `serialized_sandbox` / `streamed_text` deliverable resolvers (L2/L9/L10)
- [x] **PARITY-03**: Implement the `opendesign` context provider + declared `seed_files` + `heading_tasks` task parser (L11/L12/Q11)
- [x] **PARITY-04**: `html_skeleton` registered as a `CompactionStrategy`, re-expressing Phase 0C behind the capability (behavior-preserving vs 0C) (Q35 / L13)
- [x] **PARITY-05**: `prototype`, `od_prototype` (alias + OpenDesign provider), and `prototype_revision` (variant: `seed_files.from_run` + `previous_run` provider + post-edit `validation` gate) all expressed as manifests (§10)
- [x] **PARITY-06**: Delete kernel leaks L1–L12 — `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME`, `_resolve_final_output`, `_sanitize_carousel_deck_html`/`_unwrap_artifact`, revision seeding/post-fix, `SKIP_PLANNER_FOR_PROTOTYPE`, `ALWAYS_CLARIFY` defaults, `spec.id == "prototype-build"`, HTML readback branch, build-loop internals (`_run_build_task_loop`/`_write_build_reference_files`/`_count_plan_tasks`/`_extract_task_block`/`_run_validation_fix_loop`/`_load_template_example`), `_build_context_message` per-pipeline branches (§4/§31)
- [x] **PARITY-07**: PPT deliverable handled by a `ppt` resolver + post-step transform/validator (L3)
- [x] **PARITY-08**: Kernel has zero workflow-name/agent-id branches — grep gate `if pipeline_type`/`spec.id ==` returns 0 (INV-1)
- [x] **PARITY-09**: prototype/od_/revision/ppt/code-gen at deliverable parity + semantic event parity vs the post-0C baseline (Phase 2 Accept)
