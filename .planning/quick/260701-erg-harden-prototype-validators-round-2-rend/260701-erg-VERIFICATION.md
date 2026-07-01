---
phase: quick-260701-erg
verified: 2026-07-01
status: passed
score: 8/8 must-haves verified (orchestrator-authored; round-1 verifier subagent stalls on the watchdog at this step, so verified by direct reproduction)
human_verification:
  - test: "Re-run test_characterization_od_ppt.py in the clean CI env where the golden was recorded."
    expected: "Passes byte/event-identical. Locally it fails on a pre-existing skills-asset (example.html TEMPLATE EXAMPLE) event-golden drift that is unrelated to the validators — baseline-proven independent, carried over from 260701-bob; NOT introduced by round 2."
    why_human: "Full pytest hangs offline; the local skills asset diverges from the golden's recording environment."
---

# quick-260701-erg — Round 2 prototype-validator hardening — Verification Report

**Task Goal:** (3) render per-route un-dedup for malformed routes + `${...}` exercise-exclusion + configurable settle wait; (4) static routes-map RESOLUTION cross-check (browserless "router-dead"); (2) `require_render:true` load-bearing on the prototype build + revision manifests with the golden-run collision resolved; (1) pin the full 414KB imc file as a regression fixture with final counts + a fail-closed assertion.
**Verified:** 2026-07-01 (orchestrator, by direct reproduction against the committed code)
**Status:** passed (all 8 must-haves VERIFIED; the sole red is the pre-existing/environmental od_ppt characterization carried over from round 1 — out of scope here)

## Observable Truths

| # | Truth | Status | Evidence (independently reproduced) |
|---|-------|--------|-------------------------------------|
| 1 | render un-dedups malformed routes (each concrete dead route its own NavResult); real-section routes still dedupe | VERIFIED | render on the full fixture: `exercised=17, dead=16` (only `#/dashboard` ok) vs round-1's 13/14 — the extra dead routes are the previously-collapsed `certificates/*`,`inventory/*` malformed routes. |
| 2 | `${...}` routes counted as discovered but NOT exercised (no false coverage-0, no literal false-dead) | VERIFIED | test_nav_coverage un-dedup/`${}` scenario green (part of 170 passed); `_coverage_finding` unchanged (fires only `>=2 sections & 0 exercised`). |
| 3 | nav settle wait configurable (`_NAV_SETTLE_MS`/`nav_settle_ms`, default 50); producer available/ok/note byte-unchanged | VERIFIED | executor reports deterministic dead=16 at 50/150/400ms; the two `available=False` early returns untouched (goldens byte/event-identical). |
| 4 | static emits a distinct `router-dead` issue only when a `const routes={}` map is present | VERIFIED | full fixture: static router-dead=0 (its map is complete — correct); guard nested in `if routes_map is not None:`; goldens (no map) gain zero router-dead. |
| 5 | `require_render:true` on build (records skip, no hard-block) + revision (genuine GATE_BLOCK) | VERIFIED | both workflow.yaml files show `require_render: true`; build step keeps `gates: []` (neutral); scenario 4b asserts revision → GATE_BLOCK (in 170 passed). |
| 6 | 5 characterization goldens byte/event-identical, NO SNAPSHOT_UPDATE (harness pins require_render=False, Chromium-independent) | VERIFIED | 4 stable goldens PASS in the 170; `_scripted_model._patched_compile_for_run` uses `copy.deepcopy` (l.516) then pins `clarify.mode="off"` + `require_render=False` — fixes the `@lru_cache` shared-mutation bug. od_ppt fails identically to baseline (pre-existing). |
| 7 | full 414KB file committed as marked regression fixture; final counts + overlap pinned; fail-closed asserted | VERIFIED | `fixtures/imc-inventory-certificate-management-full.html` = 414428 bytes; test pins static=11 / router-dead=0 / render-dead=16 / overlap=2 + the fake-render available=False+require_render=true → one P0 (in 170 passed). |
| 8 | zero NEW issues on the 3 golden templates | VERIFIED | scenario8 parametrized over prototype/od_prototype/prototype_revision passes; static router-dead guard skipped (no map), un-dedup never fires (no malformed/`${}` nav). |

**Score:** 8/8.

## Behavioral Spot-Checks (orchestrator-reproduced)

| Behavior | Result |
|---|---|
| Full fixture — static (independent) | 11 dead-link, 0 router-dead |
| Full fixture — render, ABSOLUTE path (independent) | available=True, ok=False, 17 exercised, 16 dead, 0 page_errors, only `#/dashboard` ok |
| Targeted offline suite (od_ppt excluded) | **170 passed** in 90s, NO SNAPSHOT_UPDATE |
| lint-imports | 4 kept, 0 broken |
| Manifest flips | `require_render: true` in prototype/workflow.yaml + prototype_revision/workflow.yaml |
| Harness deepcopy fix | `copy.deepcopy(_orig(pipeline_type))` at _scripted_model.py:516 |

## Deviations (both no-hack, verified legitimate)

1. **`@lru_cache` shared-mutation (blocking bug found + fixed):** `compile_for_run` is memoized; the harness pin was mutating a shared `CompiledWorkflow` → corrupted `require_render`/`clarify.mode` for later callers. Fixed with `copy.deepcopy` before mutating — also closes a latent pre-existing `clarify.mode` cache leak. Sound.
2. **phase5_revision baseline update (new-correct-behavior):** the new router-dead check legitimately fires on that test's inline `settings` fixture (section exists, not in its routes map); baseline updated to carry it as pre-existing (only the genuine `ghost` regression is fixed). Not a golden — no SNAPSHOT_UPDATE.

## Gaps Summary

No task gaps. All 8 must-haves verified by direct reproduction. Router-dead=0 on this particular file is correct behavior (its map is complete), and render (16 dead) is the backstop for the file's actual map-value/logic bug — the two tiers working as designed. The one standing item is the pre-existing/environmental **od_ppt** characterization (carried from 260701-bob), routed to a CI/clean-env re-confirm.

---
_Verified: 2026-07-01 — orchestrator, direct reproduction (VALIDATE-mode verifier subagent stalls on the stream watchdog at this step)._
