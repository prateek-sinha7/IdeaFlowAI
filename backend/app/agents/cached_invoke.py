"""app/agents/cached_invoke.py — the ONE shared cached model-invoke helper (ISS-033).

Several direct one-shot model calls — SmartPlanner (``smart_planner.py``),
ClarifyEngine (``clarify_engine.py``), and the handoff Test/Compliance agents
(``handoff/classifier.py`` + ``handoff/compliance_agent.py``) — historically called
``build_model().ainvoke(...)`` (or ``self._llm.ainvoke(...)``) DIRECTLY. That had two
costs:

  1. **No Bedrock prompt-caching.** The P26 cache-point mechanism lives only in the
     ``DeepAgentRunner`` middleware path (``_BedrockCachePointsMiddleware``); a direct
     ``ainvoke`` never places a ``cachePoint``, so every call re-sends its fixed
     system/context prefix UNCACHED.
  2. **Uncounted tokens.** The direct calls dropped their ``usage_metadata`` on the
     floor, so their spend never reached the run's usage accounting (ISS-033/034).

This helper is the SINGLE cached-invoke path for those calls. It:

  * builds the model via the sanctioned :func:`app.agents.model_factory.build_model`
    (**INV-13** — no deep-agent factory call, no hand-rolled agent loop), OR uses an
    already-built model instance (the scripted-model test-injection path, mirroring
    :class:`app.agents.deep_agent_runner.DeepAgentRunner`);
  * places the SAME Bedrock ``cache_control`` the ``_BedrockCachePointsMiddleware``
    injects, so a stable system/context prefix is cache-eligible (**INV-12** — this is
    the direct-``ainvoke`` equivalent of the middleware, NOT a parallel caching scheme:
    ``langchain_aws`` reads ``cache_control`` off the per-call kwargs — see
    ``ChatBedrockConverse._generate``/``_stream``: ``filtered_kwargs.pop("cache_control")``
    → ``_apply_cache_points`` places a ``cachePoint`` on the system prefix + last
    message);
  * invokes the model and RETURNS ``(text, usage)`` and routes the ``usage`` into the
    caller's run accounting via an optional sink, so the tokens are COUNTED.

Degrade-safe throughout: caching off / a non-Bedrock provider / a missing
``usage_metadata`` never raises — the call still runs and still counts. This is a thin
invoke helper, NOT an agent: no summarizer, no tools, no graph.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agents.model_factory import build_model
from app.core.config import settings

logger = logging.getLogger("app.agents.cached_invoke")

#: Usage counts surfaced by one invoke. ``input_tokens`` is the TOTAL input (incl.
#: cache), matching the runner's ``usage`` event; the cache split rides alongside so a
#: cost site can price the uncached portion (ISS-032 parity).
Usage = dict


#: A caller-supplied sink that receives each call's :data:`Usage` so the tokens land in
#: the run's usage accounting. Must never raise (the helper guards it defensively).
UsageSink = Callable[[Usage], None]


def _bedrock_cache_control(model: Any) -> dict[str, Any] | None:
    """Return the Bedrock prompt-cache ``cache_control`` for ``model``, or ``None``.

    Identical gating + payload to
    :class:`app.agents.deep_agent_runner._BedrockCachePointsMiddleware` (INV-12: ONE
    mechanism). Bedrock-only and ``settings.BEDROCK_PROMPT_CACHE_ENABLED``-gated (read
    at CALL time so tests can monkeypatch the flag). Returns ``None`` — a no-op — on
    ChatAnthropic / a scripted-fake model (they never see ``cache_control``, so
    ChatAnthropic keeps deepagents' own built-in caching with no double-apply).
    """
    # Read the flag at call time (monkeypatch-friendly), mirroring the middleware.
    if not settings.BEDROCK_PROMPT_CACHE_ENABLED:
        return None
    # langchain_aws is heavy — keep the import lazy (matches build_model / the
    # middleware). Absent library ⇒ never a Bedrock model ⇒ no-op.
    try:
        from langchain_aws import ChatBedrockConverse
    except Exception:  # pragma: no cover — defensive; langchain_aws is a hard dep
        return None
    if not isinstance(model, ChatBedrockConverse):
        return None
    return {"type": "ephemeral", "ttl": settings.BEDROCK_PROMPT_CACHE_TTL}


def _extract_text(content: Any) -> str:
    """Pull plain text out of a chat-model response ``content`` payload.

    Anthropic (and the scripted fake) return a ``str``; Bedrock returns a list of
    content blocks (e.g. ``[{"type": "text", "text": "..."}]``). Mirrors
    ``app.agents.deep_agent_runner._extract_text`` so this one-shot call decodes model
    output identically to the agent runtime.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _usage_from_response(resp: Any) -> Usage:
    """Extract ``{input,output,cache_read,cache_write}_tokens`` off a response.

    Reads the standard ``AIMessage.usage_metadata``. Degrade-safe: a missing / ``None``
    ``usage_metadata`` (or any missing sub-key) yields all-zeros and never raises. The
    prompt-cache split lives in ``usage_metadata["input_token_details"]`` on Bedrock
    (``cache_read`` / ``cache_creation``); it is absent on ChatAnthropic / scripted /
    no-cache turns → ``(0, 0)``. Mirrors ``deep_agent_runner._cache_token_counts``.
    """
    meta = getattr(resp, "usage_metadata", None) or {}
    details = meta.get("input_token_details") or {}
    return {
        "input_tokens": int(meta.get("input_tokens", 0) or 0),
        "output_tokens": int(meta.get("output_tokens", 0) or 0),
        "cache_read_tokens": int(details.get("cache_read", 0) or 0),
        "cache_write_tokens": int(details.get("cache_creation", 0) or 0),
    }


async def cached_invoke(
    messages: "str | Sequence[BaseMessage]",
    *,
    system: str | None = None,
    model: "str | Any | None" = None,
    max_tokens: int | None = None,
    usage_sink: UsageSink | None = None,
) -> tuple[str, Usage]:
    """Invoke a chat model with Bedrock prompt-caching + token counting (ISS-033).

    Args:
        messages: the per-call message(s). A ``str`` becomes a single ``HumanMessage``;
            a message sequence is used as-is (an already-composed call).
        system: optional STABLE system/context prefix, prepended as a ``SystemMessage``.
            ``langchain_aws`` places the Bedrock ``cachePoint`` on the system prefix, so
            a prefix repeated across calls is cache-eligible (multi-turn cache-point
            placement). When ``None`` no system message is added — the request is
            byte-identical to a bare ``HumanMessage`` call (parity for the planner /
            clarify sites, whose fixed prefix is interleaved with the volatile brief).
        model: ``None`` / ``str`` → built via :func:`build_model` (the INV-13 sanctioned
            path — no deep-agent factory, no hand-rolled loop); an already-built
            ``BaseChatModel`` instance → used as-is (the scripted-model test-injection
            path, mirroring ``DeepAgentRunner``; also lets
            a caller keep its own tuned model, e.g. SmartPlanner's temperature=0).
        max_tokens: output ceiling forwarded to ``build_model`` (ignored when a model
            instance is supplied — that instance owns its own cap).
        usage_sink: optional callable; receives the call's :data:`Usage` so the tokens
            are COUNTED in the caller's run accounting (closes the ISS-033/034 counting
            half). Guarded — a raising sink never breaks the model call.

    Returns:
        ``(text, usage)`` — the response text and the :data:`Usage` dict
        ``{input_tokens, output_tokens, cache_read_tokens, cache_write_tokens}``.
    """
    # ── Resolve the model. A plain instance is used verbatim (scripted fake / a
    #    caller's own tuned model); a ``str`` / ``None`` goes through the ONE sanctioned
    #    factory (INV-13). Duck-typed on the factory boundary (avoid a heavy top import).
    if isinstance(model, str) or model is None:
        llm = build_model(model, max_tokens=max_tokens)
    else:
        llm = model

    # ── Compose the message list: stable system prefix (cache-eligible) then the
    #    per-call content.
    msg_list: list[BaseMessage] = []
    if system:
        msg_list.append(SystemMessage(content=system))
    if isinstance(messages, str):
        msg_list.append(HumanMessage(content=messages))
    else:
        msg_list.extend(messages)

    # ── Cache points: pass the Bedrock ``cache_control`` per-call kwarg (the
    #    direct-invoke equivalent of the middleware). No-op on non-Bedrock / flag-off.
    cc = _bedrock_cache_control(llm)
    invoke_kwargs: dict[str, Any] = {"cache_control": cc} if cc else {}

    resp = await llm.ainvoke(msg_list, **invoke_kwargs)

    text = _extract_text(getattr(resp, "content", resp))
    usage = _usage_from_response(resp)

    if usage_sink is not None:
        try:
            usage_sink(usage)
        except Exception:  # noqa: BLE001 — counting must never break the call
            logger.warning(
                "cached_invoke usage_sink raised; usage=%s dropped from accounting",
                usage,
                exc_info=True,
            )

    return text, usage
