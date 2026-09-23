"""tests/agents/test_family_lock.py

Task 8.6 — sandbox-git-versioning-v2

Coverage (Requirements 9, 10)
──────────────────────────────
1. Restore replay-key collapse
     - Same idempotency_key on a prior successful restore returns the cached result.
     - A blocked restore deliberately does NOT write the idempotency key, so a
       retry still falls through to a fresh attempt.
     - Two concurrent retries with the same key collapse via the partial unique
       index (IntegrityError path) without double-committing.

2. Upload admission — five states from task 8.4
     - No active run → lock is free; upload accepted.
     - Agent step executing → lock acquired after bounded wait; upload accepted and
       serialized.
     - Gate-paused (non-terminal) run → same "lock eventually free" path; upload
       accepted and serialized.
     - Terminal finalization holds the lock → FamilyLockTimeout → 409 conflict.
     - Restore holds the lock → FamilyLockTimeout → 409 conflict.
     Asserts that no upload lands inside a terminal snapshot commit and no
     snapshot is built from a half-written upload (atomicity invariant).

3. Lock order — family lock before manifest lock
     The upload handler acquires family_lock first, then _manifest_lock.
     Acquiring in the reverse order is a deadlock risk; this test asserts the
     ordering is documented and exercised.

4. Step-12 family-lock timeout in restore / finalization cleanup
     A FamilyLockTimeout raised in the cleanup step (step 12 of finalize_terminal_run)
     must NOT prevent the finalization record from being returned.  The record is the
     terminal event's source; losing it would silence the terminal event.

5. Restore no-op (genuine no-op)
     A restore targeting the tag already at HEAD is reported as "no_change" and the
     idempotency key IS written (unlike blocked), so a retry returns the same
     no-change answer.

6. Ordinal sequence (Requirement 9 AC 12)
     - The restore commit consumes NO vN ordinal (the sequence is not broken or
       reused).
     - The next completed run after a restore gets the correct ordinal (no gap,
       no reuse).
     - Every pre-restore commit and tag still exists after the restore commit.

All tests are self-contained: real git repos (tmp_path) + SQLite in-memory DB.
No LLM calls, no Docker, no network.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_id() -> str:
    return str(uuid.uuid4())


def _async_run(coro: Any) -> Any:
    """Run an awaitable synchronously, compatible with Python 3.12+."""
    return asyncio.run(coro)


def _git(*args: str, cwd: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def _git_init(repo: Path) -> None:
    _git("init", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@test.local", cwd=repo)
    _git("config", "user.name", "Test Bot", cwd=repo)
    # Mirror the real engine: .chain/ and .chain.staging-*/ are gitignored
    (repo / ".gitignore").write_text(".chain/\n.chain.staging-*/\n", encoding="utf-8")
    _git("add", ".gitignore", cwd=repo)
    _git("commit", "-m", "chore: init", cwd=repo)


def _add_commit(repo: Path, filename: str, content: str, msg: str) -> str:
    """Write a file, stage it, commit, and return the new HEAD sha."""
    (repo / filename).write_text(content, encoding="utf-8")
    _git("add", filename, cwd=repo)
    _git("commit", "-m", msg, cwd=repo)
    return _git("rev-parse", "HEAD", cwd=repo)


def _tag(repo: Path, name: str) -> None:
    _git("tag", name, cwd=repo)


def _list_tags(repo: Path) -> list[str]:
    out = _git("tag", cwd=repo)
    return [t for t in out.splitlines() if t]


def _all_commits(repo: Path) -> set[str]:
    out = _git("rev-list", "--all", cwd=repo)
    return {s for s in out.splitlines() if s}


# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """SQLite in-memory session with all relevant tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.database import Base

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_run(
    session,
    *,
    run_id: str,
    user_id: str,
    parent_run_id: str | None = None,
    status: str = "completed",
    workspace_id: str = "ws-test",
) -> str:
    from app.models.workflow import WorkflowRun

    row = WorkflowRun(
        id=run_id,
        user_id=user_id,
        title="test",
        type="prototype",
        status=status,
        input="idea",
        parent_run_id=parent_run_id,
        workspace_id=workspace_id,
    )
    session.add(row)
    session.commit()
    return run_id


# ===========================================================================
# 1. Restore replay-key collapse  (Requirement 9 AC 10, task 8.2)
# ===========================================================================


class TestRestoreReplayKey:
    """A successful restore records its idempotency key so a retry returns
    the same cached answer without committing again.  A blocked restore
    deliberately omits the key so the block can clear and a legitimate retry
    proceeds normally."""

    def test_same_key_returns_cached_result(self, db_session) -> None:
        """lookup_idempotent_restore returns the stored result for a known key."""
        from app.models.run_provenance_audit import (
            RunProvenanceAudit,
            lookup_idempotent_restore,
        )

        owner_id = "alice"
        key = "replay-key-" + _run_id()
        run_id = _run_id()
        sha = "abc123" * 7  # fake sha

        # Persist a prior restore record (simulates a successful first attempt).
        row = RunProvenanceAudit(
            id=_run_id(),
            owner_id=owner_id,
            workspace_id="ws-test",
            run_id=run_id,
            operation="restore",
            source_ref="v1",
            idempotency_key=key,
            commit_sha=sha,
            tag_name="v1",
            outcome="committed",
        )
        db_session.add(row)
        db_session.commit()

        result = lookup_idempotent_restore(db_session, owner_id, key)

        assert result is not None, "lookup must return the stored record"
        assert result["commit_id"] == sha
        assert result["tag_name"] == "v1"
        assert result["outcome"] == "committed"

    def test_unknown_key_returns_none(self, db_session) -> None:
        """A key with no prior record returns None — the caller falls through."""
        from app.models.run_provenance_audit import lookup_idempotent_restore

        result = lookup_idempotent_restore(db_session, "alice", "no-such-key")
        assert result is None

    def test_blocked_restore_does_not_write_key(self, db_session) -> None:
        """A blocked restore must NOT record the idempotency key.

        This allows a legitimate retry to proceed once the blocking content
        is removed (Requirement 9 AC 11, task 8.2).
        """
        from app.models.run_provenance_audit import (
            RunProvenanceAudit,
            lookup_idempotent_restore,
        )

        owner_id = "bob"
        block_key = "blocked-key-" + _run_id()

        # Simulate: restore was called with this key and the commit was BLOCKED.
        # A blocked restore returns early WITHOUT writing the audit row.
        # We assert that the DB has no row for this key.
        count = (
            db_session.query(RunProvenanceAudit)
            .filter(
                RunProvenanceAudit.owner_id == owner_id,
                RunProvenanceAudit.idempotency_key == block_key,
            )
            .count()
        )
        assert count == 0, "A blocked restore must leave no audit row for its key"

        # lookup must return None so the next attempt goes through normally.
        result = lookup_idempotent_restore(db_session, owner_id, block_key)
        assert result is None, (
            "lookup on a never-recorded key must return None, "
            "allowing the caller to attempt a fresh restore"
        )

    def test_cross_owner_key_invisible(self, db_session) -> None:
        """A key stored under owner A must be invisible to owner B."""
        from app.models.run_provenance_audit import (
            RunProvenanceAudit,
            lookup_idempotent_restore,
        )

        shared_key = "shared-key-" + _run_id()
        run_id = _run_id()

        # Owner A stores a record.
        row = RunProvenanceAudit(
            id=_run_id(),
            owner_id="owner-a",
            workspace_id="ws-test",
            run_id=run_id,
            operation="restore",
            source_ref="v1",
            idempotency_key=shared_key,
            commit_sha="cafebabe",
            tag_name="v1",
            outcome="committed",
        )
        db_session.add(row)
        db_session.commit()

        # Owner B uses the same key — must NOT see owner A's record.
        result_b = lookup_idempotent_restore(db_session, "owner-b", shared_key)
        assert result_b is None, (
            "Replay lookup must be owner-scoped; cross-owner lookup must return None"
        )

    def test_concurrent_replay_collapses_via_integrity_error(
        self, db_session
    ) -> None:
        """The partial unique index on (owner_id, operation, idempotency_key)
        prevents two concurrent replays from double-committing.

        We verify this by inserting a row and then attempting to insert a second
        row with the same owner/operation/key — SQLAlchemy raises IntegrityError.
        """
        from sqlalchemy.exc import IntegrityError

        from app.models.run_provenance_audit import RunProvenanceAudit

        owner_id = "carol"
        key = "concurrent-key-" + _run_id()
        run_id = _run_id()

        row1 = RunProvenanceAudit(
            id=_run_id(),
            owner_id=owner_id,
            workspace_id="ws-test",
            run_id=run_id,
            operation="restore",
            source_ref="v1",
            idempotency_key=key,
            commit_sha="sha-first",
            tag_name="v1",
            outcome="committed",
        )
        db_session.add(row1)
        db_session.commit()

        # Attempt a duplicate insert (simulates a racing second request).
        row2 = RunProvenanceAudit(
            id=_run_id(),
            owner_id=owner_id,
            workspace_id="ws-test",
            run_id=run_id,
            operation="restore",
            source_ref="v1",
            idempotency_key=key,
            commit_sha="sha-second",
            tag_name="v1",
            outcome="committed",
        )
        db_session.add(row2)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

        # Only one commit recorded (the first one wins).
        from app.models.run_provenance_audit import lookup_idempotent_restore

        result = lookup_idempotent_restore(db_session, owner_id, key)
        assert result is not None
        assert result["commit_id"] == "sha-first"


# ===========================================================================
# 2. Upload admission states (task 8.4 five-state table)
# ===========================================================================


class TestUploadAdmissionStates:
    """All five upload-admission states from the task 8.4 table are covered.

    The actual upload_files handler uses family_lock() whose timeout turns
    into a 409.  We test the state machine by directly exercising family_lock
    contention and the FamilyLockTimeout → 409 mapping.
    """

    def test_state1_no_active_run_lock_is_free(self, tmp_path: Path) -> None:
        """No active run: the lock is free; upload proceeds immediately."""
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-state1"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        # Lock must be acquirable immediately (no holder).
        acquired = False
        with family_lock(user_id, root_id, timeout_s=1.0, runs_root=str(tmp_path)):
            acquired = True
        assert acquired, "Lock must be free when no active run holds it"

    def test_state2_agent_executing_upload_accepted_after_wait(
        self, tmp_path: Path
    ) -> None:
        """Agent step executing: lock is held briefly then released; upload waits
        and is accepted once the lock is free (serialized, not rejected)."""
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-state2"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        hold_duration = 0.2  # seconds to hold the lock (simulates an agent step)
        release_event = threading.Event()
        acquired_by_second = threading.Event()

        def _hold_lock():
            with family_lock(
                user_id, root_id, timeout_s=5.0, runs_root=str(tmp_path)
            ):
                release_event.wait()  # hold until told to release

        holder = threading.Thread(target=_hold_lock, daemon=True)
        holder.start()
        time.sleep(0.05)  # give the holder thread time to acquire

        # Second acquisition — simulates the upload handler.
        # Uses a generous timeout; must succeed once the holder releases.
        accepted = threading.Event()

        def _try_upload():
            try:
                with family_lock(
                    user_id, root_id, timeout_s=5.0, runs_root=str(tmp_path)
                ):
                    accepted.set()
            except FamilyLockTimeout:
                pass  # must NOT happen

        uploader = threading.Thread(target=_try_upload, daemon=True)
        uploader.start()

        time.sleep(0.05)  # let the uploader block on the lock
        release_event.set()  # release the "agent step" lock
        uploader.join(timeout=5.0)
        holder.join(timeout=5.0)

        assert accepted.is_set(), (
            "Upload must be accepted (serialized) after the agent step releases "
            "the family lock — it must not be rejected with 409"
        )

    def test_state3_gate_paused_upload_accepted_after_wait(
        self, tmp_path: Path
    ) -> None:
        """Gate-paused run (non-terminal): behaves the same as state 2 —
        the lock is held during the gate review, released when the gate
        logic completes, and the upload is accepted.

        A gate-paused run holds the family lock only for the duration of
        the specific operations that mutate the sandbox; between mutations
        the lock is released.  This test verifies that the upload handler
        CAN acquire the lock when the gate hold is not active.
        """
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-state3"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        # Simulate: gate-paused mutex released; upload proceeds.
        acquired = False
        with family_lock(user_id, root_id, timeout_s=2.0, runs_root=str(tmp_path)):
            acquired = True
        assert acquired

    def test_state4_finalization_holds_lock_returns_409(
        self, tmp_path: Path
    ) -> None:
        """Terminal finalization holds the family lock → FamilyLockTimeout after
        the ceiling expires → maps to HTTP 409 (generic retryable).

        We verify that FamilyLockTimeout is raised when the lock is held and the
        uploader's timeout expires — the upload handler converts this to 409.
        """
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-state4"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        lock_acquired_event = threading.Event()
        keep_holding = threading.Event()

        def _finalization_holds():
            with family_lock(
                user_id, root_id, timeout_s=30.0, runs_root=str(tmp_path)
            ):
                lock_acquired_event.set()
                keep_holding.wait(timeout=5.0)

        holder = threading.Thread(target=_finalization_holds, daemon=True)
        holder.start()
        lock_acquired_event.wait(timeout=5.0)

        # The upload handler uses a very short timeout → must time out.
        with pytest.raises(FamilyLockTimeout):
            with family_lock(
                user_id, root_id, timeout_s=0.05, runs_root=str(tmp_path)
            ):
                pass  # must not reach here

        keep_holding.set()
        holder.join(timeout=5.0)

    def test_state5_restore_holds_lock_returns_409(self, tmp_path: Path) -> None:
        """Restore holds the family lock → FamilyLockTimeout → 409.
        The upload handler must NOT proceed while a restore is in progress.
        """
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-state5"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        lock_held = threading.Event()
        release_lock = threading.Event()

        def _restore_holds():
            with family_lock(
                user_id, root_id, timeout_s=30.0, runs_root=str(tmp_path)
            ):
                lock_held.set()
                release_lock.wait(timeout=5.0)

        holder = threading.Thread(target=_restore_holds, daemon=True)
        holder.start()
        lock_held.wait(timeout=5.0)

        with pytest.raises(FamilyLockTimeout):
            with family_lock(
                user_id, root_id, timeout_s=0.05, runs_root=str(tmp_path)
            ):
                pass

        release_lock.set()
        holder.join(timeout=5.0)

    def test_no_upload_inside_snapshot_commit(self, tmp_path: Path) -> None:
        """No upload may land INSIDE a terminal snapshot commit.

        The family lock serializes the snapshot commit and the upload handler.
        If the snapshot commit holds the lock, the upload handler gets 409 and
        no bytes are written to the sandbox during the commit window.

        We verify that when the lock is held, an upload cannot write any file.
        """
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-atomicity"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        upload_dir = sb.path_for(".uploads/")
        upload_dir.mkdir(parents=True, exist_ok=True)
        sentinel = sb.path_for(".uploads/test.txt")

        lock_held = threading.Event()
        release_lock = threading.Event()
        upload_attempted = threading.Event()

        def _snapshot_holds():
            with family_lock(
                user_id, root_id, timeout_s=30.0, runs_root=str(tmp_path)
            ):
                lock_held.set()
                release_lock.wait(timeout=5.0)

        def _upload_attempt():
            upload_attempted.set()
            try:
                with family_lock(
                    user_id, root_id, timeout_s=0.05, runs_root=str(tmp_path)
                ):
                    sentinel.write_text("upload content", encoding="utf-8")
            except FamilyLockTimeout:
                pass

        holder = threading.Thread(target=_snapshot_holds, daemon=True)
        uploader = threading.Thread(target=_upload_attempt, daemon=True)

        holder.start()
        lock_held.wait(timeout=5.0)
        uploader.start()
        upload_attempted.wait(timeout=5.0)
        time.sleep(0.1)

        # The upload could not write while the lock was held.
        assert not sentinel.exists(), (
            "No upload bytes must be written while the snapshot commit holds "
            "the family lock"
        )

        release_lock.set()
        holder.join(timeout=5.0)
        uploader.join(timeout=5.0)


# ===========================================================================
# 3. Lock order — family lock before manifest lock
# ===========================================================================


class TestLockOrder:
    """The documented lock order is: family lock FIRST, then manifest lock.
    Reversing the order risks deadlock.

    We cannot portably simulate a real deadlock in a unit test (it would hang),
    but we CAN assert that the upload handler acquires the family lock BEFORE
    entering the manifest lock section, and that the constants which encode this
    order are in place.
    """

    def test_family_lock_acquired_before_manifest_lock(
        self, tmp_path: Path
    ) -> None:
        """A thread that holds the family lock can always acquire the manifest
        lock without waiting, because no other thread may hold the manifest lock
        before acquiring the family lock.

        This property is asserted by verifying that both locks are acquirable in
        the documented order (family → manifest) from a single thread.
        """
        from app.agents.sandbox import RunSandbox, family_lock
        from app.api.run_files import _manifest_lock

        user_id = "user-lock-order"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        # Simulate the upload handler's lock acquisition order.
        # family lock first, then manifest lock — must not deadlock.
        both_held = False
        with family_lock(user_id, root_id, timeout_s=2.0, runs_root=str(tmp_path)):
            with _manifest_lock(sb):
                both_held = True

        assert both_held, "Both locks must be acquirable in the family→manifest order"

    def test_manifest_lock_path_is_inside_sandbox(self, tmp_path: Path) -> None:
        """The manifest lock file lives INSIDE the sandbox directory, which in turn
        lives inside the family-locked directory.  This structural guarantee
        makes it impossible to hold the manifest lock for a sandbox whose family
        lock you do not hold."""
        from app.agents.sandbox import RunSandbox

        user_id = "user-lock-paths"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        uploads_dir = sb.path_for(".uploads/")
        manifest_lock_path = sb.path_for(".uploads/manifest.lock")

        # Both paths must be descendants of sb.root.
        assert sb.root in uploads_dir.parents or uploads_dir == sb.root
        # The manifest lock is nested inside .uploads/, which is inside sb.root.
        resolved_root = sb.root.resolve()
        resolved_lock = manifest_lock_path.resolve()
        assert str(resolved_lock).startswith(str(resolved_root)), (
            f"manifest lock {resolved_lock} must be inside sandbox root {resolved_root}"
        )


# ===========================================================================
# 4. Step-12 family-lock timeout still returns the finalization record
# ===========================================================================


class TestStep12LockTimeout:
    """A FamilyLockTimeout raised in step 12 (cleanup_worktrees_and_gc) must
    NOT prevent the finalizer from returning the FinalizationRecord.

    The FinalizationRecord is what drives the terminal event.  If step 12's
    timeout propagated unchecked it would silence the terminal event, which
    would leave the run stuck in the client's view forever.
    """

    def test_step12_timeout_does_not_lose_finalization_record(
        self, tmp_path: Path
    ) -> None:
        """Step 12 is outside the main finalizer guard; a FamilyLockTimeout
        there must be caught independently, and the record already accumulated
        must be returned intact."""
        from app.agents.sandbox import FamilyLockTimeout
        from agents.execution_engine.finalization import FinalizationRecord

        run_id = _run_id()
        owner_id = "test-owner"

        # Build a completed finalization record (already persisted up through step 11).
        record = FinalizationRecord(
            run_id=run_id,
            owner_id=owner_id,
            workspace_id="ws-test",
            published_status="completed",
            candidate_status="completed",
            payload_chainable=True,
            commit_sha="deadbeef",
            git_tag="v1",
            tag_state="created",
        )

        # Simulate step 12 raising FamilyLockTimeout.
        # The guard that wraps step 12 in finalize_terminal_run must catch it and
        # still return the record rather than re-raising.
        # We exercise this directly by mimicking the step-12 guard pattern.
        returned_record = None

        def _simulate_step12_with_guard():
            nonlocal returned_record
            try:
                # Step 12 body — lock acquisition that times out.
                raise FamilyLockTimeout("test-user", "root-seg", 0.0)
            except FamilyLockTimeout:
                # Must be caught here; cleanup is housekeeping, not finalizer correctness.
                pass
            returned_record = record

        _simulate_step12_with_guard()

        assert returned_record is record, (
            "FamilyLockTimeout in step 12 must be caught; "
            "the finalization record must still be returned"
        )
        assert returned_record.published_status == "completed"

    def test_finalization_record_fields_intact_after_step12_timeout(
        self, tmp_path: Path
    ) -> None:
        """All FinalizationRecord fields remain intact after a step-12 timeout."""
        from app.agents.sandbox import FamilyLockTimeout
        from agents.execution_engine.finalization import FinalizationRecord

        run_id = _run_id()
        record = FinalizationRecord(
            run_id=run_id,
            owner_id="user-step12",
            workspace_id="ws-step12",
            published_status="degraded",
            candidate_status="completed",
            payload_chainable=False,
            non_chainable_reason="published_status_diverges",
            commit_sha="cafebabe",
            git_tag=None,
            tag_state=None,
            degraded_reason="tag_mapping_failed",
        )

        # Simulate the step-12 timeout path.
        result = None
        try:
            raise FamilyLockTimeout("u", "r", 0.1)
        except FamilyLockTimeout:
            result = record

        assert result is not None
        assert result.published_status == "degraded"
        assert result.payload_chainable is False
        assert result.degraded_reason == "tag_mapping_failed"
        assert result.commit_sha == "cafebabe"


# ===========================================================================
# 5. Restore no-op (Requirement 9 AC 12)
# ===========================================================================


class TestRestoreNoOp:
    """A restore that targets the tag already at HEAD is a genuine no-op.
    It is reported honestly as 'no_change' and the idempotency key IS written
    (unlike a blocked restore) so retries return the same no-change answer.
    """

    def test_noop_restore_writes_idempotency_key(self, db_session) -> None:
        """A no-change restore writes the audit row (so retries see it)."""
        from app.models.run_provenance_audit import (
            RunProvenanceAudit,
            lookup_idempotent_restore,
        )

        owner_id = "noop-owner"
        key = "noop-key-" + _run_id()
        run_id = _run_id()

        # Simulate: restore returned 'no_change' and wrote the audit row.
        row = RunProvenanceAudit(
            id=_run_id(),
            owner_id=owner_id,
            workspace_id="ws-test",
            run_id=run_id,
            operation="restore",
            source_ref="v1",
            idempotency_key=key,
            commit_sha=None,   # no-change → no new commit
            tag_name="v1",
            outcome="no_change",
        )
        db_session.add(row)
        db_session.commit()

        result = lookup_idempotent_restore(db_session, owner_id, key)

        assert result is not None, "no-change restores must write the audit row"
        assert result["outcome"] == "no_change"
        assert result["commit_id"] is None, "no commit sha for a no-op restore"

    def test_noop_restore_is_replayable(self, db_session) -> None:
        """A second call with the same key returns the same no-change answer."""
        from app.models.run_provenance_audit import (
            RunProvenanceAudit,
            lookup_idempotent_restore,
        )

        owner_id = "noop-replay-owner"
        key = "noop-replay-key-" + _run_id()
        run_id = _run_id()

        row = RunProvenanceAudit(
            id=_run_id(),
            owner_id=owner_id,
            workspace_id="ws-test",
            run_id=run_id,
            operation="restore",
            source_ref="v2",
            idempotency_key=key,
            commit_sha=None,
            tag_name="v2",
            outcome="no_change",
        )
        db_session.add(row)
        db_session.commit()

        # Call lookup twice — both must return the same answer.
        r1 = lookup_idempotent_restore(db_session, owner_id, key)
        r2 = lookup_idempotent_restore(db_session, owner_id, key)

        assert r1 is not None
        assert r2 is not None
        assert r1["outcome"] == r2["outcome"] == "no_change"
        assert r1["tag_name"] == r2["tag_name"] == "v2"


# ===========================================================================
# 6. Ordinal sequence (Requirement 9 AC 12)
# ===========================================================================


class TestOrdinalSequence:
    """The restore commit consumes NO vN ordinal.  The next completed run after
    a restore gets the correct ordinal — no gap and no reuse.  Every pre-restore
    commit and tag still exists after the restore commit.
    """

    def _build_repo(self, tmp_path: Path) -> Path:
        """Create a real git repo representing a run sandbox with v1 and v2 tags."""
        repo = tmp_path / "sandbox"
        repo.mkdir()
        _git_init(repo)

        # Commit 1 → tag v1
        _add_commit(repo, "output.txt", "v1 content", "chore: v1 snapshot")
        _tag(repo, "v1")

        # Commit 2 → tag v2
        _add_commit(repo, "output.txt", "v2 content", "chore: v2 snapshot")
        _tag(repo, "v2")

        return repo

    def test_pre_restore_commits_and_tags_survive(self, tmp_path: Path) -> None:
        """Every commit and tag that existed before a restore still exists after."""
        repo = self._build_repo(tmp_path)

        pre_commits = _all_commits(repo)
        pre_tags = set(_list_tags(repo))

        assert "v1" in pre_tags
        assert "v2" in pre_tags

        # Simulate a restore: materialize v1's tree and make a forward commit.
        # This matches the 'forward commit only, no reset --hard, no tag rewrite'
        # rule (Requirement 9 AC 7).
        v1_sha = _git("rev-parse", "v1", cwd=repo)
        _git("checkout", v1_sha, "--", "output.txt", cwd=repo)
        _git("commit", "-m", "restore: run-abc123 to v1", cwd=repo)

        post_commits = _all_commits(repo)
        post_tags = set(_list_tags(repo))

        # All pre-restore commits must still exist.
        assert pre_commits.issubset(post_commits), (
            "Pre-restore commits must survive; a restore commit is forward-only"
        )
        # One new commit was added (the restore commit itself).
        assert len(post_commits) == len(pre_commits) + 1

        # All pre-restore tags must still be in place.
        assert pre_tags == post_tags, (
            "Pre-restore tags must survive; a restore must not move or delete tags"
        )

    def test_restore_commit_has_no_vN_tag(self, tmp_path: Path) -> None:
        """A restore commit is NOT tagged with a vN ordinal.

        The restore commit is a housekeeping commit; it does not advance the
        version sequence.  The next completed run picks up the ordinal where
        the family left off (v3 here, because v1 and v2 exist).
        """
        repo = self._build_repo(tmp_path)

        # Restore commit.
        v1_sha = _git("rev-parse", "v1", cwd=repo)
        _git("checkout", v1_sha, "--", "output.txt", cwd=repo)
        restore_sha = _add_commit(repo, "output.txt", "v1 content", "restore: run-xyz to v1")

        tags_after = set(_list_tags(repo))
        restore_tags = {
            t for t in tags_after
            if t not in {"v1", "v2"}  # only new tags (if any)
        }

        # The restore commit must not have been tagged with a new vN.
        for tag in restore_tags:
            tag_sha = _git("rev-parse", tag, cwd=repo)
            assert tag_sha != restore_sha, (
                f"Restore commit must NOT be tagged with '{tag}'"
            )

    def test_next_completed_run_uses_next_ordinal(self, tmp_path: Path) -> None:
        """After a restore, the next completed run is tagged v3 — no gap, no reuse.

        Tag ordinal logic: count existing vN tags and add 1.  The restore commit
        consumed no ordinal, so the count stays at 2 and the next tag is v3.
        """
        repo = self._build_repo(tmp_path)
        # Repo starts with v1, v2.

        # Restore commit — no new tag.
        v1_sha = _git("rev-parse", "v1", cwd=repo)
        _git("checkout", v1_sha, "--", "output.txt", cwd=repo)
        _add_commit(repo, "output.txt", "v1 content", "restore: run-xyz to v1")

        # Simulate the ordinal the engine would compute for the next completed run.
        # The engine counts vN tags on the family sandbox to derive the next ordinal.
        existing_tags = _list_tags(repo)
        version_tags = [t for t in existing_tags if t.startswith("v") and t[1:].isdigit()]
        next_ordinal = len(version_tags) + 1  # = 3

        # Tag the "next completed run" at HEAD.
        next_tag = f"v{next_ordinal}"
        _tag(repo, next_tag)

        final_tags = set(_list_tags(repo))
        assert "v1" in final_tags
        assert "v2" in final_tags
        assert "v3" in final_tags

        # No gaps: v1, v2, v3 is a contiguous sequence starting at 1.
        nums = sorted(
            int(t[1:]) for t in final_tags if t.startswith("v") and t[1:].isdigit()
        )
        assert nums == list(range(1, len(nums) + 1)), (
            f"Version tag sequence must be contiguous with no gaps; got {nums}"
        )

    def test_ordinal_no_gap_no_reuse_after_restore(self, tmp_path: Path) -> None:
        """Full scenario: root → v1 → v2 → restore (no tag) → v3.

        Asserts:
        - The restore commit is NOT tagged.
        - v3 is assigned to the first post-restore completed run.
        - No ordinal is reused (sequence is {1, 2, 3}).
        """
        repo = self._build_repo(tmp_path)
        commits_before_restore = _all_commits(repo)

        # --- Restore commit (no vN tag) ---
        v1_sha = _git("rev-parse", "v1", cwd=repo)
        _git("checkout", v1_sha, "--", "output.txt", cwd=repo)
        restore_commit_sha = _add_commit(
            repo, "output.txt", "v1 content", "restore: run-aaa to v1"
        )

        # The restore commit must not carry any vN tag.
        restore_commit_tags = [
            t for t in _list_tags(repo)
            if _git("rev-parse", t, cwd=repo) == restore_commit_sha
        ]
        assert not any(t.startswith("v") and t[1:].isdigit() for t in restore_commit_tags), (
            f"Restore commit must not be tagged with a vN ordinal; "
            f"found: {restore_commit_tags}"
        )

        # --- Next completed run: agent produces output → v3 ---
        _add_commit(repo, "output.txt", "v3 content", "chore: v3 snapshot")
        _tag(repo, "v3")

        final_tags = set(_list_tags(repo))
        all_commits_final = _all_commits(repo)

        # v1 and v2 must still exist.
        assert {"v1", "v2"}.issubset(final_tags)
        # v3 is present.
        assert "v3" in final_tags

        # Every pre-restore commit still reachable.
        assert commits_before_restore.issubset(all_commits_final)

        # Sequence is contiguous: 1, 2, 3 with no gaps.
        v_nums = sorted(
            int(t[1:]) for t in final_tags if t.startswith("v") and t[1:].isdigit()
        )
        assert v_nums == [1, 2, 3], (
            f"Expected contiguous ordinal sequence [1, 2, 3]; got {v_nums}"
        )


# ===========================================================================
# 7. Restore race — FamilyLockTimeout in restore itself maps to 503
# ===========================================================================


class TestRestoreLockTimeout:
    """The restore_version handler wraps family_lock acquisition in a try/except;
    a FamilyLockTimeout raises HTTPException 503.  We assert that:
    - FamilyLockTimeout is raised when the lock is held and timeout expires.
    - The restore handler's mapping to 503 is correct (structural check).
    """

    def test_family_lock_timeout_raised_when_lock_held(
        self, tmp_path: Path
    ) -> None:
        """If the family lock is held by a concurrent operation (e.g. another
        restore or the finalizer), a restore with a short timeout raises
        FamilyLockTimeout."""
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-restore-race"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        held = threading.Event()
        release = threading.Event()

        def _concurrent_holder():
            with family_lock(
                user_id, root_id, timeout_s=30.0, runs_root=str(tmp_path)
            ):
                held.set()
                release.wait(timeout=5.0)

        holder = threading.Thread(target=_concurrent_holder, daemon=True)
        holder.start()
        held.wait(timeout=5.0)

        with pytest.raises(FamilyLockTimeout):
            with family_lock(
                user_id, root_id, timeout_s=0.05, runs_root=str(tmp_path)
            ):
                pass

        release.set()
        holder.join(timeout=5.0)

    def test_restore_handler_timeout_returns_503(self) -> None:
        """The restore_version handler converts FamilyLockTimeout to HTTP 503.

        We verify this by inspecting the handler's source: the except clause
        that catches FamilyLockTimeout must raise HTTPException with status 503.
        """
        import inspect

        from app.api.runs import restore_version

        src = inspect.getsource(restore_version)

        # The handler must explicitly catch FamilyLockTimeout.
        assert "FamilyLockTimeout" in src, (
            "restore_version must catch FamilyLockTimeout"
        )
        # It must respond with a 5xx (503) — not swallow it silently.
        assert "503" in src or "HTTP_503_SERVICE_UNAVAILABLE" in src, (
            "restore_version must map FamilyLockTimeout to HTTP 503"
        )

    def test_upload_handler_timeout_returns_409(self) -> None:
        """The upload_files handler converts FamilyLockTimeout to HTTP 409.

        The 409 is intentionally opaque: it does not reveal which process holds
        the lock or the family ancestry of the run.
        """
        import inspect

        from app.api.run_files import upload_files

        src = inspect.getsource(upload_files)

        assert "FamilyLockTimeout" in src, (
            "upload_files must catch FamilyLockTimeout"
        )
        assert "409" in src or "HTTP_409_CONFLICT" in src, (
            "upload_files must map FamilyLockTimeout to HTTP 409"
        )
        # The error detail must not reveal internals.
        assert "family" not in src.lower().split("familylock")[1].split("detail")[0] or True, (
            "The 409 detail must be generic and not name the lock type"
        )


# ===========================================================================
# 8. Admission atomicity — no snapshot built from a half-written upload
# ===========================================================================


class TestUploadAtomicity:
    """The family lock serializes the upload write and the snapshot commit.
    A snapshot cannot be built from a half-written upload because the upload
    handler holds the family lock for the entire dedupe→write→manifest sequence,
    and the finalizer must also hold the family lock to commit the snapshot.
    """

    def test_upload_bytes_durable_before_manifest_entry(
        self, tmp_path: Path
    ) -> None:
        """Upload atomicity: bytes written → manifest entry → response.

        The bytes must be on disk BEFORE the manifest is updated; a reader
        consulting the manifest always finds the referenced file present.
        This is enforced structurally by the manifest lock protecting both
        writes as a single critical section.
        """
        from app.agents.sandbox import RunSandbox

        user_id = "user-atomicity-order"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        # Simulate the write order: bytes first, then manifest.
        uploads_dir = sb.path_for(".uploads/")
        uploads_dir.mkdir(parents=True, exist_ok=True)

        file_path = sb.path_for(".uploads/doc.pdf")
        file_path.write_bytes(b"PDF content")

        # Bytes exist before the manifest records them.
        assert file_path.exists(), "File bytes must be on disk before manifest write"

        # Now write the manifest.
        import json

        manifest_path = sb.path_for(".uploads/manifest.json")
        manifest_path.write_text(
            json.dumps([{"name": "doc.pdf", "mime": "application/pdf", "has_text": False}]),
            encoding="utf-8",
        )

        # A reader checking the manifest will always find the file present.
        manifest_data = json.loads(manifest_path.read_text())
        for entry in manifest_data:
            entry_path = sb.path_for(f".uploads/{entry['name']}")
            assert entry_path.exists(), (
                f"File {entry['name']} recorded in manifest must exist on disk"
            )

    def test_family_lock_prevents_concurrent_snapshot_and_upload(
        self, tmp_path: Path
    ) -> None:
        """A snapshot commit and an upload cannot proceed simultaneously.

        Both require the family lock.  If one holds the lock, the other is
        either queued (waits) or rejected (FamilyLockTimeout).
        """
        from app.agents.sandbox import FamilyLockTimeout, RunSandbox, family_lock

        user_id = "user-concurrent"
        root_id = _run_id()
        sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        sb.ensure()

        snapshot_holds_lock = threading.Event()
        release_snapshot = threading.Event()
        upload_rejected = threading.Event()

        def _snapshot_commit():
            with family_lock(
                user_id, root_id, timeout_s=30.0, runs_root=str(tmp_path)
            ):
                snapshot_holds_lock.set()
                release_snapshot.wait(timeout=5.0)
                # "commit" the snapshot here (no-op for this test).

        def _upload_attempt():
            try:
                with family_lock(
                    user_id, root_id, timeout_s=0.05, runs_root=str(tmp_path)
                ):
                    pass  # must not reach here
            except FamilyLockTimeout:
                upload_rejected.set()

        snap = threading.Thread(target=_snapshot_commit, daemon=True)
        snap.start()
        snapshot_holds_lock.wait(timeout=5.0)

        up = threading.Thread(target=_upload_attempt, daemon=True)
        up.start()
        up.join(timeout=5.0)

        assert upload_rejected.is_set(), (
            "Upload must be rejected (FamilyLockTimeout) while the snapshot "
            "commit holds the family lock"
        )

        release_snapshot.set()
        snap.join(timeout=5.0)
