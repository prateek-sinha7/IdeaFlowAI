# Phase 48: Task Identity & Mutable-List Reconciliation [R3] - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 6 concern-groups (1 new module + 5 modify sites + test idioms)
**Analogs found:** 6 / 6 (all anchors read + verified at HEAD `feat/ui-2`)
**Anchor status:** All line numbers below RE-VERIFIED this session against current files. Drift vs RESEARCH flagged inline where found (none material — RESEARCH anchors hold).

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `agents/capabilities/task_identity.py` (NEW) | utility (pure kernel module) | transform | `agents/capabilities/model_pricing.py` + `agents/capabilities/validators/severity.py` | exact (pure-stdlib, capability-package sibling) |
| `agents/execution_engine/engine.py` `_compute_upstream_context_hash` (NEW helper, extract) | utility (engine-internal) | transform | `_compute_step_input_hash` (the code being factored, engine.py:5799) | exact (self-extraction) |
| `agents/execution_engine/kernel_services.py` `persist_task_html` (MODIFY) | service (capture seam) | file-I/O | itself (branch1 :1384 / branch2 :1442) | self |
| `agents/capabilities/strategies/wave_scheduler.py` `requests` build (MODIFY :270) | strategy | event-driven (fan-out) | itself + `task_loop.py` skip site | self |
| `agents/execution_engine/engine.py` `_compute_resume_completed_task_ids` + `_rematerialize_artifacts_to_disk` (MODIFY) | service (resume kernel) | batch/transform | themselves (:6198 / :5975) | self |
| `agents/execution_engine/engine.py` gate-edit `derived_from` (MODIFY 2 sites) | service (gate) | request-response | redo path `_dual_write_artifact(derived_from=_iter_derived)` (engine.py:3704) | role-match (same writer, derived_from param) |
| `tests/agents/test_task_identity.py` (NEW) + reconcile/sc001 cases | test | — | `test_sc001_nonprototype_task_loop.py`, `test_restart_resume.py` seed idiom | exact |

---

## Pattern Assignments

### 1. `agents/capabilities/task_identity.py` (NEW — utility, pure)

**Analog A — pure capability-package module shape:** `agents/capabilities/model_pricing.py` (docstring lines 1-32).

Copy this module-header discipline VERBATIM in spirit (the "scope guards" block is the template that satisfies the import-linter contract and the SC-001 no-literals rule):

```python
# agents/capabilities/model_pricing.py:13-23
"""
Scope guards:
  - PURE functions only. Imports the catalog (...) plus stdlib (``re``, ``logging``, ``__future__``).
  - MUST NOT import ``app.*``, ``agents.execution_engine``, or ``agents.workflows``
    (import-linter contract "agents.capabilities must not import the execution
    kernel or the web layer"). The kernel/web layers import THIS module, never the reverse.
"""
from __future__ import annotations
import logging
import re
```

**Analog B — single-source pure mapping + "exactly ONE definition" framing:** `agents/capabilities/validators/severity.py:1-16` (the "one home, everyone imports, never re-derives" doctrine — mirror this language for `compute_task_key`).

**Import-linter boundary FACT (VERIFIED this session):** the contract `"agents.capabilities must not import the execution kernel or the web layer"` lives at `backend/pyproject.toml:166-169` (`source_modules = ["agents.capabilities"]`, `forbidden_modules = ["agents.execution_engine", "app"]`). ⚠️ RESEARCH cited `165-169`; the `name=` line is 166, the `source_modules` line is 168, `forbidden_modules` is 169 — the contract block is `[[...contracts]]` at 165. A module INSIDE `agents.capabilities` is freely importable by strategies (intra-package) AND by the engine (the engine is not a forbidden source here; only `agents.capabilities` importing the engine is forbidden — the reverse is allowed). So one shared home works with no `ctx.runner` hop for the pure half.

**Hash discipline to COPY (canonical-JSON, no ts/uuid) — from `_compute_step_input_hash` engine.py:5852-5857:**

```python
canonical = json.dumps(
    {"upstream": sorted(upstream_hashes), "input": resolved_input},
    sort_keys=True,
    separators=(",", ":"),
)
return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Deviate: `compute_task_key` payload is `{"u": upstream_context_hash, "c": normalized_content, "o": ordinal}` — same `sort_keys=True, separators=(",",":")`, same `sha256(...).hexdigest()`. NFC normalize + `re.sub(r"\s+"," ",text).strip()` + strip `^##\s+Task\s+\d+\b:?` for heading bodies. NO `hash()`, NO timestamp (Pitfall 1).

---

### 2. `_compute_upstream_context_hash` — extract-shared-helper (INV-12)

**Analog:** the code being factored IS the analog — `_compute_step_input_hash` engine.py:5799-5857. The extract-then-reuse precedent is the same file's discipline (one home, callers rewritten to call it).

**Quote — the upstream half to LIFT (engine.py:5829-5846):**

```python
upstream_hashes: list[str] = []
if spec is not None and ordered_agents:
    consumes = set(getattr(spec, "consumes", []))
    for upstream in ordered_agents:
        if upstream.id == spec.id:
            break
        if upstream.id.startswith("_"):
            continue
        if set(getattr(upstream, "produces", [])) & consumes:
            for ref in ectx.artifacts.tree(ectx.run_id):
                if ref.producer_agent == upstream.id:
                    upstream_hashes.append(ref.content_hash)
else:
    # No consume contract reachable → hash over ALL produced upstream content
    for ref in ectx.artifacts.tree(ectx.run_id):
        upstream_hashes.append(ref.content_hash)
```

**Copy/deviate delta:**
- New method `_compute_upstream_context_hash(self, step, ectx) -> str`: contains the `spec`/`ordered_agents` resolution (5819-5827) + the block above + `return hashlib.sha256(json.dumps({"upstream": sorted(upstream_hashes)}, sort_keys=True, separators=(",",":")).encode()).hexdigest()`.
- Rewrite `_compute_step_input_hash` to call it, then fold `input`/`task_block` (5847-5850) into its own canonical payload — NO second upstream scan (Pitfall 6 / INV-12).
- Expose to strategies via a KernelServices/runner handle (e.g. `runner.upstream_context_hash(step)`) — the upstream hash is PER-STEP (identical for every task), so compute once per `strategy.run`, then map each task→key.

---

### 3. Write-path switch — `persist_task_html` + wave `requests`

**Site A — `persist_task_html` (kernel_services.py:1321).** Branch-1 write (VERIFIED :1377-1385):

```python
await self._engine._dual_write_artifact(
    self._ectx,
    producer_agent=agent_id,
    producer_step=agent_id,
    content=task_html,
    kind="html_file",
    location=filename,
    task_id=str(task_num),     # ← :1384  SWITCH to task_key
)
```

Branch-2 sibling `ArtifactRef(... task_id=str(task_num) ...)` at :1442 (store-only, `force_db_version=True`). **Delta:** thread a `task_key: str` kwarg into `persist_task_html(self, task_num, agent_id=..., *, filename, task_key)`; write it into BOTH :1384 and :1442 slots. The strategy computes `keys[i]` and passes it at the call site (task_loop.py:317). **Untouched:** the branch-2 dedup-by-content_hash, `_collect_deliverable_relpaths`, the `.uploads/` fence.

**Site B — wave `requests` (wave_scheduler.py:263-271).** VERIFIED current shape:

```python
wave_tasks = [t for t in wave if str(t.id) not in _completed_worker_task_ids]  # :263-265
task_ids = [t.id for t in wave_tasks]                                          # :266
requests = [
    {"agent": "self", "input": t.body, "task_id": t.id} for t in wave_tasks    # :270
]
```

**Delta:** build `key_by_id = {t.id: compute_task_key(...) for t in tasks}` once (after parse at :185); emit `"task_id": key_by_id[t.id]` on each request (:270). **UNTOUCHED (Pitfall 7):** `build_waves(tasks)` (:195), `depends_on`, the dup-guard, `t.id` everywhere in DAG/skip — they never read the request `task_id`. The skip comparison at :264 becomes `key_by_id[t.id] not in _completed_worker_task_ids`.

**Site C — LEAVE UNCHANGED:** `write_fragment_artifact(... task_id=str(worker_index) ...)` kernel_services.py:750 (VERIFIED). Fragment identity is location-based; the wave cursor reads `subagent_runs.task_id` (now the key via fanout.py:388 `task_id=worker.get("task_id")`), NOT fragment task_id. Documented, not switched (scope-minimal).

**Backward-compat fail-safe:** a 64-char sha256 key never equals a legacy positional `"1"` → legacy rows fall out of the skip set → re-run + supersede via versioning. No migration.

---

### 4. ORDER-based common-prefix reconcile

**Analog A — cursor to EXTEND:** `_compute_resume_completed_task_ids` engine.py:6198-6272. task_loop branch VERIFIED :6251-6259:

```python
if strategy == "task_loop":
    done = {
        str(getattr(r, "task_id", None))
        for r in tree_rows
        if getattr(r, "producer_agent", None) == agent_id
        and getattr(r, "task_id", None) is not None
    }
    if done:
        completed[agent_id] = done
```

**Delta (Pitfall 3):** a SET is insufficient for cumulative. Add an ORDERED emission — order the completed `html_file` refs (`producer_agent==agent_id`) by `min(version)` per distinct `task_id` (versions monotonic per kind → build order). Keep the existing `set` for waves and completeness (byte-neutral). Do NOT fork (INV-12) — extend the same method to also return `completed_ordered[agent_id]: list[str]`.

**Analog B — re-materialization per-location global-max to switch to boundary-version:** `_rematerialize_artifacts_to_disk` engine.py:5975-6039. VERIFIED global-max selection :6032-6034:

```python
prev = latest.get(location)
if prev is None or getattr(row, "version", 0) >= getattr(prev, "version", 0):
    latest[location] = row
```

**Delta (Pitfall 4 — the single most important behavior change):** for cumulative resume-after-edit, restore the deliverable's version AS OF the last common-prefix task = the `max(version)` `html_file` ref whose `task_id == current_keys[p-1]`, NOT the global max (which may embed deleted-task work). Add an optional `boundary_task_id`/`current_key_allow_set` param; the `.uploads/` fence (:6030), `_FILE_KINDS` (:6023), best-effort per-row guard (:6038) stay. For WAVE orphan exclusion (48-03), the same allow-set param skips restoring fragment locations whose owning worker's `subagent_runs.task_id` ∉ current-key set — merge/`serialized_sandbox` impls read only disk → orphan excluded from BOTH merge and assembly with zero merge edits.

**Version rule FACT (VERIFIED artifacts/graph.py:163):** `version = 1 + sum(1 for r in self._refs if r.run_id == run_id and r.kind == kind)` — monotonic PER (run,kind), not per location/task. Order-by-`min(version)`, restore-by-`max(version)` both derive from these rows (Pitfall 9: a task_id has multiple versions from the fix-loop re-persist).

**Common-prefix rule (new logic — no direct analog, RESEARCH design):** longest `p` s.t. `current_keys[0:p] == completed_ordered[0:p]` positionally; skip `<p`; run everything at/after first divergence even if its own key matches a completed key.

---

### 5. `derived_from` gap — BOTH gate-edit sites

**Analog (the ONLY gate action that stamps lineage today):** redo path engine.py:3695-3705:

```python
await self._dual_write_artifact(
    ectx,
    producer_agent=spec.id,
    producer_step=spec.id,
    content=output,
    kind=_kind,
    location=_location,
    derived_from=_iter_derived,   # ← :3704  the pattern to REPLICATE
)
```

`_dual_write_artifact` ACCEPTS `derived_from: str | None = None` (VERIFIED engine.py:5527) and plumbs it to `write_ref(... derived_from=derived_from ...)` (:5552).

**Gap site 1 — inline `_gate_edited` (engine.py:2971-2979, VERIFIED — NO derived_from):**

```python
_ek = self._artifact_kind_for(spec)
await self._dual_write_artifact(
    ectx,
    producer_agent=spec.id,
    producer_step=spec.id,
    content=edited,
    kind=_ek,
    location=f"artifact_refs/{spec.id}",
)   # ← add derived_from=<prior task_list ref id>
```

**Gap site 2 — declared `_apply_declared_gate_edit` (engine.py:4566-4575, VERIFIED — NO derived_from):**

```python
await self._dual_write_artifact(
    ectx,
    producer_agent=prev_spec.id,
    producer_step=prev_spec.id,
    content=edited,
    kind=_ek,
    location=(_ek_html_loc if _ek == "html_file" else f"artifact_refs/{prev_spec.id}"),
)   # ← add derived_from=<prior ref id>
```

**Copy/deviate delta:** at BOTH sites, resolve the prior ref id via a `_latest_typed_content`-style max-version lookup for that kind/agent BEFORE writing, pass `derived_from=<that id>`. Small, additive, event-free; goldens never gate-edit → INV-3 neutral (Pitfall 10 — this is the ONLY RESUME-15 gap; everything else already holds: new version via `write_ref`, max-version re-parse via `latest_typed_content`).

---

### 6. Test idioms

**SC-001 synthetic proof analog:** `tests/agents/test_sc001_nonprototype_task_loop.py` (the task_loop precedent RESEARCH names; `test_sc001_fanout.py:1-55` is the sibling fan-out idiom). Copy: manifest at REAL home `agents/workflows/<synthetic>/`, per-agent scripted models, `compile_for_run`/`get_pipeline_agents` pointed at the fixture, planner/store/review-gate neutralised, and the two-part acceptance — (a) `registry.is_registered(...)` all True, (b) `grep -rc "<name>" backend/agents/execution_engine/ == 0`. Drive: complete 2 of 4 → gate-edit the list (delete one completed + edit one pending + add one) → resume → assert exact re-run set + orphan excluded from context/assembly (Pitfall 8).

**Seed-durable idiom (`test_restart_resume.py`):** `_make_session()` + `_seed_workflow_run` + `ScopedStore(...)` + `_seed_ref(store, run_id=, owner=, ws=, kind="html_file", location=, content=, version=, producer_agent=, task_id=)` (VERIFIED :1459-1467) + `store.record_subagent_run(... status=, worker_index=, task_id=)` (:1471-1474). The strategy-level fake idiom: `_FakeRunner`/`_FakeSandbox`/`SimpleNamespace(runner=..., resume_completed_task_ids={...})` (:1305-1315).

**EXACT test-contract split (from RESEARCH §Test-Contract Changes):**

MUST UPDATE (seed keys, not positions — identity contract changed):
- `test_task_loop_skips_completed_tasks_on_resume_cursor` — seeds `resume_completed_task_ids={"prototype-build": {"1","2"}}` (:1314); update to key scheme (or key-aware companion). Behavior preserved (skip completed, run rest); values become keys.
- `test_wave_scheduler_skips_completed_workers_on_resume_cursor` — `ctx.resume_completed_task_ids={"wstep":{"tb"}}` (:1393); `tb` is author id → becomes the wrapped key (or assert the wrap mapping).
- `test_kernel_computes_resume_completed_task_ids_cursor` — seeds `_seed_ref(... task_id="1"/"2")` (:1461-1467) + `record_subagent_run(... task_id="wa"/"wb"/"wc")`; update seeded `task_id`s to keys AND assert the cursor returns keys (core RESUME-14 contract test).

MUST STAY UNTOUCHED (do NOT assert task_id VALUES — byte/event-neutral):
- The 5 `test_characterization_*.py` goldens + `characterization/_normalize.py` (`task_id` in NO event payload — proven by grep; keep `SNAPSHOT_UPDATE` unset, expect 10/10).
- Phase-45 `test_partial_task_loop_build_reenters_step_not_skipped` / `…stays_complete_no_rerun` (assert distinct-COUNT completeness — identity-agnostic).
- `test_per_task_capture.py` (4 — location + content_hash dedup).
- `test_json_tasks.py` (12) / `test_subagent_runs.py` (18) — parser/DAG/dup-guard on author `t.id`, unchanged.
- `test_wave_scheduler.py` (10) — terminal-wave skip/stale-flip, not task_id-value dependent.

---

## Shared Patterns

### Canonical-JSON hash discipline (Pitfall 1)
**Source:** `_compute_step_input_hash` engine.py:5852-5857.
**Apply to:** `task_identity.compute_task_key`, `_compute_upstream_context_hash`, normalization.
`json.dumps(..., sort_keys=True, separators=(",",":"))` → `sha256(...).hexdigest()`. NO `hash()`, NO timestamp/uuid, sort every collection, NFC unicode.

### Best-effort degrade on durable reads/writes
**Source:** `_dual_write_artifact` engine.py:5559-5573 (SQLAlchemyError-only degrade); `_rematerialize_artifacts_to_disk` :6019/:6038; cursor :6270-6271 per-step try/except.
**Apply to:** every new reconciler read — any read failure / ambiguity → leave the step OUT of the completed dict → re-run (fail-safe direction, never skip-wrongly).

### derived_from lineage stamp
**Source:** redo path engine.py:3704 (`derived_from=_iter_derived`).
**Apply to:** both gate-edit sites (2971-2979, 4566-4575).

### SC-001 no-name-literal invariant
**Source:** cursor docstring engine.py:6220-6223 ("keys ONLY on generic identity … zero workflow-name/agent-id literal").
**FACT (VERIFIED this session):** `grep -cE 'pipeline_type ==|spec.id ==' engine.py` == 0. Must stay 0.

---

## No Analog Found

| Concern | Role | Reason |
|---------|------|--------|
| Common-prefix cumulative rule (order-diff + boundary restore) | reconciler logic | No existing prefix-diff in the codebase — the cursor uses set-membership only. Novel; RESEARCH §Cumulative design is the spec. Build against the version-order facts (graph.py:163 monotonic per kind). |
| Wave orphan → re-materialization allow-set join | reconciler logic | The fragment→key join (`worker_index`↔`subagent_runs.task_id`) is new; RESEARCH marks the exact join MEDIUM confidence, the exclusion POINT (re-materialization gate) HIGH. |

---

## Anchor Verification (re-checked this session, HEAD `feat/ui-2`)

| Symbol | RESEARCH anchor | Verified anchor | Status |
|---|---|---|---|
| `_compute_step_input_hash` | 5799-5857 (upstream 5829-5846) | 5799-5857; upstream 5829-5846 | ✓ exact |
| `_dual_write_artifact` task_id/derived_from params | 5526/5527 | 5526 (`task_id`), 5527 (`derived_from`), plumbed 5549/5552 | ✓ exact |
| `_gate_edited` (no derived_from) | 2968-2981 | 2968-2981; write 2972-2979, no derived_from | ✓ exact |
| `_apply_declared_gate_edit` (no derived_from) | 4531-4579 | 4531-4579; write 4566-4575, no derived_from | ✓ exact |
| redo `derived_from=_iter_derived` | 3704 | 3704 | ✓ exact |
| `_compute_resume_completed_task_ids` | 6198-6272 (task_loop 6251-6259, wave 6260-6269) | 6198-6272; task_loop 6251-6259, wave 6260-6269 | ✓ exact |
| `_rematerialize_artifacts_to_disk` global-max | 5975-6039 (max 6032-6034, uploads 6030) | 5975-6039; max 6032-6034, uploads 6030, kinds 6023 | ✓ exact |
| `persist_task_html` branch1/branch2 | 1321-1462 (1384/1442) | 1321-1462; task_id=str(task_num) at 1384 + 1442 | ✓ exact |
| `write_fragment_artifact` task_id | 750 | 750 (`task_id=str(worker_index)`) | ✓ exact |
| fanout spawn stamp | 388 (`task_id=worker.get("task_id")`) | 388 | ✓ exact |
| wave `requests[].task_id` | 270 | 270; skip 263-265, task_ids 266 | ✓ exact |
| task_loop parse+skip | 197,210,224,241-259,317 | plan 197, parse 210, blocks 224, cursor 241-259, persist call 317 | ✓ exact |
| heading parser `Task(id=str(n),body=block)` | 105-122 | 105-122 (id 117, body 119); body includes `## Task N:` header via `_extract_task_block` :58-69 | ✓ exact |
| json parser `Task(id=str(entry['id']))` + dup-guard | 69-146 (dup 130-134) | id 112-116, dup-guard 130-134, depends_on 139-144 | ✓ exact |
| `ArtifactGraph.write_ref` version rule | graph.py:162-163 | graph.py:163 (`version = 1 + sum(... run_id ... kind ...)`) | ✓ exact |
| import-linter capabilities contract | pyproject.toml:165-169 | 165 (`[[...contracts]]`), 166 name, 168 source, 169 forbidden | ⚠ off-by-1 label only; block = 165-169 |
| name-literal count | 0 | `grep -cE 'pipeline_type ==\|spec.id ==' engine.py` == 0 | ✓ exact |

---

## Metadata

**Analog search scope:** `agents/capabilities/` (model_pricing.py, validators/severity.py, strategies/task_loop.py, strategies/wave_scheduler.py, task_parsers/), `agents/execution_engine/` (engine.py, kernel_services.py, fanout.py), `agents/artifacts/graph.py`, `backend/pyproject.toml`, `tests/agents/` (restart_resume, sc001_fanout, sc001_nonprototype_task_loop).
**Files scanned:** ~14 read + verified.
**Pattern extraction date:** 2026-07-19.
