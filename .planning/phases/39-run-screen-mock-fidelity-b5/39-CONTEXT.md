# Phase 39: Run Screen Mock Fidelity - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** Orchestrator investigation (mock render + read-only frontend map + backend event-vocabulary verification + a reviewed side-by-side baseline gallery). Follows the plan-ingestion preference: a full spec exists — copy it faithfully; skip interactive re-discovery/research.

<domain>
## Phase Boundary

Bring the **run / execution screen** to full visual fidelity with three target mocks, **as-is**. In scope: the **left conversation lane**, the **run header**, all four tabs (**Preview / Steps / Files / Audit**) with **every internal sub-navigation level**, across all **three run states** (settled / live-streaming / failed). This RE-ALIGNS the run screen that Phase 32 (`32-run-screen-redesign-a4`) already built — it is predominantly **frontend presentation** work; the data already flows.

**Target mocks (the literal spec):**
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Run.dc.html` — settled/complete run
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Run - Live.dc.html` — live/streaming
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Run - Failed.dc.html` — failed

Out of scope: other screens (home/login/composer/wizard/admin — those are Phases 35-38); backend event emission; the deliverable renderers' internals; anything not on the run screen.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### D39-1 — Invert D-15's default for this phase (fidelity, not reuse-over-clone)
The milestone POR (D-15) said "adopt the visual language, reuse existing components over rebuilding." For THIS phase that default is **inverted**: reproduce the mock's **composition exactly**. Every deviation goes in the INTENDED-DIVERGENCE REGISTER (below) with a justification. The plan MUST carry that register.

### D39-2 — Full as-is scope (user decision, 2026-07-11)
Reproduce the mocks AS IS, INCLUDING the net-new affordances: **Share** action, **Version ▾** menu, the **"Renders as"** deliverable-type switch, and the **fuller Audit categories** (secret-scan / performance / behavioral-hook rows). Share may need a small **additive** backend endpoint — additive-only, behind existing auth.

### D39-3 — Reuse the deliverable renderers (the one exception to D39-1)
The Preview-tab renderers (`UserStoryPreview`, `PPTPreview`, `PrototypePreview`, `AppBuilderPreview`, `MarkdownPreview`) are **reused as-is** — do NOT rebuild them from the mock's hardcoded website. Only wrap them in the mock's browser chrome + the "Renders as" switch.

### D39-4 — Data is already on the wire (VERIFIED — do NOT re-derive or rebuild backend)
- The engine already emits the full per-agent trace the mock renders: `agent_input` carries `context_message` + `context_sources` + `tool_calls` (`backend/agents/execution_engine/engine.py:2810-2831`); plus `agent_chunk`, `tool_call`/`tool_result`, `subagent_spawned`/`subagent_result`, `review_gate_ready`/`review_gate_approved`, `questionnaire_ready`/`questionnaire_complete`, `hook_run`, `gate_status`, `step_completed`, `summary`.
- Frontend state already carries it: `AgentRunState` has `inputPrompt`, `contextSources: ContextSource[]` (per-source sizes = the mock's "Context received" panel), `toolCalls: ToolCallEntry[]`, `thinkingText` (`frontend/src/types/index.ts:522-567`). `useWorkflow.ts` maps `agent_input`→inputPrompt/contextSources (:630-643), `tool_call`/`tool_result`→toolCalls (:646-687).
- The Audit tab is REAL, not a stub: `AuditTab.tsx:236-286` fetches `getRunGateEvents` / `getRunValidationResults` / `getRunExecRuns` and renders categorized, severity-tagged, filterable, exportable rows.
Conclusion: ~90% of the work is presentation over data that already exists.

### D39-5 — Intended-divergence register (KEEP these; do NOT "fix" toward the mock)
- Brand wordmark **"VelocityAI"** (mock says "HEXAWARE").
- Nav label **"My Workflows"** (mock says "Catalogue") — per D-11.
- Nav active-state = **purple underline** (mock uses a different treatment) — per ND-13.1.
- Live data, never the mocks' hardcoded/fiction values ("14.8M tokens", the fixed transcript, "150 design systems") — SC-001.

### D39-6 — Verification is a screenshot-diff gate, not prose (the load-bearing decision)
The last 12 UI phases drifted because fidelity was never the acceptance test. For this phase the acceptance ORACLE is a **side-by-side screenshot-diff against the mocks**. Reuse the harness the orchestrator built (see canonical refs). Each wave's Definition of Done = the diff for that surface is closed to the intended-divergence register + the baseline gallery is regenerated + a human signs off on the images. No wave is "done" on a prose claim.

## Claude's Discretion
- Exact component decomposition per wave (new sub-components vs. extending existing), provided the file map below is respected and no dual implementations are left (delete superseded code).
- Whether Share needs a persisted token (additive migration, reuse `ArtifactRef` owner_id+workspace_id if so) or is a client-only link in v1 — planner to decide and state.
- The precise structure of the formalized fidelity harness under `frontend/e2e/`.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The design contract (the spec)
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Run.dc.html` — settled-run mock (all tabs + Steps drill + left lane + Version/Share/Download header + "Renders as" switch).
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Run - Live.dc.html` — streaming states (progress bar, streaming caret, inline awaiting-you gate/clarify, running pill).
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Run - Failed.dc.html` — failed (red badge, what-went-wrong card, resume options, halted banner).
- `.planning/phases/39-run-screen-mock-fidelity-b5/39-UI-SPEC.md` — per-surface fidelity spec + the intended-divergence register.
- Baseline gallery (mock-vs-current, reviewed TRUSTWORTHY): https://claude.ai/code/artifact/62fca6df-4f86-4dd3-87f2-f176d6554ebc

### The fidelity harness (reuse + formalize under frontend/e2e)
- `frontend/e2e/tests/zzz-baseline.spec.ts` — drives our run screen through settled/live/failed via the mocked-WS harness + route-stubs (currently a throwaway capture spec — formalize it).
- The mock renderer approach: render the `.dc.html` mocks over a local HTTP server (so `support.js` + fonts load), screenshot per tab. (Reference implementation lives in the orchestrator's scratch: `capture-mocks.js` + `assemble-gallery.py`.)

### Source files (the file map — verified read-only)
- `frontend/src/components/layout/DashboardLayout.tsx` — execution shell + 2-panel split (`mainView==="execution"` :1686-1834; left lane :1707-1746; right panel :1749-1832; `runFamily` fetch :387).
- `frontend/src/components/preview/PreviewPanel.tsx` — right panel, tabs, deliverable dispatch (`TAB_CONFIG` :331-339 — current order Preview·Files·Steps·Audit, MUST become **Preview·Steps·Files·Audit**; header :753-789; `FIRST_PARTY_RENDERERS` :632-649; `DegradedRunAffordance` :357-428; `LiveVersionChip` :762).
- `frontend/src/components/ui/Tabs.tsx` — tab primitive (`role="tab"`, underline active).
- `frontend/src/components/results/AgentThinkingTab.tsx` — Steps tab (`PipelineHeader` :90-142; `AgentTimelineCard` :483-610; `ToolCallsSection` :348-404; `ConstructionDrilldown` :624-694; `StartingPointCard`; `ClarificationsCard`; `InlineGateActions`/`InlineClarifyActions`).
- `frontend/src/components/results/FilesTab.tsx` — Files tab.
- `frontend/src/components/results/AuditTab.tsx` — Audit tab (real fetches :236-286).
- `frontend/src/components/chat/RunChatLane.tsx` — left-lane composition root; `ChatPanel.tsx` ("What can I help you with?" greeting :284 — mock has NO greeting, it is a structured transcript); `MessageBubble.tsx`.
- Deliverable renderers: `frontend/src/components/preview/{UserStoryPreview,PPTPreview,PrototypePreview,AppBuilderPreview,MarkdownPreview}.tsx` — REUSE.
- Hooks (do NOT rework contracts): `frontend/src/hooks/{useWorkflow,useRunChat,useRunStream}.ts`.
- Types: `frontend/src/types/index.ts` (`AgentRunState` :522, `ContextSource` :549, `ToolCallEntry` :561, `RunFamily`/`FamilyMember` :363-377).

### Locked decisions / prior work
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 32 (run-screen-redesign, the code being re-aligned); Phase 36 (HomeLaunchGrid/D-11); Phase 33 (Concierge).
</canonical_refs>

<specifics>
## Specific fidelity gaps (from the reviewed baseline — the per-surface target)

1. **Left lane (biggest gap):** mock = structured transcript — run header (Back to history · type · Done · elapsed · tokens), user/assistant bubbles, inline "N clarifying questions" + "PIPELINE · N agents" cards, attachment chips, "Ask for a change…" composer. Ours = "What can I help you with?" chat-kit greeting + suggestion chips + "Suggested next steps" + revision composer. Replace the greeting-state with the transcript composition; keep the live-data + revision behavior.
2. **Run header:** assemble Version ▾ (from existing `runFamily`) / Share / Download. Today Version is a chip in PreviewPanel, Stop is in the lane, no Share/Download-all.
3. **Tab order:** Preview·**Files·Steps**·Audit → Preview·**Steps·Files**·Audit (`TAB_CONFIG`).
4. **Steps:** overview spine + inline "Review gate — approved" strips + Clarifications card → per-agent **2-column detail with a sticky "Context received" panel** (from `contextSources`) → task-detail drill. Data already present; reorganize the presentation.
5. **Preview:** browser chrome + the "Renders as" deliverable-type switch, wrapping the existing renderers.
6. **Files:** dark "Final output" hero + per-agent outputs timeline spine + Run-input cards (ours has the structure, needs the chrome).
7. **Audit:** 6-stat compliance grid + coverage chips + green "passed all governance gates" banner + the fuller categories (secret-scan / performance / behavioral) on top of the existing real fetches.
8. **States:** live-streaming (progress bars, streaming caret, inline awaiting-you gate/clarify, running pill) from `Run - Live`; failed (what-went-wrong card, resume options, halted banner, red badges) from `Run - Failed`.

## Proposed waves (planner to refine)
- **W1 Shell:** left structured transcript + run header (Version/Share/Download) + tab order.
- **W2 Steps:** overview spine + gate strips + Clarifications → 2-column agent detail w/ sticky Context-received → task-detail drill.
- **W3 Preview:** browser chrome + "Renders as" switch, wrapping existing renderers.
- **W4 Files:** Final-output hero + per-agent timeline + Run-input cards.
- **W5 Audit:** compliance grid + coverage banner + fuller categories.
- **W6 States:** live-streaming + failed.
- **Wsupport:** Share affordance (additive) + repair the stale mocked-e2e harness so `npm run e2e` is green and the fidelity harness runs (see scope fence).
</specifics>

<deferred>
## Deferred Ideas
- Other screens' mock fidelity (composer/wizard/admin/handoff) — future phases if a v2.1 fidelity track is opened.
- Any backend change beyond the optional additive Share endpoint.
</deferred>

<scope_fence>
## Negative Space / Forbidden (a phase that violates these is NOT done)
- Do NOT rebuild backend event emission, the `useWorkflow`/`useRunChat`/`useRunStream` contracts, or the deliverable renderers — the data already flows; this is presentation.
- Do NOT clone the mocks' inert/hardcoded/fiction data — bind to real live data (SC-001).
- Do NOT touch the intended divergences (brand / "My Workflows" / underline) toward the mock (D39-5).
- No dual implementations (INV-3/INV-12) — deleting superseded run-screen code is part of the change.
- Additive only; `feat/ui-2` only (NEVER main/staging); no commit trailer; never push without explicit go-ahead.
- Respect the deepagents runtime mandate (INV-13) and additive-migrations-only (Q3) if Share needs persistence (reuse `ArtifactRef`, never a new table).
- Known-red side task (fold in, do not ignore): the mocked e2e suite currently crashes against feat/ui-2 — `GET /api/workflows` (home grid `rows.filter`), the "Provide the brief" launch flow (stale `dashboard.runWith`), and `/api/runs/{id}/family` (`[...runFamily.members]` not iterable). Fix so `npm run e2e` is green and the fidelity harness runs.
</scope_fence>

---

*Phase: 39-run-screen-mock-fidelity-b5*
*Context gathered: 2026-07-11 via orchestrator investigation (plan-ingestion path)*
