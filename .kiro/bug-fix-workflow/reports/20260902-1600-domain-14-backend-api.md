# Domain 14 — backend·api — Run Report

**Date:** 2026-09-02T16:00:00Z  
**Session:** resumed from PAUSED (2026-08-31T18:06:11Z)  
**Cards this domain:** 29  
**Cards resolved this run:** 4 CLOSED + 2 ALREADY_FIXED + 9 ESCALATED (= 15 remaining cards from PAUSED batch)

---

## Summary

| Result | Cards |
|--------|-------|
| CLOSED (new fix) | ISS-418, ISS-435, ISS-436, ISS-437 |
| ALREADY_FIXED | BUG-016, ISS-137 |
| ESCALATED | ISS-161, ISS-398, ISS-422, ISS-180, ISS-181, ISS-263, ISS-381, BUG-015, ISS-105 |

Previously closed (PAUSED batch from 2026-08-31): ISS-182, ISS-470, ISS-471 (CLOSED); ISS-119, ISS-133, BUG-004, ISS-144 (ALREADY_FIXED or noted); ISS-134, ISS-419 (ESCALATED). See `bug-hunter/reports/20260831T180611Z-all.md` for details.

---

## B2 — `backend/app/api/run_commands.py`

### CLOSED

**ISS-418 → FIX-483** (token undercount in Analytics)  
`_apply_terminal_output_columns` re-summed only `agent_complete` tokens, missing aux spend
(SmartPlanner, clarify one-shot, validation fix-loop) that the engine folds into the
`pipeline_complete` event's own `total_input_tokens`/`total_output_tokens` fields. Fixed by
capturing those event-level totals in the `pipeline_complete` branch and preferring them when
they exceed the collector re-sum. Degrades safely on old durable tails where the event lacks
the fields. Test: `test_apply_terminal_output_columns_populates_all_columns` still passes.

**ISS-435/436/437 → FIX-484** (unscoped reconcile flags — ISS-316 siblings)  
Three related defects in `_reconcile_terminal_status`:
- **ISS-435**: `terminal_seqs` excluded degraded `pipeline_complete` seqs, leaving
  a cancelled→resumed→degraded run stuck `"cancelled"`. Fixed by adding
  `degraded_complete_seqs` to `terminal_seqs`.
- **ISS-436**: `degraded` flag was `any()` over the whole multi-attempt tail. Fixed by
  scoping to events at or after `last_reattempt_seq`.
- **ISS-437**: `failed` flag same unscoped problem. Fixed identically.

Verification: 109/109 passed (`test_restart_resume.py` + `test_rest_answers_cancel.py` +
`test_run_shutdown.py`, 16.98s).

### ESCALATED

- **ISS-161** — A question over `/messages` was classified as REVISION. Card says
  *"re-test after FIX-219 before investigating"*. FIX-219 (`_dispose_concierge_proposal`)
  already shipped; the card is a monitor note, not an actionable fix. Recommend verifying
  the symptom is gone and closing if clean, or filing a fresh targeted card if still
  reproducible.

- **ISS-398** — `_validate_model_overrides` (lives in `run_engine.py`) has no tier
  parameter; the full catalog is accepted for any tier. Fix requires a new
  `can_use_model(tier, model_id)` helper in `entitlements.py` AND an update to
  `_validate_model_overrides` in `run_engine.py` AND the two `user_workflows.py` call
  sites. Cross-domain (touches `run_engine.py` which is shared infra). Needs a design
  ruling on whether per-model tier gates belong in `entitlements.py`.

- **ISS-422** — Inferred sibling of ISS-312 (frontend text-attachment silent truncation).
  The test-writer's note says the real fix site is **frontend**
  (`PreviewPanel.tsx:handleSelectVersion/versionViewFrom`) — a backend `run_commands.py`
  label in the card's globs is a mis-classification. Escalated to the frontend triage lane.

---

## B3 — `backend/app/api/user_workflows.py`

All 4 cards are design-decision escalations. No source changes made.

- **ISS-180** — `base_version` is written by migration 0039 but nothing reads it.
  Fix requires a comparison at read/launch time and a UI staleness signal. Spec §6 G-1
  says what the feature should do; no implementation decision has been made yet.

- **ISS-181** — Two save-time validators disagree: `WorkflowCompiler` accepts at save,
  `presort_specs` 422s at launch for the same composition. Fix is to run the DAG check
  at save time. Spec §6 G-2 describes the desired behaviour; needs a design decision on
  the save-time DAG check before implementation.

- **ISS-263** — Inferred: "Save workflow" on a conditional-gate example silently drops
  the step route. ISS-381 proved the premise is wrong — the save actually 422s on the
  roster check first. The two cards' proposed fixes conflict; needs a disposition
  decision between option 1 (relax roster check) and option 2 (extend selections map
  schema to carry `route`/`produces`).

- **ISS-381** — Roster validator at `user_workflows.py:562` rejects a built-in's own
  composed `custom-agent:<instance_id>` step ids. Fix option 1 (relax roster check for
  manifest-backed rows) is smaller and unblocks ISS-263's surface symptom. Option 2
  (project `route`/`produces` through `_synthesize_step`) is larger and needs an ADR.
  Neither has been approved.

---

## B4 — `backend/app/api/run_stream.py`

No source changes. All cards resolved via ALREADY_FIXED or ESCALATED.

- **BUG-016 (of BUG-015-016)** — ALREADY_FIXED. `_STREAM_TERMINAL_TYPES` at
  `run_stream.py:83-97` already excludes `review_gate_approved` exactly as the fix spec
  requires. No change needed.

- **BUG-015 (of BUG-015-016)** — Frontend reconnect loop (`useRunStream.ts`). Fix site
  is frontend (`useRunStream.ts`, `RunConnectionProvider.tsx`, `page.tsx`). Backend is
  not involved. Escalated to frontend triage.

- **ISS-137** — `pipeline_reconnected` is a dead frame with a live frontend reducer arm
  and 6-test suite. FIX-245 deliberately left it alone (routing it through the shared
  `terminalMarkers` would silently change an untested `status:"error"` path). Design
  decision already made; ALREADY_FIXED by intention.

- **ISS-105** — `lifespan.shutdown()` is entered before SSE generator finally-blocks
  finish unwinding (uvicorn ordering). Severity minor, no observed harm, fix would require
  either uvicorn internals or a concurrent-mutation-tolerant snapshot. Escalated as
  out-of-scope for this batch.

---

## Verification

```
backend/tests/agents/test_restart_resume.py     69 → 109 total (with sibling suites)
backend/tests/unit/test_rest_answers_cancel.py  31 passed
backend/tests/unit/test_run_shutdown.py          9 passed
────────────────────────────────────────────────────────
TOTAL: 109 passed, 0 failed, 0 errors  (16.98s)
```

---

## Artifacts

- FIX-483: `20260902-1600-FIX-483.md`
- FIX-484: `20260902-1600-FIX-484.md`
- ISS-418, ISS-435, ISS-436, ISS-437 → `status: resolved`
- `bug-hunter/OPEN-ISSUES-DEDUP.md` regenerated: 108 → 106 units
- Source change: `backend/app/api/run_commands.py` (working tree, not committed)

## Ready to commit

```
git add backend/app/api/run_commands.py
git add .knowledge/cards/20260828-2231-ISS-418.md
git add .knowledge/cards/20260828-2253-ISS-435.md
git add .knowledge/cards/20260828-2253-ISS-436.md
git add .knowledge/cards/20260828-2253-ISS-437.md
git add .knowledge/cards/20260902-1600-FIX-483.md
git add .knowledge/cards/20260902-1600-FIX-484.md
git add bug-hunter/OPEN-ISSUES-DEDUP.md
git add .kiro/bug-fix-workflow/domains/14-backend-api.md
git add .kiro/bug-fix-workflow/reports/20260902-1600-domain-14-backend-api.md
git add .kiro/bug-fix-workflow/STATE.md
git commit -m "Domain 14 backend-api: fix ISS-418/435/436/437 (token undercount + unscoped reconcile flags)"
```
