"""agents/workflow_memory/memory.py — Per-user Workflow_Memory (Phase 3 / T067).

Implements FR-012: Cross-Session Constitution Memory.

Constraints (FR-012):
  - key: 1–255 chars
  - value: up to 1,048,576 chars
  - up to 1,000 entries per user
  - UNIQUE(user_id, key)
  - Entries MUST NOT be exposed to other users
  - Available across sessions and backend restarts

The Constitution is stored under the reserved key "constitution".
Per-Workflow Constitution overrides per-user Constitution (handled by the caller).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CONSTITUTION_KEY = "constitution"
_MAX_KEY_LEN = 255
_MAX_VALUE_LEN = 1_048_576
_MAX_ENTRIES_PER_USER = 1_000


class WorkflowMemoryError(Exception):
    """Raised on invalid inputs to WorkflowMemory."""


class WorkflowMemory:
    """Per-user key/value store backed by the workflow_memory DB table.

    Falls back to in-memory when the DB table doesn't exist yet (unit tests).
    """

    def __init__(self, use_db: bool = True) -> None:
        self._use_db = use_db
        # In-memory fallback: {user_id: {key: value}}
        self._mem: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Constitution helpers
    # ------------------------------------------------------------------

    async def get_constitution(self, user_id: str) -> str | None:
        """Retrieve the user's Constitution. None if not set."""
        return await self.get_entry(user_id, _CONSTITUTION_KEY)

    async def set_constitution(self, user_id: str, content: str) -> None:
        """Persist the user's Constitution."""
        await self.set_entry(user_id, _CONSTITUTION_KEY, content)

    async def delete_constitution(self, user_id: str) -> bool:
        """Delete the user's Constitution. Returns True if it existed."""
        return await self.delete_entry(user_id, _CONSTITUTION_KEY)

    # ------------------------------------------------------------------
    # Generic key/value operations
    # ------------------------------------------------------------------

    async def get_entry(self, user_id: str, key: str) -> str | None:
        """Retrieve a value by key. None if not found.

        Entries are user-scoped — user A cannot read user B's entries.
        """
        self._validate_key(key)
        if not self._use_db:
            return self._mem.get(user_id, {}).get(key)
        try:
            from app.models.database import SessionLocal
            from app.models.workflow_memory import WorkflowMemory as WMModel

            db = SessionLocal()
            try:
                row = (
                    db.query(WMModel)
                    .filter(WMModel.user_id == user_id, WMModel.key == key)
                    .first()
                )
                return row.value if row else None
            finally:
                db.close()
        except Exception as exc:
            if _is_table_missing(exc):
                return self._mem.get(user_id, {}).get(key)
            logger.warning("WorkflowMemory.get_entry failed: %s", exc)
            return None

    async def set_entry(self, user_id: str, key: str, value: str) -> None:
        """Upsert a key/value entry for the user.

        Raises WorkflowMemoryError if constraints are violated.
        """
        self._validate_key(key)
        self._validate_value(value)

        if not self._use_db:
            if user_id not in self._mem:
                self._mem[user_id] = {}
            if len(self._mem[user_id]) >= _MAX_ENTRIES_PER_USER and key not in self._mem[user_id]:
                raise WorkflowMemoryError(
                    f"User {user_id!r} has reached the {_MAX_ENTRIES_PER_USER}-entry limit."
                )
            self._mem[user_id][key] = value
            return

        try:
            from app.models.database import SessionLocal
            from app.models.workflow_memory import WorkflowMemory as WMModel

            db = SessionLocal()
            try:
                # Check entry count limit
                count = db.query(WMModel).filter(WMModel.user_id == user_id).count()
                existing = (
                    db.query(WMModel)
                    .filter(WMModel.user_id == user_id, WMModel.key == key)
                    .first()
                )
                if existing is None and count >= _MAX_ENTRIES_PER_USER:
                    raise WorkflowMemoryError(
                        f"User {user_id!r} has reached the {_MAX_ENTRIES_PER_USER}-entry limit."
                    )

                now = datetime.now(timezone.utc)
                if existing:
                    existing.value = value
                    existing.updated_at = now
                else:
                    import uuid
                    row = WMModel(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        key=key,
                        value=value,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(row)
                db.commit()
            finally:
                db.close()
        except WorkflowMemoryError:
            raise
        except Exception as exc:
            if _is_table_missing(exc):
                if user_id not in self._mem:
                    self._mem[user_id] = {}
                self._mem[user_id][key] = value
                return
            logger.warning("WorkflowMemory.set_entry failed: %s", exc)
            raise

    async def delete_entry(self, user_id: str, key: str) -> bool:
        """Delete a key/value entry. Returns True if it existed."""
        self._validate_key(key)
        if not self._use_db:
            user_data = self._mem.get(user_id, {})
            if key in user_data:
                del user_data[key]
                return True
            return False
        try:
            from app.models.database import SessionLocal
            from app.models.workflow_memory import WorkflowMemory as WMModel

            db = SessionLocal()
            try:
                row = (
                    db.query(WMModel)
                    .filter(WMModel.user_id == user_id, WMModel.key == key)
                    .first()
                )
                if row:
                    db.delete(row)
                    db.commit()
                    return True
                return False
            finally:
                db.close()
        except Exception as exc:
            if _is_table_missing(exc):
                user_data = self._mem.get(user_id, {})
                if key in user_data:
                    del user_data[key]
                    return True
                return False
            logger.warning("WorkflowMemory.delete_entry failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or len(key) > _MAX_KEY_LEN:
            raise WorkflowMemoryError(
                f"Key must be 1–{_MAX_KEY_LEN} characters, got {len(key)!r}."
            )

    @staticmethod
    def _validate_value(value: str) -> None:
        if len(value) > _MAX_VALUE_LEN:
            raise WorkflowMemoryError(
                f"Value exceeds {_MAX_VALUE_LEN:,} character limit ({len(value):,} chars)."
            )


def _is_table_missing(exc: Exception) -> bool:
    err = str(exc).lower()
    return "no such table" in err or "does not exist" in err or "failed to locate a name" in err


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_MEMORY: WorkflowMemory | None = None


def get_workflow_memory() -> WorkflowMemory:
    """Return the module-level WorkflowMemory singleton."""
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = WorkflowMemory()
    return _MEMORY
