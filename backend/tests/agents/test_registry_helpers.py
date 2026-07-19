"""Unit tests for the Phase-6 (6a) flat-list / by-id / allow-list helpers
added to the REAL ``agents.registry``.

Covers (per the Phase 6 plan, §5 T2 verify gate):
  (a) the allow-list shape for the (formerly legacy-parity) agreeing pipelines —
      user_stories, app_builder, and every *_revision. The legacy
      ``app.agents.registry`` was deleted in Phase 7a, so this is now pinned with
      hard-coded expectations derived from the real ``PIPELINE_AGENTS`` rather
      than compared against the legacy helper.
  (b) the REAL prototype ids surface for ``prototype`` and ``od_ppt`` is
      NON-empty (the formerly-``∅`` od_ppt bug fix, pinned directly).
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
    _INTERNAL_PIPELINES,
    PIPELINE_AGENTS,
    REVISION_BASE_MAP,
    allowed_custom_agent_ids,
    get_agent_by_id,
    get_all_agents_flat,
)


def _all_non_revision_non_internal_agents() -> set[str]:
    """The union of every non-revision, non-internal pipeline's agents.

    This is EXACTLY the set ``allowed_custom_agent_ids`` returns for a base
    pipeline OR for ``"custom"`` — the two branches compute the identical union
    (base = own ∪ custom ∪ all-other-base; custom = custom ∪ all-base; both
    reduce to all-base ∪ custom). The only pools excluded are the tight
    ``*_revision`` pipelines and the internal ``chat`` pipeline.
    """
    out: set[str] = set()
    for pt, ids in PIPELINE_AGENTS.items():
        if pt.endswith("_revision") or pt in _INTERNAL_PIPELINES:
            continue
        out.update(ids)
    return out

# Phase 7a removed the legacy ``app.agents.registry``. The original T2 verify
# gate parity-tested YOUR allow-list against the legacy helper for the pipelines
# that agreed (user_stories, app_builder, every revision). The legacy module is
# gone, so that parity is now re-expressed as hard-coded expectations DERIVED
# from the single source of truth (``PIPELINE_AGENTS``): a base pipeline's
# allow-list = the UNION of every non-revision, non-internal pipeline's agents
# (own ∪ custom pool ∪ all other base pipelines — the AgentLibrary UI lets a user
# fold any base-pipeline agent into any base/custom run); a revision pipeline's =
# its own agents only. (This union superseded the earlier "tightened to the
# custom pool" behaviour in commit d1a338fd — "custom workflow with prototype/ppt
# agents now runs correctly"; ``custom`` was never part of the legacy-parity
# guarantee.)
_AGREEING_REVISION_PIPELINES = sorted(REVISION_BASE_MAP.keys())  # excludes od_ppt_revision
_AGREEING_BASE_PIPELINES = ["user_stories", "app_builder"]
_CUSTOM_POOL = set(PIPELINE_AGENTS["custom"])


# ---------------------------------------------------------------------------
# (a) Allow-list shape for the (formerly legacy-parity) agreeing pipelines
# ---------------------------------------------------------------------------


class TestAllowListAgreeingPipelines:
    """The allow-list for the pipelines that used to be legacy-parity-tested now
    matches hard-coded expectations derived from the real registry."""

    @pytest.mark.parametrize("pipeline_type", _AGREEING_BASE_PIPELINES)
    def test_base_allow_list_is_union_of_non_revision_pipelines(self, pipeline_type: str):
        real = allowed_custom_agent_ids(pipeline_type)
        expected = _all_non_revision_non_internal_agents()
        assert real == expected, (
            f"allow-list mismatch for {pipeline_type!r}: "
            f"unexpected={real - expected}, missing={expected - real}"
        )
        # The pipeline's own agents and the custom pool are both folded in.
        assert set(PIPELINE_AGENTS[pipeline_type]) <= real
        assert _CUSTOM_POOL <= real
        assert real, f"expected a non-empty allow-list for {pipeline_type!r}"

    @pytest.mark.parametrize("pipeline_type", _AGREEING_REVISION_PIPELINES)
    def test_revision_allow_list_is_own_agents_only(self, pipeline_type: str):
        real = allowed_custom_agent_ids(pipeline_type)
        expected = set(PIPELINE_AGENTS[pipeline_type])
        assert real == expected, (
            f"allow-list mismatch for {pipeline_type!r}: "
            f"unexpected={real - expected}, missing={expected - real}"
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
        """A base pipeline allow-list folds in its own agents AND the custom pool
        (it is the union of every non-revision, non-internal pipeline)."""
        custom = set(PIPELINE_AGENTS["custom"])
        expected = _all_non_revision_non_internal_agents()
        for base in ("user_stories", "app_builder"):
            allowed = allowed_custom_agent_ids(base)
            assert allowed == expected
            assert set(PIPELINE_AGENTS[base]) <= allowed
            assert custom <= allowed


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
        """The legacy ``od_ppt → ∅`` bug rejected every od_ppt custom run. The
        fix treats od_ppt as a base pipeline: its allow-list is the union of every
        non-revision, non-internal pipeline (own agents ∪ custom pool ∪ all other
        base pipelines). (The legacy registry that returned ``∅`` here was deleted
        in Phase 7a; the intended NON-empty result is pinned directly.)"""
        allowed = allowed_custom_agent_ids("od_ppt")
        assert allowed, "od_ppt allow-list must be non-empty (bug fix)"
        assert allowed == _all_non_revision_non_internal_agents()
        assert set(PIPELINE_AGENTS["od_ppt"]) <= allowed
        assert set(PIPELINE_AGENTS["custom"]) <= allowed

    def test_od_ppt_revision_is_tight(self):
        """od_ppt_revision is a revision (not in REVISION_BASE_MAP, caught by the
        *_revision suffix): its own agents only, no custom pool."""
        allowed = allowed_custom_agent_ids("od_ppt_revision")
        assert allowed == set(PIPELINE_AGENTS["od_ppt_revision"])
        assert allowed  # od_ppt_revision has one agent
        assert not (allowed & set(PIPELINE_AGENTS["custom"]))

    def test_custom_is_the_union_of_base_pipelines(self):
        """The ``custom`` allow-list unions the custom-utility pool with every
        non-revision, non-internal base pipeline's agents (commit d1a338fd —
        "custom workflow with prototype/ppt agents now runs correctly"), so a
        composed custom workflow may include any base-pipeline agent. It equals
        the base-pipeline union AND folds in the custom pool itself."""
        allowed = allowed_custom_agent_ids("custom")
        assert allowed == _all_non_revision_non_internal_agents()
        assert set(PIPELINE_AGENTS["custom"]) <= allowed
        # The generic fan-out producer (Phase 51) surfaces in the custom pool.
        assert "task-list-planner" in allowed

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
