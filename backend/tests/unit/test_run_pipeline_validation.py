"""Unit tests for ``allowed_custom_agent_ids`` and ``SUPPORTED_PIPELINE_TYPES``.

Regression guard for audit ticket **G1-C6** — mass-assignment via the
``run_pipeline`` ``agent_ids`` field. Before the fix, the WS handler accepted
ANY backend agent ID, letting a client resurrect dead pipelines or cross-inject
e.g. PPT agents into a User Stories run. See ``docs/_audit/TRIAGE.md`` for the
original write-up.

What we test here: the registry helper + loader constant that gate the WS
handler. The handler itself (``app/api/websocket.py`` ~940/1001) runs exactly
this predicate in production:

    if base_pipeline_type not in SUPPORTED_PIPELINE_TYPES: reject
    if agent_ids:
        allowed = allowed_custom_agent_ids(base_pipeline_type)
        rejected = [aid for aid in agent_ids if aid not in allowed]
        if rejected: reject with code=invalid_agent_ids

We drive that predicate directly here (the full WS plumbing is covered at the
integration layer — same split as ``test_agents_api_real_registry.py``).

SOURCE-OF-TRUTH NOTE (Phase 7a rewrite)
---------------------------------------
This file previously imported the LEGACY ``app.agents.registry`` (``AgentDefinition``,
the ``*_AGENTS`` lists, its ``allowed_custom_agent_ids``, ``QUESTIONNAIRE_AGENT``,
etc.). That module is dead pipeline-legacy removed in Phase 7a. The handler was
repointed (Phase 6) to the REAL single source of truth, and so is this test:

  * ``agents.registry.allowed_custom_agent_ids`` — the loader-backed helper the
    repointed ``websocket.py`` now imports.
  * ``agents.loader.SUPPORTED_PIPELINE_TYPES`` — the loader constant the handler
    now imports for the up-front type gate.

Expectations are the REAL ids (prototype → ``prototype-specify``/``plan``/``build``/
``validate``; ppt → the ``od-ppt-*`` agents) and the REAL, tightened ``custom``
pool (8 utility agents — NOT the legacy union-of-all). The four cases that used
to be red against the legacy helper (``custom`` = utility-pool-only; the
registry-derived allow-list) now PASS against the real (tight) helper — that is
the fix this rewrite locks in.

Coverage:

1. Each base pipeline (``user_stories``, ``ppt``, ``prototype``, ``app_builder``)
   has its defaults plus the full custom-utility pool in its allow-list — and
   nothing else.
2. Cross-pipeline injection (e.g. a user-stories agent into ``ppt``) is rejected.
3. Each revision pipeline (``*_revision``) allows only its own agents; custom
   utilities and base agents are NOT allowed.
4. ``custom`` allows only the custom-utility pool.
5. Unknown pipeline types — and the agentless ``reverse_engineer`` pipeline —
   return an empty allow-list (defence-in-depth: no agent_ids can be smuggled).
6. ``SUPPORTED_PIPELINE_TYPES`` is the loader's up-front gate; ``questionnaire``
   is NOT a valid run target, and ``reverse_engineer`` — though present as a
   (now empty) pipeline type — yields an empty allow-list so nothing is runnable.
7. The allow-list is DERIVED from the registry — adding a custom agent
   automatically widens the allow-list, no double-bookkeeping.
"""

from __future__ import annotations

import pytest

from agents.loader import SUPPORTED_PIPELINE_TYPES
from agents.registry import PIPELINE_AGENTS, allowed_custom_agent_ids

# The real custom-utility pool (the 8-agent "custom" pipeline) the UI exposes for
# injection into any base pipeline. Derived from the single source of truth.
_CUSTOM_POOL = set(PIPELINE_AGENTS["custom"])


# ---------------------------------------------------------------------------
# 1. Default pipelines (no agent_ids): the helper covers each base pipeline's
# defaults plus the custom-utility pool.
# ---------------------------------------------------------------------------


class TestBasePipelinesIncludeDefaultsPlusCustomPool:
    """For ``user_stories`` / ``ppt`` / ``prototype`` / ``app_builder``, the
    allow-list is exactly ``defaults ∪ custom pool`` — no extras leak in. The
    defaults come straight from the REAL ``PIPELINE_AGENTS``.
    """

    @pytest.mark.parametrize(
        "pipeline_type",
        ["user_stories", "ppt", "prototype", "app_builder"],
    )
    def test_each_base_pipeline_allows_defaults_plus_custom_pool(
        self, pipeline_type: str
    ) -> None:
        """The set returned must be exactly ``{default IDs} ∪ {custom IDs}``."""
        expected = set(PIPELINE_AGENTS[pipeline_type]) | _CUSTOM_POOL
        assert allowed_custom_agent_ids(pipeline_type) == expected

    def test_default_pipeline_agents_are_all_individually_allowed(self) -> None:
        """Every agent in the default PPT pipeline must be in PPT's allow-list.
        Sanity check that the simplest legitimate case — running the unmodified
        default pipeline — does not get rejected. The real PPT agents are the
        ``od-ppt-*`` set.
        """
        allowed = allowed_custom_agent_ids("ppt")
        for agent_id in PIPELINE_AGENTS["ppt"]:
            assert agent_id in allowed, f"Default PPT agent {agent_id!r} not allowed"
        # And the real ids are exactly the od-ppt agents (not the retired
        # ppt-code-generator/ppt-content-strategist the legacy registry had).
        assert {"od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"} <= allowed

    def test_prototype_defaults_are_the_real_spec_kit_ids(self) -> None:
        """The prototype allow-list carries the REAL Spec-Kit ids — NOT the
        retired ``prototype_v1`` ids (requirements-analyst/…) the stale legacy
        front-end used to send (the custom-prototype bug Phase 6 fixed)."""
        allowed = allowed_custom_agent_ids("prototype")
        assert {
            "prototype-specify",
            "prototype-plan",
            "prototype-build",
            "prototype-validate",
        } <= allowed
        retired = {
            "requirements-analyst",
            "html-prototype-builder",
            "prototype-polisher",
            "prototype-finalizer",
        }
        assert not (retired & allowed), f"retired prototype_v1 ids leaked: {retired & allowed}"


# ---------------------------------------------------------------------------
# 2. Cross-pipeline injection: the central case G1-C6 was filed for.
# ---------------------------------------------------------------------------


class TestCrossPipelineInjectionIsBlocked:
    """The original bug let a client run one pipeline with another pipeline's
    agents by smuggling agent IDs through ``agent_ids``. These tests verify the
    allow-list now blocks those combinations, using REAL agent ids.
    """

    def test_ppt_pipeline_rejects_user_stories_agent(self) -> None:
        """``domain-analyst`` is a User Stories agent — not allowed in PPT."""
        ppt_allowed = allowed_custom_agent_ids("ppt")
        assert "domain-analyst" not in ppt_allowed

    def test_user_stories_pipeline_rejects_ppt_agent(self) -> None:
        """And the inverse — ``od-ppt-composer`` not allowed in user_stories."""
        us_allowed = allowed_custom_agent_ids("user_stories")
        assert "od-ppt-composer" not in us_allowed

    def test_prototype_pipeline_rejects_app_builder_agent(self) -> None:
        """Cross-product: ``app-code-generator`` is an App Builder agent."""
        proto_allowed = allowed_custom_agent_ids("prototype")
        assert "app-code-generator" not in proto_allowed

    def test_app_builder_rejects_prototype_agent(self) -> None:
        """And the inverse: a prototype agent is not allowed in app_builder."""
        ab_allowed = allowed_custom_agent_ids("app_builder")
        assert "prototype-build" not in ab_allowed

    def test_base_pipelines_only_share_the_custom_pool(self) -> None:
        """Two base pipelines may only overlap on the shared custom-utility pool
        (never on each other's own agents). This is the structural invariant
        that makes cross-injection impossible: own-agents are disjoint.
        """
        bases = ["user_stories", "ppt", "prototype", "app_builder"]
        for i, a in enumerate(bases):
            own_a = set(PIPELINE_AGENTS[a])
            for b in bases[i + 1:]:
                own_b = set(PIPELINE_AGENTS[b])
                # The two pipelines' OWN agents never overlap.
                assert not (own_a & own_b), (
                    f"{a!r} and {b!r} share own-agents {own_a & own_b!r}"
                )
                # So neither pipeline's allow-list contains the OTHER's own agents.
                allowed_a = allowed_custom_agent_ids(a)
                assert not (own_b & allowed_a), (
                    f"{b!r} agents {own_b & allowed_a!r} leaked into {a!r}"
                )


# ---------------------------------------------------------------------------
# 3. Revision pipelines: tight allow-list (no custom-utility injection).
# ---------------------------------------------------------------------------


class TestRevisionPipelinesAreTight:
    """For ``*_revision`` types, the allow-list is exactly that revision
    pipeline's own agent IDs. Revision flows assume a fixed shape; injecting a
    market-research agent into a PPT revision would feed garbage context into the
    revision agent and would not produce a usable diff.
    """

    @pytest.mark.parametrize(
        "pipeline_type",
        [
            "ppt_revision",
            "user_stories_revision",
            "prototype_revision",
            "app_builder_revision",
            "od_ppt_revision",
        ],
    )
    def test_revision_pipeline_allows_only_its_own_agents(
        self, pipeline_type: str
    ) -> None:
        expected_ids = set(PIPELINE_AGENTS[pipeline_type])
        assert allowed_custom_agent_ids(pipeline_type) == expected_ids
        assert expected_ids, f"{pipeline_type!r} should have at least one agent"

    def test_ppt_revision_rejects_custom_utility_injection(self) -> None:
        """The audit specifically called out "no custom-agent injection on
        revisions" — verify ``market-research-agent`` and friends are not in the
        allow-list for a PPT revision run.
        """
        ppt_rev_allowed = allowed_custom_agent_ids("ppt_revision")
        for utility in _CUSTOM_POOL:
            assert utility not in ppt_rev_allowed, (
                f"Custom utility {utility!r} leaked into ppt_revision"
            )

    def test_ppt_revision_rejects_base_ppt_agents(self) -> None:
        """And it doesn't accidentally pick up the base PPT agents either —
        a PPT revision is a different pipeline from a fresh PPT run.
        """
        ppt_rev_allowed = allowed_custom_agent_ids("ppt_revision")
        for ppt_agent in PIPELINE_AGENTS["ppt"]:
            assert ppt_agent not in ppt_rev_allowed, (
                f"Base PPT agent {ppt_agent!r} leaked into ppt_revision"
            )


# ---------------------------------------------------------------------------
# 4. Custom pipeline: utility pool only (no defaults, since custom starts
# from an empty default list).
# ---------------------------------------------------------------------------


class TestCustomPipelineIsUtilityPoolOnly:
    """A ``custom`` run is assembled from the agent library by the user. Its
    allow-list is exactly the real custom-utility pool — no base-pipeline agents.

    (This is one of the four cases that was RED against the legacy helper, which
    returned the union of ALL agents for ``custom``. The real helper tightens it
    to the ``custom`` pipeline — this test now PASSES, locking in the fix.)
    """

    def test_custom_allows_full_custom_utility_pool(self) -> None:
        assert allowed_custom_agent_ids("custom") == _CUSTOM_POOL

    def test_custom_rejects_base_pipeline_agents(self) -> None:
        """A user composing a ``custom`` workflow cannot reach for base pipeline
        agents like ``od-ppt-composer`` — those run only inside their own
        pipeline.
        """
        custom_allowed = allowed_custom_agent_ids("custom")
        base_own = (
            set(PIPELINE_AGENTS["ppt"])
            | set(PIPELINE_AGENTS["user_stories"])
            | set(PIPELINE_AGENTS["prototype"])
            | set(PIPELINE_AGENTS["app_builder"])
        )
        leaked = base_own & custom_allowed
        assert not leaked, f"Base pipeline agents leaked into custom allow-list: {leaked}"


# ---------------------------------------------------------------------------
# 5. Unknown pipeline types + the agentless reverse_engineer pipeline:
# empty allow-list (defence in depth).
# ---------------------------------------------------------------------------


class TestUnknownPipelineTypeReturnsEmptySet:
    """Even if the up-front ``SUPPORTED_PIPELINE_TYPES`` check ever regressed,
    the helper's empty-set fallback is the second line of defence: no agent_ids
    could be smuggled through under an unknown — or agentless — type.
    """

    @pytest.mark.parametrize(
        "bogus",
        [
            "questionnaire",     # Synthetic, not a real run target.
            "totally_made_up",   # Unknown name.
            "",                  # Empty string.
            "PPT",               # Wrong case.
        ],
    )
    def test_unknown_pipeline_type_returns_empty_set(self, bogus: str) -> None:
        assert allowed_custom_agent_ids(bogus) == set()

    def test_reverse_engineer_returns_empty_set(self) -> None:
        """``reverse_engineer`` is a PRESENT-but-EMPTY pipeline (the UI removed
        it; the registry keeps the key with no agents). The helper returns ``∅``
        for it, so the "dead pipeline resurrection" case from the audit is
        blocked even though the type itself is still in the registry/loader.
        """
        assert PIPELINE_AGENTS["reverse_engineer"] == []
        assert allowed_custom_agent_ids("reverse_engineer") == set()

    def test_helper_returns_a_fresh_mutable_set(self) -> None:
        """Callers may mutate the result without corrupting PIPELINE_AGENTS."""
        a = allowed_custom_agent_ids("user_stories")
        a.add("__sentinel__")
        assert "__sentinel__" not in allowed_custom_agent_ids("user_stories")


# ---------------------------------------------------------------------------
# 6. SUPPORTED_PIPELINE_TYPES (the loader's up-front gate in the WS handler).
# ---------------------------------------------------------------------------


class TestSupportedPipelineTypes:
    """The handler rejects unsupported pipeline types early via the loader's
    ``SUPPORTED_PIPELINE_TYPES`` (``websocket.py:992``). These tests pin the
    contract so a future refactor that drops or adds a type has to consciously
    update this test.
    """

    def test_all_four_base_pipelines_are_supported(self) -> None:
        for base in ("user_stories", "ppt", "prototype", "app_builder"):
            assert base in SUPPORTED_PIPELINE_TYPES

    def test_all_revision_pipelines_are_supported(self) -> None:
        for rev in (
            "user_stories_revision", "ppt_revision",
            "prototype_revision", "app_builder_revision",
            "od_ppt_revision",
        ):
            assert rev in SUPPORTED_PIPELINE_TYPES

    def test_custom_is_supported(self) -> None:
        assert "custom" in SUPPORTED_PIPELINE_TYPES

    def test_questionnaire_is_NOT_supported(self) -> None:
        """The questionnaire flow uses ``_handle_questionnaire`` directly; it is
        never a valid ``run_pipeline.pipeline_type``."""
        assert "questionnaire" not in SUPPORTED_PIPELINE_TYPES

    def test_reverse_engineer_type_present_but_yields_no_runnable_agents(self) -> None:
        """``reverse_engineer`` is still a declared pipeline type in the loader
        (the AGENT.md scan / loader frozenset), so the up-front type gate alone
        does NOT reject it — but the SECOND gate (``allowed_custom_agent_ids``)
        returns ``∅`` and ``get_pipeline_agents`` returns ``[]``, so no
        reverse_engineer agent can actually run. The security property the audit
        cared about (no dead-pipeline resurrection) is preserved by the empty
        agent set, not by excluding the type. This documents the REAL posture
        (the legacy registry excluded it from its supported set instead).
        """
        assert "reverse_engineer" in SUPPORTED_PIPELINE_TYPES
        assert allowed_custom_agent_ids("reverse_engineer") == set()
        from agents.registry import get_pipeline_agents
        assert get_pipeline_agents("reverse_engineer") == []


# ---------------------------------------------------------------------------
# 7. Allow-list is derived from the registry (not hardcoded).
# ---------------------------------------------------------------------------


class TestAllowListDerivedFromRegistry:
    """Non-negotiable from the fix spec: adding/removing a custom utility agent
    must automatically update the allow-list. Otherwise we'd have two places to
    keep in sync — the kind of drift that causes the next G1-C6 in 6 months.

    The real helper derives the pool from ``PIPELINE_AGENTS["custom"]`` at call
    time, so we patch that binding (in ``agents.registry``, where the helper
    reads it) and verify the allow-list widens. (This is the second of the four
    formerly-red cases: the allow-list is registry-derived, not a hand-kept list.)
    """

    def test_adding_a_custom_agent_widens_each_base_pipeline_allow_list(
        self, monkeypatch
    ) -> None:
        import agents.registry as registry_mod

        synthetic = "test-only-synthetic-utility"
        patched = list(registry_mod.PIPELINE_AGENTS["custom"]) + [synthetic]
        # Patch only the "custom" entry on a COPY of the dict so we don't mutate
        # the real PIPELINE_AGENTS (which would leak into other tests).
        patched_map = dict(registry_mod.PIPELINE_AGENTS)
        patched_map["custom"] = patched
        monkeypatch.setattr(registry_mod, "PIPELINE_AGENTS", patched_map)

        # Every base pipeline's allow-list must now contain the synthetic.
        for base in ("user_stories", "ppt", "prototype", "app_builder", "custom"):
            allowed = allowed_custom_agent_ids(base)
            assert synthetic in allowed, (
                f"Synthetic agent did not propagate into {base!r} allow-list"
            )

        # Revision allow-lists must NOT pick up the synthetic — revisions are
        # tight by design (they don't fold in the custom pool).
        for rev in ("ppt_revision", "user_stories_revision",
                    "prototype_revision", "app_builder_revision"):
            allowed = allowed_custom_agent_ids(rev)
            assert synthetic not in allowed, (
                f"Synthetic agent leaked into revision pipeline {rev!r}"
            )


# ---------------------------------------------------------------------------
# Bonus: directly simulate the WS handler's check logic — the exact predicate
# ``websocket.py`` runs in production, executed against the real helper. Catches
# the "happy path" + "rejected path" branches without a full async WS stack.
# ---------------------------------------------------------------------------


class TestHandlerRejectionLogic:
    """Mirror the validation predicate the repointed WS handler runs
    (``app/api/websocket.py:1001-1013``):

        allowed = allowed_custom_agent_ids(base_pipeline_type)
        rejected = [aid for aid in agent_ids if aid not in allowed]
        if rejected: reject with code=invalid_agent_ids
    """

    def test_default_run_with_no_agent_ids_is_a_passthrough(self) -> None:
        """When ``agent_ids`` is empty/None the handler skips the allow-list
        check entirely (``if agent_ids:`` at websocket.py:1001). Documented as a
        contract: the helper returns a non-empty set for every base pipeline, so
        even if a future bug removed the guard, an empty input would be a no-op
        rejection rather than a silent failure.
        """
        for base in ("user_stories", "ppt", "prototype", "app_builder"):
            allowed = allowed_custom_agent_ids(base)
            assert allowed, f"Empty allow-list for {base!r}"
            rejected = [aid for aid in [] if aid not in allowed]
            assert rejected == []

    def test_valid_custom_set_passes_for_ppt(self) -> None:
        """The realistic happy-path the audit asked about: PPT pipeline + custom-
        utility injection. ``market-research-agent`` and ``swot-analyst`` are
        valid for PPT (custom pool), as is a real base-PPT agent.
        """
        agent_ids = ["market-research-agent", "swot-analyst", "od-ppt-composer"]
        allowed = allowed_custom_agent_ids("ppt")
        rejected = [aid for aid in agent_ids if aid not in allowed]
        assert rejected == [], f"Unexpected rejections: {rejected}"

    def test_cross_pipeline_injection_is_rejected_for_ppt(self) -> None:
        """A user-stories agent (``domain-analyst``) and a bogus reverse-engineer
        id must both fall out of a PPT pipeline's allow-list. This is the central
        test for the audit ticket.
        """
        agent_ids = [
            "od-ppt-brief-analyst",  # legit (real PPT agent)
            "domain-analyst",        # user_stories — REJECT
            "repo-scanner",          # nonexistent / reverse_engineer — REJECT
        ]
        allowed = allowed_custom_agent_ids("ppt")
        rejected = [aid for aid in agent_ids if aid not in allowed]
        assert rejected == ["domain-analyst", "repo-scanner"]

    def test_revision_pipeline_with_non_revision_agent_id_is_rejected(self) -> None:
        """``ppt_revision`` only allows its own agents. A user trying to smuggle a
        custom-utility or base-PPT agent through a revision run is rejected.
        """
        agent_ids = [
            "ppt-revision-agent",     # legit
            "market-research-agent",  # custom utility — REJECT on revision
            "od-ppt-composer",        # base PPT — REJECT on revision
        ]
        allowed = allowed_custom_agent_ids("ppt_revision")
        rejected = [aid for aid in agent_ids if aid not in allowed]
        assert rejected == ["market-research-agent", "od-ppt-composer"]

    def test_od_prototype_alias_resolves_and_accepts_real_prototype_ids(self) -> None:
        """The WS handler resolves ``od_prototype`` → ``prototype`` before the
        allow-list check; the real helper resolves the same alias internally. A
        real prototype id therefore passes under the alias.
        """
        allowed = allowed_custom_agent_ids("od_prototype")
        assert allowed == allowed_custom_agent_ids("prototype")
        rejected = [aid for aid in ["prototype-build"] if aid not in allowed]
        assert rejected == []

    def test_unknown_pipeline_type_rejects_every_agent_id(self) -> None:
        """When the pipeline type is unknown the helper returns an empty set so
        EVERY agent_id is rejected (the second line of defence behind the
        up-front ``SUPPORTED_PIPELINE_TYPES`` check).
        """
        allowed = allowed_custom_agent_ids("totally_bogus_pipeline")
        rejected = [aid for aid in ["any-agent-id", "another-id"]
                    if aid not in allowed]
        assert rejected == ["any-agent-id", "another-id"]


# ---------------------------------------------------------------------------
# 8. model_overrides ingress allow-list validation (Phase 6 D-07, MODEL-03).
# ---------------------------------------------------------------------------
#
# The security chokepoint: ``model_overrides`` is UNTRUSTED run-payload input
# crossing into model selection — the [HIGH] threat surface of Phase 6
# (T-06-06). The WS handler runs EXACTLY this predicate
# (``app/api/websocket.py::_validate_model_overrides``) at ingress, after the
# run's agent set is resolved and BEFORE ``engine.execute`` is called:
#
#     err = _validate_model_overrides(model_overrides, {spec.id for spec in agents})
#     if err is not None: reject with code="invalid_model_override"; no run.
#
# We drive that predicate directly here (same split as the agent_ids tests
# above — the full async WS stack is covered at the integration layer). The two
# allow-lists are authoritative: model ids come from the kernel-pure
# ``ModelCatalog`` (06-01, INV-12), agent ids from the resolved run agents.


class TestModelOverrideValidation:
    """Allow-list validation for the per-agent ``model_overrides`` map.

    Both reject-cases (unknown model id, unknown agent id) MUST fail fast with a
    non-None error so the handler emits ``invalid_model_override`` and starts no
    run — this is the phase's blocking security control (T-06-06 [HIGH] /
    T-06-07 [MED]). Never an arbitrary string (Q2 trust).
    """

    def _catalog_id(self) -> str:
        from agents.capabilities.model_catalog import ModelCatalog

        return ModelCatalog().ids()[0]

    def test_empty_map_is_valid_noop(self) -> None:
        """Absent / empty ``model_overrides`` (the only kind sent until Phase 8)
        passes validation — no error, the run proceeds unchanged (INV-3)."""
        from app.api.websocket import _validate_model_overrides

        assert _validate_model_overrides({}, {"agent-a", "agent-b"}) is None
        assert _validate_model_overrides(None or {}, set()) is None

    def test_valid_override_passes(self) -> None:
        """A ``{agent_id → catalog-model-id}`` where the agent is in the run and
        the model is in the catalog passes — reaches ``engine.execute``."""
        from app.api.websocket import _validate_model_overrides

        valid_model = self._catalog_id()
        run_agents = {"prototype-specify", "prototype-build"}
        err = _validate_model_overrides(
            {"prototype-build": valid_model}, run_agents
        )
        assert err is None, f"valid override unexpectedly rejected: {err}"

    def test_unknown_model_id_is_rejected(self) -> None:
        """T-06-06 [HIGH]: an arbitrary/unknown model id (not in the catalog)
        is rejected — the load-bearing mitigation. The error names the bad
        value so the emitted ``invalid_model_override`` event is actionable.
        """
        from app.api.websocket import _validate_model_overrides

        run_agents = {"prototype-build"}
        err = _validate_model_overrides(
            {"prototype-build": "evil.attacker/unknown-model:latest"}, run_agents
        )
        assert err is not None, "unknown model id MUST be rejected (T-06-06)"
        assert "evil.attacker/unknown-model:latest" in err

    def test_unknown_model_id_rejected_even_for_valid_agent(self) -> None:
        """The model-id allow-list is enforced independently of the agent check:
        a real run agent with a bogus model id is still rejected (no arbitrary
        string ever reaches build_model)."""
        from app.api.websocket import _validate_model_overrides

        err = _validate_model_overrides(
            {"prototype-build": "claude-totally-made-up"}, {"prototype-build"}
        )
        assert err is not None
        assert "claude-totally-made-up" in err

    def test_unknown_agent_id_is_rejected(self) -> None:
        """T-06-07 [MED]: an override targeting an agent NOT in this run's agent
        set is rejected (no silent no-op), even when the model id is a valid
        catalog id."""
        from app.api.websocket import _validate_model_overrides

        valid_model = self._catalog_id()
        run_agents = {"prototype-specify", "prototype-build"}
        err = _validate_model_overrides(
            {"not-in-this-run": valid_model}, run_agents
        )
        assert err is not None, "unknown agent id MUST be rejected (T-06-07)"
        assert "not-in-this-run" in err

    def test_first_violation_is_reported(self) -> None:
        """A map with multiple bad entries is rejected (fail-fast) — the handler
        only needs ONE error to reject the whole run before it starts."""
        from app.api.websocket import _validate_model_overrides

        err = _validate_model_overrides(
            {"ghost-agent": "ghost-model"}, {"prototype-build"}
        )
        assert err is not None

    # ── CR-01: malformed (non-dict / non-string) input is REJECTED, not crash ──
    # A truthy non-dict ``model_overrides`` (string, list) bypasses the ``or {}``
    # guard at the call sites. Before the fix it reached ``.items()`` / the set
    # membership check and raised AttributeError/TypeError, killing the asyncio
    # task SILENTLY (no error event, client hangs, _PIPELINE_TASKS leak). The
    # type guards must turn every malformed case into a rejection STRING so the
    # handler emits ``invalid_model_override`` and refuses the run.

    @pytest.mark.parametrize(
        "bad",
        [
            "evil_string",          # truthy str
            ["prototype-build"],    # truthy list
            42,                     # truthy int
            ("a", "b"),             # truthy tuple
        ],
    )
    def test_non_dict_overrides_are_rejected_not_raised(self, bad) -> None:
        """A truthy non-dict ``model_overrides`` returns a rejection string
        (does NOT raise) — closing the silent-task-death vector (CR-01)."""
        from app.api.websocket import _validate_model_overrides

        err = _validate_model_overrides(bad, {"prototype-build"})
        assert err is not None, f"non-dict {bad!r} MUST be rejected, not crash"
        assert "model_overrides" in err

    def test_non_string_value_is_rejected_not_raised(self) -> None:
        """A dict with a non-string value (e.g. a list) returns a rejection
        string instead of raising TypeError on the set membership check."""
        from app.api.websocket import _validate_model_overrides

        err = _validate_model_overrides(
            {"prototype-build": ["not", "a", "string"]}, {"prototype-build"}
        )
        assert err is not None, "non-string value MUST be rejected, not crash"
        assert "string" in err

    def test_non_string_key_is_rejected_not_raised(self) -> None:
        """A dict with a non-string key returns a rejection string rather than
        flowing a non-string agent id into the run-agent membership check."""
        from app.api.websocket import _validate_model_overrides

        err = _validate_model_overrides(
            {123: "some-model"}, {"prototype-build"}
        )
        assert err is not None, "non-string key MUST be rejected, not crash"
