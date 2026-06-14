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

from agents.capabilities.model_catalog import ModelCatalog
from agents.workflows.plan import ModelPolicy

# ---------------------------------------------------------------------------
# Cost-class tier ordering (canonical, from the catalog ``cost_class`` field).
# Tier-descent walks from the model's own class down to the cheapest, picking
# one catalog id per lower class (D-05 / N11). premium > standard > cheap.
# ---------------------------------------------------------------------------
_COST_CLASS_ORDER: tuple[str, ...] = ("premium", "standard", "cheap")


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
    ) -> None:
        self._overrides: dict[str, str] = dict(model_overrides or {})
        self._workflow_model = workflow_model
        self._session_model_id = session_model_id
        self._haiku_default = haiku_default
        self._catalog = catalog or ModelCatalog()
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
        override = self._overrides.get(getattr(spec, "id", None))           # 1 override
        step_model = step.model.model if step is not None and step.model else None  # 2

        resolved = (
            override
            or step_model
            or agent_model                                                  # 3 AgentSpec.model
            or (self._workflow_model.model if self._workflow_model else None)   # 4 workflow.model
            or self._session_model_id                                       # 5a session model_id
            or self._haiku_default                                          # 5b global Haiku
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
        return resolved

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
        for cost_class in _COST_CLASS_ORDER[start + 1:]:
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
# the unit test import ONE predicate. Defensive, layered: type-name OR
# HTTP-status OR error-code / message substring. Non-matching → False (re-raise).
# ---------------------------------------------------------------------------

# Bedrock / botocore transient ClientError codes (prod, ChatBedrockConverse).
_TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelTimeoutException",
        "ServiceQuotaExceededException",
    }
)
# Transient HTTP statuses: 429 throttle, 503 ServiceUnavailable, 500 InternalServer,
# 529 Anthropic overloaded.
_TRANSIENT_STATUS: frozenset[int] = frozenset({429, 500, 503, 529})
# Type-name / message substrings (langchain-aws / langchain-anthropic may wrap the
# underlying exception; match defensively on the stringified form too).
_TRANSIENT_SUBSTRINGS: tuple[str, ...] = (
    "throttl",            # ThrottlingException / "Throttling"
    "too many requests",
    "ratelimit",          # anthropic.RateLimitError
    "rate limit",
    "serviceunavailable",
    "service unavailable",
    "overloaded",         # anthropic 529 overloaded_error
    "modeltimeout",
    "servicequotaexceeded",
)


def _is_transient_throttle(exc: BaseException) -> bool:
    """Return ``True`` iff ``exc`` is a transient throttle / overload worth a model switch.

    Layered, defensive classifier (the exact wrapped type depends on langchain-aws /
    langchain-anthropic internals — A2):

      1. botocore-shaped ``ClientError``: ``exc.response["Error"]["Code"]`` ∈ the transient
         set, OR ``ResponseMetadata.HTTPStatusCode`` ∈ the transient statuses.
      2. A ``status_code`` / ``http_status`` attribute ∈ the transient statuses (Anthropic
         clients expose this).
      3. The exception type name OR its stringified message contains a known transient
         substring (``Throttling`` / ``RateLimit`` / ``overloaded`` / …).

    Non-matching errors (``ValidationException``, ``AccessDeniedException``, generic
    ``ValueError``, ``ModelConfigurationError``) return ``False`` so the caller re-raises and
    does NOT switch models.
    """
    # 1. botocore-shaped ClientError (response dict).
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if isinstance(code, str) and code in _TRANSIENT_ERROR_CODES:
            return True
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(status, int) and status in _TRANSIENT_STATUS:
            return True

    # 2. Explicit status attribute (Anthropic-style clients).
    for attr in ("status_code", "http_status"):
        status_attr = getattr(exc, attr, None)
        if isinstance(status_attr, int) and status_attr in _TRANSIENT_STATUS:
            return True

    # 3. Type-name / message substring (defensive — covers wrapped exceptions).
    haystack = f"{type(exc).__name__} {exc}".lower()
    return any(token in haystack for token in _TRANSIENT_SUBSTRINGS)
