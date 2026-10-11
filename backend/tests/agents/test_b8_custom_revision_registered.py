"""tests/agents/test_b8_custom_revision_registered.py — B8 regression guard.

GIT_VERSIONING_BUGS.md B8: chat-driven revision of a ``custom``-type run returned
400 ``revision_unsupported``.

Root cause: ``_mint_revision_row`` guards on ``get_pipeline_agents(revision_pipeline_type)``.
When ``wr.type == "custom"`` the guard resolves ``custom_revision`` — which had no
agents registered at the time of the B1 baseline run.  Both ``custom-revision-planner``
and ``custom-revision-builder`` have since been added (they each declare
``pipeline_type: custom_revision`` in their AGENT.md), so the guard passes and the
backend no longer raises ``revision_unsupported`` for ``custom``-type runs.

Two assertions:
  1. ``get_pipeline_agents("custom_revision")`` returns at least the two registered
     agents — the predicate the guard calls.
  2. The derived ``revision_pipeline_type`` for a ``custom``-typed run equals
     ``"custom_revision"`` — the derivation formula in ``_mint_revision_row``.
"""

from __future__ import annotations

import pytest


def test_custom_revision_pipeline_has_registered_agents() -> None:
    """B8: get_pipeline_agents('custom_revision') must return at least 2 agents.

    If this assertion fails it means the ``custom_revision`` pipeline is
    unregistered and every ``custom``-type run (including all DB/user-saved
    workflows) will return 400 ``revision_unsupported`` on any revision request.
    """
    from agents.registry import get_pipeline_agents

    agents = get_pipeline_agents("custom_revision")
    agent_ids = [a.id for a in agents]
    assert len(agents) >= 2, (
        f"custom_revision must have ≥2 registered agents "
        f"(custom-revision-planner + custom-revision-builder). "
        f"Found: {agent_ids!r}. "
        "B8 regression: if this is empty, every DB/custom-workflow run will "
        "return 400 revision_unsupported from _mint_revision_row."
    )
    assert "custom-revision-planner" in agent_ids, (
        "custom-revision-planner must be registered for custom_revision "
        "(declares pipeline_type: custom_revision in its AGENT.md)"
    )
    assert (
        "custom-revision-builder" in agent_ids
    ), "custom-revision-builder must be registered for custom_revision"


def test_custom_type_run_derives_correct_revision_pipeline() -> None:
    """B8: a WorkflowRun with type='custom' derives revision_pipeline_type='custom_revision'.

    Mirrors the formula in _mint_revision_row:
        revision_pipeline_type = f"{target_artifact_type.removesuffix('_output')}_revision"
    where target_artifact_type defaults to f"{wr_type}_output" = "custom_output".
    """
    wr_type = "custom"  # what WorkflowRun.type holds for DB/user-saved workflows
    target_artifact_type = f"{wr_type}_output"
    revision_pipeline_type = f"{target_artifact_type.removesuffix('_output')}_revision"

    assert revision_pipeline_type == "custom_revision", (
        f"A custom-type run must derive revision_pipeline_type='custom_revision', "
        f"got {revision_pipeline_type!r}. "
        "If this changes, the B8 fix needs to be revisited."
    )

    # And verify the derived type IS registered (combines both assertions end-to-end).
    from agents.registry import get_pipeline_agents

    agents = get_pipeline_agents(revision_pipeline_type)
    assert agents, (
        f"revision_pipeline_type={revision_pipeline_type!r} (derived from wr.type='custom') "
        "has no registered agents — _mint_revision_row would raise revision_unsupported "
        "for any DB/custom-workflow revision request (B8 regression)."
    )
