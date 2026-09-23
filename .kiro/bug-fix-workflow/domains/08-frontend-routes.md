# Domain 8 — frontend·routes

13 cards, 5 batches.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-342 | ANALYZED | B1 | 1 | `frontend/src/app/login/page.tsx` | A′ (ISS-342 sibling of ISS-244; ISS-352 double-submit sibling of ISS-238) + C | mixed | haiku |
| ISS-352 | ANALYZED | B1 | 1 | `frontend/src/app/login/page.tsx` | A′ (ISS-342 sibling of ISS-244; ISS-352 double-submit sibling of ISS-238) + C | mixed | haiku |
| ISS-602 | ANALYZED | B1 | 1 | `frontend/src/app/login/page.tsx` | A′ (ISS-342 sibling of ISS-244; ISS-352 double-submit sibling of ISS-238) + C | mixed | haiku |
| ISS-492 | ANALYZED | B2 | 1 | `frontend/src/app/workflow/page.tsx` | A′ (ISS-492 sibling of ISS-328) + C | mixed | haiku |
| ISS-579 | ANALYZED | B2 | 1 | `frontend/src/app/workflow/page.tsx` | A′ (ISS-492 sibling of ISS-328) + C | mixed | haiku |
| ISS-195 | ANALYZED | B3 | 2 | `frontend/src/app/[...view]/page.tsx` | A′ (ISS-350 sibling of ISS-238; ISS-195 sibling of ISS-190*) + C | mixed | haiku |
| ISS-350 | ANALYZED | B3 | 2 | `frontend/src/app/[...view]/page.tsx` | A′ (ISS-350 sibling of ISS-238; ISS-195 sibling of ISS-190*) + C | mixed | haiku |
| ISS-624 | ANALYZED | B3 | 2 | `frontend/src/app/[...view]/page.tsx` | A′ (ISS-350 sibling of ISS-238; ISS-195 sibling of ISS-190*) + C | mixed | haiku |
| ISS-376 | ANALYZED | B4 | 2 | frontend·routes (mixed) | C | full | haiku |
| ISS-407 | ANALYZED | B4 | 2 | frontend·routes (mixed) | C | full | haiku |
| ISS-442 | ANALYZED | B4 | 2 | frontend·routes (mixed) | C | full | haiku |
| ISS-405 | ANALYZED | B5 | 2 | `frontend/src/app/admin/page.tsx` | A′ (ISS-415 sibling of ISS-302) + C | mixed | haiku |
| ISS-415 | ANALYZED | B5 | 2 | `frontend/src/app/admin/page.tsx` | A′ (ISS-415 sibling of ISS-302) + C | mixed | haiku |

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
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
