# Phase 48: Task Identity & Mutable-List Reconciliation [R3] — Research

**Researched:** 2026-07-19
**Domain:** Content-addressed task identity + kernel-owned resume/reconciliation over a versioned `task_list` artifact (Flowin `agents/execution_engine`)
**Confidence:** HIGH (all anchors read at current `feat/ui-2` HEAD, file:line verified; baselines run offline)

---

## Summary

Recommended shape: **3 plans**, each RED→GREEN, each byte/event-neutral on goldens (the identity change is dormant on non-resume/non-edited runs).

- **48-01 — Key module (single home) + write-path switch.** New pure module `agents/capabilities/task_identity.py` (importable by BOTH strategies and the engine — see import-linter §below). Factor the upstream half of `_compute_step_input_hash` into one reusable engine helper `_compute_upstream_context_hash(step, ectx)` (INV-12: no second upstream-hashing scheme), expose it to strategies via a `ctx.runner` handle method. Strategies compute a `task_key` per task and write it into the EXISTING `task_id` slots (`persist_task_html`, wave `requests[].task_id`). Legacy positional rows stay readable (fail-safe: unmappable → re-run).
- **48-02 — Reconciler: cumulative (`task_loop`) + RESUME-15 gate-Edit gap-close.** Extend the Phase-46 cursor (`_compute_resume_completed_task_ids`) to emit ordered keys; extend the task_loop skip from positional set-membership to the **common-prefix rule**; extend `_rematerialize_artifacts_to_disk` to restore the **common-prefix version** (not global max). Verify + gap-close the gate-Edit `derived_from` lineage for `task_list`.
- **48-03 — Reconciler: independent (waves) + orphan exclusion + SC-001 synthetic proof + update_specs compose test.** Per-key wave skip (already identity-based) upgraded to keys; orphan (completed-key ∉ current-list) exclusion at the re-materialization gate (merge impls untouched); the sc001 synthetic non-prototype reconcile fixture.

**Primary recommendation:** Put normalization/ordinal/final-sha in `agents/capabilities/task_identity.py`; keep upstream-context-hash as ONE engine helper reused by input_hash AND the key; switch WRITES only (positions→keys) — goldens never read `task_id` (proven below), so the switch is neutral. The hard novelty is the **cumulative common-prefix rule** (needs the original completed ORDER, derivable from `artifact_refs.version`), and the **re-materialization version-selection** change (global-max → common-prefix version).

---

## Verified Current-State Anchors

All `engine.py` = `backend/agents/execution_engine/engine.py`; read at HEAD (branch `feat/ui-2`).

| Concern | Symbol | Anchor | Note |
|---|---|---|---|
| input_hash (upstream + input) | `_compute_step_input_hash` | engine.py:5799–5857 | upstream half 5829–5846; `sorted(upstream_hashes)` 5852–5856; NO ts/uuid |
| step reuse lookup | `_find_reused_completion` | engine.py:5859–5892 | durable owner-scoped `run_events` |
| sole artifact writer | `_dual_write_artifact` | engine.py:5517–5573 | ACCEPTS `task_id` (5526), `derived_from` (5527) — both plumbed to `write_ref` (5549/5552) |
| max-version typed read | `_latest_typed_content` | engine.py:5575–5603 | winner = `max(version)`, `>=` tie-break (5599–5602) |
| inline gate edit | `_gate_edited` handler | engine.py:2968–2981 (+ 3805–3807) | writes new version, **NO `derived_from`** passed |
| declared gate edit | `_apply_declared_gate_edit` | engine.py:4531–4579; call-site 2232–2240 | KAN-98/WR-04 path; **NO `derived_from`** (4566–4575) |
| redo lineage (contrast) | `redo_derived_from`/`_iter_derived` | engine.py:3021, 3704, 3841 | the ONLY gate action that stamps `derived_from` today |
| kind label map | `_AGENT_KIND_MAP` / `_artifact_kind_for` | engine.py:5488–5515 | `prototype-plan → "task_list"` (lineage label; routing is by producer_agent) |
| completeness classify | `_first_incomplete_step` | engine.py:6041–6196 | task_loop branch 6137–6187 (distinct-`task_id` count vs re-parsed total) |
| **skip cursor (Phase 46-04)** | `_compute_resume_completed_task_ids` | engine.py:6198–6272 | task_loop=distinct `artifact_refs.task_id` (6251–6259); wave=`subagent_runs.task_id` where status==complete (6260–6269) |
| **re-materialization (46-03)** | `_rematerialize_artifacts_to_disk` | engine.py:5975–6039 | per-location **global `max(version)`** (6032–6034); kinds `{html_file,file_bundle,deliverable}` (6023); `.uploads/` fenced (6030) |
| resume hooks | hydrate + re-materialize calls | engine.py:1370, 1383 | gated `_is_resume`; cursor stamped at dispatch-prep 2090 |
| version rule | `ArtifactGraph.write_ref` | artifacts/graph.py:162–163 | `version = 1 + count prior (run_id,kind)` — monotonic PER KIND, not per location/task |
| per-task capture | `persist_task_html` | kernel_services.py:1321–1462 | branch1 `task_id=str(task_num)` (1384); branch2 siblings `task_id=str(task_num)` (1442, store-only) |
| subagent spawn stamp | `record_subagent_run` | kernel_services.py:438–474; fanout.py:378–389 | `task_id=worker.get("task_id")` = wave `t.id` (fanout 388) |
| fragment write | `write_fragment_artifact` | kernel_services.py:713–751 | `task_id=str(worker_index)` (750) — NOT the wave key |
| task_loop parse+skip | `TaskLoopStrategy.run` | task_loop.py:197,210,224,241–259,317 | reads `latest_typed_content(source_step)` (max-ver ✓), body=`t.body`, skip `str(task_num) ∈ cursor` |
| wave build+skip | `wave_scheduler` + `build_waves` | wave_scheduler.py:77–127,195,263–270 | `requests[].task_id=t.id`; DAG on author `t.id`; dup-guard 84 |
| heading parser | `HeadingTasksParser.parse` | heading_tasks.py:105–122 | `Task(id=str(n), title, body=block)`; **body includes the `## Task N:` header** |
| json parser | `JsonTasksParser.parse` | json_tasks.py:69–146 | `Task(id=str(entry['id']),…)`; duplicate-id `ValueError` (130–134) |

---

## Key Module Design (single home)

**Home: `backend/agents/capabilities/task_identity.py`** (pure, stdlib-only). Import-linter (`pyproject.toml:165–169`) forbids `agents.capabilities → agents.execution_engine`, but a module *inside* `agents.capabilities` is freely importable by the strategies (`agents.capabilities.strategies.*`, intra-package) AND by the kernel (the engine imports capability ports; only `app.api` is forbidden to the engine, pyproject:145). So this one module is the shared single home for BOTH callers — no `ctx.runner` hop needed for the pure half. `[VERIFIED: pyproject.toml + lint-imports 4 kept/0 broken]`

Pure functions (no engine state, no I/O):

```python
# agents/capabilities/task_identity.py
def normalize_task_content(task) -> str: ...   # reorder/whitespace-stable text of the task
def occurrence_ordinals(tasks) -> list[int]: ... # 0-based prior-identical count, per index
def compute_task_key(upstream_context_hash: str,
                     normalized_content: str,
                     ordinal: int) -> str:       # sha256 of the sorted/canonical triple
```

- `compute_task_key` = `sha256(json.dumps({"u": upstream_context_hash, "c": normalized_content, "o": ordinal}, sort_keys=True, separators=(",",":")))` — mirrors the `_compute_step_input_hash` canonical-JSON discipline (engine.py:5852–5856): sorted keys, NO timestamp/uuid → cross-restart stable.
- Namespacing: the *upstream_context_hash* IS the namespace (a spec/plan edit rotates it → all keys rotate). For waves, wrap (do not replace) the author id — see Normalization below.

**The upstream half — ONE home (INV-12).** Factor lines engine.py:5829–5846 into `_compute_upstream_context_hash(self, step, ectx) -> str` returning the sorted-upstream-hash digest, and rewrite `_compute_step_input_hash` to call it. Expose to strategies via a KernelServices handle method (e.g. `runner.upstream_context_hash(step)`), since the upstream hash needs `runner._ordered_agents` + `ectx.artifacts.tree()` (both already reachable from `ctx`). The upstream hash is **per-step** (identical for every task in the step) → compute once per `strategy.run`, then map each task to its key. Do NOT re-derive a parallel upstream scheme in the strategy (INV-12 violation).

---

## Write-Path Switch

Today three physical write sites put a POSITIONAL value into the free-String `task_id` slot. Switch each to the key; the parsed task content is in scope at the strategy layer at each site.

| Site | Today | Content in scope? | Minimal edit |
|---|---|---|---|
| `task_loop.run` → `persist_task_html(task_num,…)` (task_loop.py:317, 387) | `task_id=str(task_num)` (kernel_services.py:1384, 1442) | YES — `tasks`/`task_blocks` parsed at task_loop.py:210/224 | Compute `keys[i]` in the strategy; thread a `task_key=` kwarg into `persist_task_html`; write it into BOTH branch-1 (1384) and branch-2 (1442) task_id slots |
| wave `requests[].task_id` (wave_scheduler.py:270) | `task_id=t.id` | YES — `tasks` parsed at wave_scheduler.py:~190 | Build a `key_by_id` map once; emit `"task_id": key_by_id[t.id]` on each request; **keep `t.id` for `build_waves`/`depends_on`/dup-guard** (they never read the request task_id) |
| `write_fragment_artifact(worker_index=…)` (kernel_services.py:750) | `task_id=str(worker_index)` | n/a — fragment identity is location-based, NOT read by the cursor | **Leave unchanged.** The wave cursor reads `subagent_runs.task_id` (now the key), NOT fragment task_id. Documented, not switched (scope-minimal) |

Cleanest factoring: compute keys **in the strategy** (content + ordinal are there; upstream hash via `runner.upstream_context_hash(step)`). `persist_task_html` and `record_subagent_run` already accept a `task_id`/kwargs pass-through — no engine-internal threading needed. The value written simply changes from position to key.

**Backward-compat fail-safe (LOCKED):** legacy rows carry positional `task_id` (`"1"`, `"0"`…). The reconciler compares CURRENT-list keys (sha256 hex, 64 chars) against completed values; a positional legacy value can never equal a key → it falls out of the skip set → the task **re-runs** (never skip-wrongly), which supersedes the legacy row via versioning. No migration, no row mutation.

---

## Reconciler Design (cumulative + independent)

The reconciler EXTENDS `_compute_resume_completed_task_ids` (engine.py:6198) — does not fork it (INV-12). Two changes: (1) the completed values become keys (falls out of the write-path switch — the same reads at 6251–6269 now return keys); (2) task_loop needs completed keys **in original production order** for the common-prefix rule.

### Cumulative (`task_loop`) — the common-prefix rule

A completed-key SET is **insufficient** (the cumulative-invalidates-suffix pitfall). Because each task edits the same evolving file, task k's file-state basis is "all of 1..k-1". Rule:

1. Read the CURRENT (max-version) `task_list` via `runner.latest_typed_content(source_step)` (task_loop.py:197 already does this — an edited version is already what it re-parses ✓), parse, compute `current_keys[]`.
2. Recover the **completed ORDER**: order the completed `html_file` refs (producer_agent==step) by `min(version)` per distinct `task_id` (versions are monotonic per kind — artifacts/graph.py:162 — and each task persists after it runs, so version order == build order). → `completed_ordered[]`.
3. **Common prefix** = longest `p` such that `current_keys[0:p] == completed_ordered[0:p]` positionally. Skip indices `< p`; **run everything at/after the first divergence** — even a suffix task whose own key matches a completed key (its predecessor changed → its basis changed).
4. **Restore basis:** re-materialize the deliverable's version **as of the last common-prefix task** = the `max(version)` `html_file` ref whose `task_id == current_keys[p-1]` (the fix-loop re-persist gives multiple versions per task_id; max is the file after that task's fixes). Then the strategy runs `current[p:]` forward from that on-disk state.

This is the discretion item resolved simply-and-provably: order by `min(version)`, select restore by `max(version)` of the boundary task_id — both derivable from the per-task version rows already written.

Delete-in-the-middle correctness: original `[A,B,C]`, delete B → current `[A,C]`. Position 0 `A==A` ✓; position 1 `C != B` (divergence) → `p=1`, restore the version after A, re-run `C`. Deleted B's work is naturally superseded (never merged forward). Insert/edit early → early divergence → correct suffix re-run.

### Independent (`wave_scheduler`) — per-key + orphan exclusion

Waves have no cumulative basis (each worker writes disjoint targets), so **per-key set membership is correct** (no prefix rule). The current skip (wave_scheduler.py:263–264, `str(t.id) ∉ completed`) becomes `key_by_id[t.id] ∉ completed_keys` — completed set now holds keys (from `subagent_runs.task_id`, 6260–6269). New/edited/rotated → key absent → run. Completed-but-current → skip.

**Orphan (completed key ∉ current list) exclusion — merge impls untouched:** an orphaned worker's durable fragment must not reach the assembled deliverable, but rows are immutable (READ-side only). Recommended: gate it at **re-materialization** (the single upstream point before merge/assembly), not in the merge. Extend `_rematerialize_artifacts_to_disk` to accept an optional current-key allow-set (from the reconciler) and skip restoring any file row whose producing task is a confirmed orphan. Because merge (`_merge_fragments`) and the terminal `serialized_sandbox` resolver read only what is on disk, excluding the orphan at re-materialization excludes it from BOTH merge and assembly with **zero merge-impl edits**. Confirmed feasible. The fragment→key mapping is the one wrinkle (fragments carry `task_id=str(worker_index)`, not the key) — join via `subagent_runs` (worker_index↔task_id==key) or, simpler and preferred, restrict re-materialization to fragment locations whose owning worker's `subagent_runs.task_id` is in the current-key set. (Confidence MEDIUM on the exact join; the exclusion *point* is HIGH.)

Fail-safe everywhere: any read failure / ambiguity → leave the step out of the completed dict (existing per-step try/except at 6270) → re-run.

---

## Gate-Edit / task_list Status & Gaps (RESUME-15)

**What already works (verify):**
- The gate that reviews the plan agent's output writes an edited `task_list` version through the SAME sole writer. Inline `_gate_edited` (engine.py:2968–2979) and declared `_apply_declared_gate_edit` (4566–4575) both call `_dual_write_artifact(kind=_ek, …)` where `_ek = _artifact_kind_for(prototype-plan) = "task_list"` (5490). `write_ref` bumps `version` (graph.py:162). `edited_content` rides `POST /{id}/gate` only (WR-03, gate handler 4817–4875). ✓ mints a new version.
- `task_loop` re-parses via `runner.latest_typed_content(source_step)` (task_loop.py:197) → `_latest_typed_content` returns `max(version)` (engine.py:5599–5602). **So the edited task_list IS what the strategy re-parses.** ✓ RESUME-15's central claim holds today.

**The gap (gap-close in 48-02):** NEITHER gate-edit path stamps `derived_from`. `_dual_write_artifact` accepts it (5527) and the redo path uses it (3704/3841), but both `_gate_edited` (2972–2979) and `_apply_declared_gate_edit` (4566–4575) omit it. RESUME-15 requires `derived_from` lineage on the edited `task_list` version. **Fix in place:** pass `derived_from=<prior task_list ref id>` at both edit sites (resolve the prior via the current `_latest_typed_content`-style max-version ref id before writing the edit). Small, additive, event-free; does not perturb goldens (goldens never gate-edit). No new table (12-era "no new step-status table" lock holds — the only substrate is the existing versioned `task_list` artifact).

---

## Normalization & Ordinals

"The task's own text" per parser (what to normalize):

- **heading_tasks:** `Task.body` = the full `## Task N: …` block **including the header line** (heading_tasks.py:65–69). ⚠️ The header embeds the ordinal N (`## Task 3:` vs `## Task 1:`), so reordering a task CHANGES `body` verbatim → naive hashing is NOT reorder-stable. **Normalization MUST strip the leading `^##\s+Task\s+\d+\b:?` ordinal token** from the first line (keep the title text after the colon), then whitespace-normalize (collapse runs, strip trailing WS, normalize newlines). Result: reorder-independent, edit-sensitive.
- **json_tasks:** `Task.id` is author-chosen authoring metadata (NOT content). The task's own text = a canonical serialization of the semantic fields — recommend `title + body + sorted(targets) + sorted(depends_on) + sorted(conflict_keys)` (JSON canonical) so two same-titled workers with different targets don't collide. The key **wraps** the author id (namespaced), it does not replace it — `build_waves`/`depends_on`/dup-guard keep operating on `t.id` (wave_scheduler.py:77–127; json_tasks dup-guard 130–134). ✓ intact.

Normalization proposal (deterministic, in `task_identity.py`): `re.sub(r"\s+"," ", text).strip()` after ordinal-strip; NFC unicode; `\r\n`→`\n`. No locale calls, no dict iteration order (sort every collection) — Pitfall-1 discipline.

Occurrence ordinal (12-06 WR-05 precedent): `occurrence_ordinals(tasks)` returns, per index, the 0-based count of PRIOR tasks whose `normalize_task_content` equals this one. Two identical "Fix styling" tasks → ordinals 0 and 1 → distinct keys. Computed left-to-right over the CURRENT list (stable, position-derived only for tie-breaking identical text, not for identity).

---

## update_specs Composition (Phase 27)

`_run_spec_revision_sub_pipeline` (engine.py:4585–4700) re-runs specify→plan→analyze (positionally, index-2/-1/self — name-free) via the full `_run_agent` path, minting NEW `spec`/`task_list` versions (higher `version`, won by `_latest_typed_content`). Trigger: `_gate_update_specs` (engine.py:2986–2989) sets `spec_revision_pending_output`.

Composition proof (automatic, no new code): a new spec version → new `spec` `content_hash` → the build step's `_compute_upstream_context_hash` (consumes spec/plan) rotates → **every** `task_key` rotates → on resume/continue the reconciler finds NO current key in the completed set → all build tasks re-run. Resume after an update_specs cycle re-enters at the build step (`_first_incomplete_step`) with the max-version task_list; the rotation makes "re-run only what the new list demands" fall out of the substrate. **Add a test** (48-03): seed a completed build under spec-v1 keys, bump spec→v2 (rotating upstream), assert every task re-runs and no v1-key is skipped.

---

## Test-Contract Changes (exact list: update-vs-untouched)

Switching the WRITTEN `task_id` from position to key is a **legitimate contract change for this phase** wherever a test seeds a positional id AS the identity under test. That is NOT assertion-weakening — it updates the fixture to the new identity contract. Honest split:

**MUST update (seed keys instead of positions — the identity contract changed):**
- `tests/agents/test_restart_resume.py`
  - `test_task_loop_skips_completed_tasks_on_resume_cursor` — seeds `resume_completed_task_ids={"prototype-build": {"1","2"}}` (line 1314) and asserts skip by position. Update the cursor + the strategy's current-list keys to the new key scheme (or add a key-aware companion). The *behavior* (skip completed, run rest) is preserved; the values become keys.
  - `test_wave_scheduler_skips_completed_workers_on_resume_cursor` — `ctx.resume_completed_task_ids={"wstep":{"tb"}}` (1393); `tb` is the author id. If waves key by wrapped-id, the seed becomes the wrapped key (or the test asserts the wrap mapping).
  - `test_kernel_computes_resume_completed_task_ids_cursor` (1430) — seeds `artifact_refs` with `task_id="1"/"2"` (1461–1467) and `subagent_runs`; asserts the computed set. Update seeded `task_id`s to keys AND assert the cursor now returns keys (the core RESUME-14 contract test).
- New tests (this phase): common-prefix cumulative reconcile; cumulative version-restore selection; wave orphan exclusion; gate-edit `derived_from` on task_list; update_specs rotation compose; the sc001 synthetic reconcile.

**MUST stay untouched (byte-neutral — they don't assert task_id VALUES):**
- The 5 characterization goldens (`test_characterization_*.py`) + `characterization/_normalize.py` — `task_id` appears in NO emitted event; the normalizer never references it (verified below). Keep `SNAPSHOT_UPDATE` unset; expect 10/10.
- Phase-45 `test_partial_task_loop_build_reenters_step_not_skipped` / `…stays_complete_no_rerun` — these assert COUNT completeness (`distinct(task_id) >= total`), which is identity-agnostic (distinct positions and distinct keys count identically). Untouched.
- `test_per_task_capture.py` (4) — asserts sibling capture by LOCATION + dedup by content_hash, not task_id values. Untouched (unless a test pins `task_id=str(task_num)` literally — none do; they seed then read by location).
- `test_json_tasks.py` (12) / `test_subagent_runs.py` (18) — parser id/dedup semantics + subagent row shape; the DAG/dup-guard operate on author `t.id`, which is unchanged. Untouched.
- `test_wave_scheduler.py` (10) — terminal-wave skip + stale-flip + dispatch; not task_id-value dependent. Untouched.

**Golden neutrality — PROVEN (not asserted):** `grep '"task_id"'` across engine.py + strategies + fanout.py shows task_id appears ONLY in durable-row writes/reads and the wave `requests` dict (input to fanout) — **never inside a `{"type","data"}` event payload**. `_VOLATILE_STRIP_KEYS`/`_REQUIRED_DATA_KEYS` (characterization/_normalize.py:101–…) contain no `task_id`. Therefore what is written into the `task_id` slot is invisible to the WS/SSE event goldens by construction → the positions→keys switch is byte/event-neutral. `[VERIFIED: grep, this session]`

---

## At-Risk Tests & Baseline (real output — HEAD `feat/ui-2`, offline python3.11)

| Suite | Result | Notes |
|---|---|---|
| `test_restart_resume.py` | **16 passed / 1 failed** | KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven` = the SOLE red (Phase-49 anchor) ✓ matches CONTEXT "16/1" |
| `test_per_task_capture.py` | **4 passed** | ✓ |
| `test_wave_scheduler.py` | **10 passed** | ✓ |
| `test_json_tasks.py` | **12 passed** | ✓ |
| `test_subagent_runs.py` | **18 passed** | ✓ |
| `test_redo_gate_safety.py` | **4 passed / 3 FAILED** | ⚠️ **pre-existing on clean HEAD** (git status was clean): `test_f2_unbounded_redos_keep_a_flat_stack`, `test_f3_empty_output_after_redo_does_not_leak_lineage`, `test_redo_uses_fresh_checkpoint_thread_per_attempt`. Symptom: scripted-model gate loop runs once (`got 1 run, expected 3`; `gate_calls["n"]==0`) — an offline scripted-model/deepagents harness drift, NOT the gate-edit persistence path this phase touches. **CONTEXT expected "redo 7/0"; local offline HEAD is 4/3.** The plan MUST re-baseline against pre-phase HEAD (verify-by-delta), not the CONTEXT number, and must not treat these 3 as phase regressions. |
| goldens (5 files, `SNAPSHOT_UPDATE` unset) | **10 passed** | INV-3 dormancy floor ✓ |
| `lint-imports` (`/opt/homebrew/bin/lint-imports`) | **4 kept / 0 broken** | ✓ |

Verify-by-delta floor for this phase: restart_resume 16/1 (KAN-88 only), per_task_capture 4, wave 10, json 12, subagent 18, goldens 10, lint 4/0. redo_gate_safety: hold at its pre-phase 4/3 (do not regress the 4 passing; the 3 reds are pre-existing).

---

## Pitfalls

1. **Cross-restart key stability.** Any locale-sensitive casefold, unsorted set/dict iteration, or `hash()` (salted per-process) in normalization silently breaks resume. Discipline: canonical JSON + `sort_keys`, `sha256`, NFC, no `hash()`, no timestamp/uuid — mirror `_compute_step_input_hash` (engine.py:5852–5856). Register as Pitfall 1 (12-era D-11).
2. **Heading ordinal in `body`.** heading_tasks `body` embeds `## Task N:` (heading_tasks.py:65) — forgetting to strip N makes reordering rotate keys spuriously (defeats reorder-safety). Highest-risk normalization bug.
3. **Cumulative-invalidates-suffix.** NEVER skip a suffix task whose predecessor changed even if its own key matches a completed key. Use the ordered common-prefix rule, not set-membership, for `task_loop`. (Waves are the opposite — set-membership is correct.)
4. **Re-materialization restores global max, not the prefix version.** `_rematerialize_artifacts_to_disk` currently restores per-location `max(version)` (engine.py:6032–6034). For cumulative resume-after-edit that is the LAST task's file (may embed deleted-task work). Must select the version as of the common-prefix boundary task_id. This is the single most important behavior change and is easy to miss.
5. **Legacy-positional coexistence.** A 64-char key never collides with a positional `"1"`, so mixing is safe (unmappable legacy → re-run). But do NOT "normalize" a legacy positional row into a key — treat it as opaque, let it re-run and be superseded by versioning.
6. **INV-12 single-home hashing.** Do not compute a second upstream hash inside strategies. Factor `_compute_step_input_hash`'s upstream half into one helper and reuse it; the banned-pattern/import-linter gates + the "one home" CONTEXT discretion require it.
7. **build_waves must keep author ids.** Key-wrap the wave request `task_id` ONLY; `build_waves`/`depends_on`/dup-guard read `t.id`. Swapping `t.id` for the key at DAG level breaks dependency resolution and the duplicate guard.
8. **SC-001 name-freedom.** Key computation + reconciliation must key on generic parsed content/hashes/`strategy`/`producer_agent`/`task_id` — zero workflow/agent literals (`grep -cE 'pipeline_type ==|spec.id ==' engine.py` must stay 0). The sc001 synthetic fixture (non-prototype manifest + tasks; complete 2 of 4 → edit list: delete one completed + edit one pending + add one → resume → assert exact re-run set + orphan excluded from context/assembly) is the SC4 proof. Clone the existing `test_sc001_fanout.py` idiom.
9. **fix-loop re-persist multiplicity.** A task_id has multiple `html_file` versions (each fix-loop pass). Order completed by `min(version)` per task_id; restore by `max(version)` per task_id. Do not assume one version per task.
10. **derived_from omission is the ONLY RESUME-15 gap.** Everything else (new version, max-version read, no-new-table) already holds — resist re-architecting; stamp lineage in place at the two edit sites.

---

## Validation Architecture

nyquist_validation is enabled (no `workflow.nyquist_validation:false` found). Test infra exists and is the regression floor.

| Property | Value |
|---|---|
| Framework | pytest (+ pytest-asyncio) |
| Runtime | `python3.11` (no venv); ABSOLUTE `cd backend` (stray `backend/backend` exists) |
| Quick run | `python3.11 -m pytest tests/agents/test_restart_resume.py -q` |
| Goldens | `SNAPSHOT_UPDATE= python3.11 -m pytest tests/agents/test_characterization_*.py -q` (10 expected) |
| Import gate | `/opt/homebrew/bin/lint-imports` (4 kept/0 broken) |
| SC-001 gate | `python3.11 -m pytest tests/agents/test_banned_patterns.py tests/agents/test_sc001_fanout.py -q` |

Requirement → test map (Wave 0 = new files this phase):

| Req | Behavior | Test |
|---|---|---|
| RESUME-14 | key = sha256(upstream·normalized·ordinal); reorder/insert/dup/upstream-rotate | new `tests/agents/test_task_identity.py` (pure) + update `test_kernel_computes_resume_completed_task_ids_cursor` |
| RESUME-15 | edited task_list = new version, max-ver re-parsed, `derived_from` stamped | new gate-edit-lineage test (seed v1 task_list → gate edit → assert v2 with `derived_from=v1.id`, `_latest_typed_content` == edited) |
| RESUME-16 cumulative | common-prefix skip + prefix-version restore | new `test_task_loop_reconcile_common_prefix` in `test_restart_resume.py` |
| RESUME-16 independent | per-key wave skip + orphan exclusion from merge/assembly | new `test_wave_reconcile_orphan_excluded` |
| RESUME-16 rotation | update_specs rotates keys → all re-run | new `test_update_specs_reconcile_composes` |
| SC-001 | synthetic non-prototype reconcile, zero engine edits | new `test_sc001_reconcile` (clone `test_sc001_fanout` idiom) |

Wave 0 gaps: `tests/agents/test_task_identity.py` (pure key/normalize/ordinal), plus the reconcile/gate-edit/rotation/sc001 cases appended to the existing seed-durable-then-invoke harness (the Phase-45/46 `pre_store.write_ref(ArtifactRef(...))` idiom). No framework install needed.

---

## RESEARCH COMPLETE

**Phase:** 48 — Task Identity & Mutable-List Reconciliation [R3]
**Confidence:** HIGH

1. **Single home:** `agents/capabilities/task_identity.py` (pure; importable by strategies AND engine — import-linter verified) holds normalize/ordinal/sha; the upstream-context-hash is factored ONCE from `_compute_step_input_hash` (engine.py:5829–5846) and reused (INV-12).
2. **Write-path switch is byte/event-neutral:** `task_id` appears in NO emitted event and in NO golden normalizer key — proven by grep. Switch positions→keys at `persist_task_html` (1384/1442) and wave `requests[].task_id` (270); leave `write_fragment_artifact` and `build_waves`/`t.id` alone.
3. **Cumulative reconcile needs ORDER, not a set:** common-prefix rule over `current_keys` vs completed keys ordered by `min(version)`; restore the deliverable version as of the boundary task (`max(version)` for that task_id) — requires extending `_rematerialize_artifacts_to_disk` (today restores global max, engine.py:6032).
4. **Independent reconcile = per-key set membership + orphan exclusion** gated at re-materialization (merge/`serialized_sandbox` impls untouched).
5. **RESUME-15 mostly works today** (new version + max-version re-parse via `latest_typed_content`); the ONE gap is `derived_from` lineage omitted at BOTH gate-edit sites (2972/4566) — stamp in place.
6. **update_specs composes automatically:** new spec version rotates the upstream hash → all task_keys rotate → all tasks re-run; add a proof test.
7. **Baseline (real):** restart_resume 16/1 (KAN-88 only), per_task_capture 4, wave 10, json 12, subagent 18, goldens 10, lint 4/0. ⚠️ redo_gate_safety = **4/3 pre-existing on clean HEAD** (scripted-model harness drift, not this phase) — re-baseline verify-by-delta, do NOT trust CONTEXT's "7/0".
8. **Plan split:** 48-01 key module + write-path switch · 48-02 cumulative reconciler + gate-edit derived_from gap-close · 48-03 wave/orphan reconciler + SC-001 synthetic proof + update_specs compose. Every plan dormant on non-resume/non-edit runs (goldens 10/10, cursor None-guarded).
