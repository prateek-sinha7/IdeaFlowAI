"""Unit tests for ``app.agents.workflow_builder.middleware``.

Covers the observer's label table, the write scope, the paired ``tool_started`` /
``tool_finished`` events (also on a refusal), the status mapping for script
results, the 80 % warning and one-time limit notice, the refusal after the
tool-call cap, the stored tool row, and the pinned-message guard. The turn is a
``FakeTurnPort``; no graph or model runs.

Requirements: 20.7, 27.3, 28.3, 28.9, 38.7, 38.8, 38.9, 39.4, 39.5, 39.6, 39.7,
39.8, 47.8, 49.2.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.agents.workflow_builder.backend_fs import SKILL_READ_ONLY_MESSAGE
from app.agents.workflow_builder.events import (
    BuilderEvent,
    LimitWarning,
    ToolFinished,
    ToolStarted,
)
from app.agents.workflow_builder.middleware import (
    MAX_SUMMARY_CHARS,
    TOOL_LIMIT_MESSAGE,
    WRITE_SCOPE_MESSAGE,
    BuilderToolObserverMiddleware,
    PinnedTurnMessageMiddleware,
    cap_summary,
    is_under_workflows,
    normalise_virtual_path,
)
from app.agents.workflow_builder.ports import TurnLimits
from app.agents.workflow_builder.stages import ToolStarted as ToolStartedSignal
from tests.fakes.builder_turn import FakeTurnPort

_SKILL = "/skills/velocity-workflow-creator"
_SCRIPTS = f"python {_SKILL}/scripts"
_MANIFEST = "/workflows/a.workflow.json"


def _request(
    name: str, args: dict[str, Any], call_id: str = "call-1"
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": call_id, "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


class _Handler:
    """A tool handler that returns a fixed result and counts its calls."""

    def __init__(self, content: str = "done", *, status: str = "success") -> None:
        self.content = content
        self.status = status
        self.calls = 0

    async def __call__(self, request: ToolCallRequest) -> ToolMessage:
        self.calls += 1
        return ToolMessage(
            content=self.content,
            tool_call_id=request.tool_call["id"] or "",
            name=request.tool_call["name"],
            status=self.status,  # type: ignore[arg-type]
        )


def _limits(max_tool_calls: int = 10) -> TurnLimits:
    return TurnLimits(
        timeout_seconds=600,
        max_tool_calls=max_tool_calls,
        max_gate_rejections=2,
        warning_fraction=0.8,
    )


async def _call(
    middleware: BuilderToolObserverMiddleware,
    name: str,
    args: dict[str, Any],
    handler: _Handler | None = None,
    call_id: str = "call-1",
) -> ToolMessage:
    result = await middleware.awrap_tool_call(
        _request(name, args, call_id), handler or _Handler()
    )
    assert isinstance(result, ToolMessage)
    return result


def _of_type[T: BuilderEvent](events: list[BuilderEvent], kind: type[T]) -> list[T]:
    return [event for event in events if isinstance(event, kind)]


# --- Pure helpers -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/workflows/a.json", "/workflows/a.json"),
        ("workflows/a.json", "/workflows/a.json"),
        ("//workflows/a.json", "/workflows/a.json"),
        ("\\workflows\\a.json", "/workflows/a.json"),
        ("/workflows/../skills/x", "/skills/x"),
        ("/../../etc", "/etc"),
    ],
)
def test_normalise_virtual_path_returns_absolute_path_when_input_is_any_form(
    raw: str, expected: str
) -> None:
    assert normalise_virtual_path(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/workflows/a.json", True),
        ("/workflows/../other.md", False),
        ("/workflows", False),
        ("/workflows2/a.json", False),
        ("/skills/a.md", False),
    ],
)
def test_is_under_workflows_matches_folder_when_path_is_normalised(
    raw: str, expected: bool
) -> None:
    assert is_under_workflows(raw) is expected


def test_cap_summary_returns_text_unchanged_when_within_limit() -> None:
    assert cap_summary("one\n two   three") == "one two three"


def test_cap_summary_cuts_to_limit_when_text_is_too_long() -> None:
    capped = cap_summary("word " * 200)

    assert len(capped) <= MAX_SUMMARY_CHARS
    assert capped.endswith("...")


# --- Label table --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args", "kind", "label"),
    [
        ("read_file", {"file_path": f"{_SKILL}/SKILL.md"}, "read", "Read SKILL.md"),
        ("read_file", {"path": "/a/b.md"}, "read", "Read b.md"),
        ("read_file", {}, "read", "Read a file"),
        ("write_file", {"file_path": _MANIFEST}, "write", "Wrote a.workflow.json"),
        ("edit_file", {"file_path": _MANIFEST}, "write", "Edited a.workflow.json"),
        ("ls", {}, "read", "Listed files"),
        ("glob", {}, "read", "Searched for files"),
        ("grep", {}, "read", "Searched file contents"),
        ("write_todos", {}, "read", "Updated the plan"),
        ("list_my_agents", {}, "lookup", "Looked up your agents"),
        ("list_my_skills", {}, "lookup", "Looked up your skills"),
        ("list_my_workflow_names", {}, "lookup", "Looked up your workflow names"),
        ("list_my_connectors", {}, "lookup", "Looked up your connectors"),
        ("list_handoff_targets", {}, "lookup", "Looked up the handoff targets"),
        ("get_builder_models", {}, "lookup", "Looked up the models"),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/catalog_lookup.py overview --trust user"},
            "lookup",
            "Looked up the catalog",
        ),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/validate_manifest.py {_MANIFEST}"},
            "script",
            "Checked the workflow",
        ),
        (
            "run_skill_script",
            {
                "command": f"{_SCRIPTS}/validate_manifest.py {_MANIFEST} --compiler backend"
            },
            "script",
            "Checked the workflow with the platform",
        ),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/selftest.py"},
            "script",
            "Ran the skill self-test",
        ),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/refresh_catalog.py --check"},
            "script",
            "Checked the catalog snapshot",
        ),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/schema_sync.py --check"},
            "script",
            "Checked the schema copy",
        ),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/export_manifest.py {_MANIFEST}"},
            "script",
            "Exported the workflow",
        ),
        (
            "run_skill_script",
            {"command": f"{_SCRIPTS}/other.py"},
            "script",
            "Ran a skill script",
        ),
        (
            "propose_draft",
            {"path": _MANIFEST},
            "propose",
            "Sent the workflow to the platform check",
        ),
        ("something_else", {}, "read", "Ran a tool"),
    ],
)
async def test_awrap_tool_call_publishes_kind_and_label_when_tool_starts(
    tool: str, args: dict[str, Any], kind: str, label: str
) -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)

    await _call(middleware, tool, args)

    started = _of_type(turn.events, ToolStarted)
    assert [(e.tool, e.kind, e.label) for e in started] == [(tool, kind, label)]


async def test_awrap_tool_call_sets_command_when_tool_is_a_script() -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    command = f"{_SCRIPTS}/catalog_lookup.py   overview\n--trust user"

    await _call(middleware, "run_skill_script", {"command": command})
    await _call(middleware, "ls", {}, call_id="call-2")

    started = _of_type(turn.events, ToolStarted)
    assert started[0].command == " ".join(command.split())
    assert started[1].command is None


async def test_awrap_tool_call_signals_stage_input_when_script_runs() -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    command = f"{_SCRIPTS}/catalog_lookup.py search models --trust user"

    await _call(middleware, "run_skill_script", {"command": command})

    assert turn.signals == [
        ToolStartedSignal(
            name="run_skill_script",
            path=None,
            script="catalog_lookup.py",
            subcommand="search",
            check=False,
        )
    ]


# --- Pairing, status and summary ----------------------------------------------------


async def test_awrap_tool_call_pairs_started_and_finished_when_tool_succeeds() -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)

    await _call(middleware, "ls", {}, call_id="c-9")

    assert [type(e) for e in turn.events] == [ToolStarted, ToolFinished]
    finished = _of_type(turn.events, ToolFinished)[0]
    assert finished.call_id == "c-9"
    assert finished.status == "ok"
    assert finished.summary == "Listed files."
    assert [row.activity.call_id for row in turn.finished] == ["c-9"]


@pytest.mark.parametrize(
    ("content", "message_status", "expected"),
    [
        ("$ x\nexit code: 0\nhello", "success", "ok"),
        ("$ x\nexit code: 2\nboom", "success", "error"),
        ("$ x\nexit code: timed out\n", "success", "timed_out"),
        (
            "$ x\nexit code: none\nThe script did not finish because the turn stopped.",
            "success",
            "stopped",
        ),
        ("Refused: not allowed", "success", "refused"),
        ("runner crashed", "error", "error"),
    ],
)
async def test_awrap_tool_call_maps_status_when_script_result_has_given_header(
    content: str, message_status: str, expected: str
) -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    handler = _Handler(content, status=message_status)

    await _call(
        middleware,
        "run_skill_script",
        {"command": f"{_SCRIPTS}/selftest.py"},
        handler,
    )

    assert _of_type(turn.events, ToolFinished)[0].status == expected
    assert turn.finished[0].activity.status == expected


async def test_awrap_tool_call_reports_timed_out_when_turn_cap_stopped_the_script() -> (
    None
):
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn, stopped_by_turn_cap=lambda: True)
    handler = _Handler(
        "$ x\nexit code: none\nThe script did not finish because the turn stopped."
    )

    await _call(
        middleware,
        "run_skill_script",
        {"command": f"{_SCRIPTS}/selftest.py"},
        handler,
    )

    assert _of_type(turn.events, ToolFinished)[0].status == "timed_out"
    assert turn.finished[0].activity.status == "timed_out"


async def test_awrap_tool_call_reports_ok_when_validator_exits_with_one() -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    handler = _Handler("$ x\nexit code: 1\nINVALID: 2 error(s), 0 warning(s)\n")

    await _call(
        middleware,
        "run_skill_script",
        {"command": f"{_SCRIPTS}/validate_manifest.py {_MANIFEST}"},
        handler,
    )

    finished = _of_type(turn.events, ToolFinished)[0]
    assert finished.status == "ok"
    assert finished.summary == "Checked the workflow. Exit code 1."
    assert turn.finished[0].call.verdict == "invalid"
    assert turn.finished[0].activity.exit_code == 1


async def test_awrap_tool_call_keeps_summary_short_and_free_of_output_when_result_is_long() -> (
    None
):
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    secret = "SECRET-TOKEN-" * 100
    handler = _Handler(f"$ x\nexit code: 0\n{secret}")

    await _call(
        middleware, "run_skill_script", {"command": f"{_SCRIPTS}/selftest.py"}, handler
    )

    summary = _of_type(turn.events, ToolFinished)[0].summary
    assert len(summary) <= MAX_SUMMARY_CHARS
    assert "SECRET-TOKEN" not in summary


async def test_awrap_tool_call_publishes_error_finish_and_reraises_when_handler_raises() -> (
    None
):
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)

    async def failing(request: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware.awrap_tool_call(_request("ls", {}), failing)

    assert [type(e) for e in turn.events] == [ToolStarted, ToolFinished]
    assert _of_type(turn.events, ToolFinished)[0].status == "error"


@pytest.mark.parametrize(
    ("capped", "expected"),
    [(True, "timed_out"), (False, "stopped")],
    ids=["turn-cap", "plain-cancel"],
)
async def test_awrap_tool_call_finishes_by_stop_reason_when_handler_is_cancelled(
    capped: bool, expected: str
) -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn, stopped_by_turn_cap=lambda: capped)

    async def cancelled(request: ToolCallRequest) -> ToolMessage:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await middleware.awrap_tool_call(_request("ls", {}), cancelled)

    assert [type(e) for e in turn.events] == [ToolStarted, ToolFinished]
    assert _of_type(turn.events, ToolFinished)[0].status == expected


async def test_awrap_tool_call_still_returns_result_when_publish_fails() -> None:
    class _BrokenTurn(FakeTurnPort):
        async def publish(self, event: BuilderEvent) -> None:
            raise OSError("stream down")

    turn = _BrokenTurn()
    middleware = BuilderToolObserverMiddleware(turn)
    handler = _Handler("ok")

    result = await _call(middleware, "ls", {}, handler)

    assert result.content == "ok"
    assert len(turn.finished) == 1


async def test_awrap_tool_call_falls_back_to_generated_id_when_call_has_no_id() -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    request = ToolCallRequest(
        tool_call={"name": "ls", "args": {}, "id": None, "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )

    await middleware.awrap_tool_call(request, _Handler())

    assert _of_type(turn.events, ToolStarted)[0].call_id == "call-1"


# --- Write scope --------------------------------------------------------------------


@pytest.mark.parametrize("tool", ["write_file", "edit_file"])
@pytest.mark.parametrize(
    "path", ["/notes.md", "/workflows/../notes.md", "/workflowsx/a.json", "/"]
)
async def test_awrap_tool_call_refuses_write_when_path_is_outside_workflows(
    tool: str, path: str
) -> None:
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    handler = _Handler()

    result = await _call(middleware, tool, {"file_path": path}, handler)

    assert handler.calls == 0
    assert result.content == WRITE_SCOPE_MESSAGE
    assert turn.workflow_writes == []


async def test_awrap_tool_call_refuses_write_when_path_is_missing() -> None:
    middleware = BuilderToolObserverMiddleware(FakeTurnPort())
    handler = _Handler()

    result = await _call(middleware, "write_file", {"content": "x"}, handler)

    assert handler.calls == 0
    assert result.content == WRITE_SCOPE_MESSAGE


@pytest.mark.parametrize(
    "path", ["/skills/velocity-workflow-creator/SKILL.md", "/skills", "//skills/x"]
)
async def test_awrap_tool_call_gives_read_only_message_when_write_targets_skills(
    path: str,
) -> None:
    middleware = BuilderToolObserverMiddleware(FakeTurnPort())
    handler = _Handler()

    result = await _call(middleware, "edit_file", {"file_path": path}, handler)

    assert handler.calls == 0
    assert result.content == SKILL_READ_ONLY_MESSAGE


async def test_awrap_tool_call_allows_read_when_path_is_outside_workflows() -> None:
    middleware = BuilderToolObserverMiddleware(FakeTurnPort())
    handler = _Handler()

    await _call(middleware, "read_file", {"file_path": f"{_SKILL}/SKILL.md"}, handler)

    assert handler.calls == 1


async def test_awrap_tool_call_pairs_events_and_stores_row_when_write_is_refused() -> (
    None
):
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)

    await _call(middleware, "write_file", {"file_path": "/notes.md"}, call_id="c-1")

    started = _of_type(turn.events, ToolStarted)
    finished = _of_type(turn.events, ToolFinished)
    assert [type(e) for e in turn.events] == [ToolStarted, ToolFinished]
    assert started[0].call_id == finished[0].call_id == "c-1"
    assert finished[0].status == "refused"
    assert finished[0].summary.startswith("Wrote notes.md was refused.")
    assert turn.signals == []
    assert [row.activity.status for row in turn.finished] == ["refused"]
    assert turn.finished[0].result == WRITE_SCOPE_MESSAGE


async def test_awrap_tool_call_records_workflow_write_when_manifest_is_written() -> (
    None
):
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)

    await _call(middleware, "write_file", {"file_path": "workflows/a.workflow.json"})
    await _call(
        middleware, "write_file", {"file_path": "/workflows/notes.md"}, call_id="c-2"
    )

    assert turn.workflow_writes == ["/workflows/a.workflow.json"]


async def test_awrap_tool_call_skips_workflow_write_when_handler_reports_error() -> (
    None
):
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    handler = _Handler("Error: invalid JSON", status="error")

    await _call(middleware, "write_file", {"file_path": _MANIFEST}, handler)

    assert turn.workflow_writes == []
    assert _of_type(turn.events, ToolFinished)[0].status == "error"


# --- Limits -------------------------------------------------------------------------


async def test_awrap_tool_call_warns_once_when_calls_reach_eighty_percent() -> None:
    turn = FakeTurnPort(limits=_limits(10))
    middleware = BuilderToolObserverMiddleware(turn)

    for index in range(1, 11):
        await _call(middleware, "ls", {}, call_id=f"c-{index}")

    warnings = _of_type(turn.events, LimitWarning)
    assert [(w.kind, w.used, w.limit) for w in warnings] == [("tool_calls", 8, 10)]
    # The warning comes before the tool_started of the call that crossed 80 %.
    index_warning = turn.events.index(warnings[0])
    assert isinstance(turn.events[index_warning + 1], ToolStarted)
    assert _of_type(turn.events, ToolStarted)[7].call_id == "c-8"


async def test_awrap_tool_call_appends_notice_once_when_calls_pass_warning_point() -> (
    None
):
    turn = FakeTurnPort(limits=_limits(10))
    middleware = BuilderToolObserverMiddleware(turn, elapsed_seconds=lambda: 0.0)
    contents: list[str] = []

    for index in range(1, 11):
        result = await _call(middleware, "ls", {}, call_id=f"c-{index}")
        contents.append(str(result.content))

    with_notice = [i + 1 for i, text in enumerate(contents) if "[builder]" in text]
    assert with_notice == [8]
    assert "2 tool calls are left" in contents[7]
    assert "10 minutes" in contents[7]
    assert contents[7].startswith("done\n\n[builder]")
    # The stored result does not hold the notice.
    assert "[builder]" not in turn.finished[7].result


async def test_awrap_tool_call_adds_time_part_once_when_elapsed_passes_warning_fraction() -> (
    None
):
    turn = FakeTurnPort(limits=_limits(100))
    elapsed = [0.0]
    middleware = BuilderToolObserverMiddleware(turn, elapsed_seconds=lambda: elapsed[0])

    first = await _call(middleware, "ls", {}, call_id="c-1")
    elapsed[0] = 540.0
    second = await _call(middleware, "ls", {}, call_id="c-2")
    third = await _call(middleware, "ls", {}, call_id="c-3")

    assert "[builder]" not in str(first.content)
    assert "About 1 minute and 98 tool calls are left" in str(second.content)
    assert "[builder]" not in str(third.content)


async def test_awrap_tool_call_appends_notice_to_text_block_when_content_is_a_list() -> (
    None
):
    turn = FakeTurnPort(limits=_limits(1))
    middleware = BuilderToolObserverMiddleware(turn, elapsed_seconds=lambda: 0.0)

    async def handler(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content=[{"type": "text", "text": "body"}], tool_call_id="call-1"
        )

    result = await middleware.awrap_tool_call(_request("ls", {}), handler)

    assert isinstance(result, ToolMessage)
    assert isinstance(result.content, list)
    assert result.content[0] == {"type": "text", "text": "body"}
    assert "[builder]" in str(result.content[-1])


async def test_awrap_tool_call_appends_notice_to_command_message_when_handler_returns_command() -> (
    None
):
    turn = FakeTurnPort(limits=_limits(1))
    middleware = BuilderToolObserverMiddleware(turn, elapsed_seconds=lambda: 0.0)
    inner = ToolMessage(content="body", tool_call_id="call-1")

    async def handler(request: ToolCallRequest) -> Command[Any]:
        return Command(update={"messages": [inner], "other": 1})

    result = await middleware.awrap_tool_call(_request("ls", {}), handler)

    assert isinstance(result, Command)
    assert isinstance(result.update, dict)
    assert result.update["other"] == 1
    assert "[builder]" in str(result.update["messages"][0].content)


async def test_awrap_tool_call_refuses_call_and_stops_turn_when_cap_is_exceeded() -> (
    None
):
    turn = FakeTurnPort(limits=_limits(2))
    middleware = BuilderToolObserverMiddleware(turn)
    handler = _Handler()

    await _call(middleware, "ls", {}, handler, call_id="c-1")
    await _call(middleware, "ls", {}, handler, call_id="c-2")
    third = await _call(middleware, "ls", {}, handler, call_id="c-3")
    fourth = await _call(middleware, "ls", {}, handler, call_id="c-4")

    assert handler.calls == 2
    assert third.content == TOOL_LIMIT_MESSAGE
    assert fourth.content == TOOL_LIMIT_MESSAGE
    assert turn.stop_reasons == ["tool_calls", "tool_calls"]
    assert turn.stopping is True
    finished = _of_type(turn.events, ToolFinished)
    assert [f.status for f in finished] == ["ok", "ok", "refused", "refused"]
    assert len(_of_type(turn.events, ToolStarted)) == 4


# --- Pinned turn message ------------------------------------------------------------


def test_init_raises_when_pinned_message_id_does_not_match_turn() -> None:
    with pytest.raises(ValueError, match="turn:t-1"):
        PinnedTurnMessageMiddleware("t-1", HumanMessage(content="x", id="turn:other"))


async def test_awrap_model_call_inserts_pinned_message_after_summary_when_it_was_removed() -> (
    None
):
    pinned = HumanMessage(content="turn", id="turn:t-1")
    summary = HumanMessage(
        content="summary", additional_kwargs={"lc_source": "summarization"}
    )
    reply = AIMessage(content="reply")
    middleware = PinnedTurnMessageMiddleware("t-1", pinned)
    request: ModelRequest[Any] = ModelRequest(
        model=GenericFakeChatModel(messages=iter([])), messages=[summary, reply]
    )
    seen: list[ModelRequest[Any]] = []

    async def handler(received: ModelRequest[Any]) -> str:
        seen.append(received)
        return "response"

    result = await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]

    assert result == "response"
    assert seen[0].messages == [summary, pinned, reply]
    assert request.messages == [summary, reply]
