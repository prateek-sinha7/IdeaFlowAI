"""backend/tests/unit/test_analysis_report_cap.py — ISS-127.

``GateCommand.analysis_report`` (and its sibling ``MessageCommand.analysis_report``,
``backend/app/api/run_commands.py``) has no length cap anywhere on its path into
the composed spec-revision prompt (traced end to end on the ISS-127 card:
``run_commands.py:127`` -> ``resolve_gate`` -> ``engine.py:5387``
``ectx.spec_revision_context = analysis_report`` -> injected into every dispatch
of the 3-agent spec-revision sub-pipeline). A ``grep`` for slicing / ``MAX_*`` /
``len(...)`` truncation on that path returns nothing, so an owner-supplied string
of arbitrary size is accepted by the request schema — a cost-amplification gap on
a workflow whose measured token ceiling is 37.3M.

These tests assert the schema rejects an oversized ``analysis_report`` instead of
accepting it uncapped.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.run_commands import GateCommand, MessageCommand

OVERSIZED = "x" * 2_000_000


@pytest.mark.issue("ISS-127")
@pytest.mark.xfail(reason="ISS-127 unfixed", strict=True)
def test_gate_command_analysis_report_is_capped():
    """``update_specs`` gate action: an oversized ``analysis_report`` must be
    rejected at the schema, not injected uncapped into every spec-revision
    dispatch."""
    with pytest.raises(ValidationError):
        GateCommand(
            gate_key="run:step",
            action="update_specs",
            analysis_report=OVERSIZED,
        )


@pytest.mark.issue("ISS-127")
@pytest.mark.xfail(reason="ISS-127 unfixed", strict=True)
def test_message_command_analysis_report_is_capped():
    """Sibling field named on the ISS-127 card: ``MessageCommand.analysis_report``
    (``POST /api/runs/{id}/messages``) shares the same uncapped-length gap."""
    with pytest.raises(ValidationError):
        MessageCommand(message_id="m1", analysis_report=OVERSIZED)
