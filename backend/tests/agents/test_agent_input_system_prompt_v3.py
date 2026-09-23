"""tests/agents/test_agent_input_system_prompt_v3.py — FR-044 system_prompt in agent_input event.

Verifies that the agent_input SSE event carries the full composed system_prompt
and the context_message, exactly as the factory assembled them.

AC:
  * The emitted agent_input event's "system_prompt" field is EQUAL to the string
    ``agents.factory._compose_system_prompt`` (``policy.assemble`` output) actually
    produced for this call — captured via a spy that delegates to the real
    function, not recomputed independently.
  * The "context_message" field is EQUAL to the exact wrapped envelope
    ``_compose_context_message`` builds for the FIRST agent of a run:
    ``=== ORIGINAL USER REQUEST ===\\n{task_message}\\n=== END REQUEST ===``.
    NOTE ("equal to the task message" reconciliation): the row's literal wording
    is unreachable for any first agent — ``_compose_context_message`` unconditionally
    wraps the brief in this envelope (``engine.py`` ~13538) whenever
    ``is_first_agent`` is True, regardless of ``prompt_policy``. domain-analyst
    (used here) is on ``prompt_policy: governance`` (already "migrated" — see
    GAPS §0 Step 0), which additionally gates OFF every world block (planning
    context, OD blocks, consumed-outputs paste) that could otherwise follow the
    envelope, so the composed message for THIS agent is exactly the envelope
    and nothing else — the strongest equality achievable, verified by reading
    ``_compose_context_message`` end to end (see "## fix attempt 1" in
    ``journal/S7.md`` for the full trace).
  * Both fields are present end-to-end from composition through the event stream.

Offline-safe: scripted model only (no Bedrock / Postgres / Chromium).
"""

from __future__ import annotations

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads.  Keep this import first.
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedFakeChatModel,
    _ScriptedTurn,
)
from tests.unit.agents.test_redo_gate_safety import (  # noqa: E402
    _EngineHarness,
    _drive_agent,
    _make_ectx,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn(text: str) -> list[_ScriptedTurn]:
    return [_ScriptedTurn(texts=[text], usage=(5, 3))]


def _expected_first_agent_context_message(task_message: str) -> str:
    """The exact envelope ``_compose_context_message`` builds for the first agent
    of a run (``engine.py`` ~13538): ``is_first_agent`` unconditionally selects
    this branch, independent of ``prompt_policy``/migration state.
    """
    return (
        "=== ORIGINAL USER REQUEST ===\n"
        f"{task_message}\n"
        "=== END REQUEST ==="
    )


def _collect_agent_input_events(events: list[dict]) -> list[dict]:
    """Extract agent_input event dicts from a stream of events."""
    return [
        ev["data"]
        for ev in events
        if ev.get("type") == "agent_input"
        and "context_message" in ev.get("data", {})
    ]


class _FakeSandbox:
    """Minimal in-memory sandbox with run_id property."""

    def __init__(self, run_id: str = "test-run") -> None:
        self.run_id = run_id
        self._files: dict[str, str] = {}

    def read(self, name: str) -> str | None:
        return self._files.get(name)

    def write(self, name: str, text: str) -> None:
        self._files[name] = text

    @property
    def root(self) -> str:
        return "/tmp/fake-sandbox"


async def _drive_agent_with_sandbox(
    engine, spec, ectx, results, ordered, sandbox, index=0, task_message=None
):
    """Drive a single agent with an explicit sandbox and task message."""
    if task_message is None:
        task_message = "Build me a thing for managing tasks."

    events: list[dict] = []
    async for ev in engine._run_agent(
        spec,
        index,
        ordered,
        task_message,
        sandbox,
        ectx.run_id,
        "user_stories",
        engine._default_planning_context(task_message),
        None,
        None,
        "test-model-id",
        results,
        None,
        ectx,
    ):
        events.append(ev)
    return events


# ---------------------------------------------------------------------------
# FR-044 test — system_prompt and context_message in agent_input event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_input_carries_system_prompt_and_context_message() -> None:
    """[FR-044] The agent_input SSE event carries both system_prompt (the factory's
    composed result) and context_message (the task message sent to the agent).
    """
    import agents.factory as factory_mod
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")
    task_message = "Build me a detailed task."
    run_id = "system-prompt-run"

    # Spy on the factory's own composer: delegates to the real function and
    # records what it returned, so the assertion below compares the emitted
    # event against the ACTUAL policy.assemble output for this call — never a
    # value recomputed independently in the test.
    _orig_compose_system_prompt = factory_mod._compose_system_prompt
    composed_system_prompts: list[str] = []

    def _spy_compose_system_prompt(*args, **kwargs):
        result = _orig_compose_system_prompt(*args, **kwargs)
        composed_system_prompts.append(result)
        return result

    factory_mod._compose_system_prompt = _spy_compose_system_prompt
    try:
        with _EngineHarness(
            lambda aid, idx: ScriptedFakeChatModel(_turn("output text"))
        ) as h:
            ectx = _make_ectx(run_id)
            ectx.gate_agent_ids = []

            # Create a fake sandbox so the engine can access sandbox.run_id
            sandbox = _FakeSandbox(run_id=run_id)

            results: list[dict] = []
            events = await _drive_agent_with_sandbox(
                h.engine, spec, ectx, results, [spec], sandbox, index=0,
                task_message=task_message,
            )
    finally:
        factory_mod._compose_system_prompt = _orig_compose_system_prompt

    # Collect the agent_input event data blocks
    agent_inputs = _collect_agent_input_events(events)
    assert agent_inputs, "no agent_input events in the stream"

    # There should be exactly one agent_input event (one agent, one pass)
    assert len(agent_inputs) == 1, (
        f"expected 1 agent_input event, got {len(agent_inputs)}"
    )
    assert len(composed_system_prompts) == 1, (
        f"expected exactly 1 _compose_system_prompt call, got {len(composed_system_prompts)}"
    )

    agent_input = agent_inputs[0]

    # (1) system_prompt must be present and EQUAL to the factory's own composed
    # string (policy.assemble output) for this call.
    assert "system_prompt" in agent_input, (
        "agent_input event missing 'system_prompt' field"
    )
    system_prompt = agent_input["system_prompt"]
    assert system_prompt == composed_system_prompts[0], (
        "emitted system_prompt does not equal the factory's composed string "
        "(policy.assemble output) — the yield-then-mutate wiring at "
        "engine.py's create_runner call site dropped or altered it"
    )

    # (2) context_message must be EQUAL to the exact envelope
    # _compose_context_message builds for the first agent of a run.
    assert "context_message" in agent_input, (
        "agent_input event missing 'context_message' field"
    )
    context_message = agent_input["context_message"]
    expected_context_message = _expected_first_agent_context_message(task_message)
    assert context_message == expected_context_message, (
        f"context_message does not equal the expected first-agent envelope.\n"
        f"expected:\n{expected_context_message!r}\n"
        f"actual:\n{context_message!r}"
    )

    # (3) sanity: not a trivial/empty string.
    assert len(system_prompt) > 100, (
        f"system_prompt seems incomplete ({len(system_prompt)} chars): {system_prompt[:200]}"
    )


@pytest.mark.asyncio
async def test_agent_input_system_prompt_present_at_yield_time() -> None:
    """[C-msg / GAPS L1] system_prompt must be on the agent_input event's data
    dict AT THE MOMENT it is yielded, not only after ``_run_agent`` has fully
    run to completion.

    ``execute()``'s stamping boundary (``sink.persist`` + ``RunTrace.observe``,
    ``engine.py`` ~3494-3522) serializes each event SYNCHRONOUSLY, in the same
    loop iteration it receives it in — before ``_run_agent`` is ever resumed to
    run any further code. A prior version of ``_run_agent`` yielded the
    agent_input event BEFORE calling ``create_runner()`` and only mutated
    ``system_prompt`` onto the (already-yielded) dict afterward; that mutation
    could never reach a consumer snapshotting at the yield boundary, so the
    persisted ``.logs/{run_id}.jsonl`` trace and DB row never carried
    ``system_prompt`` for ANY agent (confirmed empirically: grep for
    ``system_prompt`` across a real run's trace file returned 0 hits).
    ``test_agent_input_carries_system_prompt_and_context_message`` above does
    not catch this — it inspects the dict only after the whole generator has
    been drained, by which point the (formerly post-yield) mutation has long
    since happened. This test snapshots a COPY of the data dict on the SAME
    loop iteration it is yielded, mirroring what the real persistence boundary
    does.
    """
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")
    task_message = "Build me a detailed task."
    run_id = "system-prompt-yield-time-run"

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output text"))
    ) as h:
        ectx = _make_ectx(run_id)
        ectx.gate_agent_ids = []
        sandbox = _FakeSandbox(run_id=run_id)
        results: list[dict] = []

        snapshots_at_yield: list[dict] = []
        async for ev in h.engine._run_agent(
            spec, 0, [spec], task_message, sandbox, ectx.run_id,
            "user_stories", h.engine._default_planning_context(task_message),
            None, None, "test-model-id", results, None, ectx,
        ):
            # Snapshot immediately — the same instant a real consumer
            # (sink.persist / RunTrace.observe) would serialize it — BEFORE
            # looping back to let the generator run any further code.
            if ev.get("type") == "agent_input":
                snapshots_at_yield.append(dict(ev.get("data") or {}))

    assert len(snapshots_at_yield) == 1, (
        f"expected 1 agent_input event, got {len(snapshots_at_yield)}"
    )
    snapshot = snapshots_at_yield[0]
    assert "system_prompt" in snapshot, (
        "agent_input event's data dict did not carry 'system_prompt' AT YIELD "
        "TIME — a consumer that persists/traces synchronously at the yield "
        "boundary (as execute() does) will never see it (C-msg failure)"
    )
    assert len(snapshot["system_prompt"]) > 100


@pytest.mark.asyncio
async def test_agent_input_context_message_matches_task() -> None:
    """[FR-044] The context_message in agent_input is the exact task message
    passed to the engine (the first agent receives the brief, no context injection).
    """
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")
    task_message = "Design a microservices architecture for a real-time analytics platform."
    run_id = "context-message-run"

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("detailed output"))
    ) as h:
        ectx = _make_ectx(run_id)
        ectx.gate_agent_ids = []

        sandbox = _FakeSandbox(run_id=run_id)

        results: list[dict] = []
        events = await _drive_agent_with_sandbox(
            h.engine, spec, ectx, results, [spec], sandbox, index=0,
            task_message=task_message,
        )

    agent_inputs = _collect_agent_input_events(events)
    assert len(agent_inputs) == 1, "expected 1 agent_input event"

    agent_input = agent_inputs[0]
    context_message = agent_input.get("context_message", "")

    # For the first agent (index 0), the context message is EQUAL to the exact
    # === ORIGINAL USER REQUEST === envelope wrapping the task message (see
    # module docstring for why literal equality to the bare task message is
    # unreachable, and why the envelope is the strongest achievable equality).
    expected_context_message = _expected_first_agent_context_message(task_message)
    assert context_message == expected_context_message, (
        f"context_message does not equal the expected first-agent envelope.\n"
        f"expected:\n{expected_context_message!r}\n"
        f"actual:\n{context_message!r}"
    )
