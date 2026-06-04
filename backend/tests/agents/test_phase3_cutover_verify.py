"""Phase-3 verify gate (task #46) — durable forward guards for the all-pipelines
runtime cutover (custom ``DeepAgent`` → LangChain ``deepagents`` via
``create_runner`` + the engine's single ``astream_events`` loop).

This module is the COMMITTED regression net. The full old-vs-new WS event-parity
capture (P1) was a transient harness (a ``git worktree`` at the pre-cutover HEAD
vs the working tree); it + the OLD engine were removed in Phase 7a. The tests
HERE are the durable guards that survive that deletion:

  1. ``TestCheckpointResume`` — P3. With the dev checkpointer (``InMemorySaver``)
     and a scripted model, a ``DeepAgentRunner`` armed with ``interrupt_on`` PAUSES
     at the gated tool (``gate`` event + a persisted interrupt on the graph state),
     and ``Command(resume={"decisions":[{"type":"approve"}]})`` on the SAME
     ``thread_id`` RESUMES the SAME graph to a terminal state with the gated tool
     executed. Proves IN-PROCESS / graph-level checkpoint resume on the dev
     checkpointer. (True cross-process resume-after-kill needs Postgres — out of
     scope for the offline suite; see the task report.)

  2. ``TestNewEngineEventVocabulary`` — forward regression. Drives the NEW engine
     end-to-end offline (scripted model) for a TEXT pipeline and a PROTOTYPE build,
     and asserts the emitted event-type vocabulary + each event's ``data`` key-shape
     conform to the documented WebSocket contract (the exact ``{type, data}`` set the
     ``websocket.py`` drainer forwards verbatim). Guards against a future change
     silently adding/dropping an event type or reshaping a payload the UI relies on.

The scripted-model recipe + the offline ``engine.execute()`` driver live in
``tests/agents/_scripted_model.py`` (imported here) so the harness and the durable
guards share one source of truth.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn, _drive


# ===========================================================================
# P3 — in-process checkpoint pause/resume on the dev InMemorySaver
# ===========================================================================


GATED_TOOL = "report_task_complete"


@tool
def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
    """Report that a build task has been completed (gated for HITL in this test)."""
    return f"✓ Task {task_number} complete: {task_title}"


def _hitl_script() -> list[_ScriptedTurn]:
    """Turn 1: text + a call to the gated tool (triggers the interrupt).
    Turn 2 (consumed only after resume): final text."""
    return [
        _ScriptedTurn(
            texts=["working "],
            tool_calls=[
                (GATED_TOOL, json.dumps({"task_number": 1, "task_title": "Shell", "summary": "x"}), "call_1")
            ],
            usage=(11, 7),
        ),
        _ScriptedTurn(texts=["all done"], usage=(13, 5)),
    ]


class TestCheckpointResume:
    """P3: prove graph-level checkpoint pause→resume on the dev InMemorySaver."""

    @pytest.mark.asyncio
    async def test_pause_then_resume_same_thread(self) -> None:
        from app.agents.deep_agent_runner import DeepAgentRunner

        checkpointer = InMemorySaver()
        thread_id = "phase3-resume-thread"
        runner = DeepAgentRunner(
            system_prompt="You are a test agent.",
            tools=[report_task_complete],
            model=ScriptedFakeChatModel(_hitl_script()),
            checkpointer=checkpointer,
            thread_id=thread_id,
            interrupt_on={GATED_TOOL: True},
        )

        # ── Drive until the gate fires (pause persisted to the checkpoint). ──
        saw_gate = False
        saw_done = False
        gate_payload: dict | None = None
        async for ev in runner.astream_events("go"):
            if ev["type"] == "gate":
                saw_gate = True
                gate_payload = ev["interrupt"]
            elif ev["type"] == "done":
                saw_done = True

        assert saw_gate, "armed run must PAUSE at the gated tool and emit a 'gate' event"
        assert not saw_done, "'gate' and 'done' are mutually exclusive — paused run never 'done'"
        assert gate_payload and gate_payload.get("interrupt_ids"), (
            "gate payload must carry interrupt_ids (the resume handles)"
        )
        # The pending action_request references the gated tool.
        names = [a.get("name") for a in (gate_payload.get("action_requests") or [])]
        assert GATED_TOOL in names, f"gate must reference the gated tool; got {names}"

        # ── The checkpoint persists the pause: re-reading state shows it paused. ──
        state_before = await runner._graph.aget_state(runner.config)
        assert state_before.next, "checkpointed state must show a pending (paused) node"
        assert thread_id == runner.config["configurable"]["thread_id"]

        # ── RESUME the SAME graph on the SAME thread_id via Command(resume). ──
        n_actions = len(gate_payload.get("action_requests") or [])
        resume_value = {"decisions": [{"type": "approve"}] * max(1, n_actions)}
        await runner._graph.ainvoke(Command(resume=resume_value), runner.config)

        # ── After resume: terminal state, and the gated tool actually executed. ──
        final_state = await runner._graph.aget_state(runner.config)
        assert final_state.next == (), (
            f"resumed graph must reach a terminal state; next={final_state.next!r}"
        )
        from langchain_core.messages import ToolMessage

        msgs = final_state.values.get("messages", [])
        tool_msgs = [
            m for m in msgs
            if isinstance(m, ToolMessage) and getattr(m, "name", "") == GATED_TOOL
        ]
        assert tool_msgs, "after approve+resume, the gated tool must have executed (ToolMessage present)"

    @pytest.mark.asyncio
    async def test_resume_continues_from_checkpoint_not_restart(self) -> None:
        """Re-invoking on the same thread_id continues from the checkpoint.

        A fresh thread would re-run turn 1 (text 'working' + the gated call). Because
        the resume continues the SAME checkpointed graph, the post-resume model turn
        is turn 2 ('all done') — proving the checkpoint carried the conversation
        forward rather than restarting it.
        """
        from app.agents.deep_agent_runner import DeepAgentRunner

        runner = DeepAgentRunner(
            system_prompt="You are a test agent.",
            tools=[report_task_complete],
            model=ScriptedFakeChatModel(_hitl_script()),
            checkpointer=InMemorySaver(),
            thread_id="phase3-resume-thread-2",
            interrupt_on={GATED_TOOL: True},
        )
        async for ev in runner.astream_events("go"):
            if ev["type"] == "gate":
                break

        result = await runner._graph.ainvoke(
            Command(resume={"decisions": [{"type": "approve"}]}), runner.config
        )
        # The final AI message after resume is turn 2's text ("all done"),
        # confirming the script advanced past turn 1 (no restart).
        from langchain_core.messages import AIMessage

        ai_texts = [
            m.content for m in result.get("messages", []) if isinstance(m, AIMessage)
        ]
        joined = " ".join(t for t in ai_texts if isinstance(t, str))
        assert "all done" in joined, (
            f"resumed run must continue to turn 2 ('all done'), not restart; got {ai_texts!r}"
        )


# ===========================================================================
# Forward regression — the NEW engine's emitted WS event vocabulary
# ===========================================================================


# The documented outbound WS contract (the union of event TYPEs the engine can
# emit, forwarded verbatim by the websocket.py drainer). A scripted offline run
# exercises the streaming subset; this list is the allowed vocabulary the run's
# events must be a subset of.
_DOCUMENTED_EVENT_TYPES = frozenset(
    {
        "workflow_validated",
        "planner_start",
        "planner_complete",
        "planner_timeout",
        "gate_status",
        "pipeline_start",
        "agent_start",
        "agent_input",
        "agent_chunk",
        "tool_call",
        "tool_result",
        "task_progress",
        "task_loop_progress",
        "agent_complete",
        "agent_error",
        "review_gate_ready",
        "review_gate_approved",
        "pipeline_complete",
        "pipeline_cancelled",
        "error",
        "summary",
        "state_restoration_failed",
    }
)

# Required data-key shapes for the load-bearing streaming events (the keys the
# frontend reducer reads). Asserted as a SUBSET check (engine may add keys, but
# must not drop these).
_REQUIRED_DATA_KEYS = {
    "agent_start": {"agent_id", "name", "role", "icon", "index", "total"},
    "agent_chunk": {"agent_id", "chunk"},
    "agent_complete": {"agent_id", "name", "duration", "output_length",
                        "input_tokens", "output_tokens", "total_tokens"},
    "tool_call": {"agent_id", "tool", "args"},
    "tool_result": {"agent_id", "tool", "result"},
    "task_progress": {"agent_id", "pipeline_run_id", "completed_tasks",
                      "completed_count", "timestamp"},
    "task_loop_progress": {"agent_id", "pipeline_run_id", "task_number",
                           "total_tasks", "timestamp"},
    "pipeline_complete": {"pipeline_type", "pipeline_run_id", "final_output",
                          "total_input_tokens", "total_output_tokens", "total_tokens"},
}


class TestNewEngineEventVocabulary:
    """Forward guard: the NEW engine emits ONLY documented event types with the
    documented payload key-shapes, for a scripted text run and a prototype build."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pipeline_type", ["user_stories", "prototype"])
    async def test_event_vocabulary_conforms_to_contract(self, pipeline_type: str) -> None:
        events = await _drive(pipeline_type, "new")
        assert events, f"{pipeline_type}: NEW engine produced no events"

        seen_types = {e.get("type") for e in events}
        # Every emitted type is in the documented vocabulary (no surprise types).
        unknown = seen_types - _DOCUMENTED_EVENT_TYPES
        assert not unknown, (
            f"{pipeline_type}: NEW engine emitted UNDOCUMENTED event type(s) the "
            f"frontend does not handle: {sorted(unknown)}"
        )

        # Each load-bearing event carries (at least) its documented data keys.
        for ev in events:
            t = ev.get("type")
            required = _REQUIRED_DATA_KEYS.get(t)
            if required is None:
                continue
            data = ev.get("data", {})
            missing = required - set(data.keys())
            assert not missing, (
                f"{pipeline_type}: event '{t}' is MISSING required data keys "
                f"{sorted(missing)} (UI depends on them); got {sorted(data.keys())}"
            )

    @pytest.mark.asyncio
    async def test_text_pipeline_core_sequence(self) -> None:
        """A text pipeline must bracket each agent with start/input/…/complete and
        bookend the run with pipeline_start … pipeline_complete."""
        events = await _drive("user_stories", "new")
        types = [e.get("type") for e in events]
        assert types[0] == "workflow_validated"
        assert "pipeline_start" in types
        assert types[-1] == "pipeline_complete"
        # Every agent_start is eventually followed by an agent_complete (or error).
        assert types.count("agent_start") == types.count("agent_complete"), (
            f"each agent_start must pair with an agent_complete; got {types}"
        )

    @pytest.mark.asyncio
    async def test_prototype_build_emits_task_progress_from_tool_args(self) -> None:
        """The prototype build derives task_progress from report_task_complete args.

        Confirms the Phase-3 mechanism: the build agent's report_task_complete
        tool call (task_number/task_title/summary) yields a task_progress event
        whose completed_tasks item carries number/title/summary — the SAME payload
        shape the pre-cutover engine produced from PrototypeArtifactStore.
        """
        events = await _drive("prototype", "new")
        tps = [e for e in events if e.get("type") == "task_progress"]
        assert tps, "prototype build must emit at least one task_progress event"
        for tp in tps:
            data = tp.get("data", {})
            ctasks = data.get("completed_tasks") or []
            assert ctasks, "task_progress must carry a non-empty completed_tasks list"
            item = ctasks[0]
            assert set(item.keys()) == {"number", "title", "summary"}, (
                f"completed_tasks item must be {{number,title,summary}}; got {sorted(item.keys())}"
            )
            assert item["number"] == 1 and item["title"] == "Build shell", (
                f"task_progress payload must reflect the report_task_complete args; got {item}"
            )


# ===========================================================================
# Task #49 — completed_count is CUMULATIVE across the build loop (regression net)
# ===========================================================================


class TestCumulativeTaskProgress:
    """Durable guard for the #49 regression: the prototype build's
    ``task_progress.completed_count`` must accumulate (1,2,3,…) across the
    build loop's per-task ``prototype-build`` invocations — NOT reset to 1 each
    task.

    The pre-cutover engine got this from a run-shared ``PrototypeArtifactStore``
    created once per run; the Phase-3 cutover derives it from
    ``report_task_complete`` tool events instead, which (before #49) were
    accumulated in a list LOCAL to ``_run_agent`` — and ``_run_build_task_loop``
    calls ``_run_agent`` fresh once per task, so the local reset every task and
    ``completed_count`` was stuck at 1 (the frontend's ``protoCompletedTaskCount``
    went non-monotonic: 0,1,1,1,2,1). The fix moves the list to run-level
    (``engine._completed_tasks``, initialized in ``execute()``).

    This test drives ``_run_build_task_loop`` directly (engine-level, scripted
    model, temp sandbox) for a 3-task and a 1-task build and asserts the emitted
    ``completed_count`` sequence is cumulative+monotonic. It survives the Phase-7
    deletion of the old engine + the transient old-vs-new worktree parity harness.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "n_tasks,expected_counts",
        [(3, [1, 2, 3]), (1, [1])],
    )
    async def test_completed_count_accumulates_across_build_loop(
        self, n_tasks: int, expected_counts: list[int], tmp_path, monkeypatch
    ) -> None:
        import agents.execution_engine.engine as engine_mod
        from app.agents.deep_agent_runner import DeepAgentRunner
        from app.agents.sandbox import RunSandbox
        from app.core.config import settings as _settings

        # Per-run sandbox in a temp dir (the real /app/runs is absent locally).
        monkeypatch.setattr(_settings, "RUNS_ROOT", str(tmp_path))

        # ── Scripted prototype-build model: each per-task invocation calls
        #    report_task_complete(task_number=<the loop's current task>) once. The
        #    build loop sets accumulated_outputs["_build_task_number"] before each
        #    call; the runner consumes a fresh model per call, so we hand each
        #    create_runner call a model scripted with that call's task number. ──
        def _build_turns(task_number: int) -> list[_ScriptedTurn]:
            return [
                _ScriptedTurn(
                    texts=["building "],
                    tool_calls=[
                        (
                            "report_task_complete",
                            json.dumps(
                                {
                                    "task_number": task_number,
                                    "task_title": f"Task {task_number}",
                                    "summary": f"did task {task_number}",
                                }
                            ),
                            f"call_{task_number}",
                        )
                    ],
                    usage=(10, 5),
                ),
                _ScriptedTurn(texts=["done"], usage=(4, 2)),
            ]

        # The build loop calls create_runner once per task, in order; a closure
        # counter gives each scripted model its task number. (The real engine
        # passes the task number to the model via _build_context_message, which
        # reads accumulated_outputs directly — but ctx.agent_outputs handed to the
        # runner is the FILTERED consumes-set, which strips _build_task_number, so
        # we can't read it off ctx here. The count under test = len of the
        # cumulative list and is independent of the reported number regardless.)
        _task_counter = {"n": 0}

        def _patched_create_runner(agent_id, ctx, **kw):
            _task_counter["n"] += 1
            tn = _task_counter["n"]
            rs = RunSandbox(ctx.user_id or "anon", ctx.run_id)
            rs.ensure()
            return DeepAgentRunner(
                system_prompt="build agent",
                tools=[report_task_complete],
                model=ScriptedFakeChatModel(_build_turns(tn)),
                run_sandbox=rs,
                checkpointer=kw.get("checkpointer"),
                thread_id=kw.get("thread_id"),
            )

        monkeypatch.setattr(engine_mod, "create_runner", _patched_create_runner)

        engine = engine_mod.ExecutionEngine()
        # Mirror execute()'s per-run init of the cumulative list (the unit under
        # test). _run_build_task_loop/_run_agent read engine._completed_tasks.
        engine._completed_tasks = []
        engine._checkpointer = None
        engine._disk_skills = {}
        engine._gate_agent_ids = []  # suppress the inter-agent review gate

        # Artifact store writes → no-op (the fake run_id has no workflow_runs row,
        # so a real INSERT fails the FK and would abort the loop). Same neutralizer
        # the _scripted_model driver applies; orthogonal to the count being tested.
        async def _noop_store(*a, **k):
            return "artifact-id"

        engine._store.store = _noop_store  # type: ignore[assignment]

        run_id = f"cumcount-{n_tasks}"
        engine._state_machine.transition(run_id, "generating")

        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()

        # A minimal prototype-build spec (real loader spec would also work; this
        # keeps the test independent of AGENT.md content).
        build_spec = next(
            s for s in __import__("agents.registry", fromlist=["get_pipeline_agents"]).get_pipeline_agents("prototype")
            if s.id == "prototype-build"
        )

        # Planner output with exactly n_tasks "## Task N:" headers so the loop runs
        # _run_agent that many times.
        plan = "\n\n".join(f"## Task {i}: do thing {i}\nbody" for i in range(1, n_tasks + 1))
        accumulated_outputs: dict[str, str] = {"prototype-plan": plan}
        results: list[dict] = []

        counts: list[int] = []
        async for ev in engine._run_build_task_loop(
            build_spec, 2, [build_spec], "build me a thing", accumulated_outputs,
            sandbox, run_id, "prototype", {}, None, None, None, results, None,
        ):
            if ev.get("type") == "task_progress":
                counts.append(ev["data"]["completed_count"])

        assert counts == expected_counts, (
            f"completed_count must be cumulative+monotonic across {n_tasks} build "
            f"tasks; expected {expected_counts}, got {counts}"
        )
        # Monotonic non-decreasing (the UI-identity property the regression broke).
        assert all(b >= a for a, b in zip(counts, counts[1:], strict=False)), (
            f"completed_count must never decrease mid-build; got {counts}"
        )
        # The cumulative list carries one item per completed task, in order.
        assert [t["number"] for t in engine._completed_tasks] == list(range(1, n_tasks + 1))
