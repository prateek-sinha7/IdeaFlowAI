"""Parity tests — the two parity traps that snapshots do NOT catch (MAN-04).

Parity trap #1 — planner: run everywhere.
  The legacy prototype planner-skip flag was False, so skip_planner is ALWAYS
  False — every dispatchable pipeline (incl. prototype) runs the planner/clarifier.
  That flag (and its module) were DELETED in 07-05; the AUTHORED truth is now the
  manifest's ``planner: run``. Every dispatchable manifest must therefore declare
  planner: run (NOT planner: skip, despite §10's illustrative YAML). A
  planner: skip would change behavior and break the prototype event snapshots.

Parity trap #2 — clarify.defaults reproduce engine._pipeline_defaults verbatim.
  The clarify-mode auto seeding (engine.py) keys the default clarifying questions
  off a per-pipeline dict. With the offline _drive harness this is NOT exercised by
  characterization snapshots — this dedicated test is the only guard. The compiled
  clarify.defaults must equal the engine dict per pipeline; revisions / ids absent
  from the dict reuse the "custom" list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.registry import _INTERNAL_PIPELINES, PIPELINE_AGENTS
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest

_BASE = Path(__file__).resolve().parents[2] / "agents" / "workflows"

# Hard-copied VERBATIM from engine.ExecutionEngine.execute's local
# `_pipeline_defaults` dict (agents/execution_engine/engine.py:752-761). This is
# the authoritative source for clarify.defaults; if the engine dict changes, this
# copy (and the manifests) must change with it. Keep in lockstep.
_ENGINE_PIPELINE_DEFAULTS: dict[str, list[str]] = {
    "od_ppt":        ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "ppt":           ["target_audience", "tone_and_style", "key_objectives", "slide_count"],
    "od_prototype":  ["target_audience", "scope", "priority", "style"],
    "prototype":     ["target_audience", "scope", "priority", "style"],
    "user_stories":  ["target_audience", "scope", "priority", "technology"],
    "app_builder":   ["technology", "scope", "target_audience", "security"],
    "mulesoft_to_springboot": ["scope", "technology", "timeline", "priority"],
    "dotnet_to_azure":        ["scope", "technology", "timeline", "priority"],
    "custom":        ["target_audience", "key_objectives", "scope", "priority"],
}
# The fallback the engine uses for any id absent from the dict: _pipeline_defaults["custom"].
_CUSTOM_DEFAULTS = _ENGINE_PIPELINE_DEFAULTS["custom"]


def _compile(workflow_id: str):
    return WorkflowCompiler().compile(
        load_manifest(workflow_id, _BASE), CapabilityRegistry()
    )


# ---------------------------------------------------------------------------
# Parity trap #1 — planner: run for every dispatchable manifest
# ---------------------------------------------------------------------------


def test_prototype_planner_runs() -> None:
    # Guards the premise of trap #1, re-expressed via the AUTHORED manifest after
    # the legacy planner-skip flag (and its module) were deleted in 07-05: the
    # prototype manifest must declare planner: run (i.e. NOT skip). If this ever
    # flips, the manifests + this test must be revisited.
    assert _compile("prototype").planner == "run"


@pytest.mark.parametrize(
    "workflow_id",
    sorted(set(PIPELINE_AGENTS) - set(_INTERNAL_PIPELINES)),
)
def test_planner_run_everywhere(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    assert plan.planner == "run", (
        f"{workflow_id} must declare planner: run "
        f"(SKIP_PLANNER_FOR_PROTOTYPE=False, parity trap #1)"
    )


# ---------------------------------------------------------------------------
# Parity trap #2 — clarify.defaults == engine _pipeline_defaults (verbatim)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workflow_id", sorted(PIPELINE_AGENTS))
def test_clarify_defaults_match_engine(workflow_id: str) -> None:
    plan = _compile(workflow_id)
    # od_prototype is an alias (no manifest); every real id resolves to itself.
    # An id present in the engine dict must match it verbatim; any id absent
    # (the *_revision manifests, reverse_engineer, chat) reuses the custom list.
    expected = _ENGINE_PIPELINE_DEFAULTS.get(workflow_id, _CUSTOM_DEFAULTS)
    assert plan.clarify.defaults == expected, (
        f"{workflow_id} clarify.defaults must reproduce the engine "
        f"_pipeline_defaults entry verbatim (engine.py:752-761)"
    )
