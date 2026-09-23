# Feature Specification: GPT model support — OpenAI models on Bedrock, and reasoning as a catalog capability

**Spec ID**: 020-gpt-model-support
**Created**: 2026-09-22
**Revised**: 2026-09-22 — second pass against the code (§4.3, §6, §7 and 14 requirements new or corrected; one requirement in the first draft named the wrong endpoint outright), then a third pass with **live Bedrock verification** (§12). The live run closed RISK-01, RISK-02 and RISK-06, **confirmed RISK-08 as a hard blocker**, and corrected the deployment region
**Status**: NOT STARTED — this branch (`feat/gpt-support`) is intentionally empty of implementation. A throwaway pass proved the mechanics and was reverted; every finding is recorded here so nothing has to be rediscovered. **The core mechanics are now verified live** (§12): both models answer, both call tools, and the effort payload is confirmed
**Root**: `backend/agents/capabilities/model_catalog.py`, `backend/app/core/config.py`, `backend/app/agents/model_factory.py`, `backend/app/agents/deep_agent_runner.py`, `backend/agents/model_policy.py`, `backend/agents/factory.py`, `backend/agents/execution_engine/engine.py`, `backend/agents/workflows/plan.py`, `backend/agents/workflows/compiler.py`, `backend/agents/workflows/selections.py`, `backend/app/api/capabilities.py`, `backend/app/api/settings.py`, `frontend/src/components/workflow/composer/CanvasConfigRail.tsx`, `frontend/src/components/workflow/AgentsPopup.tsx`, `infra/terraform/policies/bedrock-invoke.json`, `infra/terraform/foundation/variables.tf`
**Grounding**: MODEL-01/02/04/05 + D-02 precedence (`agents/model_policy.py` docstring) — the one resolution path · INV-12 — the catalog is the single hand-maintained model list; every picker is a projection over it · GEO-01 (`_normalize_geo_prefix`) · SC-001 — never a hardcoded list in the UI · INV-5 — manifests are pure data, unknown keys are rejected · the existing `thinking` block in `build_model`, which this spec generalises and then deletes
**Evidence**: Bedrock facts from the AWS model cards for [Sol](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-sol.html) and [Luna](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-luna.html), read 2026-09-22. langchain-aws facts from inspecting the 1.7.9 wheel and the installed 1.4.6 package directly. Every code path cited in §4.3, §6 and §7 was read in this worktree at `049a8c3a4`. **§12 records live Converse calls against the real account** — scripts at `scratchpad/gpt_smoke.py`, `cachepoint_check.py`, `levels_check.py`, re-runnable with the bearer token in `backend/.env`.

---

## Clarifications

### Session 2026-09-22

Decisions taken in conversation, each with the reason it is not recoverable from the code.

- **Q: Which GPT models?**
  **A: Sol and Luna. NOT Terra.** The family on Bedrock is Sol (frontier), Terra (balanced), Luna (fast/cheap). Two tiers cover the cost/capability spread; a third adds a row nobody selects.

- **Q: Which model becomes the default?**
  **A: GPT-5.6 Luna**, replacing `eu.anthropic.claude-haiku-4-5-20251001-v1:0` — ~5× cheaper input, ~4× output, 5× the context window.

- **Q: Is "GPT-5.6 Luna max" a separate model?**
  **A: No.** Bedrock publishes ONE id per model; "max" is a reasoning-effort level. The original request asked for "luna 5.6 max"; there is no such inference id.

- **Q: Does Bedrock's Converse API unify reasoning, so we do not have to?**
  **A: No, and that is AWS's design.** Converse unifies `messages`, `system`, `toolConfig` and `inferenceConfig` (maxTokens / temperature / topP / stopSequences). Reasoning sits in `additionalModelRequestFields`, documented as parameters "beyond the base set". Per-family shapes there is what the field is for.

- **Q: Then is there a layer that unifies it?**
  **A: Yes — `langchain-aws`, and ours is too old.** 1.7.9 has a profile registry and a `reasoning_effort` kwarg it translates per family. Our 1.4.6 has no such field, and its 94 profiles include `gpt-oss` but no `gpt-5.6`. See §7.

- **Q: One unified "reasoning effort" control, or separate controls per family?**
  **A: Neither — two fields, Model and Effort.** `Model Name` (Claude Haiku / GPT Sol / GPT Luna) and `Effort` (None / Low / Medium / High / xHigh / Max). Framing it as one compound "reasoning effort" concept was an error driven by langchain's naming.

- **Q: Token budget in the UI?**
  **A: No. Always maximum.** `THINKING_BUDGET_TOKENS = 32767`, `MAX_OUTPUT_TOKENS = 32768`, and `build_model` already clamps to `max_tokens - 1` — "always max" is *already the behaviour*. Removing it from the UI changes nothing.

- **Q: Is the per-family mapping branching in `model_factory`, or data on the model?**
  **A: Data — a capability on `ModelEntry`.** Precedent: `ModelEntry.vision`. It also deletes existing fragile code — see §4.3, which is worse than first assessed.

- **Q: Effort vocabulary — ours or the provider's?**
  **A: The provider's, unchanged.** `none/low/medium/high/xhigh/max` is exactly GPT-5.6's set, and Sonnet 5's set plus `none`.

---

## 1. Problem

Every run resolves to `eu.anthropic.claude-haiku-4-5-20251001-v1:0` — tier 5b of the D-02 chain, the value every agent gets when no override, step, spec, workflow or session model is set, which is today's state for every run.

1. **Cost.** Haiku 4.5 is $1.00 / $5.00 per 1M. GPT-5.6 Luna is $0.20 / $1.20.
2. **Context.** Haiku 4.5 is 200K. Both GPT-5.6 models are 1M.
3. **No reasoning control.** Extended thinking is one global setting applied identically to every Claude step in every workflow. A step that writes a spec and a step that renames a file get the same 32767-token budget.

And a structural problem the first one exposes: **per-model behaviour is decided by matching substrings against model ids, in more than one place, and those places have already drifted apart.** §4.3.

---

## 2. The models

**The deployment region is `eu-north-1` (Stockholm)**, set in `backend/.env`. `config.py:135` carries `eu-central-1` as its *default*, which the env overrides — an earlier revision of this spec was written against the default and was wrong throughout. The availability conclusion is unchanged: `eu-north-1` is also Global-CRIS-only for both models, and `_REGION_TO_GEO_PREFIX` maps it to `eu.` as expected.

Both reachable from `eu-north-1` **only** as Global cross-region inference profiles.

| | GPT-5.6 Sol | GPT-5.6 Luna |
|---|---|---|
| Bedrock model id | `openai.gpt-5.6-sol` | `openai.gpt-5.6-luna` |
| **Inference id (ours)** | **`global.openai.gpt-5.6-sol`** | **`global.openai.gpt-5.6-luna`** |
| Geo ids published | `us.` , `in.` — **no `eu.`** | `us.` , `in.` — **no `eu.`** |
| Context window | 1M | 1M |
| Converse on `bedrock-runtime` | yes | yes |
| Input modalities | text, image | text, image |
| Structured outputs | **no** | yes |
| Server-side tool use | no | no |
| Count tokens | no | no |
| Prompt caching | Responses API only | Responses API only |
| Price — Global CRIS, ≤272K in | $4.00 / $20.00 per 1M | $0.20 / $1.20 per 1M |
| Price — long context (>272K in) | $8.00 / $30.00 per 1M | $0.40 / $1.80 per 1M |
| Catalog placement | `powerful` / `premium` | `fast` / `cheap` |

**Long-context pricing is not modelled.** `Pricing` carries one input rate. Above 272K input both bill ~2×, and a 1M-context model will cross that line. RISK-05.

---

## 3. The residency decision — blocks deployment, not implementation

**From `eu-north-1` there is no EU-resident way to run either model.**

| Inference option (`bedrock-runtime`) | Sol | Luna |
|---|---|---|
| In-Region | no | no |
| Geo CRIS (EU) | no | no |
| **Global CRIS** | **yes — the only option** | **yes — the only option** |

Today's default is an EU geo profile fanning out only across the seven EU regions pinned in `bedrock-invoke.json`. Global CRIS routes anywhere. Making Luna the default moves **every run's prompts and outputs out of the EU** — a compliance decision, recorded as an ADR when taken.

Nothing else here depends on it. Only the change of the **global default** carries the consequence, and it is one line (FR-13).

---

## 4. Reasoning as a catalog capability

### 4.1 The type

```python
@dataclass(frozen=True)
class Reasoning:
    mode: str                  # "effort" | "adaptive" | "budget" | "none"
    levels: tuple[str, ...]    # what a UI may offer; () = no control at all
```

`ModelEntry` gains `reasoning: Reasoning`.

| mode | wire shape (`additionalModelRequestFields`) | who |
|---|---|---|
| `effort` | `{"reasoning": {"effort": <level>}}` | GPT-5.6 Sol, Luna |
| `adaptive` | `{"thinking": {"type": "adaptive"}}` / `{"type": "disabled"}` | Claude Sonnet 5 |
| `budget` | `{"thinking": {"type": "enabled", "budget_tokens": N}}` / `{"type": "disabled"}` | Claude Haiku 4.5, Sonnet 4.5/4.6, Opus 4.5/4.6 |
| `none` | *no field sent* | Claude Haiku 3.5 |

### 4.2 The catalog, filled in

| model | mode | levels |
|---|---|---|
| `global.openai.gpt-5.6-sol` | `effort` | none low medium high xhigh max |
| `global.openai.gpt-5.6-luna` | `effort` | none low medium high xhigh max |
| `eu.anthropic.claude-sonnet-5` / `us.` | `adaptive` | none on |
| `eu.anthropic.claude-haiku-4-5-…` / `us.` | `budget` | none on |
| `eu.anthropic.claude-sonnet-4-5-…` | `budget` | none on |
| `eu.anthropic.claude-sonnet-4-6` | `budget` | none on |
| `eu.anthropic.claude-sonnet-4-…` | `budget` | none on |
| `eu.anthropic.claude-opus-4-5-…` | `budget` | none on |
| `eu.anthropic.claude-opus-4-6-v1` | `budget` | none on |
| `us.anthropic.claude-3-5-haiku-…` | `none` | () |

**Why Claude rows are `none on`.** With the budget pinned at maximum, Low through Max produce byte-identical requests on a `budget` model, and `adaptive` accepts no level. Six labels for two behaviours is a control that lies. Sonnet 5 gains real levels after the §7 upgrade, by changing one catalog row.

### 4.3 There are THREE sources of this knowledge today, and two have already drifted

This is the finding that most strengthens the design, and the first draft understated it.

**Source 1** — `backend/app/agents/model_factory.py:277`:
```python
_ADAPTIVE_THINKING_MODEL_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5")
```

**Source 2** — `backend/app/api/capabilities.py:169`:
```python
# Mirrors the _ADAPTIVE_THINKING_MODEL_FRAGMENTS tuple in model_factory.py
# — kept in sync by grep rather than a shared import
_THINKING_FRAGMENTS = ("sonnet-5", "opus-5", "fable-5", "mythos-5", "opus-4")
```

**They are not in sync.** Source 2 carries `"opus-4"`; source 1 does not. The comment concedes the mechanism ("kept in sync by grep"), and it has already failed — exactly the failure mode FIX-584 fixed for the duplicated pipeline-label map, where both copies were missing `ppt_v2` because "the second copy is only ever updated when someone notices the first was".

**It is user-visible.** Source 2 feeds `ModelCatalogEntry.thinking_supported`, which `AnalyticsPage.tsx:826` renders as a **"Thinking: Adaptive"** row. So the Analytics page currently tells a user that Opus 4.5 and Opus 4.6 use adaptive thinking, while `build_model` sends them `{"type": "enabled", "budget_tokens": …}`. One of those two is wrong about a shipped model.

Source 2's comment also says the fragments mean `effort="max" in build_model` — `build_model` has no `effort` parameter. The comment documents a function signature that does not exist.

**Source 3** is this spec's new `levels`. Adding it without collapsing 1 and 2 would make three.

`ModelEntry.reasoning` replaces all three. `thinking_supported` is **removed** from `ModelCatalogEntry`, not left alongside — FR-14.

### 4.4 `mode: "none"` closes a live defect

`thinking_enabled` is computed with no model check whatsoever, so a Claude Haiku 3.5 step receives `{"type":"enabled","budget_tokens":32767}` — and 3.5 Haiku has no extended thinking. Whether Bedrock rejects or silently ignores that is **unverified**; the capability makes it impossible by construction. RISK-04.

---

## 5. Requirements

### Catalog and mapping

**FR-01 — Catalog carries both GPT models.** Full `ModelEntry` field sets, `vision=True`, Global-CRIS pricing. Terra is not added.

**FR-02 — `ModelEntry.reasoning` exists and every entry declares it explicitly.** No silently-applied default; the catalog test asserts presence on all entries.

**FR-03 — One mapping function.** A single `(mode, level, max_tokens) -> dict | None` in `model_factory` is the only place a reasoning wire shape is constructed. `_ADAPTIVE_THINKING_MODEL_FRAGMENTS` and `_thinking_type` are **deleted**.

**FR-14 — `thinking_supported` is removed and its consumer re-pointed.** `_THINKING_FRAGMENTS` deleted from `capabilities.py`; `ModelCatalogEntry` exposes `reasoning_mode` + `reasoning_levels` projected from the catalog; `AnalyticsPage.tsx:826` renders the mode rather than a hardcoded "Adaptive". Failing to do this leaves the drift of §4.3 in place with a third source beside it.

### Authoring, persistence, resolution

**FR-04 — Effort is per-step.** `ModelPolicy` gains `effort: str | None`. `None` means "send nothing" and must stay byte-identical to current behaviour — distinct from the level `"none"`, which explicitly disables reasoning.

**FR-05 — Compiler validates effort.** An effort outside the model's `levels` is a `CompilerError` naming the step and the valid set. `_compile_model_policy`'s `allowed` key set gains `effort`; unknown keys inside `model:` keep failing (INV-5).

**FR-15 — The selections synth carries effort into the model block.** The authoring path is `StepSelection` → `selections.py` → raw step dict → compiler. Concretely: `"effort"` joins `_LEVER_KEYS` (line 43), and a synth branch beside the existing `model` one (line 123) folds it in:
```python
effort = sel.get("effort")
if effort is not None:
    step.setdefault("model", {})["effort"] = effort
```
A key absent from `_LEVER_KEYS` is carried verbatim onto the raw step and rejected by the compiler's strict-key check, so omitting this is a hard failure, not a silent drop. **No `_ALLOWED_STEP_KEYS` change** — effort lands *inside* the `model` block, not as a top-level step key.

**FR-16 — No DB migration.** `selections` persists as `Record<string, Record<string, unknown>>` JSON. Adding a key is additive, and pre-existing rows without it resolve to `None` (FR-04). This is confirmed, not assumed.

**FR-06 — Resolution mirrors D-02 where it applies.** `ModelResolver.resolve_effort(step)` returns step effort, else workflow effort, else `None`. No tier-1 override, no AGENT.md tier, no session tier — nothing writes those, and inventing them is three untested paths. *(Verified: the canvas writes tier-2 `step.model` via the selections synth, not tier-1 `model_overrides`.)*

**FR-17 — The resolver-absent path is preserved.** `_resolve_model` falls back to the threaded `model_id` when `ectx.model_resolver is None` (direct `_run_agent` invocations that bypass `execute()`). Effort resolution needs the same guard and must yield `None` there, not raise.

### Threading and runtime

**FR-18 — The effort reaches `build_model`.** The path is `engine._resolve_effort` → `AgentContext.effort` → `create_runner` → `DeepAgentRunner` → `build_model(effort=…)`, alongside the existing `model=` threading at `engine.py:8820`. The first draft specified the resolver and the mapping function but never said how the value crosses between them.

**FR-19 — Only the agent path carries effort.** There are three `build_model` call sites: `deep_agent_runner.py:743` (the agent graph — carries effort), `cached_invoke.py:168` and `revision_analyzer.py:215` (one-shot internal calls — do not). Stated so the omission reads as a decision rather than an oversight.

**FR-07 — Effort is dropped, not forwarded, for a model that cannot take it.** Enforced at the mapping function and logged.

**FR-20 — The mid-run fallback re-resolves effort.** On a transient throttle the engine sets `ctx.model = _next_id` and rebuilds the runner (`engine.py:9426`). Sol is `premium`, so its tier-descent chain is `[standard, cheap]` — **both Claude**. A GPT step that falls back therefore rebuilds on a model of a different family, and its effort must be dropped on the rebuild rather than carried. FR-07 covers this only because the mapping is model-id-aware; a test must pin it.

**FR-21 — Prompt caching becomes capability-gated. THIS IS A HARD BLOCKER, VERIFIED.** `_BedrockCachePointsMiddleware` (`deep_agent_runner.py:436`) injects `cache_control` for **any** `ChatBedrockConverse` instance — a *transport* check, and GPT-5.6 on Bedrock is a `ChatBedrockConverse`. Measured live (§12.3):

```
FAIL  global.openai.gpt-5.6-luna      with cachePoint
      AccessDeniedException: "You invoked an unsupported model or your
                              request did not allow prompt caching."
PASS  eu.anthropic.claude-haiku-4-5   with cachePoint      <- control
```

`BEDROCK_PROMPT_CACHE_ENABLED` defaults **ON**, so with today's code **every GPT request fails with AccessDeniedException**. Not a degradation — a total failure. The gate becomes a catalog capability (`supports_prompt_caching`), not another id check. *The first draft called caching "out of scope"; it is the single thing standing between this feature and working at all.*

**FR-22 — Effort is observable after the fact.** A run currently records `model_id` on `agent_complete` but nothing about reasoning. Two runs of the same workflow at different efforts are indistinguishable in analytics while differing materially in cost. Record the resolved effort alongside the model id.

### Infrastructure

**FR-11 — IAM permits the OpenAI models.** A statement covering `openai.*` foundation-model ARNs, the `global.openai.*` inference profile, and `bedrock:InvokeModel` on `project/default` (an extra requirement AWS documents for these models). The Claude statement is untouched.

**FR-12 — Terraform validation accepts the new prefix.** `foundation/variables.tf` validates `bedrock_model_id` against `anthropic.` / `eu.anthropic.` / `us.anthropic.` only. With `use_inference_profile_for_app = true` this variable receives the profile id, so without a `global.openai.` arm `terraform plan` fails before rendering IAM.

**FR-13 — The default model change is one line and separable.** `BEDROCK_INFERENCE_PROFILE_ID`. Landable and revertable independently, because it is the only part gated on §3.

### Key entities

- **`Reasoning`** — `mode` + `levels`, kernel-pure data on `ModelEntry`.
- **`ModelPolicy.effort`** — the authored per-step value; `None` when unset.
- **`REASONING_EFFORT_LEVELS`** — the canonical vocabulary. Must live in the kernel (`agents/workflows/plan.py`): the compiler validates against it and **may not import `app.*`** under the import-linter contract, while `model_factory` (which is `app.*`) validates against the same list.

---

## 6. UI — corrected, and wider than the first draft said

### 6.1 The first draft named the wrong endpoint

It claimed `AVAILABLE_MODELS` (`/api/settings`) feeds the canvas. **It does not.** There are two projections of the catalog and the composer uses the other one:

| projection | endpoint | shape | feeds |
|---|---|---|---|
| `AVAILABLE_MODELS` | `/api/settings` | `{id, name, description, tier}` | account-level default-model picker |
| `model_catalog` | `/api/capabilities` | `ModelCatalogEntry` (adds `cost_class`, `provider`, `context_window`, `user_allowed`, four pricing rates, `thinking_supported`) | **the composer canvas**, via `useAgentCapabilities` → `CanvasView` → `CanvasConfigRail` |

`reasoning_mode` / `reasoning_levels` go on `ModelCatalogEntry` (FR-14). Whether the account-level picker also needs them depends on whether a run-level effort is ever added; it is out of scope here, so `AVAILABLE_MODELS` is untouched.

### 6.2 Two surfaces author step levers, not one

`CanvasConfigRail` (canvas) and `AgentsPopup` (the "Advanced levers" list view) both consume `useAgentCapabilities` and both write through the shared `applyLeverPatch` reducer. **Effort must appear on both**, or the two surfaces disagree about a step — the same duplicated-surface failure FIX-584 fixed. `applyLeverPatch` needs no change: it deletes a key on `""`, which is exactly the "unset" idiom.

### 6.3 The Model select renders for Code steps — pre-existing

In `CanvasConfigRail`, `{agent.mechanical && (…)}` (line 760) wraps the Code-step picker and `{!agent.mechanical && (…)}` (line 794) wraps Design context, closing at 832. **The Model block at 834 is outside both**, so a mechanical step shows a Model select — contradicting its own InfoHint, which states a Code step has "No prompt, no tools, no model".

Effort must sit inside the `!agent.mechanical` guard. That leaves a choice: move Model inside too (fixes the pre-existing bug, slightly widens the diff) or leave it (Model and Effort visibly disagree about whether a Code step has a model). **Recommendation: move it, and say so in the commit** — this is a two-line change to an inconsistency this spec would otherwise make more visible.

### 6.4 The unset idiom

The Model select uses `value={sel.model ?? ""}` with `<option value="">Default</option>`. Effort mirrors it exactly: `""` = Default (unset, send nothing), distinct from the level `none` (explicitly disable). `applyLeverPatch` already deletes the key on `""`.

### 6.5 Shape

```
Step: screen-planner                      Step: spec-writer            Step: title-namer
  Node type [ AI agent        v ]           Node type [ AI agent  v ]    Node type [ AI agent v ]
  Model     [ GPT-5.6 Sol     v ]           Model  [ Sonnet 4.6   v ]    Model [ Haiku 3.5    v ]
  Effort    [ High            v ]           Effort [ On           v ]    (no Effort - levels
            none low medium high                   none on                 is empty)
            xhigh max
```

Options are data from the model's catalog entry. Adding a model, or upgrading the library so Sonnet 5 gains real levels, needs no frontend change. Changing the Model must re-derive the options and clear an effort not valid for the new model.

### 6.6 Open UI questions

- **`CanvasNode` model pill.** `shortModel()` renders the model on the node face. Should effort appear there too? Undecided; leaning no — the pill is already tight.
- **Copy for `None`.** Every Claude step today runs thinking ON at full budget, so selecting `None` is a real change to how it runs, not a return to a default. It must never be the initial value for an unset step.

---

## 7. The langchain-aws situation

1.7.9's `ChatBedrockConverse` carries a model-profile registry and a single `reasoning_effort` kwarg it translates per family. That is the correct layer, and using it deletes FR-03's mapping function.

Our pin is **1.4.6**, which has no `reasoning_effort` field — only `additional_model_request_fields` — and 94 profiles including `gpt-oss` but **no `gpt-5.6`**. This is [langchain-aws#1262](https://github.com/langchain-ai/langchain-aws/issues/1262), fixed by PR #1266.

What 1.7.9 would give us:

| model | `reasoning_effort_levels` in 1.7.9 |
|---|---|
| `global.openai.gpt-5.6-sol` / `-luna` | none low medium high xhigh max |
| `eu.` / `us.anthropic.claude-sonnet-5` | low medium high xhigh max |
| every other model in our catalog | — none — |

**The cascade is the cost.** 1.7.9 requires `langchain-core>=1.6.3` and `boto3>=1.43.64`; we pin `langchain-core==1.4.0` and `boto3==1.43.2`. `langchain-core` is pinned deliberately — `requirements.txt` records `langchain-mistralai` held at 1.1.4 specifically to stay compatible — and `langchain`, `langgraph` and `deepagents` all sit on that floor.

**Decision: build the mapping now, upgrade separately.** A `langchain-core` bump on the agent runtime should not ride in on the back of a dropdown. When it happens, FR-03's function is deleted and the catalog's `effort` rows extend to Sonnet 5.

---

## 8. Out of scope

- **GPT-5.6 Terra.**
- **A real OpenAI provider.** These arrive over the same `bedrock-runtime` Converse transport. `ModelEntry.provider` stays a stored field nothing branches on.
- **Per-step thinking *budget*.** Effort only; the budget stays global and maximal.
- **Long-context pricing.** RISK-05.
- **Run-level effort in the launch panel.** Per-step only. `ModelPolicy.effort` at workflow level exists as a resolution tier with no UI.
- **Enabling prompt caching for GPT models.** Out of scope; *disabling* it for them is FR-21 and is not optional.

---

## 9. Success criteria

- **SC-01** Both GPT models appear in the canvas model dropdown, selectable per step, with no frontend model list edited.
- **SC-02** A step on Sol with Effort=High produces exactly `{"reasoning": {"effort": "high"}}`, by test.
- **SC-03** The same step switched to Haiku 4.5 sends `thinking`, never `reasoning`, by test.
- **SC-04** A Haiku 3.5 step sends no reasoning field at all.
- **SC-05** Every step with no effort set produces a request byte-identical to today's (INV-3 parity).
- **SC-06** `_ADAPTIVE_THINKING_MODEL_FRAGMENTS`, `_thinking_type` and `_THINKING_FRAGMENTS` no longer exist, and **no file outside the catalog decides model behaviour by matching an id substring.** A grep for each name returns nothing.
- **SC-07** A manifest declaring an effort outside a model's `levels` fails to compile, naming the step.
- **SC-08** A GPT step throttled into its fallback chain rebuilds on a Claude model and sends `thinking`, not `reasoning`, by test.
- **SC-09** No `cache_control` is injected for a GPT model.
- **SC-10** Effort set in the canvas survives save → reload → launch, and the same value appears in both `CanvasConfigRail` and `AgentsPopup`.
- **SC-11** **One live workflow run** on a GPT model completes end to end through the real stack. Still open: §12 proved the *API* answers, calls tools and takes an effort, but drove `ChatBedrockConverse` and `boto3` directly — not `build_model` → deepagents → streaming → token accounting. RISK-09.
- **SC-12** With `BEDROCK_PROMPT_CACHE_ENABLED=true` (the default), a GPT run does **not** raise `AccessDeniedException`. This is the regression guard for the only confirmed blocker; it fails today.

---

## 10. Risks

**RISK-08 — Prompt-cache injection breaks GPT runs outright. CONFIRMED, and now the only hard blocker in the code.** FR-21, §12.3. Not a new feature misbehaving — existing middleware, ON by default, acting on new models, producing `AccessDeniedException` on 100% of GPT requests. Nothing else can be tested end to end until it is gated.

**RISK-01 — ~~Tool calling on GPT-5.6 is unproven~~ CLOSED.** Verified live on **both** models (§12.2): `get_weather` invoked with `{'city': 'Berlin'}` via Converse `toolConfig`. The model card's "server-side tool use: no" is indeed a different feature from client-side tool calling, as suspected. This was the highest-risk unknown and it is now retired — though note it proves the *API* supports tool calling, not that the full deepagents loop is happy over many turns (SC-11).

**RISK-02 — ~~The `reasoning` payload shape is unverified~~ CLOSED, with discriminating evidence.** Verified live (§12.1, §12.4): nested `{"reasoning": {"effort": …}}` is accepted; flat `reasoning_effort` is **rejected** with `unknown_parameter`. The rejection matters more than the acceptance — it rules out the alternative rather than merely tolerating our guess.

**RISK-06 — ~~Model access may not be enabled~~ CLOSED.** Both models answer from `eu-north-1`. Note the credential that works is `AWS_BEARER_TOKEN_BEDROCK`; the static `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `backend/.env` are stale (`InvalidClientTokenId`) and the bearer token is short-lived — it expires ~8h after issue, so re-verification needs a fresh one.

**RISK-03 — No fallback chain for the default.** `cost_class="cheap"` derives an empty chain, so a Luna failure has nowhere to descend. Haiku had the same property, so not a regression — but as the *default*, an unavailable Luna fails every run rather than some. A fallback to another family also silently changes which reasoning mode applies (FR-20).

**RISK-04 — Haiku 3.5 may already receive an invalid `thinking` field.** Pre-existing; `mode: "none"` fixes it. Unverified whether Bedrock rejects or ignores.

**RISK-05 — Long-context under-costing**, ~2× above 272K input on 1M-context models. `Pricing` cannot express it.

**RISK-09 — The live verification used the bearer-token path, not the app's full stack.** §12 drove `ChatBedrockConverse` and raw `boto3.converse` directly. It did **not** exercise `build_model`'s provider selection, the deepagents graph, streaming, or token accounting. A GPT run could still fail somewhere between those and the API. SC-11 remains open.

**RISK-07 — The IAM statement is not region-pinned.** The Claude statement carries an EU-only `aws:RequestedRegion` condition; a Global CRIS profile routes worldwide, so that condition would deny it and the new statement omits it. That trades away a residency control and needs the §3 sign-off.

---

## 11. Verified non-issues

Checked in this worktree at `049a8c3a4`, recorded so they are not re-investigated.

- **Structured outputs.** Sol does not support them, but the codebase never uses them — no `with_structured_output`, `response_format` or `structured_output` call anywhere in `backend/app` or `backend/agents`. JSON correctness is enforced *after* the write by `ValidatingFilesystemBackend`, not by a provider feature.
- **Model allow-list at ingress.** `_VALID_MODEL_IDS = set(ModelCatalog().ids())` (`settings.py:58`) is derived, so new catalog models are accepted with no edit.
- **Entitlements.** `can_use_model` keys off `cost_class`, also derived. Consequence, stated rather than changed: **Luna (`cheap`) is available on every tier including `basic`** — correct for a default — and **Sol (`premium`) is blocked on `basic`**, consistent with the Opus models.
- **Vision gating.** `_validate_images` requires every effective run-level model to be `vision=True`; both GPT models are.
- **Geo normalisation.** `_normalize_geo_prefix` passes `global.` through untouched (`model_policy.py:111`), and `_PREMIUM_PREFIXES` excludes it, so no +10% regional premium is applied — correct for Global CRIS. No code change needed for either.
- **Model access, IAM and quota** (live, §12). Both models answer from `eu-north-1` on the current IAM identity, with **no `bedrock-invoke.json` change applied** — so FR-11/FR-12 are needed for the *deployed* role, not for the developer credential used here. Do not read §12 as evidence the terraform policy is correct.
- **Credential shape.** `AWS_BEARER_TOKEN_BEDROCK` is the working credential; the static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in `backend/.env` are stale (`InvalidClientTokenId`). The bearer token decodes to an expiry ~8h out via the repo's own `decode_bedrock_bearer_token_expiry`, and `preflight_check_provider` already fails a launch cleanly when it lapses.

---

## 12. Live verification — 2026-09-22, `eu-north-1`

Real Converse calls against the production account, via `AWS_BEARER_TOKEN_BEDROCK`. Scripts are in the session scratchpad and re-runnable with a fresh token.

### 12.1 `ChatBedrockConverse`, the app's own client — `global.openai.gpt-5.6-luna`

```
PASS  plain call                          'OK'
PASS  tool calling                        1 call: get_weather args={'city': 'Berlin'}
PASS  nested {"reasoning":{"effort":"high"}}   accepted
FAIL  flat  {"reasoning_effort":"high"}        ValidationException:
          unknown_parameter — "Unknown parameter: 'reasoning_effort'."
```

### 12.2 Tool calling on both models — raw Converse `toolConfig`

```
PASS  global.openai.gpt-5.6-luna    toolUse: get_weather {'city': 'Berlin'}
PASS  global.openai.gpt-5.6-sol     toolUse: get_weather {'city': 'Berlin'}
```

### 12.3 cachePoint — the decisive RISK-08 test, with a control

```
PASS  global.openai.gpt-5.6-luna      no cachePoint
FAIL  global.openai.gpt-5.6-luna      with cachePoint    AccessDeniedException
PASS  eu.anthropic.claude-haiku-4-5   no cachePoint
PASS  eu.anthropic.claude-haiku-4-5   with cachePoint    <- control passes
```

The Claude control is what makes this conclusive: the test harness is correct, and the failure is specific to the model family.

### 12.4 Effort levels — asked of Bedrock rather than read off the model card

```
global.openai.gpt-5.6-luna   accepted: none low medium high xhigh max
                             rejected: turbo (ValidationException)
global.openai.gpt-5.6-sol    accepted: none low medium high xhigh max
                             rejected: turbo (ValidationException)
```

Two consequences. The catalog's `levels` for both models are confirmed exactly as specified in §4.2 — and Bedrock validates the level itself, so FR-05's compile-time check is **defence-in-depth with a better error message**, not the only thing standing between a typo and a bad request.

### What this did NOT prove

See RISK-09. These are direct API calls, not runs through `build_model` → deepagents → streaming → token accounting. SC-11 is still open.

---

## Assumptions

- `eu-north-1` remains the deployment region (set in `backend/.env`; `config.py`'s default of `eu-central-1` is overridden). Every §2/§3 availability claim is region-specific.
- `MAX_OUTPUT_TOKENS` stays 32768. "Budget is always maximum" is a no-op *because* `THINKING_BUDGET_TOKENS` (32767) already equals `max_tokens - 1`; raising the output ceiling without revisiting this silently changes Claude thinking budgets.
- Bedrock facts are accurate as of 2026-09-22. Model cards change; re-read before relying on pricing or the availability matrix.

---

## Local environment

This branch develops against **:8001 (backend)** and **:3001 (frontend)**, separate from the main checkout's :8000/:3000. `compile_for_run` is `lru_cached`, so any backend Python or `workflow.yaml` change needs a genuine restart, not a reload.
