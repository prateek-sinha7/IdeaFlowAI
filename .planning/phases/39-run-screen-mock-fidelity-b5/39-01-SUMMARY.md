---
phase: 39-run-screen-mock-fidelity-b5
plan: 01
subsystem: ui
tags: [react, run-screen, chat-lane, mock-fidelity, tailwind, tokens, playwright, screenshot-gallery]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4
    provides: the redesigned run screen (RunChatLane / ChatPanel / MessageBubble, Phase-32 design tokens) this re-aligns to the mock
  - phase: 39-run-screen-mock-fidelity-b5 (plan 07)
    provides: the two-sided fidelity oracle (serve/capture-mocks + assemble-gallery + the FIDELITY_CAPTURE zzz-baseline spec) this plan regenerates + reviews
provides:
  - The LEFT conversation lane brought pixel-as-is to the three mocks across all five states (settled · clarify · gate · building · failed) — structured transcript, lane run header, inline cards, attachment chips, per-state composer
  - LaneRunHeader (NEW) — back link · type eyebrow · status token · title · per-state meta row (settled = relative-age·duration·tokens; live/terminal = duration·N/M agents·tokens)
  - The failed lane composition (What-went-wrong + Resume options + red header + reopen composer) and the live status cards (Awaiting-you clarify/gate, building pipeline mini)
  - The INTENDED-DIVERGENCE REGISTER ND-A..ND-J (ND-I/ND-J added here) surfaced in the fidelity gallery
  - Additive PipelineRunState fields (createdAt / deliverableFilename / deliverableVersion) + agent_complete honoring an explicit duration — data already on the wire, now surfaced for the lane
affects: [39-05, 39-02, 39-03, 39-04, 39-06]

# Tech tracking
tech-stack:
  added: []  # no new dependency — existing lucide-react + Phase-32 CSS tokens
  patterns:
    - "Lane composition driven by the GENERIC runState + live pipelineState (SC-001) — never a workflow name; every count/label/duration/age is live data (ND-D)"
    - "Structured-transcript adornments passed to ChatPanel via a transcriptFooter slot; greeting suppressed in run context (hideComposer)"
    - "Intended-divergence register as the fidelity oracle's caption; human review of a 5-state side-by-side gallery (no pixel-diff, ND-D)"

key-files:
  created:
    - frontend/src/components/chat/LaneRunHeader.tsx
    - frontend/src/components/chat/LaneRunHeader.test.tsx
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/chat/ChatPanel.tsx
    - frontend/src/components/chat/MessageBubble.tsx
    - frontend/src/components/chat/ChatAttachments.tsx
    - frontend/src/components/chat/RunChatLane.test.tsx
    - frontend/src/components/chat/__tests__/RunChatLane.terminal.test.tsx
    - frontend/src/styles/globals.css
    - frontend/src/types/index.ts
    - frontend/src/hooks/useWorkflow.ts
    - frontend/e2e/tests/zzz-baseline.spec.ts
    - frontend/e2e/tests/ts-chat-cards.spec.ts
    - frontend/e2e/fixtures/mockWs.ts
    - frontend/e2e/fidelity/capture-mocks.mjs
    - frontend/e2e/fidelity/assemble-gallery.mjs

key-decisions:
  - "Cloned the mock's INTERNAL composition (D39-1) via Phase-32 tokens; kept our responsive lane width (ND-E) and the register divergences (ND-A..ND-J)"
  - "Single deliverable card (INV-12): the mock-styled filename-bearing DeliverableCard from live pipelineState; retired the interim narrator ResultCard stand-in in the run lane"
  - "Additive-only surfacing of data already on the wire (D39-4): createdAt/deliverableFilename/deliverableVersion on PipelineRunState + agent_complete honoring an explicit duration — no contract/handler change"
  - "Registered two live-data extras vs the mock as intended divergences: ND-I (header Stop while live) + ND-J (attachment chips on a real failed run)"

patterns-established:
  - "LaneRunHeader owns the per-state meta composition; reuses runStats (formatDuration/formatTokenCount) as the single formatter source (INV-12)"
  - "Failed lane restyled IN PLACE (single terminal renderer, INV-12) — no parallel path; reuses parseFailedAgents (resolveAgentNames/buildAgentNameById) + sanitizeError"

requirements-completed: [RUNUI-06, RUNUI-08]

# Metrics
duration: ~5h (multi-round, three human-verify checkpoints)
completed: 2026-07-11
---

# Phase 39 Plan 01: Left Conversation Lane — Mock Fidelity Summary

**The run screen's LEFT lane is now pixel-as-is to the three mocks across all five states — a structured transcript with a new LaneRunHeader, mock bubbles/inline cards/attachment chips, live/clarify/gate/failed compositions, and a single filename-bearing deliverable card — all on live data, closed to the intended-divergence register ND-A..ND-J.**

## Performance

- **Duration:** ~5h across three human-verify checkpoint rounds (initial build → gap fixes → pixel close-out)
- **Completed:** 2026-07-11
- **Tasks:** 3 autonomous + 1 checkpoint (Task 4), plus two coordinator-directed fix rounds
- **Files modified:** 2 created · 14 modified

## Accomplishments

- **Settled lane** — replaced the "What can I help you with?" greeting with the mock's structured transcript: LaneRunHeader (Back · type · Done · title · `relative-age · duration · tokens`), user brief bubble (#ECEAFC 14/14/4/14) + 22px near-black square avatar with the rotated brand diamond, inline "N clarifying questions" + "PIPELINE · N agents" (real per-agent durations) cards, the single deliverable card ("Delivered as v1 · <filename> · open in preview →"), the run's attachment chips (file/image/**audio→mic** icons, each with a functional "×"), and the "Ask for a change…" composer.
- **Live states** — a header phase pill (Running/Clarifying/Awaiting approval), Awaiting-you clarify/gate status cards deep-linking to Steps, and a building pipeline mini (live k/N + per-agent done/running/queued dots + "N clarifications answered · task plan approved"). The ND-F scrubber is intentionally not reproduced.
- **Failed lane** — restyled the single terminal-failed branch in place: red "Failed" header, red-tinted What-went-wrong card (live sanitized error + real failed-agent names), Resume options (red "Reopen & fix…" + "Edit brief & run again"), and the mock's "Tell the agents what to change, then reopen…" composer at the foot.
- **Fidelity oracle** — regenerated the two-sided gallery with 5 fully-paired `leftlane__{settled,clarify,gate,live,failed}` sections; a human signed off all five states pixel-as-is, closed to ND-A..ND-J.

## Task Commits

1. **Task 1 (TDD): LaneRunHeader + settled structured transcript** — `fb39c751` (test/RED) → `55629dd1` (feat/GREEN)
2. **Task 2: Live/streaming lane states** — `d2be924b` (feat)
3. **Task 3: Failed lane state** — `e914d01e` (feat)
4. **Task 4 (checkpoint) + e2e re-anchor** — `03e5198a` (test)

**Coordinator-directed fix rounds (post-checkpoint, approved as as-is-to-mock):**
- `5912b7ae` (fix) — run attachment chips, always-on back link, drop "Suggested next steps" block
- `e84f902d` (test) — seed representative lane conversations + capture clarify/gate sub-states
- `7e173a02` (fix) — single filename-bearing deliverable card from live data
- `f85fb9ad` (fix) — failed composer, chip remove/audio icon, per-state meta, copy fixes
- `31e4b5db` (test) — realistic capture seeding + register ND-I/ND-J
- `da529959` (test) — drive a clarify round in the live capture so the building answered-note renders

## Files Created/Modified

- `frontend/src/components/chat/LaneRunHeader.tsx` (NEW) — the left-lane run header; `humanizeRunType`, `deriveLaneMeta`, `formatRelativeAge`, per-state meta + status tokens.
- `frontend/src/components/chat/RunChatLane.tsx` — header mount; inline transcript adornments (clarify count · pipeline mini · deliverable · Awaiting-you cards); `RunAttachmentChips` (audio icon + "×" removal); mock composer bar; failed composer; new optional props.
- `frontend/src/components/chat/ChatPanel.tsx` — suppress greeting in run context; `transcriptFooter` slot.
- `frontend/src/components/chat/MessageBubble.tsx` — mock user bubble + assistant square avatar/diamond.
- `frontend/src/components/chat/ChatAttachments.tsx` — compact chips-only mode + external open trigger.
- `frontend/src/styles/globals.css` — `--status-failed-strong` token.
- `frontend/src/types/index.ts` — additive `PipelineRunState.createdAt / deliverableFilename / deliverableVersion`.
- `frontend/src/hooks/useWorkflow.ts` — surface those fields from `pipeline_start` / `pipeline_complete`; `agent_complete` honors an explicit `duration`.
- `frontend/e2e/` — enriched `zzz-baseline` capture seeding, `mockWs` (`created_at`/`duration`/`chatNarration`), `capture-mocks` failed+scrubber fix, `assemble-gallery` ND-I/ND-J, and the `ts-chat-cards` tab re-anchor.

## Decisions Made

- **Reuse-not-rebuild for formatters/agent-name resolution** — LaneRunHeader reuses `src/lib/runStats.ts` (`formatDuration`/`formatTokenCount`); the failed card reuses `src/lib/parseFailedAgents.ts` (`resolveAgentNames`/`buildAgentNameById`) + the existing `sanitizeError` (INV-12, T-39-01-01).
- **Single deliverable card (INV-12)** — the mock-styled `DeliverableCard` from live `pipelineState` is the one deliverable representation in the run lane; the interim narrator ResultCard stand-in was retired from the settled capture.
- **Additive-only wiring** — `createdAt`/`deliverableFilename`/`deliverableVersion` + honored `duration` surface data that already flows (D39-4); no contract, handler, or existing consumer changed.

## Deviations from Plan

### Auto-fixed / directed adjustments

**1. [Rule 3 - Blocking] Failed-mock target capture crashed on a missing Preview tab**
- **Found during:** Task 4 checkpoint automation (target gallery)
- **Issue:** `capture-mocks.mjs` gated hydration on a `^Preview$` tab the failed mock omits (and its tabs carry counts, e.g. "Steps 5") → 30s timeout, no `leftlane__failed` target shot.
- **Fix:** Relaxed the hydration gate to a contains-match of any tab word; later drove the Live mock's phase scrubber to also capture the target clarify/gate lanes.
- **Committed in:** `03e5198a`, `31e4b5db`

**2. [Directed - as-is-to-mock] Deliverable filename, per-state meta, failed composer, chip-× / audio, realistic seeding**
- **Found during:** post-checkpoint coordinator review (human chose full pixel-fidelity)
- **Issue:** interim gaps vs the mock (empty transcript, unregistered "Suggested next steps", filename-less deliverable, single meta shape, no failed composer, no chip-× / audio icon, "0s" durations).
- **Fix:** closed each within 39-01's files + the harness + minimal additive `useWorkflow` surfacing; registered two live-data extras as ND-I/ND-J.
- **Committed in:** `5912b7ae`, `e84f902d`, `7e173a02`, `f85fb9ad`, `31e4b5db`, `da529959`

---

**Total deviations:** 2 clusters (1 blocking harness fix, 1 directed pixel-fidelity close-out). **Impact:** all within 39-01's files + the fidelity harness + additive `useWorkflow` surfacing — no architecture change, no implementation-register divergence (coordinator-audited). SC-001/ND-D preserved (live data only).

## Issues Encountered

- **Live sub-state framing** — the tall clarify composer squeezed the transcript scroll region, hiding the Awaiting-you card; pinned the transcript to the bottom for the clarify capture so it stays in frame.
- **Assistant prose narration** — the chat driver only produces user turns (`chat_message`) or narrator cards (`chat_reply` with a cardKind); added a `chatNarration` helper (chat_reply with no `card_kind` → a prose assistant bubble) so the capture shows the mock's bot back-and-forth.

## Note for 39-05 (reuse, do NOT re-add)

`useWorkflow.ts` now surfaces three additive optional `PipelineRunState` fields — **`createdAt`** (from `pipeline_start`), **`deliverableFilename` / `deliverableVersion`** (from `pipeline_complete`) — and `agent_complete` honors an explicit **`duration`**. `RunChatLane` reads these live; its `onBackToHistory` / `runTitle` / `runType` / `deliverableFilename` props remain 39-05 overrides. **39-05 should wire the real back-target/title and reuse these fields, not duplicate them.**

## Threat Flags

None — no new network endpoint, auth path, or trust-boundary surface. T-39-01-01 (failed-card error) mitigated via `sanitizeError` (first line, capped, no stack frames); T-39-01-02 (XSS) — all lane text renders through React JSX escaping, no `dangerouslySetInnerHTML` in the new code.

## Known Stubs

- **Voice/transcribe button** in the composer is a visual-only affordance matching the mock (attach + send are fully wired); transcription is out of 39-01 scope.

## Next Phase Readiness

- The LEFT lane is done and human-approved across all five states; the fidelity oracle + 5-state gallery are ready for the remaining Phase-39 surface waves.
- **39-02 (Steps)** is next; the lane's inline clarify/pipeline/deliverable cards deep-link into Steps via `onRequestOpenTab("thinking"/"preview")`.
- **39-05** should reuse the additive `useWorkflow` fields above and thread the real back-to-history target + run title.

## Self-Check: PASSED

- `LaneRunHeader.tsx` + `LaneRunHeader.test.tsx` present; `RunChatLane.tsx` present.
- All task commits verified in git (`fb39c751`, `55629dd1`, `d2be924b`, `e914d01e`, `03e5198a`, `5912b7ae`, `e84f902d`, `7e173a02`, `f85fb9ad`, `31e4b5db`, `da529959`).
- Verification: `npx tsc --noEmit` clean; **148** component/hook tests pass (`src/components/chat` + `src/hooks/useWorkflow`); lane e2e **7 passed** (`ts-chat` + `ts-chat-cards`); fidelity gallery = 5 paired leftlane sections, human-approved.

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11*
