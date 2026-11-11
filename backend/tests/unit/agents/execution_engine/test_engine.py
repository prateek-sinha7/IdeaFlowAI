"""``ExecutionEngine._apply_selections`` and connected-app grants (design 5.5 layer 3).

The overlay re-compiles the selections at ``trust="user"``, which admits
``tools.connectors``. The BASE plan decides whether those grants may reach a
step: only a plan that admits grants (Composer manifests) takes them.
"""

from __future__ import annotations

import dataclasses

import pytest

import asyncio
import logging
from typing import Any

from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from agents.execution_engine.run_tools import RunToolRequest
from tests.agents._scripted_model import (
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
    offline_db_seam,
)

_JIRA = "jira__get_issue"
_GITHUB = "github__list_issues"


@pytest.fixture
def predefined_plan():
    """A file-compiled plan: ``admits_connector_grants`` is False."""
    plan = compile_for_run("custom")
    assert plan.admits_connector_grants is False, "fixture assumption"
    return plan


@pytest.fixture
def admitting_plan(predefined_plan):
    return dataclasses.replace(predefined_plan, admits_connector_grants=True)


def _selection(agent_id: str, **tools: object) -> dict:
    return {agent_id: {"tools": dict(tools)}}


class TestApplySelectionsOnNonAdmittingPlan:
    def test_apply_selections_never_copies_connectors_when_plan_does_not_admit(
        self, predefined_plan
    ) -> None:
        agent_id = predefined_plan.steps[0].agent_id

        plan, _ = ExecutionEngine._apply_selections(
            predefined_plan,
            _selection(agent_id, connectors=[_JIRA, _GITHUB]),
            run_agent_ids=[agent_id],
        )

        assert all(s.tools.connectors == [] for s in plan.steps)

    def test_apply_selections_strips_path_b_steps_when_plan_does_not_admit(
        self, predefined_plan
    ) -> None:
        agent_id = predefined_plan.steps[0].agent_id

        _, user_map = ExecutionEngine._apply_selections(
            predefined_plan,
            _selection(agent_id, connectors=[_JIRA]),
            run_agent_ids=[agent_id, "composed-absent-agent"],
        )

        assert user_map, "fixture assumption: the selections compile at trust=user"
        assert all(step.tools.connectors == [] for step in user_map.values())

    def test_apply_selections_still_carries_other_tool_levers_when_connectors_dropped(
        self, predefined_plan
    ) -> None:
        agent_id = predefined_plan.steps[0].agent_id

        plan, _ = ExecutionEngine._apply_selections(
            predefined_plan,
            _selection(agent_id, write_files=True, connectors=[_JIRA]),
            run_agent_ids=[agent_id],
        )

        step = next(s for s in plan.steps if s.agent_id == agent_id)
        assert step.tools.write_files is True
        assert step.tools.connectors == []

    def test_apply_selections_keeps_base_plan_untouched_when_selections_name_connectors(
        self, predefined_plan
    ) -> None:
        agent_id = predefined_plan.steps[0].agent_id

        ExecutionEngine._apply_selections(
            predefined_plan,
            _selection(agent_id, connectors=[_JIRA]),
            run_agent_ids=[agent_id],
        )

        assert predefined_plan.admits_connector_grants is False
        assert all(s.tools.connectors == [] for s in predefined_plan.steps)

    def test_apply_selections_keeps_flag_false_on_returned_plan_when_overlaying(
        self, predefined_plan
    ) -> None:
        agent_id = predefined_plan.steps[0].agent_id

        plan, _ = ExecutionEngine._apply_selections(
            predefined_plan,
            _selection(agent_id, connectors=[_JIRA]),
            run_agent_ids=[agent_id],
        )

        assert plan.admits_connector_grants is False


class TestApplySelectionsOnAdmittingPlan:
    def test_apply_selections_copies_connectors_when_plan_admits(
        self, admitting_plan
    ) -> None:
        agent_id = admitting_plan.steps[0].agent_id

        plan, _ = ExecutionEngine._apply_selections(
            admitting_plan,
            _selection(agent_id, connectors=[_JIRA, _GITHUB]),
            run_agent_ids=[agent_id],
        )

        step = next(s for s in plan.steps if s.agent_id == agent_id)
        assert step.tools.connectors == [_JIRA, _GITHUB]
        assert plan.admits_connector_grants is True

    def test_apply_selections_applies_only_the_named_step_when_plan_admits(
        self, admitting_plan
    ) -> None:
        agent_id = admitting_plan.steps[0].agent_id

        plan, _ = ExecutionEngine._apply_selections(
            admitting_plan,
            _selection(agent_id, connectors=[_JIRA]),
            run_agent_ids=[agent_id],
        )

        others = [s for s in plan.steps if s.agent_id != agent_id]
        assert all(s.tools.connectors == [] for s in others)

    def test_apply_selections_switches_all_off_when_toggles_are_cleared(
        self, admitting_plan
    ) -> None:
        agent_id = admitting_plan.steps[0].agent_id
        saved_step = dataclasses.replace(
            admitting_plan.steps[0],
            tools=dataclasses.replace(
                admitting_plan.steps[0].tools, connectors=[_JIRA]
            ),
        )
        saved_plan = dataclasses.replace(
            admitting_plan, steps=[saved_step, *admitting_plan.steps[1:]]
        )

        plan, _ = ExecutionEngine._apply_selections(
            saved_plan,
            _selection(agent_id, connectors=[]),
            run_agent_ids=[agent_id],
        )

        step = next(s for s in plan.steps if s.agent_id == agent_id)
        assert step.tools.connectors == []

    def test_apply_selections_keeps_path_b_grants_when_plan_admits(
        self, admitting_plan
    ) -> None:
        agent_id = admitting_plan.steps[0].agent_id

        _, user_map = ExecutionEngine._apply_selections(
            admitting_plan,
            _selection(agent_id, connectors=[_JIRA]),
            run_agent_ids=[agent_id],
        )

        assert user_map[agent_id].tools.connectors == [_JIRA]

    def test_apply_selections_degrades_to_unmodified_plan_when_a_name_is_invalid(
        self, admitting_plan
    ) -> None:
        agent_id = admitting_plan.steps[0].agent_id

        plan, user_map = ExecutionEngine._apply_selections(
            admitting_plan,
            _selection(agent_id, connectors=["jira__not_a_jira_tool"]),
            run_agent_ids=[agent_id],
        )

        assert plan is admitting_plan
        assert user_map == {}


_SEAM_PIPELINE = "user_stories"
_SEAM_AGENT = "domain-analyst"
_SEAM_USER = "connector-seam-user"


def _seam_plan(*, admits: bool, connectors: list[str]):
    """The user_stories plan with the single step granting ``connectors``.

    Built with ``dataclasses.replace`` so the cached file plan is never mutated. The
    clarifier is switched off because the harness has no user to answer questions.
    """
    base = compile_for_run(_SEAM_PIPELINE)
    step = base.steps[0]
    granted = dataclasses.replace(
        step, tools=dataclasses.replace(step.tools, connectors=list(connectors))
    )
    return dataclasses.replace(
        base,
        steps=[granted, *base.steps[1:]],
        clarify=dataclasses.replace(base.clarify, mode="off"),
        admits_connector_grants=admits,
    )


def _jira_stub_tool():
    """A real LangChain tool named like the bound Jira tool, so the factory accepts it."""
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=lambda issue_key: "stub",
        name=_JIRA,
        description="Stub of the bound Jira get-issue tool.",
    )


class _RecordingBinder:
    """A RunToolBinder fake that records each request and answers as configured."""

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        *,
        raises: BaseException | None = None,
        hangs: bool = False,
    ) -> None:
        self.requests: list[RunToolRequest] = []
        self._result = result or {}
        self._raises = raises
        self._hangs = hangs

    async def __call__(self, request: RunToolRequest) -> dict[str, Any]:
        self.requests.append(request)
        if self._hangs:
            await asyncio.Event().wait()
        if self._raises is not None:
            raise self._raises
        return self._result


async def _drive_seam_run(
    plan,
    *,
    run_id: str,
    binder: _RecordingBinder | None,
) -> tuple[dict[str, Any], list[dict]]:
    """Run domain-analyst through ``execute()`` offline and capture what the factory got.

    Returns, per agent id, the ``run_tools`` and ``step_tools`` of the AgentContext handed
    to ``create_runner``, plus every event the run yielded. The user_stories plan runs all
    of its agents, so the domain-analyst entry is the one carrying the grant. Nothing touches a database
    or a model: the same offline seams the capabilities threading harness uses.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.registry import get_pipeline_agents

    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT
    spec = next(s for s in get_pipeline_agents(_SEAM_PIPELINE) if s.id == _SEAM_AGENT)

    captured: dict[str, dict[str, Any]] = {}
    orig_create_runner = factory_mod.create_runner
    orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(aid, ctx, **kw):
        captured[aid] = {"run_tools": dict(ctx.run_tools), "step_tools": ctx.step_tools}
        ctx.model = ScriptedFakeChatModel(
            [_ScriptedTurn(texts=["done"], usage=(10, 5))]
        )
        return orig_create_runner(aid, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    async def _fake_run_planner(
        user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs
    ):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover — make it an async generator

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    events: list[dict] = []
    try:
        with offline_db_seam():
            async for event in engine.execute(
                agents=[spec],
                user_message="Build me a thing for managing tasks.",
                pipeline_run_id=run_id,
                pipeline_type=_SEAM_PIPELINE,
                user_id=_SEAM_USER,
                od_context=None,
                gate_agent_ids=[],
                compiled_override=plan,
                run_tool_binder=binder,
            ):
                events.append(event)
    finally:
        factory_mod.create_runner = orig_create_runner
        if orig_engine_create_runner is not None:
            engine_mod.create_runner = orig_engine_create_runner

    return captured, events


class TestRunToolBinderSeam:
    """The run-entry seam: the binder runs once per run, only when the plan admits grants."""

    @pytest.mark.asyncio
    async def test_execute_binds_granted_tools_when_plan_admits_grants(self) -> None:
        run_id = "seam-bind-granted"
        tool = _jira_stub_tool()
        binder = _RecordingBinder({_JIRA: tool})

        captured, _ = await _drive_seam_run(
            _seam_plan(admits=True, connectors=[_JIRA]), run_id=run_id, binder=binder
        )

        assert binder.requests == [
            RunToolRequest(
                run_id=run_id,
                user_id=_SEAM_USER,
                tool_names=frozenset({_JIRA}),
            )
        ]
        assert captured[_SEAM_AGENT]["run_tools"] == {_JIRA: tool}
        assert captured[_SEAM_AGENT]["step_tools"].connectors == [_JIRA]
        # The pool is per run, but the grant is per step: a later step gets no grant.
        assert captured["epic-architect"]["step_tools"].connectors == []

    @pytest.mark.asyncio
    async def test_execute_skips_binder_when_plan_does_not_admit_grants(self) -> None:
        binder = _RecordingBinder({_JIRA: object()})

        captured, _ = await _drive_seam_run(
            _seam_plan(admits=False, connectors=[_JIRA]),
            run_id="seam-plan-not-admitted",
            binder=binder,
        )

        assert binder.requests == []
        assert captured[_SEAM_AGENT]["run_tools"] == {}

    @pytest.mark.asyncio
    async def test_execute_skips_binder_when_no_step_grants_a_connector(self) -> None:
        binder = _RecordingBinder({_JIRA: object()})

        captured, _ = await _drive_seam_run(
            _seam_plan(admits=True, connectors=[]),
            run_id="seam-no-grant",
            binder=binder,
        )

        assert binder.requests == []
        assert captured[_SEAM_AGENT]["run_tools"] == {}

    @pytest.mark.asyncio
    async def test_execute_runs_without_connector_tools_when_no_binder_is_given(
        self,
    ) -> None:
        captured, _ = await _drive_seam_run(
            _seam_plan(admits=True, connectors=[_JIRA]),
            run_id="seam-no-binder",
            binder=None,
        )

        assert captured[_SEAM_AGENT]["run_tools"] == {}

    @pytest.mark.asyncio
    async def test_execute_keeps_the_run_going_without_tools_when_binder_raises(
        self, caplog
    ) -> None:
        binder = _RecordingBinder(raises=RuntimeError("provider exploded"))

        with caplog.at_level(logging.ERROR, logger="agents.execution_engine.engine"):
            captured, _ = await _drive_seam_run(
                _seam_plan(admits=True, connectors=[_JIRA]),
                run_id="seam-binder-raises",
                binder=binder,
            )

        assert captured[_SEAM_AGENT]["run_tools"] == {}
        assert "run tool binding failed" in caplog.text
        assert "RuntimeError" in caplog.text
        assert "provider exploded" not in caplog.text

    @pytest.mark.asyncio
    async def test_execute_keeps_the_run_going_without_tools_when_binder_times_out(
        self, monkeypatch
    ) -> None:
        import agents.execution_engine.engine as engine_mod

        monkeypatch.setattr(engine_mod, "RUN_TOOL_BIND_TIMEOUT_SECONDS", 0.01)
        binder = _RecordingBinder(hangs=True)

        captured, _ = await _drive_seam_run(
            _seam_plan(admits=True, connectors=[_JIRA]),
            run_id="seam-binder-hangs",
            binder=binder,
        )

        assert len(binder.requests) == 1
        assert captured[_SEAM_AGENT]["run_tools"] == {}
