"""Property tests for ``tools.ci.builder_pattern_fixtures.compare_files``.

Requirements: 49.8.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tools.ci.builder_pattern_fixtures import compare_files

_FILES = st.dictionaries(
    st.text(alphabet="abcdef", min_size=1, max_size=3),
    st.binary(max_size=4),
    max_size=6,
)


@given(expected=_FILES, actual=_FILES)
def test_compare_files_is_empty_exactly_when_both_sides_are_equal(
    expected: dict[str, bytes], actual: dict[str, bytes]
) -> None:
    # Feature: ai-workflow-builder, per-pattern fixtures: --check agrees with equality
    assert (compare_files(expected, actual) == []) == (expected == actual)


@given(expected=_FILES, actual=_FILES)
def test_compare_files_names_every_differing_file_once(
    expected: dict[str, bytes], actual: dict[str, bytes]
) -> None:
    problems = compare_files(expected, actual)

    differing = {
        name
        for name in expected.keys() | actual.keys()
        if expected.get(name) != actual.get(name)
    }
    assert len(problems) == len(differing)
    assert all(
        any(problem.endswith(f": {name}") for problem in problems) for name in differing
    )
