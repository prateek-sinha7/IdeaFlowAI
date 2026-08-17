"""FIX-051 / ISS-035 — PIPELINE_AGENTS is derived from a folder scan, not a
hand-maintained literal dict.

Regression pins for the bug this fix closes: an agent's AGENT.md existing on
disk with correct `pipeline_type`/`order` frontmatter must be SUFFICIENT for
it to be discovered by every PIPELINE_AGENTS consumer (get_all_agents_flat,
allowed_custom_agent_ids, /api/workflows) — no separate registry.py edit
required. Proof case: the 8 `spec_kit` agents, which existed on disk fully
formed but were invisible to PIPELINE_AGENTS before this fix.
"""

from __future__ import annotations

import agents.loader as loader_module
from agents.loader import (
    SUPPORTED_PIPELINE_TYPES,
    TEMPLATE_AGENT_IDS_BY_FLAG,
    list_agent_ids,
    load_agent_spec,
)
from agents.registry import PIPELINE_AGENTS, get_all_agents_flat


def _all_agent_ids_on_disk() -> list[str]:
    prompts_dir = loader_module._PROMPTS_DIR
    return [
        p.name
        for p in prompts_dir.iterdir()
        if p.is_dir() and (p / "AGENT.md").exists()
    ]


class TestNoOrphanedAgent:
    """Every agent on disk must be reachable through PIPELINE_AGENTS."""

    def test_every_agent_pipeline_type_is_a_known_key(self):
        for agent_id in _all_agent_ids_on_disk():
            spec = load_agent_spec(agent_id)
            assert spec.pipeline_type in PIPELINE_AGENTS, (
                f"{agent_id!r}: pipeline_type {spec.pipeline_type!r} has no "
                "PIPELINE_AGENTS entry"
            )

    def test_every_agent_id_appears_in_its_pipeline_entry(self):
        """...except declared TEMPLATE agents, which are deliberately not members.

        Spec 012's ``custom-agent`` is a blank template the compiler CLONES —
        each clone gets a synthetic ``custom-agent:<instance_id>`` id. The
        template itself is never a step, and the engine asserts
        *compiled steps == PIPELINE_AGENTS membership* at run entry, so enrolling
        it would abort every ``custom`` run with ``RuntimeError`` (FINDING-07).

        It carries ``pipeline_type: custom`` only because the loader requires a
        supported value. The orphan invariant still holds in the sense that
        matters — the template is reachable via ``get_all_agents_flat`` (asserted
        below), so the composer can still offer it.
        """
        for agent_id in _all_agent_ids_on_disk():
            if agent_id in TEMPLATE_AGENT_IDS_BY_FLAG:
                continue
            spec = load_agent_spec(agent_id)
            assert agent_id in PIPELINE_AGENTS[spec.pipeline_type], (
                f"{agent_id!r} is on disk with pipeline_type={spec.pipeline_type!r} "
                f"but is missing from PIPELINE_AGENTS[{spec.pipeline_type!r}]"
            )

    def test_template_agents_are_reachable_but_never_pipeline_members(self):
        """The two halves of FINDING-07's fix, pinned together.

        Excluded from membership (or every ``custom`` run aborts) AND present in
        the flat pool (or the composer cannot offer a custom agent at all). One
        without the other is a bug in a different direction.
        """
        flat_ids = {s.id for s in get_all_agents_flat()}
        for template_id in TEMPLATE_AGENT_IDS_BY_FLAG:
            spec = load_agent_spec(template_id)
            assert template_id not in PIPELINE_AGENTS[spec.pipeline_type], (
                f"{template_id!r} is a template and must NOT be a member of "
                f"PIPELINE_AGENTS[{spec.pipeline_type!r}] — the engine asserts "
                "compiled-steps == membership at run entry"
            )
            assert template_id in flat_ids, (
                f"{template_id!r} is missing from get_all_agents_flat() — the "
                "composer's agent picker reads that list"
            )

    def test_spec_kit_agents_are_no_longer_invisible(self):
        # The exact bug: 8 spec_kit agents existed on disk, correctly formed,
        # but were absent from every PIPELINE_AGENTS entry before FIX-051.
        spec_kit_ids = {
            "analyze-agent",
            "deep-planner",
            "clarify-agent",
            "constitution-agent",
            "plan-agent",
            "research-agent",
            "specify-agent",
            "tasks-agent",
        }
        assert spec_kit_ids <= set(_all_agent_ids_on_disk()), (
            "expected fixture agents missing — spec_kit agents were removed "
            "from disk; update this test's expectations"
        )
        assert PIPELINE_AGENTS.get("spec_kit", []) and spec_kit_ids <= set(
            PIPELINE_AGENTS["spec_kit"]
        ), "spec_kit agents must be discoverable via PIPELINE_AGENTS"


class TestGetAllAgentsFlatCompleteness:
    """get_all_agents_flat() must include every agent on disk, not just the
    pipelines someone remembered to hand-list."""

    def test_includes_every_agent_with_a_supported_pipeline_type(self):
        flat_ids = {s.id for s in get_all_agents_flat()}
        expected = {
            agent_id
            for agent_id in _all_agent_ids_on_disk()
            if load_agent_spec(agent_id).pipeline_type in SUPPORTED_PIPELINE_TYPES
        }
        assert expected <= flat_ids, (
            f"agents missing from get_all_agents_flat(): {expected - flat_ids}"
        )

    def test_includes_spec_kit_agents(self):
        flat_ids = {s.id for s in get_all_agents_flat()}
        assert "analyze-agent" in flat_ids
        assert "deep-planner" in flat_ids


class TestPipelineAgentsParity:
    """The dynamically-derived PIPELINE_AGENTS must match, for every pipeline
    that already had agents before this fix, exactly what list_agent_ids()
    (the function get_pipeline_agents() already trusted) returns — proving
    the swap from a literal dict to a scan is behavior-preserving."""

    def test_matches_list_agent_ids_for_every_supported_type(self):
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            if pipeline_type == "od_prototype":
                # A pure id-alias (_OD_ALIAS_BASE) with no AGENT.md ever
                # declaring pipeline_type: od_prototype — excluded from
                # PIPELINE_AGENTS entirely, not just empty (see TestPptOdPptAlias
                # for the ppt/od_ppt sibling case, which IS included).
                assert "od_prototype" not in PIPELINE_AGENTS
                continue
            assert PIPELINE_AGENTS[pipeline_type] == list_agent_ids(pipeline_type), (
                f"PIPELINE_AGENTS[{pipeline_type!r}] drifted from list_agent_ids()"
            )

    def test_known_pipeline_agent_counts_unchanged(self):
        # Hand-verified counts from the pre-FIX-051 literal dict, pinned as a
        # behavior-preserving safety net.
        expected_counts = {
            "user_stories": 6,
            "user_stories_revision": 1,
            "ppt": 3,
            "ppt_revision": 1,
            "prototype": 5,
            # KAN-108 (416341b0) added the Revision Validation Agent, taking
            # this pipeline from 1 agent to 2.
            "prototype_revision": 2,
            "app_builder": 15,
            "app_builder_revision": 1,
            "mulesoft_to_springboot": 13,
            "dotnet_to_azure": 13,
            # Phase 51 (455eb8d5) registered the generic `task-list-planner`
            # fan-out producer into the custom pool, taking it from 8 to 9.
            # (`custom-agent` is a TEMPLATE and deliberately not a member —
            # see the `template: true` frontmatter flag, AgentSpec.template
            # in agents/loader.py.)
            "custom": 9,
            "reverse_engineer": 0,
            "chat": 7,
        }
        for pipeline_type, count in expected_counts.items():
            assert len(PIPELINE_AGENTS[pipeline_type]) == count, (
                f"{pipeline_type!r}: expected {count} agents, "
                f"got {len(PIPELINE_AGENTS[pipeline_type])}"
            )


class TestPptAgents:
    """The od-ppt agent set (formerly the od_ppt pipeline) now declares
    ``pipeline_type: ppt`` directly — WR-01 closed at the root (no more id
    alias; see agents/registry.py)."""

    def test_ppt_is_the_real_od_ppt_agents(self):
        assert PIPELINE_AGENTS["ppt"] == [
            "ppt-brief-analyst",
            "ppt-composer",
            "ppt-validator",
        ]

    def test_agents_declare_pipeline_type_ppt_directly(self):
        assert list_agent_ids("ppt") == PIPELINE_AGENTS["ppt"]
