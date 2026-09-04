# Escalated — Domain 12: frontend·workflow

4 cards with status `ESCALATED` in the LaunchWizard.tsx batch (B3).

---

## ISS-189 — LaunchWizard: unknown root cause / family

| field | value |
|---|---|
| card | ISS-189 |
| domain | 12-frontend-workflow |
| batch | B3 |
| fix site | `frontend/src/components/workflow/LaunchWizard.tsx` |
| reason for escalation | Part of the ISS-228 family (saved workflow discards override fetch). Fix requires coordination — the fixer could not resolve it within the single-file boundary for this domain. |
| decision needed | **Cross-domain coordination or product design:** clarify expected behaviour for the ISS-228 family root (saved workflow + override persistence) across LaunchWizard and its cross-domain secondaries. |
| card status | ESCALATED |

---

## ISS-197 — LaunchWizard: unknown root cause / family

| field | value |
|---|---|
| card | ISS-197 |
| domain | 12-frontend-workflow |
| batch | B3 |
| fix site | `frontend/src/components/workflow/LaunchWizard.tsx` |
| reason for escalation | Same ISS-228 family. Could not be resolved within domain boundary. |
| decision needed | **Cross-domain coordination:** same as ISS-189 above. |
| card status | ESCALATED |

---

## ISS-362 — ReviewGatesSection zero-interaction (ISS-306 class)

| field | value |
|---|---|
| card | ISS-362 |
| domain | 12-frontend-workflow |
| batch | B3 |
| fix site | `frontend/src/components/workflow/LaunchWizard.tsx` |
| reason for escalation | ReviewGatesSection zero-interaction defect (ISS-306 class). The fixer identified this is part of the `ISS-429`/`ISS-362` review-gates pattern but could not close it without a product decision on how gate seeding should behave. Also related to the ADR-0013 constraint that `approval`/`security` gates are `user_allowed=False`. |
| decision needed | **Product design decision:** define the intended interaction model for ReviewGatesSection when no gates are selected / when gates are locked by the manifest. |
| card status | ESCALATED |

---

## ISS-377 — Manifest/selections exclusivity in LaunchWizard

| field | value |
|---|---|
| card | ISS-377 |
| domain | 12-frontend-workflow |
| batch | B3 |
| fix site | `frontend/src/components/workflow/LaunchWizard.tsx` |
| reason for escalation | The card requires a design decision on manifest vs. user-selections exclusivity — i.e., whether user overrides can supersede a manifest-declared gate set and under what conditions. This overlaps with `ISS-419` (domain 14) and ADR-0013. |
| decision needed | **Product / architecture decision:** define the rule for manifest-declared vs. user-selected gate exclusivity, then align ISS-419 (backend compiler gate rejection) and ISS-377 (FE presentation) under the same model. |
| card status | ESCALATED |
