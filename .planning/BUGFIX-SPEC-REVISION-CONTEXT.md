# Bugfix brief — `update_specs` regenerates the spec; resume loses planning context

**Branch:** `bugfix/spec-revision-context-loss` (cut from `dev`@`5cebdae7`)
**Investigated:** 2026-08-11, read-only, on run `6e38b9a7-f2c1-4557-8a2d-9336e958d182`
**Status:** diagnosed, unfixed. Do not re-investigate — every claim below was verified against source, the backend log, `backend/dev.db`, and the run sandbox.

---

## 1. What happened

A user ran `od_prototype`. The backend was SIGTERM'd mid-run and auto-resumed correctly. At the analyzer gate the user clicked **"Update the Specs"**. The spec writer produced a from-scratch, shorter spec instead of revising the existing one; the planner re-planned against it and the prototype was built from the reduced task list. No UI signal that anything was lost.

**This is a routing bug, not a data-loss bug.** At the moment the degraded prompt was composed, the process held in `ectx.artifacts` (hydrated from the DB at `engine.py:1407`) a 43,670-char `spec` v1, a 37,105-char `planning_context`, and a 2,029-char `clarifications` row. All three were durable and present. None reached the prompt.

**Nothing needs new storage.** No migration, no new table, no new column. `artifact_refs` already holds every version immutably (verified: no `UPDATE`/`DELETE` against that table exists anywhere in production code).

---

## 2. The three defects

### D1 — the revision pass never injects the artifact under revision *(primary)*

`_run_spec_revision_sub_pipeline` sets only the analysis report:

- `engine.py:5054` — `ectx.spec_revision_context = analysis_report`
- `engine.py:8377-8387` — renders it with prose instructing *"Focus your output on fixing the identified issues rather than regenerating from scratch. Preserve unchanged sections."*

The agent has no way to see those sections:

- `agents/prompts/prototype-specify/AGENT.md:2` — `consumes: []`
- same file — `tools: []` → `factory.py:812` makes it a pure-text agent; live log confirms `tools=0 excluded=[... 'read_file' ...]`

Its `AGENT.md:35-51` REVISION MODE block tells it to "Preserve all sections that have ✅ status" and "Keep the same page structure". **The instruction is literally unsatisfiable today.**

Environment-independent — this fires on Postgres too.

### D2 — a resumed run rebuilds planning context from a stub

- `engine.py:1761` — `skip_planner = compiled.planner == "skip" or _resuming or _replaying_clarify`
- `engine.py:1765` — `planning_context = self._default_planning_context(user_message)`
- `engine.py:2927-2942` — every list empty; `inferred_intent = user_message[:200]`

Measured: the injected block collapsed **4,591 → 291 chars** (291 = 43 + 22 + 200 + 24 + 2, exactly reproducing the stub, truncated mid-word at `=== Attached: Job_Aid_Inland Marine Cre`). **16 of the run's 18 agent dispatches ran on the stub** — `kernel_services.py:189` stores the object once and hands the same one to every agent.

The user's clarification answers live in `planning_context["explicit_constraints"]` (`clarify_engine.py:944-951`), and the merged context is never persisted — the `planning_context` artifact is written pre-clarification at `engine.py:2888-2902`.

Checkpointer-independent — **this will reproduce in production.**

### D3 — the accidental checkpointer dependency *(why it surfaced only now)*

The revision re-run reuses the **identical** `thread_id`:

- `engine.py:3527` — `thread_id = f"{pipeline_run_id}:{spec.id}"`
- `engine.py:3540` — suffixed only `if redo_attempt:`; `revision_index` (param at `engine.py:5018`) is **dead — never referenced in the body**
- Log proof: `13:13:21 thread_id=…:prototype-specify` and `13:52:45 thread_id=…:prototype-specify` — identical, across the restart

In-process, LangGraph replays the thread so the model still "remembers" spec v1 — which is exactly what redo deliberately breaks (`engine.py:3534-3537`). On sqlite the checkpointer is `InMemorySaver`, so the restart emptied it and the dependency became visible.

⚠️ Latent and prod-reachable: **redo-then-update_specs** would revise the *rejected* draft (redo ran on `:redo1`; update_specs re-runs on the base thread).

---

## 3. The fix

### F1 — inject the prior spec *(do this first)*

Populate a second consume-once scratch field from `_latest_typed_content(ectx, specify_spec.id)` (`engine.py:6317-6345` — filters by `producer_agent`, returns the latest spec, currently called for nothing on this path) and render it in `_compose_context_message` beside the existing revision block. Clear it in the same `finally` that clears `spec_revision_context` (`engine.py:5115-5117`).

**TRAP 1 — do NOT fix this via `consumes`.** `_filter_consumed_outputs` breaks on `upstream.id == spec.id` (`engine.py:8180-8182`) and specify is `ordered_agents[0]`, so the loop body never executes. Self-consumption is structurally impossible through that path.

**TRAP 2 — there are TWO `_gate_update_specs` consumer sites.** Fix both:
- `engine.py:3254-3290` — RESUME-17 gate re-entry (restart-parked gate)
- `engine.py:4260-4310` — live post-stream (this is the one that fired here)

**TRAP 3 — do NOT give the agent file tools instead.** `spec.md` is written by the *build* step's strategy (`task_loop.py:539`); its mtime is `15:33` while the revision pass ran at `13:52`. The file did not exist. And when it appeared it was already the degraded v2 (md5-identical to `spec-v2.md`). A second on-disk copy would also duplicate what `artifact_refs` already versions (INV-3/INV-12).

Cost: ~11k tokens per revision pass.

### F2 — rehydrate planning context on resume

Preferred: **read the two existing rows back and re-merge** — `planning_context` + `clarifications` through the existing `_merge_answers` (`clarify_engine.py:908-953`). This needs **zero new writes**; the reconstruction was proven offline to reproduce the pre-restart block exactly. Alternative: persist the merged context as a new `planning_context` version after clarification so resume is a single latest-version read.

**TRAP 4 — do NOT re-run the planner on resume.** Skipping it is intentional: quick `260719-hd5` (BUG-R05) changed `_resuming = _resume_from > 0` → `_is_resume` to stop a spurious mid-run questionnaire, guarded by `tests/agents/test_restart_resume.py::test_offset0_gate_resume_does_not_replan_or_reclarify` ("planner NOT re-run, clarifier NOT re-run"). That same fix added artifact-graph hydration but **not** planning-context hydration — that asymmetry is the gap being closed.

### F3 — fresh thread for the revision pass

Thread `:rev{N}` off `spec_revision_attempt` once F1 lands, so behaviour no longer depends on the checkpointer. Also fix the docstring at `engine.py:6379`, which already claims this happens and is wrong.

---

## 4. Tests

**No test asserts on the revision payload today** — `spec_revision_context` appears in **zero** files under `backend/tests/`. That gap is why this shipped.

Write the core test FIRST and **see it RED** before fixing.

| # | Assert | Location |
|---|---|---|
| 1 | The composed context message for the specify re-dispatch **contains spec v1's text** | new — use `tests/agents/_scripted_model.py` |
| 2 | After a simulated restart, the composed prompt contains the clarification answers, not `user_message[:200]` | `tests/agents/test_restart_resume.py` |
| 3 | The revision dispatch's `thread_id` differs from the first pass's | same |
| 4 | `test_offset0_gate_resume_does_not_replan_or_reclarify` still green | existing — proves F2 rehydrated rather than re-ran |
| 5 | The 5 characterization goldens byte-identical (INV-3) | `test_characterization_od_prototype.py` + 4 siblings |
| 6 | `lint-imports` clean | `/opt/homebrew/bin/lint-imports` |

**Re-baseline first.** The goldens were last measured on `dev` at 10 failed / 6 passed with 1 broken import contract (2026-07-29, stale). Measure on the pre-change commit before treating any red as a regression.

Both new injections must be **dormant on a normal run** — no revision, no resume ⇒ byte-identical prompts (INV-3).

---

## 5. Acceptance (live, on Bedrock)

The model is stochastic, so assert *properties* against the DB, not exact text. Pull `spec` v1 and v2 from `artifact_refs`:

```
headings(v2) ⊇ headings(v1)              # today 19 vs 27  → FAIL
"Spinnaker" in v2                         # today 0 hits    → FAIL
"Workflow Completion Checklist" in v2     # today absent    → FAIL
len(v2) >= len(v1)                        # today 39,115 < 43,670 → FAIL
```

All four fail on the current run, so they are a real before/after oracle. **Run three times** — one pass on a stochastic model proves little.

Do not verify through the UI: the FE keeps one slot per agent id and `agent_start` wipes `output: ""` (FIX-039, `useWorkflow.ts`), so spec v1 is erased from the screen the moment the revision starts. Use `GET /api/runs/{id}/artifacts?kind=spec&include=content`.

---

## 6. Out of scope

- **Artifact-version UI.** The versions are stored, `GET /api/runs/{id}/artifacts` already returns `version` per node, and the Concierge already has live `list_refs`/`get_ref` tools (`concierge.py:437-446`). The version UI that exists (`VersionTimeline`/`RunHeader`) tracks whole *runs* via `getRunFamily()`, not artifacts within a run. Wiring job, separate scope.
- **Read-tool access for text-only agents.** Exclusion is all-or-nothing today (`deep_agent_runner.py:328`); a read-only middle state is a legitimate future optimisation for large artifacts, not this fix.
- **`redo` semantics.** Redo intentionally uses a fresh thread and carries no prior output. Unchanged here.
- The `pypdf` extraction failure from the earlier attempt — already fixed, unrelated.

---

## 7. Investigation traps (cost me time; will cost yours)

- Repo-root `dev.db` is a **0-byte stale file**. The live DB is `backend/dev.db` (160 MB).
- The original brief's "sandbox contains only PLANNER.md" is **wrong** — `/tmp/flowin-runs/<user_id>/<run_id>/` holds `spec.md`, `design.md`, `tasks.md`, `prototype.html`, `template.html`, `PLANNER.md`, `conversation_history/`.
- `PLANNER.md` is **write-only** (`engine.py:1913`, no reader anywhere) and contains the lost context including "Spinnaker".
- `agents/artifact_store/` no longer stores artifacts (persistence deleted in PERSIST-02); its `__init__.py` docstring is stale. The real substrate is `artifact_refs` via `ScopedStore` in `agents/authz.py`.
- `accumulated_outputs` does not exist — deleted in 05-07.
- Heading arithmetic: 13 headings absent by exact match, but 5 are renames → **8 heading losses**, of which only **2 are true content deletions** (`Component States`, `## Workflow Completion Checklist (P0)`); the other 6 were demoted into Design Notes bullets with content largely intact.
- `task_list` did **not** shrink in sympathy — tasks went 10 → 11; the heading drop is outline-flattening plus resegmentation.

**Evidence bundle:** `/tmp/flowin-investigation-2026-08-10/evidence/` — backend log across both boots, all 18 composed prompts (`seq=` headers), both spec and task_list versions.

**Neither defect is a regression.** The injection block is unchanged since FIX-048/KAN-101 (2026-07-07) and resume itself behaved correctly. No existing card covers either root cause.
