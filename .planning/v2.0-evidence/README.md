# Milestone v2.0 Evidence Pack — Universal Run Chat & VelocityAI UI Convergence

Captured 2026-07-07. These are the verbatim final reports of the six max-effort investigation agents that ground `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` (the POR), plus two synthesized contracts. **Read the POR first; come here for the detail** (file:line anchors, data contracts, per-page delta classes, borrow lists).

| Doc | What it is | Feeds |
|-----|-----------|-------|
| `01-run-ui-teardown.md` | Full structural teardown of the 4 run-screen mocks (`Hexaware Run*.dc.html`): layout, chat surfaces, Steps 3-level drill-down, Preview/Files/Audit, live-state machine, design tokens, consolidated data contract, mock-fiction list | Phases 30–31 (chat lane + run redesign), Phase 27 contracts |
| `02-workspace-shell-teardown.md` | Per-page teardown of `Hexaware Workspace v2.dc.html` + sibling files: shell chrome, all 8 views + 5 overlays, data contracts, current-product mapping, RESKIN/RESTRUCTURE/NEW-BUILD delta classes, cross-page inventory | Phases 34–37 (shell convergence) |
| `03-backend-chat-surface-map.md` | File:line map of everything chat-relevant in the backend: WS transport + full event taxonomy, gate/clarify/redo seams, run_events persistence, dormant `run_images`, compaction seams, ownership patterns, landmines, gap analysis | Phases 27–29, 32 (backbone, uploads, concierge) |
| `04-frontend-anatomy.md` | Current FE map: stack, run-screen component tree, event pipeline, the dead chat kit, upload reality, theming audit (reskin cost), e2e resilience, gap analysis | Phases 30–31, 34–37 |
| `05-chat-library-research.md` | Verified July-2026 landscape: feature matrix, integration sketches, compression verdict, ranked recommendation — the evidence behind D-09 (no external framework) | D-09 record; revisit only if D-09 reopens |
| `06-open-design-teardown.md` | `nexu-io/open-design` chat-panel teardown: why not wholesale, the 8-item borrow list with file paths, anti-lessons | Phase 30 (borrow list), D-09 |
| `07-synthesized-contracts.md` | The two session-synthesized tables: the D-12 live-state contract (real event → chat lane + composer + Steps per state) and the coverage cross-check (every target surface → data source → owning phase → status) | Phase 27 UI-SPECs |

**Provenance:** each report was produced by a dedicated Opus-4.8 max-effort investigation agent on 2026-07-07 and is preserved verbatim (evidence, not prose to re-edit). Claims cite file:line of the code/mocks *as of that date* — verify anchors before acting on them in later sessions. The IMPLEMENTATION-REGISTER corrections layered on top (e.g. which "backend-needed" items already exist) are recorded in the POR §5 and the coverage cross-check.
