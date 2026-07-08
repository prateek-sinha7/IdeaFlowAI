# Deferred / out-of-scope items — Phase 33

Discovered during 33-05 execution. These are PRE-EXISTING failures on the clean
baseline (commit 9a81a0b3), NOT caused by 33-05 changes, and outside 33-05 scope
(SCOPE BOUNDARY — only auto-fix issues directly caused by the current task).

## Pre-existing manifest test failures (baseline 9a81a0b3)

`cd backend && python3.11 -m pytest tests/agents -k manifest` fails identically
BEFORE and AFTER 33-05 (74 passed on both; 33-05 introduces zero new failures):

- `test_manifest.py::test_display_name_authored_on_real_launchable_manifest[dotnet_to_azure]`
- `test_manifest.py::test_display_name_null_where_intentionally_unauthored[custom]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[app_builder]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[custom]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[dotnet_to_azure]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[mulesoft_to_springboot]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[ppt]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[prototype]`
- `test_manifest_parity.py::test_clarify_defaults_match_engine[user_stories]`

These are workflow.yaml data-drift vs test-expectation mismatches (launchable/display_name
metadata + clarify-defaults parity), unrelated to the `chat:` field. Left untouched.

## Phase-33 verification + code-review follow-ups → Phase 34 (live-wiring pass)

Surfaced by `33-VERIFICATION.md` (PASS-WITH-CONCERNS) + `33-REVIEW.md` (ship-with-followups)
after all 5 plans landed + were independently re-verified (193 offline tests green, 5 goldens
byte-identical, all invariants held). NONE is a Critical or a blocker; NONE has a
FIX-039-sensitive remedy (`useWorkflow.ts` untouched). All sit in the phase's explicitly
DEFERRED live-wiring space ("build + offline-prove here; the live pass confirms").

### Gating end-to-end concern (verifier NEW finding)
- **The Concierge live loop is dormant end-to-end in the shipped app.** No non-test code sets
  `MessageCommand.concierge=True` (the `chat_router.py:266` escalation branch is never taken
  live), and `DashboardLayout.tsx` (~:1602) mounts `RunChatLane` WITHOUT the Phase-33 props
  (`proposals`/`onConfirmProposal`/`onRejectProposal`/`onCompact`/telemetry) and nothing POSTs
  `concierge:true` / `confirm_proposal`. Each piece is individually disclosed (33-03/33-04);
  the AGGREGATE — a complete, isolation-tested subsystem wired to NO caller — is the single
  gating dependency for the milestone core value to become observable. Intentional (goldens
  prove the dormancy), but it is the top Phase-34 wiring task. (Was cited as "plan 07"/caller-owned.)

### Code-review follow-ups (all non-FIX-039)
- **H1 — confirm-chip hold is client-trust, not server-enforced** (`run_commands.py:825-841`
  confirm vs `:538-549` write). The durable `concierge_proposal` "pending" row is written but
  never read back / verified / resolved on confirm; the confirm turn disposes the consequential
  intent purely from client-supplied `body.confirm_proposal`, and the pending row is a permanent
  ghost. NOT an escalation (bounded by the same KAN-100 terminal fence + KAN-94 armed-gate the
  mechanical channels enforce inside `_dispose_concierge_proposal`), but the hold's
  audit/integrity + idempotency guarantee is absent. Fix: on confirm, look up the pending row by
  `concierge-proposal:{message_id}:{channel}`, verify it exists+pending, dispose from the DURABLE
  params (not client input), then mark it resolved.
- **M2 — Concierge READ tools return raw SQLAlchemy ORM rows** (`concierge.py` `_read_tools`), so
  the live model receives object reprs, not data → ungrounded answers. Masked offline by the
  scripted-fake model. Fix: serialize rows to plain dicts before returning to the model.
- **M3 — the manifest `chat:` block never reaches the live Concierge** — `_ConciergeCtx`
  (`run_commands.py:848`) omits `compiled`, so `getattr(compiled,"chat",{})` in
  `concierge._compose_system_prompt` is always `{}` on the production path. The 33-05
  manifest→compiler→plan propagation is proven at the data layer but inert live until the ctx
  carries `compiled`. Fix: thread the run's `CompiledWorkflow` onto `_ConciergeCtx`.
- **M1 (minor)** — gate-action disposal defaults a missing `action` to `approve`
  (`_dispose_concierge_proposal`). Consider defaulting to a non-consequential/explicit action.

### Live-deferred (expected human_needed — Phase-34 live pass)
1. Live Concierge Q&A vs real Bedrock. 2. Multi-turn prompt-cache-point placement.
3. Live mid-run steering delivery (`_live_ectx_for_run`→None, DEF-29-09-1).
4. Live model tool-result→proposal surfacing (`_drain_concierge_proposals`→[] today).
5. FE confirm-chip round-trip + compact affordance live-visual + parent callback→POST wiring.
6. Composed-context usage sub-display (run stream fields not yet emitted).
