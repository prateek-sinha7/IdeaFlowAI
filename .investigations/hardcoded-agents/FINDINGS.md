# 🔍 Analysis: Hardcoded agents vs. dynamic folder-based discovery

**Type:** Architecture question + Code quality
**Question:** Is the project using hardcoded agent lists/definitions/registries in the backend instead of dynamically discovering agents from the folder structure? Was this intentional or organic? Does hardcoding buy anything? Is the current folder structure rich enough to go fully dynamic?
**Scope:** `backend/agents/registry.py`, `backend/agents/prompts/*/AGENT.md` (87 agent folders), `backend/agents/execution_engine/engine.py`, `backend/app/api/workflows.py`, `backend/app/api/websocket.py`, `frontend/src/data/hooks.ts`, `frontend/src/data/skills.ts`, `frontend/src/components/home/CreationHub.tsx`, plus full reads of `.planning/IMPLEMENTATION-REGISTER.md`, `.planning/ISSUES-REGISTER.md`, `.planning/FIX-REGISTER.md`, `.planning/ROADMAP.md`, and `backend/CLAUDE.md`.

---

## 1. Summary (TL;DR)

The suspicion is **partially right**. Per-agent *metadata* is already 100% dynamic — every `AGENT.md` file under `backend/agents/prompts/{agent-id}/` is parsed off disk by the loader, and the `/api/agents/library` and `/api/agents/pipelines/{type}` endpoints the frontend was just wired up to (commit `e63aa9f2`) are entirely folder-driven with zero per-agent hardcoding. What **is** hardcoded is *pipeline membership* — a single dict `PIPELINE_AGENTS` in `backend/agents/registry.py:29-181` (~90 agent-id references across 17 pipelines). This is a **documented, locked architectural decision** (`backend/CLAUDE.md`, Implementation Register Phase 4/6/7, INV-1 carve-out), not an oversight. Crucially, the runtime path `get_pipeline_agents()` already *prefers* a fully dynamic folder scan (`list_agent_ids()`, keyed on each `AGENT.md`'s `pipeline_type`/`order` frontmatter) and only falls back to `PIPELINE_AGENTS` when that scan comes back empty — which today only happens for one pipeline (`ppt`, because its agents declare `pipeline_type: od_ppt`).

The one **genuine, unintentional bug** found is on the frontend: `compatible_agents` arrays in `frontend/src/data/hooks.ts` and `frontend/src/data/skills.ts` contain agent-id string literals that have drifted stale against the real backend agent-id set (e.g. `"html-prototype-builder"`, `"prototype-polisher"`, `"requirements-analyst"`, `"ppt-slide-architect"` — none of these exist; real IDs are `prototype-build`, `domain-analyst`, `od-ppt-composer`, etc.). This data is consumed at runtime (`AgentsPopup.tsx`'s `.compatible_agents.includes(agent.id)` filter, `LibraryPage.tsx`) so these entries silently never match anything. No register entry documents this data as intentional — it appears to be organic technical debt, and it's a live demonstration of exactly the failure mode that dynamic discovery + validation is meant to prevent.

---

## 2. Root Cause / Key Finding

```
File: backend/agents/registry.py
Lines: 29-181
Code:  PIPELINE_AGENTS: dict[str, list[str]] = { "prototype": [...], "od_prototype": [...], ... }  # 17 pipelines, ~90 agent-id refs
Why:   Canonical pipeline → ordered agent-id list. Documented in backend/CLAUDE.md as the source of
       truth for "which agents belong to a pipeline (membership/order)". Locked per Implementation
       Register Phase 7 INV-1 carve-out (see §4). NOT the live path for 16/17 pipelines — those are
       served by list_agent_ids() scanning AGENT.md frontmatter. Used as: (a) fallback when the
       dynamic scan returns empty (currently only the `ppt` pipeline), (b) the engine's own
       drift-check anchor (raises RuntimeError if registry and manifest disagree), (c) a security
       allow-list input for _KNOWN_WORKFLOW_IDS.
```

```
File: frontend/src/data/hooks.ts, frontend/src/data/skills.ts
Lines: hooks.ts (8 entries), skills.ts (245 compatible_agents occurrences)
Code:  compatible_agents: ["html-prototype-builder", "prototype-polisher", ...]
Why:   Organic hardcoding, no register/ADR reference found. IDs have drifted from the real agent-id
       set on disk. This is the one finding that is an actual bug, not a locked decision.
```

---

## 3. Trace / Evidence

```
Pipeline start → get_pipeline_agents(pipeline_type)
              → list_agent_ids(pipeline_type)   [dynamic: scans backend/agents/prompts/*/AGENT.md,
                                                  filters by frontmatter `pipeline_type`, sorts by
                                                  `order`, raises on duplicate order]
              → if non-empty: RETURN dynamic result (16/17 pipelines take this path)
              → if empty (only `ppt`, because its agents declare pipeline_type: od_ppt):
                    fall back to PIPELINE_AGENTS["ppt"]  [static dict]
              → engine.py:1466-1477 asserts registry and manifest agree; raises RuntimeError on drift
```

```
Frontend agent picker → AgentsPopup.tsx filters via `.compatible_agents.includes(agent.id)`
                       → compatible_agents sourced from hardcoded arrays in hooks.ts / skills.ts
                       → some IDs (e.g. "html-prototype-builder") never match any real agent.id
                       → [SILENT FAILURE] those hook/skill entries never surface as compatible
```

---

## 4. Related Decisions & Phase Context

| Phase | Decision | Relevance |
|---|---|---|
| Phase 4 | `get_pipeline_agents("ppt")` returns `[]` because ppt agents declare `pipeline_type: od_ppt`; coverage assertions fall back to `PIPELINE_AGENTS["ppt"]`. Documented as the root of **open review finding WR-01**. | Confirms item is a known, still-open wart — not silently accidental, but also not resolved. |
| Phase 7 | INV-1 carve-out: "legitimate non-kernel `pipeline_type`/name refs (registry `REVISION_BASE_MAP`/`PIPELINE_AGENTS`, ...) are RETAINED; the grep gates are kernel-scoped." | `PIPELINE_AGENTS` explicitly exempted from a repo-wide grep-gate that would otherwise flag it — i.e. reviewed and deliberately kept. |
| Phase 20 | WF-DB-01: "The hardcoded `WORKFLOWS` module-const is NOT present in the catalog... `CreationHub.tsx`'s own `WORKFLOWS` const is untouched (home tiles still exist)." SC-001: "launchability keys on a DECLARED flag, never a name list (LOCKED)." | The 6-tile home `WORKFLOWS` const in `CreationHub.tsx` is a **separately locked** decision — curated home-page tiles, not agent membership. A dynamic sibling (`WorkflowCatalog`) already exists alongside it. |
| Issues Register ISS-015 | "No generic pipeline-type picker... was BY DESIGN; now SHIPPED in Phase 20... Guardrail (REJECTED hack): if ever built, a manifest-driven picker MUST read `GET /api/workflows`... NOT a hardcoded dropdown." Disposition: SHIPPED. | Confirms the project has already fixed one prior hardcoding instance (workflow-type dropdown) by moving to a dynamic `GET /api/workflows` endpoint — same pattern this investigation would extend. |
| `backend/CLAUDE.md` | "the registry says *which* agents belong to a pipeline (membership/order); the manifest (`workflow.yaml`) says *how* they run." | States the intended division of responsibility between `registry.py` and per-agent manifests — worth a refresh, since `list_agent_ids()` now derives membership dynamically for most pipelines, partially superseding this framing. |

No register entry (Implementation, Issues, or Fix) documents `frontend/src/data/hooks.ts` / `skills.ts` `compatible_agents` as an intentional design choice.

---

## 5. What Is Working Correctly

- ✅ Per-agent metadata (`id`, `name`, `role`, `pipeline_type`, `order`, `max_tokens`, `tools`, `guardrails`, `icon`, `estimated_duration`, `description`, `produces`/`consumes`, `gate`, `injects`, `model`) is fully dynamic, parsed from `AGENT.md` frontmatter on disk — nothing duplicated in Python.
- ✅ `get_pipeline_agents()` already prefers the dynamic scan (`list_agent_ids()`) for 16 of 17 pipelines; `PIPELINE_AGENTS` is a fallback, not the primary path, for almost all traffic today.
- ✅ The engine actively guards against registry/manifest drift on every run (`engine.py:1466-1477`, raises `RuntimeError` on mismatch) — a forgotten registry edit doesn't silently ship, it fails loudly the next time that pipeline executes.
- ✅ `GET /api/workflows` was explicitly built to replace an earlier hardcoded workflow-type list (ISS-015) — precedent for this exact class of fix already exists and shipped successfully.
- ✅ Security-relevant hardcodes (`_INTERNAL_PIPELINES`, `_KNOWN_WORKFLOW_IDS`, `allowed_custom_agent_ids`) are deliberate defenses with documented rationale, not discovery shortcuts — these should NOT be converted to pure folder-scans.
- ✅ The new frontend agents API integration (`/api/agents/library`, `/api/agents/pipelines/{type}`) correctly consumes the live dynamic endpoints with no duplicated agent data on that path.

---

## 6. What Is Not Working / At Risk

- ❌ **`frontend/src/data/hooks.ts` / `data/skills.ts` `compatible_agents` arrays contain stale agent IDs** that don't exist in `backend/agents/prompts/` (e.g. `"html-prototype-builder"`, `"prototype-polisher"`, `"requirements-analyst"`, `"ppt-slide-architect"` vs. real IDs `prototype-build`, `domain-analyst`, `od-ppt-composer`). Consumed at runtime by `AgentsPopup.tsx` and `LibraryPage.tsx` — affected hooks/skills silently never show as compatible with any agent. **No automated check catches this.**
- ⚠️ **`ppt`/`od_ppt` pipeline_type mismatch (WR-01, open since Phase 4)** — the one case where the dynamic scan returns empty and the code falls back to the static `PIPELINE_AGENTS["ppt"]` dict, plus a duplicated `.get("ppt", [])` fallback at `websocket.py:1782-1783`. Root cause: `AGENT.md` frontmatter has no way to declare an agent belongs to two `pipeline_type`s.
- ⚠️ **No test asserts `PIPELINE_AGENTS` matches the dynamic scan output.** A forgotten `registry.py` edit when adding a new agent (a step called out in `backend/CLAUDE.md`) is only caught by the engine's runtime `RuntimeError` when that specific pipeline is actually executed — not at CI/build time.
- ⚠️ `backend/agents/execution_engine/engine.py:5297-5300` `_AGENT_KIND_MAP` (4 agent-id → artifact-kind labels) is a small organic hardcode; documented as cosmetic/lineage-only and explicitly INV-1 exempted, so low risk, but is metadata that belongs on the agent itself.

---

## 7. Impact Assessment

| Dimension | Assessment |
|---|---|
| Severity | Medium (stale `compatible_agents` IDs — a real, silent bug) / Low (everything else — locked, working-as-designed, or cosmetic) |
| Reproducibility | Always, for the specific stale IDs — those hook/skill entries never match |
| Users affected | Frontend users browsing the agent library/hooks/skills picker who rely on the "compatible agents" filter |
| Pipelines affected | None at the pipeline-execution level (registry.py path is sound); frontend agent-picker UX only |
| Data at risk | No |

---

## 8. Recommended Fix Approach

> ⚠️ This is analysis only — no code was changed. Use `velocity-fix` to apply.

**Do NOT do a wholesale "delete `PIPELINE_AGENTS`, make everything a pure folder scan" rewrite.** It's a locked, documented decision, already mostly bypassed at runtime, and doubles as a drift-check anchor and security allow-list. A full removal would need to replace all three of those roles, for no behavioral gain over the current fallback design.

**Option A (preferred, scoped):**
1. Add a CI/unit test that every `compatible_agents` ID in `frontend/src/data/hooks.ts` / `skills.ts` exists in the real backend agent-id set (fetched from `/api/agents/library` or a generated manifest) — closes the actual bug (§6, item 1) without touching locked backend architecture.
2. Close WR-01 properly: extend `AGENT.md` frontmatter to support a `pipeline_types:` list (or an explicit shared-agent alias table) so `ppt` agents can declare membership in both `ppt` and `od_ppt` — removes the need for the `PIPELINE_AGENTS["ppt"]` fallback and the duplicated `websocket.py:1782-1783` `.get("ppt", [])` call site.
3. (Low priority) Add an optional `artifact_kind` field to `AGENT.md` for the 4 agents in `_AGENT_KIND_MAP`, then delete the map from `engine.py`.
4. Add a build-time or startup assertion that `PIPELINE_AGENTS` and the dynamic scan agree for every pipeline where both exist, rather than only discovering drift when a specific pipeline runs.

**Option B (alternative, broader):** Fully migrate `PIPELINE_AGENTS` itself to be generated from the dynamic scan at process startup (still keep it as a Python name for the security allow-list / drift-check use sites, but populate it from `list_agent_ids()` instead of hand-maintaining the dict). Bigger blast radius — touches a decision explicitly marked LOCKED in the Implementation Register — recommend only if the team wants to formally revisit that lock, not as part of this fix.

Files that would need to change (Option A):
- `frontend/src/data/hooks.ts`, `frontend/src/data/skills.ts` — fix stale IDs; add a test/lint step validating against the live agent-id set
- `backend/agents/prompts/*/AGENT.md` (ppt/od_ppt agents) — add `pipeline_types` support once schema is extended
- `backend/agents/registry.py` — remove the now-unneeded `ppt` special case once dual-membership is declared in frontmatter
- `backend/app/api/websocket.py:1782-1783` — remove the duplicated fallback once WR-01 is closed

Invariants to check before fixing:
- [ ] INV-1 — `PIPELINE_AGENTS`/`REVISION_BASE_MAP` are explicitly carved out of the kernel grep-gate; any change here should re-confirm the carve-out is still needed after the fix, not silently re-add hardcoding elsewhere
- [ ] SC-001 (Phase 20) — launchability must continue to key off a declared flag, never a name list; don't reintroduce a name-list check anywhere in the fix
- [ ] Engine drift-check (`engine.py:1466-1477`) — must still fire correctly after any registry/manifest schema change

---

## 9. Open Questions

- ❓ Was `backend/CLAUDE.md`'s framing ("registry says which agents belong to a pipeline") written before `get_pipeline_agents()` was changed to prefer the dynamic scan? If so, the doc is stale relative to the code and should be refreshed to describe the fallback relationship accurately.
- ❓ Why has WR-01 (`ppt`/`od_ppt` quirk) remained open since Phase 4 with no deferral disposition recorded, unlike ISS-015 which got an explicit WONTFIX-then-shipped resolution? Worth asking whether it was simply never prioritized or if there's a reason it was left alone.
- ❓ Is `frontend/src/data/hooks.ts` / `skills.ts` product-authored content (hand-curated by a non-engineer) or engineer-authored? This determines whether the right fix is a CI validation test (content stays hand-authored, just gets checked) or sourcing `compatible_agents` from the backend directly (content becomes derived, not authored).

---

## 10. References

| Type | Location |
|---|---|
| Implementation Register | Phase 4 (ppt/od_ppt quirk, WR-01), Phase 7 (INV-1 carve-out), Phase 20 (WF-DB-01, SC-001) |
| Issues Register | ISS-015 (workflow-type picker, SHIPPED via `GET /api/workflows`) |
| Fix Register | No directly related prior fix found |
| Backend docs | `backend/CLAUDE.md` (registry vs. manifest responsibility split) |
| Companion doc | `.investigations/hardcoded-agents/INVENTORY.md` (flat table of every hardcoded location) |
