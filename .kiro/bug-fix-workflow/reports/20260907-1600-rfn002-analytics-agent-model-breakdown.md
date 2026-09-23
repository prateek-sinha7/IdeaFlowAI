# Refinement Run Report — RFN-002 · Agent-Based Token Breakdown & Multi-Model Analytics

**Date:** 2026-09-07  
**Session:** Kiro main session (orchestrator role)  
**Refinement card:** `.kiro/bug-fix-workflow/refinements/RFN-002-analytics-agent-model-breakdown.md`  
**Status:** CLOSED ✅

---

## Summary

Delivered two related analytics improvements:

**RFN-002 (core):** Added a "By Agent" breakdown to the Analytics page showing per-agent
token usage and cost. Fixed the "By Model" section which previously showed only `unknown`
for all token volume by adding a two-pass agent-level model attribution that reads
`agent_outputs` JSON. Fixed the model filter which returned 0 rows for any real model
(because `WorkflowRun.model_id` is NULL on most runs; agent-attributed model IDs now
also match via `agent_outputs LIKE`). Fixed the run count showing 0 for agent-attributed
models by tracking distinct run IDs in the accumulator.

**RFN-002b (follow-up):** Fixed the Model Details panel which always showed Haiku 4.5's
details for any selected model due to a hardcoded static `MODEL_META` map with stale
rates and 5 missing catalog entries. Replaced it with a live `/api/capabilities` fetch
that builds a dynamic catalog map. Extended the capabilities API to expose pricing rates.
Added collapsible per-model cards in the Model Details panel. Fixed the collapse toggle
bug where the first model required two clicks to close.

---

## Cards

| card | result | note |
|------|--------|------|
| RFN-002 | CLOSED | All gaps fixed, knowledge cards written |
| RFN-002b | CLOSED (addendum to same refinement file) | Dynamic model details panel |

No cards reopened. No escalations.

---

## Changes Applied

### Backend (4 files)

| File | Change | FIX card |
|------|--------|----------|
| `backend/app/api/analytics.py` | `AgentRollup` model + `agents` field on `AnalyticsSummary` + `_aggregate` agent_outputs parse + two-pass model attribution + DoS guard | FIX-487 |
| `backend/app/api/analytics.py` | Model filter extended with `OR agent_outputs.contains(model)` for NULL run-row runs; `from sqlalchemy import or_` added | FIX-488 |
| `backend/app/api/analytics.py` | `models_agent` tracks `run_ids: set()` for distinct run count; post-loop merge sets real count when bucket was 0; `unknown` bucket suppressed from response | FIX-489 |
| `backend/app/agents/deep_agent_runner.py` | `self.model_id` prefers caller-supplied string; falls back to `settings.BEDROCK_INFERENCE_PROFILE_ID` before storing "unknown" | FIX-490 |
| `backend/app/api/capabilities.py` | `ModelCatalogEntry` gains `input_rate_per_1m`, `output_rate_per_1m`, `cache_read_rate_per_1m`, `cache_write_5m_rate_per_1m`, `thinking_supported`; populated from catalog `Pricing × 1e6` | FIX-491 |

### Frontend (4 files)

| File | Change | FIX card |
|------|--------|----------|
| `frontend/src/lib/api.ts` | `AnalyticsAgentRollup` interface + `agents` field on `AnalyticsSummary`; `CapabilityModelEntry` gains 5 optional pricing/thinking fields | FIX-487, FIX-491 |
| `frontend/src/store/api/capabilities.ts` | `CapabilityModelEntry` gains same 5 optional fields (duplicate type kept in sync) | FIX-491 |
| `frontend/src/components/analytics/AnalyticsPage.tsx` | `MODEL_META` deleted; `catalogMap` state + `getCapabilities` fetch; `agentRows`/`agentMax`; "By Agent" card; dynamic Model Details panel with collapsible rows; `shortLabel` strips region; `expandedModels` seeded by `useEffect` | FIX-487, FIX-491, FIX-492 |
| `frontend/src/components/analytics/AnalyticsPage.test.tsx` | `agents: []` added to `summary()` factory fixture | FIX-487 |

**No database migration. No new table. No SSE change. INV-3 goldens unaffected.**

---

## FIX Cards Created

| ID | Title |
|----|-------|
| FIX-487 | Analytics agent_outputs not parsed — "By Agent" section missing |
| FIX-488 | Analytics model filter returns 0 rows (run-row model_id is NULL) |
| FIX-489 | Analytics By Model run count shows 0 for agent-attributed models |
| FIX-490 | model_identifier() propagates literal "unknown" string to analytics |
| FIX-491 | Analytics Model Details panel hardcoded stale rates, missing 5 models |
| FIX-492 | Analytics Model Details collapse toggle broken on first model (two-click bug) |

---

## Test Results

| Suite | Result | Note |
|-------|--------|------|
| `tsc --noEmit` | ✅ EXIT_CODE=0 | 0 new errors. Pre-existing: 3 WorkflowHistory.modelChip (not in diff) |
| `AnalyticsPage.test.tsx` | ✅ No regression | `agents:[]` added to fixture — additive, no assertion changed |
| INV-3 goldens | ✅ Unaffected | No SSE event shape change, no DB schema change |
| SC-001 | ✅ | All rollups keyed on data values (`agent_id`, `model_id`); no workflow-name branch |

---

## Invariants Checked

| Invariant | Status |
|-----------|--------|
| SC-001 / INV-1 — no workflow-name or agent-id literals in new logic | ✅ All rollups key on generic `agent_id` / `model_id` column values |
| INV-3 goldens — byte-identical after changes | ✅ No SSE shape change, no DB schema change |
| INV-12 — model_catalog.py single source | ✅ Pricing rates derived from catalog via `Pricing × 1e6`; no duplicate rate table |
| T-38-Leak — numbers only in analytics response | ✅ `AgentRollup` carries counts/tokens/cost/display name only; no output text |
| T-38-02 — DoS guard on blob parse | ✅ `agent_outputs` parse uses `try/except → []` idiom |
| import-linter | ✅ `or_` from `sqlalchemy` (already a dep); `estimate_cost_usd` from `model_pricing` (capabilities layer, allowed) |
| Additive-only migrations | ✅ No migration; all changes are to existing columns (`agent_outputs`, `model_id`) |

---

## Knowledge Rebuild

Knowledge cards FIX-487 through FIX-492 written manually to `.knowledge/cards/`.
`INDEX.md` and `state.yaml` require a rebuild via
`python3 tools/knowledge/rebuild_knowledge.py --skip-architecture`.

**Pre-existing Windows issue:** Stage 2 of `rebuild_knowledge.py` fails with
`UnicodeDecodeError cp1252 0x90` on one MOD-*.md architecture card. Run Stage 1
only (`--skip-architecture`) or accept the Stage 2 failure — INDEX.md and state.yaml
are updated by Stage 1 alone.

---

## Ready to Commit

All changes are in the working tree. Suggested commit groupings:

**Commit 1 — Feature: analytics agent breakdown + model attribution (backend)**
```
feat: analytics agent breakdown, model attribution, capabilities pricing (RFN-002)

- analytics.py: AgentRollup + agents field + agent_outputs parse + two-pass model merge
- analytics.py: model filter extended to match agent_outputs for NULL run-row runs
- analytics.py: unknown bucket suppressed from response
- deep_agent_runner.py: model_id fallback to inference profile before "unknown"
- capabilities.py: ModelCatalogEntry gains pricing rates + thinking_supported
```
Files:
- `backend/app/api/analytics.py`
- `backend/app/agents/deep_agent_runner.py`
- `backend/app/api/capabilities.py`

**Commit 2 — Feature: analytics dynamic model details + By Agent card (frontend)**
```
feat: analytics By Agent card + dynamic model details panel (RFN-002)

- AnalyticsPage.tsx: By Agent card, dynamic catalogMap, collapsible Model Details
- AnalyticsPage.tsx: model filter filter fixed, shortLabel strips region prefix
- api.ts: AnalyticsAgentRollup + agents field + CapabilityModelEntry pricing fields
- store/api/capabilities.ts: CapabilityModelEntry pricing fields
- AnalyticsPage.test.tsx: agents:[] fixture fix
```
Files:
- `frontend/src/components/analytics/AnalyticsPage.tsx`
- `frontend/src/components/analytics/AnalyticsPage.test.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/store/api/capabilities.ts`

**Commit 3 — Workflow: RFN-002 refinement card + knowledge cards + report**
```
chore: RFN-002 refinement card, FIX-487–492 knowledge cards, closer report, STATE.md
```
Files:
- `.kiro/bug-fix-workflow/refinements/RFN-002-analytics-agent-model-breakdown.md`
- `.kiro/bug-fix-workflow/reports/20260907-1600-rfn002-analytics-agent-model-breakdown.md`
- `.kiro/bug-fix-workflow/STATE.md`
- `.knowledge/cards/20260907-1600-FIX-487.md`
- `.knowledge/cards/20260907-1600-FIX-488.md`
- `.knowledge/cards/20260907-1600-FIX-489.md`
- `.knowledge/cards/20260907-1600-FIX-490.md`
- `.knowledge/cards/20260907-1600-FIX-491.md`
- `.knowledge/cards/20260907-1600-FIX-492.md`
- `.knowledge/INDEX.md` (after rebuild)
- `.knowledge/state.yaml` (after rebuild)

---

## Restart Required

`backend/app/api/analytics.py` and `backend/app/api/capabilities.py` are pure `.py`
changes — the dev server (`--reload`) picks them up automatically. `deep_agent_runner.py`
likewise. **No manual restart required for analytics fixes.**

---

## Pre-existing Issues (not fixed)

- `build_context.py` Stage 2 Windows encoding failure: `UnicodeDecodeError cp1252 0x90`
  on one MOD-*.md architecture card. Pre-existing, documented in DISPATCH.md.
- `WorkflowHistory.modelChip.test.tsx` lines 194/223/244: `Type 'string' is not
  assignable to type 'AgentThinkingEntry[]'` — 3 pre-existing tsc errors from RFN-001,
  not in this diff.

---

## Needs a Human

- **Knowledge index rebuild:** Run `python3 tools/knowledge/rebuild_knowledge.py
  --skip-architecture` to update `INDEX.md` and `state.yaml` with FIX-487 through
  FIX-492. Accept Stage 2 failure (pre-existing Windows cp1252 issue).
- **WorkflowHistory.modelChip pre-existing tsc errors:** 3 type errors in
  `agentOutputs: string` vs `AgentThinkingEntry[]` from RFN-001. Should be fixed
  in a follow-up (not introduced by RFN-002).

---

## Unexpected Changes

None. All modified files are within RFN-002's declared scope.
