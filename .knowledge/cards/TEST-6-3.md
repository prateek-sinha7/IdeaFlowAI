---
id: TEST-6-3
type: test
status: done
area: [workflow, agents]
summary: >-
  6.3 Known-fail baseline (⚪ — do NOT block on these)
source: .planning/TEST-REGISTER.md#6-3-known-fail-baseline-do-not-block-on-these
---

### 6.3 Known-fail baseline (⚪ — do NOT block on these)

| Item | Where | Logged |
|---|---|---|
| `AgentProgressPanel.test.tsx` (×1, "hides chain panel when all base complete") | FE vitest | ISS-022 |
| `workflowChaining.test.ts` (×6, `availableChainTargets` ordering) | FE vitest | ISS-025 |
| `test_phase5_revision_validation.py::…event_types_subset_of_documented_vocabulary` | BE | ISS-026 |

These are pre-existing, triaged, non-regression. The register flags them so a QA run of `npm test` (102 pass / 7 fail) isn't misread as new breakage. (ISS-012 REQUIREMENTS.md traceability drift and ISS-023/024 cosmetics are also logged-open backlog, not test failures.)
