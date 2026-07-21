---
phase: 31-chat-lane-mvp-a3
verified: 2026-07-08T11:44:19Z
status: passed
score: 15/15 must-haves verified
overrides_applied: 0
---

# Phase 31: Chat Lane MVP [A3] Verification Report

**Phase Goal:** Revive the dead in-repo chat kit into the run screen, wired to Phase-29's flag-gated SSE/WS transport, in the CURRENT skin. Deliverables CHATUI-01 (revived chat lane), CHATUI-02 (in-lane gate/clarify quick-actions), CHATUI-03 (attachment UI + token widget). Open-design borrow-list 1–7 integrated WITH Apache-2.0 attribution.

**Verified:** 2026-07-08T11:44:19Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `RunChatLane` mounted in DashboardLayout's execution left column | ✓ VERIFIED | `grep RunChatLane src/components/layout/DashboardLayout.tsx` → imported + rendered inside `<div data-testid="execution-chat-lane">` (line 1590-1592), fed `messages`, `runState`, `sendMessage`, gate/clarify/revise/stop callbacks |
| 2 | Transcript region carries `role="log"` + `aria-live` (a11y invariant, open-design's documented failure not repeated) | ✓ VERIFIED | `ChatPanel.tsx` lines 206-209: `data-testid="chat-transcript"`, `role="log"`, `aria-live="polite"`, `aria-relevant="additions text"`; asserted live by `RunChatLane.test.tsx` and the new `ts-chat.spec.ts` TS-CHAT-02 (independently re-run, passed) |
| 3 | `ResultCard` renders the 5 generic card kinds and the "Deliverable" label (LOCK-F); SC-001 (no workflow-name dispatch) | ✓ VERIFIED | `ResultCard.tsx`: switch on generic `cardKind` (`clarify\|gate\|pipeline\|deliverable\|spec_revision`), `title: "Deliverable"` for the deliverable kind; `grep -rnE "\"prototype\"\|od_ppt\|app_builder\|user_stories" src/components/chat/ResultCard.tsx` → 0 hits |
| 4 | Streaming markdown + live cursor on the family-anchored transcript (D-02) | ✓ VERIFIED | `MessageBubble.tsx` keeps react-markdown/remark-gfm + streaming-cursor; `useRunChat.ts` accumulates append-only, `event_id`-deduped, `run_id`/`thread_id`-anchored messages (12 vitest cases green, independently re-run) |
| 5 | Inline gate quick-actions (4 actions incl. `update_specs`) mirror the Steps `approve_review` channel; terminal fence (KAN-100); retained edit (KAN-98) | ✓ VERIFIED | `InlineGateActions.tsx` renders Approve/Reject/Redo/Update-Specs via the same `onApprove/onReject/onRedo/onUpdateSpecs` callback shape as `ReviewGatePanel`; `!isPipelineRunning` renders nothing; mounted in `RunChatLane.tsx` and wired in `DashboardLayout.tsx` (`onApproveReview`, `onRedoReview`, `onUpdateSpecsReview`) |
| 6 | Inline clarify quick-actions mirror the Steps `submit_questionnaire` channel | ✓ VERIFIED | `InlineClarifyActions.tsx` emits canonical `[{question_id, answer}]`; mounted in `RunChatLane.tsx`, wired to `handleLaneSubmitAnswers`/`questionnaireQuestions` in `DashboardLayout.tsx` |
| 7 | Attachment intake: picker + paste + drag-drop, each routed through `resizeImage` (client resize) | ✓ VERIFIED | `useChatAttachments.ts`: `import { resizeImage } from "@/lib/resizeImage"`, called at line 137 for image files; `ChatAttachments.tsx` wires `onPaste`/`onDrop`/`onDragOver` + hidden file input, all funneling through `addFiles` |
| 8 | Token-usage widget surfaces P26 telemetry pinned fields | ✓ VERIFIED | `ChatTokenWidget.tsx` mounted in `RunChatLane.tsx` (line 329), fed `pipelineState` from `page.tsx`/`DashboardLayout.tsx` |
| 9 | Nonce'd deep-link seam: a result-card click switches the correct `PreviewPanel` tab | ✓ VERIFIED | `useTabDeepLink.ts` (fresh nonce/single-use consume, 4 vitest cases); `PreviewPanel.tsx` lines 299-430: effect keyed on `deepLinkTarget?.nonce` switches `activeTab` for ALL panel tabs (was preview/files-only before) |
| 10 | Open-design borrow-list 1-7 integrated WITH Apache-2.0 attribution | ✓ VERIFIED | `frontend/NOTICE` + `frontend/THIRD-PARTY-NOTICES.md` exist, name `nexu-io/open-design` + Apache-2.0; 10 source files carry the `Adapted from nexu-io/open-design (Apache-2.0)` header comment |
| 11 | The lane absorbs `AgentProgressPanel` controls (Stop, revise-as-chat, suggestions-as-chips) driven by D-12 composer-mode-per-state | ✓ VERIFIED | `RunChatLane.tsx` composer mode switches on generic `RunLaneState` (idle/building/clarify/gate/complete/terminal); `DashboardLayout.tsx` derives `runLaneState` from generic signals (`reviewGateData`/`questionnaireQuestions`/`pipelineState`) — no workflow-name branch (SC-001); `AgentProgressPanel` retained but its Stop/revise/suggestions responsibilities are commented as absorbed (line 1630) |
| 12 | INV-3: no backend file, no golden fixture, no `useWorkflow.ts`/`useWebSocket.ts` touched by the phase | ✓ VERIFIED | `git diff --name-only f9f759b1~1..217bf7df` → 41 files, all under `frontend/src/`, `frontend/e2e/`, `frontend/NOTICE`/`THIRD-PARTY-NOTICES.md`, and `.planning/`; zero backend files; `useWorkflow.ts`/`useWebSocket.ts` absent from the diff |
| 13 | tsc-identity held across the phase | ✓ VERIFIED | Independently re-ran `npx tsc --noEmit \| grep -v mockApi.ts \| grep -c "error TS"` → `0` |
| 14 | New chat e2e specs pass; no regression vs the pre-existing baseline (e2e-BASELINE caveat, verify BY DELTA) | ✓ VERIFIED | Independently re-ran `npx playwright test --project=mocked e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts` → **7 passed / 0 failed**. Spot-checked 2 of the 5 canonical baseline files (`ts-a.auth.spec.ts`, `ts-sse.spec.ts`): TS-A-05/06 failures confirmed pre-existing 🔴 in `.planning/TEST-REGISTER.md` (not introduced by this phase); TS-A-01/02 + both SSE specs green, matching the SUMMARY's claimed 12-baseline-green set |
| 15 | CHATUI-01/02/03 traceable in REQUIREMENTS.md | ✓ VERIFIED | `.planning/REQUIREMENTS.md` lines 222-226 + traceability table lines 458-460: all three marked `[x]` / "Complete", mapped to Phase 31 [A3]; also closes the UPLD-04 "remaining: client-side resize, paste/drag-drop (Phase 31 UI)" residue (line 220) |

**Score:** 15/15 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/components/chat/runtime/partial-json.ts` | repairJsonPrefix + parsePartialJson | ✓ VERIFIED | exists, exports present, 11 vitest cases (re-run: green) |
| `frontend/src/components/chat/runtime/streaming-json.ts` | extractStreamingJsonString | ✓ VERIFIED | exists, exports present |
| `frontend/src/components/chat/runtime/buildBlocks.ts` + `blocks.types.ts` | events→blocks reducer + ChatBlock contract | ✓ VERIFIED | exists, wired into MessageBubble.tsx agent-block strip |
| `frontend/src/components/chat/runtime/tool-renderers.tsx` | 3-tier dispatch | ✓ VERIFIED | exists, registry+fallback+try/catch isolation |
| `frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts` | measured virtualizer | ✓ VERIFIED | exists, wired into ChatPanel.tsx (>80 msgs) |
| `frontend/src/components/chat/blocks/{ThinkingBlock,TodoCard,FileOpsSummary}.tsx` | agent-block components | ✓ VERIFIED | exist, rendered via MessageBubble's block strip |
| `frontend/src/hooks/useRunChat.ts` | transcript hook | ✓ VERIFIED | exists, wired in page.tsx (transport-agnostic) |
| `frontend/src/hooks/useTabDeepLink.ts` | nonce'd seam | ✓ VERIFIED | exists, wired page.tsx → PreviewPanel.tsx |
| `frontend/src/components/chat/RunChatLane.tsx` | composition root | ✓ VERIFIED | exists (>80 lines), mounted DashboardLayout, wired to all gate/clarify/attachment/token sub-components |
| `frontend/src/components/chat/ResultCard.tsx` | narrator cards | ✓ VERIFIED | exists, 5-kind switch, LOCK-F "Deliverable" label |
| `frontend/src/components/chat/{InlineGateActions,InlineClarifyActions}.tsx` | in-lane quick-actions | ✓ VERIFIED | exist, mounted RunChatLane, wired real callbacks in DashboardLayout |
| `frontend/src/hooks/useChatAttachments.ts` + `ChatAttachments.tsx` + `ChatTokenWidget.tsx` | attachments + token widget | ✓ VERIFIED | exist, mounted RunChatLane, resizeImage/paste/drop confirmed wired |
| `frontend/e2e/tests/ts-chat.spec.ts` + `ts-chat-cards.spec.ts` | mocked e2e | ✓ VERIFIED | exist, independently re-run: 7/7 pass |
| `frontend/NOTICE` + `frontend/THIRD-PARTY-NOTICES.md` | Apache-2.0 attribution | ✓ VERIFIED | exist, name open-design + Apache-2.0 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `DashboardLayout.tsx` | `RunChatLane.tsx` | mount in execution left column | WIRED | `data-testid="execution-chat-lane"`, full prop wiring (messages/runState/gate/clarify/attachments/token) |
| `page.tsx` | `useRunChat` / legacy WS / `RunConnectionProvider` | transport-agnostic transcript feed | WIRED (dual-path) | SSE branch present but dormant (provider not mounted anywhere in the app — `enabled` defaults `false`); legacy WS branch is the ACTIVE path and is fully wired (`chatFrameListenersRef` fed by an additive branch in `handleWebSocketMessage` for `chat_message`/`chat_reply`/`stream_attached`) |
| `ResultCard.tsx` | `PreviewPanel.tsx` | nonce'd deep-link (`onRequestOpenTab` → `useTabDeepLink` → `deepLinkTarget.nonce` effect) | WIRED | confirmed end-to-end in `PreviewPanel.tsx` lines 299-430 and exercised live by `ts-chat-cards.spec.ts` TS-CHAT-CARDS-01 (re-run, passed) |
| `RunChatLane.tsx` | `buildBlocks` / `tool-renderers` / `ThinkingBlock` / `useMeasuredVirtualWindow` | ChatBlock union rendering | WIRED | via `MessageBubble.tsx`/`ChatPanel.tsx` (modified by plan 04) |
| `useChatAttachments.ts` | `resizeImage.ts` | client-side downscale before base64 | WIRED | `grep resizeImage` present + called |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `RunChatLane` transcript | `messages` | `useRunChat` fed by the ACTIVE legacy-WS chat-frame fan-out (`chatFrameListenersRef`) in `page.tsx`, dispatched from real WS `chat_message`/`chat_reply`/`stream_attached` frames | Yes (live WS frames when SSE flag OFF, which is the current app-wide default state) | ✓ FLOWING |
| `RunChatLane` gate/clarify surfaces | `laneGate` / `questionnaireQuestions` | `DashboardLayout.tsx` real `reviewGateData`/questionnaire state (same source Steps panels use) | Yes | ✓ FLOWING |
| `ChatTokenWidget` | `pipelineState` | live `pipelineState` from `page.tsx`/`DashboardLayout.tsx` (P26 telemetry fields) | Yes | ✓ FLOWING |
| SSE transport branch (`RunConnectionProvider.subscribe`) | n/a | `RunConnectionProvider` context, default `enabled:false` — provider never mounted at `app/layout.tsx` | Dormant by construction | LIVE-DEFERRED (see below — pre-existing Phase-29 deferral, not a Phase-31 gap) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| tsc identity | `npx tsc --noEmit \| grep -v mockApi.ts \| grep -c "error TS"` | `0` | ✓ PASS |
| Chat vitest suites (independently re-run) | `npx vitest run src/components/chat/ src/hooks/useRunChat.test.ts src/hooks/useTabDeepLink.test.ts src/hooks/useChatAttachments.test.ts` | 15 files / 114 tests passed | ✓ PASS |
| RunChatLane + ResultCard suites | `npx vitest run src/components/chat/RunChatLane.test.tsx src/components/chat/ResultCard.test.tsx` | 2 files / 22 tests passed | ✓ PASS |
| SC-001 grep (new phase-31 source files) | `grep -rnE "\"prototype\"\|od_ppt\|app_builder\|user_stories\|prototype-analyze\|prototype-specify"` across chat components/hooks | 0 hits in production files (2 hits are inside the tests' own grep-regex strings; `ArtifactCard.tsx`'s pre-existing `"prototype"` type-union member predates this phase and is untouched) | ✓ PASS |
| Mocked chat e2e (new specs) | `npx playwright test --project=mocked e2e/tests/ts-chat.spec.ts e2e/tests/ts-chat-cards.spec.ts` | 7 passed / 0 failed | ✓ PASS |
| Delta regression spot-check | `npx playwright test --project=mocked e2e/tests/ts-a.auth.spec.ts e2e/tests/ts-sse.spec.ts` | 4 passed / 2 failed (TS-A-05/06, confirmed pre-existing 🔴 in TEST-REGISTER.md, not a regression) | ✓ PASS (delta-consistent with SUMMARY's claimed 12-baseline-green set) |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` and none are referenced in the plans/summaries.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CHATUI-01 | 31-01, 31-02, 31-03, 31-04 | Revived chat kit: family transcript, streaming markdown, aria-live/role=log, borrow mechanisms + attribution | ✓ SATISFIED | Truths 1-4, 10 above |
| CHATUI-02 | 31-05, 31-07 | In-lane gate/clarify quick-actions mirroring Steps | ✓ SATISFIED | Truths 5-6 above |
| CHATUI-03 | 31-06, 31-07 | Attachment UI (picker/paste/drag-drop/resize) + token widget | ✓ SATISFIED | Truths 7-8 above |

No orphaned requirements found for Phase 31 in REQUIREMENTS.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/THIRD-PARTY-NOTICES.md` | 24, 26-28 | 4 of 7 "local reimplementation" table cells still read `_planned (31-02)_` / `_planned (31-04)_` even though tool-renderer registry, virtualizer, deep-link seam, and block components all shipped and carry their own per-file attribution headers | ℹ️ Info | Cosmetic doc-debt only — the substantive Apache-2.0 attribution requirement (NOTICE + per-file "Adapted from nexu-io/open-design" headers, 10 files) is fully satisfied; this is a stale bookkeeping cell in a tracking table, not a missing attribution. Each of plans 02/03 explicitly logged this as a deliberate, scoped deferral ("folded into plan 04"), and plan 04 did not close it out — a one-line polish item, not a phase-goal blocker. |

No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers found in any file touched by this phase (`git diff --name-only` file list scanned, zero hits).

### Human Verification Required

None required to close this phase. The following is a pre-existing, already-flagged Phase-29 deferral, not a new Phase-31 gap:

- **`RunConnectionProvider` app-level mount (SSE-transport activation).** The provider is built, tested, and imported by both `useWorkflow.ts` (Phase 29) and the new `useRunChat` wiring (Phase 31) — but it is not mounted anywhere in `frontend/src/app/layout.tsx`, so `NEXT_PUBLIC_SSE_TRANSPORT` is inert app-wide and the legacy WS path is the only ACTIVE transport today. This was already surfaced as a Phase-29 human_verification item (`29-VERIFICATION.md` line 57/91/111/152) and explicitly deferred to the milestone-end live pass. Phase 31's CONTEXT explicitly instructs "the flag-OFF path stays the legacy WS, unchanged" — which this phase correctly delivers (the legacy WS chat-frame routing is fully wired and independently confirmed working). Mounting the provider is out of this phase's stated 3-file scope (`31-07-PLAN.md` Task 1) and remains tracked for the milestone-end live pass (consistent with the "Defer live verification" project convention).

## Gaps Summary

No gaps found. All 15 derived must-have truths (roadmap goal + PLAN frontmatter must_haves across all 7 plans) are VERIFIED against the actual codebase — not merely claimed by SUMMARY.md. Independently re-ran (not just trusted): `tsc --noEmit` (0 new errors), 114+22 vitest cases across all chat runtime/component/hook suites, and both new mocked Playwright specs (7/7 pass) plus a spot-check of 2 baseline files confirming the claimed delta (no green→red regression; the 2 observed failures are independently confirmed pre-existing red in `TEST-REGISTER.md`). INV-3 held across the full phase commit range (`f9f759b1~1..217bf7df`): zero backend files, `useWorkflow.ts`, or `useWebSocket.ts` in the diff. SC-001 held: no new workflow-name literal in any phase-31 production file. The one cosmetic finding (stale THIRD-PARTY-NOTICES.md local-path cells) does not affect the substantive Apache-2.0 attribution requirement, which is independently satisfied by the NOTICE file + 10 per-file attribution headers.

---

_Verified: 2026-07-08T11:44:19Z_
_Verifier: Claude (gsd-verifier)_
