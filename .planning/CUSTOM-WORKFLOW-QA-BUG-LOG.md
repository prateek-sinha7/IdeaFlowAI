# Custom Workflow Composer — QA Bug Log

> Append-only issue log for the custom-workflow Composer variation QA (Simple + Canvas views).
> Part of the SSE-QA live-Bedrock campaign arc. Sibling of `SSE-QA-BUG-LOG.md`.
>
> **Protocol:** every issue gets ONE max-effort root-cause investigation agent that reads
> `IMPLEMENTATION-REGISTER.md` for the relevant area, root-causes to file:line (no-hack),
> BEFORE any fix. Fixes route through `gsd-quick`. Entries are append-only.
>
> **Bug id scheme:** `CWF-NNN`. Status: `OPEN` → `INVESTIGATING` → `ROOT-CAUSED` →
> `FIX-PLANNED` → `FIXED` → `LIVE-PROVEN`.

## Index
| ID | Title | Surface | Severity | Status |
|----|-------|---------|----------|--------|
| CWF-001 | Consumer-before-producer agent order saves+launches, aborts at runtime ("DAG unsatisfiable"), and the failed run is mislabeled `completed` | Composer / resolver / run-status | major | **FIXED · D1 LIVE-PROVEN** (D2 260718-p8m offline; D1 260718-puj) |
| CWF-002 | The per-agent model actually used is never persisted or queryable (model_id never written; cost estimate circular) → cannot verify which model a run used | Engine / run record / analytics | minor (observability) | **FIXED** (260718-rf7, offline) |

> Scope: compose / configure / save / model-selection (Simple + Canvas, Sonnet 4.5 & Haiku 4.5)
> tested **35/35 + 10/10 PASS**; a correctly-ordered custom workflow **runs to completion**
> (run `3c958122`: both agents completed, 4568-char markdown deliverable, review gate paused +
> resumed, pipeline_complete). CWF-001/002 are on the run path. See `CUSTOM-WORKFLOW-QA-TEST-SHEET.md`.

---

## CWF-001 — Consumer-before-producer order runs unsatisfiable at runtime; no compose-time guard; failed run shows `completed`
> **✅ FIXED 2026-07-18 (offline-proven; live proof pending).** Both defects closed via two grounded gsd-quick tasks (each read the full IMPLEMENTATION-REGISTER.md, plan-checked + verifier-passed):
> - **D2** — quick `260718-p8m`, commits `32c6220a`/`a0c98b8f`: launch driver `_drive_launch_to_queue` now tracks the generic `error` + `pipeline_failed` events and its terminal status is fail-safe (reconciled toward the LOCK-B revision twin) → an unsatisfiable run now shows `failed`, not `completed`.
> - **D1** — quick `260718-puj`, commits `8446a44b`/`c50afe8f`/`17114dac`: NEW additive `WorkflowResolver.presort()` (order-independent; REUSES `_detect_cycles`/`_topological_sort`; `validate()`/`:119`/`:138` byte-UNCHANGED — candidate b) + app-layer `composition_order.py`; producer-first pre-sort + satisfiability guard at save + launch (custom branch only), genuinely-unsatisfiable → 422 naming the missing edge; surfaced in `ComposerPage.tsx`.
> - **Verification:** backend 91 pass, 5 characterization goldens byte/event-identical, FE ComposerPage vitest 12 + tsc clean, mocked composer-run e2e 2/0, lint-imports 4/0. INV-1/SC-001/INV-3/INV-5/Q3 all held; kernel `validate()` untouched. feat/ui-2, trailer-free, NOT pushed. **D1 LIVE-PROVEN 2026-07-18** (backend restarted to load the fix): a mis-ordered-but-satisfiable save `[swot-analyst, market-research-agent]` → 201 persisted producer-first `[market-research-agent, swot-analyst]`; a genuinely-unsatisfiable `[swot-analyst]` alone → **422 at BOTH save and launch** (no run minted), naming the missing producer. (D2's fail-safe status is offline-proven; D1 now prevents the mislabel path at the front door, so D2 is defense-in-depth.)
- **Surface:** Composer reorder/save/launch · `WorkflowResolver` (produces/consumes DAG) · run-status lifecycle
- **Severity:** major (fails safe — 0 agents run — but silently mislabels a failure as success in the composed-workflow flow, corrupting run history/analytics/QA).
- **Found:** 2026-07-18 · live-Bedrock custom-workflow QA. Two independent defects (D1 + D2).
- **Observed:** composed `market-research-agent` + `swot-analyst` (swot consumes market-research), **reordered** so saved `agent_ids = ["swot-analyst","market-research-agent"]`. Composer allowed it, saved (201), launched (200), no warning. Run `8061cc20` → `workflow_validated` → `error`: "Workflow DAG is unsatisfiable: Agent 'swot-analyst' consumes 'market-research-agent' but no upstream agent produces it." 0 agents ran, empty output, final status **`completed`**. Control (correct order, run `3c958122`) completes fine.
- **Root cause (investigation agent — read IMPLEMENTATION-REGISTER.md + traced compiler/resolver/composer/driver; all file:line spot-checked):**
  - **D1 — order-dependent satisfiability + no pre-runtime guard.** `WorkflowResolver` satisfiability is **declared-order-dependent**: `resolver.py:119` counts a producer only if `idx < consumer_idx`; empty → the error at `resolver.py:128-131`. Yet the engine **executes in topo order anyway** (`ordered_agents = validation.dag`, `engine.py:1600`) — so declared order gates *satisfiability* but not *execution*: the inconsistency. The resolver runs in exactly ONE place — `engine.execute` Step 1 (`engine.py:1572`, error yielded `:1589-1598`), i.e. AFTER the run is minted. Every earlier layer skips produces/consumes: compiler `_validate_dag` (`compiler.py:860-904`) checks only `depends_on` cycles + dup ids (custom steps carry no `depends_on`); save `POST /api/user-workflows` (`user_workflows.py:247-335`) validates allow-list/model/selections only + persists reordered `agent_ids` verbatim (`:322`); launch `POST /api/runs` mints `status="running"` at `run_commands.py:1234` before any DAG check; `ComposerPage.tsx` `moveAgent`/`handleDrop` (`:146-182`) reorder with zero validation + send reordered ids (`:256`/`:291`). No `produces`/`consumes`/`resolver` token anywhere in the composer.
  - **D2 — failed run mislabeled `completed`.** The driver's status ladder (`run_commands.py:1358-1442`) tracks only `agent_error`/`pipeline_complete`/`pipeline_cancelled`/`degraded`; a generic `error` event is forwarded to SSE but not tracked (`any_agent_errored` stays False), so the run falls to the `else` → `wr.status = "completed"` (`:1441-1442`). **The ~4.5s cancel is NOT the cause** (cancel handler `:282-303` only `event.set()`, never writes status; the DAG error + `completed` commit happen at t≈0). A cancel-free repro yields `completed` identically.
- **Fix (proposed; route through gsd-quick):**
  - **D2 (mandatory):** in `_drive_launch_to_queue` treat a terminal non-recoverable `error` (`code=="workflow_unsatisfiable"` / `recoverable is False`) as failure → `wr.status="failed"` + `wr.error` instead of the `completed` else (`run_commands.py:1358-1442`). Single file; no WS twin (websocket.py deleted Phase 44).
  - **D1 (primary):** add order-independent produces/consumes validation at save + launch (reuse resolver graph logic on the composed `AgentSpec`s) and **topologically pre-sort `agent_ids` producer-first** before mint; reject a genuinely-unsatisfiable set pre-mint with a clear message; surface edges/auto-order in `ComposerPage.tsx`. Candidate (b) preferred over making the resolver order-independent (candidate a) — (a) changes the multi-producer tie-break (`resolver.py:134-138`) and risks the 5 characterization goldens + `test_workflow_resolver.py`. SC-001-safe (no workflow-name literal).
- **Verification:** repro deterministic (consumer before producer → DAG error, status completed). Fail-before/pass-after per D1/D2 above.

## CWF-002 — Per-agent model actually used is never persisted or queryable
- **Surface:** engine event emission · run record (`GET /api/runs/{id}`, `/summary`, `/events`) · DB · cost analytics
- **Severity:** minor / observability. Not a functional failure — but it makes "which model did this run use?" unverifiable, which blocked QA verification of the Haiku/Sonnet selection.
- **Found:** 2026-07-18 · trying to verify a completed run executed on Haiku 4.5.
- **Root cause (same investigation):** the effective model is resolved at runtime (`ModelResolver`, `engine.py:1621-1627`) but **never emitted or persisted**: `agent_start` payload (`engine.py:2931-2934`) and `agent_complete` payload (`engine.py:3684-3693`) carry no model; `_SUMMARY_SAFE_AGENT_KEYS` (`runs.py:995-1007`) + `WorkflowRunResponse` (`runs.py:88`) have no model field; `WorkflowRun.model_id` column exists (`workflow.py:37`) but has **zero assignment sites** (never written on the REST launch path). Cost `estimated_cost_usd` is computed with `wr.model_id or BEDROCK_INFERENCE_PROFILE_ID` (`run_commands.py:1464-1471`) — since `model_id` is NULL, cost is **always priced at the default profile regardless of the real model** (circular; cannot confirm the model). The model id is logged only at `logger.debug` (`model_factory.py:61,93`), off at INFO.
- **Impact / proxy:** verifying a run's model requires DEBUG logging at launch, or inference from the resolution chain (no overrides ⇒ default). For run `3c958122`, cost $0.0152 for 6903 tokens is consistent with Haiku (Sonnet would be ~$0.041) AND with the selection sent — strong indication, not a recorded fact.
- **Fix (proposed, enhancement):** set `wr.model_id` at mint; add `model` to the `agent_complete` payload + `_SUMMARY_SAFE_AGENT_KEYS`. Then cost is non-circular and the model is queryable. Route through gsd-quick if desired.
