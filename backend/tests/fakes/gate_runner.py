"""In-memory fakes for the gate-audit seam (``read_gate_events`` / ``record_gate_event``).

Extracted from ``test_restart_resume`` when that module moved to
``tests/integration/agents/``: three unit modules
(``test_redo_prompt_contract``, ``test_spec_revision_context``,
``test_task_list_gate_lineage``) need only this fake, and a unit test must not
import from an integration test module to get it.

Nothing here touches a database, a socket, or the filesystem — it is safe for the
unit suite.
"""

from __future__ import annotations


class FakeGateEventRow:
    """A minimal ``gate_events``-shaped row (readers use step/gate/outcome only)."""

    def __init__(self, step, gate, outcome):
        self.step = step
        self.gate = gate
        self.outcome = outcome


class FakeGateRunner:
    """A KernelServices-shaped fake exposing the two gate-audit methods.

    Covers exactly what the gate re-entry seeding and its consumer reach:
    ``read_gate_events`` (returns the seeded rows) and ``record_gate_event``
    (appends, and remembers the call on ``recorded``).
    """

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.recorded: list[tuple] = []

    async def read_gate_events(self, run_id):
        return list(self._rows)

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.recorded.append((step, gate, outcome, detail))
        self._rows.append(FakeGateEventRow(step, gate, outcome))
        return "gate-event-id"


def seed_gate_reentry_ectx(
    run_id, spec, *, content="PERSISTED GATED OUTPUT", runner=None
):
    """Return an ectx armed for a gate re-entry.

    One durable ``summary`` ref for the gated agent + the ``gate_reentry`` sentinel
    + ``gate_agent_ids`` so ``_should_gate`` fires. ``scoped_store`` is left None, so
    ``_dual_write_artifact`` writes the in-memory graph only (the direct-unit path,
    mirroring ``test_redo_gate_safety._make_ectx``) — that is why this helper needs no
    database and belongs here rather than beside the durable resume suite.
    """
    # Deferred: the ectx builder lives in the unit suite, and importing it at module
    # scope would make this fakes module depend on test collection order.
    from tests.unit.agents.test_redo_gate_safety import _make_ectx

    ectx = _make_ectx(run_id, gate_agent_ids=[spec.id])
    ectx.artifacts.write_ref(
        run_id=run_id,
        owner_id="anon",
        workspace_id="ws",
        kind="summary",
        producer_step=spec.id,
        producer_agent=spec.id,
        task_id=None,
        content=content,
        location=f"artifact_refs/{spec.id}",
    )
    ectx.runner = runner
    ectx.gate_reentry = {
        "agent_id": spec.id,
        "artifact_kind": "summary",
        "gate_key": f"{run_id}:{spec.id}",
    }
    return ectx


# Legacy private aliases — the call sites predate the extraction.
_FakeGateEventRow = FakeGateEventRow
_FakeGateRunner = FakeGateRunner
_seed_gate_reentry_ectx = seed_gate_reentry_ectx
