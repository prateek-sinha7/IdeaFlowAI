"""Builder reports: per-user storage (Req 44.7) and the success metrics (Req 44.6).

``storage_report`` combines the Session_Store row counts and payload sizes from
``BuilderStore.storage_usage_by_user`` with the size of each user's sandbox
folders on disk. ``collect_success_metrics`` feeds user-scoped facts from the
store to the pure functions in ``success_metrics``. Neither one returns message
text, manifests or canvas content: counts and byte sizes only.

Both functions are synchronous and touch the database or the disk, so async
callers (lifecycle at startup) run them in a worker thread.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from app.agents.workflow_builder.sandbox import BuilderSandbox, resolve_builder_root
from app.agents.workflow_builder.success_metrics import (
    SessionFact,
    SuccessMetrics,
    TurnGateFact,
    compute_success_metrics,
)
from app.api.workflow_builder.store import UserStorageRows

__all__ = [
    "StorageReport",
    "StorageStore",
    "SuccessMetricsStore",
    "UserStorage",
    "collect_success_metrics",
    "directory_size",
    "log_storage_report",
    "storage_report",
]

logger = logging.getLogger("app.api.workflow_builder.reporting")

_PLACEHOLDER_SESSION: Final = "storage-report"


class StorageStore(Protocol):
    """The part of the Session_Store the storage report reads."""

    def storage_usage_by_user(self) -> list[UserStorageRows]:
        """Return row counts and payload bytes per user."""
        ...


class SuccessMetricsStore(Protocol):
    """The part of the Session_Store the success metrics read (user-scoped)."""

    def list_session_metric_facts(self, user_id: str) -> list[SessionFact]:
        """Return one fact per session of the user."""
        ...

    def list_turn_gate_facts(self, user_id: str) -> list[TurnGateFact]:
        """Return one fact per turn of the user that called ``propose_draft``."""
        ...


@dataclass(frozen=True, slots=True)
class UserStorage:
    """Storage one user holds: Session_Store rows and sandbox folders."""

    user_id: str
    session_count: int
    message_count: int
    draft_count: int
    db_bytes: int
    canvas_state_bytes: int
    sandbox_bytes: int

    @property
    def total_bytes(self) -> int:
        """Payload bytes in the database plus bytes in the user's sandboxes."""
        return self.db_bytes + self.sandbox_bytes


@dataclass(frozen=True, slots=True)
class StorageReport:
    """Per-user storage, largest first, plus sandbox bytes no database user owns.

    Attributes:
        users: One entry per user with Session_Store rows, by ``total_bytes``
            descending, then user id.
        unattributed_sandbox_bytes: Bytes in sandbox folders whose user has no
            Session_Store rows (for example a user whose sessions were all
            deleted but whose folder remains).
    """

    users: tuple[UserStorage, ...]
    unattributed_sandbox_bytes: int

    @property
    def total_bytes(self) -> int:
        """All bytes the report covers."""
        return sum(u.total_bytes for u in self.users) + self.unattributed_sandbox_bytes

    def as_dict(self) -> dict[str, object]:
        """Return the report as a JSON-serialisable dict."""
        return {
            "total_bytes": self.total_bytes,
            "unattributed_sandbox_bytes": self.unattributed_sandbox_bytes,
            "users": [
                {
                    "user_id": u.user_id,
                    "session_count": u.session_count,
                    "message_count": u.message_count,
                    "draft_count": u.draft_count,
                    "db_bytes": u.db_bytes,
                    "canvas_state_bytes": u.canvas_state_bytes,
                    "sandbox_bytes": u.sandbox_bytes,
                    "total_bytes": u.total_bytes,
                }
                for u in self.users
            ],
        }


def directory_size(path: Path) -> int:
    """Return the total size in bytes of the regular files under ``path``.

    Symlinks are not followed and counted as nothing. A missing folder is 0.
    Entries that vanish or cannot be read while walking (a concurrent delete)
    are skipped.
    """
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _sandbox_sizes(root: Path) -> dict[str, int]:
    """Return ``{user folder name: bytes}`` for the folders directly under ``root``."""
    try:
        children = [e for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return {}
    return {entry.name: directory_size(Path(entry.path)) for entry in children}


def storage_report(
    store: StorageStore, *, sandbox_root: str | Path | None = None
) -> StorageReport:
    """Build the per-user storage report (Req 44.7).

    Args:
        store: The Session_Store (``BuilderStore`` or its fake).
        sandbox_root: Builder sandbox root. ``None`` uses ``resolve_builder_root()``.

    Returns:
        A report with one entry per user that has Session_Store rows. Sandbox
        bytes come from the user's folder under the root; folders that match no
        such user are summed in ``unattributed_sandbox_bytes``.
    """
    root = (
        resolve_builder_root() if sandbox_root is None else Path(sandbox_root).resolve()
    )
    sizes = _sandbox_sizes(root)
    users: list[UserStorage] = []
    attributed: set[str] = set()
    for rows in store.storage_usage_by_user():
        folder = BuilderSandbox(rows.user_id, _PLACEHOLDER_SESSION, root=root).user_seg
        attributed.add(folder)
        users.append(
            UserStorage(
                user_id=rows.user_id,
                session_count=rows.session_count,
                message_count=rows.message_count,
                draft_count=rows.draft_count,
                db_bytes=rows.db_bytes,
                canvas_state_bytes=rows.canvas_state_bytes,
                sandbox_bytes=sizes.get(folder, 0),
            )
        )
    users.sort(key=lambda u: (-u.total_bytes, u.user_id))
    unattributed = sum(size for name, size in sizes.items() if name not in attributed)
    return StorageReport(users=tuple(users), unattributed_sandbox_bytes=unattributed)


def log_storage_report(report: StorageReport) -> None:
    """Log the report: one INFO summary line, then one INFO line per user.

    Only ids, counts and byte sizes are logged.
    """
    logger.info(
        "builder storage report users=%d total_bytes=%d unattributed_sandbox_bytes=%d",
        len(report.users),
        report.total_bytes,
        report.unattributed_sandbox_bytes,
    )
    for u in report.users:
        logger.info(
            "builder storage user=%s sessions=%d messages=%d drafts=%d "
            "db_bytes=%d canvas_state_bytes=%d sandbox_bytes=%d",
            u.user_id,
            u.session_count,
            u.message_count,
            u.draft_count,
            u.db_bytes,
            u.canvas_state_bytes,
            u.sandbox_bytes,
        )


def collect_success_metrics(
    store: SuccessMetricsStore, user_ids: Iterable[str]
) -> SuccessMetrics:
    """Compute the three success metrics over the given users' sessions and turns.

    Reads are user-scoped: the store is queried once per user id, and the facts
    are pooled before the metrics are computed, so the median is over all users'
    saved sessions rather than a median of medians.
    """
    sessions: list[SessionFact] = []
    turns: list[TurnGateFact] = []
    for user_id in user_ids:
        sessions.extend(store.list_session_metric_facts(user_id))
        turns.extend(store.list_turn_gate_facts(user_id))
    return compute_success_metrics(sessions, turns)
