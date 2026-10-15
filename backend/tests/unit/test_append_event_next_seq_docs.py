"""Docstring guards: append_event_next_seq no longer reads the whole run log (FIX-688).

ISS-901 (QA-KB-074): three source docstrings still claim it does.
ISS-1079: two resume-marker test files still narrate the same dead cost.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _text(rel: str) -> str:
    return " ".join((ROOT / rel).read_text().split())


@pytest.mark.issue("ISS-901")
def test_read_events_docstring_does_not_list_append_event_next_seq_as_caller():
    """ISS-901 passage 1: read_events_of_types lists append_event_next_seq as a read_events caller."""
    assert "own ``append_event_next_seq`` seq allocation" not in _text(
        "agents/authz.py"
    )


@pytest.mark.issue("ISS-901")
def test_max_event_seq_docstring_does_not_blame_whole_log_read():
    """ISS-901 passage 2: _max_event_seq says the sink cannot use append_event_next_seq because of read_events."""
    assert "is why the engine sink cannot allocate through" not in _text(
        "agents/authz.py"
    )


@pytest.mark.issue("ISS-901")
def test_stamp_resume_marker_docstring_does_not_claim_whole_log_reread():
    """ISS-901 passage 3: _stamp_resume_marker claims the allocator re-reads EVERY row."""
    assert "re-reads EVERY row" not in _text("agents/execution_engine/engine.py")


@pytest.mark.issue("ISS-1079")
def test_resume_marker_tests_do_not_claim_next_seq_reads_whole_log():
    """ISS-1079: test prose must not say append_event_next_seq still derives seq via read_events."""
    t = _text("tests/agents/test_resume_marker_seq_allocation.py")
    assert not re.search(r"still derives the next seq via ``read_events", t)
