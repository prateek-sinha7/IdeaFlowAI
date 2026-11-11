"""Property tests for content hygiene in the workflow builder.

# Feature: ai-workflow-builder, Property 23: User content stays out of the prompt, events and logs

For any user message, canvas state, tool argument, tool result and exception text
that carries unique marker strings (file contents, paths, SQL text, environment
values):

* the system prompt the model receives starts with the versioned prompt file and
  holds no marker;
* no event carries a marker, except a script call's ``command`` line and the
  ``manifest`` of ``draft_applied`` (assistant text may appear in ``text`` and
  ``thinking`` events, because that is what those events are for);
* no ``error`` event and no HTTP error body carries a stack trace, SQL text, a
  file path or a marker;
* no log record, captured with ``caplog`` at DEBUG level on the root logger,
  contains a marker from a user message or an assistant message, or a line of the
  system prompt.

**Validates: Requirements 17.4, 38.15, 38.16, 38.17, 42.2, 42.4, 42.5**

Two systems under test:

* ``run_turn`` with the real ``TurnRunner``, the real ``DeepAgentRunner`` loop, the
  observer middleware, ``run_skill_script`` and ``propose_draft``. The model is
  ``FakeChatModel``, the gate is ``FakeGate``, scripts run on
  ``FakeProcessFactory`` and the store is ``InMemoryBuilderStore``.
* ``admit_message`` with a store and a Turn starter that fail with SQL and path
  text, and with requests that carry markers in every field the caller controls.

The oracle is a plain substring search for markers that the test itself draws, and
regular expressions for stack traces, SQL and paths. It reads no production helper.

File names are shown in labels by design ("Read notes.md", Req 38.7), so the
markers for paths sit in the folder part of a path and the file name is fixed.

The tests are synchronous and drive the event loop with ``asyncio.run``, because
Hypothesis does not await coroutine tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, Literal
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from langchain_core.messages import SystemMessage
from sqlalchemy.exc import IntegrityError

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder import agent as agent_module
from app.agents.workflow_builder.events import (
    BuilderEvent,
    ErrorEvent,
    TurnScoped,
    to_wire,
)
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import ScriptContext
from app.api.workflow_builder import turns
from app.api.workflow_builder.admission import BuilderAccess, admit_message
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.schemas import SendMessageRequest
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnDeps,
    TurnRequest,
    attach_task,
    register_live_turn,
    run_turn,
    set_event_bus,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.principal import principal_for
from tests.fakes.process_factory import FakeProcessFactory, ProcessScript
from tests.fakes.scripted_chat_model import FakeChatModel, ModelTurn, ScriptedToolCall

USER: Final = "user-a"
MODEL: Final = "eu.anthropic.claude-sonnet-5-5"
EFFORT: Final = "medium"
_SKILLS_ROOT: Final = SKILLS_ROOT
_PROMPT_FILE: Final = (
    Path(agent_module.__file__).resolve().parent / "prompts" / "system_prompt.v1.md"
)
_SCRIPTS: Final = f"/skills/{BUILDER_SKILL_ID}/scripts"
_VALIDATE: Final = f"python {_SCRIPTS}/validate_manifest.py /workflows/a.workflow.json"
_MANIFEST_PATH: Final = "/workflows/a.workflow.json"
_VALID_LINE: Final = "VALID: 0 error(s), 0 warning(s)\n"

# What the oracle treats as a stack trace, SQL text or a file path.
_TRACE: Final = re.compile(r"Traceback|File \"|line \d+, in |\bat 0x[0-9a-f]+")
_SQL: Final = re.compile(
    r"\b(SELECT\b.*\bFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)"
    r"|psycopg|sqlalchemy|\[SQL:|\[parameters:",
    re.IGNORECASE | re.DOTALL,
)
_PATH: Final = re.compile(
    r"[A-Za-z]:[\\/]|\\\\|(?<![\w.])/(srv|home|usr|var|tmp|etc|opt|app|root)/"
)

MARKER_NAMES: Final = (
    "user",
    "canvas",
    "file",
    "path",
    "cmd",
    "result",
    "manifest",
    "asst",
    "sql",
    "env",
)

Op = Literal[
    "notes",
    "read_missing",
    "script_ok",
    "script_refused",
    "write_outside",
    "propose",
]
_OPS: Final[tuple[Op, ...]] = (
    "notes",
    "read_missing",
    "script_ok",
    "script_refused",
    "write_outside",
    "propose",
)
Failure = Literal["sql", "path", "trace", "env"]


# --- Strategies -------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """One scripted Turn with the marker strings it carries."""

    markers: dict[str, str]
    user_template: str
    ops: tuple[Op, ...]
    failure: Failure | None


_USER_TEMPLATES: Final = (
    "{m}",
    "Please build a workflow. Note: {m}",
    "line one\nSELECT * FROM users WHERE token = '{m}'\nline three",
    "C:\\Users\\someone\\{m}\\notes.txt and /home/someone/{m}/notes.txt",
    "API_KEY={m}\nSECRET_TOKEN={m}",
    '```\nTraceback (most recent call last):\n  File "/srv/{m}.py", line 2\n```',
)


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    """Draw ten unique markers, a user text, up to six tool-call ops and a failure."""
    hexes = draw(
        st.lists(
            st.text("0123456789abcdef", min_size=10, max_size=10),
            unique=True,
            min_size=len(MARKER_NAMES),
            max_size=len(MARKER_NAMES),
        )
    )
    markers = {
        name: f"zq{index}x{value}"
        for index, (name, value) in enumerate(zip(MARKER_NAMES, hexes, strict=True))
    }
    return Scenario(
        markers=markers,
        user_template=draw(st.sampled_from(_USER_TEMPLATES)),
        ops=tuple(draw(st.lists(st.sampled_from(_OPS), min_size=0, max_size=6))),
        failure=draw(st.none() | st.sampled_from(("sql", "path", "trace", "env"))),
    )


def _failure_text(kind: Failure, markers: dict[str, str]) -> str:
    """Exception text that carries SQL, a path, a trace and an environment value."""
    sql = f"SELECT {markers['sql']} FROM secrets WHERE token = '{markers['env']}'"
    where = f"/srv/app/{markers['path']}/db.py"
    match kind:
        case "sql":
            return (
                f"(psycopg.errors.UndefinedTable) relation does not exist "
                f"[SQL: {sql}] [parameters: ('{markers['env']}',)]"
            )
        case "path":
            return f"[Errno 2] No such file or directory: '{where}' ({markers['path']})"
        case "trace":
            return (
                f'Traceback (most recent call last):\n  File "{where}", line 3, '
                f"in run\n    {sql}\nRuntimeError: {markers['sql']}"
            )
        case "env":
            return f"AWS_SECRET_ACCESS_KEY={markers['env']} rejected at {where}"


# --- A scripted Turn -----------------------------------------------------------------


def _tool_calls(op: Op, markers: dict[str, str]) -> list[ScriptedToolCall]:
    """The tool calls one op makes, in order."""
    folder = markers["path"]
    notes = f"/workflows/{folder}/notes.md"
    match op:
        case "notes":
            return [
                ScriptedToolCall(
                    "write_file", {"file_path": notes, "content": markers["file"]}
                ),
                ScriptedToolCall("read_file", {"file_path": notes}),
            ]
        case "read_missing":
            return [
                ScriptedToolCall(
                    "read_file", {"file_path": f"/skills/{folder}/missing.md"}
                )
            ]
        case "script_ok":
            return [ScriptedToolCall("run_skill_script", {"command": _VALIDATE})]
        case "script_refused":
            return [
                ScriptedToolCall(
                    "run_skill_script",
                    {"command": f"{_VALIDATE} --{markers['cmd']}={markers['file']}"},
                )
            ]
        case "write_outside":
            return [
                ScriptedToolCall(
                    "write_file",
                    {
                        "file_path": f"/etc/{folder}/x.txt",
                        "content": markers["file"],
                    },
                )
            ]
        case "propose":
            manifest = {
                "id": "wf-one",
                "steps": [{"agent": "custom-agent", "prompt": markers["manifest"]}],
            }
            return [
                ScriptedToolCall(
                    "write_file",
                    {"file_path": _MANIFEST_PATH, "content": json.dumps(manifest)},
                ),
                ScriptedToolCall("propose_draft", {"path": _MANIFEST_PATH}),
            ]


def _model(scenario: Scenario) -> FakeChatModel:
    """One model call per tool call, then a final answer or a failure."""
    markers = scenario.markers
    scripted = [
        ModelTurn(tool_calls=(call,))
        for op in scenario.ops
        for call in _tool_calls(op, markers)
    ]
    final = ModelTurn(text=(f"Working on it. {markers['asst']}",))
    if scenario.failure is not None:
        final = ModelTurn(
            text=(f"Working on it. {markers['asst']}",),
            error=RuntimeError(_failure_text(scenario.failure, markers)),
        )
    scripted.append(final)
    return FakeChatModel(turns=tuple(scripted))


def _process_scripts(scenario: Scenario) -> list[ProcessScript]:
    """One process per validator run; its output carries a tool-result marker."""
    output = f"note: {scenario.markers['result']} env={scenario.markers['env']}\n"
    return [
        ProcessScript.with_text(output + _VALID_LINE)
        for op in scenario.ops
        if op == "script_ok"
    ]


@contextmanager
def _scope(store: Any) -> Iterator[Any]:
    yield store


@dataclass(frozen=True)
class Outcome:
    """What a scripted Turn produced."""

    events: list[BuilderEvent]
    model: FakeChatModel


def _canvas(markers: dict[str, str]) -> dict[str, Any]:
    return {"steps": [{"agent": "custom-agent", "note": markers["canvas"]}]}


async def _play(scenario: Scenario, root: Path) -> Outcome:
    """Run the scenario through ``run_turn`` and return what was published."""
    markers = scenario.markers
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    store = InMemoryBuilderStore()
    bus = SessionEventBus(queue_maxsize=10_000)
    set_event_bus(bus)
    content = scenario.user_template.format(m=markers["user"])
    session = store.create_session(USER, **BuilderSessionFactory.create_kwargs())
    begun = store.begin_turn(
        USER,
        str(session.id),
        content=content,
        canvas_state=_canvas(markers),
        client_message_id="client-message-1",
        model_id="model-x",
        effort=None,
        skill_hash="hash",
    )
    live = LiveTurn(
        session_id=str(session.id),
        turn_id=str(begun.assistant_message.id),
        user_message_id=str(begun.user_message.id),
        user_id=USER,
        model_id="model-x",
        effort=None,
    )
    model = _model(scenario)
    factory = FakeProcessFactory(*_process_scripts(scenario))
    queue, _ = bus.subscribe(live.session_id, lambda: _snapshot(live))
    deps = TurnDeps(
        bus=bus,
        store_scope=lambda: _scope(store),
        sandbox_factory=lambda user, sid: BuilderSandbox(user, sid, root=root),
        gate=FakeGate(),
        chat_model=model,
        skills_root=_SKILLS_ROOT,
    )
    request = TurnRequest(content=content, canvas_state=_canvas(markers))
    spawning = partial(ScriptContext, spawn=factory, semaphore=asyncio.Semaphore(2))
    register_live_turn(live)
    try:
        with patch("app.agents.workflow_builder.agent.ScriptContext", spawning):
            task = asyncio.ensure_future(run_turn(live, request, deps))
            attach_task(live, task)
            await task
        events: list[BuilderEvent] = []
        while not queue.empty():
            item = queue.get_nowait()
            if item is not None:
                events.append(item)
    finally:
        set_event_bus(None)
    return Outcome(events, model)


def _snapshot(live: LiveTurn) -> Any:
    return turns.build_snapshot(
        live.session_id, user_id=live.user_id, store=InMemoryBuilderStore()
    )


# --- Oracles -------------------------------------------------------------------------


def _text_of(content: Any) -> str:
    """Plain text of a message content (a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
    )


def _versioned_prompt() -> str:
    """The prompt file as the spec defines it: UTF-8, LF line endings."""
    return _PROMPT_FILE.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _check_prompt(scenario: Scenario, model: FakeChatModel) -> None:
    prompt = _versioned_prompt()
    assert agent_module.SYSTEM_PROMPT == prompt
    systems = [
        _text_of(message.content)
        for call in model.calls
        for message in call
        if isinstance(message, SystemMessage)
    ]
    assert systems, "the model received no system message"
    for text in systems:
        assert text.startswith(prompt)
        for marker in scenario.markers.values():
            assert marker not in text


def _event_text(event: BuilderEvent) -> str:
    """JSON text of an event, without the two fields that may carry user content."""
    type_, data = to_wire(event)
    if type_ == "tool_started":
        command = data.pop("command")
        # Only a script call has a command line (Req 38.7).
        assert (command is not None) == (data["tool"] == "run_skill_script")
    if type_ == "draft_applied":
        data.pop("manifest")
    return json.dumps(data, ensure_ascii=False)


def _check_events(scenario: Scenario, events: list[BuilderEvent], root: Path) -> None:
    assert events
    for event in events:
        type_ = event.type
        text = _event_text(event)
        for name, marker in scenario.markers.items():
            # Assistant text is what text and thinking events are for.
            if name == "asst" and type_ in ("text", "thinking"):
                continue
            assert marker not in text, f"{name} marker in {type_} event"
        if isinstance(event, ErrorEvent):
            for pattern in (_TRACE, _SQL, _PATH):
                assert not pattern.search(text), f"{pattern.pattern} in error event"
            assert str(root) not in text
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    if scenario.failure is not None:
        assert errors, "the scripted model failure produced no error event"


def _record_text(caplog: pytest.LogCaptureFixture, record: logging.LogRecord) -> str:
    """Everything a record carries: formatted text with traceback, args and extras."""
    return f"{caplog.handler.format(record)}\n{record.getMessage()}\n{vars(record)!r}"


def _long_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if len(line.strip()) >= 40]


def _check_logs(
    scenario: Scenario, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    forbidden = [scenario.markers["user"], scenario.markers["asst"], content]
    prompt_lines = _long_lines(_versioned_prompt())
    assert prompt_lines
    for record in caplog.records:
        text = _record_text(caplog, record)
        for marker in forbidden:
            assert marker not in text, f"message marker in log {record.name}"
        for line in prompt_lines:
            assert line not in text, f"system prompt line in log {record.name}"


@pytest.fixture(autouse=True)
def _reset_turn_registries() -> Iterator[None]:
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    yield
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    set_event_bus(None)


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(scenario=scenarios())
def test_run_turn_keeps_user_content_out_of_prompt_events_and_logs_when_markers_are_everywhere(
    scenario: Scenario, caplog: pytest.LogCaptureFixture
) -> None:
    """Property 23: prompt, events and logs hold no user content for any scripted Turn."""
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "builder"
        out = asyncio.run(_play(scenario, root))
        _check_prompt(scenario, out.model)
        _check_events(scenario, out.events, root)
    _check_logs(
        scenario, caplog, scenario.user_template.format(m=scenario.markers["user"])
    )


# --- Failing requests ------------------------------------------------------------------

Fault = Literal[
    "start_raises",
    "start_and_finalise_raise",
    "begin_integrity_error",
    "bad_model_id",
    "bad_effort",
    "bad_canvas",
    "none",
]
_FAULTS: Final[tuple[Fault, ...]] = (
    "start_raises",
    "start_and_finalise_raise",
    "begin_integrity_error",
    "bad_model_id",
    "bad_effort",
    "bad_canvas",
)


@dataclass(frozen=True)
class FailingRequest:
    """One failing send request and the markers it carries."""

    markers: dict[str, str]
    fault: Fault
    user_template: str


@st.composite
def failing_requests(draw: st.DrawFn) -> FailingRequest:
    """Draw markers, a user text and the way the request fails."""
    hexes = draw(
        st.lists(
            st.text("0123456789abcdef", min_size=10, max_size=10),
            unique=True,
            min_size=len(MARKER_NAMES),
            max_size=len(MARKER_NAMES),
        )
    )
    markers = {
        name: f"zq{index}x{value}"
        for index, (name, value) in enumerate(zip(MARKER_NAMES, hexes, strict=True))
    }
    return FailingRequest(
        markers=markers,
        fault=draw(st.sampled_from(_FAULTS)),
        user_template=draw(st.sampled_from(_USER_TEMPLATES)),
    )


class _FaultyStore(InMemoryBuilderStore):
    """An in-memory store whose writes fail with SQL and path text."""

    def __init__(self, fault: Fault, text: str, statement: str) -> None:
        super().__init__()
        self._fault = fault
        self._text = text
        self._statement = statement

    def begin_turn(self, *args: Any, **kwargs: Any) -> Any:
        if self._fault == "begin_integrity_error":
            raise IntegrityError(
                self._statement, {"c": self._text}, Exception(self._text)
            )
        return super().begin_turn(*args, **kwargs)

    def finalize_assistant(self, *args: Any, **kwargs: Any) -> Any:
        if self._fault == "start_and_finalise_raise":
            raise RuntimeError(self._text)
        return super().finalize_assistant(*args, **kwargs)


def _faulty_request(case: FailingRequest) -> SendMessageRequest:
    markers = case.markers
    return SendMessageRequest(
        content=case.user_template.format(m=markers["user"]),
        model_id=f"no-such-{markers['cmd']}" if case.fault == "bad_model_id" else MODEL,
        effort=f"bogus-{markers['cmd']}" if case.fault == "bad_effort" else EFFORT,
        canvas_state=(
            {markers["canvas"]: [{"x": markers["canvas"]}]}
            if case.fault == "bad_canvas"
            else {"steps": [{"agent": "custom-agent", "note": markers["canvas"]}]}
        ),
        client_message_id="client-id-0001",
    )


async def _send(case: FailingRequest) -> HTTPException:
    """Send the failing request and return the ``HTTPException`` it raised."""
    markers = case.markers
    text = _failure_text("sql", markers) + " " + _failure_text("trace", markers)
    statement = f"INSERT INTO builder_messages (content) VALUES ('{markers['sql']}')"
    store = _FaultyStore(case.fault, text, statement)
    session = store.create_session(USER, **BuilderSessionFactory.create_kwargs())
    row = SimpleNamespace(id=USER, tier="enterprise", is_admin=False)
    access = BuilderAccess(user=row, principal=principal_for(row), tier="enterprise")  # type: ignore[arg-type]

    def start_turn(turn: Any, content: str, canvas_state: dict[str, Any]) -> None:
        if case.fault in ("start_raises", "start_and_finalise_raise"):
            raise RuntimeError(text)

    try:
        await admit_message(
            store=store,
            access=access,
            session_id=str(session.id),
            body=_faulty_request(case),
            start_turn=start_turn,
            capacity_gate=lambda user: None,
        )
    except HTTPException as exc:
        return exc
    raise AssertionError("the failing request was admitted")


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(case=failing_requests())
def test_admit_message_returns_generic_error_without_user_content_when_request_fails(
    case: FailingRequest, caplog: pytest.LogCaptureFixture
) -> None:
    """Property 23: an HTTP error body and the logs hold no markers, trace, SQL or path."""
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    exc = asyncio.run(_send(case))
    body = json.dumps(
        {"detail": exc.detail, "headers": dict(exc.headers or {})}, default=str
    )
    for name, marker in case.markers.items():
        assert marker not in body, f"{name} marker in the HTTP error"
    for pattern in (_TRACE, _SQL, _PATH):
        assert not pattern.search(body), f"{pattern.pattern} in the HTTP error"
    assert exc.status_code in (409, 422, 403, 503)
    forbidden = [
        case.markers["user"],
        case.user_template.format(m=case.markers["user"]),
    ]
    for record in caplog.records:
        text = _record_text(caplog, record)
        for marker in forbidden:
            assert marker not in text, f"message marker in log {record.name}"
