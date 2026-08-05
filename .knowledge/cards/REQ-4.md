---
id: REQ-4
type: req
status: done
area: [workflow, auth, artifacts]
summary: >-
  Manifests & Compiler (Phase 1A)
source: .planning/REQUIREMENTS.md#manifests-compiler-phase-1a
---

### Manifests & Compiler (Phase 1A)

- [x] **MAN-01**: `WorkflowManifest` schema + loader/validator reads hand-authored file-backed YAML manifests (one per workflow) (Q5/Q7 / §32)
- [x] **MAN-02**: `WorkflowCompiler` compiles a manifest to a validated typed `CompiledWorkflow` / `ExecutionPlan` (DAG of `Step`s) — thin, no DSL, no control flow in manifests (INV-5)
- [x] **MAN-03**: Compiler validates every capability reference against the `CapabilityRegistry` + trust + owner allow-list; unknown/not-allowed names → compile error (INV-4)
- [x] **MAN-04**: Every current pipeline runs from a compiled plan; artifacts still flow via the legacy `accumulated_outputs` mirror (no schema change yet) (Phase 1A Accept)
- [x] **MAN-05**: `pipeline_type` retained only as a temporary migration alias (Q1)
