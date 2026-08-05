---
id: REQ-37
type: req
status: done
area: [workflow, agents, auth, runtime]
summary: >-
  Advanced Scheduling & Git
source: .planning/REQUIREMENTS.md#advanced-scheduling-git
---

### Advanced Scheduling & Git

- **SCHED-01**: CP-SAT scheduling (topo seam left in Phase 6; §27/Q32)
- **MERGE-01**: Single-file fragment-merge parallelism (prototype stays sequential; §27/Q33)
- **GIT-01**: PR/commit push to git hosting (diff-only until N4; §27)
- **WF-DB-01**: DB-backed user-authored workflows (file-backed manifests only for now; Q5)

## Out of Scope

Explicitly excluded this milestone (designed-for via interfaces, not built).

| Feature | Reason |
|---------|--------|
| ECS/EC2 provisioning, warm/dedicated containers | Backend swap behind `RuntimeEnvironment` port — Phase 7 / separate spec (§27 / N1) |
| Container networking & cloud secrets injection, prod teardown/lease | Infra follow-up; local runtime only this milestone (§27) |
| CP-SAT scheduling | Deterministic topo wave-builder sufficient; seam left (Q32/§27) |
| Single-file fragment-merge parallelism | Prototype stays sequential; opt-in later (Q33/§27) |
| Untrusted end-user code execution | Trust seam exists; engineer-only + `security`-gated until N3 (§27/R5) |
| PR/commit push | Diff-only until git-hosting integration (N4/§27) |
| DB-backed user-authored workflows | File-backed hand-authored manifests now (Q5) |
| Hand-rolled / local `deepagents` runtime | Banned — always import the real library (INV-13/R15) |
| Auto-generated manifest index as source of truth | Manifests are hand-authored; generated index optional later, never authoritative (§28) |

## Traceability

Each v1 requirement maps to exactly one phase, **one row per requirement** (REQ-ID alone in the first cell — no grouped/comma rows). Phases are GSD integers 1–12, mapped 1:1 to plan §25 sub-phases (`[0A]…[6]`). Each v1 row carries the owning phase's verification verdict (every phase 1–12 has `NN-VERIFICATION.md` `status: passed`). v2 / Out-of-Scope items are listed for completeness with phase `v2 (deferred)` — intentionally unmapped this milestone.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SAFE-01 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-02 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-03 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-04 | Phase 1 [0A] | Complete (P1 verified — passed; ledger ratchet 01-03) |
| SAFE-05 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-06 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| SAFE-07 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06) |
| CTX-01 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| CTX-02 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| CTX-03 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| CTX-04 | Phase 2 [0B] | VOIDED/DEFERRED — `_handle_revision` is LIVE (the `run_revision` PPT-revision handler), not dead; deletion would break PPT revision (CTX-05). Deferred pending a product decision on retiring `run_revision`. See Phase 2 `02-02-SUMMARY.md`. |
| CTX-05 | Phase 2 [0B] | Complete (P2 verified — passed, 2026-06-07) |
| COMPACT-01 | Phase 3 [0C] | Complete (P3 verified — passed, 2026-06-07) |
| COMPACT-02 | Phase 3 [0C] | Complete (P3 verified — passed, 2026-06-07) |
| COMPACT-03 | Phase 3 [0C] | Complete (P3 verified — passed, 2026-06-07) |
| MAN-01 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-02 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-03 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-04 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| MAN-05 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| ART-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| ART-02 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| ART-03 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| ART-04 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| PERSIST-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| PERSIST-02 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| PERSIST-03 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-02 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-03 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| AUTHZ-04 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| MODEL-01 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| MODEL-02 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| MODEL-03 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08; FE per-agent picker relocated into the live AgentsPopup in Phase 18 — ISS-014) |
| MODEL-04 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| MODEL-05 | Phase 6 [1C] | Complete (P6 verified — passed, 2026-06-08) |
| PARITY-01 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-02 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-03 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-04 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-05 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-06 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-07 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-08 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| PARITY-09 | Phase 7 [2] | Complete (P7 verified — passed, 2026-06-09; SC-001 PROVEN) |
| CAP-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-01) |
| CAP-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-01) |
| CAP-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-01) |
| GATE-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-02) |
| GATE-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-02, validation-gate context wired in review remediation) |
| GATE-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-02) |
| TOOLPERM-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03) |
| TOOLPERM-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03) |
| TOOLPERM-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03) |
| VALID-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| VALID-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| VALID-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; single-source `map_severity` in 08-01) |
| VALID-04 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| VALID-05 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-04) |
| AGENTRT-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-04 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-05 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-03/08-05) |
| AGENTRT-06 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-06) |
| SKILL-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-05) |
| HOOK-01 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| HOOK-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| HOOK-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| HOOK-04 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| OBS-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-07) |
| API-02 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-08) |
| API-03 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-08) |
| API-06 | Phase 8 [3] | Complete (P8 verified — passed, 2026-06-09; 08-08, human-verified). Capability-palette composer UI (`WorkflowComposer`/`CapabilityPalette`) DELETED-as-superseded by the live agent-composer (ISS-014, Phase 18 — deletion 18-04, reconciled 18-05); `/api/capabilities` + the API-02 contract RETAINED. |
| RUNTIME-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-01/09-02) |
| RUNTIME-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-01/09-02) |
| RUNTIME-03 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-01/09-02) |
| REPO-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-03 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-04 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| REPO-05 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-03/09-04) |
| MCP-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| MCP-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| MCP-03 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| MCP-04 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10; 09-05) |
| INTEG-01 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10) |
| INTEG-02 | Phase 9 [4A] | Complete (P9 verified — passed, 2026-06-10) |
| EXEC-01 | Phase 10 [4B] | Complete (P10 verified — passed, 2026-06-10) |
| EXEC-02 | Phase 10 [4B] | Complete (P10 verified — passed, 2026-06-10) |
| FANOUT-01 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-02 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-03 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-04 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-05 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-06 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-07 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-08 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-09 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| FANOUT-10 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11; 11-01) |
| FANOUT-11 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| OBS-01 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| RESUME-01 | Phase 11 [5] | Complete (P11 verified — passed, 2026-06-11) |
| WAVE-01 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| WAVE-02 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| WAVE-03 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| RESUME-02 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| RESUME-03 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| RESUME-04 | Phase 12 [6] | Complete (P12 verified — passed, 2026-06-11) |
| CAPRUN-01 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| API-01 | Phase 4 [1A] | Complete (P4 verified — passed, 2026-06-07) |
| API-04 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| API-05 | Phase 5 [1B] | Complete (P5 verified — passed, 2026-06-08) |
| DEL-01 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06; 01-03) |
| DEL-02 | Phase 1 [0A] | Complete (P1 verified — passed; ledger ratchet 01-03 + dead-code scans/import-linter 01-04) |
| DEL-03 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06; 01-03) |
| DEL-04 | Phase 1 [0A] | Complete (P1 verified — passed, 2026-06-06; 01-03) |
| SURF-01 | Phase 22 | Planned (22-05) |
| SURF-02 | Phase 22 | Complete (22-02; tests + lint-imports + SC-001 green) |
| SURF-03 | Phase 22 | Planned (22-05) |
| EMP-01 | Phase 22 | Planned (22-04, 22-06) |
| EMP-02 | Phase 22 | Planned (22-04, 22-05) |
| EMP-03 | Phase 22 | Planned (22-04) |
| EMP-04 | Phase 22 | Planned (22-06) |
| WIRE-01 | Phase 22 | Planned (22-01) |
| WIRE-02 | Phase 22 | Planned (22-01) |
| WIRE-03 | Phase 22 | Planned (22-01) |
| UXFIX-01 | Phase 22 | Planned (22-07) |
| UXFIX-02 | Phase 22 | Planned (22-03) |
| UXFIX-03 | Phase 22 | Planned (22-07) |
| UXFIX-04 | Phase 22 | Planned (22-07) |
| DECIDE-01 | Phase 22 | Complete (22-08; ART-04 keep-by-default recorded; 3 stale open-question labels reconciled; N8 wave-resume left out of scope) |
| DECIDE-02 | Phase 22 | Planned (22-06, 22-08) |
| LIVE-01 | Phase 22 | Planned (22-09) |
| ECS-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (remote runtime; separate spec §27) |
| ECS-02 | v2 (deferred) | Deferred — v2, intentionally unmapped (warm/dedicated containers §27) |
| SCHED-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (CP-SAT; topo seam left Phase 12 / Q32) |
| MERGE-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (single-file fragment merge; Q33) |
| GIT-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (PR/commit push; diff-only until N4) |
| WF-DB-01 | v2 (deferred) | Deferred — v2, intentionally unmapped (DB-backed user workflows; file-backed only now, Q5) |

**Coverage:**

- v1 requirements: 117 total — all 117 present as individual rows above (one row per REQ-ID).
- Mapped to a phase: 117 / 117 ✓ (Phases 1–12; every phase `NN-VERIFICATION.md` `status: passed`).
- v1 delivered: 116 Complete + 1 VOIDED/DEFERRED (CTX-04 — `_handle_revision` is live; deletion deferred pending a `run_revision` retirement decision).
- v2 (deferred, intentionally unmapped, listed for completeness): ECS-01, ECS-02, SCHED-01, MERGE-01, GIT-01, WF-DB-01 (6).
- Traceability rows total: 123 (117 v1 + 6 v2) — every REQ-ID defined in the body has its own row.

**Per-phase counts:** P1=11 · P2=5 · P3=3 · P4=6 · P5=14 · P6=5 · P7=9 · P8=29 · P9=14 · P10=2 · P11=13 · P12=6 (= 117)
