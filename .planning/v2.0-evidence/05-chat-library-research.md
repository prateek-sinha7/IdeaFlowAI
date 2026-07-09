# Chat UI Library Landscape (verified July 2026)

> **Evidence doc — Milestone v2.0** (see `README.md` in this directory and the POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a max-effort investigation agent, 2026-07-07. Evidence behind POR D-09 (no external framework). Revisit only if D-09 reopens.

---

Monitor stopped. All research is complete and cross-verified. Here is the deliverable.

---

# Open-source chat UI libraries for a production AI-agent chat — evidence-based comparison (verified July 2026)

**Scope recap.** Backend is FastAPI + PostgreSQL + LangGraph checkpointer, agents on LangChain `deepagents` (`create_deep_agent`). Frontend is a React SPA (Tailwind, no Next hard-requirement); the chat embeds **inside** a run-detail page (Preview/Steps/Files/Audit tabs), so composable primitives beat full-page chat apps. All versions/licenses/health below were pulled live from the npm registry API, the GitHub REST API, and PyPI on 2026-07-07, and every capability claim is cited.

---

## A. Verified snapshot (versions · license · health)

| Library / package | Latest ver | License | Last release | Repo health (stars · last push · bus factor) | One-line verdict |
|---|---|---|---|---|---|
| **assistant-ui** `@assistant-ui/react` | **0.14.26** (2026-07-04) | **MIT** | daily | 11.0k★ · pushed 2026-07-07 · founder-dominated (Yonom ~2.1k commits), YC-backed | Healthiest headless fit; some churn/bus-factor |
| ↳ `@assistant-ui/react-langgraph` | 0.14.11 (2026-07-04) | MIT | with core | — | First-party LangGraph adapter (`useLangGraphRuntime`) |
| ↳ `@assistant-ui/react-ai-sdk` | 1.3.40 (2026-07-04) | MIT | with core | — | Also has an AI-SDK adapter (dual-protocol) |
| **Vercel AI SDK** `ai` | **7.0.16** (2026-07-06) | **Apache-2.0** | multi/week | 25.4k★ · pushed 2026-07-07 · ~960 open issues · Vercel | Core is **v7**, not v5 |
| ↳ `@ai-sdk/react` (`useChat`) | 4.0.17 (2026-07-06) | Apache-2.0 | multi/week | — | Versioned separately from core |
| **Vercel AI Elements** `ai-elements` | 1.9.0 (2026-03-12) | Apache-2.0 | — | repo 2.2k★ · pushed 2026-07-01 | shadcn copy-in; **lags at `ai ^6`** |
| **CopilotKit** `@copilotkit/react-core` | 1.62.2 (2026-07-02) | MIT | ~weekly | 35.8k★ · pushed 2026-07-07 · ~1,400 releases (churn) · CopilotKit Inc (open-core) | Framework; CSS-bleed + Cloud coupling |
| **AG-UI protocol** `@ag-ui/client` / `ag-ui-langgraph`(PyPI 0.0.42) | 0.0.57 / 0.0.42 | MIT | ~monthly | 14.6k★ · pushed 2026-07-06 · multi-vendor (MS/Google/AWS) | Vendor-neutral transport, pre-1.0 |
| **LangGraph SDK** `@langchain/langgraph-sdk` (`useStream`) | 1.9.25 (2026-06-25) | MIT | active | langgraphjs 3.1k★ · pushed 2026-07-06 · LangChain | LangGraph-native headless hook |
| **Agent Chat UI** langchain-ai/agent-chat-ui | (template) | MIT | active | 3.0k★ · pushed 2026-06-28 · LangChain | Reference **Next.js** app; fork it |
| **deep-agents-ui** langchain-ai/deep-agents-ui | (template) | MIT | — | 1.7k★ · **ARCHIVED 2026-07-07** | Official deepagents UI — **just deprecated** |
| **deep-chat** `deep-chat` + `deep-chat-react` | 2.4.2 (2026-01-31) | MIT | ~quarterly | 3.7k★ · commit 2026-06-20 · **single maintainer** | Active web-component; solo bus factor |
| **NLUX** `@nlux/react` | 2.17.1 (**2024-08-15**) | MPL-2.0 | **frozen ~23mo** | repo `nlkit/nlux` **404**; `nlkitai/nlux` quiet | Effectively unmaintained — avoid |
| **chatscope** `@chatscope/chat-ui-kit-react` | 2.1.1 (2025-05-15) | MIT | semi-dormant | 1.8k★ · commit 2025-05-15 · 60 open issues | Presentation-only, quiet |
| **LlamaIndex chat-ui** `@llamaindex/chat-ui` | 0.6.1 (2025-08-28) | MIT | **feature-stall (security-only since)** | 587★ · commit 2025-12-16 · small | AI-SDK+annotation coupled; stalling |
| **Lobe UI** `@lobehub/ui` | 5.19.0 (2026-07-03) | MIT | very active | 2.1k★ · pushed 2026-07-05 · 879 releases | Ant Design + CSS-in-JS — clashes w/ Tailwind |
| **shadcn-chatbot-kit** Blazity | registry (no npm) | MIT | — | 794★ · pushed 2026-02-26 · single-org | Copy-in; AI-SDK-coupled; features WIP |
| **prompt-kit** ibelick | registry (no npm) | MIT | active | 2.9k★ · pushed 2026-03-12 | Copy-in primitives, backend-agnostic |
| **Kibo UI** | registry | MIT | active | shadcnblocks-owned | Copy-in AI primitives (one slice of a big kit) |

Backend context primitives (for capability #8, all on our own stack): `langgraph` core **1.2.8 MIT**; **`langgraph-api` (the server that speaks the useStream/Agent-Protocol API) = Elastic-2.0**, not OSI; `deepagents` PyPI **0.6.12 MIT** (newer than the 0.6.7 pinned in CLAUDE.md); `langmem` 0.0.30 MIT.

---

## B. Feature matrix — 12 capabilities × library

Y = built-in / first-class · P = partial (you wire it / WIP / indirect) · N = not provided.
Caps: 1 stream-md · 2 tool/step render · 3 image upload · 4 file attach · 5 multi-thread · 6 edit/regen · 7 HITL approvals · 8 context-compression · 9 theming freedom · 10 backend-agnostic · 11 license+health · 12 SSR-not-required

| Library | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **assistant-ui** | Y | Y | Y | P | Y | Y | Y | N | **Y** | **Y** | Y | Y |
| **AI SDK useChat + AI Elements** | Y | Y | Y | Y | P | Y/P | Y | P | **Y** | Y* | Y | Y |
| **CopilotKit + AG-UI** | Y | Y | Y | Y | P | P | **Y** | P | Y* | Y | Y | Y |
| **LangGraph useStream + Agent Chat UI** | Y | Y | Y | P | Y | Y | **Y** | Y‡ | Y/P | N† | Y | P** |
| **deep-chat** | Y | P | Y | Y | P | N | N | P | Y | Y | Y | Y |
| **LlamaIndex chat-ui** | Y | Y | Y | Y | N | P | P | N | P | P | P | Y |
| **Lobe UI** | Y | P | P | P | N | Y | N | N | P | Y | Y | Y |
| **shadcn-chatbot-kit** | Y | P | Y | Y | N | P | N | N | Y | P | P | Y |
| **prompt-kit / Kibo UI** | Y | Y | Y | P | N | N | N | N | Y | Y | Y | Y |
| **NLUX** | Y | P | N | N | P | N | N | N | Y | Y | **N** | Y |
| **chatscope** | N | P | P | P | P | N | N | N | Y | Y | P | Y |

\* backend-agnostic *only if* your backend emits the vendor protocol (AI-SDK UI-message-stream / AG-UI events). † useStream is LangGraph-protocol-locked (that's a *fit*, not a flaw, for us) — but not a generic transport. ‡ context-compression "Y" = provided by LangGraph/langmem on the backend, not the UI. ** useStream (the hook) is SPA-friendly; the Agent Chat UI *app* is Next.js.

**Per-cell evidence for the four serious candidates** (weaker libs' evidence is folded into §A verdicts + §D pain points; NLUX/chatscope/Lobe/LlamaIndex are eliminated on health/coupling grounds noted above):

**assistant-ui** — 1: streaming markdown via `@assistant-ui/react-markdown`/`react-streamdown` (Shiki/KaTeX/Mermaid) https://www.assistant-ui.com/docs/ui/streamdown · 2: per-tool React renderers via `Tools()`/`makeAssistantToolUI` with `status` states https://www.assistant-ui.com/docs/tools/tool-ui · 3: `SimpleImageAttachmentAdapter` (preview/drag/paste) https://www.assistant-ui.com/docs/guides/attachments · 4: `CompositeAttachmentAdapter` (only image+text ship; PDF needs custom adapter, unsupported types error at model) same URL · 5: `ThreadListPrimitive` + custom thread-list runtime https://www.assistant-ui.com/docs/api-reference/primitives/ThreadList · 6: `ActionBarPrimitive` + `BranchPickerPrimitive` + branchable repository https://www.assistant-ui.com/docs/primitives · 7: `requires-action`/`addResult`, `useLangGraphInterruptState()` + `Command(resume=…)` (but buggiest area, see §D) https://www.assistant-ui.com/docs/runtimes/langgraph/interrupts · 8: none built-in; `ExternalStoreRuntime` is your clean hook https://www.assistant-ui.com/docs/runtimes/custom/external-store · 9: **unstyled Radix-style primitives, "no styles, no opinions"**, `data-slot`/`data-state`, optional shadcn copy-in https://www.assistant-ui.com/docs/primitives · 10: `LocalRuntime`/`ExternalStoreRuntime`/`AssistantTransport` + first-party LangGraph, AI-SDK, AG-UI, LangChain adapters https://www.assistant-ui.com/docs/runtimes/pick-a-runtime · 12: client React, runs in Vite (drop `"use client"`), ships RN primitives https://github.com/assistant-ui/assistant-ui/issues/2490.

**AI SDK useChat + AI Elements** — protocol spec (SSE, header `x-vercel-ai-ui-message-stream: v1`) https://github.com/vercel/ai/blob/main/content/docs/04-ai-sdk-ui/50-stream-protocol.mdx · 1: `text-delta` parts rendered by `Streamdown` · 2: `message.parts` carries `tool-input-*`/`tool-output-available`/`reasoning-*`; AI Elements `Tool`/`Reasoning`/`ChainOfThought`/`Task`/`Agent` components · 3/4: `sendMessage({text, files})` → `file` parts; AI Elements `PromptInput`+`Attachments` https://github.com/vercel/ai/blob/main/content/docs/04-ai-sdk-ui/02-chatbot.mdx · 5: single-chat by `id`, no thread switcher — DIY https://github.com/vercel/ai/blob/main/content/docs/04-ai-sdk-ui/03-chatbot-message-persistence.mdx · 6: `regenerate()` yes, edit via `setMessages` · 7: **native protocol** `tool-approval-request`/`tool-approval-response` + `addToolApprovalResponse()`; AI Elements `Confirmation` component (v6 added `needsApproval`) https://vercel.com/blog/ai-sdk-6 · 8: **AI Elements `Context` component shows context-window utilization + token/cost via `tokenlens`** (accounting only, no auto-compression) https://elements.ai-sdk.dev/ · 9: shadcn copy-in (Tailwind+CVA+Radix), source in your repo · 10: `DefaultChatTransport({api,headers,prepareSendMessagesRequest})` → any HTTP endpoint (only `DirectChatTransport` is Vercel-locked) https://github.com/vercel/ai/blob/main/content/docs/04-ai-sdk-ui/21-transport.mdx · 12: client hook + client components, Vite-friendly.

**CopilotKit + AG-UI** — AG-UI ~28 event types (`TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START/ARGS/END/RESULT`, `STATE_SNAPSHOT/DELTA` [JSON-Patch], `STEP_*`, `REASONING_*`, `RUN_*`) https://docs.ag-ui.com/sdk/js/core/events · 1: `CopilotChat` streams markdown (`markdownTagRenderers`) · 2: `useCopilotAction({render})`/`useRenderToolCall` generative-UI cards https://docs.copilotkit.ai/concepts/generative-ui-overview · 3/4: `attachments={{enabled:true}}` (images+PDF/docs, 3 upload modes) https://docs.copilotkit.ai/reference/v1/components/chat/CopilotChat · 5: `useThreads` list/create/rename but server-side **storage is a Cloud feature** https://docs.copilotkit.ai/integrations/built-in-agent/threads · 6: `onRegenerate` yes; editing/branching not a listed prop (Cloud) · 7: **core strength** — `useInterrupt`/`renderAndWaitForResponse` maps to LangGraph `interrupt()` https://docs.copilotkit.ai/langgraph-typescript/human-in-the-loop/interrupt-flow · 8: `useCopilotReadable` context injection, no compression util · 9: V1 CSS vars / V2 shadcn tokens / **fully headless hooks** (`useAgent`,`useCopilotKit`) but bundled `styles.css` bleeds (§D) https://docs.copilotkit.ai/langgraph/custom-look-and-feel/headless-ui · 10: self-hostable `@copilotkit/runtime`; AG-UI vendor-neutral (SSE/WS/webhooks) · 12: client React, Vite-friendly.

**LangGraph useStream + Agent Chat UI** — 1: chunk concat → `messages`, AC-UI renders `react-markdown` https://docs.langchain.com/langgraph-platform/use-stream-react · 2: AC-UI "out-of-the-box tool-call/result rendering" https://docs.langchain.com/oss/python/langgraph/ui · 3: AC-UI multimodal images (select/drag/paste) · 4: images+**PDF only** (extend yourself) https://deepwiki.com/langchain-ai/agent-chat-ui · 5: Threads/Assistants/Runs API + `ThreadProvider` · 6: `getMessagesMetadata()`+`setBranch()` state-forking; AC-UI edit+branch-switch · 7: **native** `thread.interrupt` + `thread.submit(…,{command:{resume}})` + AC-UI "Agent Inbox" · 8: **LangGraph `SummarizationNode` / langmem on the backend** https://langchain-ai.github.io/langmem/guides/summarization/ · 9: `useStream` is headless (own the pixels); AC-UI is Tailwind4+Radix you fork · 10: requires an endpoint speaking the LangGraph/Agent-Protocol REST+SSE API (self-hosted server OK; not the cloud) — a custom-transport mode (`FetchStreamTransport`) can also point at your own FastAPI SSE if it emits `values`/`messages`/`updates` https://forum.langchain.com/t/using-the-usestream-frontend-api-with-custom-fastapi-backend/3271 · 12: hook is SPA-safe; AC-UI app is Next.js.

---

## C. Top-3 integration sketches (FastAPI + LangGraph + deepagents)

### Fit 1 — assistant-ui on the LangGraph runtime
- **Backend work:** Package your deepagents graph under a LangGraph server (`langgraph.json`; `langgraph dev` for local, uses the ELv2 `langgraph-api`). Your existing FastAPI can *co-host* it — LangChain's own deepagents frontend guide mounts custom routes via `langgraph.json`'s `http.app` and even shows the three-panel IDE (file tree + diff + chat) that maps 1:1 onto your Preview/Steps/Files/Audit tabs https://docs.langchain.com/oss/python/deepagents/frontend/overview.
- **Frontend adapter code:** `useLangGraphRuntime({stream, create, load})` (or LangChain's documented `useStream` + `useExternalStoreRuntime` + `toThreadMessages` bridge, `apiUrl: 'http://localhost:2024'`, **self-hosted, not Platform**) https://docs.langchain.com/oss/python/langchain/frontend/integrations/assistant-ui. Roughly **50-150 LOC** of runtime wiring + a small interrupt UI component. Escape hatch if you refuse the LangGraph server: `AssistantTransport`/`ExternalStoreRuntime` against a plain FastAPI SSE endpoint (a few hundred LOC, fully decoupled).
- **Theming:** Style the unstyled Radix primitives directly, or install the shadcn copy-in layer (`npx assistant-ui add …`) and edit the TSX. Black/beige/one-blue + Manrope = your Tailwind theme/CSS vars; no baked-in look to fight.
- **Pain points (real issues):** LangGraph HITL interrupts are the most-complained-about area — historically implemented wrong / don't resume cleanly https://github.com/assistant-ui/assistant-ui/issues/1280, https://github.com/assistant-ui/assistant-ui/issues/1899; rapid API churn / breaking minors (`Tools()` replacing `makeAssistantToolUI`, React-19 crashes) https://github.com/assistant-ui/assistant-ui/issues/4051; adapters can silently drop attachment data (AG-UI `toAgUiMessages()`) https://github.com/assistant-ui/assistant-ui/issues/3810; attachments beyond images need custom adapters.

### Fit 2 — Vercel AI Elements + AI SDK `useChat` (you own the shadcn source)
- **Backend work:** Your FastAPI must **hand-emit the AI SDK UI-message-stream SSE protocol** — there is *no official Python helper*, and the repo's `examples/next-fastapi` still emits the stale v4 prefixed format (issue https://github.com/vercel/ai/issues/7496). Write a `StreamingResponse` generator yielding `data:{json}\n\n` frames (`start`→`text-start/delta/end`, `tool-input-*`, `tool-output-available`, `tool-approval-request`, `finish`→`[DONE]`) with header `x-vercel-ai-ui-message-stream: v1`, mapping LangGraph `messages`/`updates`/interrupts onto those parts. **~50-150 LOC**; community libs `py-ai-datastream` (27★, thin) and Pydantic-AI's `VercelAIAdapter` reduce it but add a dep.
- **Frontend:** `useChat({transport: new DefaultChatTransport({api:'/your/fastapi'})})`; `npx ai-elements@latest add conversation message prompt-input tool reasoning context` copies TSX you own.
- **Theming:** shadcn/ui + Tailwind + CVA, components lean on `currentColor` — bespoke theme is pure `tailwind.config`/CSS vars; Manrope is a drop-in.
- **Bonus for your token-cost concern:** AI Elements `Context` component displays live context-window usage + token/cost via `tokenlens` — the only library with a first-class token widget.
- **Pain points:** v4→v5→v6→v7 protocol churn (v7 requires Node 22 + ESM) and AI Elements lagging at `ai ^6` while core is 7.0.16 — **pin versions** https://vercel.com/changelog/ai-sdk-7; dynamic Chat-instance swap breaks streaming (bites thread-switching) https://github.com/vercel/ai/issues/10926; multi-thread is entirely DIY.

### Fit 3 — AG-UI protocol via the official LangGraph FastAPI adapter (+ CopilotKit headless, or your own React)
- **Backend work (lowest of the three):** `pip install ag-ui-langgraph`; `add_langgraph_fastapi_endpoint(app, graph, "/agent")` mounts a route on your existing FastAPI that streams your LangGraph-checkpointer graph as AG-UI SSE events, auto-translating AG-UI ↔ LangChain messages and surfacing `interrupt()` pauses https://pypi.org/project/ag-ui-langgraph/. **Tens of LOC.**
- **Frontend:** either `<CopilotKit runtimeUrl="/agent"><CopilotChat/>` for batteries-included, or **CopilotKit headless hooks / `@ag-ui/client` `HttpAgent` / a hand-rolled `EventSource`** for full pixel control. HITL via `renderAndWaitForResponse`/`useInterrupt`.
- **Theming:** to hit a bespoke black/beige/one-blue + Manrope with no baked-in look, **go headless** — the bundled `styles.css` overrides app Tailwind (recurring, "blocking adoption") https://github.com/CopilotKit/CopilotKit/issues/1857.
- **Pain points:** version churn / peer-dep hell (`--legacy-peer-deps`, `@ag-ui/*` vs `@langchain/langgraph-sdk` conflicts) https://github.com/CopilotKit/CopilotKit/issues/2840; thread storage, guardrails, analytics gated behind **Copilot Cloud** (self-host = wire your own persistence, i.e. your LangGraph checkpointer); AG-UI packages are still **pre-1.0** (0.0.x).

---

## D. Explicit verdict: is "compression"/context-management ever out of the box?

**No — not from any frontend chat library. It is always backend work.** Every library scores N or P on capability #8, and the P's are token *accounting/injection*, not compression:
- **Display/accounting only:** AI Elements `Context` + `tokenlens` (context-window %, token/cost) https://elements.ai-sdk.dev/; deep-chat `requestBodyLimits` (cap messages/chars sent) https://deepchat.dev/docs/connect; CopilotKit `useCopilotReadable` (context *injection*, not trimming).
- **Clean hook to implement your own:** assistant-ui `ExternalStoreRuntime` / AI SDK `prepareSendMessagesRequest` (`messages.slice(-N)`) — you control exactly what's sent.
- **The actual compression lives on your stack, and you already have it:** deepagents `SummarizationMiddleware` (auto-compacts at ~85% of context) and `SummarizationToolMiddleware` (a `compact_conversation` tool) https://reference.langchain.com/python/deepagents/middleware/summarization; LangGraph prebuilt `SummarizationNode`; `langmem` for memory/summarization https://langchain-ai.github.io/langmem/guides/summarization/.

**Design implication:** treat the frontend as a *token-usage display + a "compact" affordance* that calls a backend endpoint; keep all trimming/summarization in your deepagents/LangGraph graph. This directly serves your known prototype-token-cost problem — the fix is backend caching/summarization, not a UI library.

---

## E. Ranked recommendation

### 🥇 1. assistant-ui (headless primitives) on the LangGraph runtime
The best overall fit and the only library that natively covers ~10/12. It is genuinely headless (unstyled Radix-style primitives — embeds cleanly *inside* your run-detail tabs and restyles to black/beige/one-blue + Manrope with zero baked-in look), MIT and the healthiest of the bunch (daily commits, YC-backed), runs in a Vite SPA, and is **officially documented by LangChain** as a LangGraph frontend. Its `react-langgraph` adapter rides `@langchain/langgraph-sdk`, so you inherit LangGraph-native interrupts/branching/threads, and if you ever want off LangGraph you swap to `AssistantTransport`/AI-SDK/AG-UI adapters without an app rewrite. **Risks to budget for:** LangGraph HITL interrupts are its buggiest surface (test them early), high release velocity = migration work, and a founder-dominated bus factor.

### 🥈 2. LangGraph SDK `useStream` (headless) — the LangGraph-native backbone, build the shell yourself
Because your runtime *is* LangGraph + deepagents, `useStream` speaks your backend's protocol directly and gives the highest-fidelity interrupts (`interrupt()` → `Command(resume)`), state-forking/edit, and thread management — MIT and LangChain-maintained. Pair it with copy-in primitives (prompt-kit / Kibo / AI Elements) for the pixels, or selectively fork Agent Chat UI (MIT). **Choose this over #1 if you want zero UI-framework dependency.** The real cost is backend, not UI: you must expose the LangGraph/Agent-Protocol server API — the `langgraph-api` dev server is **ELv2 (source-available, not OSI)** and a production standalone Agent Server needs a **license key + Postgres + Redis** https://docs.langchain.com/langsmith/deploy-standalone-server; the license-free path is to implement the Agent Protocol yourself (community `open-langgraph-platform` exists but is 20★/immature). Note the official **`deep-agents-ui` reference was archived 2026-07-07** and its deepagents-interrupt handling had open bugs (https://github.com/langchain-ai/agent-chat-ui/issues/269) — don't build on it; take the hook, not the app.

### 🥉 3. AG-UI protocol via `ag-ui-langgraph` (+ CopilotKit headless or your own React)
The lowest-code, vendor-neutral way to bind a React chat to your LangGraph checkpointer — one `add_langgraph_fastapi_endpoint(...)` call on your existing FastAPI, MIT, multi-vendor governance, strong HITL. It decouples transport (AG-UI) from UI, so you can consume it with CopilotKit headless hooks *or* assistant-ui's AG-UI adapter *or* a hand-rolled reader. Ranked third only because the protocol is **pre-1.0** and CopilotKit-the-framework carries CSS-bleed + Cloud-coupling + peer-dep churn (all avoidable by going headless). *Alternative #3:* **Vercel AI Elements + `useChat`** if you prefer owning shadcn source and want the `tokenlens` `Context` widget — accepting the hand-rolled AI-SDK SSE adapter, DIY multi-thread, and the v-major treadmill.

**Not recommended:** NLUX (npm frozen since 2024-08; repo moved/gone), chatscope (presentation-only, dormant since 2025-05), Lobe UI (Ant Design + CSS-in-JS clashes with a bespoke Tailwind SPA), LlamaIndex chat-ui (feature-stalled, AI-SDK+annotation-coupled, no multi-thread), shadcn-chatbot-kit (AI-SDK-coupled, key features WIP). deep-chat is the honorable mention (MIT, active, best custom-transport story) but it's a web component with a single-maintainer bus factor and requires web-components — not React — for custom in-bubble agent-step UI.

### "Own the code" (copy-in) vs "depend on the package" — and lock-in

| | Copy-in (shadcn registry): AI Elements, prompt-kit, Kibo, shadcn-chatbot-kit, assistant-ui's styled layer | Depend-on-package: assistant-ui primitives, CopilotKit, langgraph-sdk, deep-chat |
|---|---|---|
| **You get** | TSX in your repo; infinite theming; no UI upgrade treadmill | Maintained behavior + upstream fixes/features |
| **You owe** | You own bug-fixes; no automatic improvements; primitives-only (assemble threads/HITL/runtime yourself) | You ride their release cadence (assistant-ui & CopilotKit churn hard) and API breaks |
| **Lock-in** | Near-zero to the *UI* vendor — **but** AI Elements/shadcn-chatbot-kit lock you to the **AI-SDK data model**; prompt-kit/Kibo are model-agnostic | `langgraph-sdk` locks you to the LangGraph protocol (a *fit* here); CopilotKit's advanced features lean on **Copilot Cloud**; AG-UI is explicitly vendor-neutral; assistant-ui's multi-adapter design keeps lock-in low |

**Net recommendation:** adopt a **hybrid** — depend on assistant-ui's headless primitives package (rank 1) driving the **LangGraph runtime** (rank 2's backbone), and *copy in* the styled layer so you own every pixel of the black/beige/one-blue + Manrope skin. Keep AG-UI (`ag-ui-langgraph`, rank 3) on the shortlist as the vendor-neutral transport if you later want to decouple the UI from LangGraph entirely. Put all context-compression in the deepagents/LangGraph backend (§D); use the frontend only to display token usage and trigger compaction.

*Caveat on freshness:* two facts moved during this research — `langchain-ai/deep-agents-ui` flipped to **archived on 2026-07-07** (mid-session), and AI SDK is now on **v7** with AI Elements still pinned to `ai ^6`; re-check both immediately before committing.
