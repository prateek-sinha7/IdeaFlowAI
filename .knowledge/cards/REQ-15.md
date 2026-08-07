---
id: REQ-15
type: req
status: done
area: [sse, resume, workflow, agents, auth, artifacts, runtime]
summary: >-
  Dynamic API / Frontend Contract (parallel track, §22)
source: .planning/REQUIREMENTS.md#dynamic-api-frontend-contract-parallel-track-22
---

### Dynamic API / Frontend Contract (parallel track, §22)

- [x] **API-01**: `GET /api/workflows` → list + metadata; `GET /api/workflows/{id}` → full step configs, gates, validators, deliverable, declared capabilities (§22)
- [x] **API-02**: `GET /api/capabilities` → registry palette (kind, name, `user_allowed`, config schema) incl. runtimes, skills, hooks, MCP servers, integrations, model catalog — with required auth + permission scopes (§22/§7/§30)
- [x] **API-03**: Run stream (WS/ndjson) emits existing events + new (`subagent_*`, `wave_*`, `validator_result`, `validation_warning`, `merge_*`, `budget_warning`, `gate_*`); existing-workflow contract stays at semantic parity (Q43/INV-3)
- [x] **API-04**: `GET /api/runs/{id}/artifacts` → typed artifact tree (lineage); `GET /api/runs/{id}/diff` → repo diff (§22)
- [x] **API-05**: `GET /api/runs/{id}/events?after=<seq>` → durable event replay (monotonic seq + event_id) for reconnect/resume (§22/§21)
- [x] **API-06**: Dynamic composer + capability palette + per-agent model picker; validator/issue panel; subagent + wave tree; artifact/diff viewer (reuse app-builder `FilesTab`/`AppBuilderPreview`) — additive panels (§22)
  - _Migration-ledger note (ISS-014, Phase 18 / deletion-as-superseded):_ the **capability-palette composer** half of API-06 (`WorkflowComposer.tsx` + `CapabilityPalette.tsx`) was orphaned dead UI (mounted by no route; INV-3/12 dual-impl) and is **DELETED-as-superseded** by the live `AgentsPopup` agent-composer (the "Compose a custom workflow" → Workflow-configuration modal, which is the real shipped composer). Deletion lands in plan **18-04**; rationale recorded here in 18-05. The per-agent **model picker** is relocated into the live `AgentsPopup` (locked-preferred — threads `model_overrides` for MODEL-03 end-to-end); if relocation proves too invasive it is carried to v2 (final disposition recorded in the 18-04 SUMMARY). **RETAINED:** the `GET /api/capabilities` endpoint + `test_capabilities_api.py` (API-02 registry-reflection contract + model-catalog source) — only the orphaned palette-panel UI is removed, the API contract and the agent-composer stand.
