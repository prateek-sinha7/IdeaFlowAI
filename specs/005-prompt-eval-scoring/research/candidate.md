# Candidate — Free Providers to Integrate for Eval Runs (≥1,000 req/day, $0 cost)

Derived from `providers.md` + `model_comparison.md` in this folder, purpose-built for **running
our eval harness** (`backend/evals/hybrid/`, driven via `./evals/hybrid/eval.sh`) against free models as a
zero-cost comparison point alongside real `claude-haiku-4-5-20251001` (no-thinking) runs.

**Hard filters applied:**
1. **$0 cost, no purchase required** — anything that needs a paid top-up to unlock its useful
   tier is excluded, even if the tokens themselves are then free.
2. **≥1,000 requests/day** — our eval suites run many scenarios, often with retries/fix-loops
   (see the prototype build loop's bounded fix-loop in `CLAUDE.md`), so a provider needs daily
   headroom, not just a generous per-minute rate.
3. **Tool calling that actually works** — every pipeline agent is a `deepagents` graph whose only
   interface to the sandbox is native tool calls (`write_file`/`edit_file`/etc.). A model/provider
   pairing without solid `bind_tools` support can't run our eval scenarios at all, full stop.

## The constraint, applied to each provider

| Provider | $0, no purchase? | ≥1,000 req/day? | Verdict |
|---|---|---|---|
| **Groq** | Yes — no card, no minimum spend | Yes — reported ~1,000–14,400 req/day depending on model | **In** |
| **Cerebras** | Yes — no card | Yes — ~1M tokens/day free, request ceiling far above 1,000/day in practice | **In** |
| **Mistral (La Plateforme, "Experiment" tier)** | Yes, **$0** — but requires opting your prompts/data into Mistral's training use to unlock the higher quota | Yes — ~1B tokens/month reported at ~2 RPM ⇒ up to ~2,880 req/day theoretical, comfortably above 1,000/day for sequential eval runs | **In**, with the training opt-in noted so you go in eyes-open |
| **Google AI Studio (Gemini Flash)** | Yes — no card | Unclear/model-dependent — RPD is set per Gemini model and reshuffles across versions; needs a live check | **Conditional** — verify current RPD before relying on it for a full eval sweep |
| **OpenRouter** | **No** — bare free tier is 50 req/day; the 1,000/day tier requires having purchased ≥$10 of credits | n/a | **Excluded** — this is a paid unlock, not a free one |
| **Cohere (Trial)** | Yes | **No** — ~1,000 calls **per month**, not per day | **Excluded** — fails the volume bar outright |

So the **free, eval-ready set is: Groq, Cerebras, and Mistral**, with Gemini Flash as a fourth
pending a live rate-limit check. OpenRouter and Cohere are dropped entirely — the former only
clears the bar behind a paid top-up, the latter doesn't clear it at all.

---

## Recommendation: integrate **Groq**, **Cerebras**, and **Mistral**

### Groq — primary, for fast iteration

- Genuinely $0, cleanest integration: `langchain-groq` (`ChatGroq`) is a maintained LangChain
  package with first-class `bind_tools`.
- Fastest inference of the three — best for running a full eval sweep quickly and iterating on
  prompt changes without waiting on token throughput.

### Cerebras — for token-heavy eval scenarios

- Genuinely $0, no new dependency needed — it's OpenAI-compatible, so
  `ChatOpenAI(base_url="https://api.cerebras.ai/v1", api_key=...)` works as a drop-in using a
  package we already depend on.
- Highest raw daily token ceiling (~1M/day) — best fit for long-context or multi-task eval
  scenarios (e.g. the `prototype_multi_issue_repair` style scenario with 10 bugs bundled into one
  run) that burn tokens fast regardless of request count.

### Mistral — closest weight-class match, worth the opt-in

- You've said the training opt-in is acceptable, which unlocks Mistral as a genuinely useful
  comparable: `mistral-small-latest` is the **closest same-weight-class model to Haiku** of
  anything free (see `model_comparison.md`), rather than an oversized reference point like
  Llama 3.3 70B.
- `langchain-mistralai` (`ChatMistralAI`) is maintained with working `bind_tools`.
- Caveat carried over from `providers.md`: don't send anything proprietary/sensitive through this
  tier given the training opt-in — fine for eval scenario prompts, not for real user data.

### Gemini Flash — hold pending verification

Worth adding once you confirm its live RPD (`ai.google.dev/gemini-api/docs/rate-limits`) clears
1,000/day for whichever Flash model is on free tier that week — it's the closest *positioning*
match to Haiku (Google's own "fast, non-reasoning" tier), so it's a good fourth data point, just
not one to lead with until the number is confirmed.

---

## Models to try, in priority order for eval runs

| Priority | Model | Provider | Why this one for evals |
|---|---|---|---|
| 1 | `mistral-small-latest` | Mistral | Closest weight-class match to Haiku — the fairest "is our prompt actually good, not just Haiku-flattering" comparison. |
| 2 | `llama-3.3-70b-versatile` | Groq | Strong general-purpose free model, fast iteration; treat results as an "upper bound" since it's bigger than Haiku, not same-class. |
| 3 | `gemma2-9b-it` | Groq | Smallest/fastest model on Groq, closest *size* match to Haiku on that provider — good for quick smoke-testing a prompt tweak across many scenarios before a full sweep. |
| 4 | `llama-3.3-70b` (or current Qwen3-32B slug) | Cerebras | Same family as #2 but on the higher-token-ceiling provider — use for token-heavy scenarios that would burn through Groq's cap. |
| 5 | Gemini Flash (current free-tier id — check `ai.google.dev/gemini-api/docs/pricing`) | Google AI Studio | Add once live RPD is confirmed ≥1,000/day; closest positioning match to Haiku. |

All five are non-reasoning-by-default (or, for any Qwen3 variant you substitute in at #4, remember
to pass `enable_thinking=False` explicitly) — so they're all fair no-thinking comparisons against
the Haiku baseline without extra prompting gymnastics.

---

## Integration sketch (matches the existing `model_factory.py` pattern)

`build_model()` currently branches on `settings.ANTHROPIC_API_KEY` presence (local dev) vs.
Bedrock (prod) — see `backend/app/agents/model_factory.py:57-121`. Adding these three as
additional branches follows the same shape, checked before the Bedrock fallback:

1. Add `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY` (all optional) to
   `app/core/config.py::Settings`.
2. In `build_model()`:
   - Groq: `from langchain_groq import ChatGroq` → `ChatGroq(model=..., api_key=settings.GROQ_API_KEY)`
   - Cerebras: `from langchain_openai import ChatOpenAI` → `ChatOpenAI(model=..., base_url="https://api.cerebras.ai/v1", api_key=settings.CEREBRAS_API_KEY)`
   - Mistral: `from langchain_mistralai import ChatMistralAI` → `ChatMistralAI(model=..., api_key=settings.MISTRAL_API_KEY)`
3. Thread the model id through the existing `model` override parameter `build_model()` already
   accepts, so an eval run can request e.g. `model="mistral-small-latest"` without touching
   provider-selection logic.
4. Leave the extended-thinking block (`model_factory.py:43-56`) untouched for these branches —
   none of the shortlisted models need a thinking kwarg on the default path, so the disabled-path
   guarantee (INV-3) stays intact.
5. New dependencies: `langchain-groq` and `langchain-mistralai` in `backend/requirements.txt` /
   `pyproject.toml`. Cerebras needs no new package (reuses `langchain-openai`).

Once wired, actually running `./tests/evals/eval.sh` against these models is a manual step for you — per
your standing instruction, live-model eval runs aren't something to trigger automatically. Happy
to help wire the `model_factory.py` branches and any config flags whenever you're ready to start.
