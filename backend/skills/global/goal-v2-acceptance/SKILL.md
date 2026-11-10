---
name: goal-v2-acceptance
display_name: Goal v2 — Executable Acceptance Tests
description: How to write one executable acceptance test per ledger row in the fixed v2 format that run_acceptance runs in Chrome. Use in goal_v2 acceptance, build, fix and verify.
category: workflow
isBeta: false
tags:
- testing
- acceptance
- traceability
---

# Executable acceptance tests (v2)

Each testable ledger row gets `.goal/acceptance/<id>.json`. The `run_acceptance` tool executes them in Chrome,
from a fresh page load per case, and writes `.goal/trace.json` itself. Tests are written before any code, from the
requirement and the sample data. A test that is not in this exact format cannot run — `ledger_check` mode
`acceptance_schema` rejects it.

## File format

```json
{"id": "U6-6", "title": "Hold is disabled when the quote demands immediate payment",
 "fixtures": [".uploads/IB_ORDERRESHOP_flightchange_immediate_payment_2ADT.xml"],
 "cases": [
  {"name": "immediate payment disables hold",
   "steps": [
     {"verb": "goto_tab", "target": "tab-change-order"},
     {"verb": "fill", "target": "seller-id", "value": "UNISYS01"},
     {"verb": "load_file", "target": "change-order-file", "file": ".uploads/IB_ORDERVIEW_paid_cash_2ADT_RT_MAD-FRA.xml"},
     {"verb": "click", "target": "action-uc6"},
     {"verb": "load_file", "target": "uc6-reshop-file", "file": ".uploads/IB_ORDERRESHOP_flightchange_immediate_payment_2ADT.xml"},
     {"verb": "expect_disabled", "target": "uc6-pay-hold"},
     {"verb": "expect_text", "target": "uc6-pay-hold-reason", "contains": "immediate"}
   ]},
  {"name": "normal quote keeps hold available",
   "steps": [
     {"verb": "goto_tab", "target": "tab-change-order"},
     {"verb": "fill", "target": "seller-id", "value": "UNISYS01"},
     {"verb": "load_file", "target": "change-order-file", "file": ".uploads/IB_ORDERVIEW_paid_cash_2ADT_RT_MAD-FRA.xml"},
     {"verb": "click", "target": "action-uc6"},
     {"verb": "load_file", "target": "uc6-reshop-file", "file": ".uploads/IB_ORDERRESHOP_flightchange_addcol_2ADT.xml"},
     {"verb": "expect_enabled", "target": "uc6-pay-hold"}
   ]}
 ]}
```

## Step verbs (closed set)

Each step is an object whose `verb` key names the action: `{"verb": "click", "target": "uc4-generate"}`.


`goto_tab {target}` · `load_file {target, file}` · `paste {target, file|text}` · `click {target}` ·
`fill {target, value}` · `select {target, value}` · `check {target}` · `uncheck {target}` ·
`expect_visible {target}` · `expect_hidden {target}` · `expect_enabled {target}` · `expect_disabled {target}` ·
`expect_text {target, contains|equals}` · `expect_count {target, equals|min|max}` ·
`expect_xml {target, well_formed: true, root?, contains?: [...], not_contains?: [...], xpath_text?: {xpath: value}}`
· `eval {js}` (returns true; use rarely).

`target` is a `data-test` name (the builder adds it) unless it starts with `#`, `.` or `[`. Files are sandbox
paths: `.uploads/<name>` or `.goal/fixtures/<name>`. `expect_xml` reads the element's value or text; xpaths use
local names (`//SelectedPricedOffer/TotalOfferPriceAmount`), namespaces are ignored.

## Rules

1. Name every target in the test; builders must create exactly those `data-test` names. Keep names short and
   stable: `<area>-<thing>` (`uc4-generate`, `output-change`).
2. Values come from the sample files — read them, never guess (`TotalOfferPriceAmount` = 564.45 in IB_TEST03).
3. Every output requirement ends with `expect_xml` on the generated output: `well_formed: true` plus the root and
   the values the request must carry. One well-formed document means exactly one XML declaration and one root.
   When the output is a namespaced message, `contains` also carries every namespace declaration exactly as the
   sample files of that standard write it (e.g. `xmlns:ns2="…/IATA_OffersAndOrdersMessage"`), so a wrong
   schema version fails.
4. Every validation / blocking rule gets a negative case.
5. A case the samples cannot exercise uses a minimal edited copy under `.goal/fixtures/`, named after the row
   (`U6-5-even-exchange.xml`), with a one-line `README.md` entry.
6. `testable: false` rows get no file.
7. Finish with `ledger_check` mode `acceptance_schema` clean.
