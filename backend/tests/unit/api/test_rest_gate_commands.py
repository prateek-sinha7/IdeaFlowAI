"""Static pins for the gate command vocabulary and its IDOR wiring (INV-12).

Two checks that read declarations and source text rather than exercising the endpoint:

  * ``GateCommand.action``'s ``Literal`` matches ``chat_router.GATE_ACTIONS``, the ONE
    authority for what a gate action is. ``Literal`` needs static values, so the schema
    necessarily spells them out; this pins the two together so a fifth action cannot be
    added to one home and silently diverge from the other.
  * A source-order ratchet: in ``resolve_gate``, the ownership predicate
    ``_review_gate_owned_by`` appears BEFORE every ``set_review_response`` write,
    including the redo/update_specs one (T-29-03-1 — the cross-user IDOR boundary).

Both parse text and need no store, no HTTP and no fixtures. The ENDPOINT behaviour they
guard — the owner gate actually returning 404 across users, the four actions resolving
the pause, the KAN-100 terminal fence and the KAN-94 unarmed-gate case — needs real rows
and lives in ``tests/integration/api/test_rest_gate_commands_api.py``.
"""

from __future__ import annotations

import re
from pathlib import Path


def test_gate_action_literal_matches_the_single_vocabulary_authority():
    """INV-12: ``chat_router.GATE_ACTIONS`` is the ONE authority for what a gate
    action is. ``Literal`` needs static values, so the schema necessarily spells
    them out — this pins the two together so a fifth action cannot be added to
    one home and silently diverge from the other."""
    from typing import get_args

    from app.api.chat_router import GATE_ACTIONS
    from app.api.run_commands import GateCommand

    literal_members = set(get_args(GateCommand.model_fields["action"].annotation))
    assert literal_members == set(GATE_ACTIONS), (
        "GateCommand.action's Literal drifted from chat_router.GATE_ACTIONS "
        f"({literal_members} != {set(GATE_ACTIONS)})"
    )


# ────────────────────────────────────────────────────────────────────────────
# Source-order wiring pin — ownership predicate gates set_review_response
# (grep-ratchet style, ported from the WS suite's #5 test onto run_commands.py)
# ────────────────────────────────────────────────────────────────────────────


def test_gate_handler_gates_set_review_response_on_ownership():
    import app.api.run_commands as rc_module

    source = Path(rc_module.__file__).read_text(encoding="utf-8")
    m = re.search(r"async def resolve_gate\((.*?)\n@router\.", source, re.S)
    assert m, "resolve_gate handler not found in run_commands.py"
    branch = m.group(1)

    guard_at = branch.find("_review_gate_owned_by(")
    write_at = branch.find("set_review_response(")
    assert guard_at != -1, "resolve_gate no longer checks _review_gate_owned_by"
    assert write_at != -1, "resolve_gate no longer calls set_review_response"
    assert guard_at < write_at, (
        "ownership must be verified BEFORE set_review_response "
        "(T-29-03-1: cross-user gate resolution)"
    )
    # The redo action rides the SAME owner-gated boundary — the redo write and
    # every other write are AFTER the ownership predicate.
    assert (
        'action == "redo"' in branch
    ), "resolve_gate no longer handles the redo action discriminator"
    last_write_at = branch.rfind("set_review_response(")
    assert guard_at < last_write_at, (
        "the redo/update_specs set_review_response must also be after ownership "
        "(redo rides the same IDOR boundary)"
    )
    # The read-only import of the relocated run-engine seam is present (W4a: the
    # shared predicates moved to app.api.run_engine — INV-12 extract-before-delete).
    assert "from app.api.run_engine import" in source
    assert "_review_gate_owned_by" in source
