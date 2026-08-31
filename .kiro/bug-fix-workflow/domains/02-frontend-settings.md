# Domain 2 — frontend·settings

4 cards, 2 batches.

| batch | round | fix site | cards | tier | phases | model |
|---|---|---|---|---|---|---|
| B1 | 1 | frontend·settings (ISS-354) | ISS-354 | A′ sibling of ISS-245 | **replicate FIX-345** → verify | haiku |
| B2 | 2 | `frontend/src/components/settings/AccountSettings.tsx` | ISS-430, ISS-482, ISS-581 | B (confirm-dialog) + C | full | haiku |

Notes:
- ISS-354 is a tier-A′ sibling: FIX-345 already landed the root; replicate its shape
  at the login/challenge continue-button gate the card names. Skip validate/analyze.
- B2: ISS-482 is confirm-dialog class (shares the pattern with ISS-371/372/622 in
  domain 13 — but those are in DashboardLayout, a DIFFERENT file, so no collision).
  ISS-581 (ConstitutionSection double-GET race) + ISS-430 (deferred half of ISS-292,
  ungated `<select>`) are AccountSettings.tsx-local.

Collision note: AccountSettings.tsx is this domain's alone. ISS-482 also appears in
domain 13's confirm-dialog class campaign — it is OWNED here (its primary fix site
is AccountSettings.tsx); domain 13 must not touch it.
Status: NOT STARTED.
