# Domain 5 — frontend·preview

7 cards, 2 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | frontend·preview (ISS-433, ISS-596) | ISS-433, ISS-596 | A′ (ISS-433 sibling of ISS-314/FIX-378) + C | ISS-433 replicate FIX-378; ISS-596 test-side | haiku |
| B2 | 5 | `frontend/src/components/preview/PreviewPanel.tsx` | ISS-251, ISS-388, ISS-389, ISS-599, ISS-609 | A′ (ISS-388 sibling of ISS-285) + B (stale-state) + C | mixed | haiku |

Notes:
- ISS-433: replicate FIX-378 (PrototypePreview browser-chrome focus/a11y) at the
  named sibling. ISS-596 is a test-side fixture defect (files[0] auto-open).
- B2: PreviewPanel.tsx is ~large; ONE read, all 5 cards, ONE verify. ISS-388
  replicates ISS-285/FIX-357-358 (reopenTabFor missing run-preview-full case).
  ISS-251 (duplicated resolveR* rule now exported), ISS-599 (nav error swallow),
  ISS-609 (AuditTab gets wrong runId) are PreviewPanel-local.
- ISS-389 / ISS-609 have `AuditTab.tsx` as a secondary glob. If the fix must edit
  AuditTab, that file is shared with domain 6 (components) — escalate rather than
  reach across; likely the PreviewPanel-side prop wiring is the real fix.

Collision note: PreviewPanel.tsx owned here. AuditTab.tsx is domain 6's — do not edit.
Status: NOT STARTED.
