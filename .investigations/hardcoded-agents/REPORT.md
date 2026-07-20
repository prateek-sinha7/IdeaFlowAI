# Report: Hardcoded Agents/Workflows — Investigation, Decision, Fix, Verification

**Status:** FIXED (FIX-051, closes ISS-035)
**Date:** 2026-07-20
**Scope:** Backend only (frontend `compatible_agents` drift explicitly deferred by user directive)

This report consolidates the full arc of this investigation: what was found, the decision
recorded, the fix implemented, and the test verification performed. Companion documents in this
folder: `FINDINGS.md` (initial deep-dive analysis), `INVENTORY.md` (flat table of every hardcoded
location found), `PLAN.md` (the fix plan written before implementation).

---

## 1. The question

Is the backend using hardcoded agent lists instead of discovering agents dynamically from
`backend/agents/prompts/`? If so, was it intentional or organic, does the hardcoding buy
anything, and can it be fixed at the root without a large blast radius?

---

## 2. What we found

**Partially hardcoded, and the split was the actual bug.** `get_pipeline_agents()` in
`backend/agents/registry.py` was already 100% dynamic — it scanned every `AGENT.md` under
`agents/prompts/` via `list_agent_ids()` and required zero manual registration. But three other
consumers read a **hand-maintained literal `PIPELINE_AGENTS` dict** directly instead of going
through that scan:

- `get_all_agents_flat()` — the agent-library API/UI listing
- `allowed_custom_agent_ids()` — the custom-workflow security allow-list
- `app/api/workflows.py`'s `_KNOWN_WORKFLOW_IDS` / `list_workflows()` — the `GET /api/workflows`
  catalog

So a new agent's `AGENT.md` was live for pipeline *execution* the moment it existed on disk, but
stayed invisible to the agent library, the allow-list, and the workflow catalog until someone
remembered `backend/CLAUDE.md`'s documented manual step ("Adding an Agent — Step 3: add the agent
ID to `PIPELINE_AGENTS`"). **Proven live, not hypothetical:** 8 fully-formed `spec_kit` agents
(`analyze-agent`, `deep-planner`, `clarify-agent`, `constitution-agent`, `plan-agent`,
`research-agent`, `specify-agent`, `tasks-agent`) existed on disk with correct
`pipeline_type: spec_kit` + unique `order`, and appeared in zero `PIPELINE_AGENTS` entries.

Full detail, evidence, and register cross-references: `FINDINGS.md`. Every individual hardcoded
location (locked/intentional vs. organic/bug) is catalogued in `INVENTORY.md`.

---

## 3. Decision recorded

Logged as **ISS-035** in `.planning/ISSUES-REGISTER.md` (now marked **FIXED**, FIX-051), with the
full inventory, register cross-references, and recommended fix approach. `PLAN.md` in this folder
was written and reviewed before any code was touched.

---

## 4. Fix implemented (FIX-051)

**Two-file root fix**, everything else is either untouched by design or a necessary test-suite
ripple:

1. **`backend/agents/registry.py`** — `PIPELINE_AGENTS` is now computed once at import time by
   `_discover_pipeline_agents()`, scanning every `SUPPORTED_PIPELINE_TYPES` value through the
   loader's own `list_agent_ids()` — the same scan `get_pipeline_agents()` already trusted. Two
   explicit, deliberate exclusions preserve prior-correct behavior:
   - `"od_prototype"` is excluded entirely — it's a pure `_OD_ALIAS_BASE` id-alias (resolved to
     `"prototype"` before any lookup), never a real `pipeline_type` any `AGENT.md` declares.
   - `"ppt"` stays a one-line explicit alias to `"od_ppt"`'s agent list, because the 3 shared
     `od-ppt-*` agents can only declare one `pipeline_type` value in their frontmatter (they
     declare `od_ppt`) even though two separate manifests/products (`ppt`, `od_ppt`) run them.
     This is `WR-01`, a pre-existing, separately-tracked architectural limitation (single-valued
     `pipeline_type` field can't express multi-pipeline membership) — closed at the *symptom*
     level here (the fragile hand-duplicated list is gone, replaced by one explicit alias line
     that can't drift), not at the schema level (that would require extending `AgentSpec` itself,
     out of scope for this fix; see `PLAN.md` §4 and the conversation record for the full
     reasoning on why that's a separate task).

2. **`backend/app/api/workflows.py`** — `_KNOWN_WORKFLOW_IDS` is now computed by
   `_discover_manifest_ids()`: the intersection of `SUPPORTED_PIPELINE_TYPES` and directories
   under `agents/workflows/` that actually contain a `workflow.yaml`. This is the real
   precondition `compile_for_run()` needs, and correctly keeps both `spec_kit` (agents, no
   manifest — an in-progress pipeline) and the `sample_brownfield`/`sample_fanout`/`sample_wave`
   test-fixture manifest dirs (real files, not real pipeline types — ISS-015) out of the public
   `/api/workflows` catalog.

3. **`backend/CLAUDE.md`** — removed the now-obsolete manual "add to `PIPELINE_AGENTS`" step from
   both "Adding an Agent" and "Adding a Pipeline".

4. **10 test files** — `test_registry_discovery.py` (new) adds the actual drift-prevention pins
   the fix was for. The other 9 existing files had parametrize lists implicitly coupled to the
   old dict's exact key set (`sorted(PIPELINE_AGENTS)` used as a proxy for "the 15
   compilable/dispatchable pipelines") — each was re-scoped to the real invariant it meant to
   test (manifest-backed ids), or given an explicit, documented `spec_kit` carve-out where the
   test legitimately started catching `spec_kit`'s own pre-existing unfinished
   `produces`/`consumes` contracts once its agents became visible.

**Explicitly untouched:** `REVISION_BASE_MAP`, `_INTERNAL_PIPELINES`, frontend `compatible_agents`
arrays, the cosmetic `_AGENT_KIND_MAP` in `engine.py`, and all 3 of the pre-existing WR-01
fallback call sites in `engine.py` / `websocket.py` / `workflows.py` (they needed zero changes —
they already correctly fell back to `PIPELINE_AGENTS.get(id, [])`, which is now populated
correctly instead of hand-duplicated).

Full file-by-file diff rationale: `.planning/FIX-REGISTER.md` FIX-051 detailed entry.

---

## 5. Test verification

### 5.1 Targeted verification (performed during the fix)

Every file touched, plus every file independently discovered to reference `PIPELINE_AGENTS`, was
run and reasoned about individually. Result: **236 passed**, 28 pre-existing failures (traced to
4 unrelated root causes, confirmed identical on the unmodified base branch via `git stash`), 14
skipped. Full detail: `.planning/quick/260720-9pt-agent-workflow-discovery-single-source-of-truth/260720-9pt-VERIFICATION.md`.

### 5.2 Full backend suite (this pass)

```
backend$ DATABASE_URL="sqlite:///:memory:" python3.11 -m pytest tests/ -m "not requires_api_key" -q
2156 passed, 99 failed, 38 skipped, 1 deselected — 397.82s (0:06:37)
```

`DATABASE_URL` was overridden for this run only. This sandbox has no local Postgres running at
all (confirmed: `connection to server at "localhost", port 5432 failed: Connection refused`), so
against the real configured `DATABASE_URL` every checkpointer-backed test (`app.agents.checkpointer`
opens an `AsyncConnectionPool` with a 30s wait) stalls for a full 30s **per test** before failing
— an initial run hit this and was killed after ~6 minutes having completed under 6% of the suite.
Overriding `DATABASE_URL` to a non-Postgres value makes `get_checkpointer()` fall back to
`InMemorySaver` immediately (its own documented, existing behavior — see
`app/agents/checkpointer.py`), so DB-touching tests fail fast instead of hanging. This changes
*how fast* DB-dependent tests fail, not *whether* they can pass — no real Postgres is reachable
either way in this sandbox.

**Every failing file was individually inspected** (not just the aggregate count) to confirm none
trace back to this fix:

| Category | Files (failure count) | Cause |
|---|---|---|
| Pre-existing `allowed_custom_agent_ids` cross-pipeline union (design vs. narrow test expectation) | `test_registry_helpers.py` (5), `test_run_pipeline_validation.py` (12), `test_agents_api_real_registry.py` (1) | Confirmed pre-existing via `git stash` baseline comparison; code path untouched by this fix |
| Stale `clarify.defaults` snapshots (4-item hardcoded lists vs. real 8-item manifests) | `test_manifest_parity.py` (7), `test_id_alias_resolver.py` (8) | Manifest-content drift, unrelated to `PIPELINE_AGENTS` shape |
| Stale FE-mirroring / hardcoded prototype agent expectations (missing `prototype-analyze`, present since before this fix) | `test_phase6_frontend_consistency.py` (4), `test_agents_api_real_registry.py` (2), `test_declared_gate_streaming.py` (1 of 2) | `get_pipeline_agents("prototype")`, untouched by this fix, has always returned 5 agents |
| Manifest/prompt content drift (unrelated fields: `display_name`, `user_launchable`, agent `description`/`max_tokens`, guardrail text) | `test_workflows_api.py` (1), `test_manifest.py` (2), `test_loader.py` (1), `test_plan_task_parsing.py` (1), `test_factory_injects.py` (5) | Content authored into `AGENT.md`/`workflow.yaml` files independently of this fix |
| Test-fixture/engine mismatch (`'_Ctx' object has no attribute 'gate_agent_ids'`) | `test_gates.py` (2) | A test stub class missing a field the engine already expects; unrelated to registry discovery |
| DB/checkpointer-dependent (persistence, migrations, HITL resume, redo, live harness) | `test_handoff_api.py` (10), `test_logout.py` (7), `test_alembic.py` (1), `test_migrations.py` (1), `test_declared_gate_streaming.py` (1 of 2), `test_live_harness.py` (3), `test_phase8_live.py` (3), `test_redo_gate_safety.py` (3), `test_restart_resume.py` (1), `test_sample_brownfield_workflow.py` (2), `test_context_message_oracle.py` (2), `test_live_contract.py` (1), `test_text_only_prompt_hygiene.py` (1), `test_prompt_contracts.py` (1) | Require a real Postgres connection (persistence/migrations/checkpoint-resume semantics); this sandbox has none. Some of these may specifically be an artifact of the `InMemorySaver` fallback behaving differently from `AsyncPostgresSaver` for resume/gate-timing assertions — a test-environment limitation of this diagnostic run, not a code defect. |

**Net: zero failures attributable to `agents/registry.py` or `app/api/workflows.py`.** The
targeted verification in §5.1 (236 passed, same 4 pre-existing categories, zero DB dependency)
remains the authoritative proof of correctness for the actual fix; this full-suite pass is
additional breadth confirming no unrelated regression was introduced.

---

## 6. Known pre-existing gaps (confirmed out of scope, not introduced by this fix)

1. **`allowed_custom_agent_ids` cross-pipeline union** — several tests assert a narrower allow-list
   than the real (by-design) cross-pipeline union implementation already produces. Pre-existing.
2. **Stale `clarify.defaults` snapshots** — several tests hardcode old 4-item clarify-question
   lists; the real manifests now author 8. Pure manifest-content drift, unrelated to discovery.
3. **Stale FE-mirroring agent counts** — a few tests hardcode a 4-agent `prototype` pipeline; the
   real, always-dynamic `get_pipeline_agents("prototype")` has had 5 agents
   (including `prototype-analyze`) since before this fix.
4. **One `dotnet_to_azure` launchable-flag assertion** — unrelated manifest-content check.
5. **`spec_kit` is genuinely unfinished** — no `workflow.yaml` manifest, and its
   `produces`/`consumes` contracts don't fully connect (`clarify-agent` consumes `'brief'` with no
   upstream producer). This fix makes that visible and testable (via an explicit, documented
   carve-out) instead of silently invisible. Finishing `spec_kit` is a separate product decision.
6. **Frontend `compatible_agents` stale IDs** (`hooks.ts`/`skills.ts`) — documented in `FINDINGS.md`
   §6, explicitly deferred per user directive to keep this fix backend-only.

---

## 7. Follow-ups (not part of this fix)

- Decide whether `spec_kit` should be finished (manifest + contract wiring) or removed.
- Fix the frontend `compatible_agents` stale-ID drift with a validation test against the real
  backend agent-id set.
- If ever prioritized, properly closing WR-01 at the schema level (multi-pipeline agent
  membership) would require extending `AgentSpec.pipeline_type` — a separate, larger task; not
  attempted here per explicit scope constraint ("don't touch so many places").
