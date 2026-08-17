# Fix Plan: Backend Agent/Workflow Discovery Single-Source-of-Truth

**Tracks:** ISS-035 (`.planning/ISSUES-REGISTER.md`)
**Scope:** Backend only. Frontend `compatible_agents` drift (see `INVENTORY.md` item #10/#11) is explicitly deferred — user directive.
**Principle:** Fix the actual root cause with the smallest possible diff. Do not touch locked/security decisions that aren't the cause of the discovery gap.

---

## 1. Root Cause (confirmed, corrected from the earlier FINDINGS.md read)

`get_pipeline_agents()` in `backend/agents/registry.py` is already fully dynamic — it calls
`list_agent_ids(pipeline_type)`, which scans every `AGENT.md` under `backend/agents/prompts/`
and returns the ones whose `pipeline_type` frontmatter matches. **This part works correctly
today for pipeline execution.**

The bug is that three other consumers do **not** go through that dynamic scan — they read the
hand-maintained literal `PIPELINE_AGENTS` dict directly:

| Consumer | File | What breaks when an agent/pipeline isn't manually added to `PIPELINE_AGENTS` |
|---|---|---|
| `get_all_agents_flat()` | `backend/agents/registry.py:284-311` | New agent never appears in the agent-library API/UI |
| `allowed_custom_agent_ids()` | `backend/agents/registry.py:314-374` | New agent can never be added to a custom/composed workflow (security allow-list rejects it) |
| `_KNOWN_WORKFLOW_IDS` / `list_workflows()` | `backend/app/api/workflows.py:38-243` | New pipeline_type never appears in `GET /api/workflows` |

This is a **real SRP violation**, exactly as flagged: agent membership is declared in two places
(each `AGENT.md`'s `pipeline_type`/`order` frontmatter, AND the hand-maintained
`PIPELINE_AGENTS` dict), and forgetting the second one (`backend/CLAUDE.md`'s documented
"Adding an Agent — Step 3") silently breaks discovery with no error, no test failure, no signal
at all.

**Live proof:** 8 `spec_kit` agents (`analyze-agent`, `deep-planner`, `clarify-agent`,
`constitution-agent`, `plan-agent`, `research-agent`, `specify-agent`, `tasks-agent`) exist on
disk, fully formed, correct `pipeline_type: spec_kit` + unique `order` values — and are in zero
`PIPELINE_AGENTS` entries. They are 100% invisible to the agent library, the custom-workflow
allow-list, and `/api/workflows`, despite being real, loadable `AgentSpec`s.

---

## 2. Fix

### File 1 — `backend/agents/registry.py`

Replace the **literal** `PIPELINE_AGENTS` dict (currently ~150 lines of hand-typed pipeline →
agent-id lists) with one **computed at import time** by scanning `SUPPORTED_PIPELINE_TYPES` via
the loader's own `list_agent_ids()` — the same function `get_pipeline_agents()` already trusts.
Nothing downstream changes shape: `PIPELINE_AGENTS` is still `dict[str, list[str]]`, so
`get_all_agents_flat()`, `allowed_custom_agent_ids()`, and every other consumer needs **zero**
changes — they already consume `PIPELINE_AGENTS` correctly; only how it's *populated* changes.

```python
def _discover_pipeline_agents() -> dict[str, list[str]]:
    """Single source of truth: scan agents/prompts/ (via the loader) for every
    SUPPORTED_PIPELINE_TYPES value, instead of hand-maintaining a literal dict.
    Adding an agent's AGENT.md with the correct pipeline_type/order is now
    SUFFICIENT for it to be discovered everywhere PIPELINE_AGENTS is read (flat
    listing, allow-lists, /api/workflows) — no registry.py edit required.
    """
    agents_map = {pt: list_agent_ids(pt) for pt in sorted(SUPPORTED_PIPELINE_TYPES)}
    # "ppt" is a legacy pipeline-id ALIAS for the od_ppt agent set: no AGENT.md
    # declares pipeline_type: ppt (they declare od_ppt, shared by both ids). This
    # is an id-aliasing decision, not agent data, so it stays one explicit line
    # here rather than being duplicated onto 3 AGENT.md files. Closes WR-01 at
    # the root — the PIPELINE_AGENTS.get("ppt", []) fallbacks in engine.py,
    # websocket.py, and workflows.py now resolve correctly instead of hitting a
    # hand-typed duplicate list.
    agents_map["ppt"] = agents_map.get("od_ppt", [])
    return agents_map


PIPELINE_AGENTS: dict[str, list[str]] = _discover_pipeline_agents()
```

Everything else in `registry.py` — `REVISION_BASE_MAP`, `_INTERNAL_PIPELINES`,
`_OD_ALIAS_BASE`, `get_pipeline_agents()`, `get_agent_by_id()`, `get_all_agents_flat()`,
`allowed_custom_agent_ids()` — is **untouched**. These are either small, stable, genuinely
hand-authored decisions (security boundary, id aliases, revision routing) or already-correct
consumers of `PIPELINE_AGENTS`.

**Side effect (bonus, not scope creep):** this closes the long-open **WR-01** finding
(`ppt`/`od_ppt` pipeline-type mismatch) at the root, because the 3 existing
`PIPELINE_AGENTS.get("ppt", [])` fallback call sites (`engine.py:1466-1473`,
`websocket.py:1782-1783`, `workflows.py:_spec_by_id`) now receive a correctly-populated value
instead of a hand-duplicated list that could drift from the real `od_ppt` agent set. **None of
those 3 call sites need to change** — the fallback mechanism was already correct; only its data
source was wrong.

### File 2 — `backend/app/api/workflows.py`

`_KNOWN_WORKFLOW_IDS` currently mirrors `PIPELINE_AGENTS.keys()`. After File 1's change,
`PIPELINE_AGENTS` gains keys for every `SUPPORTED_PIPELINE_TYPES` value that has *any* agent on
disk — including `spec_kit` (8 agents, no manifest yet) and the pure id-aliases `od_prototype` /
`od_prototype_revision` (0 agents by design — resolved via `_OD_ALIAS_BASE` before reaching a
manifest lookup). `list_workflows()` calls `compile_for_run(workflow_id)` for **every** key,
which raises `FileNotFoundError` when no `agents/workflows/<id>/workflow.yaml` manifest exists —
so naively switching the source would turn `GET /api/workflows` into a 500 for `spec_kit`.

The correct fix: **a "workflow" is defined by having an authored manifest**
(`agents/workflows/<id>/workflow.yaml`), not by having agents. That's already what
`compile_for_run()` requires to succeed — `_KNOWN_WORKFLOW_IDS` should be sourced from the same
place, not from `PIPELINE_AGENTS.keys()` as a proxy for it:

```python
def _discover_manifest_ids() -> frozenset[str]:
    """Workflow catalog membership = presence of agents/workflows/<id>/workflow.yaml —
    the actual precondition compile_for_run() requires. Replaces the previous
    PIPELINE_AGENTS.keys() proxy, which could contain a pipeline_type with real
    agents but no manifest (e.g. spec_kit) — that's an in-progress pipeline, not
    a launchable workflow, and must not be exposed as one.
    """
    return frozenset(
        p.name
        for p in _WORKFLOWS_DIR.iterdir()
        if p.is_dir() and (p / "workflow.yaml").exists()
    )


_KNOWN_WORKFLOW_IDS: frozenset[str] = _discover_manifest_ids()
```

And in `list_workflows()`, change the iteration source:

```python
# before:
for workflow_id in PIPELINE_AGENTS:
# after:
for workflow_id in sorted(_KNOWN_WORKFLOW_IDS):
```

`_spec_by_id()`'s existing `PIPELINE_AGENTS.get(workflow_id, [])` fallback is unaffected — `ppt`
is still both in `_KNOWN_WORKFLOW_IDS` (it has a manifest) and correctly populated in
`PIPELINE_AGENTS` (via File 1's alias line).

### Files intentionally NOT touched

- `REVISION_BASE_MAP`, `_INTERNAL_PIPELINES`, `_OD_ALIAS_BASE` (`registry.py`) — small, stable,
  hand-authored decisions about revision routing / security / id-aliasing. Not the cause of the
  discovery gap; converting them to "derive from convention" is a separate, lower-value change
  the user didn't ask for.
- `engine.py:1466-1473`, `websocket.py:1782-1783`, `workflows.py:_spec_by_id` (the 3 WR-01
  fallback call sites) — already correct, just needed a correctly-populated data source.
- Frontend `compatible_agents` (`hooks.ts`/`skills.ts`) — explicitly out of scope per user.
- `_AGENT_KIND_MAP` cosmetic hardcode (`engine.py:5297-5300`) — separate, low-priority, unrelated
  to discovery.
- Whether `spec_kit` *should* get a `workflow.yaml` manifest — a product decision, not this bug
  fix. This plan makes the gap visible/testable, not silently "fixed" by exposing an unreviewed
  pipeline as launchable.

---

## 3. Tests (drift prevention — the actual ask)

Add to `backend/tests/agents/test_registry.py` (or a new `test_registry_discovery.py` alongside
it, matching existing file-per-concern convention):

1. **No orphaned agent** — for every `AGENT.md` under `agents/prompts/`, assert its `id` appears
   in `PIPELINE_AGENTS[spec.pipeline_type]` (or, for `od_ppt` agents, also reachable via the
   `ppt` alias). This is the direct regression pin for the `spec_kit` bug class: an agent that
   exists on disk but is invisible to the registry now fails a test instead of failing silently.
2. **`get_all_agents_flat()` completeness** — assert its output includes every agent id on disk
   whose `pipeline_type` is in `SUPPORTED_PIPELINE_TYPES` (the exact symptom that was broken for
   `spec_kit`).
3. **Parity with pre-fix behavior** — assert the dynamically-computed `PIPELINE_AGENTS` for the
   15 pipelines that had a manifest before this fix matches the same ordered agent-id lists the
   old literal dict had (hand-transcribe the 15 expected lists into the test as a golden — this
   is the safety net proving the fix is behavior-preserving for everything that already worked).
4. **`ppt`/`od_ppt` alias correctness** — `PIPELINE_AGENTS["ppt"] == PIPELINE_AGENTS["od_ppt"]`
   and both equal the 3 real `od-ppt-*` agent ids in `order`.

Add to `backend/tests/unit/` (wherever `app/api/workflows.py` is already covered, e.g.
`test_workflows_api.py` — check for an existing file first):

5. **`_KNOWN_WORKFLOW_IDS` matches disk** — assert it equals exactly the set of
   `agents/workflows/*/` directories containing a `workflow.yaml` (drift pin: catches "a manifest
   was added but not discovered" and the inverse).
6. **Every known workflow compiles** — assert `compile_for_run(wid)` succeeds for every
   `wid in _KNOWN_WORKFLOW_IDS` (would have caught the `spec_kit` gap directly as "listed but
   won't compile" if the naive fix had shipped without File 2's correction).
7. **`spec_kit` is NOT exposed** — explicit negative test: `"spec_kit" not in _KNOWN_WORKFLOW_IDS`
   today (no manifest yet), documenting the current, correct, reviewed state — so if a manifest
   is later added, this test forces a conscious update rather than an unnoticed catalog change.

Run: `cd backend && python3.11 -m pytest tests/agents/test_registry.py tests/agents/test_registry_helpers.py tests/unit/ -v` before considering this done — full existing suite must stay green (parity requirement, test #3 above is the direct proof).

---

## 4. Follow-up (not part of this fix, flagged for awareness)

- `backend/CLAUDE.md` "Adding an Agent" Step 3 and "Adding a Pipeline" Step 3 currently instruct
  engineers to manually edit `PIPELINE_AGENTS` — these steps become **obsolete** after this fix
  and should be deleted from the doc (doc-only, zero code risk, but leaving stale instructions in
  place would reintroduce the same confusion this fix removes).
- Whether `spec_kit` should get a `workflow.yaml` manifest (making it a real, launchable
  pipeline) is now a clean, visible product decision instead of a silent gap — worth a follow-up
  conversation, not bundled into this fix.

---

## 5. Execution order

1. `registry.py`: swap `PIPELINE_AGENTS` to the discovery function.
2. Run existing `tests/agents/test_registry*.py` — confirm parity (test #3) before adding new tests, to isolate "did the swap change behavior" from "are the new tests correct."
3. Add tests #1, #2, #4.
4. `workflows.py`: swap `_KNOWN_WORKFLOW_IDS` + `list_workflows()` iteration.
5. Add tests #5, #6, #7.
6. Full backend test suite green.
7. Update `backend/CLAUDE.md` Steps 3 (doc-only).
