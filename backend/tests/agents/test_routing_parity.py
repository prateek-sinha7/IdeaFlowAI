"""Routing parity (07-04 / PARITY-05 + PARITY-09).

Proves the capability-routed engine path produces the SAME events + deliverable
as the legacy path for a scripted prototype build, AND that the routing is
genuinely capability-driven — the build step runs via the ``task_loop`` strategy
and the non-build steps via ``single_shot``, with NO ``spec.id == "prototype-build"``
branch reached on the routed path (INV-1).

The byte/event parity vs the post-0C baseline is locked by the
``test_characterization_*`` goldens (which now drive the ROUTED engine). This
test adds the routing-specific assertions the goldens cannot express: WHICH
strategy capability each step dispatched through, and that the build dispatch is
no longer keyed on the agent id.

Driven fully OFFLINE via the shared ``_drive`` harness (no DB / Bedrock / API key).
"""

from __future__ import annotations

import pytest

import agents.capabilities.strategies.single_shot as single_shot_mod
import agents.capabilities.strategies.task_loop as task_loop_mod
from agents.capabilities.registry import CapabilityRegistry
from tests.agents._scripted_model import _drive
from tests.agents.characterization import extract_final_output


@pytest.mark.asyncio
async def test_routed_prototype_dispatches_via_task_loop_and_single_shot(monkeypatch):
    """The routed prototype run dispatches build via task_loop, others via single_shot.

    Spies on each strategy capability's ``run`` to record WHICH agent each
    strategy handled, then asserts:
      * the build agent (``prototype-build``) ran via ``task_loop``;
      * every other agent (specify / plan / validate) ran via ``single_shot``;
      * NO agent was dispatched by a ``spec.id == "prototype-build"`` branch (the
        only build dispatch is the strategy resolution).
    """
    routed_via_task_loop: list[str] = []
    routed_via_single_shot: list[str] = []

    _orig_task_loop_run = task_loop_mod.TaskLoopStrategy.run
    _orig_single_shot_run = single_shot_mod.SingleShotStrategy.run

    async def _spy_task_loop(self, step, ctx):
        routed_via_task_loop.append(getattr(step, "agent_id", None))
        async for ev in _orig_task_loop_run(self, step, ctx):
            yield ev

    async def _spy_single_shot(self, step, ctx):
        routed_via_single_shot.append(getattr(step, "agent_id", None))
        async for ev in _orig_single_shot_run(self, step, ctx):
            yield ev

    monkeypatch.setattr(task_loop_mod.TaskLoopStrategy, "run", _spy_task_loop)
    monkeypatch.setattr(single_shot_mod.SingleShotStrategy, "run", _spy_single_shot)

    events = await _drive("prototype")
    assert events, "routed prototype produced no events"

    # The build agent routed through task_loop; the planning/validate agents through single_shot.
    assert "prototype-build" in routed_via_task_loop, (
        f"build step did NOT dispatch via task_loop (task_loop saw {routed_via_task_loop})"
    )
    assert "prototype-build" not in routed_via_single_shot, (
        "build step wrongly dispatched via single_shot"
    )
    for non_build in ("prototype-specify", "prototype-plan", "prototype-validate"):
        assert non_build in routed_via_single_shot, (
            f"{non_build} did NOT dispatch via single_shot (single_shot saw {routed_via_single_shot})"
        )
        assert non_build not in routed_via_task_loop, (
            f"{non_build} wrongly dispatched via task_loop"
        )


@pytest.mark.asyncio
async def test_routed_prototype_emits_task_loop_progress_and_html_deliverable():
    """The routed prototype build yields task_loop_progress + an HTML deliverable.

    ``task_loop_progress`` is the build-loop's per-task event — its presence proves
    the build dispatched through the per-task strategy, not a single-shot run. The
    deliverable is the prototype.html resolved through the ``single_file`` resolver.
    """
    events = await _drive("prototype")

    progress = [e for e in events if e.get("type") == "task_loop_progress"]
    assert progress, "routed prototype emitted no task_loop_progress (build loop did not run)"
    # The scripted prototype-plan emits exactly 2 tasks → 2 loop-progress events.
    task_numbers = sorted(e["data"]["task_number"] for e in progress)
    assert task_numbers == [1, 2], f"expected per-task progress for 2 tasks, got {task_numbers}"

    deliverable = extract_final_output(events)
    assert deliverable, "routed prototype produced an empty deliverable"
    assert "<" in deliverable and "section" in deliverable.lower(), (
        "routed prototype deliverable is not the built HTML"
    )


@pytest.mark.asyncio
async def test_routed_deliverable_resolution_is_capability_routed():
    """The deliverable resolves through the registry resolver, not _resolve_final_output.

    Spies on ``CapabilityRegistry.resolve`` to confirm a ``("deliverable", ...)``
    resolution happened during the routed run (single_file for prototype), proving
    the deliverable is sourced from ``compiled.deliverable.strategy`` (INV-1).
    """
    seen: list[tuple[str, str]] = []
    _orig_resolve = CapabilityRegistry.resolve

    def _spy_resolve(self, kind, name):
        seen.append((kind, name))
        return _orig_resolve(self, kind, name)

    import unittest.mock as _mock

    with _mock.patch.object(CapabilityRegistry, "resolve", _spy_resolve):
        events = await _drive("prototype")

    assert events, "routed prototype produced no events"
    assert ("deliverable", "single_file") in seen, (
        f"deliverable was NOT resolved via the single_file capability (resolves seen: {seen})"
    )
    assert ("strategy", "task_loop") in seen, "build did not resolve the task_loop strategy"
    assert ("strategy", "single_shot") in seen, "non-build steps did not resolve single_shot"
