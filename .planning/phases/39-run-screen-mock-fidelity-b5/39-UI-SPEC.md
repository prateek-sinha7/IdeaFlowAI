# Phase 39: Run Screen Mock Fidelity - UI Design Contract

**Created:** 2026-07-11
**Status:** Ready for planning
**Design source of truth:** the three mock files ARE the contract (rendered, not paraphrased). This spec pins the tokens, the per-surface fidelity, the intended divergences, and the acceptance oracle.

## Source of truth
- `Hexaware Run.dc.html` (settled), `Hexaware Run - Live.dc.html` (streaming), `Hexaware Run - Failed.dc.html` (failed) — all under `/Users/1000060523/Documents/Work/VelocityAI-New-UI/`.
- Reviewed side-by-side baseline (mock vs current): https://claude.ai/code/artifact/62fca6df-4f86-4dd3-87f2-f176d6554ebc
- When a value is ambiguous, read the `.dc.html` source — it carries the exact hex, weight, size, spacing, and DOM structure.

## Design tokens (from the mocks' Design System)
- **Type:** Manrope (UI/headings), Heebo (reading/body) — the app already loads both (`frontend/src/app/layout.tsx`); do NOT change the type system.
- **Palette:** paper `#F0EEE7`; lane `#F6F4EE`; near-black ink `#15161A`; dark bar `#111114`; single accent purple `#3C2CDA`; hairline `#E6E3DB`/`#E2DFD6`. Semantic: green `#1F7A4D` (pass), amber `#9A6B1E` (warn), red `#A33A32` (blocked/failed).
- **Geometry:** left lane 390px in the mock (our shell uses `md:w-[340px] lg:w-[360px]` — keep our responsive width, adopt the mock's internal composition); tab row = 28px gap + 2px active underline; cards ~11–14px radius.

## Per-surface fidelity (target → current)
See `39-CONTEXT.md` <specifics> for the full gap list. Summary of what each surface must become:
1. **Left lane:** structured transcript (run header · message bubbles · inline "N clarifying questions" + "PIPELINE · N agents" cards · attachment chips · "Ask for a change…" composer) — replaces the "What can I help you with?" greeting; keep live data + revision behavior.
2. **Run header:** Version ▾ menu (from `runFamily`) · Share · Download.
3. **Tabs:** order Preview · Steps · Files · Audit; underline active-state (kept — see divergences).
4. **Steps:** overview spine + inline gate strips + Clarifications card → per-agent 2-column detail with a sticky "Context received" panel → task-detail drill.
5. **Preview:** browser chrome + "Renders as" deliverable-type switch, wrapping the EXISTING renderers.
6. **Files:** dark Final-output hero + per-agent outputs timeline + Run-input cards.
7. **Audit:** 6-stat compliance grid + coverage chips + "passed all gates" banner + fuller categories (secret-scan/performance/behavioral).
8. **States:** live-streaming (progress bar, streaming caret, inline awaiting-you gate/clarify, running pill) + failed (red badge, what-went-wrong card, resume options, halted banner).

## Intended-divergence register (KEEP — do NOT match the mock here)
- Brand wordmark **"VelocityAI"** (not "HEXAWARE").
- Nav label **"My Workflows"** (not "Catalogue") — D-11.
- Nav active-state **purple underline** — ND-13.1.
- **Live/real data** everywhere — never the mocks' hardcoded values (SC-001).

## Interaction / behavior (unchanged contracts)
- All tab bodies, the Steps drill, gates, clarifications, and streaming read from the existing WS event stream + `useWorkflow`/`useRunChat` state — no contract changes.
- The deliverable renderers inside Preview are reused as-is (D39-3).

## Acceptance oracle (the gate — not prose)
- Fidelity is proven by a **side-by-side screenshot-diff** against the mocks, per surface + per state, closed to this register. Reuse/formalize the harness (`frontend/e2e/tests/zzz-baseline.spec.ts` for our side; the local-HTTP mock render for the target side). Regenerate the baseline gallery each wave; a human signs off on the images. No surface is "done" on a prose claim.
- Standard technical checks additionally: `npx tsc --noEmit` clean; targeted vitest for touched components green; `npm run e2e` green (after the stale-harness repairs in scope).

---
*Phase: 39-run-screen-mock-fidelity-b5 · UI design contract*
