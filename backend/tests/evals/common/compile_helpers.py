"""Reusable helpers for "pin compile_for_run(<id>)'s shape" tests (the L2
pattern) — usable by any pipeline, not just prototype_revision. Each
pipeline's own test supplies its own expected values; only the assertion
machinery is shared here.
"""

from __future__ import annotations

_UNSET = object()  # distinguishes "don't check this field" from "assert it equals None"


def compile_pipeline(pipeline_type: str):
    """Thin wrapper around compile_for_run — centralizes the import so
    pipeline test files don't each import agents.execution_engine.engine
    directly."""
    from agents.execution_engine.engine import compile_for_run

    return compile_for_run(pipeline_type)


def assert_step_agent_ids(compiled, expected_ids: list[str]) -> None:
    assert [s.agent_id for s in compiled.steps] == expected_ids


def assert_step_capabilities(
    step,
    *,
    strategy=_UNSET,
    gates=_UNSET,
    validators=_UNSET,
    post_step=_UNSET,
    require_render=_UNSET,
) -> None:
    """Only checks fields the caller actually passes — an OMITTED kwarg
    skips that check; a kwarg explicitly passed as ``None`` (e.g.
    ``post_step=None``) asserts the field IS None, it does not skip the
    check. (A plain ``None`` default would make those indistinguishable —
    exactly the bug this sentinel avoids.)
    """
    if strategy is not _UNSET:
        assert step.strategy == strategy
    if gates is not _UNSET:
        assert step.gates == gates
    if validators is not _UNSET:
        assert step.validators == validators
    if post_step is not _UNSET:
        assert step.post_step == post_step
    if require_render is not _UNSET:
        assert step.require_render == require_render


def assert_deliverable(
    compiled,
    *,
    strategy: str,
    name: str,
    revises_existing: bool | None = None,
) -> None:
    d = compiled.deliverable
    assert d.strategy == strategy
    assert d.name == name
    if revises_existing is not None:
        assert d.revises_existing == revises_existing
