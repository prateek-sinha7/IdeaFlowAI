"""Unit tests for ``allowed_custom_agent_ids`` and ``SUPPORTED_PIPELINE_TYPES``.

Regression guard for audit ticket **G1-C6** — mass-assignment via the
``run_pipeline`` ``agent_ids`` field. Before the fix, the WS handler accepted
ANY backend agent ID (including the deprecated ``reverse_engineer`` agents
and synthetic agents like ``QUESTIONNAIRE_AGENT``), letting a client
resurrect dead pipelines or cross-inject e.g. PPT agents into a User Stories
run. See ``docs/_audit/TRIAGE.md`` for the original write-up.

What we test here: the registry helper that gates the WS handler. The
handler itself is exercised end-to-end by manual smoke + the integration
suite; for unit-level coverage we drive the helper directly. This matches
the testing strategy already established in
``tests/unit/test_orchestrator_skill_resolution.py`` — keep WS-coupled
behaviour at the integration layer, keep registry/policy decisions at the
unit layer.

Coverage:

1. Each base pipeline (``user_stories``, ``ppt``, ``prototype``,
   ``app_builder``) has its defaults plus the full custom-utility pool in
   its allow-list — and nothing else.
2. Cross-pipeline injection (e.g. ``repo-scanner`` into ``ppt``) is rejected.
3. Each revision pipeline (``*_revision``) allows only its own agents;
   custom utilities and base agents are NOT allowed.
4. ``custom`` allows only the custom-utility pool.
5. Unknown pipeline types return an empty allow-list (defence-in-depth).
6. ``SUPPORTED_PIPELINE_TYPES`` is what the WS handler will accept up-front,
   and notably excludes ``reverse_engineer`` and ``questionnaire``.
7. The allow-list is derived from the registry — adding a custom agent
   automatically widens the allow-list, no double-bookkeeping.
"""

from __future__ import annotations

import pytest

from app.agents.registry import (
    APP_BUILDER_AGENTS,
    APP_BUILDER_REVISION_AGENTS,
    CUSTOM_AGENTS,  # re-exported from app.agents.custom_agents at registry.py:1234
    PPT_AGENTS,
    PPT_REVISION_AGENTS,
    PROTOTYPE_AGENTS,
    PROTOTYPE_REVISION_AGENTS,
    REVERSE_ENGINEER_AGENTS,
    SUPPORTED_PIPELINE_TYPES,
    USER_STORY_AGENTS,
    USER_STORY_REVISION_AGENTS,
    QUESTIONNAIRE_AGENT,
    allowed_custom_agent_ids,
)


# ---------------------------------------------------------------------------
# 1. Default pipelines (no agent_ids): the helper covers each base pipeline's
# defaults plus the custom-utility pool.
# ---------------------------------------------------------------------------


class TestBasePipelinesIncludeDefaultsPlusCustomPool:
    """For ``user_stories`` / ``ppt`` / ``prototype`` / ``app_builder``, the
    allow-list is exactly ``defaults ∪ CUSTOM_AGENTS`` — no extras leak in.
    """

    @pytest.mark.parametrize(
        "pipeline_type, defaults",
        [
            ("user_stories", USER_STORY_AGENTS),
            ("ppt", PPT_AGENTS),
            ("prototype", PROTOTYPE_AGENTS),
            ("app_builder", APP_BUILDER_AGENTS),
        ],
    )
    def test_each_base_pipeline_allows_defaults_plus_custom_pool(
        self, pipeline_type: str, defaults
    ) -> None:
        """The set returned must be exactly ``{default IDs} ∪ {custom IDs}``."""
        expected = {a.id for a in defaults} | {a.id for a in CUSTOM_AGENTS}
        assert allowed_custom_agent_ids(pipeline_type) == expected

    def test_default_pipeline_agents_are_all_individually_allowed(self) -> None:
        """Every agent in the default PPT pipeline must be in PPT's
        allow-list. Sanity check that the simplest legitimate case — running
        the unmodified default pipeline — does not get rejected.
        """
        allowed = allowed_custom_agent_ids("ppt")
        for agent in PPT_AGENTS:
            assert agent.id in allowed, f"Default PPT agent {agent.id!r} not allowed"


# ---------------------------------------------------------------------------
# 2. Cross-pipeline injection: the central case G1-C6 was filed for.
# ---------------------------------------------------------------------------


class TestCrossPipelineInjectionIsBlocked:
    """The original bug let a client run a PPT pipeline with User Stories
    agents (or vice-versa) by smuggling agent IDs through ``agent_ids``.
    These tests verify the allow-list now blocks those combinations.
    """

    def test_ppt_pipeline_rejects_user_stories_agent(self) -> None:
        """``domain-analyst`` is a User Stories agent — not allowed in PPT."""
        ppt_allowed = allowed_custom_agent_ids("ppt")
        assert "domain-analyst" not in ppt_allowed

    def test_user_stories_pipeline_rejects_ppt_agent(self) -> None:
        """And the inverse — ``ppt-code-generator`` not allowed in user_stories."""
        us_allowed = allowed_custom_agent_ids("user_stories")
        assert "ppt-code-generator" not in us_allowed

    def test_prototype_pipeline_rejects_app_builder_agent(self) -> None:
        """Cross-product: ``app-code-generator`` is an App Builder agent."""
        proto_allowed = allowed_custom_agent_ids("prototype")
        assert "app-code-generator" not in proto_allowed

    def test_reverse_engineer_agents_blocked_in_every_base_pipeline(self) -> None:
        """All 4 reverse_engineer agents (deprecated, UI removed) must be
        blocked in every base pipeline — this is the "dead pipeline
        resurrection" case from the audit.
        """
        re_ids = [a.id for a in REVERSE_ENGINEER_AGENTS]
        # Sanity: the registry still has these (Group 3 cleanup is deferred).
        assert {"repo-scanner", "deep-analyzer", "modernization-planner",
                "documentation-generator"} <= set(re_ids)

        for base in ("user_stories", "ppt", "prototype", "app_builder", "custom"):
            allowed = allowed_custom_agent_ids(base)
            for re_id in re_ids:
                assert re_id not in allowed, (
                    f"Reverse-engineer agent {re_id!r} leaked into {base!r}"
                )

    def test_questionnaire_agent_blocked_everywhere(self) -> None:
        """The synthetic ``QUESTIONNAIRE_AGENT`` exists only for
        ``_handle_questionnaire`` and must never be runnable as a pipeline
        agent. The registry's ``get_agent_by_id`` doesn't return it (it's not
        in ``ALL_AGENTS``) but a forged ID-only payload could attempt this.
        """
        for base in ("user_stories", "ppt", "prototype", "app_builder",
                     "custom", "ppt_revision", "user_stories_revision",
                     "prototype_revision", "app_builder_revision"):
            allowed = allowed_custom_agent_ids(base)
            assert QUESTIONNAIRE_AGENT.id not in allowed, (
                f"QUESTIONNAIRE_AGENT leaked into {base!r}"
            )


# ---------------------------------------------------------------------------
# 3. Revision pipelines: tight allow-list (no custom-utility injection).
# ---------------------------------------------------------------------------


class TestRevisionPipelinesAreTight:
    """For ``*_revision`` types, the allow-list is exactly that revision
    pipeline's own agent IDs. Revision flows assume a fixed shape; injecting
    e.g. a market-research agent into a PPT revision would feed garbage
    context into the revision agent and would not produce a usable diff.
    """

    @pytest.mark.parametrize(
        "pipeline_type, expected_agents",
        [
            ("ppt_revision", PPT_REVISION_AGENTS),
            ("user_stories_revision", USER_STORY_REVISION_AGENTS),
            ("prototype_revision", PROTOTYPE_REVISION_AGENTS),
            ("app_builder_revision", APP_BUILDER_REVISION_AGENTS),
        ],
    )
    def test_revision_pipeline_allows_only_its_own_agents(
        self, pipeline_type: str, expected_agents
    ) -> None:
        expected_ids = {a.id for a in expected_agents}
        assert allowed_custom_agent_ids(pipeline_type) == expected_ids

    def test_ppt_revision_rejects_custom_utility_injection(self) -> None:
        """The audit specifically called out "no custom-agent injection on
        revisions" — we verify that ``market-research-agent`` and friends
        are not in the allow-list for a PPT revision run.
        """
        ppt_rev_allowed = allowed_custom_agent_ids("ppt_revision")
        for utility in CUSTOM_AGENTS:
            assert utility.id not in ppt_rev_allowed, (
                f"Custom utility {utility.id!r} leaked into ppt_revision"
            )

    def test_ppt_revision_rejects_base_ppt_agents(self) -> None:
        """And it doesn't accidentally pick up the base PPT agents either —
        a PPT revision is a different pipeline from a fresh PPT run.
        """
        ppt_rev_allowed = allowed_custom_agent_ids("ppt_revision")
        for ppt_agent in PPT_AGENTS:
            assert ppt_agent.id not in ppt_rev_allowed, (
                f"Base PPT agent {ppt_agent.id!r} leaked into ppt_revision"
            )


# ---------------------------------------------------------------------------
# 4. Custom pipeline: utility pool only (no defaults, since custom starts
# from an empty default list).
# ---------------------------------------------------------------------------


class TestCustomPipelineIsUtilityPoolOnly:
    """A ``custom`` run starts from an empty default list and is assembled
    from the agent library by the user. Its allow-list is exactly the
    ``CUSTOM_AGENTS`` pool — no base-pipeline agents.
    """

    def test_custom_allows_full_custom_utility_pool(self) -> None:
        custom_allowed = allowed_custom_agent_ids("custom")
        expected = {a.id for a in CUSTOM_AGENTS}
        assert custom_allowed == expected

    def test_custom_rejects_base_pipeline_agents(self) -> None:
        """A user composing a ``custom`` workflow cannot reach for base
        pipeline agents like ``ppt-code-generator`` — those run only inside
        their own pipeline.
        """
        custom_allowed = allowed_custom_agent_ids("custom")
        for agent in PPT_AGENTS + USER_STORY_AGENTS + PROTOTYPE_AGENTS + APP_BUILDER_AGENTS:
            assert agent.id not in custom_allowed, (
                f"Base pipeline agent {agent.id!r} leaked into custom allow-list"
            )


# ---------------------------------------------------------------------------
# 5. Unknown pipeline types: empty allow-list (defence in depth).
# ---------------------------------------------------------------------------


class TestUnknownPipelineTypeReturnsEmptySet:
    """The WS handler also rejects unknown pipeline types up-front via
    ``SUPPORTED_PIPELINE_TYPES``. The helper's empty-set fallback is the
    second line of defence: even if the up-front check ever regressed, no
    agent_ids could be smuggled through under an unknown type.
    """

    @pytest.mark.parametrize(
        "bogus",
        [
            "reverse_engineer",  # The deprecated pipeline — registry still
                                 # has agents but the helper shouldn't reach
                                 # for them via this function.
            "questionnaire",     # Synthetic, not a real run target.
            "totally_made_up",   # Unknown name.
            "",                  # Empty string.
            "PPT",               # Wrong case.
        ],
    )
    def test_unknown_pipeline_type_returns_empty_set(self, bogus: str) -> None:
        assert allowed_custom_agent_ids(bogus) == set()


# ---------------------------------------------------------------------------
# 6. SUPPORTED_PIPELINE_TYPES (the up-front gate in the WS handler).
# ---------------------------------------------------------------------------


class TestSupportedPipelineTypes:
    """The handler now rejects unsupported pipeline types early. These tests
    pin the supported list so a future refactor that drops or adds a type
    has to consciously update this test.
    """

    def test_all_four_base_pipelines_are_supported(self) -> None:
        for base in ("user_stories", "ppt", "prototype", "app_builder"):
            assert base in SUPPORTED_PIPELINE_TYPES

    def test_all_four_revision_pipelines_are_supported(self) -> None:
        for rev in (
            "user_stories_revision", "ppt_revision",
            "prototype_revision", "app_builder_revision",
        ):
            assert rev in SUPPORTED_PIPELINE_TYPES

    def test_custom_is_supported(self) -> None:
        assert "custom" in SUPPORTED_PIPELINE_TYPES

    def test_reverse_engineer_is_NOT_supported(self) -> None:
        """The UI removed reverse_engineer in commit 047fb43; the backend
        registry still has agents for it but the run_pipeline path must
        refuse to dispatch one. Until Group 3 cleanup lands, this is the
        load-bearing check.
        """
        assert "reverse_engineer" not in SUPPORTED_PIPELINE_TYPES

    def test_questionnaire_is_NOT_supported(self) -> None:
        """The questionnaire flow uses ``_handle_questionnaire`` directly;
        it is never a valid ``run_pipeline.pipeline_type``."""
        assert "questionnaire" not in SUPPORTED_PIPELINE_TYPES


# ---------------------------------------------------------------------------
# 7. Allow-list is derived from the registry (not hardcoded).
# ---------------------------------------------------------------------------


class TestAllowListDerivedFromRegistry:
    """Non-negotiable from the fix spec: adding/removing a custom utility
    agent must automatically update the allow-list. Otherwise we'd have
    two places to keep in sync — the kind of drift that causes the next
    G1-C6 in 6 months.

    We test this by temporarily appending a synthetic agent to
    ``CUSTOM_AGENTS`` (via ``monkeypatch`` on the *registry's* binding,
    since the helper does ``CUSTOM_AGENTS`` lookup via the module-level
    import in registry.py) and verifying the allow-list now contains it.
    """

    def test_adding_a_custom_agent_widens_each_base_pipeline_allow_list(
        self, monkeypatch
    ) -> None:
        """We patch the ``CUSTOM_AGENTS`` binding that lives inside
        ``app.agents.registry`` (where the helper looks it up) rather than
        the one in ``app.agents.custom_agents``. They start as the same list
        object but Python's import semantics mean the helper sees the
        registry-module binding, not the source-module one.
        """
        from app.agents.registry import AgentDefinition
        import app.agents.registry as registry_mod

        synthetic = AgentDefinition(
            id="test-only-synthetic-utility",
            name="Test Synthetic",
            role="Test",
            description="synthetic agent used only by tests",
            icon="bug",
            order=99,
            pipeline_type="custom",
            estimated_duration=1.0,
            max_tokens=100,
            system_prompt="x" * 80,  # long enough to satisfy any min-length check
        )

        # Construct the patched list explicitly so we don't mutate the
        # real CUSTOM_AGENTS (which would leak into other tests).
        patched = list(registry_mod.CUSTOM_AGENTS) + [synthetic]
        monkeypatch.setattr(registry_mod, "CUSTOM_AGENTS", patched)

        # Every base pipeline's allow-list must now contain the synthetic.
        for base in ("user_stories", "ppt", "prototype", "app_builder", "custom"):
            allowed = allowed_custom_agent_ids(base)
            assert synthetic.id in allowed, (
                f"Synthetic agent did not propagate into {base!r} allow-list"
            )

        # Revision allow-lists must NOT pick up the synthetic — revisions
        # are tight by design.
        for rev in ("ppt_revision", "user_stories_revision",
                    "prototype_revision", "app_builder_revision"):
            allowed = allowed_custom_agent_ids(rev)
            assert synthetic.id not in allowed, (
                f"Synthetic agent leaked into revision pipeline {rev!r}"
            )


# ---------------------------------------------------------------------------
# Bonus: directly simulate the WS handler's check logic — the same boolean
# the WS handler runs in production, executed against the helper. This
# catches the "happy path" + "rejected path" branches the handler exercises,
# without standing up a full async WS stack.
# ---------------------------------------------------------------------------


class TestHandlerRejectionLogic:
    """Mirror the validation predicate the WS handler runs:

        allowed = allowed_custom_agent_ids(pipeline_type)
        rejected = [aid for aid in agent_ids if aid not in allowed]
        if rejected: reject with code=invalid_agent_ids

    We exercise that predicate directly here. The full WS plumbing
    (send_json, the receive loop, etc.) is covered at integration level.
    """

    def test_default_run_with_no_agent_ids_is_a_passthrough(self) -> None:
        """When ``agent_ids`` is empty or None, the handler skips the
        allow-list check entirely (see ``if agent_ids:`` in websocket.py).
        Documented as a contract: the helper returns a non-empty set for
        every supported base pipeline, so even if a future bug removed
        the ``if agent_ids:`` guard, the empty input would be a no-op
        rejection rather than a silent failure.
        """
        for base in ("user_stories", "ppt", "prototype", "app_builder"):
            allowed = allowed_custom_agent_ids(base)
            assert allowed, f"Empty allow-list for {base!r}"
            # rejected_count for an empty input is 0:
            rejected = [aid for aid in [] if aid not in allowed]
            assert rejected == []

    def test_valid_custom_set_passes_for_ppt(self) -> None:
        """The realistic happy-path the audit asked about: PPT pipeline +
        custom-utility injection. ``market-research-agent`` and
        ``swot-analyst`` are valid for PPT (they're in CUSTOM_AGENTS and
        PPT is a base pipeline).
        """
        agent_ids = [
            "market-research-agent", "swot-analyst", "ppt-code-generator",
        ]
        allowed = allowed_custom_agent_ids("ppt")
        rejected = [aid for aid in agent_ids if aid not in allowed]
        assert rejected == [], f"Unexpected rejections: {rejected}"

    def test_cross_pipeline_injection_is_rejected_for_ppt(self) -> None:
        """``repo-scanner`` (reverse_engineer) and ``domain-analyst``
        (user_stories) must both fall out of a PPT pipeline's allow-list.
        This is the central test for the audit ticket.
        """
        agent_ids = [
            "ppt-content-strategist",  # legit
            "repo-scanner",            # reverse_engineer — REJECT
            "domain-analyst",          # user_stories — REJECT
        ]
        allowed = allowed_custom_agent_ids("ppt")
        rejected = [aid for aid in agent_ids if aid not in allowed]
        assert rejected == ["repo-scanner", "domain-analyst"]

    def test_revision_pipeline_with_non_revision_agent_id_is_rejected(self) -> None:
        """``ppt_revision`` only allows its own agents. A user trying to
        smuggle a custom-utility or base-PPT agent through a revision run
        is rejected.
        """
        agent_ids = [
            "ppt-revision-agent",    # legit
            "market-research-agent", # custom utility — REJECT on revision
            "ppt-code-generator",    # base PPT — REJECT on revision
        ]
        allowed = allowed_custom_agent_ids("ppt_revision")
        rejected = [aid for aid in agent_ids if aid not in allowed]
        assert rejected == ["market-research-agent", "ppt-code-generator"]

    def test_unknown_pipeline_type_rejects_every_agent_id(self) -> None:
        """When the pipeline type is unknown, the helper returns an empty
        set so EVERY agent_id is rejected. (The WS handler's up-front
        ``SUPPORTED_PIPELINE_TYPES`` check should catch unknown types
        before we get here, but this is the second line of defence.)
        """
        allowed = allowed_custom_agent_ids("totally_bogus_pipeline")
        rejected = [aid for aid in ["any-agent-id", "another-id"]
                    if aid not in allowed]
        assert rejected == ["any-agent-id", "another-id"]
