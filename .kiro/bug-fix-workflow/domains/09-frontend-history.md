# Domain 9 — frontend·history

13 cards, 1 batch (all one file).

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-077 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-113 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-145 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-198 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-207 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-208 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-209 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-213 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-219 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-325 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-412 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-414 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |
| ISS-629 | ANALYZED | B1 | 3 | `frontend/src/components/history/WorkflowHistory.tsx` | B (stale-state) + A′ (ISS-414 sibling of ISS-302) + C | full; one read, one verify | **sonnet** (13 cards, pagination/stale-state cluster) |

Notes:
- This is the archetypal batch: WorkflowHistory.tsx read ONCE for 13 cards. Dominant
  theme is the **pagination/cap bug family** — `runs?limit=50` never followed up, so
  chip counts, sort, search, typeCounts all operate on a capped array (ISS-198, 207,
  208, 213, 219, 325, 629). Fixing the underlying "load more / total vs fetched"
  once likely cures most of them — a shared-cause cluster, exactly what one worker
  holding the file in its head does well. Sonnet for that reasoning.
- ISS-414 replicates ISS-302/FIX-372 (DeleteModal no name prop). ISS-145/412/209 are
  stale-state (secondary globs into PreviewPanel/RevisionFamilyView — read-only here).
- ISS-219/325/629 have integration-test secondary globs (domain 4). Do NOT edit those
  tests here; if a card needs both, escalate to sequence after domain 4.

Collision note: WorkflowHistory.tsx owned here. RevisionFamilyView.tsx,
RunDetailPage.tsx appear as secondary globs — if a fix needs them and they're not
this file, escalate. Integration test files belong to domain 4.
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
