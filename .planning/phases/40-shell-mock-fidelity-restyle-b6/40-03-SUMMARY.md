---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 03
subsystem: frontend-shell
tags: [ui-fidelity, library, restyle, shell-mock]
requires: ["40-01"]
provides: ["Library surface restyled to the Hexaware Workspace v2 mock (header + Agents/Skills/Hooks card grids)"]
affects: ["frontend/src/components/library/LibraryPage.tsx"]
tech-stack:
  added: []
  patterns: ["mock-composition restyle via existing token layer (ink ramp / brand / surface-card / line-*)", "horizontal filter-chip row replacing the legacy left sidebar to match the mock"]
key-files:
  created:
    - frontend/src/components/library/LibraryPage.test.tsx
  modified:
    - frontend/src/components/library/LibraryPage.tsx
decisions:
  - "Adopted the mock composition exactly: 'Library' h1 + count line + search lead ABOVE the Agents/Skills/Hooks tab chrome; the legacy 200px left sidebar was replaced with the mock's horizontal filter-chip row (agents show counts; skills/hooks show labels) — filter STATE + behavior preserved."
  - "Active filter chip = solid dark pill (surface-near-black + white), matching the mock (initial brand-fill draft was a fidelity gap, fixed pre-checkpoint)."
  - "Agent card CTA relabelled 'Tap to explore →' → 'Configure →' to match the mock text; the click still opens the shared AgentCapabilitiesModal (ND-Z — the drawer defers to Phase 41)."
  - "Hook event badge keeps the real event identifier (e.g. PostToolUse) rather than the mock's cosmetically-spaced 'Post Tool Use' — real-data fidelity under ND-D; surfaced to the human reviewer."
metrics:
  duration: ~30m
  completed: 2026-07-12
---

# Phase 40 Plan 03: Library Surface Restyle Summary

Restyled `LibraryPage` to the `Hexaware Workspace v2.dc.html` Library surface — a "Library" h1 + item-count line + search leading above the Agents/Skills/Hooks tab chrome, with each tab's card grid rebuilt to the mock's card composition — routing all color/type through the existing Phase-32/35 token layer (no raw hex). The shared composer-owned `AgentCapabilitiesModal` is untouched (ND-Z); the agent-detail drawer defers to Phase 41.

## What changed

- **Header (new):** leads with a light-weight "Library" h1 (26px), an item-count line (`N agents · M skills · K hooks`, live data — ND-D), and the search input on the right (restyled to the mock's surface-card / line-control / 10px-radius field). The h1 now precedes the tablist in DOM order (was tabs-lead).
- **Tab chrome:** kept the `Tabs` primitive + the ND-C purple-underline active-state (did NOT adopt the mock's pill-fill).
- **Layout:** replaced the legacy 200px left sidebar with the mock's horizontal filter-chip row above each grid. Category / skill-category / hook-event filter STATE and behavior are preserved; the active chip is a solid dark pill matching the mock.
- **Agents grid:** `repeat(auto-fill,minmax(288px,1fr))`; avatar/initials + name + uppercase category, role line, description, footer clock+duration + brand "Configure →".
- **Skills grid:** `repeat(auto-fill,minmax(360px,1fr))`; brand-fill puzzle icon + name + category, description, tag chips + "View →".
- **Hooks grid:** `repeat(auto-fill,minmax(360px,1fr))`; name + dark event badge, italic trigger, description, tag chips + "View →".
- Preserved: real search filter, category/event filtering, the skill/hook detail modals, and the agent-capabilities open path. The `Search agents…` placeholder + role=tab tab bar + real counts + no-retired-palette contract (reskin test) all stay green.

## Intended-Divergence register touch

This surface exercises (all pre-registered — no new ND letter added; the canonical register lives in the 40-01-owned `assemble-shell-gallery.mjs`, untouched):
- **ND-A** — brand "VelocityAI" (not "HEXAWARE").
- **ND-B** — nav label "My Workflows" (not "Catalogue").
- **ND-C** — nav/tab active-state = purple underline (not the mock's pill-fill).
- **ND-D** — live catalog data (63 agents / 244 skills / 8 hooks vs the mock's 14/8/8); the hook event badge shows the real event identifier (`PostToolUse`) rather than the mock's spaced "Post Tool Use".
- **ND-Z** — the mock's right-side agent-detail **drawer** (Overview/Skills/Hooks/Config) is NOT rebuilt; Phase 40 keeps the shared `AgentCapabilitiesModal`; the drawer rebuild lands with the Composer in Phase 41. Captured as `library-agent-detail` (aliased to the mock's `agent-detail-drawer`).

## Regenerated gallery (`--surface library`)

6 pairs regenerated into `frontend/e2e/fidelity/gallery-shell.html`:
`library`, `library` (full-page), `library-agents`, `library-skills`, `library-hooks`, `library-agent-detail` (ND-Z). Current side refreshed via `SHELL_CAPTURE=1 npm run e2e -- zzz-shell-baseline`; target side reused from 40-01; assembled via `assemble-shell-gallery.mjs --surface library`.

## Verification results

- `npx tsc --noEmit` — 0 errors (excluding the pre-existing `mockApi.ts` filter).
- `LibraryPage.test.tsx` (new, 5 tests) + `LibraryPage.reskin.test.tsx` (5 tests) — 10/10 passed. Asserts: h1 leads before the tablist, the count line renders, and all three tab grids render; plus the preserved Tabs/search/counts/no-retired-palette contract.
- Banned-literal greps: 0 raw hex, 0 retired palette (`text-gray-`/`bg-gray-`/`#1B2A4A`), 0 `dangerouslySetInnerHTML` (T-40-03-01 XSS mitigation held — JSX escaping only).
- `AgentsPopup.tsx` / `AgentCapabilitiesModal` untouched (git status clean — ND-Z / INV-3).
- No package-manager installs (T-40-03-SC held).

## Deviations from Plan

**1. [Rule 1 — Fidelity bug] Active filter chip corrected to the mock's dark pill**
- **Found during:** Task 2 automation (eyeballing the regenerated `library-agents`/`library-skills` captures vs the mock).
- **Issue:** the first draft rendered the active filter chip as light `brand-fill`; the mock uses a solid dark (near-black) pill with white text — an unregistered visual departure.
- **Fix:** `chipActive` → `bg-surface-near-black border-transparent text-white font-medium`; re-captured + re-assembled.
- **Files modified:** `frontend/src/components/library/LibraryPage.tsx`.

**Note (non-blocking, for the human reviewer):** two mock-vs-ours text differences are real-data choices, not gaps — the count line omits the mock's trailing "· tap any item to see its capabilities" hint, and the hook event badge shows the technical enum (`PostToolUse`) rather than the mock's spaced form. Both are ND-D-covered; flagged at the checkpoint for a keep-or-align ruling.

## Known Stubs

None. The Library catalog is a curated static reference dataset (`AgentLibraryData` / `data/skills` / `data/hooks`) — faithful to the mock's reference intent, not a stub.

## Checkpoint

Task 2 is a blocking `checkpoint:human-verify` — NOT self-certified. The regenerated gallery (`library`, `library-agents`, `library-skills`, `library-hooks`, `library-agent-detail` sections) is handed to the reviewer for the fidelity sign-off, closed to ND-A/B/C/D + ND-Z.
