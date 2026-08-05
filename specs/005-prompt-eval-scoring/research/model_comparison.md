# Model Comparison — Free Models vs. Claude Haiku 4.5 (no thinking)

**Baseline:** `claude-haiku-4-5-20251001`, our default model
(`backend/app/core/config.py:63`, wired through `backend/app/agents/model_factory.py`), run
**without extended thinking** (`THINKING_BUDGET_TOKENS=0`, the default — see
`model_factory.py:44-56`).

**Why tool calling and a thinking toggle are hard requirements here, not nice-to-haves:** every
pipeline agent runs as a `deepagents` graph (`app/agents/deep_agent_runner.py`) whose *only*
interface to the filesystem sandbox is native tool calls (`write_file`, `read_file`, `edit_file`,
`ls`, `glob`, `grep`, plus `report_task_complete` for prototype agents — see backend `CLAUDE.md`
§ Tool Sets). A model with no reliable function-calling support cannot run inside this framework
at all, regardless of how good its raw benchmark scores are. Likewise, since our baseline is
Haiku with thinking **off**, a fair free comparable needs a working no-think / instruct mode —
either a model that's non-reasoning by default, or a reasoning model with a documented switch to
turn it off.

> ⚠️ **Freshness/quality warning:** benchmark numbers below are pulled from vendor pages,
> OpenRouter's model cards, and comparison aggregators — not run by us, and several 2026-dated
> SEO sites reuse stale or estimated figures. Treat every score as directional. The real signal
> is running our own eval scenarios against candidate models — that's a deliberate manual step
> for you to trigger via `./tests/evals/eval.sh` (see `[[Never run live LLM evals myself]]`), not something
> to kick off from this doc.

---

## Comparison table

| Model | Free access | Params / class | Context | Thinking toggle | Tool calling | Approx. benchmark (MMLU / notes) | Free-tier limits (approx.) | Integrates with our framework? |
|---|---|---|---|---|---|---|---|---|
| **Claude Haiku 4.5** (no thinking) — *baseline* | Anthropic (paid) | small/fast, non-reasoning by default | 200K | Yes — off by default, `THINKING_BUDGET_TOKENS` env knob | Native, first-class | ~75% MMLU (Haiku 3.5 public figure; 4.5 not yet in public tables) | n/a | Already integrated (`ChatAnthropic` branch in `model_factory.py`) |
| **Gemini 2.0 / 3 Flash** | Google AI Studio (free tier) | small/fast, non-reasoning by default | up to 1M | N/A — Flash is non-reasoning; a separate "Flash Thinking" variant exists if you want reasoning-on instead | Native (`bind_tools` supported) | ~83.5% MMLU (2.0 Flash) | Free tier auto-enabled per project; low single/low-teens RPM, model-dependent — see `ai.google.dev/gemini-api/docs/rate-limits` | **Yes, easy** — `langchain-google-genai` (`ChatGoogleGenerativeAI`) is a maintained LangChain integration with `bind_tools`; add as a third branch in `model_factory.py` |
| **Mistral Small 3.x** | Mistral La Plateforme (free "Experiment" tier — requires opting into data-training use) | small/fast, non-reasoning by default | 32K–128K | N/A — non-reasoning line (Mistral's reasoning models are separate "Magistral" line) | Native, function calling supported since Feb-2024-era models | ~81.3% MMLU | ~1B tokens/month reported, ~2 RPM | **Yes, easy** — `langchain-mistralai` (`ChatMistralAI`) is maintained with `bind_tools` |
| **Llama 3.3 70B** | Groq (free) / Cerebras (free) | mid/large, non-reasoning | 128K | N/A — non-reasoning | Native via provider (Groq/Cerebras both expose OpenAI-style tool calling) | ~86% MMLU | Groq: ~30 RPM / ~6K TPM / ~1K RPD (binding constraint is usually daily requests); Cerebras: ~1M tokens/day, ~30 RPM | **Yes** — `langchain-groq` (`ChatGroq`) is maintained with `bind_tools`; Cerebras has no dedicated LangChain package but exposes an OpenAI-compatible endpoint, so `ChatOpenAI(base_url="https://api.cerebras.ai/v1", ...)` works as a drop-in |
| **Gemma 2 9B** | Groq (free) | small, non-reasoning | 8K | N/A | Supported (Groq tool-calling API) but weaker at multi-step tool use than the larger models here | Below Llama 3.3 70B on most suites; ~70%'s ballpark MMLU class | Uniquely raised TPM (~15K) vs. Groq's default free-tier cap | **Yes, easy** — same `ChatGroq` integration, just swap `model=` |
| **DeepSeek V3 / V3.1** | OpenRouter (`:free` variants rotate) | large MoE, non-reasoning (V3) / reasoning-capable (V3.1 has a think mode) | up to ~164K | V3: none needed (non-reasoning). V3.1: has a reasoning mode that can be prompted off — verify per-request | Native structured tool calling (V3.1 docs explicitly cover tool/code/search agents) | Competitive with Claude Sonnet 3.5 / Llama 3.1 405B on MMLU per DeepSeek's own report | OpenRouter free-tier request caps (see providers.md): ~50/day bare, ~1,000/day after $10 lifetime spend | **Yes** — via OpenRouter's OpenAI-compatible endpoint, `ChatOpenAI(base_url="https://openrouter.ai/api/v1", ...)`; confirm the specific `:free` slug still has tool-calling enabled (not all free-tier hosts of a model support it) |
| **Qwen3-32B / Qwen3-235B** | OpenRouter (`:free`) / Cerebras (free) | mid/large, **reasoning model with a toggle** | 32K–128K+ | Yes — explicit `enable_thinking=False` request param turns off `<think>` blocks | Native function calling, but Qwen's own docs warn against ReAct-style stopword tool templates when thinking is left on — set `enable_thinking=False` for clean tool-calling behavior | Strong general + coding scores, comparable tier to Llama 3.3 70B on public boards | Same OpenRouter/Cerebras free limits as above | **Yes, with one caveat** — must explicitly pass `enable_thinking=False` in the request (LangChain's OpenAI-compatible wrapper can pass this via `model_kwargs`/`extra_body`); don't assume default is off |
| **Qwen3-Coder** | OpenRouter (`:free`) | large, code-specialized | up to 1M | N/A — Coder variant only supports non-thinking mode, no flag needed | Native, strong on code/tool-use benchmarks | State-of-the-art among free models on coding benchmarks; not a general MMLU comparable | Same OpenRouter free limits | **Yes** — same OpenRouter OpenAI-compatible path; best candidate specifically for our code-gen (`prototype`, `app_builder`) pipelines rather than as a general Haiku stand-in |
| **GPT-OSS-20B / 120B** | OpenRouter (`:free`) / Cerebras (free) | small–mid, OSS, some reasoning traces | large | Traces can appear depending on invocation; check per-host default | Native tool calling | Vendor-cited as competitive with o3-mini on coding | Same OpenRouter/Cerebras free limits | **Yes** — OpenAI-compatible path on either host; verify reasoning traces are suppressed/ignored so it's a fair no-think comparison |
| **Command R7B / Command R** | Cohere (free "Trial" tier) | small, non-reasoning | 128K | N/A | Native (Cohere's own tool-calling API shape, not OpenAI-style) | Not consistently reported on public MMLU tables | ~1,000 calls/month total, ~20 RPM for chat | **Partial — needs an adapter** — `langchain-cohere` (`ChatCohere`) exists and supports `bind_tools`, but Cohere's tool-call/message format differs enough from Anthropic/OpenAI that it needs its own tested branch rather than reusing the OpenAI-compatible shortcut; smallest free quota of the group, so best for spot checks, not sustained eval runs |

---

## Reading the "integrates with our framework?" column

Our framework's only requirement to swap in a model is: **a LangChain `BaseChatModel` with working
`bind_tools`**, added as an additional branch in `build_model()` (`model_factory.py:57-121`),
selected the same way the existing `ANTHROPIC_API_KEY` / Bedrock branches are (env var presence).
Three integration shapes show up above:

1. **Dedicated LangChain package, drop-in** — Gemini (`langchain-google-genai`), Mistral
   (`langchain-mistralai`), Groq (`langchain-groq`). Cleanest option; each has first-class
   `bind_tools`.
2. **OpenAI-compatible endpoint via `ChatOpenAI(base_url=..., api_key=...)`** — OpenRouter,
   Cerebras, and most `:free` models on either. No new dependency (`langchain-openai` is almost
   certainly already a transitive dep of the LangChain stack); just point the base URL and swap
   the model id. This is the **fastest path to try the largest number of free models** without
   adding new packages.
3. **Needs its own adapter** — Cohere's native API shape doesn't map cleanly onto the OpenAI
   tool-call schema; `langchain-cohere` exists but should get its own tested branch, not the
   generic OpenAI-compat shortcut.

## Recommended shortlist to actually wire up

1. **Gemini Flash** — closest *positioning* match to Haiku (fast, non-reasoning default tier),
   clean LangChain integration.
2. **Mistral Small** — closest *weight class* match, clean LangChain integration (mind the
   training opt-in on the free tier).
3. **DeepSeek V3 or Qwen3-32B via OpenRouter** — good "does a stronger free model change the
   verdict" control, reachable through the same `ChatOpenAI(base_url=...)` shim, so cheapest to
   add technically even though it's a bigger model than Haiku.
4. Treat **Llama 3.3 70B** (Groq/Cerebras) and **Qwen3-Coder** as pipeline-specific probes —
   the former as a "bigger free model" upper bound, the latter specifically for the code-gen
   pipelines rather than as a general-purpose Haiku substitute.
5. **Command R7B** last — smallest quota, needs its own adapter, lowest priority.

See `providers.md` in this folder for the provider-level free-tier details (limits, sign-up
process, data-use caveats).

---

### Sources
- [Free LLM API in 2026: 13 Options Ranked and Compared — OpenRouter Blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [langchain_google_genai bind_tools reference](https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI/bind_tools)
- [langchain_mistralai reference](https://reference.langchain.com/python/langchain-mistralai)
- [Langchain Tooling using Groq — Medium](https://medium.com/the-ai-forum/langchain-tooling-using-groq-d60ce5117710)
- [Qwen3 Thinking mode docs — QwenCloud](https://docs.qwencloud.com/developer-guides/text-generation/thinking)
- [Qwen Function Calling docs](https://qwen.readthedocs.io/en/latest/framework/function_call.html)
- [DeepSeek-V3 Technical Report](https://arxiv.org/pdf/2412.19437)
- [DeepSeek V3.1 — OpenRouter model card](https://openrouter.ai/deepseek/deepseek-chat-v3.1)
- [Cerebras Inference Model Catalog](https://inference-docs.cerebras.ai/models/overview)
- [Cohere rate limits docs](https://docs.cohere.com/docs/rate-limits)
