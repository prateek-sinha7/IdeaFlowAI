"""Offline tests for the shared cached-invoke helper (ISS-033, plan 43-04).

Proves OFFLINE (no Bedrock, no network):
  * the helper builds through the sanctioned ``build_model`` (INV-13) or uses an
    injected model instance;
  * it places the SAME Bedrock ``cache_control`` the ``_BedrockCachePointsMiddleware``
    injects — on a real ``ChatBedrockConverse`` subclass whose ``_agenerate`` is
    stubbed so nothing hits the network (the cache config is asserted; the live
    ``cache_read>0`` observation is the B.4 live check, deferred);
  * it returns ``(text, usage)`` with the usage populated, and routes the usage into an
    injected sink (token counting closed);
  * it degrades safely on a non-Bedrock provider (no ``cache_control`` leaked) and when
    ``BEDROCK_PROMPT_CACHE_ENABLED`` is off.

Also proves the four routed call-sites (SmartPlanner, ClarifyEngine, handoff
classifier + ComplianceAgent) delegate to ``cached_invoke`` and thread a usage sink.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents import cached_invoke as ci_mod
from app.agents.cached_invoke import cached_invoke


# ---------------------------------------------------------------------------
# Recording fakes
# ---------------------------------------------------------------------------


class _RecordingChatModel(BaseChatModel):
    """Minimal non-Bedrock chat model that records the messages + kwargs it receives
    and returns a canned AIMessage carrying ``usage_metadata`` (incl. the cache split)."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, *, usage_metadata: dict | None = None, text: str = "ok", **kw: Any) -> None:
        super().__init__(**kw)
        object.__setattr__(self, "recorded_messages", None)
        object.__setattr__(self, "recorded_kwargs", None)
        object.__setattr__(
            self,
            "_usage_metadata",
            usage_metadata
            if usage_metadata is not None
            else {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
        )
        object.__setattr__(self, "_text", text)

    @property
    def _llm_type(self) -> str:
        return "recording-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        object.__setattr__(self, "recorded_messages", list(messages))
        object.__setattr__(self, "recorded_kwargs", dict(kwargs))
        msg = AIMessage(content=self._text, usage_metadata=self._usage_metadata)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _make_recording_bedrock(usage_metadata: dict | None = None, text: str = "ok"):
    """A REAL ``ChatBedrockConverse`` subclass (so ``isinstance`` gates fire) whose
    generate is stubbed to record kwargs + return a canned response — no network.

    Built with ``model_construct`` (ISS-118): that is pydantic's own no-validation
    constructor, so ``ChatBedrockConverse.__init__`` — the seam that resolves
    credentials and builds the boto3 ``bedrock-runtime`` client — never runs, while the
    instance stays a genuine subclass for the ``isinstance`` gate in
    ``cached_invoke._bedrock_cache_control``. Nothing here reads the boto client
    (``_agenerate`` is overridden), so it is left unset rather than exempting these
    tests from the ISS-102 live-model guard."""
    from langchain_aws import ChatBedrockConverse

    class _RecordingBedrock(ChatBedrockConverse):
        model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            object.__setattr__(self, "recorded_messages", list(messages))
            object.__setattr__(self, "recorded_kwargs", dict(kwargs))
            meta = usage_metadata if usage_metadata is not None else {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "input_token_details": {"cache_read": 80, "cache_creation": 5},
            }
            msg = AIMessage(content=text, usage_metadata=meta)
            return ChatResult(generations=[ChatGeneration(message=msg)])

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    return _RecordingBedrock.model_construct(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",  # ``model`` is the field alias
        region_name="us-east-1",
        max_tokens=8,
    )


# ---------------------------------------------------------------------------
# Cache-point placement (config asserted offline; live cache_read = B.4-deferred)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bedrock_call_places_cache_control_on_stable_prefix():
    model = _make_recording_bedrock()
    text, usage = await cached_invoke(
        "the volatile per-call brief",
        system="STABLE SYSTEM PREFIX",
        model=model,
    )

    # The Bedrock cache_control is passed as a per-call kwarg → langchain_aws places
    # the cachePoint on the stable system prefix + the last message. Assert the
    # cache config is correctly placed (the live cache_read>0 is the B.4 check).
    assert model.recorded_kwargs.get("cache_control") == {"type": "ephemeral", "ttl": "5m"}

    # The stable prefix went first as a SystemMessage (the cache-eligible prefix).
    msgs = model.recorded_messages
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == "STABLE SYSTEM PREFIX"
    assert isinstance(msgs[-1], HumanMessage) and msgs[-1].content == "the volatile per-call brief"

    assert text == "ok"
    # Token counting: usage populated incl. the cache split (ISS-032 shape).
    assert usage == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 80,
        "cache_write_tokens": 5,
    }


@pytest.mark.asyncio
async def test_cache_control_suppressed_when_flag_off(monkeypatch):
    monkeypatch.setattr(ci_mod.settings, "BEDROCK_PROMPT_CACHE_ENABLED", False)
    model = _make_recording_bedrock()
    await cached_invoke("brief", system="SYS", model=model)
    assert "cache_control" not in (model.recorded_kwargs or {})


@pytest.mark.asyncio
async def test_non_bedrock_provider_gets_no_cache_control():
    """ChatAnthropic / scripted models never receive cache_control (would error / is
    handled by deepagents' own middleware). Degrade-safe: still invokes + counts."""
    model = _RecordingChatModel()
    text, usage = await cached_invoke("brief", system="SYS", model=model)
    assert "cache_control" not in (model.recorded_kwargs or {})
    assert text == "ok"
    assert usage["input_tokens"] == 11 and usage["output_tokens"] == 7
    # No cache split on a non-Bedrock turn.
    assert usage["cache_read_tokens"] == 0 and usage["cache_write_tokens"] == 0


# ---------------------------------------------------------------------------
# Token counting via the injected sink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_sink_receives_token_counts():
    model = _RecordingChatModel(usage_metadata={"input_tokens": 42, "output_tokens": 9, "total_tokens": 51})
    sunk: list[dict] = []
    text, usage = await cached_invoke("brief", model=model, usage_sink=sunk.append)
    assert len(sunk) == 1
    assert sunk[0] == usage == {
        "input_tokens": 42,
        "output_tokens": 9,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


@pytest.mark.asyncio
async def test_usage_sink_that_raises_never_breaks_the_call():
    model = _RecordingChatModel()

    def _boom(_u):
        raise RuntimeError("accounting blew up")

    # The model call still returns; the counting failure is swallowed + logged.
    text, usage = await cached_invoke("brief", model=model, usage_sink=_boom)
    assert text == "ok" and usage["input_tokens"] == 11


@pytest.mark.asyncio
async def test_missing_usage_metadata_degrades_to_zeros():
    model = _RecordingChatModel(usage_metadata=None)
    # ``usage_metadata=None`` on the AIMessage → all-zeros, no crash.
    object.__setattr__(model, "_usage_metadata", None)
    _text, usage = await cached_invoke("brief", model=model)
    assert usage == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


# ---------------------------------------------------------------------------
# INV-13: model=None routes through the sanctioned build_model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_none_builds_via_build_model(monkeypatch):
    built: list[dict] = []
    fake = _RecordingChatModel()

    def _fake_build_model(model=None, *, max_tokens=None):
        built.append({"model": model, "max_tokens": max_tokens})
        return fake

    monkeypatch.setattr(ci_mod, "build_model", _fake_build_model)
    text, _usage = await cached_invoke("brief", max_tokens=1500)
    assert built == [{"model": None, "max_tokens": 1500}]
    assert text == "ok"


def test_no_create_deep_agent_import():
    """INV-13: the helper never constructs a deep agent / hand-rolled loop."""
    import inspect

    src = inspect.getsource(ci_mod)
    assert "create_deep_agent" not in src
    assert "build_model" in src  # the sanctioned model path


# ---------------------------------------------------------------------------
# Call-site delegation (the four routed sites hand off to cached_invoke)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_planner_delegates_and_counts(monkeypatch):
    from agents.planner.smart_planner import SmartPlanner

    planner = SmartPlanner.__new__(SmartPlanner)  # skip _build_llm (no creds offline)
    planner.model_id = None
    planner._llm = _RecordingChatModel(text=json.dumps({"has_topic": True}))
    planner._usage_sink = None

    sunk: list[dict] = []
    planner._usage_sink = sunk.append

    ctx = await planner.plan("Build a task manager", "prototype")
    assert ctx["has_topic"] is True and ctx["pipeline_type"] == "prototype"
    # The planner's tokens were counted through the shared helper.
    assert len(sunk) == 1 and sunk[0]["input_tokens"] == 11


@pytest.mark.asyncio
async def test_classifier_delegates(monkeypatch):
    import app.agents.handoff.classifier as clf

    # build_model runs OUTSIDE the try (ModelConfigurationError propagation preserved);
    # it can't build a real provider offline, so stub it. cached_invoke is stubbed too,
    # so the stub model is only passed through, never invoked.
    sentinel_model = object()
    monkeypatch.setattr(clf, "build_model", lambda max_tokens=None: sentinel_model)

    captured: dict[str, Any] = {}

    async def _fake_cached_invoke(messages, *, system=None, model=None, max_tokens=None, usage_sink=None):
        captured["system"] = system
        captured["messages"] = messages
        captured["model"] = model
        if usage_sink is not None:
            usage_sink({"input_tokens": 3, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0})
        return "test", {"input_tokens": 3, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0}

    monkeypatch.setattr(clf, "cached_invoke", _fake_cached_invoke)
    sunk: list[dict] = []
    mode = await clf.classify_task("write missing unit tests", usage_sink=sunk.append)
    assert mode == "test"
    # Stable classifier prompt is the cache-eligible system prefix; the pre-built model
    # (build_model(max_tokens=8), built outside the try) is passed through.
    assert captured["system"] == clf._CLASSIFIER_SYSTEM_PROMPT
    assert captured["model"] is sentinel_model
    assert len(sunk) == 1


@pytest.mark.asyncio
async def test_compliance_agent_delegates(monkeypatch):
    import app.agents.handoff.compliance_agent as comp

    captured: dict[str, Any] = {}
    report = {"verdict": "approve", "summary": "ok", "findings": [], "positives": []}

    # build_model stays in compliance_agent (built outside, passed through); stub it
    # offline. cached_invoke is stubbed too, so the stub model is never invoked.
    sentinel_model = object()
    monkeypatch.setattr(comp, "build_model", lambda max_tokens=None: sentinel_model)

    async def _fake_cached_invoke(messages, *, system=None, model=None, max_tokens=None, usage_sink=None):
        captured["system"] = system
        captured["model"] = model
        if usage_sink is not None:
            usage_sink({"input_tokens": 5, "output_tokens": 2, "cache_read_tokens": 0, "cache_write_tokens": 0})
        return json.dumps(report), {"input_tokens": 5, "output_tokens": 2, "cache_read_tokens": 0, "cache_write_tokens": 0}

    monkeypatch.setattr(comp, "cached_invoke", _fake_cached_invoke)
    sunk: list[dict] = []
    agent = comp.ComplianceAgent(usage_sink=sunk.append)
    out = await agent.review("task", "tree", {"a.py": "code"})
    assert out["verdict"] == "approve"
    assert captured["system"] == agent.system_prompt
    assert captured["model"] is sentinel_model
    assert len(sunk) == 1


# ---------------------------------------------------------------------------
# ISS-120 — per-call override (caching is currently ONE process-wide switch)
# ---------------------------------------------------------------------------


@pytest.mark.issue("ISS-120")
@pytest.mark.asyncio
async def test_cached_invoke_supports_per_call_cache_override(monkeypatch):
    """ISS-120 — a short, single-turn call must be able to opt OUT of prompt
    caching without flipping the process-wide ``BEDROCK_PROMPT_CACHE_ENABLED``
    flag (which would affect every other concurrent call too). Today the ONLY
    gate is that global setting, read at call time in both
    ``_bedrock_cache_control`` and ``_BedrockCachePointsMiddleware`` — there is
    no per-call / per-step override anywhere (card ISS-120)."""
    monkeypatch.setattr(ci_mod.settings, "BEDROCK_PROMPT_CACHE_ENABLED", True)
    model = _make_recording_bedrock()

    # A caller declaring this turn single-turn/short should be able to suppress
    # the cache point on just THIS call, leaving the global flag (and every
    # other concurrent call) untouched.
    await cached_invoke("brief", system="SYS", model=model, enable_cache=False)

    assert "cache_control" not in (model.recorded_kwargs or {})
