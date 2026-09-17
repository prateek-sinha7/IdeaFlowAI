"""Explicit, in-order deletion of everything a user owns.

Cognito-only auth migration (``.kiro/specs/login/prompt.md``), Decision 6's FK
policy: *"For ``workflow_runs``, ``workflow_definitions``, ``workflow_memory``,
``user_agents``, ``chat_sessions``(+``messages``): explicit application-level
deletion in dependency order inside the same transaction as the user delete.
Emit per-table counts in the audit event. No silent ownership reassignment."*

Why these five tables are NOT ``ON DELETE CASCADE`` like the other four
------------------------------------------------------------------------
Migration ``0039`` added ``ondelete="CASCADE"`` to ``revoked_tokens``,
``user_api_keys``, ``user_github_credentials`` and ``handoff_sessions`` — rows
that are purely dependent bookkeeping with no standalone meaning. These five
are different: they are the user's actual WORK PRODUCT (runs, saved workflows,
custom agents, chat history), and — for ``workflow_runs`` specifically — the
root of a NINE-table fan-out (``run_events``, ``artifact_refs``,
``workflow_clarifications``, ``gate_events``, ``hook_runs``, ``exec_runs``,
``run_capabilities``, ``validation_results``, ``subagent_runs``, plus
``wave_runs``) that a bare database cascade would delete silently with no
record of what was removed. Decision 6 asks for that record.

This mirrors ``api/runs.py::delete_run``'s per-run cleanup almost exactly — the
same nine child tables, the same self-referential ``parent_run_id`` nulling —
generalized from "one run" to "every run this user owns", plus the four
sibling tables ``delete_run`` never had to touch because it deletes one run,
not an account.

Ordering within the transaction
--------------------------------
1. Every table that hangs off ``workflow_runs.id`` (nine tables), scoped to
   this user's run ids.
2. Null ``parent_run_id`` on any run that points at one of this user's runs —
   preserves revision-chain rows belonging to OTHER users pointing at a run
   about to disappear (defensive; in practice a revision's parent is always
   the same owner, but nulling costs nothing and avoids relying on that).
3. The user's own ``workflow_runs`` rows.
4. ``workflow_memory``, ``user_agents`` (independent of runs).
5. ``workflows`` (saved workflows — ``WorkflowDefinition``).
6. ``messages`` then ``chat_sessions`` (messages FK into chat_sessions, no
   cascade — must go first).

``revoked_tokens``, ``user_api_keys``, ``user_github_credentials`` and
``handoff_sessions`` are deliberately NOT touched here: they cascade
automatically when the ``users`` row is deleted (migration 0039), and
re-deleting them explicitly would just be redundant work inside the same
transaction.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.artifact_ref import ArtifactRef
from app.models.chat import ChatSession, Message
from app.models.exec_runs import ExecRun
from app.models.gate_events import GateEvent
from app.models.hook_runs import HookRun
from app.models.run_capabilities import RunCapabilities
from app.models.run_event import RunEvent
from app.models.subagent_run import SubagentRun
from app.models.user_agent import UserAgent
from app.models.validation_results import ValidationResult
from app.models.wave_run import WaveRun
from app.models.workflow import WorkflowRun
from app.models.workflow_clarification import WorkflowClarification
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_memory import WorkflowMemory


def delete_user_dependents(db: Session, user_id: str) -> dict[str, int]:
    """Delete every row this user owns, EXCEPT the ``users`` row itself.

    Runs entirely inside the caller's transaction — does not commit. The
    caller (``api/admin.py::delete_user``) deletes the ``User`` row and commits
    once, so a failure anywhere in this function rolls the whole delete back
    rather than leaving a half-deleted account.

    Returns per-table row counts for the audit event (Decision 6: "emit
    per-table counts"). Tables with zero rows are OMITTED rather than
    reported as 0, keeping the audit line proportional to what actually
    happened for the common case (a user with no runs).
    """
    counts: dict[str, int] = {}

    def _record(table: str, n: int) -> None:
        if n:
            counts[table] = n

    run_ids = [
        row[0] for row in db.query(WorkflowRun.id).filter(WorkflowRun.user_id == user_id)
    ]

    if run_ids:
        # Nine tables that fan out from workflow_runs.id, in no particular
        # order relative to each other (none of them reference one another) —
        # order matters only relative to workflow_runs itself, deleted after.
        _record(
            "run_events",
            db.query(RunEvent)
            .filter(RunEvent.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "artifact_refs",
            db.query(ArtifactRef)
            .filter(ArtifactRef.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "workflow_clarifications",
            db.query(WorkflowClarification)
            .filter(WorkflowClarification.workflow_run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "gate_events",
            db.query(GateEvent)
            .filter(GateEvent.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "hook_runs",
            db.query(HookRun)
            .filter(HookRun.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "exec_runs",
            db.query(ExecRun)
            .filter(ExecRun.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "run_capabilities",
            db.query(RunCapabilities)
            .filter(RunCapabilities.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "validation_results",
            db.query(ValidationResult)
            .filter(ValidationResult.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "subagent_runs",
            db.query(SubagentRun)
            .filter(SubagentRun.parent_run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "wave_runs",
            db.query(WaveRun)
            .filter(WaveRun.run_id.in_(run_ids))
            .delete(synchronize_session=False),
        )

        # Self-referential FK: null parent_run_id on any run (this user's or,
        # defensively, another owner's) pointing at a run about to be deleted —
        # preserves the revision-chain row instead of cascading its deletion.
        db.query(WorkflowRun).filter(WorkflowRun.parent_run_id.in_(run_ids)).update(
            {WorkflowRun.parent_run_id: None}, synchronize_session=False
        )

        _record(
            "workflow_runs",
            db.query(WorkflowRun)
            .filter(WorkflowRun.id.in_(run_ids))
            .delete(synchronize_session=False),
        )

    _record(
        "workflow_memory",
        db.query(WorkflowMemory)
        .filter(WorkflowMemory.user_id == user_id)
        .delete(synchronize_session=False),
    )
    _record(
        "user_agents",
        db.query(UserAgent)
        .filter(UserAgent.user_id == user_id)
        .delete(synchronize_session=False),
    )
    _record(
        "workflows",
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.user_id == user_id)
        .delete(synchronize_session=False),
    )

    chat_session_ids = [
        row[0]
        for row in db.query(ChatSession.id).filter(ChatSession.user_id == user_id)
    ]
    if chat_session_ids:
        _record(
            "messages",
            db.query(Message)
            .filter(Message.chat_session_id.in_(chat_session_ids))
            .delete(synchronize_session=False),
        )
        _record(
            "chat_sessions",
            db.query(ChatSession)
            .filter(ChatSession.id.in_(chat_session_ids))
            .delete(synchronize_session=False),
        )

    return counts
