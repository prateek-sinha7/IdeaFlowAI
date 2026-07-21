# Phase 42 — Deferred Items

Recorded at closeout (42-11, 2026-07-15). Out of scope for the docs+harness closeout plan; tracked here for a follow-up pass.

## D-42-1 · RUNUI-09 mocked-e2e reconciliation (BLOCKING for RUNUI-09)

**Status:** OPEN · **Owner:** a dedicated e2e-reconciliation pass (not 42-11 scope).

`npx playwright test --project=mocked` at HEAD (`feat/ui-2`) = **112 passed / 33 failed / 29 skipped**.

**Root cause:** Waves 42-02..42-10 removed the legacy full-screen takeovers + reskinned the run screen (`src` changes) but did NOT reconcile the `ts-*` mocked-e2e specs. `git diff add18741..HEAD -- frontend/e2e/tests/` touched only `zzz-baseline.spec.ts` (the fidelity capture). So the 33 reds assert the pre-Phase-42 UI. 42-11 (docs + harness only) changed no `src`/spec code — it neither caused nor fixes these.

**Method (per the e2e-staleness discipline — Phase 39 did 84→4):** fix the shared `dashboard.ts` page-object first if a common selector drifted, then per-cluster; classify each red as **selector-drift** (re-anchor), **changed-behavior** (reconcile to the new inline surface, or `test.fixme` with a reason), or **harness-flake**. **Never delete a spec.**

### Failing clusters (33)

| Cluster | Count | Classification | Reconcile to |
|---------|-------|----------------|--------------|
| `ts-n.review-gate.spec.ts` (TS-N-01..06) | 9 | changed-behavior — asserts the DELETED full-screen `ReviewGatePanel` (42-05) | the inline gate in Steps (2-button + `artifactPreview` plan-preview, 42-08) |
| `ts-m.questionnaire.spec.ts` (TS-M-02..06) | 7 | changed-behavior — asserts the DELETED `QuestionnairePanel` "Quick Setup" takeover (42-02) | the inline clarify in Steps (`InlineClarifyActions`, single-submit, 42-06); note the extra affordances were dropped (Group G) |
| `ts-i.agent-panels.spec.ts` (TS-I-01/02/03, TS-I-09) | 2 | changed-behavior — per-agent RUNNING/DONE/ERROR in Steps | the reskinned Steps overview spine (violet running-row, 42-06) |
| `ts-r.cancel.spec.ts` (TS-R-02/03) | 2 | changed-behavior — cancel chrome | the terminal cancelled card (RunChatLane, ISS-035 marker) |
| `ts-chat.spec.ts` (TS-CHAT-03/04) | 2 | changed-behavior — chat clarify/gate actions | the re-homed inline clarify/gate actions |
| `ts-c.input-trigger.spec.ts` (TS-C-01/02) | 2 | verify — idea input placeholder / run-button disabled | check vs current launch surface |
| `ts-z2.saved-workflows.spec.ts` (TS-Z2-01/02) | 2 | verify — compose custom → Save (shell, not run-screen) | likely pre-existing (composer/shell), predates Phase 42 |
| `ts-q.terminal-states.spec.ts` (TS-Q-02) | 1 | changed-behavior — degraded affordance (ISS-016/017) | failed-run Audit-default + degraded chrome (Group D) |
| `ts-x.timing.spec.ts` (TS-X-08) | 1 | changed-behavior — degraded affordance no-stuck-RUNNING | same as TS-Q-02 |
| `ts-j.streaming.spec.ts` (TS-J-03) | 1 | changed-behavior — running-row Live pill in the overview spine | reskinned Steps spine (42-06) |
| `ts-g.review-gates.spec.ts` (TS-G-04) | 1 | verify — pre-run Review-gates section hidden when no agents | pre-run config surface (may predate Phase 42) |
| `ts-d.composer.spec.ts` (TS-D-08) | 1 | verify — capabilities modal three sections | composer/shell, likely predates Phase 42 |
| `ts-b.selection.spec.ts` (TS-B-06) | 1 | verify — compose custom workflow view | shell, likely predates Phase 42 |
| `ts-a.auth.spec.ts` (TS-A-06) | 1 | **pre-existing stale** — asserts the retired "NEW" pill (self-documented: "left asserting the retired pill for reconciliation") | re-anchor or `test.fixme`; predates Phase 42 |

**Verification target after the pass:** `npx playwright test --project=mocked` green (or every remaining red an explicit `test.fixme` with a reason) → flip RUNUI-09 to Complete in `REQUIREMENTS.md` + `ROADMAP.md`.

## D-42-2 · F1 — structured coverage/counts aggregate (backend/additive)

**Status:** OPEN (deferred, OUT OF SCOPE — INV-3 FE-only fence). A `{coverage, counts{P0..P3}}` aggregate on `GET /runs/{id}/validation-results` (backend/additive, goldens untouched). Until then the settled agent-detail **checks card**'s coverage/verdict TEXT is a BRITTLE parse of the analyzer's `<analysis>` output via the reused `AnalysisPreview`. Flagged in code at the checks card (`frontend/src/components/results/AgentDetailPanel.tsx`). Registered 42-09 (`2c33a6ff`).

## D-42-3 · F2 — event-free `sections` extractor (backend/additive)

**Status:** OPEN (deferred, OUT OF SCOPE — INV-3 FE-only fence). An additive `sections` extractor + `/artifacts?kind=sections` (backend/additive). Until then the settled agent-detail **pages/sections card** is a BRITTLE parse of the spec agent's `<spec>` `## ` headings via the reused `SpecPreview`. Flagged in code at the pages card. Registered 42-09 (`2c33a6ff`).

## D-42-4 · ISS-037 residual advisory items (non-blocking)

**Status:** OPEN (advisory). The TodoCard-dead-code clause was closed in 42-04 (`23e05167`). The remaining Phase-31 review M/L items stay open: (M) unhandled `sendMessage` rejection strands the optimistic bubble; (M) sent attachments not rendered in transcript; (M) transcript not cleared on historical-run switch; (L) `useTabDeepLink().consume()` never called; (L) unused `agentId` prop. All non-blocking.
