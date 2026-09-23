"""Unit tests for agents/registry.py — pipeline ordering and get_pipeline_agents.

Tests cover:
  - list_agent_ids returns IDs in strictly ascending order with no duplicates
  - get_pipeline_agents returns AgentSpec objects sorted by ascending order
  - get_pipeline_agents with unsupported pipeline type returns []

Requirements: 9.3
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from agents.loader import list_agent_ids, load_agent_spec, SUPPORTED_PIPELINE_TYPES
from agents.registry import get_pipeline_agents

# ---------------------------------------------------------------------------
# Known drift cases (ADR-0003/ADR-0005)
# ---------------------------------------------------------------------------

# prototype-revision-analyzer is step 0 of all THREE prototype revision manifests,
# but declares its own pipeline_type so registry membership cannot list it under
# all three pipelines that actually run it. This is the registry/manifest split
# working as designed — see backend/CLAUDE.md and ADR-0003.
_SHARED_ANALYZER_DRIFT = {
    "prototype_revision",
    "prototype_large_revision",
    "prototype_feature_revision",
}

# ---------------------------------------------------------------------------
# Helpers for property tests (task 6.2)
# ---------------------------------------------------------------------------

_WORKFLOWS_ROOT = pathlib.Path(__file__).parents[3] / "agents" / "workflows"


def _agents_from_workflow_yaml(pipeline_type: str) -> list[str]:
    """Return the agent IDs listed in steps of a workflow.yaml, in manifest order."""
    yaml_path = _WORKFLOWS_ROOT / pipeline_type / "workflow.yaml"
    with yaml_path.open() as fh:
        manifest = yaml.safe_load(fh)
    return [step["agent"] for step in manifest.get("steps", [])]


def _declares_membership(agent_id: str, pipeline_type: str) -> bool:
    """True when ``agent_id``'s AGENT.md claims membership in ``pipeline_type``.

    ``PIPELINE_AGENTS`` is DERIVED by scanning AGENT.md frontmatter (see the comment
    at the top of ``agents/registry.py``), and ``pipeline_type`` may be a single id OR
    a LIST — shared agents such as ``prototype-validate`` enumerate every pipeline they
    belong to (``['prototype', 'prototype_revision', ...]``). An agent appears in a
    pipeline's roster exactly when that pipeline id is among its declared value.
    """
    try:
        spec = load_agent_spec(agent_id)
    except Exception:  # noqa: BLE001 — an unloadable agent is a real roster gap
        return False
    declared = getattr(spec, "pipeline_type", None)
    if declared is None:
        return False
    if isinstance(declared, str):
        return declared == pipeline_type
    return pipeline_type in declared


def _registry_owned_yaml_agents(pipeline_type: str) -> list[str]:
    """The manifest step agents the REGISTRY is expected to own, in manifest order.

    Excludes MANIFEST-SUPPLIED agents — steps whose AGENT.md does not claim membership
    in this pipeline, so the derived roster cannot contain them.

    ``prototype-revision-analyzer`` is the live case: the revision-pipeline refactor
    promoted it to step 0 of all three revision manifests, but it declares only its own
    private ``pipeline_type: prototype_revision_analyzer`` and does NOT enumerate the
    revision pipelines — so it is deliberately absent from
    ``PIPELINE_AGENTS[<revision pipeline>]``. The engine accounts for this by passing
    ``agents=[]`` into ``execute()`` and building the roster from ``compiled.steps``
    rather than the registry list (see the comment at the ``_handle_revision`` dispatch
    site): for execution the MANIFEST is the source of truth, not the roster.

    Derived from the specs on disk, never hardcoded — if the analyzer is ever re-homed
    onto the revision pipelines it stops being exempt automatically, and
    ``test_manifest_supplied_agents_are_absent_from_the_roster`` fails to say so.
    """
    return [
        agent_id
        for agent_id in _agents_from_workflow_yaml(pipeline_type)
        if _declares_membership(agent_id, pipeline_type)
    ]


# ---------------------------------------------------------------------------
# Task 19.4 — Pipeline ordering tests
# ---------------------------------------------------------------------------


class TestPipelineOrdering:
    """Verify list_agent_ids returns strictly ascending order with no duplicates.

    Uses the REAL filesystem (agents/prompts/).
    Requirements: 9.3
    """

    def test_list_agent_ids_strictly_ascending_for_all_pipelines(self):
        """For every pipeline type, list_agent_ids must return IDs in strictly ascending order."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            if not ids:
                continue  # empty pipelines are fine (e.g. reverse_engineer)

            # Resolve each ID to its order value
            orders = [load_agent_spec(agent_id).order for agent_id in ids]

            for i in range(1, len(orders)):
                assert orders[i] > orders[i - 1], (
                    f"Pipeline {pipeline_type!r}: order is not strictly ascending at position {i}. "
                    f"Got orders={orders}, ids={ids}"
                )

    def test_list_agent_ids_no_duplicate_orders_for_all_pipelines(self):
        """For every pipeline type, no two agents may share the same order value."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            if not ids:
                continue

            orders = [load_agent_spec(agent_id).order for agent_id in ids]
            assert len(orders) == len(set(orders)), (
                f"Pipeline {pipeline_type!r}: duplicate order values found. "
                f"orders={orders}, ids={ids}"
            )

    def test_list_agent_ids_returns_list_of_strings(self):
        """list_agent_ids must return a list of strings for every pipeline type."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids = list_agent_ids(pipeline_type)
            assert isinstance(
                ids, list
            ), f"Pipeline {pipeline_type!r}: expected list, got {type(ids).__name__}"
            for agent_id in ids:
                assert isinstance(
                    agent_id, str
                ), f"Pipeline {pipeline_type!r}: agent ID {agent_id!r} is not a string"


class TestGetPipelineAgents:
    """Verify get_pipeline_agents returns AgentSpec objects sorted by ascending order.

    Requirements: 9.3, 5.6, 5.7
    """

    def test_get_pipeline_agents_returns_agent_specs_sorted_by_order(self):
        """get_pipeline_agents must return AgentSpec objects sorted by ascending order."""
        from agents.loader import AgentSpec

        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            if pipeline_type in _SHARED_ANALYZER_DRIFT:
                pytest.xfail(
                    f"{pipeline_type}: step 0 is the SHARED prototype-revision-analyzer, which "
                    "declares its own pipeline_type so registry membership cannot list it "
                    "(ADR-0003/ADR-0005 — see _SHARED_ANALYZER_DRIFT)"
                )

            specs = get_pipeline_agents(pipeline_type)
            if not specs:
                continue

            # All items must be AgentSpec instances
            for spec in specs:
                assert isinstance(
                    spec, AgentSpec
                ), f"Pipeline {pipeline_type!r}: expected AgentSpec, got {type(spec).__name__}"

            # Orders must be strictly ascending
            orders = [spec.order for spec in specs]
            for i in range(1, len(orders)):
                assert orders[i] > orders[i - 1], (
                    f"Pipeline {pipeline_type!r}: get_pipeline_agents not sorted by order. "
                    f"Got orders={orders}"
                )

    def test_get_pipeline_agents_unsupported_type_returns_empty_list(self):
        """Requirement 5.7: get_pipeline_agents with unsupported type returns []."""
        result = get_pipeline_agents("not_a_real_pipeline_type")
        assert (
            result == []
        ), f"Expected [] for unsupported pipeline type, got {result!r}"

    def test_get_pipeline_agents_empty_string_returns_empty_list(self):
        """get_pipeline_agents with empty string returns []."""
        result = get_pipeline_agents("")
        assert result == []

    def test_get_pipeline_agents_is_discovery_plus_its_own_manifest_steps(self):
        """The roster CONTAINS everything AGENT.md discovery finds, in order — and may
        contain more.

        This assertion used to be equality with ``list_agent_ids``, which encoded the
        very assumption that broke ``ppt_v2``: that a pipeline's roster is exactly the
        agents whose ``AGENT.md`` names it. ``pipeline_type`` holds ONE value, so a
        workflow REUSING an agent from another pipeline could never be described that
        way — ``ppt_v2`` reuses ppt's brief-analyst and composer, and the roster
        reported 2 of its 4 steps. The DAG resolver validates ``consumes`` against
        this list and called the whole pipeline unsatisfiable as a result.

        So the contract is now containment, not equality. What is still pinned, and is
        what the original test was actually protecting: discovery's agents all survive,
        their relative order is unchanged, and the whole list is ``order``-sorted.
        """
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            ids_from_list = list_agent_ids(pipeline_type)
            ids_from_get = [spec.id for spec in get_pipeline_agents(pipeline_type)]

            assert set(ids_from_list) <= set(ids_from_get), (
                f"Pipeline {pipeline_type!r}: discovery agents DROPPED from the roster — "
                f"list_agent_ids={ids_from_list} get_pipeline_agents={ids_from_get}"
            )
            # Relative order of the discovered agents is preserved.
            assert [
                i for i in ids_from_get if i in set(ids_from_list)
            ] == ids_from_list, (
                f"Pipeline {pipeline_type!r}: order mismatch between "
                f"list_agent_ids={ids_from_list} and get_pipeline_agents={ids_from_get}"
            )

    def test_a_reusing_pipeline_reports_every_step_it_will_run(self):
        """spec 017 — the concrete case the contract above exists for.

        ``ppt_v2``'s manifest runs four steps; two of them are ppt's, so neither
        declares ``pipeline_type: ppt_v2``. A roster missing them is not a cosmetic
        undercount: it is what the DAG resolver validates against.
        """
        roster = [spec.id for spec in get_pipeline_agents("ppt_v2")]
        assert roster == [
            "ppt-brief-analyst",
            "ppt-composer",
            "ppt-deck-qa-v2",
            "ppt-code-generator",
        ]

    def test_completing_the_roster_never_adds_a_template_agent(self):
        """``template: true`` marks a folder that exists to be INSTANTIATED, never to
        be a pipeline member — which is why discovery excludes it. A composed
        workflow's manifest steps ARE those instances, so completing from the manifest
        has to honour the same rule or every composed pipeline grows a phantom
        ``custom-agent`` member."""
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            for spec in get_pipeline_agents(pipeline_type):
                assert not getattr(
                    spec, "template", False
                ), f"Pipeline {pipeline_type!r}: template agent {spec.id!r} in the roster"


# ---------------------------------------------------------------------------
# Task 6.1 — Revision pipeline roster assertions
# ---------------------------------------------------------------------------


class TestRevisionPipelineRosters:
    """Verify the exact agent rosters for all three revision pipelines and the base prototype.

    Uses the REAL filesystem (agents/prompts/). No tmp_agent_dir fixture needed.
    Requirements: 9.4, 12.2
    """

    def test_prototype_revision_roster(self):
        """prototype_revision pipeline must contain exactly the three expected agents in order."""
        assert list_agent_ids("prototype_revision") == [
            "prototype-revision-analyzer",
            "prototype-revision-agent",
            "prototype-validate",
        ]

    def test_prototype_large_revision_roster(self):
        """prototype_large_revision pipeline must contain exactly the four expected agents in order."""
        assert list_agent_ids("prototype_large_revision") == [
            "prototype-revision-analyzer",
            "prototype-revision-planner",
            "prototype-build",
            "prototype-validate",
        ]

    def test_prototype_feature_revision_roster(self):
        """prototype_feature_revision pipeline must contain exactly the five expected agents in order."""
        assert list_agent_ids("prototype_feature_revision") == [
            "prototype-revision-analyzer",
            "prototype-revision-feature-specify",
            "prototype-plan",
            "prototype-build",
            "prototype-validate",
        ]

    def test_prototype_pipeline_unchanged(self):
        """prototype pipeline must remain the original five-agent roster unchanged."""
        assert list_agent_ids("prototype") == [
            "prototype-specify",
            "prototype-plan",
            "prototype-analyze",
            "prototype-build",
            "prototype-validate",
        ]


# ---------------------------------------------------------------------------
# Task 6.2 — Property tests: roster completeness and prototype regression
# ---------------------------------------------------------------------------


class TestRosterCompletenessProperty:
    """Property 1: Roster completeness.

    For each revision pipeline, the registry roster returned by list_agent_ids
    must equal *exactly* the agents declared in the workflow.yaml steps, in
    manifest order.  The expected list is derived by reading the YAML file at
    test time — not hardcoded — so any future change to a manifest that is not
    reflected in the AGENT.md order values will surface immediately.

    Validates: Requirements 6.2, 6.3, 9.1, 9.4
    """

    REVISION_PIPELINES = [
        "prototype_revision",
        "prototype_large_revision",
        "prototype_feature_revision",
    ]

    @pytest.mark.issue("ISS-631")
    @pytest.mark.parametrize("pipeline_type", REVISION_PIPELINES)
    def test_roster_matches_workflow_yaml_steps_in_order(self, pipeline_type: str):
        """Registry roster for each revision pipeline equals the workflow.yaml step agents in manifest order."""
        expected = _registry_owned_yaml_agents(pipeline_type)
        actual = list_agent_ids(pipeline_type)
        assert actual == expected, (
            f"Pipeline {pipeline_type!r}: registry roster {actual!r} does not "
            f"match the registry-owned workflow.yaml step agents {expected!r}. "
            "Either the AGENT.md `order` values or the workflow.yaml steps are out of sync."
        )

    @pytest.mark.parametrize("pipeline_type", REVISION_PIPELINES)
    def test_manifest_supplied_agents_are_absent_from_the_roster(
        self, pipeline_type: str
    ):
        """Non-vacuity + contract guard for the exemption above.

        Any manifest step agent that does NOT claim membership in this pipeline must
        genuinely be absent from the registry roster. If such an agent were re-homed
        onto this pipeline, the exemption would silently start hiding a real ordering
        mismatch — this test fails first and forces the exemption to be revisited.
        """
        all_steps = _agents_from_workflow_yaml(pipeline_type)
        owned = _registry_owned_yaml_agents(pipeline_type)
        manifest_supplied = [a for a in all_steps if a not in owned]
        roster = set(list_agent_ids(pipeline_type))
        leaked = [a for a in manifest_supplied if a in roster]
        assert not leaked, (
            f"Pipeline {pipeline_type!r}: {leaked!r} do not declare membership in this "
            f"pipeline yet appear in the registry roster. They are no longer "
            f"manifest-supplied — drop the exemption in _registry_owned_yaml_agents "
            f"and assert them in order instead."
        )

    @pytest.mark.parametrize("pipeline_type", REVISION_PIPELINES)
    def test_roster_contains_no_extra_agents_beyond_yaml(self, pipeline_type: str):
        """Registry must not include agents absent from the workflow.yaml steps for that pipeline."""
        expected_set = set(_agents_from_workflow_yaml(pipeline_type))
        actual_set = set(list_agent_ids(pipeline_type))
        extra = actual_set - expected_set
        assert not extra, f"Pipeline {pipeline_type!r}: registry returned extra agents not in workflow.yaml: {extra!r}"

    @pytest.mark.issue("ISS-631")
    @pytest.mark.parametrize("pipeline_type", REVISION_PIPELINES)
    def test_roster_missing_no_yaml_agents(self, pipeline_type: str):
        """Registry must include every registry-owned agent declared in the workflow.yaml steps.

        Manifest-supplied agents (foreign pipeline_type) are excluded — the engine
        sources those from ``compiled.steps``, not the roster. See
        ``_declares_foreign_pipeline_type``.
        """
        expected_set = set(_registry_owned_yaml_agents(pipeline_type))
        actual_set = set(list_agent_ids(pipeline_type))
        missing = expected_set - actual_set
        assert not missing, f"Pipeline {pipeline_type!r}: registry is missing agents from workflow.yaml: {missing!r}"


class TestPrototypePipelineRegressionProperty:
    """Property 2: No prototype pipeline regression.

    The prototype base pipeline roster must remain exactly the five agents
    declared in its workflow.yaml, in manifest order. This guards against
    accidental changes to the prototype pipeline while editing shared agents.

    Validates: Requirements 9.1, 9.4
    """

    # Pre-change canonical prototype pipeline — five agents in order.
    _EXPECTED_PROTOTYPE_ROSTER = [
        "prototype-specify",
        "prototype-plan",
        "prototype-analyze",
        "prototype-build",
        "prototype-validate",
    ]

    def test_prototype_roster_matches_workflow_yaml(self):
        """Prototype registry roster must equal the workflow.yaml step agents in manifest order."""
        expected_from_yaml = _agents_from_workflow_yaml("prototype")
        actual = list_agent_ids("prototype")
        assert actual == expected_from_yaml, (
            f"Prototype registry roster {actual!r} diverges from workflow.yaml steps "
            f"{expected_from_yaml!r}. The workflow.yaml may have been modified."
        )

    def test_prototype_roster_unchanged_from_pre_change_baseline(self):
        """Prototype pipeline must still be the exact pre-change five-agent roster."""
        actual = list_agent_ids("prototype")
        assert actual == self._EXPECTED_PROTOTYPE_ROSTER, (
            f"Prototype pipeline regression detected! "
            f"Expected {self._EXPECTED_PROTOTYPE_ROSTER!r}, got {actual!r}."
        )

    def test_prototype_roster_has_exactly_five_agents(self):
        """Prototype pipeline must contain exactly 5 agents (guard against additions/deletions)."""
        actual = list_agent_ids("prototype")
        assert (
            len(actual) == 5
        ), f"Prototype pipeline should have exactly 5 agents, got {len(actual)}: {actual!r}"
