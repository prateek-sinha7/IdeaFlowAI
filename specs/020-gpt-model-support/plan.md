# Spec 020 — GPT models on Bedrock, and an Effort dropdown that works for GPT *and* Claude

## Goal

A per-step **Effort** dropdown in the composer, beside the existing Model select, that works
for both families: six real levels on GPT-5.6 (`none` … `max`), on/off on Claude. The options
come from the model's own catalog entry, so the UI never holds a model list.

Two GPT models join the catalog on the way — Sol and Luna — because an effort control with
nothing to exercise it proves nothing.

**Not in this plan:** flipping `BEDROCK_INFERENCE_PROFILE_ID` to Luna (spec FR-13). That single
line is gated on the §3 residency sign-off, which is Bilal's call and still open. Everything
here works with the default unchanged — the GPT models become *selectable*, not *default*.

## The one decision that shapes everything

**The blocker is not the dropdown. It is that GPT requests fail 100% today, and the cause is a
middleware nobody would look at.**

`_BedrockCachePointsMiddleware` (`deep_agent_runner.py:436`) decides whether to inject a Bedrock
`cachePoint` by asking `isinstance(request.model, ChatBedrockConverse)` — a **transport** check.
GPT-5.6 on Bedrock *is* a `ChatBedrockConverse`. Measured live (spec §12.3):

```
FAIL  global.openai.gpt-5.6-luna      with cachePoint   AccessDeniedException
PASS  eu.anthropic.claude-haiku-4-5   with cachePoint   <- control
```

`BEDROCK_PROMPT_CACHE_ENABLED` defaults ON. So **T1 is the cache gate, and nothing else can be
tested end to end until it lands.** Building the dropdown first would produce a control that
looks right and fails on every run — the exact failure shape this codebase keeps being bitten
by (FIX-307's silent-clean validator, ISS-306's toggle that read OFF).

That reframes the whole plan: this is a *capability* change with a dropdown on the end, not a
UI feature with some plumbing.

## The second decision: capability data, not id substrings

Three places currently decide model reasoning behaviour by matching substrings against a model
id, and **two have already drifted** (spec §4.3):

| | |
|---|---|
| `model_factory._ADAPTIVE_THINKING_MODEL_FRAGMENTS` | `("sonnet-5", "opus-5", "fable-5", "mythos-5")` |
| `capabilities._THINKING_FRAGMENTS` | `(…same…, "opus-4")` ← **extra entry** |

The second feeds `thinking_supported` → the Analytics page's **"Thinking: Adaptive"** row, so the
UI already contradicts the runtime about Opus 4.5/4.6. The comment above it concedes the
mechanism: *"kept in sync by grep rather than a shared import"*.

Adding `levels` as a third source would make it worse. So `ModelEntry` gains one field and the
two fragment tuples are **deleted** — this plan removes more per-model branching than it adds.

## Order of work — blocker, then capability, then plumbing, then UI

```
T1  cache gate ........... unblocks everything; GPT runs stop failing
T2  Reasoning capability .. the data both the wire shape and the UI read
T3  mapping function ...... one place builds the reasoning block; 2 tuples deleted
T4  catalog: Sol + Luna ... something to point the dropdown at
T5  ModelPolicy.effort .... authoring type + compiler validation
T6  selections synth ...... how the canvas value reaches the manifest
T7  resolver ............. resolve_effort, tier 2 then tier 4
T8  threading ............ AgentContext -> factory -> runner -> build_model
T9  API projection ....... reasoning_mode/levels out, thinking_supported gone
T10 UI: CanvasConfigRail .. the dropdown itself
T11 UI: AgentsPopup ...... the second authoring surface, or the two disagree
T12 parity + regression ... INV-3 byte-identity, and the SC-12 cache guard
```

T1 first is not sequencing pedantry — it is the only order in which T10 can be *observed* to
work rather than assumed to.

## NEW files (0)

None. Every change lands in a file that already exists. That is a deliberate check on scope:
this feature is one field on a dataclass plus the places that read it.

## MODIFIED files (11)

| file | change |
|---|---|
| `backend/agents/capabilities/model_catalog.py` | `Reasoning` dataclass; `ModelEntry.reasoning` + `supports_prompt_caching`; 12 entries declare both; Sol + Luna added |
| `backend/app/agents/deep_agent_runner.py` | cache middleware gated on the catalog, not `isinstance` (T1); `build_model(effort=…)` at :743 (T8) |
| `backend/app/agents/model_factory.py` | `reasoning_fields()` mapping function; `effort` param; **delete** `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` + `_thinking_type` |
| `backend/agents/workflows/plan.py` | `ModelPolicy.effort: str \| None` |
| `backend/agents/workflows/compiler.py` | `effort` in the `model:` allow-list; validated against that model's own `levels` |
| `backend/agents/workflows/selections.py` | `"effort"` in `_LEVER_KEYS`; synth folds it into the step's `model` block |
| `backend/agents/model_policy.py` | `resolve_effort(step)` — tier 2 then tier 4 |
| `backend/agents/factory.py` | `AgentContext.effort`; passed to the runner |
| `backend/agents/execution_engine/engine.py` | `_resolve_effort`; set on the ctx beside `model=` at :8820 |
| `backend/app/api/capabilities.py` | `reasoning_mode`/`reasoning_levels` on `ModelCatalogEntry`; **delete** `_THINKING_FRAGMENTS` + `thinking_supported` |
| `frontend/src/lib/api.ts` | `CapabilityModelEntry` gains the two fields, drops `thinking_supported` |

## MODIFIED frontend (4)

| file | change |
|---|---|
| `frontend/src/components/workflow/composer/CanvasConfigRail.tsx` | the Effort select; move Model inside the `!agent.mechanical` guard |
| `frontend/src/components/workflow/AgentsPopup.tsx` | `StepSelection.effort`; the same select on the levers surface |
| `frontend/src/components/analytics/AnalyticsPage.tsx` | render `reasoning_mode` instead of the hardcoded "Adaptive" |
| `frontend/src/store/api/capabilities.ts` | the two fields on the store type |

## The mapping, in one table

`reasoning_fields(model_id, effort, max_tokens, disable_thinking)` — the only place a reasoning
block is built.

| mode | `effort` unset (parity) | `effort = "none"` | `effort` = a level |
|---|---|---|---|
| `effort` | *(nothing)* | `{"reasoning":{"effort":"none"}}` | `{"reasoning":{"effort":<lvl>}}` |
| `adaptive` | `{"thinking":{"type":"adaptive"}}` | `{"thinking":{"type":"disabled"}}` | `"on"` → adaptive |
| `budget` | `{"thinking":{"type":"enabled","budget_tokens":N}}` | `{"thinking":{"type":"disabled"}}` | `"on"` → enabled |
| `none` | *(nothing)* | *(nothing)* | *(nothing)* |

Three rules this table encodes, each of which is a bug if broken:

1. **`effort` unset ≠ `effort = "none"`.** Unset means "behave exactly as today" (INV-3 / SC-05).
   `none` means the user explicitly turned reasoning off. Every Claude step currently runs with
   thinking ON at full budget, so conflating them silently changes every existing workflow.
2. **`THINKING_BUDGET_TOKENS = 0` still wins** for the two Claude modes when effort is unset —
   the current `thinking_enabled` predicate is preserved, not replaced.
3. **An unknown model id falls back to `budget`**, not to `none`, with a warn-once log. `none`
   would be the tidier default and would silently stop sending `thinking` for any model missing
   from the catalog — a parity break disguised as a cleanup.

`mode: "none"` on Haiku 3.5 is the **one intentional behaviour change**: it currently receives
`{"type":"enabled","budget_tokens":32767}` and has no extended thinking (spec RISK-04).

## The UI contract

Options come from the entry, never from the component:

```
Model  [ GPT-5.6 Sol      v ]      Model  [ Claude Sonnet 4.6 v ]   Model [ Claude Haiku 3.5 v ]
Effort [ High             v ]      Effort [ On                v ]   (no Effort control)
         Default                            Default                   levels = []
         None Low Medium High               Off
         xHigh Max                          On
```

- `""` = **Default** (unset, send nothing) — mirrors the Model select's existing `<option value="">Default</option>` idiom, and `applyLeverPatch` already deletes a key on `""`, so the reducer needs no change.
- Claude's two levels are labelled **Off / On**; GPT's `none` is labelled **None**. The stored
  value is `none` in both cases — label is presentation, the level is the contract.
- Switching Model re-derives the options and **clears an effort the new model does not accept**,
  so a step cannot carry `xhigh` onto a Claude model and have it silently dropped at the boundary.
- `levels == []` renders no control at all.

## Change budget

| | count |
|---|---|
| new files | 0 |
| modified backend source | 10 |
| modified frontend source | 4 |
| new/modified test files | 5 |
| **id-substring branches deleted** | **2 tuples + 1 helper** |
| lines added to `engine.py` | ~8 (one resolve call + its comment) |
| migrations | 0 |
| workflow manifest changes | 0 |
| default-model changes | **0** — FR-13 is out of scope, see Goal |

No DB migration: `selections` persists as `Record<string, Record<string, unknown>>` JSON, so a
new key is additive and pre-existing rows resolve to `None`.

## Risks and failure modes

**A dropdown that looks right and does nothing.** The single most likely outcome, and this
codebase's signature failure: ISS-306's Prompt User toggle read OFF for every gated step because
routes arrived with qualified ids while nodes were keyed on bare ones — wired end to end, silent,
wrong. Mitigation: T12 asserts the *request payload*, not the component state. A test that only
checks the select's value would pass on a fully broken feature.

**Parity drift on the Claude path.** 10 of 12 catalog models are Claude and every existing
workflow runs on one. If `effort=None` does not reproduce today's request byte for byte, this
change silently alters every run in the product. SC-05 is the guard and it is not optional.

**The two authoring surfaces disagreeing.** `CanvasConfigRail` and `AgentsPopup` both write step
levers. Shipping the select on one is how FIX-584's duplicated pipeline-label map happened — both
copies missing `ppt_v2`, because "the second copy is only ever updated when someone notices the
first was". T11 exists solely to prevent that.

**Catalog lookup by exact id.** `ModelCatalog().get()` is exact-match, and `build_model` receives
a geo-normalized id. All 12 catalog entries are reachable that way — but a future model added
under one geo prefix and invoked under another would fall to the unknown-id path. The warn-once
log is what makes that visible rather than silent.

## Verification

Live Bedrock verification already exists (spec §12) and is re-runnable from the scratchpad with a
fresh `AWS_BEARER_TOKEN_BEDROCK`. It established: both models answer, both call tools, nested
`{"reasoning":{"effort":…}}` is accepted and flat `reasoning_effort` is rejected, both accept
exactly `none low medium high xhigh max`, and cachePoint fails on GPT while passing on Claude.

What it did **not** establish, and T12 cannot either: a full workflow run through
`build_model` → deepagents → streaming → token accounting (spec RISK-09 / SC-11). That needs a
real run on :8001/:3001 and is the acceptance step after T12.

## Deferred

- **FR-13**, the default-model flip — gated on the residency sign-off.
- **langchain-aws 1.7.9**, which unifies `reasoning_effort` across providers and would delete T3's
  mapping function outright. Blocked behind a `langchain-core` 1.4.0 → ≥1.6.3 bump that
  `langchain`, `langgraph`, `deepagents` and `langchain-mistralai` all sit on (spec §7).
- **Long-context pricing** (~2× above 272K input on 1M-context models; spec RISK-05).
- **Run-level effort** in the launch panel. Per-step only.
- **Re-enabling prompt caching for GPT** — it only exists on the Responses API, and we are on
  Converse. T1 disables it for those models; it does not try to recover it.
