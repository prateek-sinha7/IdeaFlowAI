"""Unit tests for ``tools.builder_spike_report`` (task 22.12, Req 46.3).

No database: ``build_report`` is pure, and ``load_rows`` / ``main`` run against a
small recording fake session that returns canned rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import TextClause

from app.agents.workflow_builder.draft_tool import _rejection_text
from app.agents.workflow_builder.ports import GateIssue
from tools import builder_spike_report as report_module
from tools.builder_spike_report import (
    SessionRow,
    ToolRow,
    TurnRow,
    build_report,
    load_rows,
    main,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
SECRET = "SECRET-USER-CONTENT"


def _session(session_id: str = "s1") -> SessionRow:
    return SessionRow(session_id, "create", "model-a", "high", "hash-1", 2)


def _turn(
    turn_id: str = "t1", *, session_id: str = "s1", seq: int = 2, **over: Any
) -> TurnRow:
    fields: dict[str, Any] = {
        "id": turn_id,
        "session_id": session_id,
        "seq": seq,
        "status": "completed",
        "outcome": "draft",
        "stop_reason": None,
        "error_code": None,
        "model_id": "model-a",
        "effort": "high",
        "skill_hash": "hash-1",
        "prompt_version": "p1",
        "usage": None,
        "adherence": None,
        "revision": 1,
        "started_at": T0,
        "ended_at": T0 + timedelta(seconds=42.5),
    }
    fields.update(over)
    return TurnRow(**fields)


def _tool(
    turn_id: str = "t1",
    name: str = "read_file",
    status: str = "ok",
    head: str | None = "file text",
) -> ToolRow:
    return ToolRow("s1", turn_id, status, {"tool": name}, head)


def _rejection_head(attempt: int = 1, attempts_left: int = 1) -> str:
    issue = GateIssue(rule="save_check", path="steps.0", message="bad")
    return _rejection_text((issue,), attempt, attempts_left)[:80]


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _FakeSession:
    """Records statements; returns canned results in the order they are asked."""

    def __init__(
        self, results: list[list[Any]] | None = None, dialect: str = "postgresql"
    ) -> None:
        self._results = [[], [], []] if results is None else list(results)
        self._dialect = dialect
        self.statements: list[Any] = []
        self.rolled_back = False
        self.closed = False

    def get_bind(self) -> Any:
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialect))

    def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        if isinstance(statement, TextClause):
            return _Result([])
        return _Result(self._results.pop(0))

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


# --- build_report ------------------------------------------------------------------


def test_build_report_returns_duration_when_both_times_set() -> None:
    result = build_report(["s1"], [_session()], [_turn()], [])
    assert result["sessions"][0]["turns"][0]["duration_seconds"] == 42.5


@pytest.mark.parametrize(
    ("started", "ended"),
    [(None, T0), (T0, None), (None, None), (T0.replace(tzinfo=None), T0)],
)
def test_build_report_returns_null_duration_when_a_time_is_missing_or_mixed(
    started: datetime | None, ended: datetime | None
) -> None:
    turn = _turn(started_at=started, ended_at=ended)
    result = build_report(["s1"], [_session()], [turn], [])
    assert result["sessions"][0]["turns"][0]["duration_seconds"] is None


def test_build_report_sums_input_and_output_with_summary_when_usage_stored() -> None:
    usage = {
        "input": 100,
        "output": 20,
        "cache_read": 5,
        "cache_write": 7,
        "summary": {"input": 10, "output": 3, "cache_read": 0, "cache_write": 0},
    }
    tokens = build_report(["s1"], [_session()], [_turn(usage=usage)], [])["sessions"][
        0
    ]["turns"][0]["tokens"]
    assert tokens["total"] == 133
    assert tokens["cache_read"] == 5
    assert tokens["summary"]["input"] == 10


@pytest.mark.parametrize("usage", [None, "x", 3, []])
def test_build_report_returns_null_tokens_when_usage_is_not_an_object(
    usage: Any,
) -> None:
    turn = build_report(["s1"], [_session()], [_turn(usage=usage)], [])["sessions"][0][
        "turns"
    ][0]
    assert turn["tokens"] is None


def test_build_report_counts_zero_when_usage_values_are_not_counts() -> None:
    usage = {"input": True, "output": -4, "cache_read": "9", "summary": "bad"}
    tokens = build_report(["s1"], [_session()], [_turn(usage=usage)], [])["sessions"][
        0
    ]["turns"][0]["tokens"]
    assert tokens["total"] == 0
    assert tokens["summary"] is None


def test_build_report_groups_tool_calls_by_tool_and_status_when_rows_exist() -> None:
    tools = [
        _tool(name="read_file"),
        _tool(name="read_file"),
        _tool(name="run_skill_script", status="refused"),
        ToolRow("s1", "t1", None, None, None),
        _tool(turn_id="other", name="write_file"),
    ]
    calls = build_report(["s1"], [_session()], [_turn()], tools)["sessions"][0][
        "turns"
    ][0]["tool_calls"]
    assert calls == {
        "total": 4,
        "by_tool": {"read_file": 2, "run_skill_script": 1, "unknown": 1},
        "by_status": {"ok": 2, "refused": 1, "unknown": 1},
    }


def test_build_report_counts_only_propose_draft_rejections_when_other_rows_match() -> (
    None
):
    rejection = _rejection_head()
    tools = [
        _tool(name="propose_draft", head=rejection),
        _tool(name="propose_draft", head=_rejection_head(2, 0)),
        _tool(name="propose_draft", head="The draft is now on the Canvas."),
        _tool(name="propose_draft", head="I could not read that file."),
        _tool(name="propose_draft", head=None),
        _tool(name="read_file", head=rejection),
    ]
    turn = build_report(["s1"], [_session()], [_turn()], tools)["sessions"][0]["turns"][
        0
    ]
    assert turn["gate_rejections"] == 2


def test_build_report_matches_the_real_rejection_text_when_header_is_cut_to_80_chars() -> (
    None
):
    for attempt, left in ((1, 1), (2, 0)):
        assert report_module._is_gate_rejection(  # noqa: SLF001 - pins the text contract
            _tool(name="propose_draft", head=_rejection_head(attempt, left))
        )


def test_build_report_passes_adherence_through_when_stored_as_object() -> None:
    adherence = {"manifest_turn": True, "mandatory_read": {"SKILL.md": True}}
    turns = [_turn("t1", adherence=adherence), _turn("t2", seq=4, adherence="junk")]
    entries = build_report(["s1"], [_session()], turns, [])["sessions"][0]["turns"]
    assert entries[0]["adherence"] == adherence
    assert entries[1]["adherence"] is None


def test_build_report_orders_turns_by_seq_and_sessions_by_request_when_unsorted() -> (
    None
):
    sessions = [_session("a"), _session("b")]
    turns = [
        _turn("t9", session_id="a", seq=8),
        _turn("t3", session_id="a", seq=2),
        _turn("tb", session_id="b", seq=2),
    ]
    result = build_report(["b", "a"], sessions, turns, [])
    assert [s["session_id"] for s in result["sessions"]] == ["b", "a"]
    assert [t["turn_id"] for t in result["sessions"][1]["turns"]] == ["t3", "t9"]


def test_build_report_lists_missing_ids_once_when_ids_repeat_or_are_unknown() -> None:
    result = build_report(["s1", "nope", "s1", "nope"], [_session()], [], [])
    assert result["missing_session_ids"] == ["nope"]
    assert len(result["sessions"]) == 1


def test_build_report_is_json_serialisable_when_all_fields_set() -> None:
    result = build_report(["s1"], [_session()], [_turn(usage={"input": 1})], [_tool()])
    assert json.loads(json.dumps(result)) == result


# --- load_rows ---------------------------------------------------------------------


def _canned_results() -> list[list[Any]]:
    return [
        [("s1", "create", "m", "high", "h", 1)],
        [
            (
                "t1", "s1", 2, "completed", "draft", None, None, "m", "high", "h",
                "p1", {"input": 1}, {"manifest_turn": True}, 1, T0, T0,
            )
        ],
        [("s1", "t1", "ok", {"tool": "read_file"}, "text")],
    ]  # fmt: skip


def test_load_rows_maps_rows_to_records_when_session_returns_tuples() -> None:
    sessions, turns, tools = load_rows(_FakeSession(_canned_results()), ["s1"])  # type: ignore[arg-type]
    assert sessions == [SessionRow("s1", "create", "m", "high", "h", 1)]
    assert turns[0].id == "t1"
    assert turns[0].adherence == {"manifest_turn": True}
    assert tools == [ToolRow("s1", "t1", "ok", {"tool": "read_file"}, "text")]


def test_load_rows_issues_only_selects_after_read_only_marker_when_postgresql() -> None:
    fake = _FakeSession(_canned_results())
    load_rows(fake, ["s1", "s1"])  # type: ignore[arg-type]
    assert isinstance(fake.statements[0], TextClause)
    assert str(fake.statements[0]) == "SET TRANSACTION READ ONLY"
    assert len(fake.statements) == 4
    assert all(isinstance(s, Select) for s in fake.statements[1:])


def test_load_rows_skips_read_only_marker_when_dialect_is_not_postgresql() -> None:
    fake = _FakeSession(_canned_results(), dialect="other")
    load_rows(fake, ["s1"])  # type: ignore[arg-type]
    assert all(isinstance(s, Select) for s in fake.statements)


def test_load_rows_never_selects_message_content_when_loading_assistant_rows() -> None:
    fake = _FakeSession(_canned_results())
    load_rows(fake, ["s1"])  # type: ignore[arg-type]
    assistant_sql = str(fake.statements[2])
    assert "content" not in assistant_sql
    assert "thinking" not in assistant_sql
    assert "canvas_state" not in assistant_sql
    tool_sql = str(fake.statements[3])
    assert "substr" in tool_sql.lower()
    assert "canvas_state" not in tool_sql


# --- main --------------------------------------------------------------------------


def test_main_prints_report_and_returns_zero_when_all_sessions_found(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = _FakeSession(_canned_results())
    code = main(["s1"], session_factory=lambda: fake)  # type: ignore[arg-type,return-value]
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["sessions"][0]["turns"][0]["turn_id"] == "t1"
    assert fake.rolled_back
    assert fake.closed


def test_main_returns_one_and_names_ids_when_a_session_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = _FakeSession(_canned_results())
    code = main(["s1", "gone"], session_factory=lambda: fake)  # type: ignore[arg-type,return-value]
    assert code == 1
    assert json.loads(capsys.readouterr().out)["missing_session_ids"] == ["gone"]


def test_main_never_prints_tool_content_when_rows_carry_user_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = _canned_results()
    results[2] = [("s1", "t1", "ok", {"tool": "read_file", "summary": SECRET}, SECRET)]
    main(["s1"], session_factory=lambda: _FakeSession(results))  # type: ignore[arg-type,return-value]
    assert SECRET not in capsys.readouterr().out


def test_main_returns_two_and_closes_session_when_query_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = _FakeSession(results=[])  # first SELECT pops an empty list -> IndexError
    code = main(["s1"], session_factory=lambda: fake)  # type: ignore[arg-type,return-value]
    assert code == 2
    assert "query error" in capsys.readouterr().err
    assert fake.rolled_back
    assert fake.closed


def test_main_returns_two_when_session_cannot_be_opened(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken() -> Any:
        raise RuntimeError("no database")

    assert main(["s1"], session_factory=broken) == 2
    assert "setup error" in capsys.readouterr().err


def test_main_exits_with_usage_error_when_no_session_id_is_given() -> None:
    with pytest.raises(SystemExit) as raised:
        main([], session_factory=lambda: _FakeSession())  # type: ignore[arg-type,return-value]
    assert raised.value.code == 2


def test_main_exits_with_usage_error_when_ids_are_blank() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["  "], session_factory=lambda: _FakeSession())  # type: ignore[arg-type,return-value]
    assert raised.value.code == 2
