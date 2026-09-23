"""app/agents/model_factory.py — single source of truth for building the LLM client.

Every agent graph builds its chat model here, so provider selection and the
Bedrock reliability tuning live in exactly one place.

Provider chain, in order:
  - ANTHROPIC_API_KEY set   → ChatAnthropic (local dev)
  - BEDROCK id + AWS_REGION → ChatBedrockConverse (production)
  - MISTRAL_API_KEY set     → ChatMistralAI (fallback & opt-in for eval)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agents.capabilities.model_catalog import ModelCatalog
from app.core.config import settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger("app.agents.model_factory")

# Dedupe the warn-once-per-unknown-id reasoning log.
_WARNED_UNKNOWN_REASONING: set[str] = set()


class ModelConfigurationError(RuntimeError):
    """Raised when no configured LLM provider (Anthropic, Bedrock, or Mistral) resolves."""


class BedrockTokenDecodeError(ValueError):
    """Raised when a Bedrock bearer token cannot be decoded to find its expiry."""


_BEDROCK_BEARER_TOKEN_PREFIX = "bedrock-api-key-"


def decode_bedrock_bearer_token_expiry(token: str):
    """Return the UTC expiry of a Bedrock bearer token — no network call.

    A Bedrock bearer token (``bedrock-api-key-<base64>``) is a base64-encoded
    presigned-SigV4 payload carrying ``X-Amz-Date`` (issue time,
    ``YYYYMMDDTHHMMSSZ``) and ``X-Amz-Expires`` (seconds of validity), so its
    expiry — issue time + that many seconds — is computable purely
    structurally, the same guarantee a JWT's ``exp`` claim gives you. Field
    extraction is by regex rather than a strict query-string parse: the
    payload's exact wrapping (raw query string vs. URL) isn't part of any
    published contract, but the two field names are.
    """
    import base64
    import re
    from datetime import datetime, timedelta, timezone

    if not token or not token.startswith(_BEDROCK_BEARER_TOKEN_PREFIX):
        raise BedrockTokenDecodeError("not a bedrock-api-key-… bearer token")
    payload_b64 = token[len(_BEDROCK_BEARER_TOKEN_PREFIX) :]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    # SigV4 presigned payloads have been observed base64'd with either alphabet;
    # pick the one the token actually uses rather than guessing wrong and
    # silently decoding to garbage (plain b64decode ignores non-alphabet chars).
    decoder = (
        base64.urlsafe_b64decode
        if ("-" in payload_b64 or "_" in payload_b64)
        else base64.b64decode
    )
    try:
        payload = decoder(padded).decode("utf-8", errors="strict")
    except Exception as exc:
        raise BedrockTokenDecodeError(
            f"could not base64-decode token payload: {exc}"
        ) from exc

    date_match = re.search(r"X-Amz-Date=([0-9TZ]+)", payload)
    expires_match = re.search(r"X-Amz-Expires=(\d+)", payload)
    if not date_match or not expires_match:
        raise BedrockTokenDecodeError("token payload missing X-Amz-Date/X-Amz-Expires")
    try:
        issued_at = datetime.strptime(date_match.group(1), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise BedrockTokenDecodeError(f"unparseable X-Amz-Date: {exc}") from exc
    return issued_at + timedelta(seconds=int(expires_match.group(1)))


def preflight_check_provider() -> "tuple[bool, str | None]":
    """No-network check that the provider ``build_model()`` would select is
    usable right now. Call once at run launch, before the engine starts any
    agent (STABILIZATION.md A4) — an expired Bedrock bearer token then fails
    the launch in milliseconds instead of after every parallel reader has
    independently discovered it via a failed model call.

    Only the Bedrock bearer-token path has a check this cheap: its expiry is
    embedded in the token itself (``decode_bedrock_bearer_token_expiry``), so
    nothing leaves the process. Anthropic's/Mistral's API keys and Bedrock's
    IAM/SSO credential chain carry no equivalent structural signal — checking
    those would mean a live model call on every launch, which the failure
    class this guards against (an expired bearer token) doesn't justify
    paying for on every run. ``build_model()`` already raises
    ``ModelConfigurationError`` for a wholly unconfigured provider;
    unaffected by this function.

    Returns ``(True, None)`` when there is nothing to check, or the token is
    still valid; ``(False, message)`` with a secret-free, actionable message
    otherwise.
    """
    from datetime import datetime, timedelta, timezone

    token = settings.AWS_BEARER_TOKEN_BEDROCK
    if not token:
        return True, None
    # Mirrors build_model()'s own precedence: a set ANTHROPIC_API_KEY is ALWAYS
    # used regardless of Bedrock config, so a stale bearer token sitting in the
    # env is irrelevant to a run that will never touch Bedrock.
    if settings.ANTHROPIC_API_KEY:
        return True, None
    try:
        expiry = decode_bedrock_bearer_token_expiry(token)
    except BedrockTokenDecodeError as exc:
        logger.warning(
            "preflight_check_provider: could not decode Bedrock bearer token "
            "structure (%s) — skipping the expiry check for this launch.",
            exc,
        )
        return True, None
    skew = timedelta(seconds=60)
    now = datetime.now(timezone.utc)
    if now >= expiry - skew:
        stamp = expiry.strftime("%Y-%m-%dT%H:%MZ")
        return False, (
            f"Bedrock bearer token expired at {stamp} — rotate "
            "AWS_BEARER_TOKEN_BEDROCK and restart the backend."
        )
    return True, None


_OLLAMA_STRING_ARGS_PATCHED = False


def _restore_ollama_string_tool_args() -> None:
    """Undo langchain_ollama re-parsing a tool argument that was a STRING on the wire.

    `chat_models._parse_arguments_from_tool_call` runs json.loads() on every
    string argument and, if the result is a dict/list, KEEPS the parsed object
    and discards the original string — without consulting the tool's declared
    parameter type. So `write_file(content='{"tasks": [...]}')` arrives at the
    tool as a dict and pydantic rejects it with "Input should be a valid string".
    The model cannot see the difference between what it sent and what arrived,
    so it rewords and re-sends the identical correct payload forever. Observed
    live: 8 attempts over 13 turns, plus the model writing "Hello world" to
    isolate the variable and correctly concluding the pipeline was at fault.

    Ollama itself is NOT at fault — the raw HTTP response carries a properly
    escaped string. The library's own docstring calls this a "band-aid fix" for
    ollama/ollama#6155 and says it "should be removed/changed if fixed
    upstream"; that issue is now CLOSED, so the compensation outlived the bug.

    This restores any value that was a string in the raw payload, which is the
    only case the band-aid mangles — a genuinely object-valued argument still
    passes through untouched. Delete this along with the USE_LOCAL_OLLAMA block
    once langchain-ollama ships without the workaround (1.1.0 is current and
    still has it).
    """
    global _OLLAMA_STRING_ARGS_PATCHED
    if _OLLAMA_STRING_ARGS_PATCHED:
        return

    from langchain_ollama import chat_models as _ocm

    _upstream = _ocm._parse_arguments_from_tool_call

    def _keep_wire_strings(raw_tool_call: dict) -> dict | None:
        parsed = _upstream(raw_tool_call)
        raw_args = (raw_tool_call.get("function") or {}).get("arguments")
        if isinstance(parsed, dict) and isinstance(raw_args, dict):
            for key, wire_value in raw_args.items():
                if isinstance(wire_value, str) and isinstance(
                    parsed.get(key), (dict, list)
                ):
                    parsed[key] = wire_value
        return parsed

    _ocm._parse_arguments_from_tool_call = _keep_wire_strings
    _OLLAMA_STRING_ARGS_PATCHED = True
    logger.warning(
        "ollama tool-arg shim active — string arguments re-parsed by "
        "langchain_ollama are restored from the raw payload"
    )


def reasoning_fields(
    model_id: str,
    effort: str | None,
    max_tokens: int,
    *,
    disable_thinking: bool = False,
    include_budget_on_adaptive: bool = False,
) -> dict:
    """Build the reasoning block for ``additionalModelRequestFields``.

    The ONE place a reasoning wire shape is constructed (spec 020 / FR-03). It
    replaces ``_ADAPTIVE_THINKING_MODEL_FRAGMENTS`` + ``_thinking_type``, which
    decided the same thing by matching substrings against a model id — a tuple
    that had already drifted from its copy in ``api/capabilities.py``.

    The shape comes from the model's catalog capability, not its id::

        effort    -> {"reasoning": {"effort": <level>}}        GPT-5.6
        adaptive  -> {"thinking": {"type": "adaptive"}}        Claude Sonnet 5
        budget    -> {"thinking": {"type": "enabled", ...}}    Claude <= 4.6
        none      -> {}                                        Claude Haiku 3.5

    Three rules that are bugs if broken:

    1. ``effort is None`` reproduces today's request EXACTLY (INV-3). Unset is
       not the same as the level ``"none"``: every Claude step currently runs
       with thinking ON at full budget, so conflating them would silently change
       every existing workflow.
    2. ``effort == "none"`` means the user explicitly turned reasoning off.
    3. An id absent from the catalog falls back to ``budget`` — today's
       behaviour. ``none`` would be tidier and would silently stop sending
       ``thinking`` for any uncatalogued model: a parity break wearing a
       cleanup's clothes.

    ``include_budget_on_adaptive`` preserves a pre-existing quirk of the
    ChatAnthropic (local-dev) branch, which sent ``budget_tokens`` alongside
    ``type: adaptive`` where the Bedrock branch omits it. Whether that is
    correct is untested here — no ``ANTHROPIC_API_KEY`` is configured — so it is
    preserved rather than quietly changed.
    """
    entry = ModelCatalog().resolve(model_id)
    if entry is None:
        if model_id not in _WARNED_UNKNOWN_REASONING:
            _WARNED_UNKNOWN_REASONING.add(model_id)
            logger.warning(
                "reasoning_fields: %r is not in the model catalog — assuming "
                "mode=budget (today's behaviour). Add a catalog entry to make "
                "its reasoning shape explicit.",
                model_id,
            )
        mode, levels = "budget", ("none", "on")
    else:
        mode, levels = entry.reasoning.mode, entry.reasoning.levels

    if mode == "none":
        return {}

    if effort is not None and effort not in levels:
        logger.warning(
            "reasoning_fields: effort=%r is not offered by %s (accepts %s) — "
            "dropping it rather than sending a request the provider rejects.",
            effort,
            model_id,
            ", ".join(levels) or "nothing",
        )
        effort = None

    if mode == "effort":
        # No global default here: an unset effort sends nothing and lets the
        # model apply its own (medium, for the GPT-5.6 family).
        return {"reasoning": {"effort": effort}} if effort else {}

    # --- Claude: adaptive / budget -----------------------------------------
    if effort == "none":
        return {"thinking": {"type": "disabled"}}

    # effort "on" or unset: the existing global predicate still decides, so an
    # unset step is byte-identical to today.
    thinking_enabled = settings.THINKING_BUDGET_TOKENS > 0 and not disable_thinking
    if thinking_enabled:
        if mode == "adaptive":
            block = {"type": "adaptive"}
            if include_budget_on_adaptive:
                block["budget_tokens"] = max(
                    1024, min(settings.THINKING_BUDGET_TOKENS, max_tokens - 1)
                )
            return {"thinking": block}
        return {
            "thinking": {
                "type": "enabled",
                "budget_tokens": max(
                    1024, min(settings.THINKING_BUDGET_TOKENS, max_tokens - 1)
                ),
            }
        }

    # Adaptive models enable thinking by DEFAULT, so an explicit disable is the
    # only way to keep it off — omitting the field is not enough.
    if disable_thinking and mode == "adaptive":
        return {"thinking": {"type": "disabled"}}
    return {}


def thinking_is_on(fields: dict) -> bool:
    """True when ``fields`` turns Claude thinking on (Claude needs temperature=1)."""
    block = fields.get("thinking")
    return bool(block) and block.get("type") != "disabled"


def build_model(
    model: str | None = None,
    *,
    max_tokens: int | None = None,
    provider: str | None = None,
    disable_thinking: bool = False,
    effort: str | None = None,
) -> "BaseChatModel":
    """Return a configured chat model for an agent graph.

    ``model`` overrides the provider default (the user's per-run selection).
    ``max_tokens`` defaults to settings.MAX_OUTPUT_TOKENS — no per-agent cap.
    ``effort`` is the per-step reasoning level (spec 020). ``None`` means send
    nothing and behave exactly as before; the level ``"none"`` means turn
    reasoning off. ``reasoning_fields`` maps it per the model's capability and
    drops it for a family that cannot take it.
    ``disable_thinking`` forces thinking OFF regardless of THINKING_BUDGET_TOKENS.
    Use this for lightweight one-shot classifier calls where thinking is
    unnecessary and the tiny max_tokens budget would be below the thinking floor.
    On adaptive models (sonnet-5, opus-5) this passes {"type": "disabled"}
    explicitly — omitting the field is not enough since those models enable
    adaptive thinking by default.
    """
    # --- LOCAL OLLAMA OVERRIDE (temp, dev-only — comment out or delete when done) ---
    # Off unless USE_LOCAL_OLLAMA is explicitly truthy, so this block can stay
    # pasted in without hijacking runs that should hit the real provider.
    # Reads .env directly: pydantic loads .env into settings WITHOUT exporting to
    # os.environ (same trap the AWS_BEARER_TOKEN_BEDROCK bridge below works around),
    # so os.getenv alone would never see a value set in the file.
    import os

    from dotenv import dotenv_values

    from app.core.config import ENV_FILE

    _ollama_env = {**dotenv_values(ENV_FILE), **os.environ}  # real env wins
    if _ollama_env.get("USE_LOCAL_OLLAMA", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        from langchain_ollama import ChatOllama

        ollama_model = _ollama_env.get("OLLAMA_MODEL") or "qwen3.5:4b"
        ollama_url = _ollama_env.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        # num_ctx/num_predict are NOT optional here. Ollama ignores the model's own
        # advertised context (qwen3.5 reports 262144) and applies its RUNTIME default
        # of 4096 unless told otherwise — so a deck agent's prompt (template + design
        # system + the previous step's full deck) fills the window and generation is
        # cut off mid-token. Observed on a baseline ppt run: ppt-composer emitted 3446
        # chars ending mid-attribute (`style="height`) and ppt-validator 5286 chars
        # likewise, producing "Invalid presentation output" in the preview. Neither
        # agent was at fault — all three declare max_tokens: 32768.
        ollama_ctx = int(_ollama_env.get("OLLAMA_NUM_CTX") or 32768)
        ollama_predict = int(_ollama_env.get("OLLAMA_NUM_PREDICT") or 16384)
        logger.warning("=" * 78)
        logger.warning(
            "!!! LOCAL OLLAMA OVERRIDE ACTIVE — using %s via %s (num_ctx=%d, "
            "num_predict=%d), NOT the real configured provider !!!",
            ollama_model,
            ollama_url,
            ollama_ctx,
            ollama_predict,
        )
        logger.warning("=" * 78)
        _restore_ollama_string_tool_args()
        return ChatOllama(
            model=ollama_model,
            base_url=ollama_url,
            reasoning=True,
            num_ctx=ollama_ctx,
            num_predict=ollama_predict,
        )
    # --- end override ---

    if max_tokens is None:
        max_tokens = settings.MAX_OUTPUT_TOKENS

    if provider == "mistral":
        if not settings.MISTRAL_API_KEY:
            raise ModelConfigurationError(
                "provider='mistral' was requested but MISTRAL_API_KEY is not set."
            )
        from langchain_mistralai import ChatMistralAI

        model_id = model or settings.MISTRAL_MODEL_ID
        logger.debug(
            "build_model: ChatMistralAI (explicit provider) model=%s max_tokens=%d",
            model_id,
            max_tokens,
        )
        # ChatMistralAI's own default is timeout=120, which cannot deliver a
        # MAX_OUTPUT_TOKENS (32768) generation and silently truncates long ones
        # into an httpx.ReadTimeout mid-stream. Seen on the first
        # mistral-large-latest prototype build: 18176 tokens in, 26 out, then
        # ReadTimeout. LLM_CALL_TIMEOUT_SECONDS is this project's declared
        # budget for one streaming call — the 120 was an unstated default
        # nobody chose, not a policy.
        return ChatMistralAI(
            model=model_id,
            api_key=settings.MISTRAL_API_KEY,
            timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
        )

    # Reasoning (extended thinking / effort) is built by ``reasoning_fields``
    # from the model's CATALOG capability — see its docstring for the shapes
    # and the parity rules. Claude still requires temperature=1 when on.

    if settings.ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic

        model_id = model or settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
        logger.debug(
            "build_model: ChatAnthropic model=%s max_tokens=%d", model_id, max_tokens
        )
        anthropic_kwargs: dict = dict(
            model=model_id,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=max_tokens,
        )
        anthropic_reasoning = reasoning_fields(
            model_id,
            effort,
            max_tokens,
            disable_thinking=disable_thinking,
            # Preserves this branch's pre-existing shape — it sent budget_tokens
            # alongside type=adaptive where Bedrock omits it.
            include_budget_on_adaptive=True,
        )
        if "thinking" in anthropic_reasoning:
            anthropic_kwargs["thinking"] = anthropic_reasoning["thinking"]
        if thinking_is_on(anthropic_reasoning):
            anthropic_kwargs["temperature"] = 1  # required when thinking is on
        return ChatAnthropic(**anthropic_kwargs)

    import os

    from botocore.config import Config
    from langchain_aws import ChatBedrockConverse

    # botocore reads the bearer token from the PROCESS ENV, and pydantic loads .env
    # into settings without exporting it. Without this bridge a native run would
    # silently fall back to SigV4 ambient credentials instead of the token.
    if settings.AWS_BEARER_TOKEN_BEDROCK and not os.environ.get(
        "AWS_BEARER_TOKEN_BEDROCK"
    ):
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.AWS_BEARER_TOKEN_BEDROCK

    # Settings alone, deliberately NOT the ``model`` override — otherwise a
    # Mistral-only environment would read as Bedrock config and skip the fallback.
    bedrock_configured = bool(
        (settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID)
        and settings.AWS_REGION
    )
    if not bedrock_configured:
        if settings.MISTRAL_API_KEY:
            from langchain_mistralai import ChatMistralAI

            mistral_model_id = model or settings.MISTRAL_MODEL_ID
            logger.debug(
                "build_model: ChatMistralAI (fallback) model=%s max_tokens=%d",
                mistral_model_id,
                max_tokens,
            )
            # Same 120s-default problem as the explicit-provider branch above.
            return ChatMistralAI(
                model=mistral_model_id,
                api_key=settings.MISTRAL_API_KEY,
                timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
            )
        raise ModelConfigurationError(
            "No LLM configured. Set ANTHROPIC_API_KEY for local dev, "
            "BEDROCK_INFERENCE_PROFILE_ID + AWS_REGION for production, "
            "or MISTRAL_API_KEY for a free-tier fallback."
        )
    model_id = (
        model or settings.BEDROCK_INFERENCE_PROFILE_ID or settings.BEDROCK_MODEL_ID
    )
    region = settings.AWS_REGION
    logger.debug(
        "build_model: ChatBedrockConverse model=%s region=%s max_tokens=%d",
        model_id,
        region,
        max_tokens,
    )
    # Passed as additional_model_request_fields only when non-empty, so the
    # thinking-disabled path never carries the kwarg at all.
    # Adaptive-mode models (sonnet-5, opus-5, etc.) reject budget_tokens —
    # Bedrock returns ValidationException: thinking.adaptive.budget_tokens:
    # Extra inputs are not permitted. Only the "enabled" type accepts it.
    # When disable_thinking=True on an adaptive model, we must explicitly pass
    # {"type": "disabled"} — omitting the field leaves adaptive thinking ON by
    # default on sonnet-5/opus-5, which would still violate the max_tokens floor.
    extra_fields: dict = reasoning_fields(
        model_id, effort, max_tokens, disable_thinking=disable_thinking
    )
    bedrock_kwargs: dict = dict(
        model=model_id,
        region_name=region,
        max_tokens=max_tokens,
        # read_timeout bounds time-to-first-token on a slow stream; adaptive
        # retries absorb on-demand throttling.
        config=Config(
            read_timeout=600,
            connect_timeout=30,
            # STABILIZATION.md A4: verified against botocore's own retry
            # classifiers (ModeledRetryableChecker/ThrottledRetryableChecker/
            # TransientRetryableChecker) that AccessDeniedException,
            # UnrecognizedClientException and ExpiredTokenException (bedrock-
            # runtime: 403/400, senderFault, no modeled `retryable` trait) are
            # NOT retried under this config — botocore already fails an
            # auth-class error on the first attempt, no code needed here to
            # force it. max_attempts=5/adaptive is retry budget for the
            # THROTTLING/5xx/timeout classes it's meant for.
            retries={"max_attempts": 5, "mode": "adaptive"},
        ),
    )
    if extra_fields:
        bedrock_kwargs["additional_model_request_fields"] = extra_fields
    if thinking_is_on(extra_fields):
        bedrock_kwargs["temperature"] = 1  # required when thinking is on
    return ChatBedrockConverse(**bedrock_kwargs)


def _build_bedrock_bearer_session():
    """Return a boto3 Session for Bedrock bearer-token auth.

    botocore (>= 1.39) uses token auth for ``bedrock-runtime`` clients whenever
    AWS_BEARER_TOKEN_BEDROCK is in the process env, so a plain session suffices.
    The env bridge below is the same one ``build_model`` does.
    """
    import os

    import boto3

    if settings.AWS_BEARER_TOKEN_BEDROCK and not os.environ.get(
        "AWS_BEARER_TOKEN_BEDROCK"
    ):
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.AWS_BEARER_TOKEN_BEDROCK
    return boto3.Session()


def model_identifier(llm) -> str:
    """Best-effort model id off a built chat model (for token-cost reporting).

    ChatBedrockConverse exposes ``.model_id``; ChatAnthropic and ChatMistralAI
    expose ``.model``. ``.model_name`` covers providers that alias it instead.
    """
    return (
        getattr(llm, "model_id", None)
        or getattr(llm, "model", None)
        or getattr(llm, "model_name", None)
        or "unknown"
    )
