"""Property test for the trust the Server_Gate accepts a draft at.

# Feature: ai-workflow-builder, Property 9: The draft's trust is the least that works

For any combination of "compiles at user", "compiles at db", requested trust and
the user's maximum trust, an accepted draft's trust is ``user`` whenever it
compiles at ``user``. It is ``db`` only when it fails at ``user``, compiles at
``db``, ``db`` was requested and the user may use ``db``. Every other case is a
rejection.

**Validates: Requirements 7.11, 37.4**

The system under test is ``ServerGate.check``. The save check (``validate``) is a
stub built per generated case: it raises ``HTTPException(422)`` at a trust that
the case says does not compile, and records the trusts it was asked about. The
builder rules and the model entitlement gate run for real on a small manifest
that passes both, so the trust decision is the only thing that varies.

The oracle is a four-way table written from the property statement. It does not
call any gate helper.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.events import TargetTrust
from app.agents.workflow_builder.ports import GateResult
from app.api.workflow_builder.gate import ServerGate

_MANIFEST: dict[str, Any] = {
    "steps": [{"key": "draft", "agent": "custom-agent", "prompt": "Write the draft."}]
}
_FAIL_TEXT = "Compile check failed."
_LABEL = "workflow:trust-property"

_trusts = st.sampled_from(("user", "db"))


class _StubSaveCheck:
    """A save check that compiles only at the trusts in ``compiles_at``."""

    def __init__(self, compiles_at: frozenset[str]) -> None:
        self._compiles_at = compiles_at
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, manifest: dict[str, Any] | None, source_label: str, *, trust: str
    ) -> None:
        self.calls.append((source_label, trust))
        if trust not in self._compiles_at:
            raise HTTPException(status_code=422, detail=_FAIL_TEXT)


def _run(
    *,
    user_ok: bool,
    db_ok: bool,
    requested: TargetTrust,
    max_trust: TargetTrust,
) -> tuple[GateResult, _StubSaveCheck]:
    compiles_at = frozenset(
        trust for trust, ok in (("user", user_ok), ("db", db_ok)) if ok
    )
    stub = _StubSaveCheck(compiles_at)
    gate = ServerGate(
        tier="enterprise",
        max_trust=max_trust,
        step_models=(),
        label=_LABEL,
        validate=stub,
    )
    result = asyncio.run(gate.check(_MANIFEST, requested_trust=requested))
    return result, stub


# Feature: ai-workflow-builder, Property 9: The draft's trust is the least that works
@settings(max_examples=100, deadline=None)
@given(
    user_ok=st.booleans(),
    db_ok=st.booleans(),
    requested=_trusts,
    max_trust=_trusts,
)
def test_check_accepts_least_trust_when_draft_compiles(
    user_ok: bool, db_ok: bool, requested: TargetTrust, max_trust: TargetTrust
) -> None:
    result, stub = _run(
        user_ok=user_ok, db_ok=db_ok, requested=requested, max_trust=max_trust
    )

    if user_ok:
        expected = "user"
    elif db_ok and requested == "db" and max_trust == "db":
        expected = "db"
    else:
        expected = None

    if expected is None:
        assert result.accepted is False
        assert result.trust is None
        assert result.issues
        # The "compiles at db" hint appears only when the agent could act on it:
        # it did not ask for db, the user may use db, and the draft compiles there.
        hint = any("target_trust='db'" in issue.message for issue in result.issues)
        assert hint == (
            not user_ok and db_ok and requested == "user" and max_trust == "db"
        )
    else:
        assert result.accepted is True
        assert result.trust == expected
        assert result.issues == ()

    # Never above what was asked for or what the user may use.
    if result.accepted and result.trust == "db":
        assert requested == "db"
        assert max_trust == "db"
    # A user who may only use "user" never has the draft checked at "db".
    if max_trust == "user":
        assert all(trust == "user" for _, trust in stub.calls)
    # Every save check carries the caller's label.
    assert all(label == _LABEL for label, _ in stub.calls)
