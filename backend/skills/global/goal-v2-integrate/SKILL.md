---
name: goal-v2-integrate
display_name: Goal v2 — Integration Check
description: "How to check that separately built pieces fit: run every use case end to end once, run all tests, fix integration faults before verify. Use in the goal_v2 integrate step."
category: workflow
isBeta: false
tags:
- integration
- testing
- fixing
---

# Integration check (v2)

The build made one task at a time. You look at the whole page once, as one product.

## Steps

1. `page_outline` — learn the structure (screens, data-test names, app-script functions) without reading the
   whole file. Read only the parts you need.
2. Architecture check against `spec.md` "Architecture": exactly one XML writer per output request type; no
   use-case code that emits its own `<?xml` declaration or root; one shared state; one output panel per
   workspace; no duplicate function names. `grep` for `<?xml` and for duplicate `function <name>(`.
3. `run_acceptance("all")` — read the summary.
4. Walk every use case end to end once in the browser with the real sample files (`.uploads/`): load, choose,
   fill, generate. For every generated output check it is ONE well-formed document (one declaration, one root)
   and carries the ids and amounts of the sample.
5. Fix integration faults with `edit_file` (never rewrite the page): duplicated envelopes, a use case not using
   the shared writer, state not shared, a broken step between tasks. Do not redesign; do not touch passing
   behaviour.
6. `run_acceptance("all")` again. Reply: integration faults found and fixed, then the runner summary line.

Never write `.goal/trace.json` yourself — only `run_acceptance` writes it.
