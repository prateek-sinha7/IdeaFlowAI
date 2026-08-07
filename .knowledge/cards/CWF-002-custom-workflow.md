---
id: CWF-002-custom-workflow
type: bug
status: open
area: [sse, agents, runtime]
summary: >-
  Per-agent model actually used is never persisted or queryable
source: .planning/CUSTOM-WORKFLOW-QA-BUG-LOG.md#cwf-002
campaign: custom-workflow
---

## CWF-002 — Per-agent model actually used is never persisted or queryable
> **✅ FIXED + LIVE-PROVEN 2026-07-18** — quick `260718-rf7`, commits `8e0af54f`/`9c6ef0f4`/`8251081d` (grounded, plan-checked + verifier-passed 6/6). (a) `agent_complete` now carries the resolved `model_id` (stripped by the existing `_VOLATILE_STRIP_KEYS` entry → 5 goldens byte-identical); (b) `wr.model_id` persisted before the cost line (non-circular cost); (c) exposed in `runs.py`. Offline: 34 unit + 5 goldens byte-identical + lint-imports 4/0. **LIVE-PROVEN** (restarted backend): a completed 1-agent Haiku run (`84472499`) shows `agent_complete.model_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"` — the per-agent model is now queryable (the exact gap that blocked verifying "did the agent run on Haiku"). feat/ui-2, trailer-free, NOT pushed.
- **Surface:** engine event emission · run record (`GET /api/runs/{id}`, `/summary`, `/events`) · DB · cost analytics
- **Severity:** minor / observability. Not a functional failure — but it makes "which model did this run use?" unverifiable, which blocked QA verification of the Haiku/Sonnet selection.
- **Found:** 2026-07-18 · trying to verify a completed run executed on Haiku 4.5.
- **Root cause (same investigation):** the effective model is resolved at runtime (`ModelResolver`, `engine.py:1621-1627`) but **never emitted or persisted**: `agent_start` payload (`engine.py:2931-2934`) and `agent_complete` payload (`engine.py:3684-3693`) carry no model; `_SUMMARY_SAFE_AGENT_KEYS` (`runs.py:995-1007`) + `WorkflowRunResponse` (`runs.py:88`) have no model field; `WorkflowRun.model_id` column exists (`workflow.py:37`) but has **zero assignment sites** (never written on the REST launch path). Cost `estimated_cost_usd` is computed with `wr.model_id or BEDROCK_INFERENCE_PROFILE_ID` (`run_commands.py:1464-1471`) — since `model_id` is NULL, cost is **always priced at the default profile regardless of the real model** (circular; cannot confirm the model). The model id is logged only at `logger.debug` (`model_factory.py:61,93`), off at INFO.
- **Impact / proxy:** verifying a run's model requires DEBUG logging at launch, or inference from the resolution chain (no overrides ⇒ default). For run `3c958122`, cost $0.0152 for 6903 tokens is consistent with Haiku (Sonnet would be ~$0.041) AND with the selection sent — strong indication, not a recorded fact.
- **Fix (proposed, enhancement):** set `wr.model_id` at mint; add `model` to the `agent_complete` payload + `_SUMMARY_SAFE_AGENT_KEYS`. Then cost is non-circular and the model is queryable. Route through gsd-quick if desired.
