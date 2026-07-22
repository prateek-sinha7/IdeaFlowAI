---
quick_id: 260705-vqv
date: 2026-07-05
type: quick
mode: docs-only
branch: new-workflow-engine
status: complete
files_modified:
  - .planning/IMPLEMENTATION-REGISTER.md
commits:
  - 0091b12c  # docs(register): add Phase 26 — cost/caching/cache-token accounting & pricing single-source
---

# Quick 260705-vqv: add Phase 26 to IMPLEMENTATION-REGISTER.md

Appended a single new `## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)` section to the END of `.planning/IMPLEMENTATION-REGISTER.md`, a structural peer of the existing Phase 25 section, documenting this session's 5 cost/caching/pricing quick tasks (p10, t2x, ttk, uvs, ed8). Pointer-first, code-free (backticked paths/symbols, `→` pointers, no pasted code).

## What was built

A byte-append (Phase 1-25 untouched) with a leading `---` separator and Phase 25's exact shape:
- **Bold lead block:** `**Folder:** … · **Status:** … · **Plans:** …` + `**Requirements delivered:**` + `**Driver:**` + `**One-line outcome:**`.
- `### The 5 quick tasks` — one bullet per p10/t2x/ttk/uvs/ed8, each citing its FIX/ISS id and final docs commit.
- `### Where the code lives (as-built)` — pointers only (model_factory, deep_agent_runner, config, model_pricing, model_catalog, engine, websocket, _normalize, FE TokenUsageSummary/useWorkflow/types).
- `### Key locked decisions (do NOT contradict)` — the load-bearing subsection; all five: (a) pricing derives from the single `model_catalog.py` source (INV-12, ed8 restore), (b) Bedrock-only caching via `_BedrockCachePointsMiddleware`, (c) cost math subtracts cached tokens (no double-count), (d) thinking enable-only default OFF, (e) +10% regional premium for eu./us./apac.
- `### Invariants & verification` — INV-3 (goldens byte/event-identical; cost+model_id stripped; 4 additive cache keys), INV-12 (one `estimate_cost_usd`, single source restored by ed8), INV-13 (deepagents middleware/kwargs only), SC-001 (isinstance/model_id dispatch) + evidence tallies.
- `### Known follow-ups (out of scope)` — ISS-033 (direct-call agents bypass runner: `smart_planner.py:389`, `clarify_engine.py:492-493`, handoff agents), ISS-034 (dollar-savings via `estimated_cost_full_usd`), deferred live Bedrock `cache_read>0` pass, adjacent er8 (FIX-033) + d4v (FIX-029).

Every claim was verified against the 5 task SUMMARY.md + VERIFICATION.md, `.planning/FIX-REGISTER.md` (FIX-034..038), and `.planning/ISSUES-REGISTER.md` (ISS-032 RESOLVED / ISS-033 OPEN / ISS-034 OPEN). Cited commit hashes were resolved against `git log`; the ed8 marker `102135ed` is its final orchestrator docs commit.

## Deviations from Plan

None — plan executed exactly as written. No code, no tests to run (docs-only). No STATE.md touched (orchestrator owns the STATE row).

## Exit gate results

- `grep -n "^## Phase 26" .planning/IMPLEMENTATION-REGISTER.md` → `2549:## Phase 26 — Cost, Caching, Cache-Token Accounting & Pricing Single-Source (post-milestone)`.
- `grep -cE "^### (The 5 quick tasks|Where the code lives|Key locked decisions|Invariants & verification|Known follow-ups)" …` → 12 (Phase 26's 5 peers added atop the file's existing matches).
- `git show --stat HEAD` → touches ONLY `.planning/IMPLEMENTATION-REGISTER.md` (1 file, 48 insertions).
- `git log -1 --format='%b'` → empty (no Co-Authored-By / Claude-Session trailer).
- All 5 task ids (p10, t2x, ttk, uvs, ed8) present.

## Commit

- `0091b12c` docs(register): add Phase 26 — cost/caching/cache-token accounting & pricing single-source (register only; SUMMARY/PLAN/STATE left for the orchestrator's final docs commit).

## Self-Check: PASSED

- FOUND: `.planning/IMPLEMENTATION-REGISTER.md` Phase 26 section (line 2549).
- FOUND commit `0091b12c` in `git log`.
- Scope confirmed: only `.planning/IMPLEMENTATION-REGISTER.md` modified by the register commit.
