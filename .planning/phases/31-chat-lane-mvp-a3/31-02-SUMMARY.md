---
phase: 31-chat-lane-mvp-a3
plan: 02
subsystem: ui
tags: [react, typescript, vitest, chat, virtualization, tool-renderer, open-design, apache-2.0]

# Dependency graph
requires:
  - phase: 31-chat-lane-mvp-a3 (plan 01)
    provides: "blocks.types ChatBlock/AgentEvent union + buildBlocks reducer — the render contract these components dispatch on"
provides:
  - "tool-renderers: registerToolRenderer/renderToolBlock/GenericToolCard — three-tier registry -> generic fallback dispatch, try/catch-isolated, name-only lookup (borrow #3, SC-001)"
  - "useMeasuredVirtualWindow + VIRTUALIZE_THRESHOLD=80 — pure measured virtual window over a scroll ref + per-index heights (borrow #5)"
  - "ThinkingBlock / TodoCard / FileOpsSummary — collapsed reasoning + plan-progress + files-this-turn block components (borrow #7)"
  - "First data-testids in the codebase: chat-tool-card, chat-thinking-block, chat-todo-card, chat-file-ops"
affects: [31-04-chat-lane, chat-runtime]

# Tech tracking
tech-stack:
  added: []  # ZERO new deps — reuses react/motion/lucide-react already in the kit
  patterns:
    - "Three-tier tool-render dispatch: Map registry (extension point) -> generic fallback, per-renderer try/catch isolation, generic-name-only lookup (SC-001-safe)"
    - "Pure windowing math behind a thin ref-reading hook: virtualization disengages below threshold, windows a slice above it; consumer owns the ResizeObserver and feeds heights via measure()"
    - "Presentational block components render the plan-01 ChatBlock variants directly; data-testids on block roots"

key-files:
  created:
    - frontend/src/components/chat/runtime/tool-renderers.tsx
    - frontend/src/components/chat/runtime/tool-renderers.test.tsx
    - frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts
    - frontend/src/components/chat/runtime/useMeasuredVirtualWindow.test.ts
    - frontend/src/components/chat/blocks/ThinkingBlock.tsx
    - frontend/src/components/chat/blocks/TodoCard.tsx
    - frontend/src/components/chat/blocks/FileOpsSummary.tsx
    - frontend/src/components/chat/blocks/blocks.test.tsx
  modified: []

key-decisions:
  - "Tool-render dispatch ships the registry + generic fallback ONLY — no family-card vocabulary pre-populated (the lane/workflow registers renderers later). Registry keyed on the generic tool name; per-renderer try/catch so a bad renderer degrades to GenericToolCard and never breaks the transcript (SC-001, T-31-02-T)."
  - "Virtual-window math is pure and lives in a free function; the hook is a thin shell that reads scrollTop/clientHeight off the passed ref (mockable) and bumps a version counter on scroll/measure. Below VIRTUALIZE_THRESHOLD=80 virtualization disengages (full range, zero spacers); above it topSpacer/bottomSpacer reconstruct the off-window height (T-31-02-D)."
  - "Block components accept the plan-01 ChatBlock discriminated variant directly (ThinkingBlock/FileOpsSummary) or a flat projection (TodoCard's Todo[]); current skin per D-15 (raw Tailwind + motion + lucide-react, reusing MessageBubble's collapsible idiom) — Phase 32 owns the reskin."

patterns-established:
  - "chat/blocks/ directory for presentational block components rendering the chat/runtime/ ChatBlock union"
  - "data-testid on every chat block root (the codebase's first testids) — chat-tool-card / chat-thinking-block / chat-todo-card / chat-file-ops"
  - "aria-expanded/aria-controls on the ThinkingBlock collapse toggle so the reasoning region is AT-legible (does not regress the aria-live/role=log story owned by the lane)"

requirements-completed: [CHATUI-01]

# Metrics
duration: 6min
completed: 2026-07-08
---

# Phase 31 Plan 02: Open-Design Rendering Mechanics (tool-renderer registry / measured virtualizer / block components) Summary

**The open-design borrow-list RENDERING pieces (#3 tool-renderer registry, #5 measured virtual window, #7 ThinkingBlock/TodoCard/FileOpsSummary) land as small, attributed, SC-001-safe React pieces that render plan-01's ChatBlock union — with the codebase's first data-testids, 48 green vitest cases, and tsc-identity.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-08T08:28:22Z
- **Completed:** 2026-07-08T08:34:03Z
- **Tasks:** 3
- **Files modified:** 8 created

## Accomplishments
- `tool-renderers.tsx` — a three-tier dispatch (`Map` registry keyed on the generic tool name → `GenericToolCard` fallback) with per-renderer try/catch isolation. Ships empty (the SC-001-safe extension point the lane populates); a crafted tool name can at worst miss the registry and fall back to the inert generic card (borrow #3, T-31-02-T).
- `useMeasuredVirtualWindow.ts` — `VIRTUALIZE_THRESHOLD=80` + a pure measured virtual window over a scroll ref + a per-index height map. Disengages below the threshold (full range, zero spacers); above it returns only the visible slice with top/bottom spacers that reconstruct the off-window height, so a >80-message list renders only what is visible (borrow #5, T-31-02-D).
- `ThinkingBlock` / `TodoCard` / `FileOpsSummary` — collapsed-by-default reasoning with a "Thought for Xs" timer, a TodoWrite-projected plan-progress strip, and a files-this-turn strip. Each renders a plan-01 `ChatBlock` variant and carries the codebase's first `data-testid` (borrow #7).
- 48 green vitest cases (7 + 5 + 6 new this plan, over the 6 chat-runtime/blocks files); tsc-identity (zero new errors vs the `e2e/fixtures/mockApi.ts` baseline); SC-001 grep 0; INV-3 held (all 8 files under `frontend/src/components/chat/`).

## Task Commits

Each task was committed atomically:

1. **Task 1: tool-renderer registry + three-tier dispatch (borrow #3)** — `f5bbf703` (feat)
2. **Task 2: measured virtual window hook (borrow #5)** — `f9f759b1` (feat)
3. **Task 3: ThinkingBlock + TodoCard + FileOpsSummary block components (borrow #7)** — `21159d91` (feat)

**Plan metadata:** _(this docs commit)_

_Opportunistic TDD (`tdd_mode=false`): Tasks 1 & 2 committed test + implementation together as one atomic unit; Task 3 (`type="auto"`) shipped components + suite together._

## Files Created/Modified
- `frontend/src/components/chat/runtime/tool-renderers.tsx` — registry + `renderToolBlock` dispatch + `GenericToolCard` + pure `deriveToolStatus`/`toRenderProps` (borrow #3)
- `frontend/src/components/chat/runtime/tool-renderers.test.tsx` — 7 vitest cases (registered renderer used, unregistered→generic, throwing renderer isolated, status pending/success/error, name-only dispatch/SC-001, standalone GenericToolCard)
- `frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts` — `useMeasuredVirtualWindow` + `VIRTUALIZE_THRESHOLD` + pure `computeWindow` (borrow #5)
- `frontend/src/components/chat/runtime/useMeasuredVirtualWindow.test.ts` — 5 vitest cases (threshold constant, disengage ≤80, windowed slice + spacer sum, measure() updates the model, determinism)
- `frontend/src/components/chat/blocks/ThinkingBlock.tsx` — collapsed reasoning + "Thought for Xs" timer, aria-expanded toggle (borrow #7)
- `frontend/src/components/chat/blocks/TodoCard.tsx` — TodoWrite-projected plan-progress strip (`Todo[]` → done/total)
- `frontend/src/components/chat/blocks/FileOpsSummary.tsx` — files-this-turn strip over the `file_ops` block
- `frontend/src/components/chat/blocks/blocks.test.tsx` — 6 vitest cases (thinking testid + collapsed-by-default + expand toggle + timer label + no-duration fallback; todo testid + progress; file-ops testid + strip)

## Decisions Made
- **Registry ships empty, no family-card vocabulary:** per the plan action, Task 1 delivers only the registry + generic fallback + status derivation. Pre-populating a Write/Edit/Read/Bash vocabulary here would couple the runtime to a specific tool set; the lane (plan 04) or a workflow registers renderers at composition time. This keeps the dispatch a pure generic-name lookup (SC-001).
- **Windowing math extracted to a pure free function (`computeWindow`, unexported):** keeps the hook a thin ref-reading shell and the math deterministic/unit-testable; the export surface stays exactly `useMeasuredVirtualWindow` + `VIRTUALIZE_THRESHOLD` as the plan's artifact contract specifies. The scroll subscription is guarded so a plain mock ref (no `addEventListener`) is a no-op — the windowing is a pure function of the injected scroll inputs.
- **`topSpacer` tracks the first-visible offset (≈ scrollTop) and is therefore invariant to changes above the fold** — see Issues; the observable that proves `measure()` feeds the subsequent window is `startIndex`, so the Task-2 measure test asserts the index shift, not the spacer.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- **Task 2 measure() test premise corrected before commit:** the initial test asserted that growing item 0's measured height would change `topSpacer`. It does not — `topSpacer` equals the offset of the first-visible item, which always sits just below `scrollTop` regardless of the heights above it (growing an above-fold item shifts *which* index is first-visible, exactly offsetting its own growth). The failing test surfaced this; retargeted the assertion to `startIndex` (50 → 48 after item 0 grows 100→300px at scrollTop 5000), which directly proves the subsequent window read the measured height. No implementation change — the hook was correct; the test's premise was wrong.

## Deferred / Follow-ups
- **THIRD-PARTY-NOTICES.md local-path rows (#3/#5/#7):** left as-is to honor this plan's declared file scope (all 8 files under `frontend/src/components/chat/`; INV-3). The borrow mechanisms are already attributed as planned rows in the table, and every local module carries the `Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md` header, so Apache-2.0 attribution is satisfied. Finalizing the table's "local reimplementation" cells to the concrete paths is a cheap doc-only follow-up (naturally folded into plan 04 when it adds its own #5/#6 rows).

## User Setup Required
None - no external service configuration required. Zero new npm dependencies (reuses react/motion/lucide-react already in the kit).

## Next Phase Readiness
- The tool-renderer registry, measured virtual window, and three block components are stable and importable by 31-04 (the chat lane composition). The lane engages `useMeasuredVirtualWindow` at >80 messages (the kit's naive auto-scroll stays for small transcripts), registers any tool renderers via `registerToolRenderer`, and renders `ThinkingBlock`/`TodoCard`/`FileOpsSummary` from the coalesced `ChatBlock[]`.
- a11y: the ThinkingBlock collapse toggle carries `aria-expanded`/`aria-controls`; it does not introduce an `aria-live`/`role=log` region (that transcript story is owned by the lane in plan 04) — so nothing here regresses it.
- Verified offline: `vitest run src/components/chat/runtime/ src/components/chat/blocks/` → 48/48 green; `tsc --noEmit` identity (0 new errors beyond the known `e2e/fixtures/mockApi.ts` baseline); SC-001 grep 0; INV-3 held (no backend / golden / e2e-spec file touched).

## Self-Check: PASSED

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*
