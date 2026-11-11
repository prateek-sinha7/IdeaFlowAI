"""Builders for AI Workflow Builder rows (sessions, messages, tool rows, revisions).

Each builder returns an ORM instance that is not attached to any database
session, with every ``NOT NULL`` column filled (``owner_id`` and ``workspace_id``
stamped with ``user_id``, as the real store does). Pass keyword overrides to change
any column. ``BuilderSessionFactory.create_kwargs`` returns the keyword arguments
of ``create_session`` for tests that go through a store instead.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_TOOL_OK,
    MESSAGE_STATUS_USER_ACCEPTED,
    SESSION_MODE_CREATE,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)

DEFAULT_USER_ID = "user-1"
DEFAULT_SKILL_HASH = "skill-hash-1"
_counter = itertools.count(1)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp_owner(values: dict[str, Any]) -> dict[str, Any]:
    """Default ``owner_id`` and ``workspace_id`` to ``user_id`` (the store's rule)."""
    values.setdefault("owner_id", values["user_id"])
    values.setdefault("workspace_id", values["user_id"])
    return values


class BuilderSessionFactory:
    """Builds ``WorkflowBuilderSession`` rows and ``create_session`` arguments."""

    @staticmethod
    def create_kwargs(**overrides: Any) -> dict[str, Any]:
        """Return valid keyword arguments for ``create_session`` (after ``user_id``)."""
        values: dict[str, Any] = {
            "title": f"Session {next(_counter)}",
            "mode": SESSION_MODE_CREATE,
            "skill_hash": DEFAULT_SKILL_HASH,
        }
        values.update(overrides)
        return values

    @staticmethod
    def build(**overrides: Any) -> WorkflowBuilderSession:
        """Return an un-attached session row with every required column set."""
        now = _now()
        values: dict[str, Any] = {
            "id": _new_id(),
            "user_id": DEFAULT_USER_ID,
            "title": f"Session {next(_counter)}",
            "mode": SESSION_MODE_CREATE,
            "target_trust": "user",
            "skill_hash": DEFAULT_SKILL_HASH,
            "next_seq": 1,
            "turn_count": 0,
            "clarify_turns_without_draft": 0,
            "created_at": now,
            "updated_at": now,
        }
        values.update(overrides)
        return WorkflowBuilderSession(**_stamp_owner(values))


def build_message(
    *, session_id: str, seq: int, role: str = MESSAGE_ROLE_USER, **overrides: Any
) -> WorkflowBuilderMessage:
    """Return an un-attached message row; defaults fit ``role`` (user by default)."""
    turn_id = overrides.pop("turn_id", None) or _new_id()
    status_by_role = {
        MESSAGE_ROLE_USER: MESSAGE_STATUS_USER_ACCEPTED,
        MESSAGE_ROLE_ASSISTANT: MESSAGE_STATUS_COMPLETED,
        MESSAGE_ROLE_TOOL: MESSAGE_STATUS_TOOL_OK,
    }
    values: dict[str, Any] = {
        # An assistant row's id is its turn id.
        "id": turn_id if role == MESSAGE_ROLE_ASSISTANT else _new_id(),
        "session_id": session_id,
        "user_id": DEFAULT_USER_ID,
        "seq": seq,
        "role": role,
        "turn_id": turn_id,
        "status": status_by_role[role],
        "content": f"{role} message {seq}",
        "created_at": _now(),
    }
    values.update(overrides)
    return WorkflowBuilderMessage(**_stamp_owner(values))


def build_tool_row(
    *, session_id: str, seq: int, turn_id: str, **overrides: Any
) -> WorkflowBuilderMessage:
    """Return an un-attached tool row under ``turn_id`` with a minimal ``tool`` payload."""
    overrides.setdefault("tool", {"name": "propose_manifest", "args": {}})
    return build_message(
        session_id=session_id,
        seq=seq,
        role=MESSAGE_ROLE_TOOL,
        turn_id=turn_id,
        **overrides,
    )


def build_revision(
    *, session_id: str, revision: int = 1, **overrides: Any
) -> WorkflowBuilderDraft:
    """Return an un-attached revision (``workflow_builder_drafts``) row."""
    values: dict[str, Any] = {
        "id": _new_id(),
        "session_id": session_id,
        "user_id": DEFAULT_USER_ID,
        "revision": revision,
        "kind": DRAFT_KIND_ACCEPTED,
        "manifest": {"id": "wf", "agents": []},
        "manifest_hash": f"manifest-hash-{revision}",
        "created_at": _now(),
    }
    values.update(overrides)
    return WorkflowBuilderDraft(**_stamp_owner(values))
