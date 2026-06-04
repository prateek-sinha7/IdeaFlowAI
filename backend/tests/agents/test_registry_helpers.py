"""Unit tests for the Phase-6 (6a) flat-list / by-id / allow-list helpers
added to the REAL ``agents.registry``.

Covers (per the Phase 6 plan, §5 T2 verify gate):
  (a) allow-list PARITY vs the legacy ``app.agents.registry`` for the pipelines
      that agree (user_stories, app_builder, and every *_revision).
  (b) the REAL prototype ids surface for ``prototype`` and ``od_ppt`` is
      NON-empty (the legacy ``od_ppt → ∅`` bug fix).
  (c) ``get_agent_by_id`` returns a spec for a real id and ``None`` for a bogus
      id.
  (d) ``get_all_agents_flat`` returns de-duplicated AgentSpecs covering the
      pipelines.

These exercise the REAL on-disk AGENT.md files under ``agents/prompts/``.
"""

from __future__ import annotations

import pytest

from agents.loader import AgentSpec
from agents.registry import (
    PIPELINE_AGENTS,
    REVISION_BASE_MAP,
    allowed_custom_agent_ids,
    get_agent_by_id,
    get_all_agents_flat,
)

# Legacy registry (the source we replicate for the agreeing pipelines).
from app.agents.registry import (
    allowed_custom_agent_ids as legacy_allowed_custom_agent_ids,
)


# Pipelines whose agent membership AGREES between the legacy and real
# registries (confirmed by survey): user_stories, app_builder, and every
# revision pipeline that exists in both. NOTE: prototype + ppt diverge (the
# whole reason for the reconciliation) and ``custom`` is deliberately tightened
# (real => the custom pool only; legacy => union of all agents), so none of
# those three are parity-tested here.
_AGREEING_REVISION_PIPELINES = sorted(REVISION_BASE_MAP.keys())  # excludes od_ppt_revision
_AGREEING_PIPELINES = ["user_stories", "app_builder", *_AGREEING_REVISION_PIPELINES]


# ---------------------------------------------------------------------------
# (a) Parity vs legacy for the agreeing pipelines
# ---------------------------------------------------------------------------


class TestAllowListLegacyParity:
    """For the pipelines that agree, YOUR allow-list must equal legacy's."""

    @pytest.mark.parametrize("pipeline_type", _AGREEING_PIPELINES)
    def test_allow_list_equals_legacy(self, pipeline_type: str):
        real = allowed_custom_agent_ids(pipeline_type)
        legacy = legacy_allowed_custom_agent_ids(pipeline_type)
        assert real == legacy, (
            f"allow-list mismatch for {pipeline_type!r}: "
            f"real-only={real - legacy}, legacy-only={legacy - real}"
        )
        assert real, f"expected a non-empty allow-list for {pipeline_type!r}"

    def test_revision_pipelines_are_tight(self):
        """A revision allow-list is exactly that revision pipeline's agents —
        no custom-utility agents folded in (the tight-revision contract)."""
        custom = set(PIPELINE_AGENTS["custom"])
        for rev in _AGREEING_REVISION_PIPELINES:
            allowed = allowed_custom_agent_ids(rev)
            assert allowed == set(PIPELINE_AGENTS[rev])
            assert not (allowed & custom) or set(PIPELINE_AGENTS[rev]) & custom, (
                f"revision {rev!r} unexpectedly includes custom-utility agents"
            )

    def test_base_pipelines_include_custom_pool(self):
        """A base pipeline allow-list = its own agents UNION the custom pool."""
        custom = set(PIPELINE_AGENTS["custom"])
        for base in ("user_stories", "app_builder"):
            allowed = allowed_custom_agent_ids(base)
            assert allowed == set(PIPELINE_AGENTS[base]) | custom


# ---------------------------------------------------------------------------
# (b) Real prototype ids + the od_ppt bug fix
# ---------------------------------------------------------------------------


class TestAllowListRealIdsAndOdFix:
    def test_prototype_contains_real_ids(self):
        """``prototype`` must allow the REAL Spec-Kit ids (not the retired
        prototype_v1 requirements-analyst/... that the legacy front-end sent)."""
        allowed = allowed_custom_agent_ids("prototype")
        real_ids = {
            "prototype-specify",
            "prototype-plan",
            "prototype-build",
            "prototype-validate",
        }
        assert real_ids <= allowed, f"missing real prototype ids: {real_ids - allowed}"
        # And the custom pool is folded in (prototype is a base pipeline).
        assert set(PIPELINE_AGENTS["custom"]) <= allowed
        # The retired prototype_v1 ids must NOT be present.
        retired = {"requirements-analyst", "html-prototype-builder", "prototype-polisher"}
        assert not (retired & allowed), f"retired ids leaked: {retired & allowed}"

    def test_od_prototype_resolves_to_prototype(self):
        """The od_prototype alias (not a registry key) resolves to prototype."""
        assert allowed_custom_agent_ids("od_prototype") == allowed_custom_agent_ids(
            "prototype"
        )

    def test_od_ppt_is_non_empty_bug_fix(self):
        """The legacy ``od_ppt → ∅`` bug rejected every od_ppt custom run.
        The fix treats od_ppt as a base pipeline: own agents ∪ custom pool."""
        allowed = allowed_custom_agent_ids("od_ppt")
        assert allowed, "od_ppt allow-list must be non-empty (bug fix)"
        assert allowed == set(PIPELINE_AGENTS["od_ppt"]) | set(PIPELINE_AGENTS["custom"])
        # Legacy returned empty — prove we diverge in the intended direction.
        assert allowed != legacy_allowed_custom_agent_ids("od_ppt")
        assert legacy_allowed_custom_agent_ids("od_ppt") == set()

    def test_od_ppt_revision_is_tight(self):
        """od_ppt_revision is a revision (not in REVISION_BASE_MAP, caught by the
        *_revision suffix): its own agents only, no custom pool."""
        allowed = allowed_custom_agent_ids("od_ppt_revision")
        assert allowed == set(PIPELINE_AGENTS["od_ppt_revision"])
        assert allowed  # od_ppt_revision has one agent
        assert not (allowed & set(PIPELINE_AGENTS["custom"]))

    def test_custom_is_the_custom_pool(self):
        assert allowed_custom_agent_ids("custom") == set(PIPELINE_AGENTS["custom"])

    def test_unknown_and_empty_pipelines_return_empty(self):
        # Unknown type → security fallback.
        assert allowed_custom_agent_ids("definitely_not_a_pipeline") == set()
        assert allowed_custom_agent_ids("") == set()
        # reverse_engineer is a present-but-EMPTY pipeline → also ∅ (matches the
        # legacy security posture; an agentless pipeline allows nothing).
        assert PIPELINE_AGENTS["reverse_engineer"] == []
        assert allowed_custom_agent_ids("reverse_engineer") == set()

    def test_returns_a_fresh_mutable_set(self):
        """Callers may mutate the result without corrupting PIPELINE_AGENTS."""
        a = allowed_custom_agent_ids("user_stories")
        a.add("__sentinel__")
        assert "__sentinel__" not in allowed_custom_agent_ids("user_stories")


# ---------------------------------------------------------------------------
# (c) get_agent_by_id
# ---------------------------------------------------------------------------


class TestGetAgentById:
    def test_real_id_returns_spec(self):
        spec = get_agent_by_id("prototype-specify")
        assert isinstance(spec, AgentSpec)
        assert spec.id == "prototype-specify"

    def test_bogus_id_returns_none(self):
        assert get_agent_by_id("no-such-agent-xyz") is None

    def test_empty_id_returns_none(self):
        assert get_agent_by_id("") is None


# ---------------------------------------------------------------------------
# (d) get_all_agents_flat
# ---------------------------------------------------------------------------


class TestGetAllAgentsFlat:
    def test_returns_agent_specs(self):
        flat = get_all_agents_flat()
        assert flat, "flat agent list must be non-empty"
        assert all(isinstance(s, AgentSpec) for s in flat)

    def test_deduplicated_by_id(self):
        """od-ppt agents live in BOTH ``ppt`` and ``od_ppt`` — the flat list
        must contain each id exactly once."""
        flat = get_all_agents_flat()
        ids = [s.id for s in flat]
        assert len(ids) == len(set(ids)), "flat list contains duplicate ids"
        # The shared od-ppt ids appear exactly once each.
        for shared in ("od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"):
            assert ids.count(shared) == 1

    def test_covers_loadable_pipeline_agents(self):
        """Every id in PIPELINE_AGENTS that actually loads must appear once in
        the flat list (the flat list spans ALL pipelines)."""
        flat_ids = {s.id for s in get_all_agents_flat()}
        expected: set[str] = set()
        for ids in PIPELINE_AGENTS.values():
            for aid in ids:
                if get_agent_by_id(aid) is not None:  # loadable on disk
                    expected.add(aid)
        assert expected <= flat_ids, f"flat list missing ids: {expected - flat_ids}"
        # And it introduces no ids that aren't declared in any pipeline.
        all_declared = {aid for ids in PIPELINE_AGENTS.values() for aid in ids}
        assert flat_ids <= all_declared, (
            f"flat list has undeclared ids: {flat_ids - all_declared}"
        )

    def test_stable_order(self):
        """The flat ordering is deterministic across calls."""
        assert [s.id for s in get_all_agents_flat()] == [
            s.id for s in get_all_agents_flat()
        ]
