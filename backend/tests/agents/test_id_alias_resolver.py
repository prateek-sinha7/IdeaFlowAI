"""MAN-05 / MAN-04 — id-alias resolver + CompiledWorkflow routing-source tests.

Covers the run-entry routing seam introduced in the engine (04-04):

  * ``resolve_alias`` is the SINGLE point mapping the legacy ``pipeline_type``
    label to a manifest id: ``od_prototype`` -> ``prototype``; every real
    ``PIPELINE_AGENTS`` key resolves to itself (MAN-05).
  * ``compile_for_run`` sources the run's CompiledWorkflow from the manifest +
    compiler layer; the engine's effective agent sequence, clarify defaults, and
    planner flag come FROM that compiled plan, not the legacy hardcoded dicts
    (MAN-04).

These are pure-data tests (no engine drive) — the end-to-end ``execute()`` run
from the compiled plan is covered by ``test_compiled_plan_runs.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.execution_engine.engine import compile_for_run, resolve_alias
from agents.loader import SUPPORTED_PIPELINE_TYPES
from agents.registry import PIPELINE_AGENTS, _OD_ALIAS_BASE, get_pipeline_agents

_MANIFEST_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_MANIFEST_BACKED_IDS = {
    pt
    for pt in SUPPORTED_PIPELINE_TYPES
    if (_MANIFEST_BASE / pt / "workflow.yaml").exists()
}

# The 13 engine-dispatchable pipelines = the manifest-backed pipelines minus
# the two non-engine-dispatched edge cases (chat = ChatRunner; reverse_engineer
# = empty). FIX-051 / ISS-035: scoped to manifest-backed ids, not raw
# PIPELINE_AGENTS keys — PIPELINE_AGENTS can now contain a pipeline_type with
# real agents but no manifest yet (e.g. spec_kit), which cannot be compiled.
_DISPATCHABLE = sorted(_MANIFEST_BACKED_IDS - {"chat", "reverse_engineer"})

# The exact verbatim per-pipeline default clarifying-question lists the engine
# formerly hardcoded in `_pipeline_defaults` (engine.py:752-761, now removed).
# The compiled plan's clarify.defaults MUST reproduce these (revisions / edge ids
# fall to the `custom` list). Kept in lockstep with the engine's former dict.
_EXPECTED_CLARIFY_DEFAULTS: dict[str, list[str]] = {
    "od_ppt": ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "ppt": ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "od_prototype": ["target_audience", "scope", "priority", "style"],
    "prototype": ["target_audience", "scope", "priority", "style"],
    "user_stories": ["target_audience", "scope", "priority", "technology"],
    "app_builder": ["technology", "scope", "target_audience", "security"],
    "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority"],
    "dotnet_to_azure": ["scope", "technology", "timeline", "priority"],
    "custom": ["target_audience", "key_objectives", "scope", "priority"],
}
_CUSTOM_DEFAULTS = _EXPECTED_CLARIFY_DEFAULTS["custom"]


# ── resolve_alias (MAN-05) ──────────────────────────────────────────────────


def test_od_prototype_resolves_to_prototype() -> None:
    """The sole id-alias: od_prototype -> prototype."""
    assert resolve_alias("od_prototype") == "prototype"


@pytest.mark.parametrize("key", sorted(PIPELINE_AGENTS))
def test_every_real_pipeline_key_resolves_to_itself(key: str) -> None:
    """Every real PIPELINE_AGENTS key is identity under the resolver (no alias)."""
    assert resolve_alias(key) == key


def test_od_prototype_is_the_only_alias() -> None:
    """The resolver maps exactly one label and is the single point of aliasing."""
    assert _OD_ALIAS_BASE == {"od_prototype": "prototype"}
    # Identity for an arbitrary unknown label (resolver never invents a mapping).
    assert resolve_alias("totally_unknown_label") == "totally_unknown_label"


# ── compile_for_run sources the agent sequence (MAN-04, concern 1) ──────────


@pytest.mark.parametrize("pipeline_type", _DISPATCHABLE + ["od_prototype"])
def test_compiled_agent_sequence_matches_registry_order(pipeline_type: str) -> None:
    """The compiled plan's step order equals the registry's agent order (no reorder).

    This is the parity guard (RESEARCH Pitfall 3): the engine sources the agent
    sequence from `compile_for_run(...).steps`, which must equal the order the
    legacy `get_pipeline_agents` / PIPELINE_AGENTS would have produced. `ppt`
    agents declare pipeline_type: od_ppt, so get_pipeline_agents("ppt") is empty
    — fall back to PIPELINE_AGENTS[id] there (matches the coverage test).
    """
    compiled = compile_for_run(pipeline_type)
    compiled_ids = [s.agent_id for s in compiled.steps]

    manifest_id = resolve_alias(pipeline_type)
    registry_order = [a.id for a in get_pipeline_agents(manifest_id)]
    expected = registry_order if registry_order else PIPELINE_AGENTS[manifest_id]
    assert compiled_ids == expected


def test_od_prototype_runs_prototypes_plan() -> None:
    """The od_prototype alias compiles to the prototype manifest's plan (D-04)."""
    compiled = compile_for_run("od_prototype")
    assert compiled.id == "prototype"
    assert [s.agent_id for s in compiled.steps] == [
        a.id for a in get_pipeline_agents("prototype")
    ]


# ── compile_for_run sources clarify defaults (MAN-04, concern 3) ────────────


@pytest.mark.parametrize("pipeline_type", _DISPATCHABLE + ["od_prototype"])
def test_compiled_clarify_defaults_match_engine_dict(pipeline_type: str) -> None:
    """The compiled clarify.defaults reproduce the engine's former _pipeline_defaults.

    The engine now sources the ALWAYS_CLARIFY default-question seed from
    `compile_for_run(...).clarify.defaults` instead of the removed hardcoded
    dict. od_prototype resolves to the prototype manifest (same defaults).
    Revisions / edge ids fall to the `custom` list.
    """
    compiled = compile_for_run(pipeline_type)
    expected = _EXPECTED_CLARIFY_DEFAULTS.get(pipeline_type, _CUSTOM_DEFAULTS)
    assert list(compiled.clarify.defaults) == expected


# ── compile_for_run sources the planner flag (MAN-04, concern 4) ────────────

# Phase 14 carve-out: the two run_revision-dispatched manifests declare
# planner: skip (clarify-auto would hang a dispatched revision at the clarify
# event.wait()). Sibling trap: tests/agents/test_manifest_parity.py
# (_RUN_REVISION_DISPATCHED) — keep both carve-outs in lockstep.
_RUN_REVISION_DISPATCHED = frozenset({"ppt_revision", "od_ppt_revision"})


@pytest.mark.parametrize("pipeline_type", _DISPATCHABLE + ["od_prototype"])
def test_compiled_planner_is_run_everywhere(pipeline_type: str) -> None:
    """Every dispatchable manifest declares planner: run — EXCEPT the two
    run_revision-dispatched manifests (planner: skip as of Phase 14; see
    _RUN_REVISION_DISPATCHED above and the sibling trap in
    test_manifest_parity.py). For every other pipeline the engine's
    skip_planner stays False and the planner/clarifier runs (byte-identical).
    """
    compiled = compile_for_run(pipeline_type)
    expected = "skip" if pipeline_type in _RUN_REVISION_DISPATCHED else "run"
    assert compiled.planner == expected
