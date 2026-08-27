"""tests/unit/test_model_resolver.py — ModelResolver precedence + chains + throttle (MODEL-01/02/05).

Wave-0 behavior tests for ``agents/model_policy.py``:

  * The 5-tier precedence (override > step.model > AgentSpec.model > workflow.model >
    session model_id or Haiku), with None tiers SKIPPED (an empty tier never blocks a
    lower one).
  * The parity-critical default (D-02 tier 5): with overrides={} and every manifest /
    agent tier None, ``resolve()`` returns ``session model_id or Haiku`` == today's exact
    ``build_model(model_id)`` input (INV-3).
  * ``ModelPolicy.max_tokens`` is documentation-only — the resolver must NOT thread it into
    any runtime cap.
  * Default tier-descent fallback chains (N11): empty ``ModelPolicy.fallback`` derives
    Opus→[Sonnet,Haiku], Sonnet→[Haiku], Haiku→[]; an explicit ``fallback`` overrides; every
    chain entry is catalog-valid.
  * Resolve-time AGENT.md ``model`` validation against the catalog (Q2 allow-list, T-06-03).
  * The co-located ``_is_transient_throttle`` predicate (D-06) classifies the throttle set;
    non-matching errors propagate (return False). Synthetic raises only — no live Bedrock.

Lightweight fakes for spec / step / ModelPolicy; no engine, no live provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agents.capabilities.model_catalog import ModelCatalog
from agents.model_policy import ModelResolver, _is_transient_throttle
from agents.workflows.plan import ModelPolicy

# ── Catalog ids (the single source — see model_catalog.py) ────────────────────────
HAIKU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET_45 = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
SONNET_46 = "eu.anthropic.claude-sonnet-4-6"
OPUS_45 = "eu.anthropic.claude-opus-4-5-20251101-v1:0"
OPUS_46 = "eu.anthropic.claude-opus-4-6-v1"


# ── Lightweight fakes ─────────────────────────────────────────────────────────────
@dataclass
class FakeSpec:
    """Stand-in for ``AgentSpec`` — only ``id`` + optional ``model`` matter to the resolver."""

    id: str
    model: str | None = None


@dataclass
class FakeStep:
    """Stand-in for the compiled ``Step`` — only ``model: ModelPolicy | None`` matters."""

    model: ModelPolicy | None = None


def _resolver(
    *,
    overrides: dict | None = None,
    workflow_model: ModelPolicy | None = None,
    session_model_id: str | None = None,
    haiku_default: str = HAIKU,
) -> ModelResolver:
    return ModelResolver(
        model_overrides=overrides or {},
        workflow_model=workflow_model,
        session_model_id=session_model_id,
        haiku_default=haiku_default,
        catalog=ModelCatalog(),
        # Pass an empty string to disable geo-prefix normalization in precedence
        # tests — they assert on the raw resolved value, not the region-swapped one.
        _region_override="",
    )


# ── Precedence (5 tiers + None-skip) ──────────────────────────────────────────────
def test_override_beats_step():
    """Tier 1: a user override wins over an explicit step.model."""
    r = _resolver(overrides={"agent-x": OPUS_45}, session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=SONNET_45)
    step = FakeStep(model=ModelPolicy(model=SONNET_46))
    assert r.resolve(spec, step) == OPUS_45


def test_step_beats_agent():
    """Tier 2: step.model wins over AgentSpec.model (no override)."""
    r = _resolver(session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=OPUS_45)
    step = FakeStep(model=ModelPolicy(model=SONNET_46))
    assert r.resolve(spec, step) == SONNET_46


def test_agent_beats_workflow():
    """Tier 3: AgentSpec.model wins over workflow.model (no override, no step.model)."""
    r = _resolver(workflow_model=ModelPolicy(model=SONNET_45), session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=OPUS_45)
    step = FakeStep(model=None)
    assert r.resolve(spec, step) == OPUS_45


def test_workflow_beats_global():
    """Tier 4: workflow.model wins over the session/global default (all higher None)."""
    r = _resolver(workflow_model=ModelPolicy(model=SONNET_46), session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=None)
    step = FakeStep(model=None)
    assert r.resolve(spec, step) == SONNET_46


def test_global_session_parity_default():
    """Tier 5a: every higher tier None → the session model_id (parity for a user-selected run)."""
    r = _resolver(session_model_id=SONNET_45)
    spec = FakeSpec(id="agent-x", model=None)
    assert r.resolve(spec, None) == SONNET_45


def test_global_haiku_parity_default():
    """Tier 5b: every tier None AND session None → the global Haiku default (today's exact path)."""
    r = _resolver(session_model_id=None, haiku_default=HAIKU)
    spec = FakeSpec(id="agent-x", model=None)
    # INV-3: with no overrides + no manifest model, resolve() == today's build_model(model_id) input.
    assert r.resolve(spec, None) == HAIKU


def test_none_tier_does_not_block_lower():
    """None-skipping: step.model None falls through to AgentSpec.model (empty tier never blocks)."""
    r = _resolver(session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=SONNET_45)
    step = FakeStep(model=None)  # tier 2 empty
    assert r.resolve(spec, step) == SONNET_45


def test_workflow_policy_with_none_model_is_skipped():
    """A workflow ModelPolicy whose .model is None is skipped (default-factory ModelPolicy today)."""
    r = _resolver(workflow_model=ModelPolicy(), session_model_id=HAIKU)  # .model == None
    spec = FakeSpec(id="agent-x", model=None)
    assert r.resolve(spec, None) == HAIKU


# ── max_tokens is documentation-only ──────────────────────────────────────────────
def test_max_tokens_is_doc_only():
    """A ModelPolicy.max_tokens does not change the resolved id and is not threaded as a cap."""
    r = _resolver(session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=None)
    step = FakeStep(model=ModelPolicy(model=SONNET_45, max_tokens=512))
    # The resolved id is unaffected by max_tokens …
    assert r.resolve(spec, step) == SONNET_45
    # … and the resolver exposes no runtime cap derived from the policy (cap stays
    # settings.MAX_OUTPUT_TOKENS in build_model).
    assert not hasattr(r, "max_tokens")
    assert not hasattr(r, "runtime_cap")


# ── Default tier-descent chains (N11) ─────────────────────────────────────────────
def test_default_chains():
    """Empty ModelPolicy.fallback derives the tier-descent chain by cost_class."""
    r = _resolver(session_model_id=HAIKU)
    # Opus → [Sonnet, Haiku] (premium descends to standard then cheap).
    opus_chain = r.chain_for(OPUS_45)
    assert opus_chain == [SONNET_45, HAIKU] or opus_chain == [SONNET_46, HAIKU]
    assert opus_chain[-1] == HAIKU and len(opus_chain) == 2
    # Sonnet → [Haiku].
    assert r.chain_for(SONNET_45) == [HAIKU]
    assert r.chain_for(SONNET_46) == [HAIKU]
    # Haiku → [] (nothing cheaper).
    assert r.chain_for(HAIKU) == []


def test_default_chain_entries_are_catalog_valid():
    """Every derived chain entry is a known, allowed catalog id."""
    r = _resolver(session_model_id=HAIKU)
    catalog = ModelCatalog()
    for model_id in (OPUS_45, OPUS_46, SONNET_45, SONNET_46, HAIKU):
        for entry in r.chain_for(model_id):
            assert catalog.is_allowed(entry), f"chain entry {entry} not catalog-valid"


def test_explicit_fallback_overrides_default():
    """An explicit ModelPolicy.fallback replaces the derived tier-descent default."""
    r = _resolver(session_model_id=HAIKU)
    policy = ModelPolicy(model=OPUS_45, fallback=[HAIKU])
    assert r.chain_for(OPUS_45, policy=policy) == [HAIKU]


def test_explicit_fallback_must_be_catalog_valid():
    """An explicit fallback with an unknown id is rejected (allow-list)."""
    r = _resolver(session_model_id=HAIKU)
    policy = ModelPolicy(model=OPUS_45, fallback=["not-a-real-model"])
    with pytest.raises(ValueError):
        r.chain_for(OPUS_45, policy=policy)


# ── Resolve-time AGENT.md model validation (T-06-03, Q2 allow-list) ───────────────
def test_resolve_rejects_unknown_agent_model():
    """An AgentSpec.model not in the catalog is rejected at resolve time (tier 3)."""
    r = _resolver(session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model="totally-bogus-model-id")
    with pytest.raises(ValueError):
        r.resolve(spec, None)


def test_resolve_accepts_known_agent_model():
    """A catalog-valid AgentSpec.model resolves cleanly (tier 3)."""
    r = _resolver(session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model=SONNET_45)
    assert r.resolve(spec, None) == SONNET_45


def test_invalid_agent_model_does_not_block_higher_override():
    """WR-01: an INVALID tier-3 AgentSpec.model must NOT pre-empt a valid tier-1
    override. The catalog check is deferred until tier 3 is the selected tier, so
    a higher-precedence override wins without raising."""
    r = _resolver(overrides={"agent-x": OPUS_45}, session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model="totally-bogus-model-id")
    assert r.resolve(spec, None) == OPUS_45


def test_invalid_agent_model_does_not_block_higher_step_model():
    """WR-01: same precedence guard for tier 2 — a valid step.model wins over an
    invalid AGENT.md model id (no ValueError, since tier 3 never gets selected)."""
    r = _resolver(session_model_id=HAIKU)
    spec = FakeSpec(id="agent-x", model="totally-bogus-model-id")
    step = FakeStep(model=ModelPolicy(model=SONNET_46))
    assert r.resolve(spec, step) == SONNET_46


# ── Throttle predicate (D-06) ─────────────────────────────────────────────────────
class _FakeClientError(Exception):
    """Synthetic botocore-shaped ClientError (no botocore import needed for the test)."""

    def __init__(self, code: str, status: int = 429):
        super().__init__(code)
        self.response = {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}


class ThrottlingException(Exception):
    """Synthetic Bedrock throttle by type-name."""


class RateLimitError(Exception):
    """Synthetic Anthropic 429 analogue by type-name."""


class ValidationException(Exception):
    """Synthetic non-transient (bad params) — must propagate."""


def test_throttle_predicate_true_for_bedrock_throttling_type():
    assert _is_transient_throttle(ThrottlingException("rate exceeded")) is True


def test_throttle_predicate_true_for_client_error_429():
    assert _is_transient_throttle(_FakeClientError("ThrottlingException", status=429)) is True


def test_throttle_predicate_true_for_client_error_5xx():
    assert _is_transient_throttle(_FakeClientError("ServiceUnavailableException", status=503)) is True
    assert _is_transient_throttle(_FakeClientError("InternalServerException", status=500)) is True


def test_throttle_predicate_true_for_anthropic_ratelimit():
    assert _is_transient_throttle(RateLimitError("429 too many requests")) is True


def test_throttle_predicate_true_for_overloaded_message():
    assert _is_transient_throttle(Exception("Error: model is overloaded (529)")) is True


def test_throttle_predicate_false_for_validation():
    assert _is_transient_throttle(ValidationException("invalid model id")) is False


def test_throttle_predicate_false_for_access_denied():
    assert _is_transient_throttle(_FakeClientError("AccessDeniedException", status=403)) is False


def test_throttle_predicate_false_for_generic_value_error():
    assert _is_transient_throttle(ValueError("nope")) is False


# ── GEO-01: geo-prefix normalization ─────────────────────────────────────────────
# Tests for _normalize_geo_prefix via ModelResolver with explicit _region_override.
# These use the _region_override parameter to simulate eu-central-1 and us-east-2
# without patching settings, keeping the tests hermetic.

from agents.model_policy import _normalize_geo_prefix  # noqa: E402


def test_normalize_swaps_us_to_eu_on_eu_region():
    """us. prefix → eu. prefix when AWS_REGION is eu-central-1."""
    result = _normalize_geo_prefix(
        "us.anthropic.claude-sonnet-5", _region_override="eu-central-1"
    )
    assert result == "eu.anthropic.claude-sonnet-5"


def test_normalize_swaps_eu_to_us_on_us_region():
    """eu. prefix → us. prefix when AWS_REGION is us-east-2."""
    result = _normalize_geo_prefix(
        "eu.anthropic.claude-sonnet-5", _region_override="us-east-2"
    )
    assert result == "us.anthropic.claude-sonnet-5"


def test_normalize_noop_when_already_correct():
    """eu. prefix on eu-central-1 is a no-op."""
    result = _normalize_geo_prefix(
        "eu.anthropic.claude-sonnet-5", _region_override="eu-central-1"
    )
    assert result == "eu.anthropic.claude-sonnet-5"


def test_normalize_noop_for_global_prefix():
    """global. prefix is never swapped — it routes anywhere by design."""
    result = _normalize_geo_prefix(
        "global.anthropic.claude-sonnet-5", _region_override="eu-central-1"
    )
    assert result == "global.anthropic.claude-sonnet-5"


def test_normalize_noop_for_no_geo_prefix():
    """A bare model id (no geo prefix) passes through unchanged."""
    result = _normalize_geo_prefix(
        "anthropic.claude-sonnet-5", _region_override="eu-central-1"
    )
    assert result == "anthropic.claude-sonnet-5"


def test_normalize_noop_for_unknown_region():
    """Unknown region — pass through so Bedrock can surface the real error."""
    result = _normalize_geo_prefix(
        "us.anthropic.claude-sonnet-5", _region_override="unknown-region-99"
    )
    assert result == "us.anthropic.claude-sonnet-5"


def test_normalize_noop_for_empty_region_override():
    """Empty string _region_override (used by test helpers) disables normalization."""
    result = _normalize_geo_prefix(
        "us.anthropic.claude-sonnet-5", _region_override=""
    )
    assert result == "us.anthropic.claude-sonnet-5"


def test_resolver_normalizes_agent_model_on_eu_region():
    """End-to-end: resolver with eu-central-1 override swaps us. → eu. for AGENT.md model."""
    r = ModelResolver(
        session_model_id=HAIKU,
        catalog=ModelCatalog(),
        _region_override="eu-central-1",
    )
    # AGENT.md declares us. prefix — should be normalized to eu. for EU deployment.
    spec = FakeSpec(id="prototype-validate", model="us.anthropic.claude-sonnet-5")
    assert r.resolve(spec, None) == "eu.anthropic.claude-sonnet-5"


def test_resolver_normalizes_agent_model_on_us_region():
    """End-to-end: resolver with us-east-2 override keeps us. prefix intact."""
    r = ModelResolver(
        session_model_id=HAIKU,
        catalog=ModelCatalog(),
        _region_override="us-east-2",
    )
    spec = FakeSpec(id="prototype-validate", model="us.anthropic.claude-sonnet-5")
    assert r.resolve(spec, None) == "us.anthropic.claude-sonnet-5"
