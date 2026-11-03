"""WR-02 follow-up — machine-readable ``code`` on every ``agent_error`` event.

Verifies the full pipeline path that the new developer-diagnostic field travels:

    ScriptedFakeChatModel raises exception
    → DeepAgentRunner swallows non-throttle → yields {"type":"error","error":str(exc)}
    → engine._run_agent error arm calls _classify_agent_error(raw)
    → emits agent_error SSE event {"error": <sanitized>, "code": <category>}

Placement: ``integration/agents/`` — drives the real ``ExecutionEngine.execute()``
which opens a ``SessionLocal()`` to persist run events.  The offline scripted-model
harness (same as ``test_engine_runner_error_arm.py``) keeps this Bedrock-free and
deterministic.
"""

from __future__ import annotations

import uuid

import pytest

# Side-effect import: sets RUNS_ROOT to a temp dir + forces InMemory checkpointer
# before app.core.config loads.  Keep first (mirrors test_engine_runner_error_arm.py).
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedFakeChatModel,
    ScriptedNonTransientError,
    _ScriptedTurn,
    _RUNS_ROOT,
)

from agents.execution_engine.engine import _AGENT_ERROR_CODE_LABELS


# ── helpers ───────────────────────────────────────────────────────────────────


def _text_turn(tag: str) -> list[_ScriptedTurn]:
    return [_ScriptedTurn(texts=[f"completed on {tag}. "], usage=(5, 3))]


async def _drive_one_error(*, error_message: str) -> list[dict]:
    """Drive the engine for the user_stories pipeline with ONE failing agent
    (the first in the roster).  The failing agent raises
    ``ScriptedNonTransientError(error_message)``; all others complete normally.

    Returns the full ordered list of SSE events from ``ExecutionEngine.execute()``.
    """
    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = get_pipeline_agents("user_stories")
    assert specs, "user_stories roster is empty — harness misconfigured"
    ids = [s.id for s in specs]
    error_id = ids[0]  # only the first agent fails

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_compile = engine_mod.compile_for_run

    def _patched_create_runner(agent_id: str, ctx, **kw):
        if agent_id == error_id:
            ctx.model = ScriptedFakeChatModel(
                [], raise_exc=ScriptedNonTransientError(error_message)
            )
        else:
            ctx.model = ScriptedFakeChatModel(_text_turn(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    def _patched_compile(pipeline_type: str, _orig=_orig_compile):  # type: ignore[assignment]
        compiled = _orig(pipeline_type)
        compiled.planner = "skip"
        return compiled

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    engine_mod.compile_for_run = _patched_compile

    engine = ExecutionEngine()

    async def _noop_dual_write(*a, **k):  # type: ignore[return]
        return None

    engine._dual_write_artifact = _noop_dual_write  # type: ignore[assignment]

    run_id = str(uuid.uuid4())
    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=[],
            user_message="test error-code diagnostic",
            pipeline_run_id=run_id,
            pipeline_type="user_stories",
            session_id="wc02-code-test",
        ):
            events.append(ev)
    finally:
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile

    return events


def _agent_error_data(events: list[dict]) -> list[dict]:
    """Return the ``data`` dict of every ``agent_error`` event."""
    return [e["data"] for e in events if e.get("type") == "agent_error"]


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_error_event_always_carries_code_field() -> None:
    """Every ``agent_error`` event must include a ``"code"`` key — never absent.

    This is the baseline contract: regardless of what the provider said, the
    developer-diagnostic field is always present so callers can always read it.
    """
    events = await _drive_one_error(
        error_message="Invalid request (synthetic non-transient)"
    )
    errs = _agent_error_data(events)
    assert errs, "no agent_error events emitted — harness misconfigured"

    for data in errs:
        assert "code" in data, f"agent_error data is missing 'code' field: {data!r}"


@pytest.mark.asyncio
async def test_unrecognised_error_text_produces_unknown_code() -> None:
    """An error whose text matches no needle → ``code == 'UNKNOWN'``.

    ``ScriptedNonTransientError``'s default message ("Invalid request (synthetic
    non-transient)") contains none of the category needles, so it falls through
    ``_classify_agent_error`` to the catch-all ``"UNKNOWN"``.
    ``"UNKNOWN"`` is the signal for the developer to check the server WARNING log
    (``raw=…`` field) rather than inferring the cause from the UI.
    """
    events = await _drive_one_error(
        error_message="Invalid request (synthetic non-transient)"
    )
    errs = _agent_error_data(events)
    assert errs

    for data in errs:
        assert (
            data["code"] == "UNKNOWN"
        ), f"expected code='UNKNOWN' for unrecognised error, got {data['code']!r}"


@pytest.mark.asyncio
async def test_payload_too_large_error_produces_correct_code() -> None:
    """An error text containing the 'payload' needle → ``code == 'PAYLOAD_TOO_LARGE'``.

    Covers the Bedrock shape: ``ValidationException: The request payload is too
    large for model``.
    """
    events = await _drive_one_error(
        error_message="ValidationException: The request payload is too large for model"
    )
    errs = _agent_error_data(events)
    assert errs

    for data in errs:
        assert (
            data["code"] == "PAYLOAD_TOO_LARGE"
        ), f"expected PAYLOAD_TOO_LARGE, got {data['code']!r}"


@pytest.mark.asyncio
async def test_credential_error_text_produces_correct_code() -> None:
    """An error text containing 'access denied' → ``code == 'CREDENTIAL_ERROR'``.

    Covers the Bedrock shape where an expired/missing IAM credential surfaces as
    an ``AccessDeniedException``.
    """
    events = await _drive_one_error(
        error_message="AccessDeniedException: Access denied to resource"
    )
    errs = _agent_error_data(events)
    assert errs

    for data in errs:
        assert (
            data["code"] == "CREDENTIAL_ERROR"
        ), f"expected CREDENTIAL_ERROR, got {data['code']!r}"


@pytest.mark.asyncio
async def test_code_is_bounded_vocabulary_never_provider_text() -> None:
    """The ``code`` value is always one of the declared labels or ``'UNKNOWN'``.

    Guards against accidentally echoing raw provider text as the code (WR-02).
    The set of valid codes is sealed by ``_AGENT_ERROR_CODE_LABELS``; nothing
    outside it should ever appear on the wire.
    """
    allowed: frozenset[str] = frozenset(_AGENT_ERROR_CODE_LABELS) | {"UNKNOWN"}

    events = await _drive_one_error(
        error_message="Invalid request (synthetic non-transient)"
    )
    for data in _agent_error_data(events):
        code = data.get("code", "")
        assert (
            code in allowed
        ), f"agent_error code {code!r} is outside the allowed vocabulary {allowed}"


@pytest.mark.asyncio
async def test_user_message_and_code_are_independent() -> None:
    """The ``error`` (user-facing) and ``code`` (developer) fields are independent.

    A PAYLOAD_TOO_LARGE error produces a specific user message AND the matching
    code — verifying both tier 1 (user) and tier 2 (developer) are set correctly
    on the same event.
    """
    from agents.execution_engine.engine import _sanitize_agent_error

    raw = "ValidationException: The request payload is too large for model"
    events = await _drive_one_error(error_message=raw)
    errs = _agent_error_data(events)
    assert errs

    expected_user_msg = _sanitize_agent_error(raw)
    for data in errs:
        # User tier: sanitized, friendly sentence
        assert (
            data["error"] == expected_user_msg
        ), f"user-facing error mismatch: {data['error']!r} != {expected_user_msg!r}"
        # Developer tier: machine-readable code
        assert (
            data["code"] == "PAYLOAD_TOO_LARGE"
        ), f"developer code mismatch: {data['code']!r}"
