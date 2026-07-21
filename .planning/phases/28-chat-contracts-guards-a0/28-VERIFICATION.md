---
phase: 28-chat-contracts-guards-a0
verified: 2026-07-07T23:45:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
---

# Phase 28: Chat Contracts & Guards [A0] Verification Report

**Phase Goal:** Every contract the later phases build against is pinned before code: event vocabulary + golden guards, Steps artifact-derivation rules, the live-state contract, the e2e chat driver, and the ND-1..ND-9 decision records.
**Verified:** 2026-07-07T23:45:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

This is a contracts/tests/docs phase — additive only, no kernel/runtime change by design (INV-3). All must-haves were verified against the actual codebase (not SUMMARY.md claims), including spot-checks of every non-trivial line-number citation inside the contract docs against the live source.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `chat_message`/`chat_reply`/`stream_attached` are members of `_DOCUMENTED_EVENT_TYPES` | ✓ VERIFIED | `backend/tests/agents/test_phase3_cutover_verify.py:241-243`, confirmed by grep + by the passing `test_chat_events_are_documented` assertion |
| 2 | `message_id`/`replayed_through_seq` are members of `_VOLATILE_STRIP_KEYS`; `live` and card discriminators deliberately NOT stripped | ✓ VERIFIED | `backend/tests/agents/characterization/_normalize.py:182-183`; `_REQUIRED_DATA_KEYS` diff confirmed untouched |
| 3 | A characterization proof asserts the 3 chat event types never appear in any of the 5 golden event streams, paired with a documented-membership guard | ✓ VERIFIED | `backend/tests/agents/test_chat_event_neutrality.py` (90 lines) — read in full; parametrized over the 5 pipelines, reads committed fixtures only, no engine drive |
| 4 | The 5 characterization goldens remain byte-identical and event-identical after the additions (INV-3) | ✓ VERIFIED | Independently re-ran: `test_chat_event_neutrality.py` + `test_phase3_cutover_verify.py` + 5 `test_characterization_*.py` → **22 passed, 1 warning in 51.44s**; `git status --porcelain backend/tests/agents/characterization/golden/` → empty (zero fixture changes) |
| 5 | lint-imports reports 4 contracts / 0 broken | ✓ VERIFIED | Independently re-ran `/opt/homebrew/bin/lint-imports` from `backend/` → "Contracts: 4 kept, 0 broken." |
| 6 | The Steps-L2 artifact-derivation contract states the exact data source for each of the four artifact kinds, incl. the KAN-99 N-1 cap | ✓ VERIFIED | `contracts/STEPS-ARTIFACT-DERIVATION-CONTRACT.md` — pages←route_table, tasks←task_list, checks←validation_results, construction←task_progress+wave_*/subagent_* dual source, N-1 cap explained in its own section. Line-number citations (`engine.py:3105-3116` task_progress emit) spot-checked and confirmed accurate. |
| 7 | Every run-screen figure is pinned to an exact producing field, with `agent_input.context_sources` verified as carrying name+size in code | ✓ VERIFIED | `contracts/FIGURE-TO-FIELD-PINNING.md` — all cited emit sites spot-checked against `engine.py` (lines 3470-3482, 2316-2345, 2769-2780 all match exactly); `context_sources` sub-fields (`agent_name`, `summary_length`, `full_output_length`) confirmed verbatim at `engine.py:5115-5140` (`_build_context_sources`); unconfirmable figures (cache/reduction %, uploaded-file rows, live interim tokens) are honestly marked UNVERIFIED rather than asserted |
| 8 | The D-12 live-state contract table maps every real run state to chat-lane render + composer mode + Steps behavior, including all post-merge deltas | ✓ VERIFIED | `contracts/LIVE-STATE-CONTRACT.md` — 10-state table + all 5 post-merge deltas (update_specs 4th gate action + reject-confirm + terminal fence, spec-revision loop-back + terminology rule, planner window KAN-97, N-1 cap KAN-99, event-driven gates KAN-94) present as first-class sections |
| 9 | The mockWs chat-driver contract + resolved-decisions record (LOCK-A..G, ND-1..ND-13) exist, transport is additive-only, Concierge always-on, LOCK-E deferrals recorded | ✓ VERIFIED | `contracts/MOCKWS-CHAT-DRIVER-CONTRACT.md` (frame envelope + 3 chat frame types + LOCK-B + RUNUI-05 all present); `contracts/RESOLVED-DECISIONS.md` (LOCK-A..G table + 13 distinct ND rows, each RESOLVED/RESOLVED-deferred/DEFERRED with a lock source) |

**Score:** 9/9 truths verified

Note: the phase goal text says "ND-1..ND-9" but the delivered `RESOLVED-DECISIONS.md` covers ND-1..ND-13 (a superset, matching the plan's own must_haves and the POR's full decision-lock scope) — not a gap, exceeds the roadmap wording.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/tests/agents/test_phase3_cutover_verify.py` | 3 chat event types added to `_DOCUMENTED_EVENT_TYPES` w/ comment | ✓ VERIFIED | Confirmed present w/ documenting comment block (lines 229-243) |
| `backend/tests/agents/characterization/_normalize.py` | 2 volatile subkeys added w/ comment | ✓ VERIFIED | Confirmed present w/ documenting comment (lines 172-183) |
| `backend/tests/agents/test_chat_event_neutrality.py` | Proof test, ≥30 lines | ✓ VERIFIED | 90 lines; 2 test functions, both pass |
| `.planning/phases/28-chat-contracts-guards-a0/contracts/STEPS-ARTIFACT-DERIVATION-CONTRACT.md` | 4 kinds → sources, KAN-99 cap | ✓ VERIFIED | All required tokens present; content substantively correct against source |
| `.planning/.../FIGURE-TO-FIELD-PINNING.md` | figures → fields, context_sources verified | ✓ VERIFIED | All required tokens present; 3 spot-checked emit-site citations confirmed byte-accurate |
| `.planning/.../LIVE-STATE-CONTRACT.md` | D-12 table + post-merge deltas | ✓ VERIFIED | All required tokens present; full 10-state table + 5 deltas |
| `.planning/.../MOCKWS-CHAT-DRIVER-CONTRACT.md` | e2e driver API + frame catalogue | ✓ VERIFIED | All required tokens present |
| `.planning/.../RESOLVED-DECISIONS.md` | LOCK-A..G + ND-1..ND-13 | ✓ VERIFIED | All required tokens present; 13 distinct ND ids confirmed via grep |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `test_chat_event_neutrality.py` | `golden/*.events.json` | reads each stream, asserts chat types absent | ✓ WIRED | Confirmed by reading the test source and re-running it green |
| `test_phase3_cutover_verify.py::TestNewEngineEventVocabulary` | `_DOCUMENTED_EVENT_TYPES` | subset check | ✓ WIRED | Test passes; `test_chat_events_are_documented` in the neutrality module also imports and checks this directly |
| `STEPS-ARTIFACT-DERIVATION-CONTRACT.md` (construction) | backend `wave_*`/`subagent_*`/`task_progress` events | named event types + KAN-99 note | ✓ WIRED | Emit sites spot-checked in `engine.py` and `wave_scheduler.py`/`fanout.py` line citations |
| `FIGURE-TO-FIELD-PINNING.md` (Context received rail) | `agent_input.context_sources` | verified field-name mapping | ✓ WIRED | `_build_context_sources` read directly at `engine.py:5115-5140`, matches doc exactly |
| `MOCKWS-CHAT-DRIVER-CONTRACT.md` | `frontend/e2e/fixtures/mockWs.ts` | extends the `{type, data:{…,event_id,seq}}` envelope | ✓ WIRED | Doc states the additive-extension constraint and cites the exact envelope shape |
| `RESOLVED-DECISIONS.md` | POR §3 AUTONOMOUS-RUN DECISION LOCK | one row per ND with disposition | ✓ WIRED | 13-row table present, each with a lock-source citation |

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX` across all phase-created/modified files (3 test files + 5 contract docs) returned zero matches. No stub patterns, no placeholder prose, no fenced-code-implementation leakage into the "contract, not implementation" docs (confirmed 0 fenced code blocks in the 5 contract docs per the plan's own constraint).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CHAT-06 | 28-01, 28-02, 28-03 (declared on all three) | Golden neutrality — new event types in `_DOCUMENTED_EVENT_TYPES`, volatile keys in `_VOLATILE_STRIP_KEYS`, characterization proof that chat never fires on golden paths | ✓ SATISFIED | REQUIREMENTS.md line 452 marks it "Phase 28 [A0] / Complete"; codebase evidence (truths 1-5 above) directly satisfies the requirement text. No orphaned requirements found — CHAT-06 is the only ID REQUIREMENTS.md maps to Phase 28. |

### Human Verification Required

None. This phase produces no UI, no runnable endpoint, and no visual surface — every must-have is either an importable Python guard (verified by direct import + pytest) or a markdown contract document (verified by content inspection and line-citation spot-checks against live source). No human verification items apply.

### Gaps Summary

None found. All 9 derived truths verified, all 8 required artifacts exist and are substantive (not stubs — several are 70-100+ line documents with tables, verified line citations, and explicit UNVERIFIED flags where a figure could not be confirmed rather than fabricating a value), all key links hold, CHAT-06 is satisfied and correctly traced, no anti-patterns, additive-only honored (diff `826a011d..HEAD` is 3 additive test files + 5 additive doc files + planning-doc updates only — zero production backend/frontend code touched), no golden fixture regenerated, no decision re-opened.

---

_Verified: 2026-07-07T23:45:00Z_
_Verifier: Claude (gsd-verifier)_
