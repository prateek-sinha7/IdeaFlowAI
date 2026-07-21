# Synthesized Contracts — Live-State Contract (D-12) & Coverage Cross-Check

> **Evidence doc — Milestone v2.0.** Synthesized 2026-07-07 from the run-UI teardown (`01`), the backend map (`03`), and the frontend anatomy (`04`), locked with the user. These are Phase 28 (A0) UI-SPEC inputs — the FE work in Phases 31–32 builds against these tables, not against ad-hoc mock interpretation.

## 1. Live-state contract (POR D-12, full table)

The mock's Clarify/Gate/Building segmented control is a **prototype demo device** (scrubs the mock between moments) — excluded from the product. The real run state drives everything. The transcript **accumulates** across states and revision runs (the mock swaps content per phase; the product must not).

| Real state (driving signal) | Chat lane renders | Composer mode | Steps behavior |
|---|---|---|---|
| Planner running (`planner_start`, pre-clarify) | narrator line + planner card | steering (queued) | planner row active (mock omits this state) |
| **Clarify waiting** (`questionnaire_ready`; run `waiting_for_user`) | "Paused — N questions for you" card + awaiting badge + quick-reply chips | **composer = answer channel** (mechanical router treats input as clarify answers); full option-picker in chat AND inline in Steps | clarify Q&A inline (option buttons + submit); collapses to settled "N clarifications answered" record on `questionnaire_complete` |
| **Gate paused** (`review_gate_ready`; run `waiting_for_user`) | clarifications done-line + "Paused — needs approval" card with Approve / Request changes / **Redo + instructions** | gate-action mode (free text = redo instructions) | inline gate strip on the trace row (plan preview + actions); pulsing review dot on the Steps tab; one `approve_review` message regardless of surface |
| **Building** (`agent_start`/`agent_chunk`/`agent_thinking`…) | live pipeline mini-card (per-agent dots: done ✓ / live / queued) refreshed from agent lifecycle events | **steering mode** — hint: "guidance applies at the next step" (honest: no mid-generation injection) | streaming trace: reasoning cursor (`agent_thinking`), construction waves (`task_progress` / `wave_*` / `subagent_*`), progress spine, indeterminate bars on Preview/Files until deliverable validates |
| Validation / fix-loop (validator events; mock omits) | narrator line ("validating — fix attempt N") | steering (queued) | validator rows + fix-loop attempts visible in agent detail |
| **Complete** (`pipeline_complete`) | deliverable card ("Delivered as vN — open in Preview →") + pipeline summary card | **revision mode** — free text becomes a revision turn (child run in family, D-02) | all rows done; gate strips show "approved"; L1 status line "Run complete · N/N agents · duration" |
| Degraded (`pipeline_complete` + `status:degraded`) | "completed with issues" card naming failed agents | revision mode | degraded affordances (P16); failed agents flagged in trace |
| **Failed** (`pipeline_failed`) | **"What went wrong" card** (from `agents_failed` + sanitized error) + resume options: "Edit brief & run again" (ships — relaunch) · "Reopen & fix from failed step" (ND-4, not v1) | revision/relaunch mode | failed/skipped badges per agent (P13/P16 data); Audit auto-expands the blocking record |
| Cancelled (`pipeline_cancelled`) | "Cancelled by you" line + "Run again" | relaunch mode | trace frozen at cancellation point |
| Revision running (child run active) | same transcript continues (family-stitched, D-02); "v2 building…" chip | steering mode | Steps shows the child run's trace; version timeline updates |

Reconnect/reopen: the lane rehydrates from `run_events` replay (`after_seq`) + REST `/events`; the family transcript stitches via `/family` (P25). Every figure shown (tokens, durations, cache %) must come from a pinned field — see Phase 28 SC-2 and the data contract in `01-run-ui-teardown.md` §7.

## 2. Coverage cross-check (target surface → data source → owning phase)

Register-corrected: items the shell teardown flagged "backend-needed" that **already exist** are marked ✓exists.

| Target surface (mock) | Data source | Phase | Status/notes |
|---|---|---|---|
| Chat column: bubbles, bot rows, composer, voice | dead in-repo kit + new `chat_message`/`chat_reply` events | 29+31 | kit has voice already |
| Chat result cards (clarify/pipeline/deliverable) deep-linking to tabs | narrator projections of existing events; nonce'd deep-link seam (borrow #6) | 29+31 | |
| Composer attachment chips (file/image/audio) | upload endpoint + `run_images` | 30+31 | audio = voice-transcribe only (kit), not audio-to-model |
| Run header: status pill, meta, version selector, Download | run state + `LiveVersionChip` (P25) + existing download | 32 | ✓exists |
| Preview: browser chrome + typed-renderer switch (Prototype/Stories/Deck/App-IDE/Doc) | existing `FIRST_PARTY_RENDERERS` + generic mimetype dispatch | 32 | switcher = manual override UI |
| Steps L1: status line, per-agent progress spine, trace rows | agent lifecycle events | 32 | |
| Steps L1: collapsible Clarifications block | `ClarificationsCard` + `kind="clarifications"` artifacts (P25) | 32 | ✓exists — relocated |
| Steps L1: gate strips (approved / awaiting inline) | `review_gate_*` events + `ReviewGatePanel` | 32 | **structural**: gate/clarify move from full-panel overlays to inline Steps cards |
| Steps L2: reasoning block (live cursor) | `agent_thinking` | 32 | |
| Steps L2: artifact blocks ×4 (pages/tasks/checks/construction) | route table (`route_table.py`) / `task_list` artifact / `validation_results` / wave+subagent+task events | 28+32 | per-kind derivation rules = Phase 28 contract |
| Steps L2: tool calls, full input prompt, output, summary | `tool_call`/`tool_result`, `agent_input`, `agent_chunk`, `summary` | 32 | ✓exists (persisted) |
| Steps L2: "Context received" rail (name+size+cache/−%) | `agent_input.context_sources` + P26 cache telemetry + compaction data | 28+32 | verify payload fields in Phase 28 |
| Steps L3: per-task drill-down | `task_progress` (task_loop) **AND** `subagent_*`/`wave_*` (fanout) | 32 | dual source — both feed L3 |
| Files: deliverable hero, agent outputs, run inputs | mimetype persistence (P22), FilesTab, prompt.md/clarifications.md (P25) | 32 | ✓exists |
| Audit: log entries, severity, categories, explainers | `hook_runs` endpoint ✓exists; **new**: `gate_events`/`validation_results`/`exec_runs` read endpoints | 32 | |
| Audit: stat counters, coverage chips, verdict, filters, blocked-only | derived client-side | 32 | |
| Audit: export CSV/JSON · compliance PDF | client-side generation · ND-6 | 32 · deferred | |
| Live affordances (pulse/spin/bar/cursor/live pills) | streaming events | 32 | phase scrubber excluded (demo device) |
| Failed: failed/skipped badges, degraded affordances | P13/P16 terminal events | 32 | ✓exists |
| Failed: "What went wrong" chat card | `pipeline_failed` + `agents_failed` + sanitized error | 31 | |
| Failed: "Reopen & fix from failed step" | — (crash-resume exists; user-triggered failed-run resume does not) | ND-4 | new backend scope; "Edit brief & run again" ships |
| Share button | mock-only | ND-5 deferred | |
| Planner overlay / "Suggested next steps" chips | `PlanningOverlay` → Steps row + chat narration; chain buttons → chat quick-chips | 31/32 | folded |
| Shell chrome (top bar, nav pill, profile menu, notifications) | AppHeader + NotificationPanel restyle; notifications feed = new | 35 (feed: 38) | |
| Home: prompt launcher + deliverable grid + recents | merge `input` + `home` views + recents from history | 36 | per-card time/agent estimates → 38 |
| History: grouping, token/duration sort, delete | `token_usage` (P26) ✓exists · `DELETE /api/runs/{id}` ✓exists | 36 | grouping/sort UI new |
| My Workflows (mock "Catalogue") | `SavedWorkflowsPage` + 0021 cols ✓exists | 36 | D-11 rename; kebab actions wire to existing CRUD |
| Run detail/reopen page | run-summary endpoint aggregating `run_events` + `/family` ✓ + `token_usage` ✓ + P13/P16 failure data ✓ | 36 | page = new-build; data mostly exists |
| Configure (generic per-run setup: templates/DS/gates/settings) | prototype wizard parts exist; generic promotion = new; draft-save = ND-1 | 37 | biggest shell restructure |
| Agent drawer (4-tab inspector) | AgentsPopup/AgentModelPicker/SkillManager parts; prompt-override = ND-7 | 37 | |
| Workflow dialog (capabilities/context/compaction) | `/api/capabilities` (P22) ✓exists; "Engineer-only" = `user_allowed` reflection | 37 | |
| Analytics (date-scoped, donut/bars, model table, spend) | new aggregation endpoints; P26 telemetry as source | 38 | mock filters are static — real recompute needed |
| DS picker "150 systems" | ~14 in mock | ND-8 | product decision |

## 3. Figure-to-field pinning (Phase 28 deliverable, seed list)

Every number the design shows must map to a producing field: per-agent duration/tokens → `agent_complete` payload; run totals + cache split → `pipeline_complete` totals / `workflow_runs.token_usage` (P26); est. cost → `estimated_cost_usd` (shared `estimate_cost_usd`, cache-discounted); context-source sizes → `agent_input.context_sources`; cache −% → cache telemetry + compaction ratios; version numbers → `/family` `revision_index` (1-based chronological, `created_at ASC, id ASC`). Phase 28 completes and pins this list with exact field names verified in code.

---

## CORRECTIONS (2026-07-07 post-merge verification)

1. **§1 Gate-paused row:** actions are now Approve / Reject (via a two-step confirmation dialog; confirmed reject navigates home + resets — KAN-95) / Redo+instructions / **Update the Specs** (analyze gates; KAN-101). On `pipeline_cancelled/failed` the gate card auto-dismisses and `approve_review` is fenced with `pipeline_not_running` (KAN-100) — gate actions are unavailable post-terminal.
2. **§1 add a loop-back state:** `update_specs` triggers an in-run specify→plan→analyze sub-pipeline (Building-like; driven by re-fired `agent_start` on already-done agents) that returns to the SAME gate — distinct from both "Building" and "Revision running (child run)". Narrator card: "Revising spec — cycle N". Terminology: **spec-revision loop** (intra-run) ≠ **revision run** (family child).
3. **§1 planner window:** between questionnaire-submit and `pipeline_start`, PlanningOverlay shows (questions cleared, run id set — KAN-97); name it in the clarify→building transition.
4. **§1 Building row / §2 Steps L3:** the final `task_progress` fires BEFORE the build agent's fix-loop — checklist caps at N-1 until truly done (KAN-99).
5. **§2 row "Steps L2 output ✓exists (persisted)":** nuance — a human gate-edit persists to the artifact graph but is NOT re-emitted over WS; the FE retains it client-side (`retainAgentEdit`, KAN-98).
6. **§2 coverage:** the "image upload" rows should read the image spine as LANDED (run-entry, payload-transient — ND-10 for persistence); remaining = files endpoint, uploaded_files provider, per-turn carrier, resize.
7. **§1 gate row driving signal:** gates are event-driven — declared gates may not fire when `gate_agent_ids` excludes the agent (KAN-94).
