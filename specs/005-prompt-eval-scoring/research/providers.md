# Free-Tier LLM Providers — Options for Prompt Eval Benchmarking

**Purpose:** find free-of-charge inference providers whose models are close enough in class to
`claude-haiku-4-5-20251001` (no-thinking, our current default per
`backend/app/core/config.py:63` / `backend/app/agents/model_factory.py:60`) that we can run our
eval prompts against them for a zero-cost sanity comparison before/alongside real Haiku runs.

**Baseline model:** Claude Haiku 4.5, no extended thinking — a fast, cheap, non-reasoning
mid-tier model. The right free comparables are other **small-to-mid, non-reasoning, instruction-tuned**
chat models, not frontier reasoning models.

> ⚠️ **Freshness warning:** rate limits, quotas, and model rosters on all of these free tiers change
> often (weekly-to-monthly) and several of the pages that show up in search results are SEO
> aggregator sites (`tokenmix.ai`, `costbench.com`, `pricepertoken.com`, `freellm.net`, etc.) whose
> numbers are not authoritative. Treat every limit below as "approximately this, as of when this
> doc was written (2026-07-28)" and re-verify against the official docs link before depending on it
> for a real eval run.

---

## 1. OpenRouter — best for breadth (one key, many free models)

- **What it is:** an API aggregator/router in front of many providers. Filters models by
  `Price: Free` in its catalog.
- **Free-tier shape:** $0/token on models tagged `:free`. Documented cap is roughly
  **50 requests/day** on a bare free account, or **1,000 requests/day** once you've ever purchased
  ≥$10 of credits (no obligation to keep spending), plus a **20 req/min** ceiling. Exact numbers are
  enforced live by OpenRouter and should be checked at request time.
- **Relevant free models (roster shifts constantly — check live filter):**
  - `qwen/qwen3-coder:free` — strong code-oriented free model, 1M context.
  - `openai/gpt-oss-20b:free` — small OSS reasoning-capable model, cited as competitive with o3-mini on coding.
  - Various Llama, Gemma, Mistral, and DeepSeek `:free` variants rotate in/out.
- **Why it matters for us:** single integration point, OpenAI-compatible API — trivial to drop into
  our existing model factory pattern (`backend/app/agents/model_factory.py`) as another provider
  branch, no separate SDK needed.
- **Docs:** https://openrouter.ai/models?order=top-weekly (filter `Price: Free`), overview:
  https://openrouter.ai/blog/tutorials/free-llm-apis-compared/

## 2. Google AI Studio (Gemini API) — best "closest to Haiku" candidate

- **What it is:** Google's direct Gemini API, distinct from Vertex AI. New projects start on a
  **Free Tier** automatically (no billing account required) with access to a subset of models at
  free-tier rate limits.
- **Relevant free model:** **Gemini Flash line** (currently `gemini-3-flash-preview` / whichever
  Flash model has an active free tier — check https://ai.google.dev/gemini-api/docs/pricing, the
  free-vs-paid model list moves as new Gemini versions ship). Flash is Google's fast/cheap,
  non-reasoning-by-default tier — the closest *class* match to Haiku 4.5 of anything free.
- **Rate limits:** vary per model, generally low RPM (single digits to ~15) on true free tier;
  see https://ai.google.dev/gemini-api/docs/rate-limits for the live table.
- **Caveat:** Google states free-tier prompts/responses **may be used to improve Google products**
  unless you're in the EU/UK/EEA — don't send anything sensitive/proprietary through the free tier.
- **Docs:** https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/rate-limits

## 3. Groq — best for raw speed, good Llama/Gemma access

- **What it is:** custom LPU hardware, OpenAI-compatible API, hosts open models (not its own).
- **Free tier:** always-free, no credit card. Exact numbers vary by model and are shown live in the
  console (https://console.groq.com/docs/rate-limits); ballpark reported figures: ~30 RPM,
  low-thousands TPM, ~1,000–14,400 requests/day depending on model. **Daily request cap is usually
  the binding constraint**, not per-minute throughput.
- **Relevant models:** `llama-3.3-70b-versatile` (closest "generalist mid-size" comparable),
  `gemma2-9b-it`, various Mixtral/Llama-Guard variants.
- **Docs:** https://console.groq.com/docs/rate-limits, https://console.groq.com/docs/models

## 4. Cerebras Inference — highest free token volume

- **What it is:** wafer-scale inference hardware, OpenAI-compatible API.
- **Free tier:** reported **~1,000,000 tokens/day**, resets daily (not a one-time trial credit),
  ~30 req/min, with a temporary 8K context cap on some free-tier models. No credit card to start.
- **Relevant models:** `llama-3.3-70b`, `llama3.1-8b`, Qwen3 32B/235B, GPT-OSS-120B — rotates.
- **Docs:** https://inference-docs.cerebras.ai/models/overview, https://cloud.cerebras.ai

## 5. Mistral (La Plateforme) — broadest model access on free tier

- **What it is:** Mistral's own API.
- **Free tier ("Experiment" tier):** reported ~1B tokens/month at ~2 RPM across effectively their
  whole catalog — **but requires opting in to having your data used for training** to unlock that
  quota. Read the ToS before sending any proprietary prompt content.
- **Relevant model:** `mistral-small-latest` — Mistral's small, fast, non-reasoning chat model;
  the most direct "same weight class as Haiku" candidate outside of Gemini Flash.
- **Docs:** https://docs.mistral.ai/deployment/laplateforme/overview/, pricing page for current
  free-tier terms.

## 6. Cohere — smallest free quota, still worth having

- **What it is:** Cohere's own API (Command family).
- **Free ("Trial") tier:** reported **1,000 calls/month** total across endpoints, ~20 req/min for
  chat models (Command A / R+ / R / R7B). Explicitly for dev/testing only, not production.
- **Relevant model:** `command-r7b` or `command-r` — smaller Command variants are the closest size
  match to Haiku.
- **Docs:** https://docs.cohere.com/docs/rate-limits

## 7. Others worth a mention, lower priority

- **GitHub Models** — free-with-a-GitHub-account access to a rotating catalog (including some
  Llama/Mistral/Phi models) at low rate limits; convenient if we already auth via GitHub.
- **HuggingFace Inference Providers** — free credits/rate-limited router in front of many OSS
  models; good for one-off spot checks, less reliable for repeated benchmark runs.

---

## Recommendation for our use case

Given we want a **free stand-in for Haiku 4.5 (no thinking)** to compare prompt behavior against:

1. **Primary comparable:** Gemini Flash via Google AI Studio — same "fast non-reasoning tier"
   positioning as Haiku, plus we may already have Google Cloud project access.
2. **Secondary comparable:** Mistral Small via Mistral's free Experiment tier — similar weight
   class, provided we're fine with the data-training opt-in.
3. **Volume/throughput testing:** Cerebras or Groq running Llama 3.3 70B — bigger model than
   Haiku, so treat results as "upper bound" rather than an apples-to-apples stand-in, but useful
   for cheap high-volume smoke-testing of prompts before spending real Haiku budget.
4. **Convenience/breadth:** OpenRouter if we want to try several of the above through one
   OpenAI-compatible client without juggling four SDKs/keys.

See `model_comparison.md` in this folder for the benchmark-score side of this comparison.

---

### Sources
- [Free LLM API in 2026: 13 Options Ranked and Compared — OpenRouter Blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- [OpenRouter Free Models List 2026](https://buldrr.com/openrouter-free-models-list-2026-all-27-models-ranked-tested/)
- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Groq Rate Limits docs](https://console.groq.com/docs/rate-limits)
- [Cerebras Inference Model Catalog](https://inference-docs.cerebras.ai/models/overview)
- [Cerebras Free Tier writeup](https://adam.holter.com/cerebras-opens-a-free-1m-tokens-per-day-inference-tier-and-ccerebras-now-offers-free-inference-with-1m-tokens-per-day-real-speed-benchmarks-show-2600-tokens-sec-on-llama4scout-here-are-the-actual-n/)
- [Cohere rate limits docs](https://docs.cohere.com/docs/rate-limits)
