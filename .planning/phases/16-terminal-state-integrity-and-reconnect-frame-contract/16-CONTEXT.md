# Phase 16: Terminal-State Integrity & Reconnect Frame-Contract - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Source:** Locked decisions from the 2026-06-13 deep root-cause investigation — one Opus 4.8 agent per issue, each read IMPLEMENTATION-REGISTER.md in full and traced the live code. Findings + proper (no-hack) fixes are recorded in `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation" (clusters A+B). No interactive discuss round needed: root causes are code-proven (file:line) and the fixes are locked.

<domain>
## Phase Boundary

Make abnormal run outcomes faithful end-to-end. Today a run that did NOT truly succeed shows success chrome; a cancelled run leaves a stuck card; reconnect/replay frames diverge from live. This phase closes **6 root-caused issues** that collapse into **3 mechanisms** + 1 reconnect-contract pair:

1. **ISS-016 (MAJOR)** — a runner-surfaced model/tool error is swallowed into an empty-but-successful `agent_complete`; the run ends `pipeline_complete` instead of `pipeline_failed`.
2. **ISS-017** — the FE Preview shows the neutral "Output will appear here" empty-state for a terminal run with no content (no degraded/failed affordance). FE face of ISS-016.
3. **ISS-007 + ISS-002 (ONE root cause)** — the `pipeline_cancelled` ack is never delivered on the live wire after `cancel_pipeline`; the in-flight agent card stays "RUNNING" (007) and the cancel test is flaky (002).
4. **ISS-008 + ISS-009 (cluster B, same handler)** — durable-replay revision frames carry `section: None` (008) and the live-attach reconnect ack omits `live: true` (009).

IN SCOPE: `backend/agents/execution_engine/engine.py` (agent event-consume loop + cancel terminal emission), `backend/app/api/websocket.py` (cancel path + replay/reconnect frame construction), `frontend/src/components/preview/PreviewPanel.tsx` + `frontend/src/app/dashboard/page.tsx` (one degraded/empty affordance), and their tests (incl. fault-injection).

OUT OF SCOPE (other clusters → separate phases):
- **Cluster C (test-infra):** ISS-003 (token-delta clarify hang), ISS-010 (OTLP in-memory test), ISS-011 (HITL skip-on-expiry).
- **Cluster D (prompt/deliverable adherence):** ISS-004, ISS-005, ISS-006.
- **Cluster E (custom-workflow UX):** ISS-014 (delete dead composer), ISS-015 (WONTFIX), ISS-019 (wave-fold CSS), ISS-021 (generic deliverable renderer).
- The **optional ISS-016 "second signal"** (empty-but-clean output → degraded, gated on deliverable readback) — deliberately deferred; this phase only handles the *error-event* path + the FE affordance.
- The ISS-021 BE `deliverable_mimetype` contract.
- Any live Bedrock re-check (deferred to the next live pass per the defer-live-verification convention).

</domain>

<decisions>
## Implementation Decisions (LOCKED — proven file:line)

### A1 · ISS-016 — engine consumes the runner `error` event (MAJOR) [LOCKED]
- **Root cause:** `engine.py:2326-2377` — the `_run_agent` event-consume loop branches only on `chunk`/`usage`/`tool_call`/`tool_result`. The runner (`backend/app/agents/deep_agent_runner.py:507-527`) swallows every non-throttle exception (e.g. `ValidationException` "Operation not allowed") into `yield {"type":"error", "error": str(exc)}` and returns. With no `error` arm, that event is dropped, the stream "ends clean", `output=""`, and a normal `agent_complete` (`engine.py:2619`, `output_length:0`) is emitted. F3 terminal gating (`engine.py:1704-1891`) keys on `agent_error` counts (`_failed_agent_ids`), which this path never produces → clean `pipeline_complete`.
- **Fix:** add an `elif etype == "error":` arm in the consume loop (~`engine.py:2350`). On a runner `error`: capture the message, mark the agent failed, **skip the result/`agent_complete` block for that agent**, and route into the SAME recoverable-failure emission the timeout/except paths already use — emit `{"type":"agent_error", "data":{"agent_id": spec.id, "error": <msg>, "recoverable": True}}` (mirror how `timed_out` is handled but WITHOUT appending a completed result). Then the existing engine terminal block maps `_failed_agent_ids` → `pipeline_failed` (all agents) / `status:degraded` `pipeline_complete` (some agents), which the FE already renders. **No FE change, no F3 change.** Keys on event TYPE (`error`) → SC-001-clean.
- **Runner stays as-is:** it keeps its `{"type":"error"}` yield (the 06-05 D-05 LOCKED design keeps the runner's non-throttle swallow; only the engine's *consumption* changes). Do NOT promote the runner to re-raise — see rejected hack.
- **Test debt (MUST flip):** `backend/tests/agents/test_model_fallback.py:257-271 test_non_transient_propagates` currently encodes the bug as the expected contract (only asserts `built_for == [PRIMARY]`, never checks emitted events). After the fix it must also assert the run surfaces an `agent_error` and (single-agent) a `pipeline_failed`.
- **REJECTED hacks:** (a) re-raise ALL runner exceptions to hit the engine `except` at `:2688` — breaks the 06-05 D-05 LOCKED throttle-only-raise design + risks looping non-recoverable errors. (b) re-key F3 to gate on "any empty `agent_complete`" — conflates the exception path with a legitimately-empty completion; the correct move is to make the fault PRODUCE an `agent_error`. (c) match `ValidationException`/"Operation not allowed" text — workflow/provider-name-shaped branching violates SC-001.

### A2 · ISS-017 — FE degraded/empty affordance [LOCKED]
- **Root cause:** `frontend/src/components/preview/PreviewPanel.tsx:205` computes `hasContent`; `:291-294` renders the neutral "Output will appear here" whenever `!hasContent`. `frontend/src/app/dashboard/page.tsx:359` only sets content when `final_output` is truthy (empty → no content) and `:1006` is the same gate on history-reopen. The only non-success affordance keys on a server `degraded` flag the empty run never carried.
- **Fix:** when the run is **terminal** (not streaming) AND `!hasContent`, render a degraded/failed affordance instead of the neutral empty-state — keyed on the **server signal** (the `pipeline_failed`/`status:degraded` that ISS-016 now produces, already surfaced by `frontend/src/hooks/useWorkflow.ts` `agent_error`/`pipeline_failed`/degraded handlers). Apply on BOTH the live path and the history-reopen path (`handleSelectWorkflowRun`). Show failed-agent names + a "view details"/retry hint when present.
- **Division of labor:** ISS-016 (BE) makes the run TELL the truth (`pipeline_failed`/degraded); ISS-017 (FE) makes the FE SHOW the truth. ISS-017 cannot be fully right without ISS-016 — do them together.
- **REJECTED hack:** a purely client-side `if (terminal && !finalOutput) show "failed"` with no BE change — re-creates the IN-03 FE-vs-DB disagreement (the run is `status:completed` in the DB), mislabels a legitimately-empty deliverable, and treats the symptom not the disease. The truthful signal must come from the server.

### A3 · ISS-007 + ISS-002 — cancel delivery (ONE root cause) [LOCKED]
- **Root cause (proven, repro `/tmp/iss007_repro.py`):** the WS `cancel_pipeline` handler (`backend/app/api/websocket.py:605`) cancels the run via **destructive `task.cancel()`** instead of the engine's cooperative `cancel_event` (`engine.py:523`, checked per-chunk; clean terminal at `engine.py:1670-1678`). On cancel, the drainer's `except asyncio.CancelledError` (`websocket.py:1718-1722`) runs `bg.cancel(); raise` and dies **before** the bg task yields `pipeline_cancelled` — the frame lands on a queue no one drains. DB is correctly `cancelled`; the live wire gets no terminal → the FE card stays RUNNING (007). The flaky test (002) is the test-visible face: it only passes when the CPython-3.11 `wait_for` result-vs-cancel race (`websocket.py:1669`) happens to slip a frame through first. Mirrored in the revision drainer (`websocket.py:1997-2050`).
- **Fix (use the cooperative path + forward the terminal):**
  1. In `_handle_workflow_execution` / `_handle_revision_execution`, create an `asyncio.Event` and pass it to `engine.execute(..., cancel_event=ev)`; keep a per-run handle. In the `cancel_pipeline` handler (`websocket.py:596-615`), **`cancel_event.set()` instead of `current_pipeline_task.cancel()`**. The bg task keeps running; the engine emits `pipeline_cancelled` through the normal persisted+drained path; the drainer sends it and breaks on the terminal.
  2. **Keep destructive `task.cancel()` ONLY on the `WebSocketDisconnect` path** (`websocket.py:1176-1196`) — no socket to ack; durable replay covers reconnect. (`test_disconnect_path_cancels_running_task` must stay green.)
  3. **Close the engine pre-agent cancel gap:** the cooperative clean-terminal path is per-chunk; the *pre-agent* break (`engine.py:1509-1511`) falls through to `pipeline_complete` (`:1741`). On that break, transition to "cancelled" and emit `pipeline_cancelled` (mirror the WR-03 gate-block→cancel precedent + the outer handler at `:1670-1678`).
  4. **Defense-in-depth:** adopt `asyncio.timeout()` in place of `asyncio.wait_for()` at the 3 drainer sites (`websocket.py:1669/:802/:1999`) — the correct CPython-3.11 primitive (removes the latent swallow).
  5. *(Alternative belt, if the cooperative wiring proves heavy in one drainer: a residual-drain in the `except CancelledError` — `await asyncio.shield(asyncio.wait_for(bg_task, ~2s))` then drain `event_queue`→WS before `raise`, reusing the WR-01 residual-drain at `websocket.py:2069-2084`. The cooperative `cancel_event` is the primary, root-cause fix; the residual-drain is the fallback. The planner picks the cleanest single approach per drainer — do NOT ship both for the same path.)*
- **FE needs ZERO change** — `frontend/src/hooks/useWorkflow.ts:403` already resets every running/thinking agent → idle on `pipeline_cancelled`.
- **Tests:** `backend/tests/unit/test_pipeline_cancel.py` (the ack now deterministic — currently fails at line 180/187); tighten `test_run_revision_ws_dispatch.py::test_cancellation_lands_row_cancelled` (currently accepts the frame stuck in-queue — require it in `sent_types`).
- **REJECTED hacks:** "just swap `wait_for`→`asyncio.timeout()` and stop" (the register's own suggestion) — proven insufficient: cancel propagates but `pipeline_cancelled` delivered 0/10; FE clears cards on a timeout (the FE must not lie); sync ack inside the `cancel_pipeline` handler (races the task's own ack/DB write — the existing comment at `:599-604` rejected this for the right reason; cooperative `cancel_event` removes the race).

### B · ISS-008 + ISS-009 — reconnect frame-contract (same handler) [LOCKED]
- **ISS-008 root cause:** `websocket.py:766-767` (the durable-replay `for _r in _missed:` loop) hardcodes `"section": None`. `section` is a WS-frame-wrapper field, **never persisted** (`RunEvent` has no column). WR-03 (commit `d71c55e6`) fixed only the live-attach drainer (`:807/:822`) via `_reattach_section`, computed inside `if _has_live_task:`; the replay branch never got it.
  - **Fix:** in the replay branch, derive `_replay_section` ONCE before the loop from the owner-scoped run row's `type` via the **WR-06 inverse**: `f"{run_type.removesuffix('_revision')}_output"` when `run_type.endswith("_revision")` else `None`; apply it at `:767`. The run row is already loaded in this branch (`get_run`) — hoist it before the loop. Round-trip proven faithful for all revision types (`od_ppt_output`↔`od_ppt_revision`, etc.); non-revision keeps `section: None` (byte-identical to live-attach).
- **ISS-009 root cause:** `websocket.py:792-796` (the live-attach `pipeline_reconnected` ack) omits the `live` key; only `:783` (the no-live-task branch) sets `live: False`. FE tolerates via `useWorkflow.ts:455 if (live !== false)`, but the FE comment already (wrongly) assumes the BE sends `live: true`.
  - **Fix:** add `"live": True` to the live-attach ack `data` dict (`:794`) — symmetric, self-describing. FE keeps its tolerant `live !== false` guard.
- **Fix together** — same handler region (`websocket.py:763-822`), both one-liners.
- **REJECTED hacks:** synthesize a fake/constant section on replay or special-case a workflow name (SC-001); add a `section` DB column (over-engineering + non-additive-feeling migration for a presentation-only field); have the FE infer liveness from the `message` text.

### INVARIANTS (apply to every change)
- **INV-3 / Q3 byte+event parity:** the 5 characterization goldens (`prototype`/`od_prototype`/`prototype_revision`/`od_ppt`/`app_builder`) MUST stay byte-identical. The scripted model never raises or cancels and always streams non-empty output, so the new `error`/cancel arms are **dormant** on goldens — the plan MUST run the characterization suite to PROVE it (do not assume).
- **SC-001:** no workflow special-cased; every new branch keys on a generic event type (`error`, cancel) or the generic `run_type` suffix transform — never a workflow/model/provider name.
- **Ports & Adapters / import-linter:** engine-internal + WS-adapter + FE edits only; no new cross-boundary import. `lint-imports` stays 4 kept / 0 broken.
- **Persistence:** zero new tables, zero migrations.

</decisions>

<canonical_refs>
## Canonical References (downstream agents MUST read before planning/implementing)

### The WHY (findings + proper fixes)
- `.planning/ISSUES-REGISTER.md` → "Deep Root-Cause Investigation (2026-06-13)" table — the per-issue Root cause / Proper fix / Rejected hack / Verification columns for ISS-016/017/007/002/008/009, plus the "Verification / fault-injection levers" and "Fix-clustering" blocks. This is the spec.

### Behavior anchors (READ-ONLY unless named as an edit target)
- `backend/agents/execution_engine/engine.py` — `_run_agent` consume loop `:2326-2377` (add `error` arm); `agent_complete` `:2619`; F3 terminal gating `:1704-1891`; cooperative `cancel_event` `:523` / clean terminal `:1670-1678`; pre-agent cancel break `:1509-1511`.
- `backend/app/agents/deep_agent_runner.py:507-527` — the non-throttle swallow → `{"type":"error"}` (stays as-is).
- `backend/app/api/websocket.py` — `cancel_pipeline` handler `:596-615`; main drainer cancel handler `:1718-1722`; revision drainer `:1997-2050`; 3 `wait_for` sites `:1669/:802/:1999`; disconnect path `:1176-1196`; replay loop `:763-786` (`section` at `:766-767`); reconnect acks `:783` (`live:False`) / `:792-796` (live-attach, omits `live`); WR-01 residual-drain precedent `:2069-2084`.
- `frontend/src/components/preview/PreviewPanel.tsx:205,291-294`; `frontend/src/app/dashboard/page.tsx:359,1006`; `frontend/src/hooks/useWorkflow.ts:403,455`.

### Fix-injection / test anchors
- `backend/tests/agents/_scripted_model.py:106-176` — `ScriptedFakeChatModel([], raise_exc=ScriptedNonTransientError())` raises a `ValidationException`-coded error pre-token (the deterministic offline lever for ISS-016).
- `backend/tests/agents/test_model_fallback.py:257-271` — `test_non_transient_propagates` (MUST be flipped: currently encodes the bug).
- `backend/tests/unit/test_pipeline_cancel.py` (cancel ack); `backend/tests/unit/test_run_revision_ws_dispatch.py::test_cancellation_lands_row_cancelled` (tighten); `/tmp/iss007_repro.py` (three-layer cancel repro).
- `backend/tests/agents/test_ws_reconnect_replay.py` (add a revision-replay `section` assertion); the WR-03 live-attach contract test `test_reconnect_drainer_preserves_revision_section` (mirror onto the replay branch).
- Offline suite per the project memory: targeted parity/gate suite (~35s) + `lint-imports` at `/opt/homebrew/bin/lint-imports` (full pytest hangs offline).

</canonical_refs>

<specifics>
## Specific Ideas / Landmines

- **ISS-016 evidence note:** the S01 capture dir was overwritten by a later successful re-run, but the ISSUES-REGISTER row preserved the original (6× `agent_complete`/0-tokens/empty `final_output`; log `deep_agent_runner.astream_events failed: ValidationException ... Operation not allowed`). The mechanism is code-proven regardless of which capture survives — verify from code + fault-injection, not the screenshot.
- **Two distinct error signals — keep separate:** the *exception/`error`-event* path (ISS-016, in scope) vs the *empty-but-clean output* path (no exception, scope-DEFERRED — needs deliverable-readback gating so prototype/code-gen agents whose text stream is only tool confirmations aren't false-flagged). This phase ONLY does the error-event path.
- **Parity proof is mandatory, not optional:** because these edits touch the live terminal/cancel/replay paths, every plan task that edits `engine.py` or `websocket.py` must end by running the 5 characterization goldens + banned-patterns + migration-ledger + `lint-imports` and recording byte/event identity.
- **Cancel approach choice:** prefer the cooperative `cancel_event` as the single root-cause fix; the residual-drain is the fallback for any drainer where cooperative wiring is awkward. Do not ship both for the same path (no dual mechanism).

</specifics>

<deferred>
## Deferred Ideas
- ISS-016 second signal (empty-but-clean → degraded) — separate follow-up.
- Clusters C / D / E (ISS-003/010/011, ISS-004/005/006, ISS-014/015/019/021) — their own phases.
- Live Bedrock re-check of the `pipeline_failed`-on-model-error and `pipeline_cancelled`-delivery paths — next live pass (defer-live-verification convention).
</deferred>

---

*Phase: 16-terminal-state-integrity-and-reconnect-frame-contract*
*Context gathered: 2026-06-13 from the deep root-cause investigation (clusters A+B), code-proven file:line.*
