---
id: REQ-10
type: req
status: done
area: [sse]
summary: >-
  Safe Local Exec — Gated on N3 (Phase 4B)
source: .planning/REQUIREMENTS.md#safe-local-exec-gated-on-n3-phase-4b
---

### Safe Local Exec — Gated on N3 (Phase 4B)

- [x] **EXEC-01**: A constrained `exec` profile runs only behind the `security` gate + `ExecutionPolicy` — command allow/deny, network default-deny, resource caps (cpu_seconds/mem_mb), ephemeral creds (§8/§14 / N3 ⚠️ — own threat model first)
- [x] **EXEC-02**: compile/test/lint validators land; a sample compile/test validator passes; egress denied by default (Phase 4B Accept)
