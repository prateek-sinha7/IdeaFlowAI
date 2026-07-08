# Phase 33: Concierge + Compaction [A5] — Research

**Researched:** 2026-07-08
**Domain:** Backend capability system (registry lockstep) · deepagents 0.6.7 middleware · Phase-29 chat backbone · INV-3 characterization goldens
**Confidence:** HIGH (every load-bearing claim verified against installed package + file:line; a few forward-design points marked unverified)

> Provenance legend: **[VERIFIED: file:line]** = read in this session · **[VERIFIED: cmd]** = tool output this session · **[CITED: POR/CONTEXT]** = locked design doc · **[ASSUMED]** = training/inference, needs confirmation.

---

<user_constraints>
## User Constraints (from 33-CONTEXT.md — LOCKED, do not re-open)

### Locked Decisions
- **ONE `chat:concierge` capability, per-run instances (D-05).** Workflow-specificity from CONTEXT (compiled manifest, artifacts, events, conversation), NEVER per-workflow code. Proposal-only tools; the engine executes proposals through the SAME channels as the Phase-29 router; consequential proposals behind a **confirm chip**. Optional per-workflow customization = declared manifest `chat:` data (suggestions, concierge notes), compiled as DATA (INV-5). "The Concierge proposes; the engine disposes."
- **Mechanical router first, Concierge as escalation (D-04).** Routable turns (clarify/gate/steering/revision) stay **zero-model-call**; only free-form turns hit the Concierge. `update_specs` routes to the shipped KAN-101 loop (never rebuild spec-revision as a steering note or child run).
- **Compaction backend-owned (D-08).** Summarize-beyond-budget + keep-recent-verbatim; `context_provider:conversation` feeds the compacted history. FE only DISPLAYS usage + a compact affordance — no FE compression.
- **Concierge rollout (ND-2):** default-on lane+router; Concierge behind a per-run toggle initially; **Haiku default** model.
- **Live-deferred to Phase 34:** live Concierge Q&A, multi-turn cache-point placement, live mid-run steering delivery. Build + offline-prove here (expect `human_needed` on those items in Phase 34).

### Locked Invariants
- **SC-001 / INV-1** — brand-new custom workflow gets lane+router+Concierge with ZERO engine/FE/orchestrator code; no workflow-name / `pipeline_type` / `spec.id` branch anywhere new.
- **INV-13** — Concierge model calls ONLY via `deep_agent_runner` / `create_deep_agent` (banned-pattern CI gate).
- **INV-3** — 5 goldens byte/event-identical; chat/concierge events NEVER fire on golden paths; new event types → `_DOCUMENTED_EVENT_TYPES`, new `pipeline_complete` keys → `_VOLATILE_STRIP_KEYS`.
- **INV-5** — manifest `chat:` key compiles as DATA.
- **INV-12** — ONE chat subsystem; reuse Phase-29 seams, do NOT fork ChatRunner / touch `test_chat_contract.py` golden / change `user_message` semantics; `_INTERNAL_PIPELINES` stays.
- **import-linter** — capabilities never import kernel/`app`; heavy-dep Concierge impl under `app/agents/**` against ports (expect **4 kept / 0 broken**).
- **additive migrations only** — reuse `run_events`; owner_id + workspace_id on anything persisted.
- **owner-scoped Concierge reads** — IDOR → 404 via `ScopedStore`.
- **Bedrock caching already ON (P26)** — do NOT re-diagnose; multi-turn placement is the Phase-34 live check.

### Deferred Ideas (OUT OF SCOPE)
Live Concierge Q&A + multi-turn cache-point placement + live mid-run steering (Phase 34). Per-agent prompt-override, team-sharing, resume-from-failed (LOCK-E). FE reskin (done Phase 32). Handoff screen (post-v2.0).
</user_constraints>

---

<phase_requirements>
## Phase Requirements (ROADMAP SC 1–4)

| ID | Description | Research Support |
|----|-------------|------------------|
| SC-1 | Concierge answers run questions from REAL run data; proposals execute only through existing channels (proposal-only + confirm chip) | `chat:concierge` via `deep_agent_runner` (§deepagents API); READ tools over `ScopedStore.read_events`/`list_refs`; PROPOSAL execution via `run_commands` §Phase-29 Seams |
| SC-2 | `compaction:chat_history` + `context_provider:conversation` bound composed history — long transcript stays under budget, recent verbatim | deepagents `SummarizationMiddleware` / `create_summarization_middleware` (§deepagents API); clone `uploaded_files` provider (§Registry); offline shape proof (§Compaction-Under-Budget) |
| SC-3 | Post-run chat turns produce revision runs stitched into the family | `CHANNEL_REVISION` → `_mint_revision_row` + `_drive_revision_to_queue` (§Phase-29 Seams) |
| SC-4 | **SC-001 proof** — brand-new custom workflow gets lane+router+Concierge with ZERO code | §SC-001 Proof Strategy |
</phase_requirements>

---

## Summary

The 8 load-bearing facts the planner MUST internalize:

1. **The registry lockstep is exactly 4 mechanical edits per capability + 1 test bump.** `@register(kind, name, ...)` at `registry.py:180` auto-adds `(kind,name)` to `_KNOWN` (line 209) — so the "`_KNOWN` membership" step is *automatic* when the impl module is imported. What is NOT automatic and MUST be hand-added: (a) the impl module path in `discover()`'s `_builtin_modules` tuple (`registry.py:252`), (b) the pair in the drift-guard's `_EXPECTED_NAMES` list (`test_registry_capabilities.py:38`), and (c) the count assertion `assert len(_KNOWN) == 66` (`test_registry_capabilities.py:163`) → **66 → 69** for the 3 new caps. **[VERIFIED: registry.py:180-218, test_registry_capabilities.py:113-164]**

2. **`context_provider:conversation` is a near-verbatim clone of `uploaded_files.py`.** The `ContextProvider` port is a one-method Protocol: `name: str` + `async def load(self, ctx) -> dict[str, str]` (`base.py:76-83`). Clone `context_providers/uploaded_files.py` — self-gate on a declared inject token, degrade-not-crash, import-pure (registry decorator + stdlib only, NO `app.*`). Difference: it reads compacted chat `run_events` (via the owner-scoped read surface) instead of the `.uploads` sidecar. **[VERIFIED: base.py:76, uploaded_files.py:58-138]**

3. **deepagents 0.6.7 `create_deep_agent(...)` takes a `middleware=[...]` param and already bakes summarization into its base stack.** The runner composes `middleware=[_ToolFilterMiddleware(...), _BedrockCachePointsMiddleware()]` at `deep_agent_runner.py:352`; the Concierge inherits both by running through this exact runner (INV-13 + P26 caching for free). deepagents auto-adds `create_summarization_middleware(model, backend)` in-graph, and the public `langchain.agents.middleware.SummarizationMiddleware(model, *, trigger, keep=('messages',20), token_counter, summary_prompt, trim_tokens_to_summarize=4000)` is the tunable knob for the chat-history compaction. **[VERIFIED: `python3.11 -c inspect`, deep_agent_runner.py:347-356, graph.py:53/595/667/740]**

4. **The chat router today maps EVERY turn to one of 4 channels with zero model calls; there is NO concierge channel yet.** `route_chat_turn` (`chat_router.py:235`) is pure: clarify→answers, gate→gate, running→steering, terminal→revision. Free-form running turns currently fall into `CHANNEL_STEERING`. The escalation seam must add a Concierge path WITHOUT making any routable turn call a model — the classification for "genuinely free-form / a question" happens in the app layer (`post_message`, `run_commands.py:419`), and the router stays pure/deterministic. **[VERIFIED: chat_router.py:235-295, run_commands.py:419-614]**

5. **Proposals execute through 3 existing seams already wired in `post_message`.** Gate: `art_store.set_review_response(gate_key, approved=..., action=..., instructions=...)` (`run_commands.py:526-558`, incl. `update_specs`→KAN-101). Steering: `apply_steering(ectx, note)` → `ectx.steering_notes` (`chat_router.py:301`). Revision: `_mint_revision_row(...)` + `_drive_revision_to_queue(...)` (`run_commands.py:577-609`). The Concierge's `propose_*` tools produce structured intents; the app layer disposes them through these SAME functions (behind a confirm chip for consequential ones). **[VERIFIED: run_commands.py:526-609]**

6. **Chat/concierge events must stay dormant on the 5 goldens — this is already an enforced standing proof.** `test_chat_event_neutrality.py` asserts `{chat_message, chat_reply, stream_attached}` appear in NONE of the 5 golden event streams (`prototype`, `od_prototype`, `od_ppt`, `prototype_revision`, `app_builder`). Any NEW concierge event type must (a) be added to `_DOCUMENTED_EVENT_TYPES` (`test_phase3_cutover_verify.py:182`), (b) never fire on a golden path (extend the neutrality guard), and (c) if it adds `pipeline_complete` keys, add them to `_VOLATILE_STRIP_KEYS` (`_normalize.py:101`). Byte-identity is proven by running the characterization suite with `SNAPSHOT_UPDATE` UNSET. **[VERIFIED: test_chat_event_neutrality.py:34-89, _normalize.py:101-171]**

7. **The chat lane already persists to `run_events` (no new table).** A chat turn is a `chat_message` `run_events` row appended idempotently via `ScopedStore.append_event_next_seq(...)` keyed on `event_id = chat:{message_id}` (`run_commands.py:365-416`). `chat_reply` (narrator projection back to the lane) is a documented type. The Concierge's reads use `ScopedStore.read_events(run_id, after_seq)` (`authz.py:314`, owner+workspace scoped → cross-owner returns nothing → 404). Persistence is additive-only; anything persisted carries owner_id + workspace_id (stamped by `ScopedStore`). **[VERIFIED: authz.py:284-389, run_commands.py:365-416]**

8. **Dependency order is forced: compaction + conversation provider land BEFORE the Concierge.** The Concierge's context is composed FROM the compacted conversation (`context_provider:conversation` reads the bounded history that `compaction:chat_history` produces). Build the read/bound substrate first, prove compaction-under-budget offline, then build the orchestrator that consumes it. See §Dependency Ordering.

**Primary recommendation:** Land the 3 capabilities in order — `compaction:chat_history` → `context_provider:conversation` → `chat:concierge` — each as a self-registering module (kernel-pure for the two providers; the Concierge's heavy-dep impl under `app/agents/**` behind a port, per import-linter). Bump the drift guard `66 → 69` in one commit with the `_KNOWN`/`discover()` edits. Add the router escalation in the app layer only; keep `route_chat_turn` pure. Prove everything offline (register/discover lockstep, compaction shape, proposal→channel units, goldens byte-identical with concierge dormant, lint-imports 4/0). Mark live Q&A/cache/steering `human_needed` for Phase 34.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Free-form turn → Concierge escalation classification | API / Backend (`app/api/chat_router.py` + `run_commands.post_message`) | — | Router keys on generic run-state; escalation decision is app-layer so `route_chat_turn` stays pure/zero-model (INV-1) |
| Concierge model call (Q&A, propose) | API / Backend (`app/agents/deep_agent_runner.py`) | — | INV-13: model calls only via `create_deep_agent`; heavy-dep impl under `app/agents/**` |
| Concierge READ tools (events/artifacts/steps) | Database/Storage (`agents/authz.py::ScopedStore`) | — | Owner-scoped default-deny read; IDOR→404 lives in ONE place (§19) |
| `compaction:chat_history` (summarize-beyond-budget) | API/Backend capability + deepagents middleware | Kernel port (`compaction` kind) | Backend-owned (D-08); in-graph growth handled by `SummarizationMiddleware` |
| `context_provider:conversation` (compacted history → context) | Kernel-side capability (`agents/capabilities/context_providers/`) | Database/Storage (reads `run_events`) | Pure `ContextProvider` port; import-linter keeps it off `app.*` |
| Proposal execution (gate/steering/revision) | API/Backend (`app/api/run_commands.py`) | — | Same channels the mechanical router uses; app disposes, Concierge proposes |
| Confirm-chip UX + compact affordance + token display | Frontend (`RunChatLane` + P26 token widget) | — | FE only displays/confirms; no FE compression (D-08) |
| Post-run turn → revision run stitching | API/Backend (`run_commands` revision channel) | — | Reuse `_mint_revision_row`/`_drive_revision_to_queue` family seam (D-02) |

---

## Registry Lockstep & the 3 New Capabilities

### The `@register` decorator signature **[VERIFIED: registry.py:180-218]**
```python
def register(
    kind: str,
    name: str,
    *,
    user_allowed: bool = False,
    description: str = "",
    config_schema: dict | None = None,
) -> Callable[[type[_T]], type[_T]]:
    # side effects at import:
    #   _KNOWN.add((kind, name))                 # ← membership is AUTOMATIC (line 209)
    #   _IMPLS[(kind, name)] = cls()             # instantiates the class ONCE
    #   _TRUST[(kind, name)] = user_allowed
    #   _META[(kind, name)] = {description, config_schema}
```
Decorate a **stateless impl class** exposing a `name` attribute matching the registry key. The decorator returns the class unchanged.

### `discover()` wiring **[VERIFIED: registry.py:221-344]**
`discover()` is lazy (engine import / first `execute()` / first `resolve()`), idempotent (guarded by `_DISCOVERED`), and **explicitly** `importlib.import_module`s a hardcoded tuple — NO auto-walk. Two lists:
- `_builtin_modules` (`registry.py:252`) — kernel-side capability modules, imported eagerly. **Add `compaction:chat_history` and `context_provider:conversation` module paths here** (e.g. `"agents.capabilities.compaction.chat_history"`, `"agents.capabilities.context_providers.conversation"`).
- `_forward_packages` (`registry.py:312`) — best-effort package imports incl. the app-side `app.agents.*` packages (heavy-dep impls that import the kernel PORT, never the reverse). **The Concierge's heavy-dep impl registers via an app-side package here** (e.g. add/extend an `"app.agents.chat"` or similar package that self-registers `chat:concierge`), so `agents.capabilities` never imports `app.*`.

### The drift-guard test to bump **[VERIFIED: test_registry_capabilities.py:38-164]**
Function name is **stale** (`test_registered_count_is_exactly_fifty`) but it asserts:
```python
assert len(_KNOWN) == 66            # ← line 163: bump to 69
assert set(_KNOWN) == set(_EXPECTED_NAMES)   # ← line 164
```
So the planner MUST:
1. Add the 3 pairs to `_EXPECTED_NAMES` (`test_registry_capabilities.py:38`).
2. Change `66` → `69` at line 163 (and append 3 lines to the running comment tally at lines 129-162, matching house style).
3. Optionally seed the 3 pairs in the `_KNOWN` literal (`registry.py:81`) for the compiler-import-time membership path — the codebase seeds names in the literal AND lets `@register` re-add them (idempotent set-add). Both the current `uploaded_files`/`run_images` entries do this. **Recommended: add all 3 to the `_KNOWN` literal** so manifest references validate at compiler import with zero impls bound (INV-4 pure-membership path — `test_membership_path_is_impl_free_at_import`).

### Per-capability module placement

| Capability | Kind | Module path (kernel vs app) | Port | `user_allowed` | Discover list |
|------------|------|-----------------------------|------|----------------|---------------|
| `compaction:chat_history` | `compaction` | `agents/capabilities/compaction/chat_history.py` (kernel-pure, like `html_skeleton.py`) | duck-typed `compact(...)` — the `compaction` kind has **no formal Protocol port** (`html_skeleton` is duck-typed `compact(html)->str`) | `False` (or `True` if user-selectable) | `_builtin_modules` |
| `context_provider:conversation` | `context_provider` | `agents/capabilities/context_providers/conversation.py` (kernel-pure clone of `uploaded_files.py`) | `ContextProvider` (`base.py:76`) — `async load(ctx) -> dict[str,str]` | inherit `uploaded_files` (no explicit flag = default `False`) | `_builtin_modules` |
| `chat:concierge` | `chat` (NEW kind — free string, no central if/elif) | **app-side** impl under `app/agents/**` (heavy-dep: reaches `deep_agent_runner`/`create_deep_agent`); registers via a `_forward_packages` app package | `AgentRuntimeAdapter`-adjacent / bespoke — **[ASSUMED: A1]** likely a thin orchestrator port; confirm exact port shape at plan time | `False` (privileged — runs a model, spawns proposals) | `_forward_packages` (app-side) |

**Note on the `chat` kind:** KIND strings are free (registry docstring line 22-24: "there is no central if/elif over KIND strings; KINDs are free strings keyed in `_KNOWN`"). `test_new_kinds_are_accepted` proves an arbitrary new kind registers. So `("chat", "concierge")` needs no special-casing. **[VERIFIED: registry.py:22-24, test_registry_capabilities.py:294-300]**

**Import-linter direction (CRITICAL):** the two providers are kernel-side and MUST import ONLY the registry decorator + stdlib (no `app.*`, no `agents.execution_engine`) — mirror the `uploaded_files.py` import-purity docstring (lines 34-37). The Concierge's model-calling impl lives app-side and imports the kernel PORT (the legal `app → ports` direction), registered by the registry importing its package. Expect **4 kept / 0 broken** contracts.

---

## deepagents 0.6.7 API (verified)

**Installed:** `deepagents==0.6.7` at `/opt/homebrew/lib/python3.11/site-packages/deepagents/`. **[VERIFIED: `python3.11 -c import deepagents`]**

### `create_deep_agent(...)` — full signature **[VERIFIED: `inspect.signature`]**
```python
create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware] = (),        # ← composition seam
    subagents: Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    permissions: list[FilesystemPermission] | None = None,
    backend: BackendProtocol | Callable[...] | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    response_format = None,
    state_schema: type[DeepAgentState] | None = None,
    context_schema: type | None = None,
    checkpointer: None | bool | BaseCheckpointSaver = None,
    store: BaseStore | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph
```

### How the runner already composes it (the Concierge rides this) **[VERIFIED: deep_agent_runner.py:347-356]**
```python
self._graph = create_deep_agent(
    model=self._model,                       # build_model(...) — Haiku default; INV-13
    tools=self.tools,
    system_prompt=system_prompt,
    subagents=None,                          # library sub-agent dispatch OFF
    middleware=[_ToolFilterMiddleware(excluded=excluded),
                _BedrockCachePointsMiddleware()],   # ← P26 caching inherited here
    backend=backend,
    checkpointer=checkpointer,
    interrupt_on=interrupt_on,
)
```
**The Concierge inherits P26 Bedrock prompt-caching automatically** by running through `DeepAgentRunner` — `_BedrockCachePointsMiddleware` (`deep_agent_runner.py:205-258`) injects `cache_control` on `ChatBedrockConverse` requests, gated by `settings.BEDROCK_PROMPT_CACHE_ENABLED` (default ON), no-op on ChatAnthropic/scripted-fake. **Do NOT add a second cache middleware.** Multi-turn cache-point PLACEMENT is Phase-34 live.

### `SummarizationMiddleware` — in-graph history growth **[VERIFIED: `inspect.signature`, graph.py]**
Two forms exist:
- **deepagents base-stack default:** `create_deep_agent` already wires `create_summarization_middleware(model, backend)` (`deepagents.middleware.summarization`, signature `(model: BaseChatModel, backend) -> _DeepAgentsSummarizationMiddleware`) — so summarization is ALREADY ON in every agent graph (comment at `deep_agent_runner.py:346`: "Summarization stays on (base-stack default)"). **[VERIFIED: graph.py:53/595/667/740]**
- **Public tunable (langchain):** `langchain.agents.middleware.SummarizationMiddleware.__init__`:
```python
SummarizationMiddleware(
    model: str | BaseChatModel,
    *,
    trigger: ('fraction', float) | ('tokens', int) | ('messages', int) | list[...] | None = None,
    keep: ('fraction', float) | ('tokens', int) | ('messages', int) = ('messages', 20),
    token_counter: Callable[[Iterable[BaseMessage|...]], int] = count_tokens_approximately,
    summary_prompt: str = "<role>Context Extraction Assistant...",   # long default
    trim_tokens_to_summarize: int | None = 4000,
)
```
This is the knob for `compaction:chat_history`: **`trigger`** sets the budget (e.g. `('tokens', N)` or `('fraction', 0.8)`), **`keep`** sets the recent-verbatim window (e.g. `('messages', 20)` or `('tokens', N)`), `summary_prompt` shapes the summary of the older tail. Note `SummarizationMiddleware is not create_summarization_middleware` (the deepagents wrapper differs from the langchain class — `DA_Sum is SummarizationMiddleware → False`). **[VERIFIED: `python3.11 -c`]**

**Design note for `compaction:chat_history`:** the CONTEXT frames two layers — (1) *backend-owned transcript compaction* that bounds the composed `context_provider:conversation` block (summarize turns beyond budget, keep recent verbatim), provable OFFLINE as a pure function like `html_skeleton.compact(...)`; and (2) *in-graph growth* handled by the deepagents `SummarizationMiddleware` already in the Concierge's runner. Layer (1) is the phase's testable deliverable (§Compaction-Under-Budget). **[CITED: 33-CONTEXT.md D-08]**

---

## Phase-29 Seams to Build On

### 1. Chat router escalation point **[VERIFIED: chat_router.py]**
- `route_chat_turn(run_state: RunState, turn: ChatTurn) -> Dispatch` at **`chat_router.py:235`** — PURE, zero model calls, keys only on generic `RunState.phase` (clarify_waiting/gate_paused/running/terminal) + generic turn discriminators. Docstring line 32-33 explicitly reserves: *"Free-form / ambiguous turns … are left for the Concierge escalation (Phase 33)."*
- `Dispatch` dataclass (`chat_router.py:154`) carries per-channel params; channels are `CHANNEL_ANSWERS/GATE/STEERING/REVISION` (`chat_router.py:49-52`).
- **Escalation design (build here):** add a `CHANNEL_CONCIERGE` constant + a `Dispatch` branch for genuinely free-form turns, BUT keep the model-free guarantee: routable turns (structured clarify responses, gate `action` in `GATE_ACTIONS`, revision after terminal, steering-with-`sticky`) MUST still resolve to their existing channels with zero model call. The Concierge is invoked in the app layer (`post_message`) when the dispatch is `CHANNEL_CONCIERGE`. **[ASSUMED: A2]** exact free-form predicate (e.g. "running/terminal + no action + question-shaped") is a plan-time decision; keep it a pure structural check, never a workflow-name branch (INV-1).

### 2. Owner-scoped READ surface **[VERIFIED: authz.py]**
- `class ScopedStore` at **`authz.py:58`**, constructed `ScopedStore(owner_id, workspace_id, session=None)`.
- `async def read_events(self, run_id, after_seq)` at **`authz.py:314`** — owner+workspace scoped (`_scope_owner_ws`), ordered by `seq` asc; cross-owner returns nothing → 404. This is the Concierge READ-tools source AND `context_provider:conversation`'s source.
- Artifact reads: `list_refs(run_id, kind=None)` (`authz.py:228`), `get_ref` (`authz.py:211`), `lineage`/`tree` (`authz.py:251/276`). Gate/step audit: `read_gate_events` (`authz.py:831`).
- IDOR is enforced in ONE place — the default-deny filters `_scope_owner_ws` (`authz.py:119`) / `_scope_with_visibility` (`authz.py:104`). Concierge read tools MUST go through `ScopedStore`, never raw ORM.

### 3. Proposal execution channels (app layer disposes) **[VERIFIED: run_commands.py:526-609]**
Already wired in `post_message` (`run_commands.py:419`):
- **Gate:** `await art_store.set_review_response(gate_key, approved=..., action=..., instructions=...)` — four actions; `update_specs` → KAN-101 loop (lines 550-554). `_gate_is_pending` (line 505) gates on KAN-94 armed ground truth.
- **Steering:** `apply_steering(ectx, note)` → `ectx.steering_notes` (`chat_router.py:301-316`); best-effort (no-op without live ectx handle — DEF-29-09-1). Durable `chat_message` row is the record; engine re-derives from `run_events` (ND-9).
- **Revision:** `_mint_revision_row(rdb, user, parent_run_id, target_artifact_type, instruction)` + `asyncio.create_task(_drive_revision_to_queue(...))` (`run_commands.py:584-605`) — mints + drives the family child run onto the per-run queue.
- **Concierge proposal mapping:** `propose_gate_action` → `set_review_response`; `propose_steering_note` → `apply_steering`; `propose_revision` → `_mint_revision_row`+`_drive_revision_to_queue`. Consequential proposals behind a confirm chip (the app layer holds the proposal until the FE confirms, then calls the seam). No new execution path — reuse these.

### 4. Revision-family stitching (D-02) **[VERIFIED: run_commands.py:577-609]**
Post-terminal free-form turns already route to `CHANNEL_REVISION` and mint a family child via the shipped revision seam. Reuse `_mint_revision_row`/`_drive_revision_to_queue` + `REVISION_BASE_MAP` (registry). Do NOT fork a new revision path. Live stitching (the child run's events flowing back into the family transcript) rides the existing per-run queue + `run_events`.

### 5. Persistence (additive-only) **[VERIFIED: run_commands.py:365-416, authz.py:284-389]**
- Chat turns reuse `run_events` (`type="chat_message"`), idempotent by `event_id = chat:{message_id}` via `append_event_next_seq` (`authz.py:331`, optimistic-concurrency on `uq_run_events_run_seq`/`uq_run_events_run_event`, migration 0024).
- `chat_reply` (narrator/assistant projection) is a documented type for Concierge answers back to the lane.
- ANY new persisted row carries `owner_id` + `workspace_id` (stamped by `ScopedStore`). Prefer reusing `run_events` for concierge messages — no new table needed (LOCK-B precedent).

---

## INV-3 Golden Characterization

### The 5 goldens **[VERIFIED: test_chat_event_neutrality.py:37-45]**
`prototype`, `od_prototype`, `od_ppt`, `prototype_revision`, `app_builder` — event streams at `tests/agents/characterization/golden/{pipeline}.events.json`.

### `test_chat_contract.py` — DO NOT TOUCH **[VERIFIED: test_chat_contract.py:1-61]**
This is the FROZEN `ChatRunner` free-chat contract golden (the `user_message` multi-phase sequencer). INV-12 forbids forking `ChatRunner` or touching this golden. It is a *separate subsystem* from the run-chat lane; the Concierge does NOT run through `ChatRunner`. Leave it untouched.

### The event-type + normalizer registries
- **`_DOCUMENTED_EVENT_TYPES`** — `test_phase3_cutover_verify.py:182`; already contains `chat_message`, `chat_reply`, `stream_attached` (lines 241-243). Any NEW Concierge event type (e.g. a `concierge_proposal`) MUST be added here or the forward-vocabulary guard rejects it. **[VERIFIED: test_phase3_cutover_verify.py:182-243]**
- **`_VOLATILE_STRIP_KEYS`** — `tests/agents/characterization/_normalize.py:101`; strips run-specific/additive keys (`seq`, `event_id`, `message_id`-adjacent, `deliverable_mimetype`, cache keys, `image_count`, etc.) so additive `pipeline_complete` keys stay parity-neutral. Any NEW `pipeline_complete` key the Concierge/compaction path adds MUST be added here. **[VERIFIED: _normalize.py:95-174]**

### The concierge-dormant assertion (standing proof) **[VERIFIED: test_chat_event_neutrality.py:60-89]**
`test_chat_events_absent_from_golden` asserts the chat event types appear in NONE of the 5 golden `type` sequences. **Extend this guard to include any new Concierge event types.** The scripted characterization harness has no chat lane, so a golden run emits none — that neutrality is exactly what keeps INV-3 holding while the vocabulary grows.

### Byte-identical proof procedure
1. Ensure `SNAPSHOT_UPDATE` is UNSET (do NOT regenerate fixtures).
2. Run the characterization suite for the 5 pipelines + `test_chat_event_neutrality.py` + `test_phase3_cutover_verify.py`.
3. A passing run against the UNCHANGED `golden/*` fixtures IS the proof. `seq`-contiguity is checked separately on raw events; the multiset parity is checked on normalized events.

---

## Compaction-Under-Budget Proof

**Model the offline test on `test_phase3_compaction.py`** (`tests/agents/test_phase3_compaction.py`) — the deterministic, fully-offline CI half of the token-trim phase. Shape **[VERIFIED: test_phase3_compaction.py:1-138]**:

1. Import `_scripted_model` first (side-effect: `RUNS_ROOT`→temp, `ENV=development`) so the test is fully offline.
2. Build a **long transcript fixture** (many chat turns; a generous `_FILLER`-style body so the full block is a realistic input-token proxy — the existing test uses a 60×-repeated paragraph to exceed a realistic ceiling).
3. Call the compaction capability directly: `ChatHistoryCompaction().compact(transcript, budget=...)` (mirror `HtmlSkeletonCompaction().compact(html)`).
4. **Assert the two properties:**
   - **Under budget:** composed context length (or token count via `count_tokens_approximately`) ≤ the configured budget — the analog of `test_html_skeleton_reduction_gate` (`assert len(skeleton) <= 0.5 * len(source)`).
   - **Recent verbatim + older summarized:** the N most-recent turns appear **byte-for-byte** in the output (fidelity assertion, analog of `test_html_skeleton_is_faithful_to_source`), while older turns are replaced by a summary marker/shorter form. Assert a specific recent turn's exact text is present and a specific old turn's verbatim text is absent (summarized).

This proves SC-2 with zero network/Bedrock. The `context_provider:conversation` provider then composes that bounded output into the Concierge/steering context block (a second unit test asserts the provider returns the compacted block, cloning `test_uploaded_files_provider.py` shape).

---

## SC-001 Proof Strategy

**Claim:** a brand-new custom workflow gets lane + router + Concierge with ZERO engine/FE/orchestrator code.

**Why it holds structurally (from evidence):**
- The mechanical router keys ONLY on generic `RunState` (status + open_gate + gate_key) — never a workflow name (`chat_router.py:9-14, 94-106`). A new workflow's runs produce the same generic signals → the router works unchanged.
- The Concierge is ONE capability resolved by `(kind="chat", name="concierge")` via `registry.resolve(...)` — a static dict lookup, no workflow branch (`registry.py:393-413`). Workflow-specificity is injected as DATA: the compiled manifest's `chat:` block, artifacts, events, and the conversation context (all read at runtime).
- The `chat:` manifest key compiles as DATA (INV-5) — a new workflow authors optional `chat:` suggestions/notes; no compiler control-flow keys off it.

**The proof test (build here):** author a **throwaway custom manifest** (a minimal `workflow.yaml` with a `chat:` data block and a generic agent sequence) under a test fixture, compile it, and assert:
1. Its runs route through `route_chat_turn` identically (a free-form turn → `CHANNEL_CONCIERGE`; a gate turn → `CHANNEL_GATE`) with NO code referencing the new workflow's name.
2. `registry.resolve("chat", "concierge")` returns the same shared impl.
3. `grep` for the throwaway workflow name in `agents/execution_engine/`, `app/api/chat_router.py`, and the Concierge impl returns **0** (the SC-001 grep gate — mirror the Phase-7 `if pipeline_type`/`spec.id ==` → 0 gate).

This is the milestone core-value proof (ROADMAP SC-4). **[CITED: 33-CONTEXT.md, IMPLEMENTATION-REGISTER §Phase 7 SC-001 PROVEN precedent]**

---

## Dependency Ordering

**Forced order:** `compaction:chat_history` → `context_provider:conversation` → `chat:concierge`.

1. **`compaction:chat_history` first** — it is a pure function (`compact(...)`) with an offline reduction+fidelity gate; nothing depends on runtime state. It defines the bounded-history contract.
2. **`context_provider:conversation` second** — it READS the compacted history (calls the compaction contract) and exposes it as a `dict[str,str]` context block. It depends on (1) for what "bounded" means, and on `ScopedStore.read_events` (already shipped, Phase 29).
3. **`chat:concierge` last** — it CONSUMES the conversation context block (composed into its system prompt via the context-provider loop) plus its READ tools + proposal tools. It cannot be meaningfully built or tested until (1) and (2) bound its input.

Bump the drift guard `66 → 69` in the SAME commit that adds all three to `_KNOWN`/`_EXPECTED_NAMES`/`discover()` — a partial bump breaks `test_registered_count_is_exactly_fifty` (which asserts BOTH the count AND `set(_KNOWN) == set(_EXPECTED_NAMES)`). If landing incrementally, bump the count per-capability (66→67→68→69) with matching `_EXPECTED_NAMES` additions each step so the guard stays green at every commit.

---

## Validation Architecture

**nyquist_validation = true** (config.json) — validation section included. **Offline-only** (full pytest HANGS: Chromium/Bedrock/Postgres-gated — memory note "offline-test-suite-targeted"). Runner: `python3.11` (no venv).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio, Hypothesis) — `python3.11 -m pytest` |
| Config | `backend/` project config; `_scripted_model` harness for offline (sets `RUNS_ROOT`→temp, `ENV=development`) |
| Quick run | `python3.11 -m pytest tests/agents/test_registry_capabilities.py -x` |
| Register/parity suite | `python3.11 -m pytest tests/agents/test_registry_capabilities.py tests/agents/test_chat_event_neutrality.py tests/agents/test_phase3_cutover_verify.py` |
| Import gate | `/opt/homebrew/bin/lint-imports` (expect **4 kept / 0 broken**) |

### Requirements → Test Map (offline)
| Req | Behavior | Test type | Command | Exists? |
|-----|----------|-----------|---------|---------|
| Registry lockstep | 3 new caps registered + count = 69 + `_KNOWN`==`_EXPECTED_NAMES` | unit | `pytest tests/agents/test_registry_capabilities.py -x` | ✅ (bump 66→69) |
| discover() binds impls | resolve() returns each new impl | unit | `pytest tests/agents/test_registry_capabilities.py -k discover` | ✅ pattern exists |
| `context_provider:conversation` | returns compacted block; dormant un-gated | unit | new `tests/agents/test_conversation_provider.py` (clone `test_uploaded_files_provider.py`) | ❌ Wave 0 |
| `compaction:chat_history` under budget | long transcript ≤ budget, recent verbatim | unit | new `tests/agents/test_chat_history_compaction.py` (clone `test_phase3_compaction.py`) | ❌ Wave 0 |
| Router escalation | free-form → CONCIERGE; routable → zero-model existing channel | unit | new `tests/unit/test_concierge_escalation.py` (extend router tests) | ❌ Wave 0 |
| Proposal → channel | `propose_*` disposed via `set_review_response`/`apply_steering`/`_mint_revision_row` | unit | new test (mock the seams) | ❌ Wave 0 |
| INV-3 goldens byte-identical | 5 goldens unchanged; concierge dormant | characterization | `SNAPSHOT_UPDATE` unset + `pytest tests/agents/test_chat_event_neutrality.py` (extend for new event types) | ✅ (extend) |
| Import purity | providers ↛ app; concierge app-side ↛ kernel-reverse | lint | `/opt/homebrew/bin/lint-imports` | ✅ |
| INV-13 | `create_deep_agent` only in allow-listed module | banned-pattern | `pytest tests/agents/test_banned_patterns.py` | ✅ |
| SC-001 | throwaway manifest → lane+router+Concierge, grep name → 0 | integration+grep | new fixture test | ❌ Wave 0 |

### Wave 0 gaps
- [ ] `tests/agents/test_chat_history_compaction.py` — under-budget + fidelity (clone `test_phase3_compaction.py`)
- [ ] `tests/agents/test_conversation_provider.py` — provider load + dormant (clone `test_uploaded_files_provider.py`)
- [ ] `tests/unit/test_concierge_escalation.py` — router escalation classification (zero-model on routable)
- [ ] proposal→channel unit test — Concierge proposals dispose through existing seams
- [ ] SC-001 throwaway-manifest fixture + grep gate
- [ ] extend `test_chat_event_neutrality.py` for any new Concierge event type(s)

### LIVE-DEFERRED to Phase 34 (mark `human_needed`, do NOT hang/fabricate)
- Live Concierge Q&A against a real Bedrock model
- Multi-turn cache-point PLACEMENT confirmation
- Live mid-run steering delivery (needs the DEF-29-09-1 live in-process ectx handle — `_live_ectx_for_run` returns `None` today, `run_commands.py:350-362`)

---

## Security Domain

**security_enforcement = true, ASVS level 1** (config.json).

### Applicable ASVS categories
| Category | Applies | Standard control (in-codebase) |
|----------|---------|-------------------------------|
| V4 Access Control | **yes** | `ScopedStore` default-deny owner+workspace scope; Concierge reads via `read_events`/`list_refs`; cross-owner → nothing → **404 (never 403)** (`authz.py:104-127, 314`). Two-layer owner check in `post_message` (`run_commands.py:446-472`). |
| V5 Input Validation | **yes** | Chat turn `text` free-form (sanitize at render); per-turn images cap-validated via `_validate_images` (mime allow-list, ~3.75MB/img, ≤20, ~8MB aggregate) BEFORE persist (`run_commands.py:474-489`). |
| V6 Cryptography | no (new) | Secrets Fernet-encrypted in existing `ScopedStore.write_mcp_credential` — Concierge holds no new secrets. |
| V2/V3 Auth/Session | no (new) | `Depends(get_current_user)` on `post_message` — reused. |

### Threat patterns
| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Concierge reads another owner's run events/artifacts (IDOR) | Information Disclosure | ALL reads through `ScopedStore` (owner+workspace filter) → 404; NEVER raw ORM |
| Concierge executes a consequential proposal without consent | Elevation / Tampering | Proposal-only tools; app disposes; consequential ones behind confirm chip |
| Prompt injection via run content into Concierge model | Tampering | Concierge is proposal-only (cannot self-execute); READ tools are scoped; treat run content as untrusted context |
| `chat:concierge` code-exec/spawn | Elevation | `exec`/`spawn_subagents` default OFF (§Constraints); Concierge runtime is model+read+propose only |
| Fabricated gate resolution on a stopped run | Tampering | KAN-100 terminal fence + KAN-94 armed-gate ground truth already enforced in `post_message` |

---

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python · FastAPI · PostgreSQL · LangGraph checkpointer — extend, don't replace.
- **INV-13:** every agent (incl. Concierge) on `deepagents==0.6.7`, `from deepagents import create_deep_agent`, adapter id `langchain_deepagents`; no hand-rolled deep agent; banned-pattern CI gate (R15). Verified installed `deepagents 0.6.7`.
- **Hexagonal:** kernel depends only on capability ports; concrete impls self-register; adding a capability = add module + register, no kernel edit; enforced by import-linter (§31).
- **Compiler thin, no DSL (INV-5):** manifests are data (`chat:` block compiles as data).
- **Additive migrations only (Q3):** every new table carries `owner_id` + `workspace_id`. (Prefer reusing `run_events` — no new table.)
- **No dual implementations (INV-3/INV-12):** reuse Phase-29 seams; deleting superseded code is part of the change.
- **GSD workflow enforcement:** edits go through a GSD command.
- **Offline verify:** targeted suites + `/opt/homebrew/bin/lint-imports` + `python3.11`; NEVER run full pytest (hangs). Commit-scope prefixes per `backend/CLAUDE.md`.

---

## Runtime State Inventory

This is an **additive backend capability** phase (not a rename/migration). No stored-key renames, no OS-registered state, no build-artifact churn. The only persistence touch is **reuse** of `run_events` (`chat_message`/`chat_reply`) — additive rows, not schema changes. Explicitly:
- Stored data: **None new** — chat reuses `run_events`; no key/collection renamed.
- Live service config: **None** — no external service config embeds anything.
- OS-registered state: **None**.
- Secrets/env vars: **None new** — `settings.BEDROCK_PROMPT_CACHE_ENABLED` reused (already ON, P26).
- Build artifacts: **None** — no package rename.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `chat:concierge` needs a bespoke/thin orchestrator port (exact port shape TBD at plan time; may reuse `AgentRuntimeAdapter` or a new `chat` Protocol in `base.py`) | Registry §per-capability table | A `base.py` port addition is a kernel edit — must confirm whether the `chat` kind needs a formal Protocol or stays duck-typed like `compaction:html_skeleton`. Low risk (duck-typed precedent exists). |
| A2 | The free-form "escalate to Concierge" predicate is a pure structural check added in the app layer (`post_message`), NOT in `route_chat_turn`, to preserve zero-model routing | Phase-29 Seams §1 | If added inside `route_chat_turn`, risks a model call on the pure router path (breaks D-04). Mitigated by the locked "routable = zero model" decision. |
| A3 | `compaction:chat_history` is provable offline as a pure `compact(...)` function (analog to `html_skeleton`) separate from the in-graph `SummarizationMiddleware` | deepagents API / Compaction-Under-Budget | If compaction can only be observed in-graph, the offline shape proof is harder; but D-08 frames it as backend-owned + FE displays usage, implying a testable pure layer. |
| A4 | New Concierge event type(s) (if any beyond `chat_reply`) must be added to `_DOCUMENTED_EVENT_TYPES` + neutrality guard | INV-3 Golden | Skipping this fails the forward-vocabulary guard; low risk (mechanism is documented). |

---

## Open Questions

1. **Does the `chat` kind need a formal Protocol port in `base.py`?**
   - Known: KIND strings are free; `compaction:html_skeleton` is duck-typed with no port; new kinds register without a central if/elif.
   - Unclear: whether the Concierge orchestrator wants a typed port for the plan-checker's tier verification.
   - Recommendation: prefer duck-typed (no `base.py` edit) unless the planner needs a typed contract; if a port is added, it is a one-method Protocol like the others.

2. **Exact budget/keep values for `compaction:chat_history`.**
   - Known: `SummarizationMiddleware` defaults `keep=('messages', 20)`, `trim_tokens_to_summarize=4000`.
   - Unclear: the target token budget for the composed conversation block.
   - Recommendation: parameterize `compact(transcript, budget, keep_recent)`; assert the shape (under budget + recent verbatim) rather than a magic number, so the test is robust.

3. **Where does the Concierge's heavy-dep impl package live for `discover()`?**
   - Known: app-side capability packages are imported in `_forward_packages` (`app.agents.validators`, `app.agents.runtime`, `app.agents.repo_index`).
   - Recommendation: add an analogous `app.agents.chat` (or reuse an existing app package) that self-registers `chat:concierge`, so `agents.capabilities` never imports `app.*`.

---

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `deepagents` | Concierge runtime (INV-13), SummarizationMiddleware | ✓ | 0.6.7 | — |
| `langchain.agents.middleware` | `SummarizationMiddleware`, `AgentMiddleware` | ✓ | (bundled) | — |
| `python3.11` | test/runtime | ✓ | project Python | — |
| `/opt/homebrew/bin/lint-imports` | import-linter gate | ✓ (memory-confirmed) | — | — |
| Bedrock / SSO | live Concierge Q&A + cache placement | ✗ (offline) | — | **Phase-34 live-deferred** (`human_needed`) |
| Postgres / Chromium | full pytest | ✗ (offline) | — | targeted offline suites only |

**Missing with fallback:** live Bedrock → defer live Q&A/cache/steering to Phase 34; build + offline-prove here.

---

## Sources

### Primary (HIGH confidence — read/executed this session)
- `backend/agents/capabilities/registry.py` (lines 81, 180-218, 221-344, 393-413) — lockstep mechanics
- `backend/tests/agents/test_registry_capabilities.py` (38-164) — drift guard (66→69)
- `backend/agents/capabilities/base.py` (76-83, 157-169) — ContextProvider / AgentRuntimeAdapter ports
- `backend/agents/capabilities/context_providers/uploaded_files.py` (58-138) — clone target
- `backend/app/api/chat_router.py` (235-316) — mechanical router + escalation seam
- `backend/agents/authz.py` (58, 104-127, 314) — ScopedStore read surface
- `backend/app/api/run_commands.py` (365-416, 419-614) — chat lane + proposal channels
- `backend/app/agents/deep_agent_runner.py` (205-258, 298-356) — create_deep_agent + P26 cache middleware
- `backend/tests/unit/test_chat_contract.py` (1-61) — frozen ChatRunner golden (do-not-touch)
- `backend/tests/agents/test_chat_event_neutrality.py` (34-89) — concierge-dormant standing proof
- `backend/tests/agents/characterization/_normalize.py` (95-174) — `_VOLATILE_STRIP_KEYS`
- `backend/tests/agents/test_phase3_compaction.py` (1-138) — compaction-under-budget test shape
- `backend/agents/capabilities/compaction/html_skeleton.py` (1-60) — compaction port shape (duck-typed `compact`)
- `python3.11 -c inspect` — `create_deep_agent` + `SummarizationMiddleware` + `create_summarization_middleware` signatures; `deepagents==0.6.7`
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 5 (ScopedStore), Phase 7 (SC-001 proven), Phase 8 (registry `@register`/`discover`)

### Locked design (CITED)
- `.planning/phases/33-concierge-compaction-a5/33-CONTEXT.md` — the phase contract (D-04/D-05/D-08, invariants)
- `backend/CLAUDE.md`, `./CLAUDE.md` — project constraints (INV-13, hexagonal, additive migrations)

---

## Metadata

**Confidence breakdown:**
- Registry lockstep: **HIGH** — exact decorator/`discover()`/drift-guard read at file:line; count 66→69 verified.
- deepagents API: **HIGH** — signatures from live `inspect` on installed 0.6.7.
- Phase-29 seams: **HIGH** — router/ScopedStore/run_commands all read at file:line.
- INV-3 goldens: **HIGH** — neutrality + normalizer registries read directly.
- Compaction proof shape: **HIGH** (test pattern) / **MEDIUM** (`compact` API for chat is A3-assumed, not yet built).
- `chat:concierge` port shape: **MEDIUM** — A1 (duck-typed vs Protocol) is a plan-time decision.

**Research date:** 2026-07-08
**Valid until:** ~2026-08-07 (stable brownfield codebase; deepagents pinned at 0.6.7)

## RESEARCH COMPLETE
