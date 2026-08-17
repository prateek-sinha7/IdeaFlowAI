---
quick_id: 260812-mq5
slug: iss034-cache-cost-delta
date: 2026-08-12
issue: ISS-034
decision: OWNER-DECISIONS D2 (LOCKED)
---

# ISS-034 — surface the prompt-cache dollar delta (Analytics only, SIGNED)

## Goal

Emit the as-if-uncached counterfactual `estimated_cost_full_usd` at both run-cost sites,
strip it from the characterization goldens, roll it up in Analytics as a **legacy-safe**
`spend_full` + `metered_runs`, and render a **signed** prompt-cache delta on the Analytics
page only.

## Locked constraints (D2)

- Both cost sites, one shared `estimate_cost_usd` (INV-12) — no rate literal, no second table.
- Add the key to `_VOLATILE_STRIP_KEYS`. **Zero golden regeneration.** If a golden moves, the
  change is wrong.
- **No migration** — `token_usage` is an untyped JSON blob; every reader is a tolerant `json.loads`.
- **No per-run badge** (would reverse the KAN-83 removal + revive 3 quarantined e2e cases).
- Signed copy: positive → "saved"; negative → "cost more"; zero → render nothing.
  **Percentage primary**, dollar secondary.

## The catastrophic-number trap (must be handled)

`analytics.py:_num` coerces a missing field to `0.0`. **All 11 persisted rows predate the key**
(verified: 0 rows carry it). A naive `Σ _num(usage.get("estimated_cost_full_usd"))` totals
`$0.00` against a real `$17.69` → renders "caching cost you $17.69 more (−100%)" on day one.

Required: `r_cost_full = _num(usage.get("estimated_cost_full_usd")) or r_cost`
→ a legacy row contributes a **zero delta**, never a fabricated baseline. Plus `metered_runs`
so the UI can state how much of the window is actually measured.

## Verified line numbers at HEAD c05906c0 (analysis cites had drifted)

| Site | Analysis said | D2 said | **Actual at HEAD** |
|---|---|---|---|
| engine.py `pipeline_complete` | 2842-2855 | 2847-2854 | **2873-2880** |
| run_commands.py durable row | 2100-2115 | 2107-2114 | **2171-2178** |

Third `estimate_cost_usd` at `run_commands.py:1574` is the Concierge `chat_usage` per-message
event (FIX-233) — a DIFFERENT writer, out of scope, deliberately untouched.

## Tasks

1. `backend/agents/execution_engine/engine.py` — add `estimated_cost_full_usd` to
   `_pipeline_complete_data` after `estimated_cost_usd`.
2. `backend/app/api/run_commands.py` — add the key to the `_apply_terminal_output_columns`
   `token_usage` blob (the documented SOLE writer of these columns).
3. `backend/tests/agents/characterization/_normalize.py` — add to `_VOLATILE_STRIP_KEYS`.
4. `backend/app/api/analytics.py` — `spend_full` + `metered_runs` on `AnalyticsSummary`,
   legacy-safe fold in `_aggregate`.
5. `frontend/src/lib/api.ts` — mirror the two new fields on the `AnalyticsSummary` TS type.
6. `frontend/src/components/analytics/AnalyticsPage.tsx` — signed delta line + scope footnote.
7. Tests: new `backend/tests/agents/test_iss034_cost_full.py`; legacy-row case in
   `backend/tests/unit/test_analytics_api.py`; 4 FE cases in `AnalyticsPage.test.tsx`.

## Footnote accuracy correction

D2's mandated footnote ("Concierge chat and handoff runs are not yet metered") is **no longer
accurate** for the Concierge half. Verified at HEAD:

- Concierge **is** metered per message — `concierge.py:578-609` accumulates a `usage_total` and
  sets `ctx.usage`; `run_commands.py:1559-1583` writes a `chat_usage` run_event carrying its own
  `estimated_cost_usd` (FIX-233).
- But `chat_usage` has **zero readers** — nothing aggregates it, and Analytics reads only
  `workflow_runs.token_usage`. So chat spend is recorded and **excluded** here, not unmetered.
- Handoff: `app/services/handoff_pipeline.py` has **zero** token metering and writes **no**
  `WorkflowRun` rows — genuinely unmetered and outside the Analytics population.

Truthful wording used instead: *"Engine agent tokens only — Concierge chat is recorded per
message but not included here; handoff runs are not metered."*

## Measured baselines at c05906c0 (BEFORE)

| Check | Baseline |
|---|---|
| Characterization goldens | **10 passed** |
| Golden file SHA-256 (15 files) | recorded to scratchpad |
| `lint-imports` from `backend/` | **4 kept / 0 broken** |
| `test_wire_parity.py` | **4 F / 2 P** — PRE-EXISTING (stale wsframes goldens, dev-wide) |
| model_pricing + iss032 + analytics_api + deliverable_mimetype + sc001_gate_flag | **71 passed** |
| `AnalyticsPage.test.tsx` | **4 passed** |
| frontend `tsc --noEmit` | **2 pre-existing errors** |

## Proof obligations

- New tests seen **RED first** (legacy-row case specifically).
- Goldens **10 passed** after, with all 15 golden SHA-256 unchanged.
- Non-vacuity control: key emitted and **NOT** stripped must go **RED**.
- `SNAPSHOT_UPDATE` must not appear anywhere in the change.
