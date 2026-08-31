# Domain 13 — frontend·layout

23 cards, 2 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | `frontend/src/components/layout/DashboardLayout.tsx` | BUG-006-007, BUG-008-011, BUG-012-FOLLOWUP-LABEL, BUG-012, BUG-014, BUG-019-020, BUG-DEF-44-12-4, ISS-136, ISS-252, ISS-283, ISS-346, ISS-347, ISS-348, ISS-349, ISS-371, ISS-372, ISS-373, ISS-432, ISS-472, ISS-473, ISS-474, ISS-622 | B (stale-state + confirm-dialog + route-depth) + A′ (ISS-348/349 sibling of ISS-238; ISS-432 sibling of ISS-315; ISS-622 confirms-dialog sibling) + C | full; one read | **sonnet** (22 cards, ~2400-line file, stale-state + confirm-dialog clusters + tier/entitlements) |
| B2 | 2 | frontend·layout (ISS-143) | ISS-143 | B (stale-state: AppHeader) | full | haiku |

Notes:
- DashboardLayout.tsx: the **largest single-file batch** in the backlog. Dominant
  classes:
  - **stale-state** (BUG-006/008/012/014/019-020/DEF-44, ISS-136/252/346/347): the
    workflowType / effectiveReviseType / pipelineState stale-label/stale-status
    family that threads through the whole layout. These share a single root cause
    (computed state derives from stale snapshot references); fixing the derivation
    once likely cures most.
  - **confirm-dialog** (ISS-371/372/373/622): handleBackNav discards typed content.
  - **route-depth** (ISS-348/349 replicate ISS-238/FIX-344; ISS-432 replicates
    ISS-315/FIX-375).
  - **tier/entitlements** (ISS-472/473/474): no userTier prop passed to child screens.
  - ISS-283/284: ISS-228 LaunchWizard family — secondary glob here (handleLaunchSaved).
    If the fix needs to also edit LaunchWizard.tsx, coordinate with domain 12 or
    escalate.
- Sonnet is non-negotiable: 22 cards, ~2400 lines, multiple interleaved state bugs.
  This is the single most complex batch in the backlog.
- B2 ISS-143: AppHeader label gate stale terminal check — small, separate file.

Collision note: DashboardLayout.tsx owned here. LaunchWizard.tsx (domain 12),
ComposerPage.tsx (domain 10), IdeaInputPage (multiple domains), page.tsx (domain 8),
PreviewPanel (domain 5) all appear as secondary globs — escalate any cross-file edit.
Status: NOT STARTED.
