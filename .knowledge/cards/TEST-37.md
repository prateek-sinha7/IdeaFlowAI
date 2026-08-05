---
id: TEST-37
type: test
status: done
area: [sse, workflow, agents, artifacts]
summary: >-
  TS-V — Full per-workflow end-to-end (each pipeline, real Bedrock)
source: .planning/TEST-REGISTER.md#ts-v-full-per-workflow-end-to-end-each-pipeline
covers: [TS-V-01, TS-V-02, TS-V-03, TS-V-04, TS-V-05, TS-V-06, TS-V-07, TS-V-08, TS-V-09]
---

### TS-V — Full per-workflow end-to-end (each pipeline, real Bedrock)

One green-path run per workflow type, asserting the full chain (trigger → clarify? → agents → gates? → waves? → deliverable + mimetype). Detailed expectations in §4.

| ID | Workflow | Key assertions | Status |
|---|---|---|---|
| TS-V-01 | `user_stories` (6 agents) | clarify questionnaire → agent cards → `Product Backlog`; **0** fabricated tool-XML in any chunk/final (F4) | ✅ (S01) |
| TS-V-02 | `od_prototype` (4 agents, wizard) | template wizard → 2 human gates (`Specification Review`, `Task Plan Review`) → Spec-Kit live view → prototype iframe | ✅ (S02) |
| TS-V-03 | `od_ppt` (3 agents, wizard) | deck in `Slide Deck Preview` (not QA narration) → revise → revised deck | ✅ (S03) |
| TS-V-04 | `app_builder` (15 agents) | IDE file tree; infra-generator emits `/api/v1` (≥6, 0 bare `/api/` — ISS-005); `getDatabase` not `getDb` (ISS-006); devops emits files | ✅ (V7 live) |
| TS-V-05 | **`custom` SC-001 (`ui_custom_proto`)** | factfind → 3-worker fanout (wave panel) → human gate → task_loop build (validators) → custom **HTML deliverable in generic iframe** — **proves a brand-new workflow runs with zero engine edits** | ✅ (V2 live, 190s/$0.17) |
| TS-V-06 | `sample_fanout` | 3 workers + `copy_disjoint` merge in wave panel; serialized bundle deliverable | ✅ (S10) |
| TS-V-07 | `sample_wave` | multi-wave topo execution; wave fold above the fold | ✅ (V1) |
| TS-V-08 | `mulesoft_to_springboot` | migration path tile → inventory/decompose agents → deliverable | 🟠 (06-12 with source) |
| TS-V-09 | `dotnet_to_azure` | migration path tile → .NET inventory/modernise agents → deliverable | 🟠 (06-12) |
