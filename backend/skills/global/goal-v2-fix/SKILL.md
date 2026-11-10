---
name: goal-v2-fix
display_name: Goal v2 — Fix
description: How to fix only the failing requirements in the runner-written trace, with the smallest change, re-running their tests with run_acceptance. Never writes the trace. Use in the fix step of goal_v2.
category: workflow
isBeta: false
tags:
- fixing
- testing
---

# Fix (v2)

1. Read `.goal/trace.json` (written by `run_acceptance`). Work list: results with status `fail` or `error`.
   No trace or nothing failing → reply exactly "nothing to fix".
2. Per failing id: read its acceptance test (`failing_step`, `observed`), its ledger row and spec section. Use
   `page_outline` to find the code; read only that region.
3. Fix the cause with `edit_file` (smallest change). Fix the product, never the test. If the test contradicts the
   ledger row, say so in your reply with the row text — do not edit the test.
4. `run_acceptance("<the ids you fixed>")` until they pass, then `run_acceptance("<use-case prefix>")` for each
   use case you touched (e.g. "U6-") so nothing that passed now fails.
5. Never write or edit `.goal/trace.json` or `.goal/acceptance/*`. Write what you did to `.goal/fix-notes.md`
   (append: pass number, id, cause, change).

Reply with one line per id: fixed / not fixed (why).
