---
phase: 33-concierge-compaction-a5
verified: 2026-07-09T00:00:00Z
status: human_needed
score: 4/4 ROADMAP success criteria proven at the phase's offline-provable bar
overrides_applied: 0
overall_verdict: PASS-WITH-CONCERNS
re_verification:
  previous_status: none
  previous_score: n/a
  note: "Initial verification. Branch feat/ui-2, tree clean at HEAD 5e20984f."
human_verification:
  - test: "Live Concierge Q&A against real Bedrock (Haiku)"
    expected: "The Concierge answers run questions grounded in real run events/artifacts, non-hallucinated"
    why_human: "Requires a live model call (SSO/Bedrock); offline uses a scripted BaseChatModel. Phase-34."
  - test: "Multi-turn prompt-cache-point placement across turns"
    expected: "P26 cache points land correctly across a multi-turn Concierge conversation"
    why_human: "Cache placement is only observable against a live provider. Phase-34."
  - test: "Live mid-run steering delivery (DEF-29-09-1)"
    expected: "A disposed steering_note reaches the running engine's live ectx"
    why_human: "_live_ectx_for_run returns None today (no live-ectx registry); durable row is the record. Phase-34."
  - test: "Live model tool-result -> proposal surfacing"
    expected: "A Concierge that decides to propose surfaces the intent -> concierge_proposal hold row -> confirm -> dispose end-to-end"
    why_human: "converse() returns str only; _drain_concierge_proposals yields [] against the current impl. Disposal+confirm CONTRACT proven offline via a test-double. Phase-34."
  - test: "FE confirm-chip round-trip end-to-end + compact affordance on real usage"
    expected: "User sees a held proposal, clicks confirm, the app POSTs {concierge:true, confirm_proposal:{...}} and the seam executes; compact surfaces on real composed-context usage"
    why_human: "RunChatLane confirm/compact are presentational callback props; the parent (DashboardLayout) does not yet thread proposals/onConfirmProposal/onCompact. Caller wiring = Phase-34 / 'plan 07'."
  - test: "Composed-context usage sub-display against a live run stream"
    expected: "ChatTokenWidget shows composed-context % once the run stream emits composedContextTokens/contextBudgetTokens"
    why_human: "Stream fields not yet emitted; sub-display degrades hidden until then. Phase-34."
concerns:
  - id: NEW-33-01
    severity: concern
    summary: "The Concierge live path is fully DORMANT end-to-end in the shipped app: no non-test caller activates it (BE: nothing sets MessageCommand.concierge=True; FE: DashboardLayout mounts RunChatLane WITHOUT proposals/onConfirmProposal/onRejectProposal/onCompact/telemetry props, and nothing POSTs concierge:true). Every piece is proven offline in isolation + at the seam/contract level, but there is currently NO end-to-end trigger anywhere in the running application. This is by phase policy (build + offline-prove; live wiring is 'plan 07'/Phase-34) and is consistent with the goldens proving intentional dormancy — but SC-1/SC-3 have zero live end-to-end path today and depend entirely on unshipped caller wiring. Disclosed in pieces across 33-03/33-04 summaries; surfaced here consolidated as the single Phase-34 activation dependency."
---

# Phase 33: Concierge + Compaction [A5] — Verification Report

**Phase Goal (ROADMAP SC 1–4):** (1) Concierge answers run questions from REAL run data; proposals execute only through existing channels (proposal-only + confirm chip). (2) `compaction:chat_history` + `context_provider:conversation` bound the composed history under budget with recent turns verbatim. (3) Post-run chat turns produce revision runs stitched into the family. (4) SC-001: a brand-new custom workflow gets lane + router + Concierge with ZERO engine/FE/orchestrator code.

**Verified:** 2026-07-09 (offline, branch `feat/ui-2`, tree clean at HEAD `5e20984f`)
**Status:** human_needed (all offline goals met; live pass items open by policy)
**Overall Verdict:** **PASS-WITH-CONCERNS**
**Re-verification:** No — initial verification.

---

## Overall Verdict: PASS-WITH-CONCERNS

Every ROADMAP success criterion is proven at the bar the phase policy sets ("build + offline-prove here; the live pass confirms"). All eight invariants I re-ran independently hold. Goldens are byte-identical with `SNAPSHOT_UPDATE` unset. The concerns are (a) the six expected, disclosed live-deferred items (Phase-34), and (b) one consolidated observation I surface: the Concierge path is fully dormant end-to-end in the shipped app because no caller (BE or FE) yet activates it — expected by policy, but the single dependency that gates SC-1/SC-3 becoming live.

---

## Per-SC Verdicts (ROADMAP SC 1–4)

### SC-1 — Concierge answers run questions from REAL run data; proposals execute only through existing channels (proposal-only + confirm chip)
**Verdict: PASS (offline contract) — live Q&A + surfacing deferred (Phase-34)**

- `chat:concierge` is ONE registered capability, `registry.resolve("chat","concierge")` returns the shared impl; model runs ONLY through `DeepAgentRunner` (grep: `create_deep_agent`=0, `DeepAgentRunner`=6 in `concierge.py`). — `test_concierge_capability.py` 7 passed.
- READ tools owner-scoped via `ScopedStore` (grep 18 refs, raw-ORM=0); PROPOSAL-ONLY tools `propose_steering_note`/`propose_revision`/`propose_gate_action` (+`update_specs`) return structured `ProposalIntent` and self-execute nothing.
- Disposal routes through the SAME Phase-29 seams (`set_review_response`/`apply_steering`/`_mint_revision_row`+`_drive_revision_to_queue`); consequential ones held behind a `concierge_proposal` confirm-chip row. — `test_concierge_proposal_channels.py` 15 passed.
- **Deferred (disclosed):** `converse()` returns `str` only; `_drain_concierge_proposals` yields `[]` against the current impl (evidence: `run_commands.py:478-489`), so live proposal surfacing is Phase-34. Live grounded Q&A needs Bedrock.

### SC-2 — compaction:chat_history + context_provider:conversation bound composed history under budget with recent turns verbatim
**Verdict: PASS (fully proven offline)**

- `compaction:chat_history` pure `compact(transcript,*,budget,keep_recent)` keeps recent turns verbatim + summarizes the tail under budget; `context_provider:conversation` self-gates on the `conversation` inject token, reads owner-scoped `run_events`, bounds via `registry.resolve("compaction","chat_history")`, returns single `{conversation_context: ...}` block, `{}` when un-gated (dormant → INV-3). — `test_chat_history_compaction.py` (4) + `test_conversation_provider.py` (9) passed.

### SC-3 — Post-run chat turns produce revision runs stitched into the family
**Verdict: PASS (offline seam contract) — live stitching deferred (Phase-34)**

- `propose_revision` disposes through the existing `_mint_revision_row` + `_drive_revision_to_queue` seam (reuses `REVISION_BASE_MAP`, no fork); a CONFIRMED revision (via the confirm round-trip body) returns `proposal.revision_run_id`. Proven at unit level (`test_concierge_proposal_channels.py`). INV-12 held: `test_chat_contract.py` 11 passed, ChatRunner untouched.
- **Deferred (disclosed):** live queue-drive stitching into the family transcript rides the same live path as proposal surfacing (Phase-34).

### SC-4 / SC-001 — a brand-new custom workflow gets lane + router + Concierge with ZERO engine/FE/orchestrator code
**Verdict: PASS (fully proven offline — milestone core value)**

- Throwaway `sc001_throwaway_wf` manifest routes identically through name-free `route_chat_turn`, resolves the shared `chat:concierge`, compiles its `chat:` DATA block to `CompiledWorkflow.chat`, and is read by the Concierge. Grep gate: `sc001_throwaway_wf` = 0 in every engine/router/concierge source path; no `pipeline_type==/spec.id==/workflow_name==` branch in the chat surface. — `test_sc001_lane_router_concierge.py` 9 passed. Manifest + CompiledWorkflow `chat` fields confirmed present via `dataclasses.fields`.

---

## Invariant Table (independently re-run)

| Invariant | Result | Evidence (command I ran) |
| --- | --- | --- |
| Capabilities registered + resolvable, drift-guard 69 | **PASS** | `test_registry_capabilities.py` green; `grep len(_KNOWN)==69` = 3 hits, `==68/66` = 0 |
| Compaction-under-budget + conversation provider (SC-2) | **PASS** | `test_chat_history_compaction.py` + `test_conversation_provider.py` green (13) |
| INV-13 (Concierge model ONLY via DeepAgentRunner) | **PASS** | `test_banned_patterns.py` 11 passed; `grep create_deep_agent concierge.py` = 0; `DeepAgentRunner` = 6 |
| Concierge proposal-only + owner-scoped + escalation + disposal | **PASS** | `test_concierge_capability.py`(7)+`test_concierge_escalation.py`(13)+`test_concierge_proposal_channels.py`(15) green; ScopedStore=18, raw-ORM=0 |
| INV-12 (ChatRunner not forked) | **PASS** | `test_chat_contract.py` 11 passed; `git diff --name-only f9c9cefd HEAD` shows NO chat_contract/ChatRunner edit |
| SC-001 (name-free lane+router+Concierge) | **PASS** | `test_sc001_lane_router_concierge.py` 9 passed; grep gate 0 in engine/router/concierge |
| INV-3 (5 goldens byte/event-identical, concierge dormant) | **PASS** | `test_chat_event_neutrality.py`+`test_phase3_cutover_verify.py`+5 characterization suites (31) green with SNAPSHOT_UPDATE UNSET; `git diff --stat golden/` EMPTY; tree clean after run |
| INV-5 (manifest chat: is DATA) | **PASS** | `grep "if .*\.chat\b|chat ==" manifest.py compiler.py` = 0 |
| import-linter | **PASS** | `/opt/homebrew/bin/lint-imports` = 4 kept / 0 broken |
| owner-scoping (IDOR→404) | **PASS** | ScopedStore reads only (18 refs), zero raw ORM in concierge.py; cross-owner denial asserted in `test_concierge_capability.py` |

**Total independently green (offline):** 116 + 46 + 31 = 193 tests across the phase's suites, plus grep/git/lint gates.

---

## Pre-existing / Out-of-scope (NOT attributed to Phase 33)

- **9 `test_clarify_defaults_match_engine` failures** (7 in `test_manifest_parity.py` + 2 in `test_manifest.py`). Confirmed root cause is a `plan.clarify.defaults` vs engine `_pipeline_defaults` mismatch (e.g. `prototype` has 4 extra items incl. `user_journeys`) — entirely unrelated to the `chat:` field added this phase. Matches the task's HEAD-vs-baseline discriminating result. Logged in `deferred-items.md`.
- **~120 CreationHub/home-redesign Playwright failures (DEF-29-06-1)** — out of scope, not touched.

---

## Human Verification Required (all disclosed live-deferred / Phase-34 — confirmed still open)

1. Live Concierge Q&A vs real Bedrock (grounded, non-hallucinated).
2. Multi-turn prompt-cache-point placement.
3. Live mid-run steering delivery — `_live_ectx_for_run` returns `None` today (`run_commands.py:361-373`, DEF-29-09-1).
4. Live model tool-result → proposal surfacing — `_drain_concierge_proposals` yields `[]` (`run_commands.py:478-489`); disposal+confirm CONTRACT proven offline via a test-double.
5. FE confirm-chip round-trip end-to-end + compact affordance — presentational callback props only; DashboardLayout mount (line 1602) threads NONE of `proposals`/`onConfirmProposal`/`onRejectProposal`/`onCompact`; caller wiring = Phase-34 / "plan 07".
6. Composed-context usage sub-display — degrades hidden until the run stream emits `composedContextTokens`/`contextBudgetTokens`.

---

## NEW Concern Not Disclosed by the SUMMARYs (consolidated)

**The Concierge live loop is fully DORMANT end-to-end in the shipped application.** I checked both edges of the wiring, not just the summaries:

- **Backend:** no non-test code sets `MessageCommand.concierge = True` (grep of `backend/app/` = 0), so `route_chat_turn`'s opt-in escalation branch (`chat_router.py:266`, `turn.concierge and ...`) is never taken in the live app.
- **Frontend:** `RunChatLane` is mounted by `DashboardLayout.tsx:1602` **without** any of the Phase-33 concierge props (`proposals`, `onConfirmProposal`, `onRejectProposal`, `compactAvailable`, `onCompact`, composed-context telemetry). Nothing in non-test FE code POSTs `concierge: true` or `confirm_proposal`.

Consequently, today the escalation branch, the confirm-chip render, the compact affordance, and the proposal surfacing/hold/confirm/dispose loop have **no live activation path anywhere in the running product** — every one is exercised only by unit tests and the throwaway SC-001 fixture. Each individual piece of this is disclosed across 33-03 (escalation marker "the FE sets") and 33-04 ("Plan 07: the caller must thread proposals/onConfirmProposal/…"), and it is consistent with the phase policy (build + offline-prove; goldens prove the dormancy is intentional). What the SUMMARYs do **not** state plainly is the aggregate: **the phase ships a complete, tested-in-isolation subsystem that is not wired to any caller**, so SC-1 and SC-3 have zero end-to-end reachability until the "plan 07"/Phase-34 caller wiring lands. This is the single gating dependency for the milestone core value to become observable, and it should be tracked as such rather than assumed live. It is **not** a Phase-33 goal failure given the explicit offline-proof policy — hence PASS-WITH-CONCERNS, not FAIL.

---

## Gaps Summary

No BLOCKER gaps. All artifacts exist, are substantive, are import-clean, and pass their offline suites; goldens are byte-identical. The only open items are the six disclosed, expected live-deferred Phase-34 checks plus the one consolidated dormancy observation above — none of which contradict the phase's offline-provable success bar.

---

_Verified: 2026-07-09 (offline)_
_Verifier: Claude (gsd-verifier)_
