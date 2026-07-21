# Phase 49: Gate Resume Across Restart [R4] — Research

**Researched:** 2026-07-19
**Domain:** ExecutionEngine restart-resume tier · HITL review/clarify gate re-entry (Python · FastAPI · LangGraph checkpointer · asyncio HITL)
**Confidence:** HIGH (every anchor read at file:line on `feat/ui-2` HEAD; baseline suite run offline)

> Research-only deliverable. No source edited. All line numbers are current HEAD (`backend/agents/execution_engine/engine.py` = 7489 lines).

---

## Summary

RESUME-17 completes the R0–R3 tier: make branch (a) of `restore_non_terminal_runs` **re-arm** (not fail) a `waiting_for_user` run when it is a compiled-manifest run with durable state, so both clarify and review gates survive a restart. The machinery to do this WITHOUT a model re-run already exists in three shipped forms that this phase composes: (1) `derive_open_gate` (chat_router.py:192) + `_dangling_review_gate` (run_stream.py:119) already derive an open gate from durable `run_events` purely; (2) `_run_agent`'s `pending_revision_output` short-circuit (engine.py:2978–3042) is a working precedent for **re-opening a gate with persisted output and zero model call**; (3) `resume_run`→`_execute_impl(_resume_from=k, _is_resume=True, live_ectx_register=…)` (engine.py:6916) already re-enters the single dispatch loop at a step offset with all Phase-46 live-layer/queue hooks threaded.

**Recommended shape — 3 plans (matches CONTEXT decomposition):**
- **49-01 — Pendency derivation + classification & re-arm skeleton.** Factor ONE shared open-gate derivation (promote `derive_open_gate` to a shared home both chat_router and the engine call); add the public store accessor for `_resume_events` (IN-02); flip branch (a) fail→re-arm gated on `_is_resumable_in_flight`; **flips the KAN-88 test green here** (status stays `waiting_for_user`, `resume_run` not called by the classifier — the re-arm driver is spawned separately).
- **49-02 — Review-gate re-entry at the gate phase, all five actions.** Open-gate override in `_first_incomplete_step`/`_compute_resume_offset` so a produced-but-ungated step is re-entered in GATE MODE; a `pending_revision_output`-style sentinel in `_run_agent` that skips the model call, re-seeds `output`/`ectx.last_streamed` from the max-version ref, re-emits `review_gate_ready`, re-arms the store event, and falls into the existing wait/consumer; redo-attempt continuation derived from durable evidence.
- **49-03 — Clarify twin + KAN-88 hardening + regression floor.** Symmetric clarify re-arm (replay questions from the durable `questionnaire_ready` payload, re-enter the wait, proceed into normal dispatch on answers); dedup/double-emit proofs; goldens dormancy; the at-risk suite held at baseline.

**Primary recommendation:** Do NOT build a parallel gate machine. Re-enter the ONE existing `_run_agent` run+gate loop at its gate wait via a resume sentinel, exactly mirroring the shipped `spec_revision_pending_output` re-open path — the crux is the classifier override (an open gate must beat the "produced ⇒ complete" disjunct), not the wait.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Restart classify → re-arm vs fail | Kernel (engine `restore_non_terminal_runs`) | — | Startup scan owns branch (a); `_is_resumable_in_flight` is the shipped gate |
| Open-gate pendency derivation | Shared pure fn (app `chat_router` today) | Kernel reads it via injected/duplicated pure logic | Must be name-free + shared (INV-12); banned-pattern gate forbids `pipeline_type ==` in `agents/execution_engine/` |
| Gate-mode step re-entry | Kernel (`_first_incomplete_step` / `_run_agent` loop) | — | The consumer lives inside `_run_agent`; only the kernel can re-enter it |
| HITL waiter (asyncio.Event) | `ArtifactStore` (in-memory, per-process) | — | The store owns the resume/review events; re-arm reuses `get_review_event`/`get_resume_event` |
| Answer/gate ingress (POST /gate, /answers) | App (`run_commands`) | — | Byte-unchanged; consumes the re-armed events transparently |
| SSE gate re-emit on open | App (`run_stream` D-14g) | — | Already re-emits `review_gate_ready` from durable events; FE story already done |
| Driver lifecycle (queue/task/live-ectx) | App bridge (`run_engine`) injected into kernel | Kernel drives | Ports & adapters — kernel reaches app only via injected callbacks (main.py:141–154) |

---

## Verified Current-State Anchors

All confirmed by reading HEAD.

| Symbol | Location | Current behavior |
|--------|----------|------------------|
| `restore_non_terminal_runs` | engine.py:4937 | 3-way classify. Branch (a) = **fail** (`:4990–5008`); branch (b) = `_stamp_resume_marker` + register queue/task + `create_task(resume_run)` (`:5009–5059`); branch (c) = WR-05 fail (`:5060–5071`) |
| Branch (a) as shipped | engine.py:4990–5008 | `wr.status = "failed"` + WR-05-clarify error. THIS is the KAN-88 flip to reverse |
| `_is_resumable_in_flight` | engine.py:5088 | True iff `compile_for_run(wr.type)` succeeds AND (≥1 `read_events` OR `tree()` OR `read_wave_runs` row), owner-scoped. Offline/no-DB ⇒ False (WR-05 path) |
| `resume_run` | engine.py:6744 | Reads durable `workflow_runs` row → `_compute_resume_offset` → `_execute_impl(_resume_from=offset, _is_resume=True, selections=…, live_ectx_register=self._resume_live_ectx_register, _sink=…)`. **Drives with `cancel_event=None`** (no cancel kwarg at :6916) |
| `_compute_resume_offset` | engine.py:7015 | Builds temp ectx+scoped_store → `_first_incomplete_step`. Any failure ⇒ offset 0 |
| `_first_incomplete_step` | engine.py:6400 | Per-step completeness. **Non-wave step: complete iff `agent_id in produced_agents OR completed_step_events` (`:6550`)** — the disjunct that silently skips a produced-but-ungated step. task_loop = distinct-task count vs parsed total; wave = terminal wave rows |
| `_run_agent` redo loop | engine.py:2969 (`while True:`) | Loop locals `redo_directive`/`redo_derived_from`/`redo_attempt`/`spec_revision_attempt` reset at `:2965–2968` |
| `pending_revision_output` short-circuit | engine.py:2978–3042 | **The precedent:** if `ectx.spec_revision_pending_output` is set, sets `output` from it, updates `results`, and **jumps straight to `_run_review_gate` skipping the model call** |
| Inline gate consumer (post-stream) | engine.py:3827–3998 | `_gate_rejected`→cancel; `_gate_edited`→dual_write + results update; `_gate_redo`→set locals + `redo_attempt += 1` + `record_gate_event(spec.id,"human","redo",…)` + break; `_gate_update_specs`→sub-pipeline + `spec_revision_attempt += 1` + `ectx.spec_revision_pending_output = …` + break |
| Redo thread-id | engine.py:3185–3198 | `thread_id = f"{run}:{spec.id}"`; **`if redo_attempt: thread_id = f"{thread_id}:redo{redo_attempt}"`** — collision is the P23 checkpointer-replay bug |
| `_run_review_gate` | engine.py:4764 | `gate_key=f"{run}:{agent_id}"` (`:4802`); `get_review_event`→`clear`→emit `review_gate_ready` (`:4822`)→`await event.wait()` (`:4866–4869` plain wait when `cancel_event is None`)→read response→yield `_gate_*` |
| `ArtifactStore` HITL | store.py:42,53,111,118 | `_resume_events` dict; `get_resume_event` / `get_review_event(gate_key)` (`review:{gate_key}` key); `set_review_response`/`set_questionnaire_responses` set the event |
| `derive_open_gate` | chat_router.py:192 | Pure `(kind, gate_key)` from events; review beats questionnaire; resolution vocabularies at `:72` (`_QUESTIONNAIRE_RESOLUTIONS`) + `:84` (`_REVIEW_RESOLUTIONS`) |
| `_dangling_review_gate` / `_GATE_RESOLUTION_TYPES` | run_stream.py:119 / :68 | Last unresolved `review_gate_ready`; D-14g re-emits it on SSE attach (`:188–191`) |
| `_gate_is_pending` (IN-02) | run_commands.py:134 | `store._resume_events.get(f"review:{gate_key}")` private peek → PUBLIC accessor target |
| Clarify wait | clarify_engine.py:261–277 | `get_resume_event`→`clear`→emit `questionnaire_ready {questions, round}`→`await event.wait()`→read responses→`questionnaire_complete` |
| Planner/clarify SKIP on resume | engine.py:1695,1708 | `_resuming = _resume_from > 0`; `skip_planner = compiled.planner=="skip" or _resuming`. **A resumed run never re-runs planner OR clarify** (see Clarify Twin caveat) |
| Dispatch loop offset skip | engine.py:2162,2171 | `for i, spec in enumerate(ordered_agents): if i < _resume_from: continue` (the single dispatch loop; enumerate-pin = 1) |
| Resume live-layer/cursor block | engine.py:2084–2149 | `_is_resume` gate: `_compute_resume_completed_task_ids`, `_rematerialize_artifacts_to_disk`, `_redrain_steering_notes` |
| App-layer hook wiring | main.py:141–155 | `_resume_register_queue/_register_resume_task/_cleanup`, `_resume_live_ectx_register/_unregister`, `_resume_milestone_sink` all set BEFORE `restore_non_terminal_runs()` |
| gate_events audit row | gate_events.py:26 + kernel_services.py:279/1118 + authz.py:869/904 | Cols `run_id, owner_id, workspace_id, step, gate, outcome, detail`. Redo writes `(step=spec.id, gate="human", outcome="redo")` (engine.py:3907). `read_gate_events(run_id)` default-deny |
| strategy→`_run_agent` chain | single_shot.py:60 → kernel_services.py:1230 → engine._run_agent | `ctx.runner.run_agent(step, ctx)` → `engine._run_agent(...)`; the gate lives inside `_run_agent` |

---

## Pendency Derivation (the shared home — IN-02)

There are **three near-duplicate derivations of "is a gate open?"** today:

1. `derive_open_gate(events)` — chat_router.py:192 — the **complete, canonical** one: returns `(kind, gate_key)`, handles BOTH clarify and review, review-beats-questionnaire precedence, dict-or-ORM rows. Resolution sets: `_QUESTIONNAIRE_RESOLUTIONS` (chat_router.py:72) and `_REVIEW_RESOLUTIONS` (chat_router.py:84).
2. `_dangling_review_gate(rows)` — run_stream.py:119 — **review-only** subset: returns the last unresolved `review_gate_ready` ROW; uses `_GATE_RESOLUTION_TYPES` (run_stream.py:68, identical set to `_REVIEW_RESOLUTIONS`).
3. `_gate_is_pending(store, gate_key)` — run_commands.py:134 — **not durable** — an in-memory `store._resume_events` peek (the IN-02 debt).

**Verified fact:** `_REVIEW_RESOLUTIONS` (chat_router.py:84) and `_GATE_RESOLUTION_TYPES` (run_stream.py:68) are **byte-identical frozensets** — `{review_gate_approved, pipeline_complete, pipeline_cancelled, pipeline_failed, budget_aborted, error}`. `derive_open_gate` is the superset (it also derives clarify). **CITED**.

**Design — ONE shared home (Claude's discretion, INV-12):**
- Promote the review-resolution vocabulary + the pure open-gate scan to a **single module the kernel and app both import**. `derive_open_gate` already lives in `app/api/chat_router.py`, but the **kernel cannot import `app.*`** (import-linter forbidden direction; engine reaches app only via injected callbacks — main.py:138). Two valid options:
  - **(Recommended) Move the pure derivation to a name-free module the kernel MAY import** — e.g. `agents/execution_engine/gate_pendency.py` (or an existing kernel-side pure module) exporting `derive_open_gate(events) -> (kind, gate_key)` + the resolution frozensets. `chat_router.derive_open_gate` and `run_stream._dangling_review_gate` then re-export/wrap it (app→kernel import is allowed; kernel→app is not). This satisfies INV-12 (one derivation) AND the import-linter direction. Confirm the target module has NO app/kernel-forbidden imports (it is pure over event dicts — chat_router.py:203–216 already reads via getattr/get, so it lifts cleanly).
  - Alternative: keep `derive_open_gate` in the app and have the engine call a passed-in pure callable (a fifth injected hook). More surface than option 1; prefer option 1.
- **Public store accessor (IN-02, LOCKED):** add a public method on `ArtifactStore` (store.py) — e.g. `def review_event_pending(self, gate_key) -> bool` and/or `def get_registered_review_event(self, gate_key) -> asyncio.Event | None` — that encapsulates the `self._resume_events.get(f"review:{gate_key}")` + `not event.is_set()` logic. `run_commands._gate_is_pending` (run_commands.py:134, and its callers at :209/:644/:797) then call the accessor instead of poking `store._resume_events`. Keep `_gate_is_pending`'s helper signature or inline the accessor — either way the `store._resume_events.get(...)` literal disappears from the app layer.

**Clarify pendency — exact durable resolvers (CONFIRM):** an open clarify gate = a durable `questionnaire_ready` (chat_router.py:68) with NO subsequent event in `_QUESTIONNAIRE_RESOLUTIONS` = `{questionnaire_complete, pipeline_start, pipeline_complete, pipeline_cancelled, pipeline_failed, error}` (chat_router.py:72). The engine emits `questionnaire_complete` after answers are merged (clarify_engine.py:295) — that is the durable resolver. **VERIFIED** (chat_router.py:72; clarify_engine.py:295).

**Who calls what after factoring:**
- `restore_non_terminal_runs` branch (a) → reads durable events (via `_is_resumable_in_flight`'s owner-scoped store) → shared `derive_open_gate` → `(kind, gate_key)` decides review-rearm vs clarify-rearm vs (no open gate → fall through).
- `_compute_resume_offset`/`_first_incomplete_step` → shared `derive_open_gate` for the review open-gate OVERRIDE (see crux below).
- `run_stream`/`chat_router`/`run_commands` → unchanged public behavior, now backed by the shared home + the store accessor.

---

## Branch-(a) Re-Arm Design

**Current (engine.py:4990–5008):** `wr.status = "failed"` unconditionally for every `waiting_for_user` row.

**Target:** flip fail→re-arm ONLY when the branch-(b)-style gate passes (`await self._is_resumable_in_flight(wr)` — engine.py:5088) AND the durable events show an open gate. Otherwise keep the byte-unchanged fail (goldens + `test_stateless_run_keeps_wr05_failed_path` untouched; the WR-05-clarify message path stays for the stateless case).

**Insertion point + ordering (arm-then-classify, LOCKED fail-safe):**
```
if wr.status == "waiting_for_user":
    if await self._is_resumable_in_flight(wr):
        kind, gate_key = derive_open_gate(<durable events for wr>)   # shared home
        if kind in ("review", "questionnaire"):
            try:
                # ARM FIRST — guarantee a live waiter exists before leaving waiting_for_user
                await self._store.get_review_event(gate_key)  # or get_resume_event(run) for clarify
                # register queue+task via the injected 46-05 hooks (mirror branch b :5032–5058)
                _task = asyncio.create_task(self._rearm_gate_run(pipeline_run_id))
                # status UNCHANGED → stays "waiting_for_user" (KAN-88 assertion)
                resumed_gate += 1
            except Exception:
                # fail-safe: fall back to the CURRENT fail behavior (KAN-88 rationale)
                wr.status = "failed"; wr.error = "...WR-05-clarify..."; abandoned += 1
        else:
            wr.status = "failed"; ...   # no derivable open gate → current fail
    else:
        wr.status = "failed"; ...       # stateless → WR-05-clarify (byte-unchanged)
```
- **KAN-88 rationale honored:** the fix is "recreate the waiter", not "don't fail". Arm the store event (and spawn the driver that will `await` it) BEFORE leaving `waiting_for_user`. If arming/spawn raises → the current fail path (fail-safe).
- **The KAN-88 test flips here:** `test_waiting_for_user_run_is_rearmed_not_driven` (test_restart_resume.py:877) seeds a `waiting_for_user` `sample_wave` row with durable state via the harness. It asserts (1) `engine.resume_run` (spied) is **not** called by the classifier, and (2) status stays `waiting_for_user`. **The re-arm driver must NOT be `resume_run`** (the spy would catch it) — it is a NEW method (`_rearm_gate_run` or a `resume_run(..., gate_only=True)` variant that the test does not spy). Since the test replaces `engine.resume_run` with a spy and calls only `restore_non_terminal_runs`, spawning a distinct coroutine (or the create_task never awaited within the test's event-loop turn) keeps `resume_called["n"] == 0`. **Confirm the driver entry point is not `resume_run` verbatim.** See KAN-88 section.
- **Note (test harness reality):** `_is_resumable_in_flight` calls `compile_for_run(wr.type)`; the test patches `compile_for_run` for `sample_wave` and seeds `wave_runs`/`run_events`, so `_is_resumable_in_flight` returns True in the test. But the seeded `waiting_for_user` row in the KAN-88 test has NO durable events seeded (only the `workflow_runs` row via `_seed_workflow_run`). **VERIFY:** with no durable rows, `_is_resumable_in_flight` returns False → the test would hit the else/fail branch and status would go to `failed` (test fails). **This is load-bearing:** either (a) the re-arm must NOT depend on `_is_resumable_in_flight` for the status-stays-`waiting_for_user` outcome, OR (b) the test seeds enough state. Re-reading the test: it seeds only the run row; the current code sets `failed`, and the assertion wants `waiting_for_user`. So the design must leave `waiting_for_user` UNCHANGED for a `waiting_for_user` row even when not resumable-in-flight — i.e. **the safe default for `waiting_for_user` is "leave it armed/untouched", and only actively fail on an explicit non-recoverable condition.** RECONCILE with the LOCKED decision (re-arm only for compiled+durable): the KAN-88 test's row IS compiled (`sample_wave` patched) — the missing piece is durable rows. **Recommend:** for branch (a), treat "compilable pipeline" as sufficient to LEAVE the status `waiting_for_user` (arm the event, spawn nothing if no open gate derivable) rather than failing; reserve `failed` for the genuinely stateless/uncompilable legacy case. Confirm against the test at plan time — the test is the contract.

---

## Gate-Mode Re-Entry (review) — the crux

### The completeness interaction (LOAD-BEARING, verified)
For a produced-but-ungated `single_shot` step, `_first_incomplete_step` returns `continue` at engine.py:6550 because `agent_id in produced_agents` (the durable `artifact_refs` row exists — `_dual_write_artifact` wrote it before the gate opened). **A naive resume SKIPS the unresolved gate** — the offset lands PAST step k. **CONFIRMED** by reading `:6548–6552`.

### The open-gate override
Insert, in `_first_incomplete_step` (before the non-wave `produced_agents` check at :6548) OR in `_compute_resume_offset` before returning:
```
open_kind, open_gate_key = derive_open_gate(<durable run_events already read at :6431>)
if open_kind == "review" and open_gate_key:
    k = index of the agent whose id == gate_key.split(":", 1)[1]   # gate_key = f"{run}:{agent_id}"
    return k        # re-enter step k in GATE MODE (do not skip, do not re-run the model)
```
- **Generic keying (INV-1):** the step is identified by parsing `agent_id` out of the durable `review_gate_ready` payload's `gate_key` (`{run_id}:{agent_id}`, engine.py:4802) and matching it to `ordered_agents[i].id` — zero workflow/agent-name literals.
- **Reuse the already-read events:** `_first_incomplete_step` already calls `store.read_events(ectx.run_id, 0)` at :6431 — pass those same rows to `derive_open_gate` (no extra round-trip).
- **No conflict with Phase-46 cursor / Phase-48 reconciler:** the override only changes the RETURNED OFFSET; `_compute_resume_completed_task_ids` (:6557, gated on `_is_resume` at :2084) and `_rematerialize_artifacts_to_disk` (:2137) run independently and are keyed per-step — re-entering step k in gate mode does not perturb them (step k for a gated `single_shot`/spec agent is not task-granular, so its cursor entry is empty).

### Skip-the-model re-entry inside `_run_agent`
Mirror the **shipped** `pending_revision_output` short-circuit (engine.py:2978–3042) exactly:
1. Before the dispatch loop re-enters (in the `_is_resume` block ~engine.py:2084–2149), for the open-gate step set a resume sentinel on `ectx`, e.g. `ectx.gate_reentry = {"agent_id": <k>, "output": <max-version content>, "artifact_kind": <kind>, "gate_key": <key>}`. Seed `output` from the persisted max-version ref via `_latest_typed_content(ectx, agent_id)` (engine.py:5631 — max(version), F5 discipline) AFTER `_hydrate_artifacts_from_store` (engine.py:6049, called on resume at :1370) has re-populated `ectx.artifacts` from the durable graph. **This satisfies WR-02** (`ectx.last_streamed` must be the real output the gate reviews).
2. At the top of `_run_agent`'s `while True:` (alongside the `pending_revision_output` check at :2978), add: if `getattr(ectx, "gate_reentry", None)` matches `spec.id`, set `output = ectx.gate_reentry["output"]`, seed `ectx.last_streamed = output`, ensure a `results[-1]` entry for `spec.id` exists, **clear the sentinel (consume-once)**, and jump straight into the `if self._should_gate(spec, ectx):` → `_run_review_gate(...)` block (the identical call shape at :2987–3041), skipping `agent_start`/`_compose_context_message`/the `astream_events` model call entirely.
3. `_run_review_gate` (engine.py:4764) then does `get_review_event(gate_key)` → `clear` → **re-emit `review_gate_ready`** (existing type, engine-counter seq via the resume sink at :6938) → `await event.wait()`. **The store event is the SAME one branch (a) armed** (`review:{gate_key}`), and the re-emit re-arms it (clear+wait). Falls into the EXISTING consumer.

### All five actions post-restart (identical, via the existing consumer at :3827–3998)
- **approve** → generator exhausts without a break → `return` from `_run_agent` → the dispatch loop continues to k+1 (downstream proceeds). ✓
- **reject** → `_gate_rejected` → `pipeline_cancelled` + terminal. ✓
- **edit** → `_gate_edited` → `_dual_write_artifact` with `derived_from = _latest_typed_ref_id` (KAN-98 retained-edit + Phase-48 lineage, engine.py:3864–3877). ✓
- **redo** → `_gate_redo` → new `:redo{N}` thread (see continuation below). ✓
- **update_specs** → `_gate_update_specs` → the Phase-27 sub-pipeline fires from the re-entered loop (engine.py:3918–3988). ✓

### Loop locals that MUST be reconstructed
`redo_attempt`, `spec_revision_attempt`, `redo_directive`, `redo_derived_from` all reset to 0/empty at `_run_agent` entry (engine.py:2965–2968). On gate re-entry, `redo_directive`/`redo_derived_from` correctly start empty (a fresh gate action supplies them). **`redo_attempt` and `spec_revision_attempt` must be seeded from durable evidence** or a post-restart redo reuses a pre-restart `:redo{N}` thread → the P23 checkpointer-replay bug (the model "remembers" its rejected output). See next section.

---

## Redo / Update-Specs Continuation

### `redo_attempt` — derive prior count from durable evidence
Two candidate signals (Claude's discretion → **pick the robust one**):

**(A) P23 redo `gate_events` audit rows (recommended primary).** The inline `_gate_redo` consumer writes `record_gate_event(spec.id, "human", "redo", {"has_instructions": …})` (engine.py:3905–3910) → a `gate_events` row with `step=spec.id, gate="human", outcome="redo"` (gate_events.py:36–38). Count via `ctx.runner.read_gate_events(run_id)` (kernel_services.py:1118 → authz.py:904, default-deny owner-scoped): `prior_redos = len([r for r in rows if r.step==spec.id and r.gate=="human" and r.outcome=="redo"])`. Seed `redo_attempt = prior_redos`. **Caveat (honest):** the audit row is written **best-effort** (engine.py:3901–3915, "Never breaks the run") — a persist failure under-counts.

**(B) Artifact version count.** Each redo re-run writes a new versioned ref via `derived_from` lineage (engine.py:3865/3893). `versions = count of refs where producer_agent==spec.id AND kind==artifact_kind`. But edits ALSO mint versions (engine.py:3865) — over-counts.

**Recommendation:** seed `redo_attempt = max(gate_events_redo_count, artifact_version_count − 1)`. Because the FAILURE MODE to avoid is **reusing** a `:redo{N}` thread id (collision = the replay bug), the fail-safe direction is to over-estimate N, never under-estimate. Taking the MAX of both durable signals guarantees the next `:redo{N}` id is strictly greater than any pre-restart thread. This is the robust choice; document the reasoning in the plan.

### `spec_revision_attempt` — for update_specs
**Gap (verified):** the inline `_gate_update_specs` consumer (engine.py:3918–3988) does **NOT** write a `gate_events` audit row (only `_gate_redo` does, at :3905). So there is no direct durable count of prior spec-revision cycles. `spec_revision_attempt` feeds `revision_index=spec_revision_attempt` into `_run_spec_revision_sub_pipeline` (engine.py:3952) which threads it into the sub-pipeline's checkpoint thread ids. **Recommendation:** derive from the count of durable revised-spec artifact versions for the sub-pipeline's spec kind (the sub-pipeline re-runs specify→plan→analyze, each writing versioned refs), seeded fail-safe HIGH like redo_attempt; OR add a best-effort `record_gate_event(spec.id,"human","update_specs",…)` in the inline consumer this phase so the count becomes symmetric with redo. The latter is a 1-line additive audit row (dormant on goldens — they never update_specs) and makes the derivation robust. **Flag as an open decision for the planner** (Assumptions Log A2).

---

## Clarify Twin

**The asymmetry (verified, load-bearing):** a resumed run (`_resume_from > 0`) SKIPS planner AND clarify (`skip_planner = … or _resuming`, engine.py:1708), and the clarify gate only fires when `gate_verdict == "CLARIFY_REQUIRED"` (engine.py:1835), which a resumed run never sets. A clarify-parked run has NO produced steps, so `_first_incomplete_step` returns offset 0 → `_resuming = (0 > 0) = False` → `resume_run`'s `_execute_impl` would **re-run the planner AND re-generate clarify questions via the LLM** (clarify_engine.py:247 `_generate_questions`). That violates "no model re-run / replay questions from the durable payload".

**Design — a dedicated clarify re-arm (do NOT route clarify through the review offset):**
- Branch (a), when `derive_open_gate` returns `("questionnaire", None)`, spawns the clarify re-arm driver (distinct from the review one).
- The driver replays the durable `questionnaire_ready` payload's `questions` + `round` (persisted in `run_events`; the emit shape is at clarify_engine.py:266–274) and re-enters the wait: `get_resume_event(run)` → `clear` → re-emit `questionnaire_ready` (existing type, engine-counter seq) → `await event.wait()`. This is a **replay** — no `_generate_questions` LLM call.
- Answers ride the **UNCHANGED** `POST /{id}/answers` (run_commands.py; `set_questionnaire_responses` sets the same `_resume_events[run]` event — store.py:80). On submit, the run must proceed into the **normal dispatch** (planner→agents) exactly as a never-restarted run.
- **Multi-round semantics (`clarify.rounds`) unchanged:** the clarify loop is `while round_num < effective_rounds` (clarify_engine.py:244). Replaying one round and proceeding on answers matches the live behavior; if the durable payload shows round N of M, the re-arm replays round N and the subsequent evaluation (clarify_engine.py:314–317) decides whether to ask round N+1 or PROCEED. **Simplest faithful implementation:** re-enter `ClarifyEngine.run` with the merged planning_context reconstructed from the durable Q&A already persisted (`_persist_qa`, clarify_engine.py:290), letting it resume its loop — but that risks an LLM re-gen for the NEXT round. **Recommendation:** for R4 scope, replay the OPEN round's questions from the durable event and, on answers, feed them through the existing `_merge_answers`/proceed path; treat a fresh next-round generation as the same LLM call the live run would make (acceptable — it is not a re-run of an already-answered round). Confirm the exact re-entry seam at plan time (`clarify_engine.run` vs a thin replay wrapper).
- Status stays `waiting_for_user` throughout (KAN-88 assertion), transitioning on resolution exactly as a live run.

**Where the run proceeds after answers:** into `_execute_impl`'s Step 4 dispatch (engine.py:1891) as a normal run — the clarify re-arm driver must drive the FULL pipeline from planning onward (this is the "no step dispatch differs" note: unlike review re-entry, clarify is pre-dispatch, so after answers it is essentially a fresh drive with the answered context, NOT a `_resume_from=k` skip).

---

## Driver & Lifecycle

- **Reuse the 46-05 auto-resume infrastructure.** The re-arm driver (review AND clarify) is spawned like branch (b): register the live queue BEFORE any emit (engine.py:5032–5040), `create_task`, register the driver task (engine.py:5049–5058). Thread the SAME hooks main.py wires at :141–154: `_resume_register_queue`, `_resume_register_task`, `_resume_cleanup`, `_resume_live_ectx_register/_unregister`, `_resume_milestone_sink`. Workspace recovered via `_recover_workspace_id` (engine.py:6012, Pitfall 2); selections re-applied via `selections_json` (0023) through `_apply_selections`.
- **What differs from full resume:** for REVIEW re-entry, the driver enters `_execute_impl` with `_resume_from = k` (the gated step) — the dispatch loop skips i<k, re-enters `_run_agent` at k in gate mode, and **parks at the wait until the user resolves** (no downstream dispatch until approve). For CLARIFY, the driver drives from planning (offset 0) but in replay mode (no question re-gen). In both cases: **no step dispatches past the gate until the HITL resolution fires the event.**
- **asyncio lifecycle:** the parked coroutine `await event.wait()`s indefinitely — **this matches today's live gate behavior** (clarify_engine.py:277 / _run_review_gate:4869 both block indefinitely; "No automatic timeout — Human_Gate stays open indefinitely", clarify_engine.py:259–260). The driver task lives in `_PIPELINE_TASKS` via `_resume_register_task`; on resolution/completion the `finally` in `resume_run` (engine.py:6985–7013) fires `_fire_resume_cleanup` + live-ectx unregister — **the WR-01 leak precedent** (engine.py:6722–6743). The re-arm driver MUST replicate this finally (queue None sentinel → cleanup → live-ectx unregister) or a parked run leaks its registry entries.
- **cancel_event on the parked wait:** `resume_run` drives `_execute_impl` with `cancel_event=None` (engine.py:6916 has no cancel kwarg), so `_run_review_gate` takes the **plain `await event.wait()`** branch (engine.py:4866–4869) — no cancel racing. This matches the LOCKED deferral (the cancel-aware gate wait, P23 T8/F7, is out of scope) and "the parked-run Stop path is unchanged". **VERIFIED.**

---

## KAN-88 + Test-Contract Changes

**The anchor test (test_restart_resume.py:877–899), quoted behavior:**
- Seeds a `waiting_for_user` row via `_seed_workflow_run(session, run_id, owner="wf-user", status="waiting_for_user")` — **only the `workflow_runs` row, NO durable `run_events`/`artifact_refs`/`wave_runs`.**
- Spies `engine.resume_run` (`_spy_resume` increments a counter).
- Calls `await engine.restore_non_terminal_runs()`.
- **Asserts:** (1) `resume_called["n"] == 0` — "waiting_for_user must NOT be auto-resumed (branch a)"; (2) `row.status == "waiting_for_user"` — "status must be unchanged".

**Current failure (recorded):** `AssertionError: waiting_for_user status must be unchanged` — HEAD sets `failed`.

**Confirming the re-arm flips it green WITHOUT editing the test:**
- The re-arm driver must **not be `engine.resume_run`** (the spy would fire) — spawn a distinct coroutine (`_rearm_gate_run`). Assertion (1) holds.
- Status must stay `waiting_for_user`. Given the test seeds NO durable rows, `_is_resumable_in_flight` returns False (no events/tree/wave rows). **Therefore the branch-(a) logic must leave a compilable `waiting_for_user` row at `waiting_for_user`** even without durable step rows (arm the event / no-op), reserving `failed` for the uncompilable/legacy stateless case only. This is the reconciliation flagged in Branch-(a) Design above. Under that shape, assertion (2) holds and the test flips green with zero test edits. **CONFIRM this reading at plan time** — the test is the contract; if the LOCKED "re-arm only for durable" is read strictly, the test would need durable seeding, which the CONTEXT forbids (KAN-88 test flips WITHOUT edits). The consistent resolution: **`waiting_for_user` + compilable ⇒ leave armed (never fail); only stateless/uncompilable ⇒ fail.**

**Other restart tests — honest change list:**
- `test_stateless_run_keeps_wr05_failed_path` (test_restart_resume.py:908) — status `generating`, no durable rows → branch (c) WR-05 fail. **UNTOUCHED** (branch (a) change is scoped to `waiting_for_user`; this row is `generating`). Must stay green.
- `test_midwave_resume_does_not_reinvoke_completed_workers` (:393), `test_resumed_events_seq_continues_past_durable_tail` (:798), the CR-03/CR-04/WR-01 strategy tests (:544/:668/:754), the RESUME-05 completeness tests (:1051/:1081), RESUME-08 re-materialize (:1170) — all branch (b)/strategy/classifier tests, **UNTOUCHED** by the branch-(a) `waiting_for_user` change UNLESS the open-gate override in `_first_incomplete_step` perturbs them. **Risk:** the override calls `derive_open_gate` on the durable events; these tests seed `run_events` WITHOUT `review_gate_ready`, so `derive_open_gate` returns `(None, None)` → override is dormant → offset unchanged. **VERIFY** the override is a no-op when no gate is open (it is, by construction).
- **Legitimately-changing tests:** none should change assertions — the only behavior change is `waiting_for_user + compilable` no longer failing. If any existing test asserts a `waiting_for_user` compilable row goes `failed`, it changes (search found only the KAN-88 test asserting on `waiting_for_user`). **Honest update list = { KAN-88 anchor flips RED→GREEN }; untouched list = everything else in the file.**

---

## At-Risk Tests & Baseline (real output, offline, python3.11, `cd backend/`)

| Suite | Command | Baseline (HEAD) |
|-------|---------|-----------------|
| restart_resume | `pytest tests/agents/test_restart_resume.py` | **1 failed, 24 passed** — the 1 fail is the KAN-88 anchor `test_waiting_for_user_run_is_rearmed_not_driven` (must flip green) |
| redo_gate_safety | `pytest tests/agents/test_redo_gate_safety.py` | **3 failed, 4 passed** — pre-existing harness drift: `_fake_gate()` lacks the `update_specs_eligible` kwarg (KAN-101 signature). Held 4/3 by delta (CONTEXT LOCKED — do not fix) |
| declared_gate_streaming | `pytest tests/agents/test_declared_gate_streaming.py` | **3 failed** — `sqlite3.IntegrityError: FOREIGN KEY constraint failed` on `run_events` persist (workflow_runs FK unseeded); Postgres/real-DB-gated, environment-red, NOT phase-related. Record baseline = 3 red (env). Confirm unchanged post-phase |
| approve_review_ownership | `pytest tests/unit/test_approve_review_ownership.py` | **6 passed** (file is under `tests/unit/`, not `tests/agents/` — CONTEXT path was approximate) |
| sse_stream | `pytest tests/unit/test_sse_stream.py` | **17 passed** (incl. `TestGateRearm::test_paused_gate_reemits_review_gate_ready_on_attach`, `test_rearm_is_read_only`, `test_fresh_attach_does_not_double_emit_open_gate` — the D-14g adjacency) |
| mechanical_router | `pytest tests/unit/test_mechanical_router.py` | **28 passed** (`derive_open_gate` / `route_chat_turn`) |
| rest_answers_cancel | `pytest tests/unit/test_rest_answers_cancel.py` | **9 passed** (clarify answers seam) |
| concierge_escalation | `pytest tests/unit/test_concierge_escalation.py` | **13 passed** |
| clarify_json_parse | `pytest tests/unit/test_clarify_json_parse.py` | **11 passed** |
| goldens (5 characterization) | `pytest tests/agents/test_characterization_*.py` | **10 passed** (SNAPSHOT_UPDATE unset) |
| banned_patterns | `pytest tests/agents/test_banned_patterns.py` | **11 passed** (SC-001/INV-1 gate; enumerate-pin = 1 at engine.py:2162) |
| lint-imports | `lint-imports` | **4 kept, 0 broken** |

**Regression floor for the phase:** restart_resume → 25/0 (KAN-88 flips + no new red); redo_gate_safety held 4/3; declared_gate_streaming held at its env-baseline; goldens 10/10; banned_patterns 11/0; lint 4/0; sse_stream 17/0; mechanical_router 28/0. Run the KAN-88 twin (clarify) as a NEW test in 49-03.

---

## Pitfalls

### Pitfall 1: Double-emit vs D-14g (re-arm re-emit + SSE-attach re-emit)
The branch-(a) re-arm re-emits `review_gate_ready` (engine-counter seq, durable), AND D-14g re-emits it on SSE attach (run_stream.py:188–191, seq from the durable row). Both are the SAME existing type. **Confirm harmless:** the FE dedups by `event_id`; the SSE path re-emits the durable row's own `event_id`, and it re-emits ONLY when `dangling.seq <= after_seq` (run_stream.py:190 — the CR-01 double-emit guard already shipped and tested by `test_fresh_attach_does_not_double_emit_open_gate`). The re-arm's fresh emit gets a new seq/event_id but represents the same open gate — idempotent for the inline gate UI. **Warning sign:** two gate cards. Verify against the shipped SSE dedup test staying green.

### Pitfall 2: State-machine transition (must stay `waiting_for_user`, no spurious `run_resuming`)
Branch (a) must NOT `_stamp_resume_marker` in a way that flips status (the marker is an additive EVENT, not a status change — engine.py:5122). `_run_review_gate` transitions to `waiting_for_user` on re-emit (engine.py:4819) — correct. Do NOT emit `pipeline_start`/`run_resuming` for a gate re-arm (a `pipeline_start` is in `_QUESTIONNAIRE_RESOLUTIONS` — chat_router.py:75 — and would CLOSE a clarify gate in `derive_open_gate`). **Warning sign:** the re-armed clarify gate immediately derives as resolved.

### Pitfall 3: Goldens dormancy
All new machinery must be dormant on scripted runs. The 5 characterization runs never park at a gate (SNAPSHOT_UPDATE unset), branch (a) never fires (they complete), the open-gate override returns `(None,None)`, and the resume sentinel is unset → byte/event-identical. The re-emitted `review_gate_ready`/`questionnaire_ready` are EXISTING types through the existing emit boundary with engine-counter seq (0024/DEF-43-03-1). **Proof:** goldens 10/10 must stay green; `redoable`/`update_specs_eligible`/`artifact_kind` are already in `_VOLATILE_STRIP_KEYS` (engine.py:4790/4800).

### Pitfall 4: P23 checkpointer-replay class (redo numbering)
If `redo_attempt` is not seeded from durable evidence, a post-restart `:redo1` reuses a pre-restart thread → the model replays its rejected output (engine.py:3190–3198). **Avoid:** seed `redo_attempt = max(gate_events_redo_count, artifact_version_count−1)` (fail-safe HIGH). Same class for `spec_revision_attempt`.

### Pitfall 5: INV-12 single-wait (no second HITL)
Do NOT build a parallel gate/wait. Reuse `_run_review_gate` / the store `get_review_event`+`set_review_response` half / the `_run_agent` loop. The re-entry is a NEW resume sentinel + the open-gate offset override — everything downstream is the SHIPPED consumer. Banned-pattern gate stays green (zero `pipeline_type ==` in `agents/execution_engine/`).

### Pitfall 6: Cancel-during-parked (unchanged)
The parked wait uses plain `await event.wait()` (cancel_event None on resume, engine.py:4866–4869). The Stop path for a parked run is unchanged (deferred cancel-aware wait, P23 T8/F7). Do not add a cancel race here — it widens scope past R4.

### Pitfall 7: Import-linter direction (shared home)
The kernel must NOT import `app.*` (main.py:138). Put the shared `derive_open_gate` in a kernel-importable pure module; have `chat_router`/`run_stream` import IT (app→kernel is allowed). `lint-imports` must stay 4/0.

### Pitfall 8: `_is_resumable_in_flight` vs the KAN-88 test's no-durable-rows row
See Branch-(a) + KAN-88 sections — the branch-(a) status decision for `waiting_for_user` must not hinge on durable-row presence in a way that fails the KAN-88 test (which seeds no durable rows). Resolve to "compilable ⇒ leave `waiting_for_user`".

---

## Validation Architecture

**Framework:** pytest (+ pytest-asyncio); python3.11, no venv; ABSOLUTE `cd backend/`. Config: `backend/pytest.ini`/`pyproject`. Quick run: the targeted files below (~50s total). Full offline suite HANGS (Chromium/Bedrock/Postgres-gated — memory note) — use the targeted floor.

**Phase requirements → test map:**
| Req | Behavior | Test | Command | Exists? |
|-----|----------|------|---------|---------|
| RESUME-17 (review) | branch (a) re-arms review gate; status stays `waiting_for_user`; resume_run not called | `test_waiting_for_user_run_is_rearmed_not_driven` | `pytest tests/agents/test_restart_resume.py -k rearmed` | ✅ (RED→GREEN anchor) |
| RESUME-17 (five actions) | approve proceeds; reject/edit/redo/update_specs work post-restart | NEW in 49-02 | seed durable `review_gate_ready`+ref, invoke re-entry, assert gate re-opens + each action | ❌ Wave 0 |
| RESUME-17 (redo numbering) | post-restart redo uses `:redo{N}` past pre-restart N | NEW in 49-02 | seed 2 redo `gate_events` rows, assert next thread == `:redo3` | ❌ Wave 0 |
| RESUME-17 (clarify twin) | branch (a) re-arms clarify; questions replayed; answers proceed | NEW in 49-03 (KAN-88 twin) | seed `questionnaire_ready`, assert re-emit + `waiting_for_user` + POST /answers proceeds | ❌ Wave 0 |
| RESUME-17 (dormancy) | goldens byte/event-identical | existing characterization | `pytest tests/agents/test_characterization_*.py` | ✅ |
| RESUME-17 (SC-001) | no name literals | existing banned_patterns | `pytest tests/agents/test_banned_patterns.py` | ✅ |

**Sampling:** per task commit → the touched targeted file; per wave merge → the full at-risk table; phase gate → restart_resume 25/0 + redo_gate_safety 4/3 + goldens 10/10 + banned_patterns 11/0 + lint 4/0 + sse_stream 17/0 + the new review/clarify twins green.

**Wave 0 gaps:**
- [ ] `tests/agents/test_restart_resume.py` — new review re-entry + five-actions + redo-numbering cases (extend the file; reuse `_ResumeHarness` + `_seed_workflow_run` + the `ScopedStore`/`write_ref` seed helpers at :952/:1146).
- [ ] `tests/agents/test_restart_resume.py` — new clarify-twin case (seed `questionnaire_ready` via `pre_store.append_event`, assert re-arm).
- [ ] No framework install needed (pytest-asyncio present; harness patterns exist).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The KAN-88 test flips green by leaving a compilable `waiting_for_user` row untouched (not gating the status decision on durable-row presence, since the test seeds none). | Branch-(a) / KAN-88 | If the LOCKED "re-arm only for durable" is read strictly, the test can't pass without edits (CONTEXT forbids edits) — must reconcile at plan time. HIGH — this is the anchor. |
| A2 | `spec_revision_attempt` has no durable audit row today; deriving it needs an added best-effort `record_gate_event(...,"update_specs",...)` or an artifact-version count. | Redo/Update-Specs | Under-seeding risks a spec-revision sub-pipeline thread collision post-restart (rarer than redo). MEDIUM. |
| A3 | The shared open-gate module can live kernel-side and be imported by app (`chat_router`/`run_stream`) without breaking import-linter. | Pendency Derivation | If a hidden app dep exists in the lifted code, need option-2 (injected callable). LOW — the derivation is pure over event dicts. |
| A4 | `declared_gate_streaming`'s 3 reds are environment (Postgres FK), not a phase concern; they stay red at baseline offline. | At-Risk Tests | If they were meant green, a real regression could hide. LOW-MEDIUM — verify in a DB-backed env at milestone-end. |
| A5 | Clarify multi-round replay of the OPEN round (then normal proceed) is faithful without re-generating the answered round via LLM. | Clarify Twin | A wrong re-entry seam could re-ask an answered round or re-gen questions. MEDIUM — confirm the `ClarifyEngine.run` re-entry seam at plan time. |

---

## Open Questions

1. **Exact branch-(a) status rule for a compilable-but-no-durable-rows `waiting_for_user` row.** Recommendation: leave `waiting_for_user` (arm event, no fail); fail only stateless/uncompilable. Resolve against the KAN-88 test contract in 49-01.
2. **`spec_revision_attempt` durable derivation** — add a symmetric audit row (recommended, 1-line additive, golden-dormant) or count spec-kind versions. Decide in 49-02.
3. **Clarify re-entry seam** — thin replay wrapper vs re-entering `ClarifyEngine.run` with reconstructed merged context. Decide in 49-03 (bias to reuse `ClarifyEngine.run`, INV-12).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3.11 | test/run | ✓ | 3.11 (no venv) | — |
| pytest + pytest-asyncio | validation | ✓ | (suite runs) | — |
| lint-imports | import-linter gate | ✓ | 4 contracts kept | — |
| Postgres | declared_gate_streaming (real-DB tests) | ✗ (offline) | — | Targeted offline floor; defer DB-gated suite to milestone-end |
| Bedrock/Chromium | live/render tests | ✗ | — | Offline scripted-model harness (per memory notes) |

---

## Sources

### Primary (HIGH — read at file:line, HEAD `feat/ui-2`)
- `backend/agents/execution_engine/engine.py` — restore/classify :4937–5120; `_run_agent` loop + gate consumers :2925–4001; `_run_review_gate` :4764–4931; `resume_run` :6744–7013; `_first_incomplete_step` :6400–6555; `_compute_resume_offset` :7015; `_latest_typed_content` :5631; redo thread-id :3185–3198; resume live-block :2084–2149; planner/clarify skip :1691–1708; dispatch loop :2162–2172.
- `backend/agents/artifact_store/store.py` — HITL events :40–172.
- `backend/app/api/chat_router.py` — `derive_open_gate` :192; resolution vocabularies :72/:84.
- `backend/app/api/run_stream.py` — `_dangling_review_gate` :119; `_GATE_RESOLUTION_TYPES` :68; D-14g re-emit :188–191.
- `backend/app/api/run_commands.py` — `_gate_is_pending` :134; gate/answers endpoints :162–239.
- `backend/agents/execution_engine/clarify_engine.py` — wait/emit :244–331.
- `backend/app/models/gate_events.py`; `backend/agents/execution_engine/kernel_services.py:279/1118/1230`; `backend/agents/authz.py:869/904`; `backend/app/main.py:141–155`; `backend/agents/capabilities/strategies/single_shot.py:60`.
- `backend/tests/agents/test_restart_resume.py` — KAN-88 anchor :877–899; harness :188–360.
- Baseline test runs (this session, recorded in the At-Risk table).

### Secondary (design context)
- `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` §5.5/§6-R4/§7/§8; `.planning/phases/49-.../49-CONTEXT.md`.

## Metadata
- Standard stack / mechanics: HIGH — every anchor read at HEAD; baseline suite executed offline.
- Architecture (re-entry via existing loop): HIGH — the `pending_revision_output` precedent is the exact template.
- KAN-88 flip mechanics: MEDIUM-HIGH — one reconciliation (A1) must be confirmed against the test at plan time.
- Research date: 2026-07-19 · Valid until: ~2026-08-02 (fast-moving; Phases 45–48 just reshaped this tier).

---

## RESEARCH COMPLETE

**Phase:** 49 — Gate Resume Across Restart [R4]
**Confidence:** HIGH

1. **Branch (a) today FAILS** every `waiting_for_user` run (engine.py:4990–5008); flip fail→re-arm gated on `_is_resumable_in_flight`, arm-then-classify, fail-safe to the current fail — status stays `waiting_for_user`.
2. **The crux is the classifier, not the wait:** a produced-but-ungated step classifies complete at engine.py:6550 and gets skipped; add an open-gate override (via shared `derive_open_gate`) so `_first_incomplete_step` returns the gated step k.
3. **Re-enter with zero model call** by cloning the shipped `pending_revision_output` short-circuit (engine.py:2978–3042): re-seed `output`/`last_streamed` from the max-version ref, re-emit `review_gate_ready`, re-arm the store event, fall into the EXISTING five-action consumer.
4. **Redo numbering continuation:** seed `redo_attempt = max(gate_events redo-count, artifact-version−1)` (fail-safe HIGH) to avoid the P23 `:redo{N}` replay collision; update_specs count needs an added audit row (A2).
5. **Clarify twin is asymmetric:** resumed runs skip clarify (engine.py:1708) — needs a dedicated replay driver (questions from durable `questionnaire_ready`, answers via unchanged POST /answers, then normal dispatch).
6. **Driver reuses 46-05 hooks** (main.py:141–155); parks indefinitely on plain `await event.wait()` (cancel_event None on resume — matches today + the deferred T8/F7); WR-01 cleanup in `finally`.
7. **Baseline recorded:** restart_resume 1F/24P (KAN-88 anchor), redo_gate_safety 3F/4P (held), goldens 10/10, banned_patterns 11/0, lint 4/0, sse_stream 17/0, mechanical_router 28/0. KAN-88 flips green with NO test edits (A1 reconciliation required).
8. **Recommended 3-plan split:** pendency+re-arm skeleton (flips KAN-88) · review re-entry + five actions + redo continuation · clarify twin + hardening + regression floor. Output: `.planning/phases/49-gate-resume-across-restart-r4/49-RESEARCH.md`.
