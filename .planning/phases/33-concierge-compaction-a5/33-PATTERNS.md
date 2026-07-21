# Phase 33: Concierge + Compaction [A5] - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 3 new capabilities + 5 registry/test lockstep files + 2 Phase-29 seams + 3 FE + 4 characterization/gate tests + new unit tests
**Analogs found:** 18 / 18 (every new file has a concrete in-tree analog; the `chat:concierge` orchestrator port is the one MEDIUM — duck-typed vs Protocol is a plan-time call, precedent exists)

All analog claims carry file:line. Build order below matches the forced dependency chain from RESEARCH §Dependency Ordering: **(1) compaction + conversation provider + registry lockstep → (2) concierge + router escalation + proposal channels → (3) revision stitching + FE + SC-001 proof + golden neutrality**.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/capabilities/compaction/chat_history.py` | capability impl (kernel-pure) | transform (pure `compact()`) | `agents/capabilities/compaction/html_skeleton.py:29-107` | exact (same kind, duck-typed `compact`) |
| `backend/agents/capabilities/context_providers/conversation.py` | capability impl (kernel-pure) | request-response (async `load`) | `agents/capabilities/context_providers/uploaded_files.py:58-138` | exact (same port, clone) |
| `backend/app/agents/chat/concierge.py` (+ pkg `__init__`) | capability impl (app-side, heavy-dep) | request-response + event-driven (model call + propose) | `app/agents/deep_agent_runner.py:347-356` (runner) | role-match (net-new orchestrator port — A1) |
| `backend/agents/capabilities/registry.py` | registry | — | self (`_KNOWN:81`, `discover():252/312`) | exact (mechanical edit) |
| `backend/tests/agents/test_registry_capabilities.py` | test (drift guard) | — | self (`_EXPECTED_NAMES:38`, count assert `:163`) | exact |
| `backend/tests/agents/test_input_providers_run_images.py` | test (count assert) | — | self (`:132`) | exact |
| `backend/tests/agents/test_uploaded_files_provider.py` | test (count assert) | — | self (`:200`) | exact |
| `backend/app/api/chat_router.py` | router | request-response | self (`route_chat_turn:235`) | exact (add CHANNEL_CONCIERGE branch) |
| `backend/app/api/run_commands.py` | API command handler | CRUD / event-driven | self (`post_message` dispatch `:525-609`) | exact (add proposal→channel disposal) |
| `backend/tests/agents/test_chat_history_compaction.py` | test (new) | transform | `tests/agents/test_phase3_compaction.py:1-80` | exact (clone) |
| `backend/tests/agents/test_conversation_provider.py` | test (new) | request-response | `tests/agents/test_uploaded_files_provider.py:1-60` | exact (clone) |
| `backend/tests/unit/test_concierge_escalation.py` | test (new) | request-response | `chat_router.py` router tests | role-match |
| proposal→channel unit test (new) | test | event-driven | `run_commands.py:525-609` seams (mock) | role-match |
| SC-001 throwaway-manifest fixture test (new) | test (integration+grep) | — | `tests/agents/test_sc001_gate_flag.py:1-40` | role-match |
| `backend/tests/agents/test_chat_event_neutrality.py` | test (extend) | — | self (`:60-89`) | exact (extend guard) |
| `backend/tests/agents/characterization/_normalize.py` | test infra (extend) | — | self (`_VOLATILE_STRIP_KEYS:101`) | exact |
| `frontend/src/components/chat/RunChatLane.tsx` | FE component | request-response | self (`:16` chips, `:38` ChatTokenWidget import) | exact (add confirm chips + compact affordance) |
| `frontend/src/components/chat/ChatTokenWidget.tsx` | FE component | request-response | self (P26 token/context-usage widget — EXISTS) | exact (token/context display already here) |

**INV-13 note:** `app/agents/deep_agent_runner.py` is the ONLY allow-listed `create_deep_agent` import site (`test_banned_patterns.py:13-26`). The Concierge impl MUST run its model call THROUGH `DeepAgentRunner`, never `import create_deep_agent` itself — else the banned-pattern gate fails.

---

## Wave 1 — compaction:chat_history + context_provider:conversation + registry lockstep

### `backend/agents/capabilities/compaction/chat_history.py` (capability, transform)

**Analog:** `agents/capabilities/compaction/html_skeleton.py:29-45`

**Register + duck-typed `compact` pattern** (html_skeleton.py:29-45):
```python
from agents.capabilities.registry import register

@register(
    "compaction",
    "html_skeleton",
    description="Compact prior HTML context down to a structural skeleton to fit the model context window.",
)
class HtmlSkeletonCompaction:
    name = "html_skeleton"
    def compact(self, html: str) -> str:
        ...
```
**What changes:** kind stays `"compaction"`, name `"chat_history"`. Signature becomes `compact(self, transcript, *, budget, keep_recent) -> str` (parameterize per RESEARCH Open-Q2 — assert shape, not a magic number). Import-PURE: registry decorator + stdlib ONLY (mirror the docstring purity clause at html_skeleton.py:16-19; NO `app.*`, NO `agents.execution_engine`). The `compaction` kind has NO formal Protocol port — it is duck-typed `compact(...)`, so no `base.py` edit. Summarize turns beyond `budget`, keep the `keep_recent` most-recent turns byte-verbatim. In-graph message growth is separately handled by deepagents' base-stack `SummarizationMiddleware` already wired in the runner — do NOT re-add it (RESEARCH §deepagents API).

### `backend/agents/capabilities/context_providers/conversation.py` (capability, request-response)

**Analog:** `agents/capabilities/context_providers/uploaded_files.py:58-110`

**ContextProvider port** (base.py:75-83):
```python
@runtime_checkable
class ContextProvider(Protocol):
    name: str
    async def load(self, ctx: Any) -> dict[str, str]: ...
```

**Clone shape** (uploaded_files.py:58-110):
```python
@register("context_provider", "uploaded_files", description="...")
class UploadedFilesProvider:
    name = "uploaded_files"
    async def load(self, ctx: Any) -> dict[str, str]:
        injects = set(getattr(ctx, "current_spec_injects", None) or set())
        if "uploaded_files" not in injects:
            return {}                       # ← self-gate on DECLARED inject token (INV-1)
        runner = getattr(ctx, "runner", None)
        sandbox = getattr(runner, "sandbox", None)
        if sandbox is None:
            return {}
        ...
        return {"uploaded_files_context": body}   # ← single named block, or {} on any miss
```
**What changes:** name `"conversation"`, self-gate token `"conversation"`, returned block key `"conversation_context"`. Instead of reading the `.uploads` sidecar via `ctx.runner.sandbox`, it reads compacted chat history: pull `run_events` via the owner-scoped `ScopedStore.read_events(run_id, after_seq)` (`authz.py:314`) and pass them through `compaction:chat_history.compact(...)` (resolved via the registry). Keep degrade-not-crash → `{}` (dormant on golden runs so INV-3 holds). Import-PURE (registry + stdlib only; NO `app.*`). Reach the scoped store via a `ctx` handle, never raw ORM.

### Registry lockstep (3 mechanical edits + literal seeding)

**`registry.py:81` `_KNOWN` literal** — add 3 pairs (RESEARCH recommends seeding the literal so manifest refs validate impl-free at compiler import):
```python
    ("compaction", "chat_history"),          # 33 / D-08
    ("context_provider", "conversation"),    # 33 / D-08
    ("chat", "concierge"),                   # 33 / D-05 (new KIND — free string, no if/elif)
```

**`registry.py:252` `_builtin_modules`** — add the two kernel-side module paths (the concierge is NOT here — it is app-side):
```python
        "agents.capabilities.compaction.chat_history",
        "agents.capabilities.context_providers.conversation",
```
The Concierge registers via `_forward_packages` (`registry.py:312`) — add an app-side package e.g. `"app.agents.chat"` whose `__init__` imports `concierge.py` (so `agents.capabilities` never imports `app.*`; import-linter stays 4 kept / 0 broken).

**`@register` decorator signature** (registry.py:180, verified):
```python
def register(kind, name, *, user_allowed=False, description="", config_schema=None): ...
# side effect at import: _KNOWN.add((kind, name)); _IMPLS[(kind,name)] = cls()
```
Membership is AUTOMATIC on import; discover() wiring + drift-guard bump are the manual steps.

### Drift-guard bump (3 test files, 66 → 69)

**`test_registry_capabilities.py:38` `_EXPECTED_NAMES`** — append the 3 pairs (matching house comment style).
**`test_registry_capabilities.py:163`** — `assert len(_KNOWN) == 66` → `69` (and append 3 lines to the running tally comment at :129-162).
**`test_input_providers_run_images.py:132`** — `assert len(_KNOWN) == 66` → `69`.
**`test_uploaded_files_provider.py:200`** — `assert len(_KNOWN) == 66` → `69`.
Bump all in the SAME commit as the `_KNOWN`/`discover()` edits (a partial bump red-fails `test_registered_count_is_exactly_fifty`, which asserts count AND `set(_KNOWN)==set(_EXPECTED_NAMES)` at :164). If landing incrementally, step 66→67→68→69 with matching `_EXPECTED_NAMES` additions each commit.

### Wave-1 tests

**`test_chat_history_compaction.py`** — clone `test_phase3_compaction.py:1-42`: `from tests.agents import _scripted_model` FIRST (offline env), build a long `_FILLER`-style transcript, call `ChatHistoryCompaction().compact(transcript, budget=...)`, assert (a) under budget — analog of `assert len(skeleton) <= 0.5*len(source)`, and (b) recent-verbatim + old-summarized — a specific recent turn's exact text present, a specific old turn's verbatim text absent.

**`test_conversation_provider.py`** — clone `test_uploaded_files_provider.py:1-60`: `_FakeSandbox`/`SimpleNamespace` ctx fakes, assert `.name == "conversation"`, gated `load` returns `{"conversation_context": ...}`, un-gated / empty → `{}` (dormant), and the registry-lockstep assert here also moves 66 → 69.

---

## Wave 2 — chat:concierge + router escalation + proposal→channel

### `backend/app/agents/chat/concierge.py` (capability impl, app-side, model + propose)

**Analog:** `app/agents/deep_agent_runner.py:347-356` (the ONE sanctioned runner)

**How the runner composes the graph** (deep_agent_runner.py:347-356):
```python
self._graph = create_deep_agent(
    model=self._model,                     # build_model(...) — Haiku default; INV-13
    tools=self.tools,
    system_prompt=system_prompt,
    subagents=None,
    middleware=[_ToolFilterMiddleware(excluded=excluded), _BedrockCachePointsMiddleware()],
    backend=backend,
    checkpointer=checkpointer,
    interrupt_on=interrupt_on,
)
```
**What changes:** The Concierge is ONE per-run instance resolved by `(kind="chat", name="concierge")`. It runs its model call THROUGH `DeepAgentRunner` (inherits P26 `_BedrockCachePointsMiddleware` + base-stack summarization for free — do NOT add a second cache/summarize middleware). Tools split two ways:
- **READ tools** — over `ScopedStore` (owner+workspace scoped, `authz.py:314` `read_events`, `:228` `list_refs`, `:211` `get_ref`, `:831` `read_gate_events`). NEVER raw ORM (IDOR → 404).
- **PROPOSAL-ONLY tools** — `propose_steering_note`, `propose_revision`, `propose_gate_action` (action set incl. `update_specs`). These return structured intents; they do NOT self-execute.

Heavy-dep impl lives UNDER `app/agents/**` (import-linter: capabilities never import kernel/app; the app-side impl imports the kernel PORT — legal `app → ports` direction). **A1 (MEDIUM):** the `chat` kind can stay duck-typed (no `base.py` edit, mirroring `compaction:html_skeleton`) OR add a one-method Protocol port — a plan-time call; prefer duck-typed unless the plan-checker needs a typed contract. `user_allowed=False` (privileged: runs a model). Register via the `app.agents.chat` package in `_forward_packages`.

### `backend/app/api/chat_router.py` (router — add escalation branch)

**Analog:** self, `route_chat_turn:235-295` + the channel constants at `:49-52`

**Existing channel constants** (chat_router.py:49-52):
```python
CHANNEL_ANSWERS = "answers"
CHANNEL_GATE = "gate"
CHANNEL_STEERING = "steering"
CHANNEL_REVISION = "revision"
```
**Existing running-turn fallthrough** (chat_router.py:291-295) — free-form running turns currently ALL become steering:
```python
    # PHASE_RUNNING — steering: queue the note for the NEXT agent dispatch (29-08 seam).
    return Dispatch(channel=CHANNEL_STEERING, note={"text": turn.text, "sticky": bool(turn.sticky)})
```
**What changes:** add `CHANNEL_CONCIERGE = "concierge"` constant + a `Dispatch` branch for genuinely free-form turns. **CRITICAL (A2):** keep the model-free guarantee — routable turns (structured clarify responses, `turn.action in GATE_ACTIONS`, post-terminal revision, steering-with-`sticky`) MUST still resolve to their existing channels with ZERO model call. The escalation predicate is a PURE structural check (e.g. running/terminal + no `action` + question-shaped), NEVER a workflow-name branch (INV-1). The actual Concierge invocation happens in the app layer (`post_message`), not inside this pure router.

### `backend/app/api/run_commands.py` (proposal → channel disposal)

**Analog:** self, `post_message` dispatch execution `:525-609`

**Existing dispatch execution seams** (run_commands.py:531-609):
```python
elif dispatch.channel == CHANNEL_GATE:
    await art_store.set_review_response(_gk, approved=..., action=..., instructions=...)   # :547-558 (incl. update_specs → KAN-101)
elif dispatch.channel == CHANNEL_STEERING:
    apply_turn_images(_live_ectx_for_run(run_id), ...)                                    # steering via apply_steering / ectx.steering_notes
elif dispatch.channel == CHANNEL_REVISION:
    child_run_id, _ = _mint_revision_row(rdb, user=..., parent_run_id=run_id, ...)        # :584
    task = asyncio.create_task(_drive_revision_to_queue(...))                             # :595
```
**What changes:** add a `CHANNEL_CONCIERGE` branch that invokes the Concierge capability, then disposes each `propose_*` intent through the SAME functions — `propose_gate_action → set_review_response`, `propose_steering_note → apply_steering` (chat_router.py:301), `propose_revision → _mint_revision_row + _drive_revision_to_queue`. NO new execution path. Consequential proposals are held behind a **confirm chip**: the app returns the proposal, waits for FE confirmation, then calls the seam. Concierge answers project back to the lane as a `chat_reply` `run_events` row (documented type). Reuse `run_events` — no new table (owner_id + workspace_id stamped by `ScopedStore`).

### Wave-2 tests

**`tests/unit/test_concierge_escalation.py`** — assert free-form running/terminal turn → `CHANNEL_CONCIERGE`; every routable turn (clarify/gate-action/revision/sticky-steering) still routes to its existing channel with zero model call (mirror the existing `route_chat_turn` router tests).
**proposal→channel unit test** — mock `set_review_response` / `apply_steering` / `_mint_revision_row`, assert each `propose_*` intent disposes through the matching seam exactly once.

---

## Wave 3 — revision stitching + FE + SC-001 proof + golden neutrality

### Revision-family stitching (D-02) — reuse, do NOT fork

**Analog:** `run_commands.py:577-609` (`CHANNEL_REVISION` → `_mint_revision_row` + `_drive_revision_to_queue`). Post-terminal free-form Concierge revision proposals ride this EXACT seam + `REVISION_BASE_MAP` (registry). Live stitching (child events back into the family transcript) rides the existing per-run queue + `run_events`. No new revision path.

### FE (small)

**`frontend/src/components/chat/RunChatLane.tsx`** — EXISTS (`:16` already renders "Suggested next steps" as quick-reply CHIPS; `:38` already imports `ChatTokenWidget`). What changes: add confirm-chip UX for consequential Concierge proposals + a "compact" affordance. Model the chips on the existing suggestion-chip render path.
**`frontend/src/components/chat/ChatTokenWidget.tsx`** — EXISTS (the P26 token / context-usage widget; already imported by RunChatLane). Token/context display is ALREADY here — extend only to surface the composed-context usage if the phase needs it. **No net-new FE token widget — do not create one.**

### SC-001 throwaway-manifest proof

**Analog:** `tests/agents/test_sc001_gate_flag.py:1-40` (the name-free discriminator precedent + offline-safe harness shape).
Build a throwaway custom `workflow.yaml` (minimal `chat:` data block + generic agent sequence) under a test fixture, compile it, and assert: (1) its runs route through `route_chat_turn` identically (free-form → `CHANNEL_CONCIERGE`, gate → `CHANNEL_GATE`) with NO code referencing the workflow name; (2) `registry.resolve("chat", "concierge")` returns the shared impl; (3) `grep` for the throwaway name in `agents/execution_engine/`, `app/api/chat_router.py`, and the Concierge impl returns **0** (the SC-001 grep gate). This is ROADMAP SC-4, the milestone core-value proof.

### INV-3 golden neutrality (extend, do NOT touch goldens)

**`test_chat_event_neutrality.py:60-89`** — `test_chat_events_absent_from_golden` asserts `{chat_message, chat_reply, stream_attached}` appear in NONE of the 5 golden streams (`prototype`, `od_prototype`, `od_ppt`, `prototype_revision`, `app_builder`). Extend the guarded set to include ANY new Concierge event type.
**`characterization/_normalize.py:101` `_VOLATILE_STRIP_KEYS`** — add any new `pipeline_complete` keys the concierge/compaction path introduces.
**`_DOCUMENTED_EVENT_TYPES`** (`test_phase3_cutover_verify.py:182`) — add any new Concierge event type or the forward-vocabulary guard rejects it.
Prove byte-identity: run the characterization suite with `SNAPSHOT_UPDATE` UNSET against the UNCHANGED goldens. Do NOT touch `test_chat_contract.py` (frozen `ChatRunner` golden — INV-12; the Concierge does NOT run through `ChatRunner`).

---

## Shared Patterns

### Owner-scoped reads (all Concierge READ tools + conversation provider)
**Source:** `agents/authz.py:314` `ScopedStore.read_events(run_id, after_seq)` (constructed `ScopedStore(owner_id, workspace_id, session=None)` at `:58`; default-deny filter `_scope_owner_ws` at `:119`). Cross-owner → nothing → 404. NEVER raw ORM.
**Apply to:** `context_provider:conversation`, every Concierge READ tool.

### Register + import-purity (both kernel-side capabilities)
**Source:** `uploaded_files.py:34-37` / `html_skeleton.py:16-19` purity docstrings — registry decorator + stdlib ONLY; no `app.*`, no `agents.execution_engine`.
**Apply to:** `compaction/chat_history.py`, `context_providers/conversation.py`.

### INV-13 model-call funnel
**Source:** `deep_agent_runner.py:347-356` is the ONLY allow-listed `create_deep_agent` site (`test_banned_patterns.py:13-26`).
**Apply to:** `chat:concierge` — run through `DeepAgentRunner`, never import `create_deep_agent`.

### Additive persistence (no new table)
**Source:** `run_commands.py:365-416` — chat turns append to `run_events` (`type="chat_message"`) idempotently via `ScopedStore.append_event_next_seq`, keyed `event_id=chat:{message_id}`. `chat_reply` is a documented projection type.
**Apply to:** Concierge answers + any persisted concierge message; owner_id + workspace_id stamped by `ScopedStore`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `chat:concierge` orchestrator PORT (if added) | port | — | The `chat` kind has no formal Protocol today (duck-typed precedent = `compaction:html_skeleton`). A1: prefer duck-typed (no `base.py` edit); if a typed port is wanted it is a one-method Protocol like the others — net-new but modeled on `base.py:75-83`. |

Everything else has an exact in-tree analog.

## Metadata

**Analog search scope:** `backend/agents/capabilities/{compaction,context_providers}`, `backend/agents/capabilities/registry.py`, `backend/agents/authz.py`, `backend/app/api/{chat_router,run_commands}.py`, `backend/app/agents/deep_agent_runner.py`, `backend/tests/agents/`, `backend/tests/unit/`, `frontend/src/components/chat/`.
**Files scanned:** 14 read at file:line + registry/test/FE greps.
**Pattern extraction date:** 2026-07-08

## PATTERN MAPPING COMPLETE
