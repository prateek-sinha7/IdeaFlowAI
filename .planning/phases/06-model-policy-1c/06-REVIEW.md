---
phase: 06-model-policy-1c
reviewed: 2026-06-08T12:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - backend/agents/capabilities/model_catalog.py
  - backend/agents/capabilities/registry.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/loader.py
  - backend/agents/model_policy.py
  - backend/app/agents/deep_agent_runner.py
  - backend/app/api/settings.py
  - backend/app/api/websocket.py
  - backend/tests/agents/_scripted_model.py
  - backend/tests/agents/test_loader.py
  - backend/tests/agents/test_model_catalog.py
  - backend/tests/agents/test_model_fallback.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/unit/test_model_resolver.py
  - backend/tests/unit/test_run_capabilities.py
  - backend/tests/unit/test_run_pipeline_validation.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 6: Code Review Report — Model Policy [1C]

**Reviewed:** 2026-06-08T12:00:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 6 introduces `ModelResolver` (5-tier precedence), the APPROACH-B engine-level fallback loop, per-run `model_overrides` ingress validation at the WebSocket layer, and `ModelCatalog` as the single source of model metadata. The resolver precedence logic, chain derivation, exhaustion handling, and INV-3 parity path are all correct. The `settings.py` projections are genuine derived views of the catalog — INV-12 holds. The `record_capabilities` persistence and the `{} → NULL` parity rule are correctly wired.

Two **critical** correctness/security findings were identified:

1. **Silent task death from non-dict `model_overrides`** — a malformed WS payload (string or list as `model_overrides`) bypasses the `or {}` guard, raises `AttributeError` inside `_validate_model_overrides` before the event queue is even created, kills the asyncio task silently, and leaves the client with no feedback and a leaked `_PIPELINE_TASKS` entry.
2. **Thread-id collision on mid-stream fallback** — the APPROACH-B retry rebuilds the runner with the SAME LangGraph `thread_id`; if the first attempt was checkpointed (mid-stream throttle), the fallback runner resumes from the prior model's checkpoint state rather than restarting cleanly, potentially producing a mixed-model graph execution.

Three **warnings** round out the findings, covering: a precedence-inversion where tier-3 `AgentSpec.model` catalog validation fires before the tier-1 override can win; HTTP 500 being over-classified as transient (allowing model switches on configuration errors); and an undocumented, observable mid-stream duplicate-chunk hazard in the APPROACH-B path.

---

## Critical Issues

### CR-01: Non-dict `model_overrides` silently kills the asyncio task with no client error event

**File:** `backend/app/api/websocket.py:479` and `backend/app/api/websocket.py:1116-1133`

**Issue:** `model_overrides = message_data.get("model_overrides") or {}` (line 479) only replaces *falsy* values with `{}`. A truthy non-dict value — `"evil_string"`, `["list"]` — passes through unchanged. The second normalisation in `_handle_workflow_execution` (line 1123: `model_overrides = model_overrides or {}`) has the same gap.

`_validate_model_overrides` is then called with the non-dict and immediately crashes on `model_overrides.items()` with `AttributeError` (string) or the same for a list. Crucially this call is at line 1124, **before** the `event_queue` is created (line 1206) and **before** `_run_pipeline_to_queue` starts. The exception propagates out of `_handle_workflow_execution` and kills the asyncio task created at line 498. The task is now `done()` (with a stored exception) but:

- No `error` event is ever put into `event_queue` (it was never created).
- The drainer loop never runs (we never reached it).
- The client receives **zero feedback** — the pipeline request vanishes silently.
- `_PIPELINE_TASKS` retains the now-dead task entry (cleaned up only inside `_run_pipeline_to_queue`'s `finally`, which never ran).

Similarly, a valid dict with a non-hashable value (`{"agent": ["list"]}`) causes `TypeError` in the `not in allowed_model_ids` set membership check — same silent-death path.

**Fix:**

```python
# In _validate_model_overrides, add an explicit type guard at the top:
def _validate_model_overrides(
    model_overrides: dict, run_agent_ids: set[str]
) -> str | None:
    if not model_overrides:
        return None
    if not isinstance(model_overrides, dict):
        return (
            f"model_overrides must be a dict (got {type(model_overrides).__name__!r})"
        )
    from agents.capabilities.model_catalog import ModelCatalog
    allowed_model_ids = set(ModelCatalog().ids())
    for agent_id, model_id in model_overrides.items():
        if not isinstance(agent_id, str):
            return f"model_overrides keys must be strings (got {type(agent_id).__name__!r})"
        if not isinstance(model_id, str):
            return f"model_overrides[{agent_id!r}] value must be a string (got {type(model_id).__name__!r})"
        if agent_id not in run_agent_ids:
            return (
                f"model_overrides targets agent {agent_id!r}, which is not part "
                f"of this run's agents"
            )
        if model_id not in allowed_model_ids:
            return (
                f"model_overrides for agent {agent_id!r} requests model "
                f"{model_id!r}, which is not an allowed model"
            )
    return None
```

These type guards turn all malformed-payload cases into a proper `str` return, which the caller converts into the documented `invalid_model_override` error event before any WorkflowRun is created.

---

### CR-02: Thread-id collision on APPROACH-B fallback rebuild — LangGraph resumes from prior checkpoint rather than restarting cleanly

**File:** `backend/agents/execution_engine/engine.py:1830-1835`

**Issue:** The fallback retry (lines 1830-1835) rebuilds the runner with the identical `thread_id`:

```python
agent = create_runner(
    spec.id,
    ctx,
    thread_id=thread_id,   # same id as the throttled run
    checkpointer=ectx.checkpointer,
)
```

`thread_id` is computed once before the retry loop (lines 1656-1661) and never changed. When the LangGraph checkpointer is active (the live path — `ectx.checkpointer` is always set by `execute()`), any checkpoint state written during the *failed* first attempt (messages, partial tool calls, mid-stream graph nodes) is still present under that thread. The fallback `astream_events` call therefore **resumes** from that checkpoint with the new (fallback) model rather than starting cleanly from the original `context_message`. This produces a mixed-model graph execution and may replay events (re-emit old `on_chat_model_stream` chunks) or skip prompt context from the retry.

The docstring's "Pitfall 4" comment acknowledges that a mid-stream throttle "cannot un-emit" the already-streamed tokens, but does not address the checkpoint state collision that would cause the retry to *continue* rather than *restart*.

**Fix:** Generate a fresh `thread_id` for each retry attempt to avoid reusing checkpointed state:

```python
# Inside the except block, after advancing the resolver, before create_runner:
_attempt_suffix = f":retry{_attempt}"
thread_id_retry = thread_id + _attempt_suffix
agent = create_runner(
    spec.id,
    ctx,
    thread_id=thread_id_retry,
    checkpointer=ectx.checkpointer,
)
```

This ensures each attempt starts with a clean graph state. The original `thread_id` variable used for the first attempt does not need to change (it remains the canonical conversation id for that invocation slot).

---

## Warnings

### WR-01: Tier-3 `AgentSpec.model` catalog validation fires before the tier-1 override is checked — invalid AGENT.md model blocks runs even when a valid override exists

**File:** `backend/agents/model_policy.py:87-103`

**Issue:** The catalog validation for `AgentSpec.model` (tier 3) runs unconditionally at the top of `resolve()`, before the `or`-chain that applies the actual precedence:

```python
agent_model = getattr(spec, "model", None)
if agent_model is not None and not self._catalog.is_allowed(agent_model):
    raise ValueError(...)   # fires here

resolved = (
    self._overrides.get(...)   # tier 1 — never reached if above raised
    or ...
    or agent_model             # tier 3
    ...
)
```

If an `AGENT.md` is authored with an invalid (retired or mistyped) model id, `resolve()` raises `ValueError` for **every invocation of that agent**, even when `model_overrides={"agent-x": VALID_ID}` is provided (which would have made tier 1 win and tier 3 irrelevant). The override cannot rescue the agent.

This is latent today (no existing `AGENT.md` declares a `model` field), but the pattern will surface the first time any `AGENT.md` gets a `model:` entry that later becomes invalid (e.g. a model retirement).

**Fix:** Move the catalog validation to inside the `or`-chain so it fires only when tier 3 is actually selected:

```python
def resolve(self, spec, step=None) -> str:
    agent_model = getattr(spec, "model", None)

    resolved = (
        self._overrides.get(getattr(spec, "id", None))
        or (step.model.model if step is not None and step.model else None)
        or agent_model   # only used if tiers 1 and 2 are None
        or (self._workflow_model.model if self._workflow_model else None)
        or self._session_model_id
        or self._haiku_default
    )
    # Validate only if tier 3 actually won (agent_model is what was selected).
    if resolved == agent_model and agent_model is not None:
        if not self._catalog.is_allowed(agent_model):
            raise ValueError(
                f"AGENT.md model {agent_model!r} for agent "
                f"{getattr(spec, 'id', '?')!r} is not a known, allowed catalog model"
            )
    return resolved
```

---

### WR-02: HTTP 500 status alone (without a matching error code) is classified as a transient throttle, enabling model switches on configuration errors

**File:** `backend/agents/model_policy.py:225-227`

**Issue:** In `_is_transient_throttle`, the botocore-shaped `ClientError` branch returns `True` for any `ResponseMetadata.HTTPStatusCode` in `_TRANSIENT_STATUS` (which includes 500), independent of the `Error.Code`:

```python
status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
if isinstance(status, int) and status in _TRANSIENT_STATUS:
    return True
```

The code check (lines 222-224) is guarded by a separate `if isinstance(code, str) and code in _TRANSIENT_ERROR_CODES: return True` earlier in the same block. If the `Error.Code` is something like `"ModelConfigurationError"` (not in `_TRANSIENT_ERROR_CODES`) but the HTTP status is 500, the predicate still returns `True`. This can classify a Bedrock configuration error (wrong model ID for region, invalid inference profile) as a transient throttle, causing the engine to switch models rather than surfacing the error.

**Fix:** Tighten the status-only branch by requiring the code to be absent or unknown (not a known non-transient code), or simply gate the status check on the code already having matched:

```python
# In the botocore response block:
code = response.get("Error", {}).get("Code")
if isinstance(code, str):
    if code in _TRANSIENT_ERROR_CODES:
        return True
    # Only fall through to status check if the code is unknown
    # (not a known non-transient code like ValidationException / AccessDeniedException)
    _NON_TRANSIENT_CODES = frozenset({"ValidationException", "AccessDeniedException",
                                       "ModelConfigurationError", "ResourceNotFoundException"})
    if code in _NON_TRANSIENT_CODES:
        return False
# Status-only fallback (no code, or unknown code)
status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
if isinstance(status, int) and status in _TRANSIENT_STATUS:
    return True
```

---

### WR-03: Mid-stream APPROACH-B retry emits duplicate `agent_chunk` events to the WebSocket client without documentation or client-side handling

**File:** `backend/agents/execution_engine/engine.py:1740-1845`

**Issue:** When a throttle occurs after tokens have already been streamed, the engine resets the `output_chunks` accumulator (correct — the final deliverable reflects only the successful attempt) but the `agent_chunk` events **already yielded** to the WebSocket drainer cannot be un-sent. The client therefore receives:

```
[agent_chunk events from attempt 1] → [agent_model_fallback] → [agent_chunk events from attempt 2]
```

The final agent output will be correct (from attempt 2 only), but the client's live streaming display will show the attempt-1 chunks in the output panel during the run. Depending on the frontend implementation this may manifest as doubled text in the streaming view.

The Pitfall 4 comment in the code acknowledges that "the retried attempt RE-STREAMS from scratch" and "the final deliverable reflects the successful attempt", but does not mention the duplicate-chunk hazard or note that frontend consumers should reset their chunk buffer on an `agent_model_fallback` event.

**Fix:** Document on the `agent_model_fallback` event that it signals a reset boundary, and add a `reset_output: true` field to the event payload so the frontend knows to discard previous chunks for this agent:

```python
yield {
    "type": "agent_model_fallback",
    "data": {
        "agent_id": spec.id,
        "pipeline_run_id": pipeline_run_id,
        "fallback_model": _next_id,
        "attempt": _attempt + 1,
        "reset_output": True,   # client should discard prior agent_chunk events
        "timestamp": _now(),
    },
}
```

---

## Info

### IN-01: `_attempt >= _max_attempts` bound check in the retry loop is always redundant

**File:** `backend/agents/execution_engine/engine.py:1812`

**Issue:** The retry-exhaustion condition at line 1812 is:
```python
if _next_id is None or _attempt >= _max_attempts:
```

`_next_id is None` is already sufficient for exhaustion: `resolver.advance()` returns `None` when the cursor passes the end of `_chain` (line 162: `return self.current()` which returns `None` when `_cursor >= len(_chain)`). Since `_max_attempts = len(_chain)` and the cursor starts at 0, `advance()` returns `None` exactly when `_attempt == _max_attempts`. The secondary condition `_attempt >= _max_attempts` is therefore never `True` when `_next_id is not None`, and never `False` when `_next_id is None`. It is dead code that adds noise to the bound reasoning without providing a safety net.

This is harmless today and not worth a code change during a release cycle, but worth a follow-up cleanup.

**Fix:** Remove or annotate the redundant check:
```python
if _next_id is None:  # chain exhausted — no further fallback available
    ...
    raise
```

---

_Reviewed: 2026-06-08T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
