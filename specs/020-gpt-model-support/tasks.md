# Tasks: GPT models on Bedrock, and an Effort dropdown that works for GPT *and* Claude

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)
**Status**: Implemented — 24/24 (12 planned + 12 found during the work). FR-13 now LANDED (see T24). Not committed (Bilal owns all git).
**Outstanding**: nothing in code. FR-13 landed on Bilal's direction 2026-09-22 — read the
residency note at `config.py`'s `BEDROCK_INFERENCE_PROFILE_ID` before shipping.
**Branch**: `feat/gpt-support` · **Worktree**: `VELOCITY-AI-worktrees/feat-gpt-support`

## How to execute these

- **One test file at a time.** Never run the full suite — it breaks this machine. Each task
  names its exact command.
- **No git.** No `add`, no `commit`, no branch operations. Bilal handles all of it.
- **Use `./venv/bin/python`, never bare `python3`.** The shell's `python3` is macOS 3.9.6 and
  `tools/` + several imports need 3.12.
- **Surgical.** Every changed line traces to a task. Do not improve adjacent code, reformat, or
  refactor anything a task does not name.
- **`effort` unset must stay byte-identical to today.** 10 of 12 catalog models are Claude and
  every existing workflow runs on one. Any task that cannot preserve that reports FAIL.
- **T1 comes first and is not reorderable.** Until the cache gate lands, every GPT request fails
  `AccessDeniedException`, so nothing downstream can be *observed* to work.
- A task's PASS criteria are the contract. A criterion that cannot be verified reports FAIL, not
  "probably fine".

## Ledger

| id | task | size | files | status | evidence |
|---|---|---|---|---|---|
| **Blocker** | | | | | |
| T1 | Cache gate — stop `cachePoint` reaching GPT | small | `model_catalog.py`, `deep_agent_runner.py` | ☑ | `test_bedrock_cache_and_thinking.py` 22 passed. Gate proven non-vacuous: removing it fails both SC-12 rows, control still passes. |
| **Capability** | | | | | |
| T2 | `Reasoning` on `ModelEntry`, 10 Claude rows | small | `model_catalog.py` | ☑ | `test_model_catalog.py` 9 passed, 12 entries. |
| T3 | `reasoning_fields()`; delete 2 id-substring tuples | **medium** | `model_factory.py` | ☑ | `test_model_factory.py` 43 passed. Both `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` and `_THINKING_FRAGMENTS` gone — `grep` finds neither. |
| T4 | Catalog: GPT-5.6 Sol + Luna | small | `model_catalog.py` | ☑ | `test_model_pricing.py` 29 passed. See deviation D-2. |
| **Authoring** | | | | | |
| T5 | `ModelPolicy.effort` + compiler validation | small | `plan.py`, `compiler.py` | ☑ | `test_compiler.py` 35 passed. |
| T6 | Selections synth carries effort | small | `selections.py` | ☑ | `test_user_workflows_selections.py` 32 passed. |
| T7 | `ModelResolver.resolve_effort` | small | `model_policy.py` | ☑ | `test_model_resolver.py` 34 passed. |
| T8 | Thread effort to `build_model` | **medium** | `factory.py`, `engine.py`, `deep_agent_runner.py` | ☑ | `test_execution_engine.py` 17 passed. |
| **Surface** | | | | | |
| T9 | API projection; delete `thinking_supported` | small | `capabilities.py`, `api.ts`, `capabilities.ts` | ☑ | `test_capabilities_api.py` 14 passed. |
| T10 | Effort select in `CanvasConfigRail` | **medium** | `CanvasConfigRail.tsx` | ☑ | `CanvasConfigRail.effort.test.tsx` 10 passed + existing `CanvasConfigRail.test.tsx` 39 passed. |
| T11 | Effort select in `AgentsPopup` + Analytics fix | small | `AgentsPopup.tsx`, `AnalyticsPage.tsx` | ☑ | `AgentsPopup.reskin.test.tsx` 14 passed; `AnalyticsPage.test.tsx` 13 passed / 5 pre-existing failures (identical to main). ISS-668 went from **xfail to passing**. |
| **Acceptance** | | | | | |
| T12 | Parity + payload regression guards | **medium** | 3 test files | ☑ | 15 new guards in `test_model_factory.py`, 3 in `test_bedrock_cache_and_thinking.py`, 10 in `CanvasConfigRail.effort.test.tsx`. SC-05 parity measured, not asserted from intent — see below. |
| **Unplanned** | | | | | |
| T13 | `AgentDetailPanel` id→label map → live catalog | small | `AgentDetailPanel.tsx` | ☑ | Found during T11. The map was already stale (9 rows vs a catalog of 12) and its own comment conceded it needed hand-editing per catalog change. `AgentDetailPanel.modelChip.test.tsx` 18 passed, now parametrised over the whole catalog including both GPT rows. |
| T14 | One `modelChangePatch` for both surfaces | small | `AgentsPopup.tsx`, `CanvasConfigRail.tsx` | ☑ | T10 and T11 had each derived the clear-the-stale-effort rule independently. Extracted beside `effortLevelsFor`; `effortHelpers.test.tsx` 16 passed covers all three helpers once for both surfaces. |
| T15 | Effort lever on the **third** authoring surface | small | `AgentsPopup.tsx` (`AdvancedExpander`) | ☑ | Found by driving the real UI. `AgentsPopup.tsx` has TWO model levers — `ConfigLeversFlat` (:1851, the modal) and `AdvancedExpander` (:2197, what the composer's **Simple view** renders via `AgentRow`). T11 only wired the first, so a step configured in Simple view had no Effort control at all. |
| T18 | Remove Claude Haiku 3.5 | small | `model_catalog.py`, 3 backend tests, 4 frontend tests | ☑ | Bilal, 2026-09-22. AWS serves it in NO form in `eu-north-1` — `list_foundation_models` returns zero `claude-3-5-haiku` rows, and there is no eu./global. profile. Entry added 2026-08-14, GEO-01 landed 2026-08-27 and then rewrote its us. prefix to an eu. profile that never existed. Scanned every text/json column in the database first: **0 rows** referenced it. Catalog 11 entries. |
| T24 | FR-13 — global default is Luna, in CODE not env | small | `config.py`, `backend/.env` | ☑ | Bilal, 2026-09-22. The default was never really env-dependent: ONE code default at `config.py` feeds ~12 call sites that all read `settings.BEDROCK_INFERENCE_PROFILE_ID`. The worktree `.env` was merely shadowing it. Default moved to `global.openai.gpt-5.6-luna` in code and the `.env` line deleted; verified with `Settings(_env_file=None)` and a live 9-agent run where every agent resolved to Luna with no override anywhere. Revert is that one line. **Residency warning is inline at the field.** |
| T21 | Gate the SECOND cache-point path | small | `cached_invoke.py`, `test_cached_invoke.py` | ☑ | Found by a real run with the default flipped to Luna: `SmartPlanner failed: AccessDeniedException ... did not allow prompt caching`, planning silently skipped. T1 gated `_BedrockCachePointsMiddleware`; `cached_invoke` is a SECOND path its own docstring says places "the SAME cache_control" — used by SmartPlanner, ClarifyEngine and both handoff agents. One guard in the shared helper covers all four. 4 new tests, incl. one asserting both paths agree per catalog model. |
| T22 | Composer save dropped per-step model + effort | small | `userWorkflows.ts`, `types/index.ts`, new test file | ☑ | Found by the same run: four agents each set to a different model ALL executed on the default. `agentToManifestStep` read `selections[id]` for gates/tools/strategy/task_source/fanout — never `.model` or `.effort`, so the full-manifest save branch dropped them. Pre-existing for `model` (predates spec 020). 5 new tests in `userWorkflows.modelEffort.test.ts`. |
| T23 | Composer Save leaked its re-entrancy lock | small | `ComposerPage.tsx` | ☑ | Pre-existing (identical on main). `isSavingRef` is set at the head of `handleSave`, but the detached-step and not-authenticated guards `return` BEFORE the `try` whose `finally` clears it — so one rejected save made every later Save click a silent no-op for the page's life: no request, no new error. Blocked this validation until fixed. |
| T20 | Picker is alphabetical after Default | small | `model_policy.py` | ☑ | Bilal, 2026-09-22. Settled on plain alphabetical by label. A vendor-grouped pass (GPT first) was built and then reverted the same day — the `ModelEntry.vendor` field it needed went with it, since nothing else read it and a field every new entry must fill but no code consumes is how a catalog rots. Order pinned by `test_selectable_models_is_alphabetical`. |
| T19 | Sort the picker; catalog order left alone | small | `model_policy.py` | ☑ | The dropdown was `_ENTRIES` authoring order (Haiku 4.5, GPT, Sonnet 4.5, 4.6, 5, 4, Opus) — noise to a reader. `selectable_models()` now sorts cheap→standard→premium, then label. The CATALOG is deliberately NOT re-sorted: `model_pricing` bills an unknown model at the FIRST `cost_class="cheap"` entry, so its order is load-bearing. Verified the anchor is still Claude Haiku 4.5 at $1.00/1M. |
| T17 | One row per model in every picker; no tier suffix | small | `model_policy.py`, `model_catalog.py`, `settings.py`, `capabilities.py`, 3 components | ☑ | Bilal, 2026-09-22. `(fast)`/`(powerful)` dropped from all 3 dropdowns — `tier` is display-only and reaches no request, so it read as a latency promise. `us.`/`eu.` duplicates collapsed by `selectable_models()`: 12 catalog rows → 10 picker rows. Decision recorded below. |
| T16 | `AgentRow` pill resolves its label from the catalog | small | `AgentRow.tsx` | ☑ | Its local `shortModel()` kept the last `[.:/]` segment of the raw id: `global.openai.gpt-5.6-luna` rendered as **"6-luna"** and `…claude-haiku-4-5-20251001-v1:0` as **"0"**. Pre-existing (every Claude id was already wrong); visible on the GPT path, so fixed the way `CanvasNode` already did it. |

### SC-05 parity — measured

Recorded by replaying `build_model()` over every catalog id × `disable_thinking` against the
**pre-change** tree (main @ `049a8c3a4`) and diffing against this one. **21 of 24 combinations are
byte-identical.** The 3 that differ, each authorised:

| combination | pre-change | now | why |
|---|---|---|---|
| Haiku 3.5, thinking on | `thinking: enabled @32767` | *(nothing)* | SC-04 — the model has no extended thinking; it was being sent a field it does not support |
| Luna, thinking on | `thinking: enabled @32767` | *(nothing)* | did not exist pre-change |
| Sol, thinking on | `thinking: enabled @32767` | *(nothing)* | did not exist pre-change |

The table is pinned in `test_sc05_every_catalog_model_is_byte_identical_without_an_effort`, which
also fails if a model is added to the catalog without recording its parity position — so this
cannot rot silently.

### Regression baseline

Every failure below reproduces identically on main @ `049a8c3a4`; none is caused by this branch.
Verified by running each file in both trees.

| suite | result |
|---|---|
| `test_create_runner.py` | 2 failed (`reserved_path_guard`) — same 2 on main |
| `test_allowed_step_keys.py` | 3 failed (`missing={'outputs','replaces'}`) — same 3 on main; `effort` is not implicated |
| `AnalyticsPage.test.tsx` | 5 failed (token division + 4 pipeline chips) — same 5 on main |
| `tsc --noEmit` | 12 errors — byte-identical list to main |
| `ruff` (9 changed source files) | 38 findings — byte-identical list to main |
| `eslint` (6 changed source files) | 2 errors, 38 warnings on main → 39 here. The one addition is `react-hooks/static-components` in `CanvasConfigRail.tsx`, fired by the Effort block's `<InfoHint>`: the rule already reports 15 times in that file for the same in-render component definition. Silencing it means hoisting `InfoHint` out — a refactor of pre-existing code no task asks for. |

### Deviations from the plan

- **D-1 — T4 landed before T3.** The catalog rows were cheaper to add while `model_catalog.py`
  was already open for T2. No downstream effect: T3 reads the field, it does not care when the
  rows arrived.
- **D-2 — the GPT rows sit third and fourth in `_ENTRIES`, not first.** Placing Luna first broke
  `test_none_model_prices_as_haiku_1x`: `_resolve_pricing` falls back to the *first*
  `cost_class="cheap"` entry for an unknown id, so an unpriced model silently billed at Luna's
  rate — a 5x under-estimate. Ordering in that file is load-bearing.
- **D-3 — `normalize_model_id()` moved from `model_pricing.py` into `model_catalog.py`.** The plan
  had `reasoning_fields` matching ids exactly, but the ChatAnthropic dev path holds bare ids
  (`claude-sonnet-4-5`) that never match a Bedrock profile id. `ModelCatalog.resolve()` does exact
  then normalized; the pricing module now imports it rather than owning it.
- **D-4 — T13 through T16 were not in the plan.** See their ledger rows. T15 and T16 were both
  found only by driving the real UI on :3001 — the component tests passed throughout, because
  they render the surfaces the tests know about, and T15's surface was one nobody had listed.
- **D-5 — the Analytics row was renamed "Thinking" → "Reasoning"** and its budget value
  "Enabled" → "Budget". Required: the row can now read "Effort (none–max)" for a GPT model, and
  GPT's effort is not extended thinking.

## Task graph

```
T1 ──┬─► T2 ──┬─► T3 ──┬─► T4 ──► T9 ──┬─► T10 ──► T12
     │        │        │               │
     │        │        └─► T5 ─► T6    └─► T11
     │        │              └─► T7 ─► T8 ─┘
     └────────┴─ (T1 independent; everything else waits on T2's field existing)
```

T2 gates everything because `Reasoning` is the type T3, T9 and the UI all read.

---

## Blocker

### T1 — Cache gate: stop `cachePoint` reaching GPT (FR-21, SC-12)

**Files**: `backend/agents/capabilities/model_catalog.py`, `backend/app/agents/deep_agent_runner.py`

Verified live: `global.openai.gpt-5.6-luna` + `cachePoint` → `AccessDeniedException`, while
`eu.anthropic.claude-haiku-4-5` passes the identical call (spec §12.3).

1. Add `supports_prompt_caching: bool` to `ModelEntry`. All 10 existing (Claude) entries: `True`.
2. In `_BedrockCachePointsMiddleware._maybe_apply` (`deep_agent_runner.py:456`), after the
   existing `isinstance(request.model, ChatBedrockConverse)` check, look the model up and bail
   when caching is unsupported:
   ```python
   entry = ModelCatalog().get(model_identifier(request.model))
   if entry is not None and not entry.supports_prompt_caching:
       return request
   ```
   `model_identifier` already exists (`model_factory.py:402`) and reads `.model_id` off a
   `ChatBedrockConverse`.
3. Keep the `isinstance` check — it is still what keeps ChatAnthropic on deepagents' own caching
   path (no double-apply). This adds a second gate; it does not replace the first.
4. An **unknown** id (`entry is None`) keeps caching ON — today's behaviour, and the parity-safe
   direction. Comment that the fail-open is deliberate.

**PASS**: with `BEDROCK_PROMPT_CACHE_ENABLED=True`, a `ChatBedrockConverse` whose model id is a
GPT entry gets no `cache_control` in `model_settings`; a Claude id still does; an unknown id
still does.
**Verify**: `./venv/bin/python -m pytest backend/tests/agents/test_bedrock_cache_and_thinking.py -q`

---

## Capability

### T2 — `Reasoning` on `ModelEntry` (FR-02)

**File**: `backend/agents/capabilities/model_catalog.py`

```python
@dataclass(frozen=True)
class Reasoning:
    """How a model exposes reasoning, and what a UI may offer for it."""
    mode: str                  # "effort" | "adaptive" | "budget" | "none"
    levels: tuple[str, ...]    # () = no control at all
```

Add `reasoning: Reasoning` to `ModelEntry` (no default — every entry declares it, so a new model
cannot silently inherit one). Also export `REASONING_EFFORT_LEVELS = ("none","low","medium","high","xhigh","max")`;
the compiler validates against a model's own `levels`, and this constant is the documented
superset.

Declare the 10 existing entries per plan.md's table: Sonnet 5 (both geos) `adaptive`/`("none","on")`;
Haiku 3.5 `none`/`()`; everything else `budget`/`("none","on")`.

**PASS**: all 10 entries carry an explicit `Reasoning`; `ModelEntry` has no default for it;
`Reasoning` is frozen.
**Verify**: `./venv/bin/python -m pytest backend/tests/agents/test_model_catalog.py -q`

### T3 — `reasoning_fields()`, and delete two id-substring tuples (FR-03, SC-06)

**File**: `backend/app/agents/model_factory.py`

One function builds every reasoning block, per plan.md's mapping table:

```python
def reasoning_fields(model_id: str, effort: str | None, max_tokens: int,
                     *, disable_thinking: bool) -> dict:
```

Then **delete** `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` and `_thinking_type` and route the existing
`extra_fields` construction through the new function.

Three rules that are bugs if broken:
- `effort=None` reproduces today's request exactly (INV-3). For `budget`/`adaptive` that means
  the existing `settings.THINKING_BUDGET_TOKENS > 0 and not disable_thinking` predicate still
  decides, and the budget clamp `max(1024, min(THINKING_BUDGET_TOKENS, max_tokens - 1))` is
  unchanged.
- `effort="none"` is NOT `effort=None`. It means explicitly off → `{"type":"disabled"}` /
  `{"effort":"none"}`.
- An id absent from the catalog falls back to `budget`, warn-once. `none` would be tidier and
  would silently stop sending `thinking` for any uncatalogued model — a parity break wearing a
  cleanup's clothes.

`mode="none"` on Haiku 3.5 is the one intentional behaviour change (spec RISK-04).

**PASS**: `grep -rn "_ADAPTIVE_THINKING_MODEL_FRAGMENTS\|_thinking_type" backend/` returns
nothing; every row of plan.md's mapping table is covered by a test case.
**Verify**: `./venv/bin/python -m pytest backend/tests/unit/test_model_factory.py -q`

### T4 — Catalog: GPT-5.6 Sol and Luna (FR-01)

**File**: `backend/agents/capabilities/model_catalog.py`

| | Sol | Luna |
|---|---|---|
| id | `global.openai.gpt-5.6-sol` | `global.openai.gpt-5.6-luna` |
| tier / cost_class | `powerful` / `premium` | `fast` / `cheap` |
| context_window | `1000000` | `1000000` |
| pricing (in/out/cr/cw) | `4e-6, 20e-6, 0.4e-6, 5e-6, 5e-6` | `0.2e-6, 1.2e-6, 0.02e-6, 0.25e-6, 0.25e-6` |
| vision | `True` | `True` |
| supports_prompt_caching | **`False`** | **`False`** |
| reasoning | `effort`, all six levels | `effort`, all six levels |

Both **must not** be first in `_ENTRIES`: `model_pricing._resolve_pricing` falls back to the
first `cost_class="cheap"` entry for an unknown id, so a leading Luna silently reprices every
unknown model from $1.00/1M to $0.20/1M. Place them after the two Haiku 4.5 rows.

Comment on both: Global CRIS is the only option from `eu-north-1` (no in-Region, no `eu.`
profile), so these entries do **not** preserve EU residency; long-context (>272K in) bills ~2×
and is not modelled; the cache fields are unreachable on Converse.

Bump the inventory counts in `test_model_catalog.py` (9 → 12) and `test_model_pricing.py`
(10 → 12). **Note both were already stale before this spec** — they read 9 and 10 against a
catalog of 10 — so the delta is not purely ours.

**PASS**: 12 entries; both GPT ids in `_EXPECTED_IDS`; `estimate_cost_usd(None, 1_000_000, 0) == 1.0`
(unknown-id pricing still resolves to Haiku, proving neither GPT row leads the tuple).
**Verify**: `./venv/bin/python -m pytest backend/tests/agents/test_model_pricing.py -q`

---

## Authoring

### T5 — `ModelPolicy.effort` + compiler validation (FR-04, FR-05)

**Files**: `backend/agents/workflows/plan.py`, `backend/agents/workflows/compiler.py`

- `plan.py`: `effort: str | None = None` on `ModelPolicy`, commented that `None` ≠ `"none"`.
- `compiler.py`: add `"effort"` to `_compile_model_policy`'s `allowed` set (line ~1400) and
  validate it **against that model's own `levels`**, not the global superset — a `xhigh` on a
  Claude step is a `CompilerError` naming the step, the value and the valid set. When the block
  names no model, validate against `REASONING_EFFORT_LEVELS`.
- The compiler may import `agents.capabilities.model_catalog` (it already imports
  `agents.capabilities.registry`), so no new contract violation.

**PASS**: `{"model":"global.openai.gpt-5.6-sol","effort":"high"}` compiles;
`{"model":"eu.anthropic.claude-haiku-4-5-20251001-v1:0","effort":"xhigh"}` raises naming the step;
an unknown key inside `model:` still raises (INV-5).
**Verify**: `./venv/bin/python -m pytest backend/tests/unit/test_workflow_compiler.py -q`

### T6 — Selections synth carries effort (FR-15, FR-16)

**File**: `backend/agents/workflows/selections.py`

Add `"effort"` to `_LEVER_KEYS` (line ~43) and, beside the existing `model` branch (line ~123):

```python
effort = sel.get("effort")
if effort is not None:
    step.setdefault("model", {})["effort"] = effort
```

A key absent from `_LEVER_KEYS` is carried verbatim onto the raw step and then rejected by the
compiler's strict-key check — so omitting the `_LEVER_KEYS` entry is a hard failure, not a silent
drop. No `_ALLOWED_STEP_KEYS` change: effort lands *inside* the `model` block.

Order matters: `setdefault` means a selection carrying only `effort` still produces a valid
`model` block, and one carrying both keeps the model id.

**PASS**: `{"effort":"high"}` → `{"model":{"effort":"high"}}`; `{"model":"X","effort":"high"}` →
`{"model":{"model":"X","effort":"high"}}`; `{}` → no `model` key at all (parity).
**Verify**: `./venv/bin/python -m pytest backend/tests/unit/test_user_workflows_selections.py -q`

### T7 — `ModelResolver.resolve_effort` (FR-06, FR-17)

**File**: `backend/agents/model_policy.py`

```python
def resolve_effort(self, step=None) -> str | None:
    step_effort = step.model.effort if step is not None and step.model else None
    return step_effort or (self._workflow_model.effort if self._workflow_model else None)
```

Tier 2 then tier 4 only. No tier-1 override, no AGENT.md tier, no session tier — nothing writes
those, and inventing them is three untested paths. Takes `step` alone, not `(spec, step)`: there
is no spec tier, so a `spec` parameter would be one no branch reads.

**PASS**: step effort wins over workflow effort; workflow effort used when the step has none;
`None` when neither; no exception when `step.model` is `None`.
**Verify**: `./venv/bin/python -m pytest backend/tests/unit/test_model_resolver.py -q`

### T8 — Thread effort to `build_model` (FR-18, FR-19, FR-20)

**Files**: `backend/agents/factory.py`, `backend/agents/execution_engine/engine.py`,
`backend/app/agents/deep_agent_runner.py`

The value has to cross from the resolver to the mapping function:

1. `factory.py`: `AgentContext.effort: str | None = None`, beside `model` (line ~58).
2. `engine.py`: a `_resolve_effort(ectx, step)` static beside `_resolve_model` (line ~7737),
   returning `None` when `ectx.model_resolver is None` (the resolver-absent path used by direct
   `_run_agent` invocations — FR-17). Set `effort=` on the `AgentContext` beside `model=` at
   line ~8820.
3. `deep_agent_runner.py`: accept `effort` and pass it to `build_model` at line ~743.

**Only the agent path carries effort.** `cached_invoke.py:168` and `revision_analyzer.py:215` are
one-shot internal calls and stay untouched — stated so the omission reads as a decision.

**FR-20 — the fallback loop.** On a transient throttle the engine sets `ctx.model = _next_id`
(line ~9426) and rebuilds. Sol is `premium`, so its tier-descent chain is `[standard, cheap]` —
**both Claude**. The effort must be dropped on the rebuild. T3's mapping function already does
this because it is model-id-aware; T12 pins it.

**PASS**: a step with an effort reaches `build_model(effort=…)`; `AgentContext` default is `None`;
an `ExecutionContext` with no resolver yields `None` rather than raising.
**Verify**: `./venv/bin/python -m pytest backend/tests/agents/test_create_runner.py -q`

---

## Surface

### T9 — API projection; delete `thinking_supported` (FR-14, SC-06)

**Files**: `backend/app/api/capabilities.py`, `frontend/src/lib/api.ts`,
`frontend/src/store/api/capabilities.ts`

- `ModelCatalogEntry` gains `reasoning_mode: str` and `reasoning_levels: list[str]`, projected
  straight off `m.reasoning`.
- **Delete** `_THINKING_FRAGMENTS` (line ~169) and the `thinking_supported` field. That tuple
  differs from `model_factory`'s by `"opus-4"` under a comment conceding they are "kept in sync
  by grep" — leaving it is how the third source gets created.
- Mirror both on the two TS types; drop `thinking_supported` from both.

**PASS**: `grep -rn "_THINKING_FRAGMENTS\|thinking_supported" backend/ frontend/src/` returns
nothing; `/api/capabilities` carries `reasoning_mode`/`reasoning_levels` for all 12 models.
**Verify**: `./venv/bin/python -m pytest backend/tests/unit/test_capabilities_api.py -q`

### T10 — The Effort select in `CanvasConfigRail` (FR-09, §6.3, §6.4)

**File**: `frontend/src/components/workflow/composer/CanvasConfigRail.tsx`

1. **Move the Model block inside the `!agent.mechanical` guard.** It currently sits *outside*
   both conditionals (line ~834), so a Code step shows a Model select — contradicting its own
   InfoHint, which says a code step has "No prompt, no tools, no model". Pre-existing; fixing it
   here stops Effort and Model disagreeing about whether a Code step has a model.
2. Add the Effort select directly beneath Model, same markup and classes:
   - options from `modelOptions.find(m => m.id === sel.model)?.reasoning_levels ?? []`
   - `<option value="">Default</option>` first — `applyLeverPatch` already deletes on `""`
   - labels: `none` → **Off** on a Claude (`adaptive`/`budget`) model, **None** on an `effort`
     model; `xhigh` → **xHigh**; others capitalised
   - render nothing when `reasoning_levels` is empty
   - **when Model changes, clear an effort the new model does not accept** — otherwise a step
     carries `xhigh` onto Claude and it is dropped silently at the boundary
3. Unset model (`sel.model === ""`) means the workflow default, whose levels are unknown to the
   rail — render no Effort control rather than guessing.

**PASS**: GPT step offers 6 levels + Default; Claude step offers Off/On + Default; Haiku 3.5 and
Code steps offer none; switching GPT→Claude with `xhigh` set clears it.
**Verify**: `cd frontend && npx vitest run src/components/workflow/composer/CanvasConfigRail.effort.test.tsx`

### T11 — `AgentsPopup` + the Analytics row (FR-09, §6.2, FR-14)

**Files**: `frontend/src/components/workflow/AgentsPopup.tsx`,
`frontend/src/components/analytics/AnalyticsPage.tsx`

- `StepSelection` gains `effort?: string` (line ~1380). `applyLeverPatch` needs no change.
- The same Effort select on the levers surface. **Shipping it on one surface only is how FIX-584
  happened** — two copies of the pipeline-label map, both missing `ppt_v2`, because the second
  copy is only updated when someone notices the first was wrong.
- `AnalyticsPage.tsx:826` renders `reasoning_mode` instead of the hardcoded "Adaptive" string.
  That row is currently wrong for Opus 4.5/4.6.

**PASS**: both surfaces offer the same levels for the same step; the Analytics row reads the
model's real mode.
**Verify**: `cd frontend && npx vitest run src/components/analytics/AnalyticsPage.test.tsx`

---

## Acceptance

### T12 — Parity and payload regression guards (SC-02…SC-10, SC-12)

**Files**: `backend/tests/unit/test_model_factory.py`,
`backend/tests/agents/test_bedrock_cache_and_thinking.py`, one frontend test

Assert the **request payload**, never the component state. A test that only checks the select's
value passes on a fully broken feature — which is exactly how ISS-306's Prompt User toggle read
OFF for every gated step while every hop of its write path was wired.

| criterion | assertion |
|---|---|
| SC-02 | Sol + `high` → `{"reasoning":{"effort":"high"}}` |
| SC-03 | Haiku 4.5 + any effort → `thinking`, never `reasoning` |
| SC-04 | Haiku 3.5 → no reasoning field at all |
| SC-05 | **every** catalog model with `effort=None` → byte-identical to pre-change output |
| SC-08 | a GPT id whose fallback rebuilt on Claude sends `thinking` |
| SC-12 | `BEDROCK_PROMPT_CACHE_ENABLED=True` + GPT id → no `cache_control` |

SC-05 is the one that matters most and the easiest to skip: 10 of 12 models are Claude and every
shipped workflow runs on one.

**PASS**: all six rows green; no test asserts only on UI state.
**Verify**: `./venv/bin/python -m pytest backend/tests/unit/test_model_factory.py -q` then
`./venv/bin/python -m pytest backend/tests/agents/test_bedrock_cache_and_thinking.py -q`

### Decision — geo prefixes stay runtime-only (Bilal, 2026-09-22)

**Rejected**: moving Claude to `global.` CRIS. It is available — a live
`list_inference_profiles` on `eu-north-1` returns `global.anthropic.*` for haiku-4-5,
sonnet-4-5, sonnet-4-6, sonnet-5, opus-4-5 and opus-4-6 — but `global.` routes worldwide and
would give up EU data residency for every Claude run. That is the same trade already gating
FR-13, and it was declined.

**Kept**: GEO-01 runtime rewriting, unchanged.

**Changed**: the user no longer picks a geo prefix. Measured on `eu-north-1`:

- The region publishes **20 `global.`, 17 `eu.` and ZERO `us.`** inference profiles.
- All three `us.` catalog ids therefore resolve only because `_normalize_geo_prefix` rewrites
  them. Picking "Claude Sonnet 5 (US)" returned the EU profile — a control that could not do
  what it said.

`selectable_models()` (`model_policy.py`) collapses them for the PICKER only, preferring the
prefix that matches `AWS_REGION`. `ModelCatalog.ids()` / `is_allowed()` / `_VALID_MODEL_IDS`
stay complete, so an AGENT.md or a saved workflow naming `us.…` still validates — which is
why the duplicates were in the catalog to begin with.

### CLOSED — Claude Haiku 3.5 removed (Bilal, 2026-09-22)

`us.anthropic.claude-3-5-haiku-20241022-v1:0` → GEO-01 → `eu.anthropic.claude-3-5-haiku-…`,
which does not exist in `eu-north-1`; nor does a `global.` twin, nor the base foundation model.
Pre-existing and unrelated to this spec — the entry landed 2026-08-14, GEO-01 on 2026-08-27,
so the us. prefix was correct-looking when written and only became unresolvable once the
normalizer arrived.

Removed. Every text/json column in the database was scanned first: **0 rows** referenced it, so
nothing saved is invalidated. Catalog 12 → 11, picker 10 → 9.

`reasoning.mode == "none"` lost its only catalog model but is still a live branch, so its
coverage moved to a synthetic entry (`test_sc04_reasoning_mode_none_sends_no_field`,
`CanvasConfigRail.effort.test.tsx`, `AnalyticsPage.test.tsx`) rather than being deleted with the
model — otherwise the next model needing it ships on an untested branch.

### Live verification — done 2026-09-22, :8001 + :3001

Driven in real `/Applications/Google Chrome.app` against this worktree's own servers, signed in as
`qa-admin@flowinqa.com`. Screenshots in `.playwright-mcp/spec020-0*.png` (main checkout).

| surface | state | result |
|---|---|---|
| Canvas rail | GPT-5.6 Luna | Effort offers Default/None/Low/Medium/High/xHigh/Max |
| Canvas rail | Claude Haiku 4.5 | Effort offers Default/Off/On |
| Canvas rail | Haiku 3.5 | no Effort row at all |
| Canvas rail | Luna `xhigh` → Haiku 4.5 | effort cleared to Default automatically |
| Simple view | GPT-5.6 Sol | Effort offers all six; pill reads "GPT-5.6 Sol" |
| `/api/capabilities` | live | 9 picker rows (11 catalog − 2 geo duplicates), both GPT rows present |
| Canvas rail | model list | Default, then 9 rows alphabetical. No tier, no (EU)/(US); values are inference-profile ids |

Still NOT verified: a real run end to end (spec SC-11 / RISK-09). That needs a fresh
`AWS_BEARER_TOKEN_BEDROCK` and costs money — Bilal's call.

**Do not start this backend with a plain `uvicorn`.** This worktree shares one Postgres with every
other checkout, so `restore_non_terminal_runs()` auto-resumes whatever was in flight anywhere —
it resumed two unrelated runs on the first start here. Use
`scratchpad/run8001.py`, which no-ops that call.

### Acceptance — after T12, not a task

A real run on :8001/:3001 with a GPT model selected and an effort set (spec SC-11 / RISK-09).
§12's live verification drove `ChatBedrockConverse` and `boto3` directly — it never exercised
`build_model` → deepagents → streaming → token accounting. Needs a fresh
`AWS_BEARER_TOKEN_BEDROCK` (~8h life) and is Bilal's call to start.
