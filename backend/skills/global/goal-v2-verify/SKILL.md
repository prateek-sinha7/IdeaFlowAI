---
name: goal-v2-verify
display_name: Goal v2 — Verify
description: "How to verify with evidence from run_acceptance only: a full fresh run every pass, trace_fresh clean, then the route decision. Never edits the page or trace. Use in goal_v2 verify."
category: workflow
isBeta: false
tags:
- verification
- testing
---

# Verify (v2)

You judge; you never edit `prototype.html`, the tests or the trace.

1. `run_acceptance("all")` — always, every pass, even if a trace exists. It writes `.goal/trace.json`
   (runner-stamped, page hash, pass counter).
2. `ledger_check` mode `trace_fresh` must be clean (runner-written, current page, full run, every testable id).
   If it is not, run `run_acceptance("all")` again — never hand-write results.
3. Look at the page as a person once: light and dark, 1024 px wide. Anything broken that no test caught: name it
   in your reply with the ledger id it belongs to (the fix step reads your reply as feedback).
4. Decide from the trace counts only:
   final reply is exactly one line, no markdown — `{"decision": "ok"}` when no result is `fail` or `error`,
   otherwise `{"decision": "retry"}`.
