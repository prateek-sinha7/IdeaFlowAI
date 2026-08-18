# Hardcoded Agent References — Flat Inventory

Companion to `FINDINGS.md`. Every location in the codebase where agent identity/membership is
hardcoded rather than read dynamically from `backend/agents/prompts/*/AGENT.md`.

| # | Location | What's hardcoded | Used by | Intentional? | Safe to remove? |
|---|---|---|---|---|---|
| 1 | `backend/agents/registry.py:29-181` | `PIPELINE_AGENTS` dict — pipeline → ordered agent-id list, 17 pipelines, ~90 agent-id refs | Fallback path in `get_pipeline_agents()`; engine drift-check anchor; security allow-list input | **Locked** — `backend/CLAUDE.md`, Implementation Register Phase 4/7 (INV-1 carve-out) | No — still serves 3 distinct roles even though bypassed as primary path for 16/17 pipelines |
| 2 | `backend/agents/registry.py:211-216` | `REVISION_BASE_MAP` — 4 revision → base pipeline mappings | Revision pipeline resolution | Intentional | Low priority — not every base has a revision, so a naming-convention derivation wouldn't be strictly safer |
| 3 | `backend/agents/registry.py:194` | `_INTERNAL_PIPELINES = frozenset({"chat"})` | Hides internal-only pipeline from user-facing listings | Intentional, security boundary | No — this is a security decision, not a discovery convenience |
| 4 | `backend/agents/registry.py:263-265` | `_OD_ALIAS_BASE = {"od_prototype": "prototype"}` | Alias resolution for on-demand prototype variant | Intentional | Trivial, stable; no need to change |
| 5 | `backend/agents/execution_engine/engine.py:5297-5300` | `_AGENT_KIND_MAP` — 4 prototype agent-id → artifact-kind labels | Cosmetic/lineage labeling only | Intentional but organic-flavored; explicitly INV-1 exempted as cosmetic-only | Yes, low risk — could become an `AGENT.md` field (`artifact_kind`) |
| 6 | `backend/agents/execution_engine/engine.py:3733` | Default arg `agent_id: str = "prototype-build"` | Fallback default when no agent specified | Incidental | Yes, cosmetic |
| 7 | `backend/app/api/workflows.py:52` | `_KNOWN_WORKFLOW_IDS = frozenset(PIPELINE_AGENTS.keys())` | Derived from #1, not independently hardcoded | N/A (derived) | N/A |
| 8 | `backend/app/api/websocket.py:1782-1783` | `PIPELINE_AGENTS.get("ppt", [])` fallback for the `ppt`/`od_ppt` shared-agent quirk | WebSocket dispatch for `ppt` pipeline | Intentional workaround, but tracked as **open, unresolved review finding WR-01** (Phase 4) | Fixable properly — extend `AGENT.md` frontmatter to support dual `pipeline_types` |
| 9 | `frontend/src/components/home/CreationHub.tsx:15-22` | `WORKFLOWS` const — 6 curated home-page tiles | Home page workflow launcher tiles | **Explicitly locked** — Implementation Register Phase 20 (WF-DB-01, SC-001) | No — deliberately curated subset; a dynamic sibling (`WorkflowCatalog`) already exists alongside it for the full list |
| 10 | `frontend/src/data/hooks.ts` (8 entries) | `compatible_agents: [...]` agent-id string literals per hook | `AgentsPopup.tsx`, `LibraryPage.tsx` compatibility filtering | **Organic — no register/ADR reference found** | Needs a drift-validation test, not removal; some IDs are stale/broken today |
| 11 | `frontend/src/data/skills.ts` (245 occurrences) | `compatible_agents: [...]` agent-id string literals per skill | `AgentsPopup.tsx`, `LibraryPage.tsx` compatibility filtering | **Organic — no register/ADR reference found** | Same as #10 — this is the largest concentration of stale/unvalidated agent-id references in the codebase |

## Confirmed stale agent IDs (bug, not a locked decision)

These IDs appear in `hooks.ts` / `skills.ts` `compatible_agents` arrays but do **not** exist as real
agent folders under `backend/agents/prompts/`:

| Stale ID referenced in frontend data | Real agent ID on disk |
|---|---|
| `html-prototype-builder` | `prototype-build` |
| `prototype-polisher` | *(no direct equivalent found — verify against current `backend/agents/prompts/` listing)* |
| `requirements-analyst` | `domain-analyst` |
| `ppt-slide-architect` | `od-ppt-composer` |

## What is NOT hardcoded (dynamic, working correctly)

| Area | Mechanism |
|---|---|
| Per-agent metadata (name, role, model, tools, guardrails, icon, duration, description, produces/consumes, gate, injects) | Parsed live from `AGENT.md` frontmatter in each `backend/agents/prompts/{agent-id}/` folder |
| `GET /api/agents/library` | Fully folder-driven, no per-agent Python hardcoding |
| `GET /api/agents/pipelines/{type}` | Fully folder-driven |
| `get_pipeline_agents()` primary path (16 of 17 pipelines) | Dynamic scan via `list_agent_ids()`, keyed on `AGENT.md` `pipeline_type`/`order` frontmatter |
| `GET /api/workflows` | Dynamic — replaced an earlier hardcoded workflow-type list per ISS-015 |
