# Feature Specification: Mistral as the Free-Tier Eval Provider

**Spec ID**: 004-mistral-eval-provider
**Created**: 2026-07-28 (as `004-groq-eval-provider`)
**Retargeted**: 2026-07-29 — onto Mistral, the provider that survived. See §7.
**Status**: **Implemented and in production use.** Wired into `build_model()`, pinned by every
shipped grading config, and covered by offline tests.
**Stack**: python | fastapi | (no frontend surface)

---

## 1. Problem statement

The eval harnesses need to dispatch **real agents** to be worth anything — a scripted stand-in
proves the machinery works, not that the prompt does. Real dispatch costs money, and the
harnesses are run repeatedly while iterating on a prompt.

So they need a **$0 provider**, reachable **without disturbing any other caller's configuration**.
Specifically, an engineer with `ANTHROPIC_API_KEY` set for local dev must be able to run an eval
against a free model *without* unsetting it, editing `.env`, or otherwise mutating shared
environment state that every other code path also reads.

## 2. What is implemented

### 2.1 The provider chain

`app/agents/model_factory.build_model()` resolves in strict order:

| Tier | Condition | Client |
|---|---|---|
| explicit | `provider="mistral"` passed | `ChatMistralAI`, unconditionally |
| 1 | `ANTHROPIC_API_KEY` set | `ChatAnthropic` (local dev) |
| 2 | Bedrock model id **and** `AWS_REGION` resolve | `ChatBedrockConverse` (production) |
| 3 | `MISTRAL_API_KEY` set | `ChatMistralAI` (free-tier fallback) |
| — | none of the above | `ModelConfigurationError` |

```python
build_model()                      # implicit chain — every existing call site
build_model(provider="mistral")    # forces Mistral regardless of tiers 1 and 2
```

The explicit opt-in is the whole point of this spec: it is keyword-only, defaults to `None`, and
**every existing call site is unaffected** because they all omit it.

### 2.2 Settings surface

`app/core/config.py`:

| Setting | Default | Notes |
|---|---|---|
| `MISTRAL_API_KEY` | `""` | Empty means Mistral is never reachable, by either path |
| `MISTRAL_MODEL_ID` | `mistral-small-latest` | The closest weight-class match to Haiku 4.5 among the free providers surveyed — see [`005/research/`](../005-prompt-eval-scoring/research/candidate.md). Overridable per call via `build_model(model=...)` |

### 2.3 Dependency

`langchain-mistralai==1.1.4` — pinned deliberately, **not** the latest. 1.1.5+ requires
`langchain-core>=1.4.7`, which conflicts with this repo's `langchain-core==1.4.0` pin.
Resolver-verified 2026-07-28.

## 3. Behavioural requirements

- **R-01 — The explicit opt-in overrides everything.** `provider="mistral"` wins over a
  configured Anthropic *or* Bedrock. Tested both ways.
- **R-02 — No silent fallback on a failed opt-in.** `provider="mistral"` with no
  `MISTRAL_API_KEY` raises `ModelConfigurationError` naming the flag. It must never quietly
  resolve to Anthropic — an eval that silently graded a different model than requested is worse
  than one that fails.
- **R-03 — `provider=None` is byte-identical to pre-feature behaviour.** Regression-guarded: with
  the default, behaviour is the same whether or not `MISTRAL_API_KEY` happens to be set, as long
  as an earlier tier resolves.
- **R-04 — Bedrock's "configured" test ignores the `model` override.** Bedrock counts as
  configured only if settings alone resolve a model id + region — otherwise a bare `model=`
  override in a Mistral-only environment would be mistaken for Bedrock config and skip tier 3.
- **R-05 — Only `"mistral"` is honoured as an explicit provider.** `"anthropic"` and `"bedrock"`
  are silently ignored and fall through the implicit chain. The grading package encodes this as
  `HONOURED_PROVIDERS = ("mistral",)` in both `config.py` and `judge.py`, and **hard-fails** a
  run whose rubric pins an unhonourable provider rather than grading with the wrong model.

## 4. Where it is used

| Consumer | How |
|---|---|
| `evals/grading/` | All four shipped configs pin it explicitly: `mistral-small-latest` as the agent under test, `mistral-large-latest` as the judge |
| `evals/hybrid/` | `eval.sh benchmark --provider mistral`, threaded through `live_scenario._resolve_ctx_model` → `build_model(model, provider="mistral")` |

**Why the grading configs pin rather than rely on the chain.** Leaving `provider: null` means
"walk the chain and stop at the first tier that *looks* configured" — and **Bedrock looks
configured even with an expired token**. An unpinned run can therefore silently never reach
Mistral and fail late. Pinning is the only way to know which model actually ran.

## 5. Known limits

- **The free "Experiment" tier uses API inputs and outputs for model training BY DEFAULT.** Opt
  out in the Admin Console's Privacy menu (`console.mistral.ai`) before sending anything you care
  about. Documented at the settings field, not just here.
- **`mistral-small-latest` is not Claude.** It is a weight-class approximation for cost-free
  iteration. A score obtained against it is not comparable to one obtained against Haiku — see
  `005`'s baseline rules.
- **`"anthropic"`/`"bedrock"` are not honoured** (R-05). Writing `provider: anthropic` in a
  config is a no-op that happens to work wherever `ANTHROPIC_API_KEY` is set.

## 6. Tests

Offline, no network, all constructors mocked:

| Suite | Covers |
|---|---|
| `tests/unit/test_model_factory.py` | The full tier matrix: each tier in isolation, Bedrock-wins-over-Mistral ordering, the explicit opt-in overriding Anthropic *and* Bedrock, the loud failure with no key, the `provider=None` regression guard, and `model_identifier()`'s shape fallbacks |
| `tests/unit/test_grading_judge.py` | A pinned-but-uncredentialed judge provider hard-fails |
| `evals/hybrid/common/test_live_scenario_model_resolution.py` | The harness passes `provider="mistral"` through to `build_model` and leaves `provider=None` a pure pass-through |

## 7. History — this spec was originally about Groq

Written on 2026-07-28 as **`004-groq-eval-provider`**, specifying Groq (`langchain_groq.ChatGroq`)
as the free-tier provider, with Mistral added alongside it as a fourth tier.

Groq did not work out and was **removed entirely on 2026-07-29**: the dependency, the
`GROQ_API_KEY`/`GROQ_MODEL_ID` settings, the `provider="groq"` branch, its fallback tier, its
entry in `HONOURED_PROVIDERS`, and its test matrix. Mistral moved from tier 4 to tier 3.

The **design contribution survived intact** — the keyword-only `provider=` opt-in, the
no-silent-fallback rule, and the ordering guarantees were all specified here first and are
unchanged. Only the provider behind them changed, which is why this spec was retargeted rather
than withdrawn.

The provider research that led to both choices is in
[`005/research/`](../005-prompt-eval-scoring/research/README.md).
