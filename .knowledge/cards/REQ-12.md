---
id: REQ-12
type: req
status: done
area: [resume, workflow, agents, runtime]
summary: >-
  Wave Scheduler & Durable Resume (Phase 6)
source: .planning/REQUIREMENTS.md#wave-scheduler-durable-resume-phase-6
---

### Wave Scheduler & Durable Resume (Phase 6)

- [x] **WAVE-01**: `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves, runs each wave via fan-out; deterministic builder, CP-SAT seam left (Q31/Q32)
- [x] **WAVE-02**: `wave_runs` persistence; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential (Q33 / Phase 6 Accept)
- [x] **WAVE-03**: Resume mid-wave via `subagent_runs`/`wave_runs` records after a restart (§21 / N8 — confirm)
