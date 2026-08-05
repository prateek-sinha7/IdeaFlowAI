---
id: BUG-020-sse
type: bug
status: done
area: [sse]
summary: >-
  Type eyebrow shows the RAW type ("OD_PROTOTYPE") instead of a humanized label
source: .planning/SSE-QA-BUG-LOG.md#bug-020
campaign: sse
severity: "🟡 minor"
---

### BUG-020 — Type eyebrow shows the RAW type ("OD_PROTOTYPE") instead of a humanized label  [🟡 minor] [FIXED ✅ — LIVE-PROVEN]
- **RESOLVED:** FIXED + LIVE-PROVEN (quick 260717-rs7; commit `1f3730d8`; feat/ui-2, NOT pushed). Root cause: `frontend/src/components/chat/LaneRunHeader.tsx:184` `const type = runType || humanizeRunType(pipelineState?.pipeline_type)` — `runType` (raw, from `DashboardLayout:1777` `effectiveReviseType || pipeline_type`) was used VERBATIM; `humanizeRunType` was a DEAD fallback. Raw "od_prototype" → CSS-uppercased "OD_PROTOTYPE". Fix (1 line): `const type = humanizeRunType(runType || pipelineState?.pipeline_type)` → "od_prototype"→"Prototype"→"PROTOTYPE"; "user_stories"→"USER STORIES"; "od_ppt"→"PPT". `humanizeRunType` UNCHANGED (the `od_ppt`→"Ppt" lock at LaneRunHeader.test.tsx:38 stays green). In-component option (b), chosen over call-site (a) which would break 5 raw-string assertions; ZERO tests broke. RED→GREEN vitest (raw runType="od_prototype" → "Prototype"); 24 green; tsc clean. **LIVE-PROVEN** (screenshot `bug020-prototype-eyebrow.png`): reopened od_prototype `2774f80c` → eyebrow "PROTOTYPE".
