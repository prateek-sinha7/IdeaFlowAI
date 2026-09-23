# Domain 3 — frontend·lib

4 cards, 2 batches.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-386 | ANALYZED | B1 | 3 | `frontend/src/lib/routes.ts` (ISS-386) | B (route-depth) | full | haiku |
| BUG-013-GROUNDED-CONTEXT | ANALYZED | B2 | 4 | `frontend/src/lib/api.ts` | C | full | haiku |
| ISS-413 | ANALYZED | B2 | 4 | `frontend/src/lib/api.ts` | C | full | haiku |
| ISS-486 | ANALYZED | B2 | 4 | `frontend/src/lib/api.ts` | C | full | haiku |

Notes:
- ISS-386: `runStepsAgent` missing a version param the sibling helpers have —
  small, mechanical, in `routes.ts`. All route literals must go through routes.ts
  (project invariant); this fix is adding the missing param there.
- B2 `api.ts`: BUG-013 (EventSource-per-run saturating the 6-conn limit) is the
  substantial one — read RunConnectionProvider too (secondary glob, read-only here;
  if it needs editing, that's a routes/providers concern → escalate cross-file).
  ISS-413 (missing created_at in get_run_events response type) + ISS-486 (untested
  query-string route) are type/lib-local.

Collision note: `api.ts` and `routes.ts` are lib-local. BUG-013's blast radius
mentions `RunConnectionProvider.tsx` — do not edit it from this domain; escalate if
the fix genuinely requires it.
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
