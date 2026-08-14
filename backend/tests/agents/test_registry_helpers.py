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

from agents.loader import TEMPLATE_AGENT_IDS_BY_FLAG, AgentSpec
from agents.registry import (
    _INTERNAL_PIPELINES,
    PIPELINE_AGENTS,
    REVISION_BASE_MAP,
    allowed_custom_agent_ids,
    get_agent_by_id,
    get_all_agents_flat,
)


def _tight_base_allow_list(pipeline_type: str) -> set[str]:
    """What a base pipeline may run: its OWN agents plus the custom-utility pool.

    Deliberately NOT the union of every base pipeline. ``allowed_custom_agent_ids``
    is the ONLY gate on ``agent_ids`` for both the REST launch path
    (``app/api/run_commands.py``) and the save-workflow path
    (``app/api/user_workflows.py``) — whatever it returns is loaded and run, with
    no per-agent check downstream. Meanwhile ``entitlements.can_run_pipeline``
    takes only a ``pipeline_type``, so it cannot see which pipeline an individual
    agent came from.

    Union those two facts and a broad allow-list is a tier bypass: a ``basic``
    user launching ``ppt`` (allowed at their tier) could pass ``app_builder``
    agent ids (NOT allowed at their tier) and be accepted. That is exactly the
    class ``tests/unit/test_run_pipeline_validation.py::TestCrossPipelineInjectionIsBlocked``
    exists to prevent.

    HISTORY — do not "reconcile" these tests to the code a third time.
    ``b59e9ad2`` (KAN-75) broadened the branches to a full union for a composer
    UI feature, without reconciling against the tier model. ``455eb8d5`` then
    found these very tests failing and, per its own commit message, "reconcile[d]
    the 5 stale test_registry_helpers allow-list tests to the actual union
    contract" — i.e. rewrote the tests to match the insecure code. The
    cross-injection tests in ``test_run_pipeline_validation.py`` were never
    touched, so the suite has been asserting two contradictory policies for the
    same function ever since. If cross-pipeline composition is wanted, it needs a
    per-agent tier check at the call sites — not a wider allow-list.
    """
    return set(PIPELINE_AGENTS.get(pipeline_type, ())) | set(PIPELINE_AGENTS["custom"])


def _all_non_revision_non_internal_agents() -> set[str]:
    """The union of every non-revision, non-internal pipeline's agents.

    Retained only as the "everything" reference set for the negative assertions
    below (proving the allow-list is a STRICT subset of it). It is no longer what
    ``allowed_custom_agent_ids`` returns — see ``_tight_base_allow_list``.
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
    def test_base_allow_list_is_own_agents_plus_custom_pool(self, pipeline_type: str):
        real = allowed_custom_agent_ids(pipeline_type)
        expected = _tight_base_allow_list(pipeline_type)
        assert real == expected, (
            f"allow-list mismatch for {pipeline_type!r}: "
            f"unexpected={real - expected}, missing={expected - real}"
        )
        # The pipeline's own agents and the custom pool are both folded in.
        assert set(PIPELINE_AGENTS[pipeline_type]) <= real
        assert _CUSTOM_POOL <= real
        assert real, f"expected a non-empty allow-list for {pipeline_type!r}"

    @pytest.mark.parametrize("pipeline_type", _AGREEING_BASE_PIPELINES)
    def test_base_allow_list_excludes_other_pipelines_agents(self, pipeline_type: str):
        """The security property, asserted directly rather than implied.

        Another base pipeline's exclusive agents must NOT be runnable here. This
        is the tier-bypass guard: `can_run_pipeline` gates by pipeline_type only,
        so an agent borrowed from a higher-tier pipeline would otherwise ride in
        on a lower-tier pipeline_type the user IS entitled to.
        """
        allowed = allowed_custom_agent_ids(pipeline_type)
        for other, ids in PIPELINE_AGENTS.items():
            if other == pipeline_type or other.endswith("_revision"):
                continue
            if other in _INTERNAL_PIPELINES or other == "custom":
                continue
            exclusive = set(ids) - _tight_base_allow_list(pipeline_type)
            leaked = exclusive & allowed
            assert not leaked, (
                f"{other!r} agents are runnable under {pipeline_type!r}: {sorted(leaked)} "
                "— cross-pipeline injection / tier bypass"
            )

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
        """A base pipeline allow-list is its own agents AND the custom pool —
        and nothing else. It is a STRICT subset of the all-pipelines union."""
        custom = set(PIPELINE_AGENTS["custom"])
        everything = _all_non_revision_non_internal_agents()
        for base in ("user_stories", "app_builder"):
            allowed = allowed_custom_agent_ids(base)
            assert allowed == _tight_base_allow_list(base)
            assert set(PIPELINE_AGENTS[base]) <= allowed
            assert custom <= allowed
            assert allowed < everything, (
                f"{base!r} allow-list is the full union — the tier bypass is back"
            )


# ---------------------------------------------------------------------------
# (b) Real prototype ids + the ppt/od_ppt bug fix
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

    def test_ppt_is_non_empty_bug_fix(self):
        """The legacy ``od_ppt → ∅`` bug rejected every od_ppt custom run. The
        od_ppt agent set now declares ``pipeline_type: ppt`` directly (WR-01
        closed at the root — see agents/registry.py), so ``ppt``'s allow-list is
        its own agents ∪ the custom pool, same as any other base pipeline."""
        allowed = allowed_custom_agent_ids("ppt")
        assert allowed, "ppt allow-list must be non-empty (bug fix)"
        assert allowed == _tight_base_allow_list("ppt")
        assert set(PIPELINE_AGENTS["ppt"]) <= allowed
        assert set(PIPELINE_AGENTS["custom"]) <= allowed

    def test_ppt_revision_is_tight(self):
        """ppt_revision (formerly od_ppt_revision) is a revision pipeline: its
        own agents only, no custom pool."""
        allowed = allowed_custom_agent_ids("ppt_revision")
        assert allowed == set(PIPELINE_AGENTS["ppt_revision"])
        assert allowed  # ppt_revision has one agent
        assert not (allowed & set(PIPELINE_AGENTS["custom"]))

    def test_custom_is_the_union_of_base_pipelines(self):
        """``custom`` is OPEN by design — every non-revision, non-internal agent.

        Mixing agents from different pipelines into one runtime-composed
        workflow is the custom workflow builder's entire purpose (spec 012), so
        this branch is deliberately wide and must stay that way.

        It is not an entitlement bypass the way the BASE-pipeline branch would
        be: ``custom`` appears only in the ``enterprise`` tier
        (``entitlements.TIER_PIPELINES``), and enterprise already holds every
        pipeline unioned in here — so this branch grants nothing the caller
        could not already reach directly.

        That equivalence is load-bearing, and this test pins it: if ``custom``
        is ever granted to a tier that does NOT hold every pipeline, the
        assertion below fails and the branch must be narrowed to the custom pool
        plus a per-agent origin-tier check.
        """
        from app.core.entitlements import TIER_PIPELINES

        allowed = allowed_custom_agent_ids("custom")
        assert allowed == _all_non_revision_non_internal_agents()
        assert set(PIPELINE_AGENTS["custom"]) <= allowed
        # The generic fan-out producer (Phase 51) surfaces in the custom pool.
        assert "task-list-planner" in allowed

        # The safety equivalence: any tier holding "custom" must hold every
        # pipeline whose agents this branch exposes.
        exposed = {
            pt for pt in PIPELINE_AGENTS
            if not pt.endswith("_revision") and pt not in _INTERNAL_PIPELINES
        }
        for tier, pipelines in TIER_PIPELINES.items():
            if "custom" not in pipelines:
                continue
            missing = {pt for pt in exposed if pt in TIER_PIPELINES["enterprise"]} - pipelines
            assert not missing, (
                f"tier {tier!r} may run 'custom' — which exposes every pipeline's "
                f"agents — but is not entitled to {sorted(missing)}. That makes the "
                "open custom branch a real entitlement bypass; narrow it to the "
                "custom pool and add a per-agent origin-tier check."
            )

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
        for shared in ("ppt-brief-analyst", "ppt-composer", "ppt-validator"):
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
        # And it introduces no ids beyond those declared in a pipeline — EXCEPT
        # declared template agents (spec 012). ``custom-agent`` is a blank
        # template the compiler CLONES into ``custom-agent:<instance_id>`` steps;
        # it is deliberately NOT a PIPELINE_AGENTS member, because the engine
        # asserts compiled-steps == membership at run entry and a template is
        # never a step (FINDING-07). It still belongs in the flat pool: that is
        # the list the composer's agent picker reads, and a custom agent nobody
        # can select is the feature not existing.
        all_declared = {aid for ids in PIPELINE_AGENTS.values() for aid in ids}
        all_declared |= TEMPLATE_AGENT_IDS_BY_FLAG
        assert flat_ids <= all_declared, (
            f"flat list has undeclared ids: {flat_ids - all_declared}"
        )

    def test_stable_order(self):
        """The flat ordering is deterministic across calls."""
        assert [s.id for s in get_all_agents_flat()] == [
            s.id for s in get_all_agents_flat()
        ]
