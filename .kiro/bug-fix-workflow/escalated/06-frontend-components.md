# Escalated — Domain 6: frontend·components

2 cards with status `ESCALATED`.

---

## ISS-112 — No FE attachment-ref data source

| field | value |
|---|---|
| card | ISS-112 |
| domain | 06-frontend-components |
| batch | B2 |
| fix site | frontend·components (mixed) |
| escalation source | Run result 2026-09-01 |
| reason for escalation | The frontend has no attachment-ref data source to drive the feature this card requires. There is no backend endpoint or store field currently surfacing the attachment reference data the UI would need to display. |
| decision needed | **Product / backend design decision:** define where attachment-ref data comes from (new API field, new endpoint, or existing field repurposed) before any FE fix is possible. |
| card status | ESCALATED |

---

## ISS-434 — Needs `PipelineRunState.deliverableMimetype`

| field | value |
|---|---|
| card | ISS-434 |
| domain | 06-frontend-components |
| batch | B2 |
| fix site | frontend·components (mixed) |
| escalation source | Run result 2026-09-01 |
| reason for escalation | The fix requires a `deliverableMimetype` field on `PipelineRunState` that does not exist yet. Adding it requires a coordinated backend + frontend change (new field in the run-state shape, SSE event payload, and store). |
| decision needed | **Backend + frontend design decision:** agree on the field name, type, and which SSE event carries it; then sequence the backend change (domain 14/15) before the FE fix can land. |
| card status | ESCALATED |
