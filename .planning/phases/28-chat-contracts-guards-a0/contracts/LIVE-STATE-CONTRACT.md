# Live-State Contract (POR D-12)

**Phase 28 (A0) UI-SPEC input for phases 31 (chat lane) + 32 (run redesign).**
**Authority:** POR D-12 + evidence `07-synthesized-contracts.md` §1 (full table) INCLUDING the CORRECTIONS / post-merge deltas + evidence `01-run-ui-teardown.md` §2B/§5/§7. Per POR D-15 rule iii, **product behavior is truth** — the mock is a visual reference only.

> Transcribed verbatim from the locked POR + evidence pack; no decision re-derived or re-opened (mode: yolo / skip_discuss, AUTONOMOUS-RUN DECISION LOCK, `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §3).

---

## 0. Framing rules (excluded mock devices + accumulation)

- **The Clarify / Gate / Building segmented scrubber is a MOCK DEMO DEVICE** (`Live:76–80`, "Prototype control — scrub the run to a moment"). It lets a reviewer jump the mock between moments and is **excluded from the product** — replaced by a real phase indicator driven by the live run state. Never build the scrubber.
- **The transcript ACCUMULATES** across states and revision runs. The mock swaps its chat content per phase (`CHAT`/`PHINFO` lookups); the **product must NOT** — the chat lane is an append-only transcript, family-stitched across revision runs (D-02), rehydrated from `run_events` replay (`after_seq`) + REST `/events`, family-joined via `/family` (P25).
- Every figure the lane shows (tokens, durations, cache %) must come from a pinned field — see `FIGURE-TO-FIELD-PINNING.md`.

---

## 1. Live-state contract table

Columns: **Real state (driving event/signal)** | **Chat lane renders** | **Composer mode** | **Steps behavior**.

| Real state (driving signal) | Chat lane renders | Composer mode | Steps behavior |
|---|---|---|---|
| **Planner running** (`planner_start`, pre-clarify) | narrator line + planner card | steering (queued) | planner row active (the mock omits this state) |
| **Clarify waiting** (`questionnaire_ready`; run `waiting_for_user`) | "Paused — N questions for you" card + awaiting badge + quick-reply chips | **composer = answer channel** (mechanical router treats input as clarify answers); full option-picker in chat AND inline in Steps | clarify Q&A inline (option buttons + submit); collapses to a settled "N clarifications answered" record on `questionnaire_complete` |
| **Gate paused** (`review_gate_ready`; run `waiting_for_user`) | clarifications done-line + "Paused — needs approval" card. Actions: **Approve / Reject / Redo + instructions / Update the Specs** (see §2a) | gate-action mode (free text = redo instructions) | inline gate strip on the trace row (plan preview + actions); pulsing review dot on the Steps tab; one `approve_review` message regardless of surface |
| **Building** (`agent_start` / `agent_chunk` / `agent_thinking`…) | live pipeline mini-card (per-agent dots: done ✓ / live / queued) refreshed from agent lifecycle events | **steering mode** — hint "guidance applies at the next step" (honest: no mid-generation injection) | streaming trace: reasoning cursor (`agent_thinking`), construction waves (`task_progress` / `wave_*` / `subagent_*`), progress spine, indeterminate bars on Preview/Files until the deliverable validates. **KAN-99 N-1 cap:** the checklist caps at N-1 until the build agent's fix-loop finishes (see §2d) |
| **Validation / fix-loop** (validator events; mock omits) | narrator line ("validating — fix attempt N") | steering (queued) | validator rows + fix-loop attempts visible in agent detail |
| **Complete** (`pipeline_complete`) | deliverable card ("Delivered as vN — open in Preview →") + pipeline summary card | **revision mode** — free text becomes a revision turn (child run in family, D-02) | all rows done; gate strips show "approved"; L1 status line "Run complete · N/N agents · duration" |
| **Degraded** (`pipeline_complete` + `status:degraded`) | "completed with issues" card naming failed agents (`agents_failed[]`) | revision mode | degraded affordances (P16); failed agents flagged in trace |
| **Failed** (`pipeline_failed`) | **"What went wrong" card** (from `agents_failed` + sanitized error) + resume options: "Edit brief & run again" (ships — relaunch) · "Reopen & fix from failed step" (ND-4, not v1) | revision / relaunch mode | failed/skipped badges per agent (P13/P16 data); Audit auto-expands the blocking record |
| **Cancelled** (`pipeline_cancelled`) | "Cancelled by you" line + "Run again" | relaunch mode | trace frozen at the cancellation point |
| **Revision running** (child run active) | same transcript continues (family-stitched, D-02); "v2 building…" chip | steering mode | Steps shows the child run's trace; version timeline updates |

**Reconnect / reopen:** the lane rehydrates from `run_events` replay (`after_seq`) + REST `/events`; the family transcript stitches via `/family` (P25).

---

## 2. Post-merge deltas (CORRECTIONS — do not summarize away)

These are the merged KAN-92..101 facts folded onto §1. Each is a first-class contract row/note.

### (a) Gate-paused gains the FOURTH action **Update the Specs** (+ reject-confirm + terminal fence)

The gate-paused row's actions are now FOUR (evidence 07 §1 CORRECTIONS #1, KAN-101):
- **Approve** → `review_gate_approved`; optional `_gate_edited` (internal).
- **Reject** → via a **two-step confirmation dialog**; a confirmed reject **navigates home + resets** (KAN-95); internally `_gate_rejected` → pipeline cancelled.
- **Redo + instructions** → `_gate_redo {instructions}`; re-runs the SAME agent with the instruction appended as an `ADDITIONAL INSTRUCTIONS (REVISE)` block.
- **Update the Specs** → the analyze-gate action (KAN-101); carries `analysis_report` in the `instructions` field; triggers the spec-revision loop (§2b).

**Terminal fence (KAN-100):** on `pipeline_cancelled` / `pipeline_failed` the gate card **auto-dismisses** and `approve_review` is fenced — a post-terminal gate action returns the WS error `pipeline_not_running` (recoverable:false). Gate actions are unavailable post-terminal. (`_run_review_gate` also races `cancel_event`, so Stop dismisses a paused gate.)

### (b) The spec-revision loop-back state (`update_specs`)

**A NEW state, distinct from both "Building" and "Revision running (child run)"** (evidence 07 §1 CORRECTIONS #2, KAN-101):
- `update_specs` triggers an **in-run** specify→plan→analyze sub-pipeline (`_run_spec_revision_sub_pipeline`) that returns to the **SAME gate**.
- It is **Building-like**: driven by **re-fired `agent_start` on already-done agents** (the specify/plan/analyze agents re-run on their BASE thread_ids, accumulating dialogue — ND-11).
- Narrator card: **"Revising spec — cycle N"** (`revision_index` = `spec_revision_attempt`).

**TERMINOLOGY RULE (mandatory — never conflate):**
- **spec-revision loop** = the INTRA-RUN `update_specs` sub-pipeline (KAN-101); same run, re-opens the same gate.
- **revision run** = a FAMILY CHILD run (D-02); a new `WorkflowRun` with `parent_run_id`, dispatched as the `<base>_revision` pipeline.

These are different mechanisms with different lifecycles. Phase 31/32 must render and label them distinctly.

### (c) The planner window (named transient)

Between **questionnaire-submit** and `pipeline_start`, the PlanningOverlay shows (questions cleared, run id set) — evidence 07 §1 CORRECTIONS #3, **KAN-97**. Name this the **planner window** in the clarify→building transition; it is a distinct transient, not part of clarify-waiting and not yet Building.

### (d) The KAN-99 N-1 checklist cap on the Building row

The final `task_progress` fires BEFORE the build agent's fix-loop — the construction checklist **caps at N-1** until the agent truly finishes (evidence 07 §1 CORRECTIONS #4, **KAN-99**). See `STEPS-ARTIFACT-DERIVATION-CONTRACT.md` §3. Do not treat `completed_count == total − 1` as a stall.

### (e) Gates are event-driven (KAN-94)

Gates are **event-driven, not manifest-driven**: a declared human gate may NOT fire when `gate_agent_ids` excludes the agent (`_evaluate_gates` skips it) — evidence 07 §1 CORRECTIONS #7, **KAN-94**. The gate-paused row is entered only when a gate actually fires for the current agent; the chat lane must not assume a declared gate will pause.

---

## 3. Additional merged notes

- **Gate edit not echoed (KAN-98):** a human gate-edit persists to the artifact graph but is NOT re-emitted over WS — the FE retains it client-side (`retainAgentEdit`).
- **Image spine LANDED (payload-transient):** image input is live end-to-end for `prototype` (run-entry, payload-transient — never sandbox/DB/run_events → does not survive reopen/replay; ND-10). Composer attachment chips (file/image/audio) are backed by `run_images` for images; audio = voice-transcribe only.

---

## 4. Coverage self-check (all D-12 states + five deltas present)

States covered: planner-running, clarify-waiting (`questionnaire_ready`), gate-paused (`review_gate_ready`), building, validation/fix-loop, complete (`pipeline_complete`), degraded, failed (`pipeline_failed`), cancelled (`pipeline_cancelled`), revision-running. Post-merge deltas covered: (a) `update_specs` gate action + reject-confirm + terminal fence (`pipeline_not_running`, KAN-100), (b) spec-revision loop-back state + terminology rule, (c) planner window (KAN-97), (d) KAN-99 N-1 cap, (e) event-driven gates (KAN-94).
