# Domain 12 — frontend·workflow

22 cards, 3 batches.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-368 | RESOLVED | B1 | 2 | `frontend/src/components/workflow/AgentsPopup.tsx` | A′ (ISS-368 sibling of ISS-246; ISS-399 sibling of ISS-290; ISS-491 sibling of ISS-326) | replicate → verify | haiku |
| ISS-399 | RESOLVED | B1 | 2 | `frontend/src/components/workflow/AgentsPopup.tsx` | A′ (ISS-368 sibling of ISS-246; ISS-399 sibling of ISS-290; ISS-491 sibling of ISS-326) | replicate → verify | haiku |
| ISS-491 | RESOLVED | B1 | 2 | `frontend/src/components/workflow/AgentsPopup.tsx` | A′ (ISS-368 sibling of ISS-246; ISS-399 sibling of ISS-290; ISS-491 sibling of ISS-326) | replicate → verify | haiku |
| ISS-420 | RESOLVED | B2 | 2 | frontend·workflow (mixed) | A′ (ISS-420/421 sibling of ISS-311; ISS-480 sibling of ISS-320) + C (ISS-603 test fixture) | mixed | haiku |
| ISS-480 | RESOLVED | B2 | 2 | frontend·workflow (mixed) | A′ (ISS-420/421 sibling of ISS-311; ISS-480 sibling of ISS-320) + C (ISS-603 test fixture) | mixed | haiku |
| ISS-603 | RESOLVED | B2 | 2 | frontend·workflow (mixed) | A′ (ISS-420/421 sibling of ISS-311; ISS-480 sibling of ISS-320) + C (ISS-603 test fixture) | mixed | haiku |
| BUG-048 | RESOLVED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ (ISS-361 sibling of ISS-247; ISS-364-366 sibling of ISS-363; ISS-421 sibling of ISS-311; ISS-423 sibling of ISS-312) + C | full; one read | **sonnet** (16 cards, ~large file, launch-wizard family + ConfigLeversFlat stale-state) |
| ISS-189 | ESCALATED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-197 | ESCALATED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-217 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-228 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-284 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-361 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-362 | ESCALATED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-364 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-365 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-366 | ALREADY_FIXED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-377 | ESCALATED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-384 | RESOLVED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-421 | RESOLVED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-423 | RESOLVED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |
| ISS-429 | RESOLVED | B3 | 3 | `frontend/src/components/workflow/LaunchWizard.tsx` | A (ISS-228 family) + A′ | full; one read | **sonnet** |

Notes:
- B1 all-A′: three replicates (FIX-348, FIX-360, FIX-388), one file, skip validate/
  analyze. Simple.
- B3 LaunchWizard.tsx — the largest batch in the backlog (16 cards). Includes:
  - ISS-228 family root (saved workflow discards override fetch)
  - 5 tier-A′ replicates of landed diffs (ISS-361/363/311/312)
  - ISS-429/362 ReviewGatesSection zero-interaction (ISS-306 class)
  - ISS-384 savedName/savedDescription never exposed
  - ISS-377 manifest/selections exclusivity
  - ISS-217 hydration/bfcache mount-once gate (substantial)
  Sonnet is essential; Haiku would loop on ISS-228+377+217.
- B2 mixed: ISS-420 replicates ISS-311/FIX-376 (Advanced button unguarded). ISS-480
  replicates ISS-320/FIX-385 (delete zero confirm on SkillManager). ISS-603 test
  fixture defect (WorkflowView.attachmentRemove).
- Secondary globs: IdeaInputPage (domain 13/layout), CanvasConfigRail (domain 10),
  `[...view]/page.tsx` (domain 8). Escalate if a card fix truly needs those.

Collision note: LaunchWizard.tsx, AgentsPopup.tsx, WorkflowView.tsx owned here.
IdeaInputPage / DashboardLayout (domain 13), page.tsx (domain 8), ComposerPage
(domain 10), ReviewGatesSection (shared — coordinate), CanvasConfigRail (domain 10)
are NOT — escalate cross-file needs.
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
