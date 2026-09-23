# Domain 10 — frontend·composer

14 cards, 2 batches.

| card | status | batch | round | fix site | tier | phases | model |
|---|---|---|---|---|---|---|---|
| ISS-183 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-192 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-223 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-333 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-334 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-340 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-353 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-393 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-410 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-431 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-604 | ANALYZED | B1 | 4 | `frontend/src/components/workflow/composer/ComposerPage.tsx` | A (ISS-393 family) + A′ (ISS-353 sibling of ISS-245; ISS-431 sibling of ISS-315) + C | full; one read | **sonnet** (11 cards, family, ~large file) |
| ISS-178 | ANALYZED | B2 | 4 | frontend·composer (mixed) | A′ (ISS-489 sibling of ISS-326) + C | mixed | haiku |
| ISS-382 | ANALYZED | B2 | 4 | frontend·composer (mixed) | A′ (ISS-489 sibling of ISS-326) + C | mixed | haiku |
| ISS-489 | ANALYZED | B2 | 4 | frontend·composer (mixed) | A′ (ISS-489 sibling of ISS-326) + C | mixed | haiku |

Notes:
- ComposerPage.tsx cluster: run-once guards (ISS-333 no-length-guard, ISS-431
  replicates ISS-315/FIX-375), the getWorkflowDetail catch-all (ISS-334/410 catch
  ANY error not just 404), PPT-type hardcodes (ISS-340), and ISS-393 (part of the
  ISS-392 family owned by domain 7 — the server-sink persistence). **ISS-393 spans
  domain 7's LibraryPage — coordinate: fix the shared persistence path once, in
  whichever domain runs first, and mark the other done.** Flag to operator.
- ISS-223 (`deliverable/ppt` registered without user_allowed) has backend secondary
  globs (compiler.py, user_workflows.py, ppt.py) — that's a backend fix; escalate to
  sequence with domain 14, or fix the FE guard only and card the backend half.
- B2: ISS-178 graphLayout edge derivation, ISS-382 CanvasNode Tools chip (secondary
  glob CanvasConfigRail — domain 12-adjacent), ISS-489 replicate ISS-326/FIX-388.

Collision note: ComposerPage.tsx owned here. LibraryPage.tsx (7), AgentsPopup/
CanvasConfigRail (12), `[...view]/page.tsx` (8) are NOT — escalate ISS-393/223/382
rather than reaching across.
Status: the `status` column above is authoritative — it is what the line
reads and writes. A whole-file status could only drift from it.
