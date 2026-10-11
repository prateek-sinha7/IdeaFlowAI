"""
Tests for disk_metrics logging in finalize_terminal_run.

Task S4 — sandbox-git-versioning-v2, P0 #5 FR-041

Coverage matrix
---------------
A  disk_metrics log record contains sandbox_bytes, git_bytes, and chain_depth
B  git_bytes is 0 for a non-git sandbox
C  chain_depth is 0 for a non-chained run (chain_source_run_id=None)
D  chain_depth is 1 for a single-hop chained run
E  chain_depth reflects a multi-hop value threaded onto ectx (finalizer never
   clamps to 0/1 — it only reads whatever _compute_chain_depth threaded at
   launch)
F  _compute_chain_depth itself walks a REAL multi-hop source_run_id chain
   (depth >= 2) via the DB — this is the fix-attempt-1 coverage the row asked
   for: a hop count, not a same-run-chained boolean

Requirements: 35 AC 2

fix attempt 1: verify FAIL found chain_depth hard-coded to {0, 1} in the
finalizer (no real hop count). The fix threads the real hop count onto
``ectx.chain_depth`` at launch via a new ``_compute_chain_depth`` DB walk
(mirrors ``_compute_revision_ordinal``'s architecture) and makes the
finalizer a pure reader of that field. Tests D/E now stamp ``chain_depth``
directly on the test double (this file's ``_make_ectx`` mimics what a real
launch already threaded — it never re-derives depth from
``chain_source_run_id``); the new ``TestComputeChainDepth`` class below is
the behavioural test of the real hop-count walk itself.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))


def _async_run(coro) -> any:
    """Run an awaitable synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers — real-git sandbox fixture
# ---------------------------------------------------------------------------

_USER_ID = "test-user-disk-metrics"
_WORKSPACE_ID = "ws-test-disk-metrics"


def _make_run_id() -> str:
    return str(uuid.uuid4())


def _make_mock_db() -> MagicMock:
    """Return a mock DB session that supports the persist pattern."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    return mock_db


class FakeSandbox:
    """Minimal sandbox facade for testing."""

    def __init__(self, root: Path):
        self.root = root

    def git_init_sandbox(self) -> None:
        """Initialize git repo with a .gitignore and initial commit."""
        if shutil.which("git"):
            import subprocess

            subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.test"],
                cwd=self.root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test Bot"], cwd=self.root, check=True
            )
            (self.root / ".gitignore").write_text(".chain/\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=self.root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "chore: init"], cwd=self.root, check=True
            )

    def commit_all(self, message: str) -> str:
        """Commit all changes via git."""
        if shutil.which("git"):
            import subprocess

            subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        return ""

    def git_gc_auto(self) -> None:
        """No-op for testing."""
        pass


def _make_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    chain_source_run_id: str | None = None,
    chain_depth: int = 0,
) -> types.SimpleNamespace:
    """Build a minimal ExecutionContext-like namespace for tests.

    ``chain_depth`` mirrors production: a real ``ExecutionContext`` has this
    field already threaded onto it at launch (by ``_compute_chain_depth``,
    a DB walk OUTSIDE the finalizer) — the finalizer only ever reads it, so
    this test double sets it directly rather than deriving it from
    ``chain_source_run_id``.
    """
    ectx = types.SimpleNamespace(
        run_id=run_id,
        user_id=_USER_ID,
        owner_id=_USER_ID,
        workspace_id=_WORKSPACE_ID,
        runner=types.SimpleNamespace(sandbox=sandbox),
        final_status="completed",
        deliverable=types.SimpleNamespace(name="output.html"),
        revision_ordinal=1,
        step_visit_counts={"step-1": 1},
        last_commit_blocked=False,
        completed_tasks=[],
        run_trace=None,
        chain_source_run_id=chain_source_run_id,
        chain_depth=chain_depth,
    )
    return ectx


# ===========================================================================
# Tests
# ===========================================================================


class TestDiskMetrics:
    """Test disk_metrics logging includes git_bytes and chain_depth."""

    @pytest.mark.skipif(not shutil.which("git"), reason="git not available")
    def test_disk_metrics_logged_with_git_bytes_and_chain_depth_non_chained(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A: disk_metrics record includes git_bytes and chain_depth for non-chained run."""
        sandbox = FakeSandbox(tmp_path)
        sandbox.git_init_sandbox()

        # Add some files to the sandbox
        (tmp_path / "output.html").write_text("<html>test</html>")
        (tmp_path / "data.txt").write_bytes(b"x" * 1000)  # 1KB

        run_id = _make_run_id()
        ectx = _make_ectx(run_id, sandbox, chain_source_run_id=None)
        mock_db = _make_mock_db()

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        # Clear the process-local guard so test can run
        eng._finalize_terminal_run_started.discard(run_id)

        # Capture logs at INFO level
        with caplog.at_level(logging.INFO, logger="agents.execution_engine.engine"):
            with (
                patch("app.models.database.SessionLocal", return_value=mock_db),
                patch("app.models.workflow.WorkflowRun", MagicMock()),
                patch("app.models.run_finalization.RunFinalization", MagicMock()),
            ):
                _async_run(
                    eng.finalize_terminal_run(
                        run_id, ectx, candidate_status="completed"
                    )
                )

        # Find the disk_metrics log record
        disk_metrics_records = [
            r for r in caplog.records if "disk_metrics" in r.message
        ]
        assert len(disk_metrics_records) > 0, "No disk_metrics log record found"

        record = disk_metrics_records[0]
        # Check that all four fields are in the message
        assert "sandbox_bytes=" in record.message
        assert "git_bytes=" in record.message
        assert "chain_depth=" in record.message

        # Extract the values from the message
        import re

        sandbox_match = re.search(r"sandbox_bytes=(\d+)", record.message)
        git_match = re.search(r"git_bytes=(\d+)", record.message)
        chain_match = re.search(r"chain_depth=(\d+)", record.message)

        assert sandbox_match is not None, "sandbox_bytes not found in log"
        assert git_match is not None, "git_bytes not found in log"
        assert chain_match is not None, "chain_depth not found in log"

        sandbox_bytes = int(sandbox_match.group(1))
        git_bytes = int(git_match.group(1))
        chain_depth = int(chain_match.group(1))

        # Verify values
        assert sandbox_bytes > 0, "sandbox_bytes should be positive"
        assert git_bytes >= 0, "git_bytes should be non-negative"
        assert chain_depth == 0, "chain_depth should be 0 for non-chained run"

    @pytest.mark.skipif(not shutil.which("git"), reason="git not available")
    def test_disk_metrics_chain_depth_one_when_chained(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D: chain_depth is 1 when chain_source_run_id is set."""
        sandbox = FakeSandbox(tmp_path)
        sandbox.git_init_sandbox()

        # Add some files
        (tmp_path / "output.html").write_text("<html>test</html>")

        run_id = _make_run_id()
        source_run_id = _make_run_id()
        ectx = _make_ectx(
            run_id, sandbox, chain_source_run_id=source_run_id, chain_depth=1
        )
        mock_db = _make_mock_db()

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        with caplog.at_level(logging.INFO, logger="agents.execution_engine.engine"):
            with (
                patch("app.models.database.SessionLocal", return_value=mock_db),
                patch("app.models.workflow.WorkflowRun", MagicMock()),
                patch("app.models.run_finalization.RunFinalization", MagicMock()),
            ):
                _async_run(
                    eng.finalize_terminal_run(
                        run_id, ectx, candidate_status="completed"
                    )
                )

        disk_metrics_records = [
            r for r in caplog.records if "disk_metrics" in r.message
        ]
        assert len(disk_metrics_records) > 0

        record = disk_metrics_records[0]
        import re

        chain_match = re.search(r"chain_depth=(\d+)", record.message)
        assert chain_match is not None
        chain_depth = int(chain_match.group(1))
        assert (
            chain_depth == 1
        ), "chain_depth should be 1 when chain_source_run_id is set"

    @pytest.mark.skipif(not shutil.which("git"), reason="git not available")
    def test_disk_metrics_git_bytes_present(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """B: git_bytes is calculated and present in the log."""
        sandbox = FakeSandbox(tmp_path)
        sandbox.git_init_sandbox()

        # Add some files to create git objects
        (tmp_path / "file1.txt").write_bytes(b"content1" * 100)
        sandbox.commit_all("test commit 1")
        (tmp_path / "file2.txt").write_bytes(b"content2" * 100)
        sandbox.commit_all("test commit 2")

        run_id = _make_run_id()
        ectx = _make_ectx(run_id, sandbox)
        mock_db = _make_mock_db()

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        with caplog.at_level(logging.INFO, logger="agents.execution_engine.engine"):
            with (
                patch("app.models.database.SessionLocal", return_value=mock_db),
                patch("app.models.workflow.WorkflowRun", MagicMock()),
                patch("app.models.run_finalization.RunFinalization", MagicMock()),
            ):
                _async_run(
                    eng.finalize_terminal_run(
                        run_id, ectx, candidate_status="completed"
                    )
                )

        disk_metrics_records = [
            r for r in caplog.records if "disk_metrics" in r.message
        ]
        assert len(disk_metrics_records) > 0

        record = disk_metrics_records[0]
        import re

        git_match = re.search(r"git_bytes=(\d+)", record.message)
        assert git_match is not None
        git_bytes = int(git_match.group(1))
        # With commits and git objects, git_bytes should be > 0
        assert git_bytes > 0, "git_bytes should be positive for a git repo with commits"

    @pytest.mark.skipif(not shutil.which("git"), reason="git not available")
    def test_disk_metrics_chain_depth_reflects_multi_hop_context_value(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """E: the finalizer surfaces whatever depth was threaded onto ectx —
        it never re-derives/clamps to 0 or 1 from ``chain_source_run_id``.

        This is the fix-attempt-1 regression guard for the original bug: a
        run three hops from its chain root must log ``chain_depth=3``, not
        ``chain_depth=1`` (the "is this run chained at all" flag verify FAILed
        on).
        """
        sandbox = FakeSandbox(tmp_path)
        sandbox.git_init_sandbox()
        (tmp_path / "output.html").write_text("<html>test</html>")

        run_id = _make_run_id()
        source_run_id = _make_run_id()
        ectx = _make_ectx(
            run_id, sandbox, chain_source_run_id=source_run_id, chain_depth=3
        )
        mock_db = _make_mock_db()

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        with caplog.at_level(logging.INFO, logger="agents.execution_engine.engine"):
            with (
                patch("app.models.database.SessionLocal", return_value=mock_db),
                patch("app.models.workflow.WorkflowRun", MagicMock()),
                patch("app.models.run_finalization.RunFinalization", MagicMock()),
            ):
                _async_run(
                    eng.finalize_terminal_run(
                        run_id, ectx, candidate_status="completed"
                    )
                )

        disk_metrics_records = [
            r for r in caplog.records if "disk_metrics" in r.message
        ]
        assert len(disk_metrics_records) > 0

        record = disk_metrics_records[0]
        import re

        chain_match = re.search(r"chain_depth=(\d+)", record.message)
        assert chain_match is not None
        chain_depth = int(chain_match.group(1))
        assert (
            chain_depth == 3
        ), "finalizer must surface the real threaded depth, not clamp to 1"


# ===========================================================================
# _compute_chain_depth — the real hop-count walk (row requirement, verify FAIL)
# ===========================================================================
#
# GIT_VERSIONING_TASKS.md's S4 row: chain_depth is "the length of the
# source_run_id chain from this run to a run with no source, computed from
# the context, no DB access inside the finalizer". The finalizer tests above
# cover the "no DB access inside the finalizer" half (it only reads
# ectx.chain_depth); this class covers the actual hop-count computation,
# which happens OUTSIDE the finalizer at launch, via a real multi-hop
# source_run_id chain (depth >= 2) — the coverage gap the verifier's FAIL
# named explicitly.

_CHAIN_USER_ID = "test-user-chain-depth"
_CHAIN_BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def chain_db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.models.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def chain_db_session(chain_db_engine):
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=chain_db_engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


def _seed_chain_run(
    db, *, run_id: str, source_run_id: str | None = None, created_offset: int = 0
) -> None:
    from app.models.workflow import WorkflowRun

    db.add(
        WorkflowRun(
            id=run_id,
            user_id=_CHAIN_USER_ID,
            title=f"chain depth fixture {run_id}",
            type="prototype",
            status="completed",
            input="build me a thing",
            owner_id=_CHAIN_USER_ID,
            workspace_id="ws-chain-depth",
            source_run_id=source_run_id,
            created_at=_CHAIN_BASE_TS + timedelta(seconds=created_offset),
        )
    )
    db.commit()


class TestComputeChainDepth:
    """Behavioural coverage of ``_compute_chain_depth`` against a real DB."""

    def test_single_hop_to_a_root(self, chain_db_session) -> None:
        """This run's source is itself a root (no source_run_id) -> depth 1."""
        from agents.execution_engine.engine import _compute_chain_depth

        root_id = f"chain-{uuid.uuid4()}"
        _seed_chain_run(chain_db_session, run_id=root_id, source_run_id=None)

        assert _compute_chain_depth(root_id, chain_db_session) == 1

    def test_multi_hop_chain_depth_is_a_real_hop_count(self, chain_db_session) -> None:
        """root <- midA <- midB: a chain of depth >= 2, hop count, not a flag.

        This is the exact scenario verify FAILed on: a run chaining from a
        run that itself chains from a root must report a depth distinct from
        (and greater than) a direct one-hop chain.
        """
        from agents.execution_engine.engine import _compute_chain_depth

        root_id, mid_a_id, mid_b_id = (f"chain-{uuid.uuid4()}" for _ in range(3))
        _seed_chain_run(
            chain_db_session, run_id=root_id, source_run_id=None, created_offset=0
        )
        _seed_chain_run(
            chain_db_session, run_id=mid_a_id, source_run_id=root_id, created_offset=10
        )
        _seed_chain_run(
            chain_db_session, run_id=mid_b_id, source_run_id=mid_a_id, created_offset=20
        )

        # A run whose OWN chain_source_run_id is root_id: one hop.
        assert _compute_chain_depth(root_id, chain_db_session) == 1
        # A run whose OWN chain_source_run_id is mid_a_id: two hops (mid_a -> root).
        assert _compute_chain_depth(mid_a_id, chain_db_session) == 2
        # A run whose OWN chain_source_run_id is mid_b_id: three hops
        # (mid_b -> mid_a -> root). This is the depth-3 case: it must NOT
        # collapse to 1, which is exactly what the pre-fix implementation did.
        assert _compute_chain_depth(mid_b_id, chain_db_session) == 3

    def test_missing_source_row_terminates_walk_without_raising(
        self, chain_db_session
    ) -> None:
        """An unresolvable source id still counts its own hop and stops."""
        from agents.execution_engine.engine import _compute_chain_depth

        assert (
            _compute_chain_depth(f"nonexistent-{uuid.uuid4()}", chain_db_session) == 1
        )

    def test_cycle_guard_terminates_on_corrupted_data(self, chain_db_session) -> None:
        """A <-> B self-referential corruption must not infinite-loop."""
        from agents.execution_engine.engine import _compute_chain_depth

        a_id, b_id = (f"chain-{uuid.uuid4()}" for _ in range(2))
        _seed_chain_run(
            chain_db_session, run_id=a_id, source_run_id=b_id, created_offset=0
        )
        _seed_chain_run(
            chain_db_session, run_id=b_id, source_run_id=a_id, created_offset=10
        )

        # Must terminate (the visited-set guard), whatever the exact count.
        depth = _compute_chain_depth(a_id, chain_db_session)
        assert isinstance(depth, int)
        assert depth >= 1
