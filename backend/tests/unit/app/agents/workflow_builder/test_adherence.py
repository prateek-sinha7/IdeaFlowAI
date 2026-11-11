"""Unit tests for ``app.agents.workflow_builder.adherence``.

Checks that the record is derived from the Turn's tool calls only: a mandatory
file counts as read in full when the union of its read ranges covers its line
count, the lookups count only on exit 0, and the validator verdict is the last
run's.

Requirements: 28.10 (adherence record), 49.2.
"""

from __future__ import annotations

import pytest

from app.agents.workflow_builder.adherence import (
    DEFAULT_READ_LIMIT,
    MANDATORY_FILES,
    ToolCall,
    record,
)

_SKILL = "/skills/velocity-workflow-creator"
_LINES = {
    "SKILL.md": 250,
    "docs/problem-decomposition.md": 120,
    "docs/quick-reference.md": 60,
    "docs/prompt-writing.md": 300,
}


def _read(
    relative: str,
    offset: int | None = None,
    limit: int | None = None,
    *,
    ok: bool = True,
) -> ToolCall:
    return ToolCall(
        name="read_file",
        ok=ok,
        path=f"{_SKILL}/{relative}",
        offset=offset,
        limit=limit,
    )


def _script(
    script: str,
    subcommand: str | None = None,
    exit_code: int | None = 0,
    verdict: str | None = None,
) -> ToolCall:
    return ToolCall(
        name="run_skill_script",
        script=script,
        subcommand=subcommand,
        exit_code=exit_code,
        verdict=verdict,  # type: ignore[arg-type]  # test passes plain strings
    )


def test_record_marks_nothing_when_turn_has_no_calls() -> None:
    result = record([], _LINES)

    assert result.manifest_turn is False
    assert result.mandatory_read == dict.fromkeys(MANDATORY_FILES, False)
    assert result.overview_ran is False
    assert result.example_ran is False
    assert result.validator_ran is False
    assert result.last_validator_verdict is None


def test_record_marks_file_read_when_one_read_covers_all_lines() -> None:
    result = record([_read("docs/quick-reference.md", 0, 60)], _LINES)

    assert result.mandatory_read["docs/quick-reference.md"] is True
    assert result.mandatory_read["SKILL.md"] is False


def test_record_marks_file_unread_when_read_stops_one_line_short() -> None:
    result = record([_read("docs/quick-reference.md", 0, 59)], _LINES)

    assert result.mandatory_read["docs/quick-reference.md"] is False


def test_record_marks_file_read_when_paged_reads_join() -> None:
    calls = [
        _read("SKILL.md", 100, 100),
        _read("SKILL.md", 0, 100),
        _read("SKILL.md", 200, 100),
    ]

    result = record(calls, _LINES)

    assert result.mandatory_read["SKILL.md"] is True


def test_record_marks_file_unread_when_paged_reads_leave_a_gap() -> None:
    calls = [_read("SKILL.md", 0, 100), _read("SKILL.md", 101, 200)]

    result = record(calls, _LINES)

    assert result.mandatory_read["SKILL.md"] is False


def test_record_uses_deepagents_defaults_when_offset_and_limit_are_omitted() -> None:
    exact = {"SKILL.md": DEFAULT_READ_LIMIT}
    longer = {"SKILL.md": DEFAULT_READ_LIMIT + 1}
    call = [_read("SKILL.md")]

    assert record(call, exact).mandatory_read["SKILL.md"] is True
    assert record(call, longer).mandatory_read["SKILL.md"] is False


def test_record_ignores_read_when_call_failed() -> None:
    result = record([_read("docs/quick-reference.md", 0, 500, ok=False)], _LINES)

    assert result.mandatory_read["docs/quick-reference.md"] is False


def test_record_ignores_read_when_limit_is_not_positive() -> None:
    result = record([_read("docs/quick-reference.md", 0, 0)], _LINES)

    assert result.mandatory_read["docs/quick-reference.md"] is False


def test_record_ignores_read_when_path_is_under_another_skill() -> None:
    other = ToolCall(
        name="read_file", path="/skills/other-skill/SKILL.md", offset=0, limit=500
    )

    result = record([other], _LINES)

    assert result.mandatory_read["SKILL.md"] is False


def test_record_resolves_dot_segments_and_backslashes_when_path_is_not_normal() -> None:
    call = ToolCall(
        name="read_file",
        path=f"{_SKILL}\\docs\\..\\SKILL.md",
        offset=0,
        limit=500,
    )

    result = record([call], _LINES)

    assert result.mandatory_read["SKILL.md"] is True


def test_record_never_marks_file_read_when_line_counts_lack_it() -> None:
    result = record([_read("SKILL.md", 0, 10_000)], {})

    assert result.mandatory_read["SKILL.md"] is False


def test_record_marks_empty_file_read_when_any_read_succeeded() -> None:
    lines = {**_LINES, "docs/prompt-writing.md": 0}

    read = record([_read("docs/prompt-writing.md", 0, 100)], lines)
    unread = record([], lines)

    assert read.mandatory_read["docs/prompt-writing.md"] is True
    assert unread.mandatory_read["docs/prompt-writing.md"] is False


def test_record_tracks_other_skill_when_skill_id_is_given() -> None:
    call = ToolCall(
        name="read_file", path="/skills/other-skill/SKILL.md", offset=0, limit=500
    )

    result = record([call], _LINES, skill_id="other-skill")

    assert result.mandatory_read["SKILL.md"] is True


def test_record_ignores_non_mandatory_files_when_they_are_read() -> None:
    result = record([_read("docs/catalog.md", 0, 1000)], _LINES)

    assert set(result.mandatory_read) == set(MANDATORY_FILES)
    assert not any(result.mandatory_read.values())


@pytest.mark.parametrize("subcommand", ["overview", "example"])
def test_record_marks_lookup_ran_when_it_exits_zero(subcommand: str) -> None:
    result = record([_script("catalog_lookup.py", subcommand)], _LINES)

    assert result.overview_ran is (subcommand == "overview")
    assert result.example_ran is (subcommand == "example")


@pytest.mark.parametrize("exit_code", [1, 2, None])
def test_record_ignores_lookup_when_it_did_not_exit_zero(exit_code: int | None) -> None:
    calls = [
        _script("catalog_lookup.py", "overview", exit_code),
        _script("catalog_lookup.py", "example", exit_code),
    ]

    result = record(calls, _LINES)

    assert result.overview_ran is False
    assert result.example_ran is False


def test_record_accepts_lookup_when_script_has_a_directory_prefix() -> None:
    call = _script("scripts/catalog_lookup.py", "overview")

    assert record([call], _LINES).overview_ran is True


def test_record_ignores_lookup_when_subcommand_is_something_else() -> None:
    result = record([_script("catalog_lookup.py", "search")], _LINES)

    assert result.overview_ran is False
    assert result.example_ran is False


def test_record_marks_validator_run_when_verdict_is_invalid() -> None:
    call = _script("validate_manifest.py", exit_code=1, verdict="invalid")

    result = record([call], _LINES)

    assert result.validator_ran is True
    assert result.last_validator_verdict == "invalid"


def test_record_reports_unknown_verdict_when_validator_printed_none() -> None:
    result = record([_script("validate_manifest.py", verdict=None)], _LINES)

    assert result.validator_ran is True
    assert result.last_validator_verdict == "unknown"


def test_record_reports_last_verdict_when_validator_ran_twice() -> None:
    calls = [
        _script("validate_manifest.py", exit_code=1, verdict="invalid"),
        _script("validate_manifest.py", exit_code=0, verdict="valid"),
    ]

    result = record(calls, _LINES)

    assert result.last_validator_verdict == "valid"


def test_record_ignores_validator_when_it_never_exited() -> None:
    result = record([_script("validate_manifest.py", exit_code=None)], _LINES)

    assert result.validator_ran is False
    assert result.last_validator_verdict is None


@pytest.mark.parametrize("tool", ["write_file", "edit_file"])
def test_record_marks_manifest_turn_when_a_workflow_file_is_written(tool: str) -> None:
    call = ToolCall(name=tool, path="/workflows/contract-review.workflow.json")

    assert record([call], _LINES).manifest_turn is True


def test_record_leaves_manifest_turn_off_when_file_is_not_a_manifest() -> None:
    call = ToolCall(name="write_file", path="/workflows/notes.md")

    assert record([call], _LINES).manifest_turn is False


def test_record_leaves_manifest_turn_off_when_the_write_failed() -> None:
    call = ToolCall(name="write_file", ok=False, path="/workflows/a.workflow.json")

    assert record([call], _LINES).manifest_turn is False


def test_record_ignores_unknown_tools_when_they_appear() -> None:
    call = ToolCall(name="grep", path="/workflows/a.workflow.json")

    result = record([call], _LINES)

    assert result.manifest_turn is False


def test_as_dict_returns_json_shape_when_record_is_built() -> None:
    result = record(
        [_read("SKILL.md", 0, 250), _script("catalog_lookup.py", "overview")], _LINES
    )

    data = result.as_dict()

    assert data == {
        "manifest_turn": False,
        "mandatory_read": {
            "SKILL.md": True,
            "docs/problem-decomposition.md": False,
            "docs/quick-reference.md": False,
            "docs/prompt-writing.md": False,
        },
        "overview_ran": True,
        "example_ran": False,
        "validator_ran": False,
        "last_validator_verdict": None,
    }
