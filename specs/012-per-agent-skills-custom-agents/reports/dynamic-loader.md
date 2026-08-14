# Dynamic loader — hardcoded frozenset → filesystem discovery

Investigation of the change in `backend/agents/loader.py` and `backend/agents/registry.py`
on branch `fix/hardcoded-agents-registry`.

> **Verdict: SPEC012-ADR-04.** Adopted and implemented — verified on disk:
> `sample_brownfield`/`sample_fanout`/`sample_wave` are `user_launchable: false`, matching
> this report's SC-001-aligned fix. See `../ADR.md`.

## The change

`SUPPORTED_PIPELINE_TYPES` was a hand-typed `frozenset` literal of 17 entries. It is now derived at import time:

```python
_ID_ALIAS_TYPES = frozenset({"od_prototype", "od_prototype_revision"})

def _discover_supported_pipeline_types() -> frozenset[str]:
    types = set()
    if _WORKFLOWS_DIR.exists():
        for entry in _WORKFLOWS_DIR.iterdir():
            if entry.is_dir() and (entry / "workflow.yaml").exists():
                types.add(entry.name)
    for spec in iter_agent_specs():
        types.add(spec.pipeline_type)
    types |= _ID_ALIAS_TYPES
    return frozenset(types)

SUPPORTED_PIPELINE_TYPES = _discover_supported_pipeline_types()
TEMPLATE_AGENT_IDS_BY_FLAG = ...   # also computed once at import
```

Related in the same diff: a new `iter_agent_specs()` tolerant disk scan; `AgentSpec.template: bool = False` parsed from frontmatter; removal of the `pipeline_type not in SUPPORTED_PIPELINE_TYPES` check inside `_build_spec` (circular once the set is derived); `list_agent_ids` filtering on `spec.template` rather than by hardcoded name. In `registry.py`, `_discover_pipeline_agents()` iterates `sorted(SUPPORTED_PIPELINE_TYPES)` and `get_all_agents_flat()` reads the precomputed `TEMPLATE_AGENT_IDS_BY_FLAG` (0.8ms → 0.018ms per warm call).

The set grew from 17 to 21.

## Verdict

The biggest risk is not security — it is a **documented-invariant break**. `app/api/workflows.py`'s `_KNOWN_WORKFLOW_IDS` filters on `SUPPORTED_PIPELINE_TYPES`, and two pre-existing tests hard-assert that `sample_brownfield`, `sample_fanout`, `sample_wave` are absent from that set (ISS-015). Verified by import: all four `sample_*` ids are now in `SUPPORTED_PIPELINE_TYPES`, and `_discover_manifest_ids()` now includes them — so `GET /api/workflows` will return engine test fixtures as catalog rows, and both tests fail.

Three of those four reference agents with **no `AGENT.md`** on disk — structurally unrunnable. Actual *launch* is still blocked by an independent, unmodified allow-list (`app/core/entitlements.py::TIER_PIPELINES`), the real security boundary, untouched by this diff.

**The change itself is correct** — it is SC-001 compliance. The fallout belongs in the manifests and the tests, not in reverting the code. See "The SC-001 reading" below.

## Why it was hardcoded

Introduced in `9374ac28` ("feat(agents): folder-per-agent architecture + DeepAgent migration") as a **schema/typo guard**: `agents/loader.py` (~line 261, pre-diff) raised `AgentSpecError` if an `AGENT.md`'s `pipeline_type` was not in the frozenset — validating authored input, not a security control.

Corroborated by `specs/001-ai-workflow-os/tasks.md:49` and `ROLLOUT.md:20-44` (*"the loader validates `pipeline_type` against this frozenset and will raise `AgentSpecError` for any unknown value"*), and by `backend/CLAUDE.md`'s "Adding a Pipeline" Step 1, which still instructs contributors to edit the now-removed literal.

No ADR, `.knowledge/` card, or `INV-*` frames it as tenancy or security. `git log -S "SUPPORTED_PIPELINE_TYPES"` shows only two touching commits: the introducing one and `c4f57977` ("derive PIPELINE_AGENTS from a folder scan, not a hand-maintained dict").

## The 4 new entries

Verified by import (`DATABASE_URL=sqlite:///…`): `added: ['sample_brownfield', 'sample_fanout', 'sample_subagents', 'sample_wave']`, `removed: []`.

| id | flags | agents referenced | agents on disk? |
|---|---|---|---|
| `sample_brownfield` | `is_beta: true`, `user_launchable: true` | `brownfield-analyze`, `brownfield-build` | **no** |
| `sample_fanout` | `is_beta: true`, `user_launchable: true` | `sample-fanout-plan`, `sample-fanout-worker` | **no** |
| `sample_wave` | `is_beta: true`, `user_launchable: true` | `sample-wave-plan`, `sample-wave-worker` | **no** |
| `sample_subagents` | `is_beta: true`, `user_launchable: true` | `custom-agent` ×4 instances | **yes** |

All four are spec-012 / execution-engine fixtures used by `tests/agents/test_sc001_fanout.py` and `test_sample_*_workflow.py`. For the three with no `AGENT.md`, `registry._discover_pipeline_agents()` resolves `PIPELINE_AGENTS[id] = []` while `compile_for_run` still produces non-empty steps — the mismatch the membership assertion would catch with `RuntimeError` if a run were attempted.

## Security: is the allow-list load-bearing?

**No, not for launch.** Two independent gates exist; this diff touched only the first.

1. `run_commands.py:1521` / `user_workflows.py:432` reject `pipeline_type not in SUPPORTED_PIPELINE_TYPES` — a shape check
2. Both then call `entitlements.py::can_run_pipeline(user.tier, pipeline_type)` (`run_commands.py:1638`, `user_workflows.py:443`), checking `TIER_PIPELINES` — a separate hardcoded `dict[str, set[str]]` (`entitlements.py:8-43`) untouched here

`TIER_PIPELINES` has no entry for `sample_brownfield`/`sample_fanout`/`sample_wave` in any tier including `enterprise`, so `can_run_pipeline` returns `False` regardless of the widened type set. `sample_subagents` is pre-existing in the `enterprise` tier.

**Conclusion:** widening `SUPPORTED_PIPELINE_TYPES` grants no launch access. The regression is **catalog visibility** — `GET /api/workflows` never calls `can_run_pipeline` (visibility and launchability are documented as separate concerns, `workflows.py:109-111`), but ISS-015's stricter rule is what breaks.

## The SC-001 reading

`.knowledge/INVARIANTS.md:22`:

> **SC-001** | Launchability is keyed on the declared flag, never a hardcoded name list — a saved workflow is pure data, no new pipeline name

The hardcoded frozenset was itself an SC-001 violation, so this change is compliance, not regression. And the failing test's own opening comment states the same principle (`tests/unit/test_workflows_api.py:104-115`):

> *"launchability is a DECLARED manifest flag surfaced per row, **never a hardcoded name list**. Every non-revision, non-internal pipeline is user_launchable=true (**including the sample_\* proofs — nothing is hidden from the catalog**; incomplete pipelines are marked is_beta=true instead, which the FE renders greyed-out and non-interactive rather than absent)."*

Thirty lines later the same test asserts three of them are absent. The test contradicts itself, and its first half is the invariant.

What actually happened: those three were never *decided* to be hidden. They were omitted from a hand-typed list, and a later test comment rationalized the omission as a rule. `FANOUT-USER-FACING-SCOPE.md:30` records the original intent — *"`sample_fanout/workflow.yaml` and `sample_wave/workflow.yaml` carry NO `user_launchable` key → default `False` … not launchable"* — which is no longer true: all three declare `user_launchable: true` at HEAD, committed, unrelated to this diff. `ISS-020` (*"the fixture workflows have no product launch surface anyway"*) went stale the same way.

**Recommended fix, invariant-aligned:**

1. Set `user_launchable: false` on `sample_brownfield`, `sample_fanout`, `sample_wave` — restores documented intent, pure data, no name list
2. Change the two tests from "must be absent" to "must be `user_launchable: false`" — which is what the test's own first paragraph says the rule is
3. Leave `sample_subagents` launchable + beta — it runs, and it is the spec-012 proof

## Import-time and deployment risks

- Discovery and `TEMPLATE_AGENT_IDS_BY_FLAG` run once at import (`loader.py:283`, `:295-297`), scanning both directories and fully parsing ~85 `AGENT.md` files via `iter_agent_specs()` — called twice (`loader.py:274`, `:296`). Bounded (tens of ms) but unconditional on any `import agents.loader`.
- If `_WORKFLOWS_DIR` does not exist, source (a) is silently skipped (`loader.py:268`) with **no warning**, unlike `iter_agent_specs()`'s per-agent failure logging (`loader.py:153-158`). A misresolved workflows dir would silently drop every authored type with no diagnostic.
- `iter_agent_specs()` tolerates a missing `_PROMPTS_DIR` (`loader.py:143-144`) and broken individual files (caught and logged, `:151-159`).
- Paths are `Path(__file__).resolve().parent`-relative, so CWD-independent. `backend/Dockerfile:170-175` copies the whole `agents/` tree into the image. Nothing writes to those directories at runtime (they are baked in, not the `/app/skills` or `/app/runs` bind-mounts), so no cache-staleness risk.
- No test currently patches `_WORKFLOWS_DIR`/`_PROMPTS_DIR` after import, but since the constants are computed at first import, any future test doing so sees stale data.

## Ripple effects

| Reader | file:line | Impact | Severity |
|---|---|---|---|
| `app/api/workflows.py::_discover_manifest_ids` | `workflows.py:65-75` | `_KNOWN_WORKFLOW_IDS` now includes all 4 `sample_*`; catalog endpoints expose them | **High** (confirmed) |
| `test_workflows_api.py::test_sample_fixtures_are_not_exposed` | `:336-344` | Fails | **High** |
| `test_workflows_api.py::test_list_carries_launchable_flags` | `:104-141` | Fails | **High** |
| `test_workflows_api.py::test_matches_workflows_directory_independently` | `:317-334` | Still passes but is now tautological — re-derives using the same set the code uses | Medium (false confidence) |
| `agents/registry.py::_discover_pipeline_agents` | `:61-88` | Adds 4 keys; 3 resolve to `[]` | Low |
| `run_commands.py::_resolve_launch_agents` | `:1521` | Accepts `sample_*` past this gate; blocked next by entitlements | Low |
| `user_workflows.py::create_user_workflow` | `:428-445` | Same shape; 403s via `can_run_pipeline` | Low |
| `test_manifest_parity.py::_MANIFEST_BACKED_IDS` | `:38-42` | Silently pulls 4 `sample_*` manifests into parity checks never designed for them | Medium |
| `for pt in sorted(SUPPORTED_PIPELINE_TYPES)` loops | `test_registry.py:33,49,62,83,116`; `test_guardrails.py:129,300`; `test_compiled_plan_runs.py:42`; `test_manifest_coverage.py:41`; `test_registry_discovery.py:137` | Now iterate 4 more types | Medium |
| `entitlements.py::TIER_PIPELINES` | `:8-43` | **Unaffected** — still the real launch gate | N/A |

## The removed `_build_spec` check

Before, it raised `AgentSpecError` for any `pipeline_type` not in the frozenset, catching typos at load time with a clear error. Now (`loader.py:168-179`) it is removed, with a comment acknowledging the check would be circular.

**New symptom:** a typo'd `pipeline_type` no longer errors — it becomes its own one-agent phantom pipeline type via source (b), silently removing the agent from its intended pipeline's membership while creating an unlaunchable one-entry `PIPELINE_AGENTS` key (no `workflow.yaml`, so `compile_for_run` would raise `FileNotFoundError`). The diff names an unimplemented "startup consistency check" as the intended replacement.

## The `template` flag

`AgentSpec.template: bool = False`, parsed strictly (`loader.py:194-204`) — non-bool raises `AgentSpecError`, matching the `_optional_bool` pattern in `agents/workflows/manifest.py:442`.

**Naming inconsistency:** manifest vocabulary uses `is_beta`/`user_launchable`; frontmatter uses the bare noun `template` rather than `is_template`. Stylistic drift, not a bug.

## Test fragility

- The two ISS-015 tests fail against this diff as-is
- `test_loader.py:410,633-643` is now closer to tautological for source-(b) types
- The `for pt in sorted(SUPPORTED_PIPELINE_TYPES)` loops mean any future directory dropped under `agents/workflows/` — even a WIP with no agents — silently joins a dozen unrelated test loops with zero test-file changes. The friction this refactor removed ("adding a workflow is a source-code edit") is reintroduced as "adding a workflow silently changes what unrelated tests iterate over."
- `test_manifest_parity.py:38-42` has identical fragility, and its own comment block (lines 30-37) shows this class of problem already required special-casing `spec_kit`/`od_prototype*` out of similar derived-set logic

## Recommendations

1. **Fix the ISS-015 break via manifest flags + test assertions** (see "The SC-001 reading"). Roughly 20 lines. Do not reintroduce a skip-list — that is what SC-001 forbids.
2. **Update `backend/CLAUDE.md`'s "Adding a Pipeline" Step 1** — it still describes editing the nonexistent frozenset literal.
3. **Implement the deferred startup consistency check** (`loader.py:176-179`) — validate every declared `pipeline_type` maps to something runnable, failing loud at import rather than at first-launch `FileNotFoundError`.
4. **Scope the `for pt in SUPPORTED_PIPELINE_TYPES` test loops** to exclude fixture types so future additions do not silently expand unrelated assertions.
5. **Minor:** rename `AgentSpec.template` to `is_template` for symmetry with `is_beta`, or document the divergence.
