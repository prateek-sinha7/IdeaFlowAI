"""agents/model_policy.py — the per-agent ``ModelResolver`` + throttle predicate (MODEL-01/02/05).

This is the heart of Phase 6 (Model Policy). ONE resolution path decides the effective
model id for every agent invocation, by the locked precedence (D-02), so the engine never
hand-threads a single session id again. The parity-critical default (tier 5 =
``session model_id or Haiku``) keeps existing single-model runs byte/semantic-identical
(INV-3): with no overrides and every manifest/agent tier ``None`` (today's state), every
agent resolves to exactly the id ``build_model`` received before this phase.

Kernel module (NOT under ``agents.capabilities`` / ``agents.workflows``) — import-linter
places no contract on it, so it may import the pure-data plan types, the catalog, and
``app.core.config.settings`` (the global Haiku default). It carries NO ``app.models`` /
``execution_engine`` reach. The resolver is constructed at ``execute()`` entry and rides on
``ExecutionContext.model_resolver`` (typed ``object | None`` — import-pure, like
``scoped_store``); the three ``_run_agent`` model sites consult it.

Precedence (D-02 — highest wins, ``None`` tiers SKIPPED):
  1. user override            ``model_overrides[spec.id]``
  2. step.model               ``step.model.model``           (compiled Step — None today)
  3. AgentSpec.model          ``spec.model``                 (AGENT.md — D-09; None today)
  4. workflow.model           ``workflow_model.model``       (CompiledWorkflow.model — None today)
  5a. session model_id        ``session_model_id``           (the user-selected run model)
  5b. global Haiku default    ``haiku_default``              (settings.BEDROCK_INFERENCE_PROFILE_ID)

Fallback chains (N11 / D-05) — owned here for the 06-05 fallback loop: an empty
``ModelPolicy.fallback`` derives the tier-descent default (Opus→[Sonnet, Haiku],
Sonnet→[Haiku], Haiku→[]) from the catalog ``cost_class``; an explicit ``fallback``
overrides it. Every chain entry is catalog-validated.

``_is_transient_throttle(exc)`` (D-06) co-located here so the 06-05 engine retry loop and
the unit test import ONE predicate. It is a defensive layered classifier (type-name OR
HTTP-status OR error-code/message substring); non-matching errors return ``False`` (the
caller re-raises, no model switch).
"""

from __future__ import annotations

import logging

from agents.capabilities.model_catalog import (
    ModelCatalog,
    ModelEntry,
    normalize_model_id,
)
from agents.workflows.plan import ModelPolicy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost-class tier ordering (canonical, from the catalog ``cost_class`` field).
# Tier-descent walks from the model's own class down to the cheapest, picking
# one catalog id per lower class (D-05 / N11). premium > standard > cheap.
# ---------------------------------------------------------------------------
_COST_CLASS_ORDER: tuple[str, ...] = ("premium", "standard", "cheap")

# ---------------------------------------------------------------------------
# Geo-prefix normalization (GEO-01) — resolves CRIS prefix to match AWS_REGION.
#
# AGENT.md files may declare a model with any geo prefix (e.g. "us.anthropic.
# claude-sonnet-5" for local dev at us-east-2). When the same code is deployed
# to eu-central-1, that US prefix causes a Bedrock ValidationException — the US
# CRIS profile is not available in EU regions. Rather than editing AGENT.md per
# environment, the resolver normalizes the geo prefix at runtime using AWS_REGION.
#
# Supported prefixes: us. / eu. / au. / apac. (global. passes through unchanged).
# Unknown regions pass through unchanged and let Bedrock reject if truly wrong.
# ---------------------------------------------------------------------------

# All known geo prefixes — the resolver replaces these when the region doesn't match.
_GEO_PREFIXES: tuple[str, ...] = ("us.", "eu.", "au.", "apac.")

# Map AWS region → the correct CRIS geo prefix for that geography.
# Source: AWS Bedrock documentation for cross-region inference profiles.
_REGION_TO_GEO_PREFIX: dict[str, str] = {
    # US regions
    "us-east-1": "us.",
    "us-east-2": "us.",
    "us-west-1": "us.",
    "us-west-2": "us.",
    "ca-central-1": "us.",
    "ca-west-1": "us.",
    # EU regions
    "eu-central-1": "eu.",
    "eu-central-2": "eu.",
    "eu-north-1": "eu.",
    "eu-south-1": "eu.",
    "eu-south-2": "eu.",
    "eu-west-1": "eu.",
    "eu-west-2": "eu.",
    "eu-west-3": "eu.",
    # APAC regions
    "ap-northeast-1": "apac.",
    "ap-northeast-2": "apac.",
    "ap-northeast-3": "apac.",
    "ap-south-1": "apac.",
    "ap-south-2": "apac.",
    "ap-southeast-1": "apac.",
    "ap-southeast-2": "apac.",
    "ap-southeast-3": "apac.",
    "ap-southeast-4": "apac.",
    "ap-southeast-5": "apac.",
    "ap-southeast-6": "apac.",
    "ap-southeast-7": "apac.",
    "ap-east-2": "apac.",
}


def _normalize_geo_prefix(model_id: str, *, _region_override: str | None = None) -> str:
    """Swap a CRIS geo prefix to match the deployment AWS_REGION.

    Example: ``us.anthropic.claude-sonnet-5`` on ``eu-central-1``
             → ``eu.anthropic.claude-sonnet-5``

    Rules:
    - ``global.`` prefixes are never swapped (they route anywhere by design).
    - Models with no geo prefix pass through unchanged.
    - Unknown AWS regions pass through unchanged (let Bedrock surface the error).
    - Already-correct prefix is a no-op (fast path).

    ``_region_override`` is for testing only — it bypasses ``settings.AWS_REGION``
    so unit tests can assert normalization behaviour without patching settings.

    This is called after the D-02 precedence chain resolves so it applies
    equally to tier-1 overrides, tier-3 AGENT.md values, and the session default.
    The catalog validation for tier-3 always runs on the RAW (pre-normalization)
    value, which must be in the catalog — both ``us.`` and ``eu.`` Sonnet-5 entries
    are present so validation passes before the swap happens.
    """
    if _region_override is not None:
        region = _region_override
    else:
        # Lazy import to avoid a circular import at module load time.
        # model_policy is a kernel module that may be imported before app.core.config
        # is fully initialised; the lazy import is safe here because _normalize_geo_prefix
        # is only called from resolve(), which only runs at request time.
        try:
            from app.core.config import settings as _settings  # noqa: PLC0415

            region = _settings.AWS_REGION or ""
        except Exception:  # noqa: BLE001
            return model_id  # config unavailable — pass through

    correct_prefix = _REGION_TO_GEO_PREFIX.get(region)
    if not correct_prefix:
        # Unknown region — pass through unchanged.
        return model_id

    # Identify the geo prefix the model id currently carries.
    current_prefix: str | None = None
    for prefix in _GEO_PREFIXES:
        if model_id.startswith(prefix):
            current_prefix = prefix
            break

    if current_prefix is None or current_prefix == correct_prefix:
        # No geo prefix, or already correct — nothing to do.
        return model_id

    # Swap the prefix.
    normalized = correct_prefix + model_id[len(current_prefix) :]
    logger.debug(
        "model_resolver: geo-prefix swapped %r → %r (AWS_REGION=%r)",
        model_id,
        normalized,
        region,
    )
    return normalized


class ModelResolver:
    """Resolve the effective model id per agent invocation, by the D-02 precedence.

    Constructed once per run at ``execute()`` entry with the run-level inputs and a
    ``ModelCatalog`` reference. Stateless w.r.t. a single ``resolve()`` call — but it ALSO
    holds the active fallback chain + cursor the 06-05 engine retry loop drives
    (``set_chain`` / ``advance`` / ``current``), so one object owns both selection and
    fallback composition.
    """

    def __init__(
        self,
        *,
        model_overrides: dict[str, str] | None = None,
        workflow_model: ModelPolicy | None = None,
        session_model_id: str | None = None,
        haiku_default: str = "",
        catalog: ModelCatalog | None = None,
        _region_override: str | None = None,
    ) -> None:
        self._overrides: dict[str, str] = dict(model_overrides or {})
        self._workflow_model = workflow_model
        self._session_model_id = session_model_id
        self._haiku_default = haiku_default
        self._catalog = catalog or ModelCatalog()
        # For testing: bypass settings.AWS_REGION with an explicit region string.
        # Pass the empty string "" to disable geo-prefix normalization entirely.
        self._region_override = _region_override
        # Active fallback chain + cursor (06-05 retry loop). The cursor points at the
        # CURRENTLY-running id; advance() moves to the next chain entry.
        self._chain: list[str] = []
        self._cursor: int = 0

    # ── Precedence resolution (D-02) ─────────────────────────────────────────────────
    def resolve(self, spec, step=None) -> str:
        """Return the effective model id for ``spec`` under ``step`` by the 5-tier precedence.

        ``None`` tiers are skipped (an empty tier never blocks a lower one). Tier 3
        (``AgentSpec.model``) is catalog-validated at resolve time (Q2 allow-list,
        T-06-03): an unknown AGENT.md model id raises ``ValueError`` rather than silently
        flowing into ``build_model`` — but ONLY when tier 3 is actually the selected tier
        (WR-01). A higher-precedence tier-1 override or tier-2 step.model must be able to
        win even when AGENT.md declares an invalid (e.g. retired) model id, so the tier-3
        catalog check is deferred until after the precedence ``or``-chain resolves.
        """
        # 3. AgentSpec.model — resolved below; catalog-validated only if it WINS.
        agent_model = getattr(spec, "model", None)
        # The two higher-precedence tiers, computed first so we can tell whether
        # tier 3 is actually the SELECTED tier before validating it (WR-01).
        override = self._overrides.get(getattr(spec, "id", None))  # 1 override
        step_model = step.model.model if step is not None and step.model else None  # 2

        resolved = (
            override
            or step_model
            or agent_model  # 3 AgentSpec.model
            or (
                self._workflow_model.model if self._workflow_model else None
            )  # 4 workflow.model
            or self._session_model_id  # 5a session model_id
            or self._haiku_default  # 5b global Haiku
        )

        # Log effective model resolution so operators can verify tier-3 AGENT.md
        # overrides (e.g. prototype-revision-analyzer using Sonnet 5) are active.
        _tier = (
            "tier-1/override"
            if override
            else "tier-2/step.model"
            if step_model
            else "tier-3/agent.md"
            if agent_model
            else "tier-4/workflow"
            if (self._workflow_model and self._workflow_model.model)
            else "tier-5/session"
        )
        agent_id = getattr(spec, "id", "?")
        logger.info(
            "model_resolver: agent=%r  resolved=%r  tier=%s",
            agent_id,
            resolved,
            _tier,
        )
        # CR-01 defense-in-depth: catalog-validate tier-2 ``step.model`` when it is
        # the SELECTED tier. ``step.model`` originates from a user-composed
        # ``selections`` map (synth → compiler ``_compile_model_policy``, which accepts
        # any string id). The WS / save chokepoints now allow-list it, but the kernel
        # must never trust an unvalidated id regardless of caller — so the resolver is
        # the last line before ``build_model``. (Tier-1 ``override`` is validated at the
        # MODEL-03 ingress chokepoint; lower tiers 4/5 are catalog-trusted upstream.)
        if override is None and step_model is not None:
            if not self._catalog.is_allowed(step_model):
                raise ValueError(
                    f"step.model {step_model!r} for agent "
                    f"{getattr(spec, 'id', '?')!r} is not a known, allowed catalog model"
                )
        # Validate tier 3 ONLY when no higher-precedence tier resolved — i.e. when
        # AgentSpec.model is actually the selected tier. An invalid AGENT.md model
        # id must not block a run that a tier-1 override or tier-2 step.model would
        # have rescued (WR-01). Lower tiers (4/5) are catalog-trusted upstream.
        if override is None and step_model is None and agent_model is not None:
            if not self._catalog.is_allowed(agent_model):
                raise ValueError(
                    f"AGENT.md model {agent_model!r} for agent "
                    f"{getattr(spec, 'id', '?')!r} is not a known, allowed catalog model"
                )
        # GEO-01: swap the CRIS geo prefix (us./eu./au.) to match the deployment
        # AWS_REGION before returning. AGENT.md files declare the model with any
        # regional prefix; this makes the same manifest work on both local dev
        # (us-east-2) and production (eu-central-1) without any per-environment
        # edits. The swap happens AFTER catalog validation so the raw AGENT.md
        # value is what gets validated (both us. and eu. Sonnet-5 are in the
        # catalog), and the normalized value is what reaches build_model.
        return _normalize_geo_prefix(resolved, _region_override=self._region_override)

    # ── Reasoning effort (spec 020) ──────────────────────────────────────────────────
    def resolve_effort(self, step=None) -> str | None:
        """Return the effective reasoning effort, or ``None``.

        A deliberately SHORTER precedence than ``resolve()``: step.model.effort
        (tier 2), then workflow.model.effort (tier 4). There is no tier-1
        override, no AGENT.md tier and no session tier, because effort is
        authored on the step in the canvas and nothing else writes it — the
        other three would be untested code paths for a value nothing sets.

        Takes only ``step``: unlike ``resolve()`` there is no spec tier, so a
        ``spec`` parameter would be one that no branch reads.

        ``None`` means "send no reasoning field", which is NOT the level
        ``"none"`` (explicitly off). That distinction is what keeps an unset
        step byte-identical to its pre-effort behaviour.

        The value is NOT family-checked here — the kernel does not know which
        models accept which levels. ``model_factory.reasoning_fields`` is the
        single place that decides, and it drops a level the model cannot take.
        """
        step_effort = step.model.effort if step is not None and step.model else None
        workflow_effort = self._workflow_model.effort if self._workflow_model else None
        return step_effort or workflow_effort

    # ── Fallback chain derivation (N11 / D-05) ───────────────────────────────────────
    def chain_for(self, model_id: str, policy: ModelPolicy | None = None) -> list[str]:
        """Return the ordered fallback chain for ``model_id``.

        An explicit, non-empty ``policy.fallback`` overrides the derived default — but every
        entry must be catalog-valid (``ValueError`` otherwise). With no explicit fallback the
        tier-descent default is derived from the catalog ``cost_class``: from the model's own
        class down to the cheapest, one catalog id per lower class
        (premium→[standard, cheap] = Opus→[Sonnet, Haiku]; standard→[cheap] = Sonnet→[Haiku];
        cheap→[] = Haiku→[]).
        """
        if policy is not None and policy.fallback:
            for entry in policy.fallback:
                if not self._catalog.is_allowed(entry):
                    raise ValueError(
                        f"explicit fallback entry {entry!r} is not a known, allowed catalog model"
                    )
            return list(policy.fallback)
        return self._derive_tier_descent(model_id)

    def _derive_tier_descent(self, model_id: str) -> list[str]:
        """Derive the default tier-descent chain from the catalog ``cost_class``."""
        entry = self._catalog.get(model_id)
        if entry is None:
            return []
        try:
            start = _COST_CLASS_ORDER.index(entry.cost_class)
        except ValueError:
            return []
        chain: list[str] = []
        # For each strictly-cheaper cost class, pick the first catalog id in that class.
        for cost_class in _COST_CLASS_ORDER[start + 1 :]:
            pick = self._first_id_in_class(cost_class)
            if pick is not None:
                chain.append(pick)
        return chain

    def _first_id_in_class(self, cost_class: str) -> str | None:
        """Return the first user-allowed catalog id whose ``cost_class`` matches."""
        for entry in self._catalog.list():
            if entry.cost_class == cost_class and entry.user_allowed:
                return entry.id
        return None

    # ── Active chain + cursor (consumed by the 06-05 engine retry loop) ──────────────
    def set_chain(self, primary: str, policy: ModelPolicy | None = None) -> None:
        """Arm the active fallback chain for ``primary`` (cursor at the primary)."""
        self._chain = [primary, *self.chain_for(primary, policy)]
        self._cursor = 0

    def current(self) -> str | None:
        """The id the cursor currently points at, or ``None`` if the chain is exhausted."""
        if 0 <= self._cursor < len(self._chain):
            return self._chain[self._cursor]
        return None

    def advance(self) -> str | None:
        """Move the cursor to the next chain id; return it, or ``None`` if exhausted."""
        self._cursor += 1
        return self.current()


# ---------------------------------------------------------------------------
# Throttle classification (D-06) — co-located so the engine retry (06-05) and
# the unit test import ONE predicate. Defensive, layered, FAIL-OPEN for
# provider faults: error-code (case-insensitive) OR HTTP-status OR
# EventStreamError OR message substring. Non-matching → False (re-raise).
# ---------------------------------------------------------------------------

# Defensive import — botocore is a real runtime dependency (langchain-aws /
# app.agents.model_factory already require it), but this module has carried
# none so far; guard so a stripped install degrades to "never an
# EventStreamError" rather than an ImportError at module load.
try:
    from botocore.exceptions import EventStreamError as _EventStreamError
except ImportError:  # pragma: no cover - botocore always present in prod/dev
    _EventStreamError = None  # type: ignore[assignment]

# Bedrock / botocore transient ClientError codes (prod, ChatBedrockConverse).
# Compared via ``.casefold()`` below: Bedrock's EVENT-STREAM error frame
# (``ConverseStream``) carries the LOWER-camel ``:exception-type`` header value
# (``internalServerException``), not the PascalCase shape name botocore uses for
# a regular (non-streaming) ``ClientError`` (``InternalServerException``) — a
# case-sensitive membership test silently missed the streaming shape. This is
# the exact incident this predicate exists to catch.
# ``ModelStreamErrorException`` / ``ModelErrorException`` are confirmed
# retryable by TWO independent in-repo sources, not guessed: (1) the real
# bedrock-runtime botocore service model (2023-09-30) documents
# ModelStreamErrorException as "An error occurred while streaming the
# response. Retry your request." — the streaming sibling of
# InternalServerException, same "try again" contract as the incident; (2)
# ``app/agents/llm_errors.py._BEDROCK_CODE_MAP`` (the free-chat path's
# already-reviewed Bedrock error classifier) marks BOTH
# ``recoverable=True`` from real-incident experience (STABILIZATION.md A4).
_TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelTimeoutException",
        "ServiceQuotaExceededException",
        "ModelStreamErrorException",
        "ModelErrorException",
    }
)
_TRANSIENT_ERROR_CODES_CF: frozenset[str] = frozenset(
    c.casefold() for c in _TRANSIENT_ERROR_CODES
)

# Permanent (genuinely OUR fault) error codes — checked FIRST and also
# case-insensitively; a match returns False immediately, before the
# EventStreamError fail-open below gets a chance to flip it transient.
# Confirmed against the real bedrock-runtime botocore service model
# (2023-09-30: AccessDeniedException/ValidationException/ResourceNotFoundException,
# all ``error.senderFault: true``), ``app/agents/llm_errors.py._BEDROCK_CODE_MAP``
# (same four codes mapped ``recoverable=False``, plus the credential-family
# codes below), and ``app/agents/model_factory.py`` (STABILIZATION.md A4):
# "verified against botocore's own retry classifiers... that
# AccessDeniedException, UnrecognizedClientException and ExpiredTokenException
# ... are NOT retried" / "no modeled retryable trait". UnauthorizedException /
# InvalidSignatureException join the same generic AWS SigV4 credential/signature
# family — never service-specific (they precede the request ever reaching
# Bedrock), always a local credentials/clock problem, never transient.
#
# Deliberately NOT here (stays transient — "preserve every currently-True
# behaviour" + the llm_errors.py precedent, despite ``senderFault: true``):
#   - ModelTimeoutException / ServiceQuotaExceededException: already
#     transient before this change.
#   - ModelNotReadyException: HTTP 429 + senderFault, but ITS OWN AWS doc says
#     "The AWS SDK will automatically retry the operation up to 5 times" —
#     officially retryable; already covered by the existing 429 HTTP-status
#     check when ResponseMetadata is present.
#   - ModelStreamErrorException / ModelErrorException: see the transient-set
#     comment above.
# Not added despite being a real bedrock-runtime exception shape:
#   - ConflictException: no production evidence it is ever raised by
#     Converse/ConverseStream (absent from llm_errors.py's reviewed map) —
#     not enumerated here rather than guessed.
# No Bedrock exception shape exists for a content/guardrail rejection — a
# guardrail intervention is a NORMAL response field (Converse API
# ``stopReason: "guardrail_intervened"`` / ``GuardrailAction``), never a raised
# exception (confirmed by scanning every ``Guardrail*`` shape in the
# bedrock-runtime service model: none is flagged ``"exception": true``).
_PERMANENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "AccessDeniedException",
        "UnauthorizedException",
        "UnrecognizedClientException",
        "ExpiredTokenException",
        "InvalidSignatureException",
        "ValidationException",
        "ResourceNotFoundException",
    }
)
_PERMANENT_ERROR_CODES_CF: frozenset[str] = frozenset(
    c.casefold() for c in _PERMANENT_ERROR_CODES
)

# Models that have ALREADY streamed successfully in this process. A permanent code
# means "genuinely our fault" — true for an ARN that never resolved, false for one
# that served traffic minutes ago. Bedrock intermittently answers ConverseStream with
# ResourceNotFoundException ("Inference Profile ARN not found") for a profile that is
# demonstrably present: run 353bb0af lost pb-validate that way on
# eu.anthropic.claude-sonnet-4-6 while pb-spec and pb-design had just used the SAME id
# successfully, and a direct probe right after returned OK. Because this predicate is
# the single gate for the runner's same-model retry, the runner's re-raise AND the
# engine's model-fallback loop, one permanent verdict kills all three defences at once.
_PROVEN_MODELS: set[str] = set()

# Permanent codes that flip to transient once the model is proven. ONLY resource
# lookup: an auth/validation/signature failure stays permanent forever — those are
# never provider lies, and a proven model must not launder them into a retry.
_PROVABLY_TRANSIENT_CODES_CF: frozenset[str] = frozenset({"resourcenotfoundexception"})


def mark_model_proven(model_id: str) -> None:
    """Record that ``model_id`` served at least one successful stream here."""
    if model_id:
        _PROVEN_MODELS.add(model_id)


# Transient HTTP statuses: 429 throttle, 503 ServiceUnavailable, 500 InternalServer,
# 529 Anthropic overloaded.
_TRANSIENT_STATUS: frozenset[int] = frozenset({429, 500, 503, 529})
# Type-name / message substrings (langchain-aws / langchain-anthropic may wrap the
# underlying exception; match defensively on the stringified form too).
_TRANSIENT_SUBSTRINGS: tuple[str, ...] = (
    "throttl",  # ThrottlingException / "Throttling"
    "too many requests",
    "ratelimit",  # anthropic.RateLimitError
    "rate limit",
    "serviceunavailable",
    "service unavailable",
    "overloaded",  # anthropic 529 overloaded_error
    "modeltimeout",
    "servicequotaexceeded",
    "internal server",  # EventStreamError message text / generic wrapping
    "internalserver",  # the lower-camel event-stream code, stringified
)


def _is_transient_throttle(exc: BaseException, model_id: str | None = None) -> bool:
    """Return ``True`` iff ``exc`` is a transient throttle / overload worth a model switch.

    FAIL-OPEN for provider faults, not fail-closed: Bedrock's ``ConverseStream``
    can put an event-stream error frame on an otherwise-open stream (surfaced by
    botocore as ``EventStreamError``) carrying a ``response`` dict with NO
    ``ResponseMetadata``/``HTTPStatusCode`` (botocore's event-stream parser never
    attaches one) and a LOWER-camel ``:exception-type`` code
    (``internalServerException``) that a case-sensitive PascalCase whitelist
    misses entirely. Classification order:

      1. A PERMANENT code (case-insensitive) → ``False`` immediately — genuinely
         our fault (bad auth/signature/ARN/input), never worth a retry.
      2. A known TRANSIENT code (case-insensitive) → ``True``.
      3. botocore-shaped ``ClientError``/``EventStreamError`` response dict:
         ``ResponseMetadata.HTTPStatusCode`` ∈ the transient statuses → ``True``.
      4. A ``status_code`` / ``http_status`` attribute ∈ the transient statuses
         (Anthropic clients expose this) → ``True``.
      5. ``exc`` is a ``botocore.exceptions.EventStreamError`` whose code (if
         any) was not caught by step 1 → ``True``. A mid-stream provider fault
         is, by construction, something that happened on Bedrock's side of an
         already-accepted request — fail OPEN for the one exception family this
         predicate cannot otherwise enumerate exhaustively, rather than fail
         CLOSED on an unrecognized code.
      6. The exception type name OR its stringified message contains a known
         transient substring (``Throttling`` / ``RateLimit`` / ``overloaded`` /
         ``internal server`` / …) → ``True``.
      7. Otherwise → ``False`` so the caller re-raises and does NOT switch
         models (a generic ``ValueError``, ``ModelConfigurationError``, or a
         permanent code already ruled out above).
    """
    # botocore-shaped ClientError / EventStreamError response dict — both carry
    # ``{"Error": {"Code": ..., "Message": ...}}``; only ClientError also carries
    # ``ResponseMetadata``.
    response = getattr(exc, "response", None)
    code = None
    if isinstance(response, dict):
        raw_code = response.get("Error", {}).get("Code")
        if isinstance(raw_code, str):
            code = raw_code

    # 1 + 2. Error code, case-insensitive: permanent first, then transient.
    if code is not None:
        folded = code.casefold()
        if folded in _PERMANENT_ERROR_CODES_CF:
            # A resource-lookup failure on a model that already worked in this
            # process is the provider contradicting itself, not our configuration error.
            if (
                model_id
                and folded in _PROVABLY_TRANSIENT_CODES_CF
                and model_id in _PROVEN_MODELS
            ):
                return True
            return False
        if folded in _TRANSIENT_ERROR_CODES_CF:
            return True

    # 3. HTTP status (ClientError only — EventStreamError never has this key).
    if isinstance(response, dict):
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(status, int) and status in _TRANSIENT_STATUS:
            return True

    # 4. Explicit status attribute (Anthropic-style clients).
    for attr in ("status_code", "http_status"):
        status_attr = getattr(exc, attr, None)
        if isinstance(status_attr, int) and status_attr in _TRANSIENT_STATUS:
            return True

    # 5. Fail-open for a mid-stream provider fault: an EventStreamError whose
    # code (if any) already cleared the permanent check in step 1.
    if _EventStreamError is not None and isinstance(exc, _EventStreamError):
        return True

    # 6. Type-name / message substring (defensive — covers wrapped exceptions).
    haystack = f"{type(exc).__name__} {exc}".lower()
    return any(token in haystack for token in _TRANSIENT_SUBSTRINGS)


# ---------------------------------------------------------------------------
# Selectable models (spec 020) — the USER-FACING projection of the catalog.
# ---------------------------------------------------------------------------
def selectable_models() -> list[ModelEntry]:
    """Return the catalog with the geo-prefix duplicates collapsed, one per model.

    The catalog deliberately carries BOTH ``us.`` and ``eu.`` rows for some
    models, because catalog validation runs on the RAW declared id: an AGENT.md
    or a saved step may name either prefix and must still validate (see
    ``resolve()``'s GEO-01 note). That is a resolution concern, not a choice.

    Offering both to a user is offering a choice that does not exist —
    ``_normalize_geo_prefix`` rewrites the prefix to match ``AWS_REGION`` before
    the request is built, so picking "(US)" on an EU deployment silently yields
    the EU profile. Verified live 2026-09-22: ``eu-north-1`` publishes no ``us.``
    inference profile at all.

    So: one entry per normalized family, preferring the one whose prefix already
    matches the deployment region (cosmetic — both resolve identically).

    Sorted alphabetically by label. "Default" is not in here — every picker
    prepends it as its own first option, so the list below is what follows it.
    ``_ENTRIES`` order is authoring order and reads as noise (Haiku 4.5, GPT,
    Sonnet 4.5, 4.6, 5, 4, Opus...); alphabetical is the order a reader can
    predict without knowing the catalog.

    The catalog itself is deliberately NOT re-sorted: its order is load-bearing,
    since ``model_pricing`` bills an unknown model at the FIRST
    ``cost_class="cheap"`` entry. Sorting here is free because pricing reads
    ``ModelCatalog().list()``, never this projection.

    This is a PROJECTION for pickers only. ``ModelCatalog.ids()`` /
    ``is_allowed()`` stay complete, so nothing this hides becomes invalid.
    """
    # Same lazy config import _normalize_geo_prefix uses, and the same
    # degrade-quietly contract: no config, no preference, just catalog order.
    try:
        from app.core.config import settings as _settings  # noqa: PLC0415

        region = _settings.AWS_REGION or ""
    except Exception:  # noqa: BLE001
        region = ""
    region_prefix = _REGION_TO_GEO_PREFIX.get(region, "")
    chosen: dict[str, ModelEntry] = {}
    for entry in ModelCatalog().list():
        key = normalize_model_id(entry.id)
        incumbent = chosen.get(key)
        if incumbent is None:
            chosen[key] = entry
        elif (
            region_prefix
            and entry.id.startswith(region_prefix)
            and not incumbent.id.startswith(region_prefix)
        ):
            chosen[key] = entry  # same slot, better prefix
    return sorted(chosen.values(), key=lambda e: e.label)
