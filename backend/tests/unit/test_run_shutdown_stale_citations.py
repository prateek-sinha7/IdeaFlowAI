"""tests/unit/test_run_shutdown_stale_citations.py — ISS-104.

``app/api/run_shutdown.py`` cites specific line numbers in
``app/api/run_commands.py`` to point a reader at the code its comments
describe. Those citations have drifted from the code they describe (the
lines they name now hold unrelated code), so a fixer who follows one lands
in the wrong place.

Each test resolves one cited line number and asserts the code the comment
claims lives there actually does. They fail today because the citations are
stale; they pass once the citations are corrected to the real locations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_BACKEND_APP = Path(__file__).resolve().parents[2] / "app"
_RUN_COMMANDS = _BACKEND_APP / "api" / "run_commands.py"


def _line(path: Path, lineno: int) -> str:
    """1-indexed line lookup, matching how the citations are written."""
    return path.read_text().splitlines()[lineno - 1]


@pytest.mark.issue("ISS-104")
@pytest.mark.xfail(reason="ISS-104 unfixed", strict=True)
def test_concierge_hold_citation_points_at_the_never_cancel_comment():
    """run_shutdown.py:99 cites run_commands.py:1401 for the comment that
    says to hold the Concierge task and NEVER cancel it on generator
    teardown. That text now lives elsewhere."""
    assert "NEVER cancel it on" in _line(_RUN_COMMANDS, 1401)


@pytest.mark.issue("ISS-104")
@pytest.mark.xfail(reason="ISS-104 unfixed", strict=True)
def test_chat_reply_persist_citation_points_at_the_durable_write():
    """run_shutdown.py:100 cites run_commands.py:1356 for the durable
    ``chat_reply`` row write inside ``_drive``'s second try. That write now
    lives elsewhere."""
    assert 'type="chat_reply"' in _line(_RUN_COMMANDS, 1356)


@pytest.mark.issue("ISS-104")
@pytest.mark.xfail(reason="ISS-104 unfixed", strict=True)
def test_driver_terminal_write_citations_point_at_the_status_writes():
    """run_shutdown.py:278 cites run_commands.py:2155 (launch) and :2473
    (revision) as the driver's own terminal status write. Neither line
    holds a status write today."""
    assert "status" in _line(_RUN_COMMANDS, 2155)
    assert "status" in _line(_RUN_COMMANDS, 2473)
