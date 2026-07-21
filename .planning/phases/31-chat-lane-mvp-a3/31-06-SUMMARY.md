---
phase: 31-chat-lane-mvp-a3
plan: 06
subsystem: ui
tags: [react, attachments, drag-drop, clipboard, resize, tokens, telemetry, vitest]

# Dependency graph
requires:
  - phase: 31-03
    provides: "ChatAttachment payload-transient type (retained:false default) + ChatMessage.attachments field"
  - phase: 30-04
    provides: "resizeImage.ts — client-side aspect-preserving downscale + degrade-not-block"
  - phase: 27 (P26 telemetry)
    provides: "PipelineRunState token fields (totalTokens/estimatedCostUsd/cacheReadTokens) + TokenUsageSummary skin"
provides:
  - "useChatAttachments hook — chat-lane attachment intake (picker/paste/drag-drop) routing images through resizeImage before base64, files passthrough, with a client allow-list + size cap"
  - "ChatAttachments component — drop zone (drag-active state) + paste handler + hidden multi-file picker + removable preview chips + ND-10 reopen placeholder"
  - "ChatTokenWidget component — compact lane token-usage widget mirroring TokenUsageSummary (P26), cached % only when cacheRead>0"
affects: [31-04 chat lane composition, 31-07 live integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PendingAttachment extends the pinned 31-03 ChatAttachment ref with live payload (id + base64 data) — the ref persists metadata, the data rides the outbound payload only (ND-10)"
    - "Attachment intake normalizes picker/paste/drop through ONE addFiles path (image → resizeImage, file → passthrough)"
    - "Structural event-shape params (ClipboardEventLike/DragEventLike) so handlers accept both React synthetic and native DOM events"

key-files:
  created:
    - frontend/src/hooks/useChatAttachments.ts
    - frontend/src/hooks/useChatAttachments.test.ts
    - frontend/src/components/chat/ChatAttachments.tsx
    - frontend/src/components/chat/ChatAttachments.test.tsx
    - frontend/src/components/chat/ChatTokenWidget.tsx
    - frontend/src/components/chat/ChatTokenWidget.test.tsx
  modified: []

key-decisions:
  - "Introduced PendingAttachment (extends ChatAttachment, adds id/data/width/height) rather than redefining the pinned 31-03 type — the ref stays canonical, the live payload is a superset carrying base64 for preview + send"
  - "Client cap = allow-list reject BEFORE base64 for disallowed types + ~3.75MB post-resize per-image / 10MB per-doc — UX defense-in-depth mirroring server _validate_images; server stays authoritative (T-31-06-D/T)"
  - "ChatAttachments has two modes: LIVE intake (owns the hook) and REOPENED (renders stored refs; retained:false → ND-10 placeholder, no <img>) — the placeholder IS the ND-10 disposition, not durable storage"
  - "ChatTokenWidget is a distinct compact widget (not a reuse of TokenUsageSummary) per plan 'sized for the lane'; local formatters mirror the P26 skin, every figure pinned to a live-state field (SC-001)"

patterns-established:
  - "First chat-lane data-testids on attachment/token surfaces: chat-attachments, chat-attach-chip, chat-attach-dropzone, chat-token-widget"
  - "resizeImage wiring point for lane attachments (UPLD-04): grep-provable in useChatAttachments.ts"

requirements-completed: [CHATUI-03]

# Metrics
duration: ~10min
completed: 2026-07-08
---

# Phase 31 Plan 06: Chat-Lane Attachments + Token Widget Summary

**Chat-lane attachment intake adding clipboard paste + drag-drop on top of the launch-composer picker, wiring Phase-30 resizeImage for client downscale (UPLD-04), with ND-10 payload-transient preview chips and a compact P26 token-usage widget (CHATUI-03).**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-08T10:58Z
- **Completed:** 2026-07-08T11:02Z
- **Tasks:** 2
- **Files modified:** 6 (all created)

## Accomplishments
- `useChatAttachments` hook: a single `addFiles` intake fed by picker, clipboard `onPaste`, and `onDrop`; images route THROUGH `resizeImage` before base64 (UPLD-04), non-image docs pass through untouched; a client allow-list + `~3.75MB` post-resize / `10MB` doc cap mirror the server caps; every record is `retained:false` (ND-10).
- `ChatAttachments` component: a drop zone with a visible drag-active state, a paste handler bound to the surface, a hidden multi-file picker, and removable preview chips (image thumbnail from the resized base64; file → name + size). A REOPENED mode renders the ND-10 "image not kept on reopen" placeholder for a non-retained ref with NO `<img>`.
- `ChatTokenWidget`: a compact lane widget mirroring `TokenUsageSummary` (P26) — pinned `totalTokens`/`estimatedCostUsd`/`cacheReadTokens` figures, cached-% segment only when `cacheRead > 0`, renders nothing before any token data.

## Task Commits

Each task was committed atomically:

1. **Task 1: useChatAttachments — picker + paste + drag-drop intake with client resize** - `98d5e7af` (feat)
2. **Task 2: ChatAttachments preview chips (+ND-10 placeholder) and ChatTokenWidget (P26)** - `a0ad74f8` (feat)

**Plan metadata:** _(final docs commit — this SUMMARY + STATE + ROADMAP)_

## Files Created/Modified
- `frontend/src/hooks/useChatAttachments.ts` - attachment intake hook (picker/paste/drag-drop → resize/passthrough + cap + PendingAttachment state)
- `frontend/src/hooks/useChatAttachments.test.ts` - 6 specs (resize-through / passthrough / paste / drop / cap reject / remove+clear)
- `frontend/src/components/chat/ChatAttachments.tsx` - composer sub-surface: drop zone + paste + picker + preview chips + ND-10 placeholder
- `frontend/src/components/chat/ChatAttachments.test.tsx` - 3 specs (chip render+remove / drag-active toggle / ND-10 placeholder no-<img>)
- `frontend/src/components/chat/ChatTokenWidget.tsx` - compact P26 token-usage widget
- `frontend/src/components/chat/ChatTokenWidget.test.tsx` - 3 specs (pinned totals / cached-% gate / empty)

## Decisions Made
- See key-decisions in frontmatter. Chief among them: `PendingAttachment extends ChatAttachment` (no redefinition of the pinned 31-03 type), and `ChatTokenWidget` as a distinct compact widget rather than a reuse of `TokenUsageSummary`.

## Deviations from Plan

None - plan executed exactly as written.

Note on TDD: Task 1 carried `tdd="true"`. Global `workflow.tdd_mode` is `false` and no MVP+TDD gate was passed by the orchestrator, so the task was committed as a single atomic `feat` commit (hook + test together) rather than split RED/GREEN commits. The behavior tests specified in `<behavior>` were authored and are all green.

## Issues Encountered
None.

## Verification Evidence (offline)
- `npx vitest run src/hooks/useChatAttachments.test.ts` → 6 passed.
- `npx vitest run src/components/chat/ChatAttachments.test.tsx src/components/chat/ChatTokenWidget.test.tsx` → 6 passed (2 files).
- `npx tsc --noEmit` (excluding the known `e2e/fixtures/mockApi.ts` baseline) → **0 new `error TS`** (tsc identity held).
- UPLD-04: `grep -q "resizeImage" src/hooks/useChatAttachments.ts` → present.
- SC-001: grep for `prototype|od_ppt|app_builder|prototype-analyze|prototype-specify` across all three source files → 0 hits (keyed on generic telemetry / event shapes only).
- INV-3 + FIX-039: `git status` shows only the 6 plan-scoped files; no backend, no golden fixture, no `frontend/e2e/**`, no `useWorkflow.ts` touched.

## Known Stubs
None. All three surfaces are wired to real inputs (resizeImage, live PipelineRunState telemetry, the pinned ChatAttachment type). The lane composition that threads the hook's `onChange` into `sendMessage` and mounts the widget is plan 04/07 scope (interface delivered here, consumed there) — this is the plan's declared boundary, not a stub.

## Next Phase Readiness
- The attachment intake + preview surface and the token widget are ready for plan 04 (lane composition) to mount: the lane wires `ChatAttachments onChange` into the transport payload and renders `ChatTokenWidget` off the live run state.
- No blockers. Live end-to-end multimodal send remains milestone-end live-deferred (DEF-29-09-1 live-ectx registry), unchanged by this FE-only plan.

## Self-Check: PASSED

All 6 created files present on disk; both task commits (`98d5e7af`, `a0ad74f8`) present in git history.

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*
