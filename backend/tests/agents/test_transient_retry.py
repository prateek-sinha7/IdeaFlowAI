"""tests/agents/test_transient_retry.py — the mid-stream EventStreamError incident.

Covers two changes made together:

  * ``agents.model_policy._is_transient_throttle`` now classifies Bedrock's
    event-stream error frame (``botocore.exceptions.EventStreamError``,
    ``internalServerException`` — lower-camel, case-sensitive misses the old
    PascalCase whitelist) as transient, fails OPEN for the ``EventStreamError``
    family generally, and adds a PERMANENT fast path for genuinely-our-fault
    codes so the fail-open default can never swallow those.
  * ``app.agents.deep_agent_runner.DeepAgentRunner.astream_events`` now retries
    a transient throttle on the SAME model (bounded, full-jitter exponential
    backoff) when the failing attempt has yielded NOTHING downstream yet,
    before falling back to today's re-raise/swallow behavior.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from botocore.exceptions import EventStreamError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

import app.agents.deep_agent_runner as runner_module
from agents.model_policy import _is_transient_throttle
from app.agents.deep_agent_runner import DeepAgentRunner, _retry_delay_seconds

# ===========================================================================
# _is_transient_throttle — the classifier (Change 1)
# ===========================================================================


def _event_stream_error(code: str, message: str = "synthetic") -> EventStreamError:
    """A real ``botocore.exceptions.EventStreamError`` (not a duck-typed stand-in) —
    the classifier's ``isinstance(exc, EventStreamError)`` branch only exists for
    this exact exception type, so the test has to use the real class to exercise it."""
    return EventStreamError(
        {"Error": {"Code": code, "Message": message}}, "ConverseStream"
    )


class _FakeClientError(Exception):
    """Synthetic botocore-shaped ``ClientError`` (no botocore import needed for a
    regular, non-streaming code/status check — mirrors tests/unit/test_model_resolver.py)."""

    def __init__(self, code: str | None, status: int | None = None) -> None:
        super().__init__(code or "no-code")
        error: dict[str, Any] = {}
        if code is not None:
            error["Code"] = code
        response: dict[str, Any] = {"Error": error}
        if status is not None:
            response["ResponseMetadata"] = {"HTTPStatusCode": status}
        self.response = response


def test_incident_shape_is_transient() -> None:
    """The EXACT incident: an event-stream frame with the lower-camel
    ``internalServerException`` code and AWS's own "try your request again" text.

    Without Change 1 this is False: the pre-change ``_TRANSIENT_ERROR_CODES``
    frozenset holds the PascalCase ``"InternalServerException"`` and the old
    membership test was case-sensitive (``"internalServerException" in
    frozenset({"InternalServerException", ...})`` is ``False`` — different
    strings). The HTTP-status fallback can't save it either: botocore's
    event-stream parser never attaches a ``ResponseMetadata``/``HTTPStatusCode``
    to an ``EventStreamError``, and the old substring list had no "internal
    server" token. So the pre-change function returns ``False`` for this exact
    shape — this assertion is the regression guard for that.
    """
    exc = _event_stream_error(
        "internalServerException",
        "The system encountered an unexpected error during processing. "
        "Try your request again.",
    )
    assert _is_transient_throttle(exc) is True


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("ThrottlingException", 429),
        ("TooManyRequestsException", 429),
        ("ServiceUnavailableException", 503),
        ("InternalServerException", 500),
        ("ModelTimeoutException", 408),
        ("ServiceQuotaExceededException", 400),
    ],
)
def test_previously_transient_codes_stay_transient(code: str, status: int) -> None:
    assert _is_transient_throttle(_FakeClientError(code, status=status)) is True


@pytest.mark.parametrize("status", [429, 500, 503, 529])
def test_transient_http_status_alone_stays_transient(status: int) -> None:
    """No recognized code, only a transient HTTP status — the step-3 fallback."""
    assert (
        _is_transient_throttle(_FakeClientError("SomeUnmappedException", status=status))
        is True
    )


def test_anthropic_ratelimit_message_stays_transient() -> None:
    assert _is_transient_throttle(Exception("429 too many requests")) is True


def test_overloaded_message_stays_transient() -> None:
    assert _is_transient_throttle(Exception("Error: model is overloaded (529)")) is True


@pytest.mark.parametrize(
    "code",
    [
        "AccessDeniedException",
        "UnauthorizedException",
        "UnrecognizedClientException",
        "ExpiredTokenException",
        "InvalidSignatureException",
        "ValidationException",
        "ResourceNotFoundException",
    ],
)
def test_permanent_codes_are_not_transient(code: str) -> None:
    assert _is_transient_throttle(_FakeClientError(code, status=400)) is False


def test_generic_value_error_is_not_transient() -> None:
    assert _is_transient_throttle(ValueError("nope")) is False


def test_event_stream_error_with_permanent_code_is_not_transient() -> None:
    """The fail-open EventStreamError branch must not override the permanent
    fast path — a permanent code stays permanent even arriving via a stream."""
    exc = _event_stream_error("ValidationException", "bad request")
    assert _is_transient_throttle(exc) is False


def test_event_stream_error_with_unknown_code_fails_open() -> None:
    """An EventStreamError code this predicate has never seen before still comes
    back transient — the fail-OPEN default for the one exception family this
    predicate cannot enumerate exhaustively (any code not in the permanent set)."""
    exc = _event_stream_error("SomeFutureBedrockStreamFault", "never seen before")
    assert _is_transient_throttle(exc) is True


# ===========================================================================
# _retry_delay_seconds — full-jitter exponential backoff (Change 2)
# ===========================================================================


def test_retry_delay_stays_within_bounds() -> None:
    for attempt in range(6):
        ceiling = min(30.0, 2.0 * 2**attempt)
        for _ in range(20):
            delay = _retry_delay_seconds(attempt)
            assert 0 <= delay <= ceiling, (attempt, delay, ceiling)


def test_retry_delay_is_capped() -> None:
    # base * factor**attempt blows past the 30s cap well before attempt=10.
    for _ in range(20):
        delay = _retry_delay_seconds(10)
        assert 0 <= delay <= 30.0


def test_retry_delay_jitter_is_real() -> None:
    import random

    random.seed(1234)
    samples = {_retry_delay_seconds(3) for _ in range(30)}
    assert len(samples) > 1, "expected random jitter, got a constant delay"


# ===========================================================================
# DeepAgentRunner.astream_events — in-runner retry (Change 2)
# ===========================================================================


class _RaiseThenSucceedModel(BaseChatModel):
    """Raises ``exc`` on the first ``fail_count`` calls, then streams ``final_text``.

    Mirrors ``tests/agents/_scripted_model.py::ScriptedFakeChatModel``'s proven
    recipe (a minimal ``BaseChatModel`` whose ``_stream`` yields real
    ``AIMessageChunk``s) — the stock LangChain fakes do not drive the deepagents
    loop. Raising from ``_stream`` fires BEFORE any ``on_chat_model_stream``
    delta, so the runner's ``_astream_events_once`` yields NOTHING downstream
    for a failing call — exactly the "nothing yielded yet" case the retry is
    scoped to.
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self, exc: BaseException, fail_count: int, final_text: str, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_exc", exc)
        object.__setattr__(self, "_fail_count", fail_count)
        object.__setattr__(self, "_final_text", final_text)
        object.__setattr__(self, "_calls", 0)

    @property
    def _llm_type(self) -> str:
        return "raise-then-succeed-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_RaiseThenSucceedModel":
        return self

    def _stream(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        object.__setattr__(self, "_calls", self._calls + 1)
        if self._calls <= self._fail_count:
            raise self._exc
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=self._final_text,
                usage_metadata={
                    "input_tokens": 3,
                    "output_tokens": 2,
                    "total_tokens": 5,
                },
            )
        )

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Never exercised by astream_events (v2 always streams), but BaseChatModel
        # requires a concrete implementation.
        object.__setattr__(self, "_calls", self._calls + 1)
        if self._calls <= self._fail_count:
            raise self._exc
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self._final_text))]
        )


def _make_runner(model: BaseChatModel, thread: str) -> DeepAgentRunner:
    return DeepAgentRunner(
        system_prompt="You are a text agent. Say hello.",
        tools=[],
        model=model,
        exclude_builtin_tools=True,
        thread_id=thread,
    )


@pytest.mark.asyncio
async def test_runner_retries_transient_failure_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "sleep", _fake_sleep)

    exc = _event_stream_error(
        "internalServerException",
        "The system encountered an unexpected error during processing. Try your request again.",
    )
    model = _RaiseThenSucceedModel(exc, fail_count=1, final_text="hello there")
    runner = _make_runner(model, "retry-success")

    events = [ev async for ev in runner.astream_events("hi")]

    done = [e for e in events if e.get("type") == "done"]
    assert (
        done
    ), f"expected a terminal done event, got: {[e.get('type') for e in events]}"
    assert "hello there" in done[-1]["output"]
    assert not [e for e in events if e.get("type") == "error"]
    # Exactly one retry: the model was called twice (fail once, succeed once).
    assert model._calls == 2
    # The retry actually slept (through the patched asyncio.sleep) exactly once.
    assert len(sleeps) == 1
    assert 0 <= sleeps[0] <= 2.0  # _retry_delay_seconds(0) ceiling = min(30, 2*2**0)


@pytest.mark.asyncio
async def test_runner_does_not_retry_permanent_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "sleep", _fake_sleep)

    exc = _event_stream_error("ValidationException", "bad request")
    model = _RaiseThenSucceedModel(exc, fail_count=99, final_text="never reached")
    runner = _make_runner(model, "retry-permanent")

    events = [ev async for ev in runner.astream_events("hi")]

    errors = [e for e in events if e.get("type") == "error"]
    assert (
        errors
    ), f"expected a swallowed error event, got: {[e.get('type') for e in events]}"
    assert not [e for e in events if e.get("type") == "done"]
    # No retry at all: the model was called exactly once, no sleep happened.
    assert model._calls == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_runner_exhausts_retries_then_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SUSTAINED transient throttle (every attempt fails) exhausts the bounded
    retry budget and re-raises — preserving today's behavior so the engine's own
    model-fallback chain still gets its turn."""

    async def _fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(runner_module.asyncio, "sleep", _fake_sleep)

    exc = _event_stream_error("internalServerException", "try again")
    model = _RaiseThenSucceedModel(exc, fail_count=99, final_text="never reached")
    runner = _make_runner(model, "retry-exhausted")

    with pytest.raises(EventStreamError):
        [ev async for ev in runner.astream_events("hi")]

    # 1 initial + 2 retries = 3 total attempts, bounded.
    assert model._calls == 3
