---
id: REQ-3
type: req
status: done
area: [auth]
summary: >-
  Context Compaction / Token-Trim (Phase 0C)
source: .planning/REQUIREMENTS.md#context-compaction-token-trim-phase-0c
---

### Context Compaction / Token-Trim (Phase 0C)

- [x] **COMPACT-01**: The dead `_extract_html_skeleton` is wired as build-task-2+ context compaction (Tier#1 / L13)
- [x] **COMPACT-02**: The change is gated on the semantic snapshot (same pages/routes, equal-or-better validation pass) plus a measured token/cost delta — not byte-identity (the sanctioned INV-3 exception)
- [x] **COMPACT-03**: A measured token reduction is demonstrated on a multi-task build (Accept criterion)
