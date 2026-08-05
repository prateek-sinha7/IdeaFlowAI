---
id: FIX-002b
type: fix
date: 2026-06-22
status: done
area: [frontend, workflow]
files:
  - frontend/src/components/layout/AppHeader.tsx
summary: >-
  Add Catalogue tab to main nav for saved workflow navigation — Catalogue /
  SavedWorkflowsPage was fully implemented but only reachable via profile dropdown; no
  main nav tab existed
source: .planning/FIX-REGISTER.md#fix-002
collision_of: FIX-002
invariants: [INV-1, INV-3, INV-12, SC-001]
---

# FIX-002b

> **Reused id.** The register uses `FIX-002` for more than one unrelated
> fix. This card is one of them; the suffix exists only here, so that one card
> means one fix. The register itself is unchanged — see `source:`.

**Phase / trigger:** Phase 21 (Saved Workflows)

<!-- verbatim from the register -->

### FIX-002 — Add Catalogue Tab to Main Navigation

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-fix https://velocityai-hex.atlassian.net/browse/KAN-75`

#### Root Cause
`SavedWorkflowsPage` was fully implemented (Phase 21), wired as `"saved-workflows"` in `DashboardLayout.MainView`, and accessible via the profile dropdown — but there was no entry in the primary navigation bar (`<nav>` in `AppHeader`). The nav only contained Home and Library tabs. Users had no obvious route to the Catalogue without finding the profile dropdown.

Trace:
```
User opens app → sees nav: Home | Library
→ no Catalogue tab
→ must find profile dropdown → "Saved Workflows" buried there
→ poor discoverability (KAN-75)
```

#### Phase Context
- **Phase(s) involved:** Phase 21 — Saved Workflows
- **Relevant register section:** `_register-parts/21-saved-workflows-user-authored-named-persisted-custom-workflo.md`
- **Deleted code verified (not resurrected):** no deleted code involved
- **Locked decisions respected:** visual style matches exactly the existing Home/Library nav buttons (same Tailwind classes)

#### Fix Applied
| File | Change | Why |
|------|--------|-----|
| `frontend/src/components/layout/AppHeader.tsx` | Added `LayoutGrid` icon import; added "Catalogue" `<button>` to the center `<nav>` block after Library, navigating to `"saved-workflows"`, active when `currentPage === "saved-workflows"` | Exposes Saved Workflows as a primary nav destination per KAN-75 |

#### Invariants Verified
- **INV-1** (no pipeline_type branches): not affected
- **INV-3** (golden parity): not affected — no deliverable changes
- **INV-12** (no duplication): `SavedWorkflowsPage` already exists — no new component created
- **SC-001** (zero engine edits): not affected — frontend nav only

#### Verification
- TypeScript: 0 diagnostics on `AppHeader.tsx`
- Execution trace: click Catalogue → `onNavigate("saved-workflows")` → `DashboardLayout.handleNavigate` → `setMainView("saved-workflows")` → `headerPage = "saved-workflows"` → Catalogue tab active → `SavedWorkflowsPage` renders ✓
- No backend changes needed

#### Notes
- The profile dropdown "Saved Workflows" entry is kept (redundant but harmless — provides a secondary access path).
- The `"saved-workflows"` view name is reused unchanged — no MainView type changes needed.
