# Domain 8 — frontend·routes

13 cards, 5 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | `frontend/src/app/login/page.tsx` | ISS-342, ISS-352, ISS-602 | A′ (ISS-342 sibling of ISS-244; ISS-352 double-submit sibling of ISS-238) + C | mixed | haiku |
| B2 | 1 | `frontend/src/app/workflow/page.tsx` | ISS-492, ISS-579 | A′ (ISS-492 sibling of ISS-328) + C | mixed | haiku |
| B3 | 2 | `frontend/src/app/[...view]/page.tsx` | ISS-195, ISS-350, ISS-624 | A′ (ISS-350 sibling of ISS-238; ISS-195 sibling of ISS-190*) + C | mixed | haiku |
| B4 | 2 | frontend·routes (mixed) | ISS-376, ISS-407, ISS-442 | C | full | haiku |
| B5 | 2 | `frontend/src/app/admin/page.tsx` | ISS-405, ISS-415 | A′ (ISS-415 sibling of ISS-302) + C | mixed | haiku |

Notes:
- Route literals MUST go through `routes.ts` (invariant) — a hand-written path
  anywhere here is itself a defect. Several of these cards ARE that defect.
- ISS-195 is a sibling of ISS-190, whose root has NO landed FIX card (see TRIAGE.md).
  Do NOT treat ISS-195 as A′ — validate/analyze it properly or escalate. Marked *.
- B3/B5 route-depth siblings (ISS-350/348/349) replicate ISS-238/FIX-344's missing
  depth guard. `[...view]/page.tsx` is the catch-all — surgical, high-traffic.

Collision note: each batch owns ONE route file; all disjoint. Rounds 1 and 2 keep
`[...view]/page.tsx` (a magnet file also referenced by composer/workflow cards)
isolated — it is OWNED here; domains 10/12 must not edit it.
Status: NOT STARTED.
