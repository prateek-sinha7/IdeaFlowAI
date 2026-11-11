"""Property tests for the adherence record (``adherence.record``).

# Feature: ai-workflow-builder, Property 28: Adherence is derived from what was read and run

For any sequence of ``read_file`` calls and script calls in a turn, a mandatory
file is marked read in full if and only if the union of the requested line
ranges covers its line count, and ``overview_ran``, ``example_ran`` and the last
validator verdict match the calls that succeeded.

**Validates: Requirements 28.10**

The expected values come from the oracles below. They restate the rules with
plain sets and comparisons and do not call the production helpers.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.adherence import (
    DEFAULT_READ_LIMIT,
    MANDATORY_FILES,
    ToolCall,
    record,
)

_SKILL = "/skills/velocity-workflow-creator"

# (path as the model writes it, mandatory file it names or None).
_READ_TARGETS: list[tuple[str, str | None]] = [
    *((f"{_SKILL}/{name}", name) for name in MANDATORY_FILES),
    (f"{_SKILL}/docs/../SKILL.md", "SKILL.md"),
    (f"{_SKILL}/docs/./quick-reference.md", "docs/quick-reference.md"),
    (f"{_SKILL}/docs/catalog.md", None),
    ("/skills/other-skill/SKILL.md", None),
    ("/workspace/SKILL.md", None),
]
_WRITE_TARGETS = [
    ("/workspace/out.workflow.json", True),
    ("/workspace/dir/out.workflow.json", True),
    ("/workspace/notes.md", False),
    ("/workspace/out.workflow.json.bak", False),
]
_SCRIPTS = ["catalog_lookup.py", "validate_manifest.py", "other.py"]
_SUBCOMMANDS = ["overview", "example", "search", None]
_VERDICTS = ["valid", "invalid", "unknown", None]


@st.composite
def _reads(draw: st.DrawFn) -> ToolCall:
    path, _ = draw(st.sampled_from(_READ_TARGETS))
    return ToolCall(
        name="read_file",
        ok=draw(st.booleans()),
        path=path,
        offset=draw(st.none() | st.integers(min_value=-5, max_value=120)),
        limit=draw(st.none() | st.integers(min_value=0, max_value=120)),
    )


@st.composite
def _writes(draw: st.DrawFn) -> ToolCall:
    path, _ = draw(st.sampled_from(_WRITE_TARGETS))
    return ToolCall(
        name=draw(st.sampled_from(["write_file", "edit_file"])),
        ok=draw(st.booleans()),
        path=path,
    )


@st.composite
def _scripts(draw: st.DrawFn) -> ToolCall:
    exit_code = draw(st.none() | st.sampled_from([0, 1, 2]))
    return ToolCall(
        name="run_skill_script",
        ok=exit_code is not None,
        script=draw(st.sampled_from(_SCRIPTS)),
        subcommand=draw(st.sampled_from(_SUBCOMMANDS)),
        exit_code=exit_code,
        verdict=draw(st.sampled_from(_VERDICTS)),
    )


_CALLS = st.lists(
    st.one_of(_reads(), _writes(), _scripts(), st.just(ToolCall(name="ls"))),
    max_size=40,
)
# Small line counts make full coverage common. A missing key means the file is
# not in the skill package.
_LINE_COUNTS = st.fixed_dictionaries(
    {},
    optional={
        name: st.integers(min_value=1, max_value=150) for name in MANDATORY_FILES
    },
)


def _expected_mandatory_read(
    calls: list[ToolCall], line_counts: dict[str, int]
) -> dict[str, bool]:
    expected: dict[str, bool] = {}
    for name in MANDATORY_FILES:
        lines: set[int] = set()
        for call in calls:
            if call.name != "read_file" or not call.ok:
                continue
            target = dict(_READ_TARGETS)[call.path or ""]
            if target != name:
                continue
            offset = 0 if call.offset is None else call.offset
            limit = DEFAULT_READ_LIMIT if call.limit is None else call.limit
            lines.update(range(max(offset, 0), offset + limit))
        expected[name] = name in line_counts and set(range(line_counts[name])) <= lines
    return expected


@settings(max_examples=100, deadline=None)
@given(calls=_CALLS, line_counts=_LINE_COUNTS)
def test_record_marks_file_read_when_ranges_cover_line_count(
    calls: list[ToolCall], line_counts: dict[str, int]
) -> None:
    result = record(calls, line_counts)

    assert result.mandatory_read == _expected_mandatory_read(calls, line_counts)
    assert list(result.mandatory_read) == list(MANDATORY_FILES)


@settings(max_examples=100, deadline=None)
@given(calls=_CALLS, line_counts=_LINE_COUNTS)
def test_record_reports_script_runs_when_calls_exited(
    calls: list[ToolCall], line_counts: dict[str, int]
) -> None:
    scripts = [c for c in calls if c.name == "run_skill_script"]
    lookups = [
        c for c in scripts if c.script == "catalog_lookup.py" and c.exit_code == 0
    ]
    validators = [
        c
        for c in scripts
        if c.script == "validate_manifest.py" and c.exit_code is not None
    ]

    result = record(calls, line_counts)

    assert result.overview_ran == any(c.subcommand == "overview" for c in lookups)
    assert result.example_ran == any(c.subcommand == "example" for c in lookups)
    assert result.validator_ran == bool(validators)
    if validators:
        assert result.last_validator_verdict == (validators[-1].verdict or "unknown")
    else:
        assert result.last_validator_verdict is None


@settings(max_examples=100, deadline=None)
@given(
    runs=st.lists(
        st.builds(
            ToolCall,
            name=st.just("run_skill_script"),
            script=st.just("validate_manifest.py"),
            exit_code=st.sampled_from([0, 1]),
            verdict=st.sampled_from(_VERDICTS),
        ),
        min_size=2,
        max_size=6,
    )
)
def test_record_reports_last_verdict_when_validator_ran_repeatedly(
    runs: list[ToolCall],
) -> None:
    result = record(runs, {})

    assert result.validator_ran is True
    assert result.last_validator_verdict == (runs[-1].verdict or "unknown")


@settings(max_examples=100, deadline=None)
@given(calls=_CALLS, line_counts=_LINE_COUNTS)
def test_record_marks_manifest_turn_when_manifest_write_succeeded(
    calls: list[ToolCall], line_counts: dict[str, int]
) -> None:
    expected = any(
        c.name in {"write_file", "edit_file"}
        and c.ok
        and dict(_WRITE_TARGETS)[c.path or ""]
        for c in calls
    )

    assert record(calls, line_counts).manifest_turn is expected


@settings(max_examples=100, deadline=None)
@given(calls=_CALLS, line_counts=_LINE_COUNTS)
def test_record_returns_same_result_when_read_calls_are_reordered(
    calls: list[ToolCall], line_counts: dict[str, int]
) -> None:
    reads = [c for c in calls if c.name == "read_file"]
    others = [c for c in calls if c.name != "read_file"]

    forward = record([*reads, *others], line_counts)
    backward = record([*reversed(reads), *others], line_counts)

    assert forward == backward
