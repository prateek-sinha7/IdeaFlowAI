# Domain 7 — frontend·library

11 cards, 2 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | `frontend/src/components/library/LibraryPage.tsx` | BUG-073, BUG-095, ISS-318, ISS-330, ISS-335, ISS-336, ISS-378, ISS-392, ISS-441, ISS-591 | A (ISS-392/318 families) + B (silent-discard) + C | full; families share one diff | **sonnet** (10 cards, ~large file, families) |
| B2 | 1 | frontend·library (ISS-605) | ISS-605 | C (test-side a11y) | validate→fix(test)→verify | haiku |

Notes:
- LibraryPage.tsx carries a Tier-A family root: **ISS-392 + ISS-393** (AgentCapabilities
  modal has no backend persistence for Config-tab overrides) and **ISS-318 + ISS-441**
  (Skills tab mirrors into an in-memory ref, lost on reload). ISS-393/441 secondary
  globs reach AgentsPopup.tsx / ComposerPage.tsx (domains 12/10) — the REAL fix is a
  server sink; if it must edit those files, escalate to coordinate with those domains.
  This is the one domain where a family genuinely spans domains — flag it to the operator.
- Sonnet because: 10 cards in one 2k-line file, a real family requiring a persistence
  path (design judgment, not mechanical), and silent-discard is subtle.
- ISS-336 replicates ISS-232/FIX-340 (unmemoized catalog array). ISS-330/335 are the
  missing `failed`/`length===0` branches. ISS-591 markdown-render gaps.

Collision note: LibraryPage.tsx owned here. AgentsPopup.tsx (domain 12),
ComposerPage.tsx (domain 10) are NOT this domain's — escalate the ISS-392/393 family
rather than editing them.
Status: NOT STARTED.
