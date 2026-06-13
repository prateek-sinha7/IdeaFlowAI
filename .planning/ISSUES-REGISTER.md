# Issues Register

> Running log of every issue found — product, test-infra, harness, or cosmetic — no matter how small.
> Seeded 2026-06-13 from the milestone-end live pass + Phase 15 + the in-progress UI campaign.
> Status: OPEN · FIXED · DEFERRED (recorded, intentional) · MONITORING (watch on next pass) · WONTFIX.
> Tag: `product` (user-facing/runtime), `test-infra`, `harness` (my driver, not the app), `docs`, `cosmetic`.

| ID | Sev | Tag | Status | Title | Source / Evidence |
|----|-----|-----|--------|-------|-------------------|
| ISS-001 | major | product | **FIXED** (P15, live-confirmed) | od_ppt deliverable returned the validator's QA narration, not the deck (LV-02) — broke od_ppt preview + the whole revision chain | REPORT-2026-06-12 §LV-02; closed by Phase 15 prompt contract; live run 8c060c35 resolved an 18,661-char deck |
| ISS-002 | minor | test-infra | OPEN | `test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack` fails deterministically — CPython 3.11 `wait_for` result-vs-cancel race at the 3 WS drainer sites (websocket.py:1669/:802/:1999); NOT credential-gated (LV-01) | REPORT-2026-06-12 §LV-01; fix: `asyncio.timeout()` at the 3 sites |
| ISS-003 | minor | test-infra | OPEN | `test_phase3_token_delta_live` hangs live forever at the clarify `event.wait()` — `_drive_live` never sets `clarify.mode=off` (LV-03) | REPORT-2026-06-12 §LV-03; fix: flip compiled clarify off inside `_drive_live` |
| ISS-004 | minor | product | DEFERRED (next live pass) | sdlc-governance agent family emits fabricated tool-call XML preamble (`<function_calls>`/`<invoke name="read_file">`) on live Haiku before content (F4 residual) | REPORT-2026-06-12 §F5-residual; prompt contract shipped P15; live-stream re-confirm pending |
| ISS-005 | minor | product | DEFERRED (next live pass) | `app-infra-generator` ignored its own `/api/v1` rule live (0× in 3,083 lines vs api-design 58× / devops 50×) (F5 residual) | REPORT-2026-06-12 §F5; forceful top-of-body contract shipped P15; live re-confirm pending |
| ISS-006 | minor | product | OPEN | app_builder contract drift: `tests/setup.ts` imports `getDb` but impl exports `getDatabase` — one TS2305 in the Jest global setup | REPORT-2026-06-12 §F5 re-audit, residual 1 |
| ISS-007 | trivial | product | MONITORING | IN-02: `pipeline_cancelled` ack not delivered on the live wire for `cancel_pipeline` (run row + durable log still correct; reconnect learns outcome) | REPORT-2026-06-12 §Known-Info; matches register IN-02 |
| ISS-008 | trivial | product | MONITORING | IN-04: durable-REPLAY revision frames carry `section: None` (live-attach carries the real section; replay path uncovered) | REPORT-2026-06-12 §Known-Info |
| ISS-009 | trivial | product | MONITORING | IN-01 (Phase 12): `pipeline_reconnected` live-attach ack omits `live:true` (only `live:false` is explicit) | REPORT-2026-06-12 §Known-Info |
| ISS-010 | trivial | product | DEFERRED | OTLP span export unverifiable in this env (no collector endpoint + needs a hook-declaring workflow) — declaration-driven hooks mean legacy pipelines emit none by design | REPORT-2026-06-12 §Phase-8 sweep |
| ISS-011 | minor | product | MONITORING | Phase-8 HITL live tail (3 tests) failed on SSO-token expiry mid-sweep, not product; HITL independently proven on the WS product path. Re-run after fresh `aws sso login` | REPORT-2026-06-12 §Phase-8 sweep (4 failed = 1 root cause) |
| ISS-012 | cosmetic | docs | OPEN | 113 REQ-IDs present in REQUIREMENTS.md body but missing from its Traceability table (project-wide doc drift) | surfaced by `/gsd-progress`, noted in PROJECT.md Phase-14 evolution |
| ISS-013 | minor | harness | OPEN | UI driver generic selectors don't match real Flowin controls — questionnaire submit is **"Run with defaults"** / **"Skip all & run directly"** (not submit/continue); options are **radio cards** not buttons → driver fell back to WS on S01. Fixing before the campaign runs for real. | UI campaign S01 screenshot `02-questionnaire.png` (2026-06-13) — the UI itself renders correctly; this is a harness gap |

## Notes
- This register is append-only by ID. When an issue is fixed, flip Status to FIXED and cite the closing commit/phase; don't delete the row.
- UI-campaign findings land here as scenarios run (a row per real product issue; harness/driver gaps tagged `harness`).
- The IN-01..IN-06 advisories from phases 12–14 are tracked in the per-phase REVIEW.md files; only the ones independently re-observed this pass are surfaced here (ISS-007/008/009) to avoid duplicating the phase registers.
