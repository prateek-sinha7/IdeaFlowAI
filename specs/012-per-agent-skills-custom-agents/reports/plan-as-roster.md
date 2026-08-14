# Plan-as-roster — deleting the membership assertion

Investigation of the change in `backend/agents/execution_engine/engine.py` that removed
the compiled-plan-vs-registry membership assertion and rebuilt the run roster from the plan.

Branch `fix/hardcoded-agents-registry`.

> **Verdict: SPEC012-ADR-01 and SPEC012-ADR-02.** Both adopted. The membership assertion
> is deleted, not restored (global `ADR-0003`); the roster-clobber regression this report
> flagged is fixed — the plan fills in rather than overrules a caller-supplied roster
> (global `ADR-0008`). See `../ADR.md`.

## The change

The engine built the run's agent roster twice, from two independently authored sources:

- **PLAN** — `compile_for_run(pipeline_type)` → `[s.agent_id for s in compiled.steps]`, from `agents/workflows/<id>/workflow.yaml`
- **MEMBERSHIP** — `get_pipeline_agents(compiled.id)` → from `pipeline_type:` + `order:` in each `agents/prompts/*/AGENT.md`

An assertion at `engine.py:1715-1722` raised `RuntimeError` when the two lists differed. It was deleted, and `agents` is now rebuilt from the plan:

```python
if compiled.steps:
    from agents.loader import load_agent_spec
    agents = [load_agent_spec(s.agent_id) for s in compiled.steps]
```

The same plan-based fallback was added to `resume_run()` (~`engine.py:7970`) and `_compute_resume_offset` (~`engine.py:8409`).

## Verdict

The deleted assertion was a **cross-file drift detector**, not dead code: it caught the case where `workflow.yaml` (hand-authored step order) and an `AGENT.md`'s `pipeline_type`/`order` frontmatter (hand-authored membership) disagree — two independently edited files with no shared schema. That guard is gone and nothing replaces it at runtime; only one static test (`tests/agents/test_manifest_coverage.py::test_all_load_compile`) still checks parity, and only for the 14 manifest-backed production pipelines.

Parity currently holds for all 14 of those — but not for the 4 `sample_*` composed-workflow fixtures, which already prove registry and plan diverge in this codebase today (registry returns `[]`, plan has real steps). Several UI-facing and security-facing call sites still read the **registry** roster independently of the engine's now-plan-only roster, so a future manifest/registry drift would silently desynchronize what the UI shows, what mint-time counts say, and which model-override targets are legal, from what the engine actually runs — exactly the failure mode the assertion was built to catch loudly at run start.

## Why the guard existed

- Added in commit `7dd4c5b5` / `c6e171ad` ("test(agents): MAN-05 routing structure test + MAN-04 compiled-plan integration"): *"engine: fix the 1A agent-sequence drift assertion to compare the compiled plan against the registry MEMBERSHIP source (`get_pipeline_agents`/`PIPELINE_AGENTS`), not `validation.dag` — the resolver legitimately topo-reorders contract-coupled agents."*

- The deleted comment stated: *"any manifest/registry drift fails LOUDLY here rather than silently diverging from the agents the engine drives (RESEARCH Pitfall 3)."*

- `backend/CLAUDE.md` documents it as a load-bearing invariant: the data-flow diagram shows `ASSERT [...] == membership → else RuntimeError`; prose: *"the engine **asserts** the compiled step agent-ids equal that membership and raises `RuntimeError` on drift, so the manifest and registry can never silently diverge"*; "Adding a Pipeline" Step 4: *"or the engine aborts at run entry with `RuntimeError` (the membership assertion in `engine.py`)."*

- `.investigations/hardcoded-agents/FINDINGS.md` (commit `c4f57977`) corroborates: *"The engine actively guards against registry/manifest drift on every run (`engine.py:1466-1477`, raises `RuntimeError` on mismatch) — a forgotten registry edit doesn't silently ship, it fails loudly the next time that pipeline executes."* That investigation made `PIPELINE_AGENTS` folder-scan-derived from `AGENT.md` frontmatter but never touched the `workflow.yaml` side, so the two compared sources remained separately-authored files.

- `.planning/phases/51-.../51-PATTERNS.md:117` still reads **"The membership assertion — DO NOT BREAK"**, cited across six-plus phase plans as recently as Phase 51.

No ADR (`.knowledge/cards/ADR-0001.md`, `ADR-0002.md`) discusses it — no evidence found there.

**No planning document records the removal.** The only trace is the inline comment at `engine.py:1473-1491`. Deliberate at the code level, never reconciled with the surrounding documentation.

## What is now unprotected

- **Reorder a manifest's `steps`** without updating `AGENT.md` `order` fields: previously `RuntimeError` at run entry. Now the run silently executes the new order while registry-reading consumers keep reporting the old one.
- **Change an `AGENT.md`'s `pipeline_type`** without touching `workflow.yaml`: previously `RuntimeError`. Now the engine still runs whatever the manifest lists; registry-visible membership is simply wrong with no signal.
- **Delete an `AGENT.md` folder** referenced by a manifest step: previously a clear membership-drift error. Now `load_agent_spec(s.agent_id)` raises a generic loader exception — after a `WorkflowRun` row (with a registry-derived `agent_count`) has already been minted.
- **Add a composed-workflow template-instance step** is the one case genuinely fixed (registry legitimately returns `[]`) — but the fix is delivered by trusting the plan unconditionally for *every* pipeline, which is the source of the regressions above.

## Ripple effects

| Consumer | file:line | Impact | Severity |
|---|---|---|---|
| `GET /api/agents/pipelines/{type}` | `app/api/agents.py:115-139` | Registry-sourced roster/duration, independent of the engine's plan-sourced roster | High |
| Launch mint `agent_count` | `app/api/run_commands.py:1675, 1785` | Registry-sourced (falls back to plan only when registry is empty); can disagree with what runs | Medium |
| Revision mint `agent_count` | `app/api/run_commands.py:2246-2271` | Same pattern for revision pipelines | Medium |
| `model_overrides` allow-list | `app/api/run_engine.py:539` | Docstring names the exact reintroduced risk: an override for an agent absent from the registry-derived `run_agent_ids` is wrongly rejected, or the inverse silently no-ops (T-06-07) | High |
| `resume_run` offset log | `engine.py:8005-8008` | `len(agents)` in the log can differ from plan-sourced dispatch length; cosmetic | Low |
| `backend/CLAUDE.md` | whole doc | Still describes the deleted `RuntimeError` as active; misleads contributors | Medium |
| `get_all_agents_flat()` / `allowed_custom_agent_ids()` | `agents/registry.py` | Unaffected mechanically, but shares the same latent "registry == runtime roster" assumption | Low–Medium |

## A regression this introduced

`run_commands.py:1643-1653`:

```python
if agent_ids:                       # user picked agents in the composer
    agents = [load_agent_spec(aid) for aid in agent_ids]
else:
    agents = get_pipeline_agents(base_pipeline_type)
```

`engine.py:1491` then overwrites that unconditionally whenever `compiled.steps` is non-empty, and `agents` is not reassigned again before `ordered_agents` at `engine.py:1707`.

`custom/workflow.yaml` declares 9 fixed steps. **A user who picks 3 agents in the composer now gets all 9.** The caller's runtime composition is discarded.

This is the concrete reason "the plan is always the roster" cannot be stated as an unqualified rule: there are three roster sources, not two, and the third — the caller's runtime selection — exists in no file.

| Who composed the run | Roster should be |
|---|---|
| User, at runtime (`agent_ids`, canvas workflow) | their list |
| The manifest | `compiled.steps` |
| Registry | never — a catalog for the UI, not an execution input |

## Resume

`_execute_impl` (shared by fresh and resumed runs) rebuilds `agents` from `compiled.steps` unconditionally, so the dispatch roster is internally consistent between original and resumed runs.

However `_compute_resume_offset` (`engine.py:8409-8461`) independently recomputes `agents` from a **raw** `compile_for_run(pipeline_type)` with no `selections` overlay, while the real dispatch loop applies `_apply_selections` (EMP-01) first. If a run's persisted `selections_json` changed the step set or order, the offset index and the resumed roster can diverge — a pre-existing structural risk, but this change removes the last assertion that would have caught a mismatch before a resume inherited it.

Offset semantics are a plain index into `ordered_agents`; they stay valid only if `compile_for_run` is deterministic between the original run and the resume.

## Test gaps

- No test ever exercised the deleted `RuntimeError` directly (`git log -S` on its error string finds only its introduction).
- `test_compiled_plan_runs.py::test_runs_from_compiled_plan` is now **tautological** for 12 of 13 parametrized cases — the dispatch roster is built from `compiled.steps` by construction, so `started == compiled_ids` is guaranteed. Only `test_od_prototype_alias_runs_prototype_plan` still cross-checks against `get_pipeline_agents`.
- `tests/agents/test_manifest_coverage.py:52-64` is the only surviving check of the invariant, and it is test-time only.
- Nothing covers: `GET /api/agents/pipelines/{type}` vs `compile_for_run` disagreement; `_validate_model_overrides`'s allow-list vs the dispatched roster; the resume-offset-vs-selections divergence; **or a `custom` run with a user-picked subset** (the regression above).

## Safety claim: confirmed for production pipelines

Script over every manifest, `DATABASE_URL=sqlite:///:memory:`, no DB or network:

```
14/14 real pipelines: OK (app_builder, app_builder_revision, chat, custom, dotnet_to_azure,
hello_html, mulesoft_to_springboot, ppt, ppt_revision, prototype, prototype_revision,
reverse_engineer, user_stories, user_stories_revision)

sample_brownfield / sample_fanout / sample_subagents / sample_wave → MISMATCH
  (compiled has real steps, registry returns [] — the composed-workflow case this targets)
```

The claim holds today for production pipelines, but it is an empirical fact about 14 hand-authored files, not an enforced invariant. Nothing prevents future drift.

## Recommendations

1. **Fix the `custom` roster clobber** — do not overwrite a caller-supplied composition. Live bug.
2. Restore a non-blocking runtime drift signal (log/warn, scoped to non-empty `get_pipeline_agents(compiled.id)`) comparing plan vs registry for file-backed pipelines.
3. Re-source `agent_count` (`run_commands.py:1785, 2271`) and `GET /api/agents/pipelines/{type}` (`app/api/agents.py:115`) from `compile_for_run`, not the registry.
4. Re-scope `_validate_model_overrides`'s `run_agent_ids` (`run_engine.py:539`) to the plan roster.
5. Update `backend/CLAUDE.md` — remove the now-false `RuntimeError` claim.
6. De-tautologize or document `test_compiled_plan_runs.py::test_runs_from_compiled_plan`.
7. Either apply the `selections` overlay inside `_compute_resume_offset`, or add a test pinning the assumption that selections never change step set or order.
8. **Record the decision.** Phase 51 says "DO NOT BREAK"; nothing records the reversal. Whichever way it goes, write it down.
