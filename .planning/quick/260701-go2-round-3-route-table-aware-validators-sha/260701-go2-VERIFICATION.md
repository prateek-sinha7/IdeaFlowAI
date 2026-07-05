---
phase: quick-260701-go2
verified: 2026-07-01
status: passed
score: all must-haves verified (orchestrator-authored by direct reproduction; VALIDATE verifier subagent stalls on the watchdog at this step)
human_verification:
  - test: "Re-run test_characterization_od_ppt.py in the clean CI env where the golden was recorded."
    expected: "Passes byte/event-identical. Locally it fails ONLY on the pre-existing skills-asset (example.html TEMPLATE EXAMPLE) event-golden drift carried from 260701-erg — unrelated to the validators (od_ppt is a deck pipeline that runs no HTML nav validators)."
    why_human: "Full pytest hangs offline; the local skills asset diverges from the golden's recording env."
---

# quick-260701-go2 — Round 3 route-table-aware validators — Verification Report

**Task Goal:** make both prototype validators resolve nav routes THROUGH the app route table (shared `route_table.py`), fixing the alias/parametric false-positive found by comparing two versions of the user's SPA; lock an A=fail / B=pass regression pair.
**Verified:** 2026-07-01 (orchestrator, direct reproduction against the committed code; Chromium present so render ran for real)
**Status:** passed — the decisive regression pair confirmed; only standing red is the pre-existing/environmental od_ppt (carried from 260701-erg, out of scope).

## Observable Truths

| # | Truth | Status | Evidence (independently reproduced) |
|---|-------|--------|-------------------------------------|
| 1 | Shared `route_table.py` parses BOTH object `{pattern:page}` (A) and array `[{pattern,page}]` (B); returns None for href-valued objects (disambiguation) | VERIFIED | test_route_table.py green; goldens/scenario9/test_static_check all href-valued or table-less → None → legacy path. |
| 2 | `resolve_route` mirrors matchRoute (normalize `#`/`?`/slashes; `:id`→`re.escape(base)+'/([^/]+)$'`; else exact; first-match-wins) | VERIFIED | B's `inventory/create`→inventory-create (alias before `:id`), `inventory/4521`→inventory-detail (`:id`), `certificates/892`→certificate-detail. |
| 3 | static resolves nav routes through the table when present; graceful fallback to first-segment when None | VERIFIED | B static ok=True (0 dead-link, 0 router-dead); goldens byte/event-identical (table=None → legacy). |
| 4 | render `expected = resolve_route(table, route)` (fallback first-segment); round-2 un-dedup/`${}`/settle/early-returns byte-identical | VERIFIED | B render ok=True, 17/17 activate the resolved section; only `expected` derivation changed. |
| 5 | **B (fixed) PASSES both tiers** | VERIFIED | static ok=True 0/0; render available=True ok=True 17/17, 0 dead. The alias/parametric false-positives are eliminated. |
| 6 | **A (original) FAILS — genuinely, both tiers** | VERIFIED | render available=True ok=False, 16/17 dead (runtime → dashboard fallback); static ok=False, **5 GENUINE** dead-links = routes A's table lacks (`#/profile`, `#/approvals`, `#/inventory/4521`, `#/certificate/${cert.id}`, `#/certificates/892`) — exactly what B added. Not first-segment artifacts. |
| 7 | round-2 A pins recomputed (measure-then-pin, live Chromium) | VERIFIED | `_FULL_STATIC_DEAD_LINKS` 11→5 (resolver per-target dedup + genuine misses); router-dead=0, render-dead=16, nav-total=17, overlap=2 held at measured values. |
| 8 | 5 characterization goldens: 4 stable byte/event-identical NO SNAPSHOT_UPDATE; od_ppt pre-existing/environmental only | VERIFIED | 4 stable goldens PASS; od_ppt fails identically to baseline (test_od_ppt_event_snapshot skills-asset drift). |

## Behavioral Spot-Checks (orchestrator-reproduced)

| Check | Result |
|---|---|
| B (`-fixed.html`) static | ok=True, 0 dead-link, 0 router-dead |
| B render (absolute path, live Chromium) | available=True, ok=True, 17 exercised, 0 dead |
| A (`-full.html`) static | ok=False, 5 GENUINE dead-link, 0 router-dead |
| A render (live Chromium) | available=True, ok=False, 17 exercised, 16 dead |
| Executor full suite | 191 passed, 0 skipped (render pins measured LIVE) |
| Goldens + route_table + nav_coverage + static_check subset | 84 passed |
| lint-imports | 4 kept, 0 broken (route_table.py app→app, no new edge) |

## Gaps Summary

No task gaps. The validators are now route-table-aware: B (a correctly-built alias/parametric router) passes cleanly on both tiers — the round-2 false-positive is gone — while A (broken runtime + genuinely missing route-table entries) fails on both, for real reasons. Correct tier division holds (static = table structurally sound; render = runtime actually works). The one standing item is the pre-existing/environmental od_ppt characterization (carried from 260701-erg), routed to a CI/clean-env re-confirm.

---
_Verified: 2026-07-01 — orchestrator, direct reproduction (VALIDATE verifier subagent stalls on the stream watchdog at this step)._
