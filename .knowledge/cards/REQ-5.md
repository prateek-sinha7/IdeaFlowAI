---
id: REQ-5
type: req
status: done
area: [sse, resume, workflow, agents, auth, artifacts]
summary: >-
  Typed Artifacts, Lineage & Persistence (Phase 1B)
source: .planning/REQUIREMENTS.md#typed-artifacts-lineage-persistence-phase-1b
---

### Typed Artifacts, Lineage & Persistence (Phase 1B)

- [x] **ART-01**: `ArtifactGraph` + `ArtifactRef` — typed, content-addressed, owner-scoped DAG replaces loose `accumulated_outputs: dict[str,str]` (L15 / §17 / INV-10)
- [x] **ART-02**: Every artifact write records producer step/agent/task, content hash, location, version, parents, visibility, retention (INV-10)
- [x] **ART-03**: Typed `produces`/`consumes` routing replaces string matching; revision lineage tracked via `parents`/`derived_from` (§17)
- [x] **ART-04**: Default retention = **keep-by-default** — run artifacts are retained indefinitely; `run_ttl`/`days:N` are opt-in overrides (N9 — DECIDED keep-by-default, Phase 22 / DECIDE-01)
- [x] **PERSIST-01**: Migration adds `artifact_refs`, extends `workflow_runs` (+ workspace_id, owner_id, parent_run_id, source_run_id, plan_id, status, budget_snapshot_json), adds `workspaces`, `run_events` — additive only, every table carries `owner_id` + `workspace_id` (§18 / Q3)
- [x] **PERSIST-02**: Dual-write typed refs alongside the legacy mirror; reads migrate incrementally; the `accumulated_outputs` mirror is deleted in this phase once reads migrate (L15 / §31)
- [x] **PERSIST-03**: `run_events` rows carry monotonic per-run `seq` + `event_id` for durable replay/resume; index (run_id, seq) (§18/§21)
- [x] **AUTHZ-01**: Ownership model `user → workspace → (repository|project) → run → {artifacts, subagent_runs}`; everything carries `owner_id` + `workspace_id` (INV-8 / §19)
- [x] **AUTHZ-02**: Default-deny store-layer scoped-query helper; all artifact/run reads go through it; no cross-owner read/write (§19)
- [x] **AUTHZ-03**: Anonymous runs get a synthetic `anon:<session_id>` owner — never `None` (§19)
- [x] **AUTHZ-04**: Authz-denial tests (cross-owner parent/artifact access) pass (Phase 1B Accept / R8)
