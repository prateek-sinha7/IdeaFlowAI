# Phase 31: Chat Lane MVP [A3] - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR + evidence.

<domain>
## Phase Boundary

Revive the dead in-repo chat kit into the run screen and wire it to Phase-29's SSE/REST transport + chat-message events. Ships in the CURRENT skin (BEFORE the Phase-32 reskin) so it delivers value early. FRONTEND-heavy (+ a little narrator glue if needed).

Deliverables (CHATUI-01/02/03):
1. The revived chat kit renders the FAMILY-anchored transcript (D-02, `/family`) with streaming markdown (react-markdown) + `aria-live`/`role="log"` on the streaming region (open-design's documented a11y failure — do NOT repeat it).
2. Result cards (clarify/gate/pipeline/deliverable/spec-revision) deep-link into the run tabs via the nonce'd seam (open-design borrow #6).
3. Gate/clarify quick-actions IN-LANE, mirroring Steps — one `approve_review`/answer either way; four gate actions incl. `update_specs` (KAN-101); event-driven gates (KAN-94); terminal fence hides gate actions (KAN-100); gate-edit retained client-side (KAN-98).
4. Attachment UI: file picker + preview EXIST (image waves); ADD paste + drag-drop + wire the client resize (Phase 30's `resizeImage.ts`). Token-usage widget from P26 telemetry.
5. Open-design borrow-list items 1–7 integrated WITH Apache-2.0 attribution/NOTICE: `partial-json` repair, `extractStreamingJsonString`, tool-renderer registry, `buildBlocks` events→blocks reducer, scroll/anchor + measured virtualizer (>80 msgs), the nonce'd deep-link seam, ThinkingBlock/todo/file-ops blocks.

REUSE (do not rebuild): the dead kit at `frontend/src/components/chat/` (`ChatPanel.tsx`, `ChatInput.tsx`, `MessageBubble.tsx`, `ArtifactCard.tsx`, `ErrorMessage.tsx` — streaming bubbles, markdown, cursor, typing indicator, auto-scroll, voice already implemented in raw Tailwind + motion). Phase-29's `frontend/src/providers/RunConnectionProvider.tsx` + `frontend/src/hooks/useRunStream.ts` (the SSE twin — behind the `NEXT_PUBLIC_SSE_TRANSPORT` flag; the flag-OFF path stays the legacy WS, unchanged). Preserve the FIX-039 unconditional-accumulator-reset ordering when touching `useWorkflow.ts`.

Authoritative inputs (READ): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §2 (D-09 no-framework / revive-kit + borrow-list; D-15 reskin-look-keep-behavior — chat MVP is CURRENT-skin so it's mostly BEHAVIOR, cite the canonical shared-surface spec `evidence 11 §B` where it touches shared idioms; D-02 family-anchored). Evidence: `04-frontend-anatomy.md` (the dead chat kit inventory + CORRECTIONS addendum), `06-open-design-teardown.md` (the borrow list with file paths + anti-lessons: keep react-markdown, ship aria-live), `07-synthesized-contracts.md` (D-12 live-state table — composer mode per state), `01-run-ui-teardown.md` (chat column + result cards). Phase-28 contracts: `.planning/phases/28-chat-contracts-guards-a0/contracts/` (`LIVE-STATE-CONTRACT.md`, `MOCKWS-CHAT-DRIVER-CONTRACT.md`).

### ⚠ e2e-BASELINE CAVEAT (verify by DELTA, not absolute)
Phase 29 recorded a PRE-EXISTING `feat/ui-2` e2e baseline breakage (DEF-29-06-1: most mocked Playwright specs already red before any v2.0 work; DEF-29-04-1: 12/50 pipeline-validation). So Phase 31 FE verification MUST verify BY DELTA (per the "verify by identity" discipline): new chat specs PASS, and there is NO NEW breakage vs the current `feat/ui-2` baseline — do NOT chase absolute-green e2e. Use the Phase-29 mock-SSE driver (`29-06`) + the Phase-28 MOCKWS-CHAT-DRIVER contract. tsc: identity (only the known pre-existing errors, zero new).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3; do NOT re-open)

- No external chat framework (D-09) — revive the in-repo kit + borrow-list (Apache-2.0 attribution). Keep react-markdown; ship `aria-live`/`role="log"`.
- Family-anchored transcript (D-02); Concierge always-on (ND-2) but the Concierge itself is Phase 33 — this MVP shows the lane + narrator cards + router-backed quick actions, not the LLM concierge.
- Output name "Deliverable" (LOCK-F). Run output card/labels say "Deliverable".
- Behavior over restyle: this is the CURRENT skin; the reskin is Phase 32. Where a shared idiom is unavoidable, take the `evidence 11 §B` canonical value (running=blue, etc.).

INVARIANTS: SC-001 (result cards/quick-actions keyed on generic event types, never a workflow name), INV-3 (FE-only — the 5 backend goldens are untouched by construction), a11y (aria-live), import-linter unaffected (FE). No backend runtime change (chat backbone already built in Phase 29).
</decisions>

<code_context>
## Existing Code Insights (from evidence 04/06 + Phase 29)

`frontend/src/components/chat/*` (dead kit to revive); `frontend/src/app/dashboard/page.tsx` + `frontend/src/components/layout/DashboardLayout.tsx` (already thread `messages`/`streamingContent`/`onSendMessage` props that nothing renders — the mount points); `frontend/src/hooks/useWorkflow.ts` (the flag-selected transport + reducer — FIX-039 ordering); `frontend/src/providers/RunConnectionProvider.tsx` + `useRunStream.ts` (Phase-29 SSE); `frontend/src/components/workflow/AgentProgressPanel.tsx` (the revise composer + suggestions to fold into the lane); `frontend/e2e/fixtures/mockWs.ts` + the Phase-29 mock-SSE driver. Offline verify: `vitest run <file>` + mocked Playwright (`--project=mocked`) + `tsc --noEmit` identity; no live server.
</code_context>

<specifics>
## Specific Ideas

Deliverables: mount the revived chat lane in the execution surface (left column, absorbing the AgentProgressPanel controls: stop, revise-as-chat, suggestions-as-chips); stream via the SSE transport (flag-gated) with markdown + aria-live; result cards with tab deep-links; in-lane gate/clarify quick-actions (4 gate actions incl update_specs); attachment UI (picker/preview exist → add paste + drag-drop + wire resizeImage); token-usage widget; borrow-list 1–7 with attribution. New `data-testid`s on chat surfaces (the codebase's first). Verify by delta.
</specifics>

<deferred>
## Deferred Ideas

The Concierge LLM (Phase 33). The full reskin (Phase 32). Mid-run live steering delivery (DEF-29-09-1 — needs the live-ectx registry). Image persistence (ND-10). Absolute-green e2e (baseline is pre-existing-red — out of scope; delta-verify only).

## Execution-viability note (autonomous run)
FE-only, offline-verifiable via vitest + mocked Playwright + tsc-identity. No live server needed. Verify by DELTA against the pre-existing e2e baseline. If a check needs a live backend, mark it live-deferred — do not hang, do not fabricate.
