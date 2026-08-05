---
id: TEST-6-1
type: test
status: done
area: [sse, workflow]
summary: >-
  6.1 What IS verified
source: .planning/TEST-REGISTER.md#6-1-what-is-verified
covers: [UI-CAMPAIGN]
---

### 6.1 What IS verified

- **Backend (🟢):** the entire §2 set is green offline + characterization-locked + CI-gated (44 passed/7 skipped parity+gate suite; 206-test compiler/model/gate suite; `lint-imports` 4/0; SC-001 proofs; alembic head 0020; registry==63). This is the trust floor.
- **Live + visual (✅), 2026-06-13 campaign (V1–V8) + 2026-06-12 re-pass + UI-CAMPAIGN (S01–S12):**
  - ISS-016/017 model-error → `pipeline_failed` + degraded panel (on the srini `ValidationException`) — **the major one**.
  - ISS-021 custom HTML in the generic sandboxed iframe; ISS-007/002 cancel delivery + cards clear; ISS-019 wave-fold above the fold; ISS-014 composer deleted + relocated model picker; ISS-005 `/api/v1`×6; ISS-006 `getDatabase`.
  - F1 declared-gate streaming (2 review gates); F4 zero tool-XML (user_stories/od_ppt); F6 sample_fanout; ISS-001/LV-02 od_ppt deck (18,661 chars); SC1 revision real loop (118 frames); WR-03 revision reconnect section (29 frames).
  - Per-workflow green paths: user_stories, od_prototype (Spec-Kit + 2 gates), od_ppt, app_builder (121-file IDE), **custom `ui_custom_proto` (the SC-001 headline, 190s/$0.17)**, sample_fanout, sample_wave.
- **Live-mech + offline-backed (🟡):** ISS-008/009 reconnect contract; revision lineage/terminal-fidelity; degraded partial.
