"""agents/execution_engine/state_machine.py — WorkflowRun lifecycle state machine.

Phase 2: in-memory dict persistence.
Phase 3 (T071): upgrades the write target to DB (workflow_runs.status column).

Lifecycle states (10 — `specifying` removed per clarification, no trigger exists;
`diverted` added by 014-conditional-gates, RISK-03):
  clarifying, waiting_for_user, planning, analyzing, generating, revising,
  completed, failed, cancelled, diverted

State mapping:
  - planning        : Deep_Planner_Agent begins
  - clarifying      : ClarifyEngine opens its gate
  - waiting_for_user: paused for user input
  - analyzing       : Analyze_Agent (Validation_Gate) runs
  - generating      : domain agents begin
  - revising        : revision run in progress
  - completed/failed/cancelled/diverted : terminal states

Every transition is persisted BEFORE returning so a crash mid-transition
leaves the run in the new state (safer failure mode).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Valid lifecycle states
VALID_STATES: frozenset[str] = frozenset(
    {
        "clarifying",
        "waiting_for_user",
        "planning",
        "analyzing",
        "generating",
        "revising",
        "completed",
        "failed",
        "cancelled",
        # RISK-03 (014-conditional-gates): "diverted" joined TERMINAL_STATES below
        # but was missing here — transition(run_id, "diverted") would otherwise
        # raise StateMachineError("Invalid state 'diverted'") the moment the T29
        # cross-workflow-trigger wiring calls it (the same mechanism cancelled/
        # failed already use).
        "diverted",
    }
)

# Terminal states — no transitions out
TERMINAL_STATES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "diverted"})


class StateMachineError(Exception):
    """Raised on an invalid state transition."""


class StateMachine:
    """In-memory WorkflowRun state machine (Phase 2).

    Phase 3 upgrades `_persist()` to write to the DB workflow_runs.status column.
    """

    def __init__(self) -> None:
        # {run_id: current_state}
        self._states: dict[str, str] = {}

    def get_state(self, run_id: str) -> str | None:
        """Return the current state of a run, or None if unknown."""
        return self._states.get(run_id)

    def transition(self, run_id: str, new_state: str) -> str:
        """Transition a run to a new state. Persists before returning.

        Args:
            run_id: The WorkflowRun identifier.
            new_state: The target state (must be in VALID_STATES).

        Returns:
            The new state.

        Raises:
            StateMachineError: if new_state is invalid or the current state is terminal.
        """
        if new_state not in VALID_STATES:
            raise StateMachineError(
                f"Invalid state {new_state!r} for run {run_id!r}. "
                f"Valid states: {sorted(VALID_STATES)}"
            )

        current = self._states.get(run_id)
        if current in TERMINAL_STATES:
            raise StateMachineError(
                f"Cannot transition run {run_id!r} from terminal state {current!r} "
                f"to {new_state!r}."
            )

        # Persist BEFORE returning (Phase 2: in-memory; Phase 3: DB write)
        self._persist(run_id, new_state)
        logger.debug(
            "StateMachine: run=%s transition %s -> %s",
            run_id, current or "(none)", new_state,
        )
        return new_state

    def _persist(self, run_id: str, new_state: str) -> None:
        """Persist the state transition.

        Phase 2: in-memory dict.
        Phase 3 (T071): also write to workflow_runs.status DB column.
        """
        self._states[run_id] = new_state
        # Phase 3: persist to DB (best-effort — in-memory is the authoritative
        # source for the current process; DB is for cross-restart resumability)
        try:
            from app.models.database import SessionLocal
            from app.models.workflow import WorkflowRun

            db = SessionLocal()
            try:
                wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
                if wr:
                    wr.status = new_state
                    db.commit()
            finally:
                db.close()
        except Exception as exc:
            # Non-fatal: in-memory state is still correct for the current process
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "StateMachine._persist DB write failed (non-fatal): %s", exc
            )

    def forget_run(self, run_id: str) -> None:
        """Evict the state-machine entry for a completed/terminal run (D5 fix — KAN-139).

        Removes ``run_id`` from the in-memory ``_states`` dict so the process-lifetime
        dict does not grow unbounded. Called by ``_cleanup_pipeline`` (run_engine.py)
        so run-end and state-machine cleanup are one atomic operation. Replaces the
        private-dict reach at ``run_commands.py:412`` (the FIX-105 workaround) — that
        site can use this public method instead. Idempotent (pop with default).
        """
        self._states.pop(run_id, None)
        logger.debug("StateMachine: evicted state entry for run=%s", run_id)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_MACHINE: StateMachine | None = None


def get_state_machine() -> StateMachine:
    """Return the module-level StateMachine singleton."""
    global _MACHINE
    if _MACHINE is None:
        _MACHINE = StateMachine()
    return _MACHINE
