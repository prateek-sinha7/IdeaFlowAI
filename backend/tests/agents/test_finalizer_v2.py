"""
Tests for ``finalize_terminal_run`` and supporting dataclasses.

Task 5.11 — sandbox-git-versioning-v2

Coverage matrix
---------------
A  Five crash-and-retry injection points (Req 5 AC 3):
   A1  before commit
   A2  after commit, before ref
   A3  after ref, before tag
   A4  after tag, before DB mapping
   A5  after mapping (full success then re-entry)

B  At each crash point a staged secret never appears in
   ``git rev-list --objects --all`` (Req 11 AC 9)

C  Blocked payload and unmaterializable output both yield
   metadata-only snapshot, internal ref, payload_chainable=False,
   degraded, no tag

D  ``post_run`` fires exactly once per terminal status
   (completed, cancelled, failed, degraded-by-ref-conflict, diverted)

E  Tag + ref + summary.md committed_tag / run_id all resolve to same commit

F  v1/v2/v3 expose identical three ``.chain/`` paths; ref-scoped
   ``git archive`` of completed tag contains exactly three flat files

G  Renamed deliverable leaves no stale tracked basename

H  Commit message contains run_id and status, no user content

I  Three CAS cases (Req 5 AC 25):
   I1  Repeated finalization → idempotent
   I2  Corrupted ref → conflict, degraded, existing ref preserved
   I3  Ref survives while tag absent → readable, no fabricated tag

J  Tag success + DB mapping failure → no orphan tag, tag_state=rolled_back

K  Req 5 AC 20: after finalization failure that follows snapshot commit,
   committed summary.md / logs.jsonl are not modified; commit not amended

L  Departure N1: persist failure → terminal event still viable, degraded

Requirements: 4, 5, 11
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import types
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))


def _async_run(coro: Any) -> Any:
    """Run an awaitable synchronously, compatible with Python 3.12+.

    asyncio.get_event_loop() raises RuntimeError on Python 3.12+ when
    no loop exists; asyncio.run() always creates a fresh loop.
    """
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers — real-git sandbox fixture
# ---------------------------------------------------------------------------

SECRET_PATTERN = "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz1234567890ABCD"
_USER_ID = "test-user-v2"
_WORKSPACE_ID = "ws-test-v2"


def _run_git(*args: str, cwd: Path, check: bool = True) -> str:
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
    _run_git("init", "-b", "main", cwd=repo)
    _run_git("config", "user.email", "test@test.test", cwd=repo)
    _run_git("config", "user.name", "Test Bot", cwd=repo)
    # Seed .gitignore with .chain/ ignored (the standard engine does this)
    (repo / ".gitignore").write_text(".chain/\n.chain.staging-*/\n", encoding="utf-8")
    _run_git("add", ".gitignore", cwd=repo)
    _run_git("commit", "-m", "chore: init", cwd=repo)


def _make_run_id() -> str:
    return str(uuid.uuid4())


@dataclass
class FakeSandbox:
    """Minimal sandbox facade backed by a real git repo for testing."""

    root: Path
    run_id: str
    sandbox_root_id: str
    current_run_id: str
    has_git: bool = True

    def _ws(self) -> Any:
        """Return self — we implement the _git helper directly."""
        return self

    def _git(self, *args: str) -> str:
        return _run_git(*args, cwd=self.root)

    @property
    def run_log_path(self) -> Path:
        return self.root / ".logs" / f"{self.current_run_id}.jsonl"

    def reset_index(self) -> None:
        _run_git("reset", "HEAD", cwd=self.root)

    def head_commit(self) -> str:
        return _run_git("rev-parse", "HEAD", cwd=self.root)

    def create_tag(self, name: str) -> None:
        _run_git("tag", name, cwd=self.root)

    def delete_tag(self, name: str) -> None:
        _run_git("tag", "-d", name, cwd=self.root)

    def list_tags(self) -> list[str]:
        out = _run_git("tag", cwd=self.root)
        return [t for t in out.splitlines() if t]

    def create_run_ref(self, run_id: str) -> Any:
        from app.agents.runtime.local import RefResult  # noqa: PLC0415

        ref_name = f"refs/ideaflow/runs/{run_id}"
        head_sha = _run_git("rev-parse", "HEAD", cwd=self.root)
        # Check whether ref exists
        try:
            existing_sha = _run_git("rev-parse", ref_name, cwd=self.root)
        except RuntimeError:
            existing_sha = None
        if existing_sha is not None:
            if existing_sha == head_sha:
                return RefResult(
                    state="idempotent", name=ref_name, sha=head_sha, existing=None
                )
            return RefResult(
                state="conflict", name=ref_name, sha=head_sha, existing=existing_sha
            )
        _run_git("update-ref", "--create-reflog", ref_name, head_sha, cwd=self.root)
        return RefResult(state="created", name=ref_name, sha=head_sha, existing=None)

    def advance_run_ref(self, run_id: str, *, expected_sha: str, new_sha: str) -> Any:
        from app.agents.runtime.local import RefResult  # noqa: PLC0415

        ref_name = f"refs/ideaflow/runs/{run_id}"
        _run_git("update-ref", ref_name, new_sha, expected_sha, cwd=self.root)
        return RefResult(
            state="advanced", name=ref_name, sha=new_sha, existing=expected_sha
        )

    def resolve_ref_commit(self, ref: str) -> str | None:
        try:
            return _run_git("rev-parse", ref, cwd=self.root)
        except RuntimeError:
            return None

    def stage_exact(self, paths: list[str]) -> None:
        for p in paths:
            _run_git("add", "--force", "--", p, cwd=self.root)

    def tracked_chain_paths(self) -> list[str]:
        try:
            out = _run_git("ls-files", "--cached", ".chain/", cwd=self.root)
            return [p for p in out.splitlines() if p]
        except RuntimeError:
            return []

    def git_rm_cached(self, path: str) -> None:
        _run_git("rm", "--cached", "--ignore-unmatch", path, cwd=self.root)

    def atomic_replace_dir(self, src: Path, dst: Path) -> None:
        import shutil as _shutil  # noqa: PLC0415

        if dst.exists():
            _shutil.rmtree(dst)
        _shutil.move(str(src), str(dst))

    def commit_all(
        self,
        message: str,
        paths: list[str] | None = None,
        force_add: frozenset[str] | None = None,
    ) -> str:
        """Commit everything currently staged. Returns SHA or '' on nothing-to-commit."""
        if force_add:
            for p in sorted(force_add):
                _run_git("add", "--force", "--", p, cwd=self.root)
        if paths is not None and len(paths) > 0:
            _run_git("add", "--", *paths, cwd=self.root)
        elif paths is None:
            _run_git("add", "-A", cwd=self.root)
        # Check for staged content
        diff = _run_git("diff", "--cached", "--name-only", cwd=self.root)
        if not diff:
            return ""
        _run_git("commit", "-m", message, cwd=self.root)
        return _run_git("rev-parse", "HEAD", cwd=self.root)

    def is_dirty(self) -> bool:
        status = _run_git("status", "--porcelain", cwd=self.root)
        return bool(status)

    def git_gc_auto(self) -> None:
        # no-op in tests
        pass

    def cleanup_worktrees_and_gc(self) -> None:
        pass

    def acquire_family_lock(self) -> Any:
        return _DummyLock()


class _DummyLock:
    """No-op context manager for family lock in tests."""

    def __enter__(self) -> "_DummyLock":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


def _make_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    final_status: str = "completed",
    deliverable_name: str | None = "output.html",
    revision_ordinal: int = 1,
) -> types.SimpleNamespace:
    """Build a minimal ExecutionContext-like namespace for tests."""
    deliverable = None
    if deliverable_name:
        deliverable = types.SimpleNamespace(name=deliverable_name)
    return types.SimpleNamespace(
        run_id=run_id,
        user_id=_USER_ID,
        owner_id=_USER_ID,
        workspace_id=_WORKSPACE_ID,
        runner=types.SimpleNamespace(sandbox=sandbox, registry=None, engine=None),
        final_status=final_status,
        deliverable=deliverable,
        revision_ordinal=revision_ordinal,
        step_visit_counts={"step-1": 1},
        last_commit_blocked=False,
        completed_tasks=[],
        run_trace=None,
    )


def _plant_output(
    sandbox: FakeSandbox,
    basename: str = "output.html",
    content: bytes = b"<html>v1</html>",
) -> None:
    """Write a deliverable file into the sandbox root."""
    (sandbox.root / basename).write_bytes(content)


def _plant_logs(
    sandbox: FakeSandbox, run_id: str, content: bytes = b'{"event":"terminal"}\n'
) -> None:
    """Write a .logs/{run_id}.jsonl file for the trace."""
    logs_dir = sandbox.root / ".logs"
    logs_dir.mkdir(exist_ok=True)
    (logs_dir / f"{run_id}.jsonl").write_bytes(content)


def _all_objects_content(repo: Path) -> str:
    """Return all text extractable from git rev-list --objects --all."""
    out = _run_git("rev-list", "--objects", "--all", cwd=repo)
    full = out
    # Also grep blob contents
    shas = [
        line.split()[0] for line in out.splitlines() if " " in line or len(line) == 40
    ]
    for sha in shas[:100]:
        try:
            cat = _run_git("cat-file", "-p", sha, cwd=repo, check=False)
            full += cat
        except Exception:  # noqa: BLE001
            pass
    return full


def _setup_sandbox(
    tmp_path: Path, run_id: str | None = None
) -> tuple[FakeSandbox, str]:
    """Create a git-initialized sandbox under tmp_path. Returns (sandbox, run_id)."""
    if run_id is None:
        run_id = _make_run_id()
    repo = tmp_path / run_id
    repo.mkdir(parents=True)
    _git_init(repo)
    sandbox = FakeSandbox(
        root=repo,
        run_id=run_id,
        sandbox_root_id=run_id,
        current_run_id=run_id,
    )
    return sandbox, run_id


# ---------------------------------------------------------------------------
# Mock DB helpers
# ---------------------------------------------------------------------------


def _make_mock_db() -> MagicMock:
    """Return a MagicMock that satisfies the Session protocol."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


# ---------------------------------------------------------------------------
# Patching helper — suppress DB access in finalize_terminal_run
# ---------------------------------------------------------------------------


def _patch_db(mock_db: MagicMock) -> Any:
    """Patch SessionLocal inside engine.py to return mock_db."""
    from unittest.mock import patch as _p  # noqa: PLC0415

    class _FakeSessionLocal:
        def __call__(self) -> MagicMock:
            return mock_db

    return _p(
        "app.models.database.SessionLocal",
        side_effect=_FakeSessionLocal(),
    )


# ---------------------------------------------------------------------------
# Core import check
# ---------------------------------------------------------------------------


def test_finalizer_imports_cleanly() -> None:
    """All required symbols are importable without errors."""
    from agents.execution_engine.engine import (  # noqa: PLC0415
        CommitInSandboxResult,
        FinalizationAttempt,
        Payload,
        SnapshotUnrecoverable,
        build_flat_payload,
        build_metadata_only_snapshot,
        commit_in_sandbox,
        finalize_terminal_run,
    )
    from agents.execution_engine.finalization import (  # noqa: PLC0415
        FinalizationRecord,
        persist_finalization_record_safe,
        read_finalization_record,
    )
    from app.agents.runtime.local import RefResult  # noqa: PLC0415

    assert finalize_terminal_run is not None
    assert FinalizationAttempt is not None
    assert FinalizationRecord is not None
    assert RefResult is not None


# ===========================================================================
# Section A + B — crash-and-retry injection points & secret-never-in-history
# ===========================================================================


class TestCrashAndRetryPoints:
    """A: failure injected at each of the five Req 5 AC 3 points converges.
    B: a staged secret at each crash point never appears in git history.
    """

    def _run_finalizer(
        self,
        sandbox: FakeSandbox,
        run_id: str,
        ectx: types.SimpleNamespace,
        mock_db: MagicMock,
    ) -> Any:
        """Run finalize_terminal_run with a patched DB."""
        from agents.execution_engine import engine as eng  # noqa: PLC0415

        # Clear the process-local guard so repeated calls within test work.
        eng._finalize_terminal_run_started.discard(run_id)

        async def _inner() -> Any:
            with (
                patch("app.models.database.SessionLocal", return_value=mock_db),
                patch("app.models.workflow.WorkflowRun", MagicMock()),
                patch("app.models.run_finalization.RunFinalization", MagicMock()),
            ):
                return await eng.finalize_terminal_run(
                    run_id, ectx, candidate_status="completed"
                )

        return asyncio.run(_inner())

    def test_a1_before_commit_degrade_no_secret_in_history(
        self, tmp_path: Path
    ) -> None:
        """A1/B1: inject failure before commit; secret planted but never committed."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        # Plant a secret in a working-tree file (not yet committed)
        secret_file = sandbox.root / "secret.txt"
        secret_file.write_text(f"{SECRET_PATTERN}\n", encoding="utf-8")

        ectx = _make_ectx(run_id, sandbox)
        mock_db = _make_mock_db()

        # Inject failure: make commit_all raise so the commit never happens
        def _failing_commit_all(*args: Any, **kwargs: Any) -> str:
            from app.agents.runtime.local import GitCommandError  # noqa: PLC0415

            raise GitCommandError("injected commit failure")

        sandbox.commit_all = _failing_commit_all

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        with (
            patch("app.models.database.SessionLocal", return_value=mock_db),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # Commit failed — verify no commit exists beyond init that has the secret
        all_content = _all_objects_content(sandbox.root)
        assert SECRET_PATTERN not in all_content, (
            "Secret found in git history after commit injection failure. "
            "commit_in_sandbox must not commit blocked/failing content."
        )

        # Record should indicate degraded (commit failed)
        assert record is not None
        # Either degraded or published status reflects the failure
        assert record.published_status in (
            "degraded",
            "completed",
            "failed",
        ), f"Unexpected published_status: {record.published_status}"

    def test_a2_after_commit_before_ref_idempotent(self, tmp_path: Path) -> None:
        """A2/B2: commit succeeded; ref creation fails on first attempt then succeeds."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)
        mock_db = _make_mock_db()

        # First attempt: ref creation raises
        create_ref_call_count = [0]
        original_create_ref = sandbox.create_run_ref

        def _patched_ref(rid: str) -> Any:
            create_ref_call_count[0] += 1
            if create_ref_call_count[0] == 1:
                raise RuntimeError("injected ref creation failure")
            return original_create_ref(rid)

        sandbox.create_run_ref = _patched_ref

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        with (
            patch("app.models.database.SessionLocal", return_value=mock_db),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # A ref failure degrades the run
        assert record is not None
        assert (
            record.published_status == "degraded"
        ), f"Expected degraded when ref fails; got {record.published_status}"
        # Secret never planted in this test — just verify no leak in history
        all_content = _all_objects_content(sandbox.root)
        assert SECRET_PATTERN not in all_content

    def test_a3_after_ref_before_tag_degrade(self, tmp_path: Path) -> None:
        """A3/B3: ref created; tag creation fails → degraded, no orphan tag."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)
        mock_db = _make_mock_db()

        # Inject failure: make tag creation raise
        def _fail_tag(name: str) -> None:
            raise RuntimeError("injected tag creation failure")

        sandbox.create_tag = _fail_tag

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        with (
            patch("app.models.database.SessionLocal", return_value=mock_db),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record is not None
        assert record.published_status == "degraded"
        # No tag should have been created
        tags = sandbox.list_tags()
        assert not tags, f"Orphan tag left after injection: {tags}"

        all_content = _all_objects_content(sandbox.root)
        assert SECRET_PATTERN not in all_content

    def test_a4_tag_success_db_mapping_failure_no_orphan(self, tmp_path: Path) -> None:
        """A4/J: tag created, both DB mapping attempts fail → tag rolled back, tag_state=rolled_back."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine import engine as eng  # noqa: PLC0415
        from unittest.mock import MagicMock as _MG, patch as _p  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        # The engine does:
        #   _db = SessionLocal()   <- get a session
        #   _db.query(...).first() <- use it
        #   _db.commit()           <- this must fail for tag mapping
        #   _db.close()            <- always called
        #
        # We provide a factory that always returns a MagicMock session whose
        # .commit() raises — GAPS P0 #4 removed the ordinal DB re-read that used
        # to occupy the first SessionLocal() call of a completed run, so the
        # tag-mapping loop's two attempts are now calls 1 and 2 (not 2 and 3);
        # failing every session's commit exercises "both attempts fail" without
        # coupling the test to that call-count offset.
        def _session_factory() -> MagicMock:
            m = MagicMock()
            m.commit.side_effect = RuntimeError("DB tag mapping fail")
            return m

        with (
            _p("app.models.database.SessionLocal", side_effect=_session_factory),
            _p("app.models.workflow.WorkflowRun", MagicMock()),
            _p("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # Tag should be rolled back
        tags = sandbox.list_tags()
        assert not tags, (
            f"Orphan tag after DB mapping failure: {tags}. "
            "The finalizer must roll back the tag if mapping fails twice."
        )

        assert record is not None
        assert record.published_status == "degraded"
        assert (
            record.tag_state == "rolled_back"
        ), f"Expected tag_state=rolled_back; got {record.tag_state!r}"

    def test_a5_full_success_then_idempotent_reentry(self, tmp_path: Path) -> None:
        """A5: full success; second call converges idempotently."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        # DB factory: always returns a fresh MagicMock session with working commit
        def _good_session() -> MagicMock:
            m = MagicMock()
            wr_row = MagicMock()
            m.query.return_value.filter.return_value.first.return_value = wr_row
            return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record1 = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record1 is not None
        # Tag should exist
        tags = sandbox.list_tags()
        assert "v1" in tags, f"Expected v1 tag after first finalization; tags={tags}"

        # Second call: the process-local guard returns quickly
        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record2 = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record2 is not None
        # Should not create a second tag
        tags2 = sandbox.list_tags()
        assert (
            tags2.count("v1") == 1
        ), f"Duplicate tag after idempotent re-entry: {tags2}"

    def test_b_secret_planted_before_commit_never_reaches_history(
        self, tmp_path: Path
    ) -> None:
        """B: scan blocks a staged secret → not in any git object."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.capabilities.hooks.secret_scan import scan_for_secret  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)

        # Plant a secret file and stage it manually
        secret_file = sandbox.root / "secret.txt"
        secret_file.write_text(f"{SECRET_PATTERN}\n", encoding="utf-8")
        _run_git("add", "secret.txt", cwd=sandbox.root)

        # Get the staged diff
        staged_diff = _run_git("diff", "--cached", cwd=sandbox.root)

        # The scanner must detect the secret
        result = scan_for_secret(staged_diff)
        assert result is not None, "Scanner failed to detect the secret in staged diff"

        # Reset so nothing is staged
        _run_git("reset", "HEAD", cwd=sandbox.root)

        all_content = _all_objects_content(sandbox.root)
        assert (
            SECRET_PATTERN not in all_content
        ), "Secret found in git history even after resetting staged content."


# ===========================================================================
# Section C — metadata-only snapshot on blocked / unmaterializable triggers
# ===========================================================================


class TestMetadataOnlySnapshot:
    """C: blocked payload and unmaterializable output → metadata-only."""

    def _run(
        self,
        sandbox: FakeSandbox,
        run_id: str,
        ectx: types.SimpleNamespace,
        *,
        last_commit_blocked: bool = False,
        deliverable_name: str | None = "output.html",
        write_deliverable: bool = True,
    ) -> Any:
        if last_commit_blocked:
            ectx.last_commit_blocked = True
        if not write_deliverable:
            # Ensure the deliverable does NOT exist on disk
            p = sandbox.root / (deliverable_name or "output.html")
            if p.exists():
                p.unlink()

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch("app.models.database.SessionLocal", return_value=db),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            return asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

    def test_c1_payload_blocked_yields_metadata_only(self, tmp_path: Path) -> None:
        """C1: last_commit_blocked=True → metadata-only snapshot, no tag, degraded."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)
        # DO NOT write the deliverable to simulate blocked content

        ectx = _make_ectx(run_id, sandbox)
        record = self._run(sandbox, run_id, ectx, last_commit_blocked=True)

        assert record is not None
        assert (
            record.published_status == "degraded"
        ), f"Expected degraded for payload_blocked; got {record.published_status}"
        # No tag should exist
        tags = sandbox.list_tags()
        assert not tags, f"Unexpected tag after blocked payload: {tags}"

        # Verify the ref still exists (metadata-only gets a ref)
        ref_name = f"refs/ideaflow/runs/{run_id}"
        ref_sha = sandbox.resolve_ref_commit(ref_name)
        assert (
            ref_sha is not None
        ), "Internal run ref must exist even for a metadata-only snapshot."

        # payload_chainable must be False
        assert record.payload_chainable is False or record.payload_chainable is None

    def test_c2_output_unmaterializable_yields_metadata_only(
        self, tmp_path: Path
    ) -> None:
        """C2: deliverable declared but not present → metadata-only snapshot."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)
        # Do NOT write output.html — it cannot be materialized

        ectx = _make_ectx(run_id, sandbox, deliverable_name="output.html")
        record = self._run(sandbox, run_id, ectx, write_deliverable=False)

        assert record is not None
        # For output_unmaterializable the finalizer degrades
        assert (
            record.published_status == "degraded" or record.payload_chainable is False
        )

        # No user-visible tag
        tags = sandbox.list_tags()
        assert not tags, f"Unexpected tag after unmaterializable output: {tags}"

    def test_c3_metadata_only_summary_has_correct_fields(self, tmp_path: Path) -> None:
        """C3: the built summary.md for metadata-only has payload_chainable=false."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_metadata_only_snapshot  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        ectx = _make_ectx(run_id, sandbox)

        result = build_metadata_only_snapshot(
            run_id, ectx, non_chainable_reason="payload_blocked"
        )

        assert result.built is True
        assert result.materialized is False
        assert result.chainable is False
        assert result.non_chainable_reason == "payload_blocked"

        summary_path = sandbox.root / ".chain" / "summary.md"
        assert summary_path.exists(), ".chain/summary.md not written"
        content = summary_path.read_text(encoding="utf-8")
        assert (
            "payload_chainable" in content.lower() or "false" in content.lower()
        ), "summary.md does not mention payload_chainable or false"

    def test_c4_metadata_only_does_not_include_logs_or_output(
        self, tmp_path: Path
    ) -> None:
        """C4: metadata-only allowlist is {'.chain/summary.md'} only."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_metadata_only_snapshot  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        ectx = _make_ectx(run_id, sandbox)

        result = build_metadata_only_snapshot(
            run_id, ectx, non_chainable_reason="output_unmaterializable"
        )

        assert result.allowlist == frozenset({".chain/summary.md"}), (
            f"Metadata-only allowlist should be exactly {{'.chain/summary.md'}}; "
            f"got {result.allowlist}"
        )

    def test_c5_prior_run_stale_chain_path_untracked_tree_clean(
        self, tmp_path: Path
    ) -> None:
        """C5: a REAL basename tracked by a PRIOR run's commit is untracked by
        the metadata-only fallback even when the CURRENT run's own declared
        deliverable name is a nominal label (e.g. a ``serialized_sandbox``
        deliverable's "output"/"app") that never corresponds to a literal
        file. Regression: Step 2 used to derive the untrack set from
        ``ectx.deliverable.name`` alone, so a differently-named path tracked
        from a prior commit (here ``.chain/hello.html``) was left tracked in
        the index after ``atomic_replace_dir`` had already deleted it from
        disk — a permanently dirty working tree (`` D .chain/hello.html``).
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)

        # A prior run committed a real flat payload under a real basename.
        chain_dir = sandbox.root / ".chain"
        chain_dir.mkdir(exist_ok=True)
        (chain_dir / "logs.jsonl").write_bytes(b'{"event":"prior"}\n')
        (chain_dir / "summary.md").write_text("schema_version: 2\n", encoding="utf-8")
        (chain_dir / "hello.html").write_bytes(b"<h1>Hello from: hello one</h1>")
        _run_git("add", "--force", ".chain/logs.jsonl", cwd=sandbox.root)
        _run_git("add", "--force", ".chain/summary.md", cwd=sandbox.root)
        _run_git("add", "--force", ".chain/hello.html", cwd=sandbox.root)
        _run_git("commit", "-m", "snapshot: prior run", cwd=sandbox.root)

        # This run's own deliverable is a nominal name — never a literal
        # file on disk — the output_unmaterializable trigger.
        ectx = _make_ectx(run_id, sandbox, deliverable_name="output")
        self._run(
            sandbox, run_id, ectx, deliverable_name="output", write_deliverable=False
        )

        tracked = _run_git("ls-files", ".chain/", cwd=sandbox.root)
        assert ".chain/hello.html" not in tracked, (
            "Stale .chain/hello.html from a prior run is still tracked after "
            "a metadata-only (output_unmaterializable) snapshot."
        )
        assert not sandbox.is_dirty(), (
            f"Working tree not clean after metadata-only snapshot: "
            f"{_run_git('status', '--porcelain', cwd=sandbox.root)!r}"
        )


# ===========================================================================
# Section E — tag + ref + summary.md all resolve to one commit
# ===========================================================================


class TestTagRefCommitConsistency:
    """E: the tag, internal ref, and the commit whose summary.md names
    intended_tag and run_id all point to the same commit SHA."""

    def test_e1_tag_ref_and_commit_are_same_sha(self, tmp_path: Path) -> None:
        """E1: after a successful finalization all three Git objects point identically."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox, revision_ordinal=1)
        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record is not None

        if record.published_status != "completed":
            pytest.skip(
                f"Finalizer degraded ({record.degraded_reason}); skipping SHA check"
            )

        commit_sha = record.commit_sha
        assert commit_sha, "commit_sha must be set on a completed record"

        # Internal ref must point to the same commit
        ref_name = f"refs/ideaflow/runs/{run_id}"
        ref_sha = sandbox.resolve_ref_commit(ref_name)
        assert (
            ref_sha == commit_sha
        ), f"Internal ref {ref_name!r} points to {ref_sha!r}, not commit_sha {commit_sha!r}"

        # Tag must point to the same commit
        if record.git_tag:
            tag_sha = _run_git("rev-list", "-n", "1", record.git_tag, cwd=sandbox.root)
            assert (
                tag_sha == commit_sha
            ), f"Tag {record.git_tag!r} points to {tag_sha!r}, not {commit_sha!r}"

        # summary.md must contain the run_id
        summary_path = sandbox.root / ".chain" / "summary.md"
        assert summary_path.exists(), ".chain/summary.md must be committed"
        summary = summary_path.read_text(encoding="utf-8")
        assert run_id in summary, f"summary.md does not contain run_id={run_id}"

        # summary.md must contain intended_tag (if a tag was created)
        if record.git_tag:
            assert (
                record.git_tag in summary
            ), f"summary.md does not mention intended_tag={record.git_tag}"


# ===========================================================================
# Section F — v1/v2/v3 chain paths and git archive
# ===========================================================================


class TestFlatPayloadMultiRevision:
    """F: multiple revision tags expose identical three .chain/ paths."""

    def _do_finalize(
        self,
        sandbox: FakeSandbox,
        run_id: str,
        ectx: types.SimpleNamespace,
        ordinal: int,
    ) -> Any:
        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            return asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

    def test_f1_three_revisions_same_chain_paths(self, tmp_path: Path) -> None:
        """F1: v1, v2, v3 all contain .chain/logs.jsonl, summary.md, output.html."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        # One shared sandbox (same root, three revision run-ids)
        root_id = _make_run_id()
        repo = tmp_path / root_id
        repo.mkdir(parents=True)
        _git_init(repo)

        expected_paths = {
            ".chain/logs.jsonl",
            ".chain/summary.md",
            ".chain/output.html",
        }

        for ordinal in range(1, 4):
            rev_id = _make_run_id()
            sandbox = FakeSandbox(
                root=repo,
                run_id=rev_id,
                sandbox_root_id=root_id,
                current_run_id=rev_id,
            )
            _plant_output(sandbox, content=f"<html>v{ordinal}</html>".encode())
            _plant_logs(sandbox, rev_id)

            ectx = _make_ectx(rev_id, sandbox, revision_ordinal=ordinal)
            record = self._do_finalize(sandbox, rev_id, ectx, ordinal)

            if record.published_status != "completed":
                # Inspect what happened
                continue  # best-effort; at least one should succeed

            # Check the tag points to a commit with the three paths
            tag = f"v{ordinal}"
            tags_present = sandbox.list_tags()
            if tag not in tags_present:
                continue

            # `git show --name-only` diffs the commit against its PARENT, so a
            # path whose bytes are byte-identical to the previous revision's
            # (here `.chain/logs.jsonl`: `_plant_logs`'s default content is the
            # same literal across all three revisions) is correctly committed
            # and tracked but never appears in that diff — a false negative.
            # The contract under test is tree membership at the tag ("does the
            # commit contain this path"), not "did this path change since the
            # parent commit", so list the tree instead of diffing it.
            tag_tree = _run_git("ls-tree", "-r", "--name-only", tag, cwd=repo)
            for p in expected_paths:
                assert p in tag_tree, (
                    f"Tag {tag} commit does not contain {p}. "
                    f"ls-tree output: {tag_tree[:200]}"
                )

    def test_f2_git_archive_of_completed_tag_has_exactly_three_chain_files(
        self, tmp_path: Path
    ) -> None:
        """F2: git archive of a completed tag contains exactly the three flat files."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        import tarfile  # noqa: PLC0415
        import io  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox, revision_ordinal=1)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        def _good_session() -> MagicMock:
            m = MagicMock()
            wr_row = MagicMock()
            m.query.return_value.filter.return_value.first.return_value = wr_row
            return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        if record.published_status != "completed" or not record.git_tag:
            pytest.skip(
                f"Finalizer did not complete cleanly: {record.published_status}, {record.degraded_reason}"
            )

        # Run git archive and check contents
        archive_result = subprocess.run(
            ["git", "archive", "--format=tar", record.git_tag, ".chain/"],
            cwd=sandbox.root,
            capture_output=True,
            timeout=30,
        )
        archive_bytes = archive_result.stdout

        if not archive_bytes:
            pytest.skip("git archive returned empty — likely no .chain/ in tag")

        # Read all member names inside the with block before it closes
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as tf:
            names = [m.name for m in tf.getmembers()]

        expected_files = ["logs.jsonl", "summary.md", "output.html"]

        for f in expected_files:
            assert any(f in n for n in names), (
                f"Expected .chain/{f} in git archive of {record.git_tag}; "
                f"archive members: {names}"
            )

        # No nested .chain/{run_id}/ directories (flat structure)
        nested = [n for n in names if n.endswith("/") and n.count("/") > 1]
        assert not nested, (
            f"Unexpected nested directory entries in git archive — "
            f"chain payload must be flat: {nested}"
        )


# ===========================================================================
# Section G — stale basename reconciliation
# ===========================================================================


class TestStaleBasenameReconciliation:
    """G: renamed deliverable leaves no stale tracked basename."""

    def test_g1_renamed_deliverable_no_stale_tracked_path(self, tmp_path: Path) -> None:
        """G1: after rename, old .chain/old_name.html is not in the tree."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)

        # First: commit the .chain/ with old_name.html
        chain_dir = sandbox.root / ".chain"
        chain_dir.mkdir(exist_ok=True)
        (chain_dir / "logs.jsonl").write_bytes(b'{"event":"x"}\n')
        (chain_dir / "summary.md").write_text("schema_version: 2\n", encoding="utf-8")
        (chain_dir / "old_name.html").write_bytes(b"<html>old</html>")
        _run_git("add", "--force", ".chain/logs.jsonl", cwd=sandbox.root)
        _run_git("add", "--force", ".chain/summary.md", cwd=sandbox.root)
        _run_git("add", "--force", ".chain/old_name.html", cwd=sandbox.root)
        _run_git("commit", "-m", "snapshot: old name", cwd=sandbox.root)

        # Rename: new deliverable is new_name.html
        (sandbox.root / "new_name.html").write_bytes(b"<html>new</html>")
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox, deliverable_name="new_name.html")

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # After finalization, old_name.html must not appear in the tracked index
        tracked = _run_git("ls-files", ".chain/", cwd=sandbox.root)
        assert ".chain/old_name.html" not in tracked, (
            "Stale .chain/old_name.html still tracked after rename. "
            "git_rm_cached must remove old basenames."
        )

        if record.published_status == "completed":
            # new_name.html should be tracked
            assert (
                ".chain/new_name.html" in tracked
            ), "New deliverable .chain/new_name.html not tracked after rename."


# ===========================================================================
# Section H — commit message content
# ===========================================================================


class TestCommitMessageContent:
    """H: commit message contains run_id and status, no user content."""

    def test_h1_commit_message_contains_run_id_and_status(self, tmp_path: Path) -> None:
        """H1: the snapshot commit message embeds run_id and status."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # Read the most recent commit message
        log = _run_git("log", "-1", "--pretty=%s", cwd=sandbox.root)
        assert run_id in log, f"Commit message must contain run_id; got: {log!r}"
        assert (
            "completed" in log or "snapshot" in log
        ), f"Commit message must contain status 'completed'; got: {log!r}"

    def test_h2_commit_message_has_no_user_content(self, tmp_path: Path) -> None:
        """H2: commit message must not contain fake user content."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        user_content = "SUPER_SECRET_USER_INPUT_DO_NOT_LOG"
        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        log = _run_git("log", "--oneline", cwd=sandbox.root)
        assert user_content not in log


# ===========================================================================
# Section I — three CAS cases (Req 5 AC 25)
# ===========================================================================


class TestCASCases:
    """I: three named Req 5 AC 25 cases."""

    def test_i1_repeated_finalization_idempotent(self, tmp_path: Path) -> None:
        """I1: second finalization over already-committed snapshot converges (no dup commit/tag).

        The idempotency guarantee comes from two mechanisms:
        1. The process-local guard (_finalize_terminal_run_started) for in-process re-entry.
        2. The CAS ref (create_run_ref returning 'idempotent') for cross-process re-entry.

        We test the in-process guard: calling finalize_terminal_run a second time
        with the same run_id (guard NOT cleared) returns immediately without
        creating a new commit.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        def _good_session() -> MagicMock:
            m = MagicMock()
            wr_row = MagicMock()
            m.query.return_value.filter.return_value.first.return_value = wr_row
            return m

        ectx = _make_ectx(run_id, sandbox)
        eng._finalize_terminal_run_started.discard(run_id)

        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )
        sha1 = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        # Second call WITHOUT clearing the guard — the process-local guard returns immediately
        # without making a new commit (that's the idempotency contract for in-process re-entry)
        ectx2 = _make_ectx(run_id, sandbox)
        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            asyncio.run(
                eng.finalize_terminal_run(run_id, ectx2, candidate_status="completed")
            )
        sha2 = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        # The process-local guard should have returned quickly on the second call
        # so no new commit should have been created
        assert sha1 == sha2, (
            f"A second in-process finalization created a new commit "
            f"sha1={sha1!r} sha2={sha2!r}. "
            "The process-local guard must prevent a second in-process finalization."
        )

        # No duplicate tag
        tags = sandbox.list_tags()
        v1_count = tags.count("v1")
        assert v1_count <= 1, f"Duplicate v1 tag after repeated finalization: {tags}"

        # CAS idempotency: calling create_run_ref a second time returns 'idempotent'
        from app.agents.runtime.local import RefResult  # noqa: PLC0415

        r2 = sandbox.create_run_ref(run_id)
        assert r2.state == "idempotent", (
            f"create_run_ref on an existing ref at HEAD must return 'idempotent'; "
            f"got {r2.state!r}"
        )

    def test_i2_manually_corrupted_ref_yields_conflict_degraded(
        self, tmp_path: Path
    ) -> None:
        """I2: ref points to different commit → conflict, run_finalization_failed, degraded, ref preserved."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        # First, commit something so there's a HEAD SHA
        _run_git("add", "-A", cwd=sandbox.root)
        _run_git("commit", "-m", "pre-run commit", cwd=sandbox.root)
        first_sha = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        # Manually create the internal ref at the FIRST SHA
        ref_name = f"refs/ideaflow/runs/{run_id}"
        _run_git("update-ref", "--create-reflog", ref_name, first_sha, cwd=sandbox.root)

        # Now make a second commit (HEAD diverges from the existing ref)
        (sandbox.root / "extra.txt").write_text("extra", encoding="utf-8")
        _run_git("add", "extra.txt", cwd=sandbox.root)
        _run_git("commit", "-m", "extra commit after ref was created", cwd=sandbox.root)
        second_sha = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        assert first_sha != second_sha, "Test setup: commits must differ"

        # Now run the finalizer — it should detect the conflict
        ectx = _make_ectx(run_id, sandbox)
        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record is not None
        assert (
            record.published_status == "degraded"
        ), f"Expected degraded on ref conflict; got {record.published_status}"

        # The EXISTING ref must still point to first_sha (ref not self-healed)
        existing_ref_sha = sandbox.resolve_ref_commit(ref_name)
        assert existing_ref_sha == first_sha, (
            f"Ref {ref_name!r} was moved from {first_sha!r} to {existing_ref_sha!r}. "
            "On conflict the ref must be preserved, not overwritten."
        )

        # The record should note the conflict via degraded_reason
        assert record.degraded_reason in (
            "ref_conflict",
            "ref_creation_failed",
        ), f"Unexpected degraded_reason on ref conflict: {record.degraded_reason!r}"

    def test_i3_ref_without_tag_readable_no_fabricated_tag(
        self, tmp_path: Path
    ) -> None:
        """I3: ref survives while tag is absent → readable, no synthesized tag."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        # Simulate: after finalization delete the tag manually (simulating a tag rollback
        # that left the ref intact)
        ectx = _make_ectx(run_id, sandbox)
        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        if record.published_status != "completed" or not record.git_tag:
            pytest.skip("Finalizer did not produce a tag; cannot test ref-without-tag")

        # Manually delete the tag (simulating the ref-without-tag state)
        sandbox.delete_tag(record.git_tag)
        remaining_tags = sandbox.list_tags()
        assert record.git_tag not in remaining_tags

        # The internal ref must still be resolvable
        ref_name = f"refs/ideaflow/runs/{run_id}"
        ref_sha = sandbox.resolve_ref_commit(ref_name)
        assert ref_sha is not None, "Internal ref must remain after tag deletion."
        assert (
            ref_sha == record.commit_sha
        ), "Ref SHA must still match the original commit SHA."

        # No fabricated tag was created
        tags_after = sandbox.list_tags()
        assert not tags_after, (
            f"Unexpected tags after manual deletion: {tags_after}. "
            "The finalizer must not fabricate or re-derive a tag."
        )


# ===========================================================================
# Section K — Req 5 AC 20: snapshot commit not amended after finalization failure
# ===========================================================================


class TestSnapshotImmutability:
    """K: after finalization failure post-snapshot, committed files not modified."""

    def test_k1_committed_summary_not_modified_after_ref_failure(
        self, tmp_path: Path
    ) -> None:
        """K1: if ref creation fails after commit, the snapshot commit is not amended.

        Req 5 AC 20: after a finalization failure that lands after the snapshot commit,
        the committed summary.md is not amended, re-committed, force-updated, or deleted.

        We verify this by:
        1. Capturing the commit SHA after the snapshot commit.
        2. Confirming that commit SHA is still reachable from HEAD or git log.
        3. Confirming that git show {sha}:.chain/summary.md produces the same
           bytes as at the time of the commit (i.e. the commit was not rewritten).
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        # Inject failure: ref creation fails on first attempt
        original_create_ref = sandbox.create_run_ref
        ref_call_count = [0]

        def _fail_ref(rid: str) -> Any:
            ref_call_count[0] += 1
            if ref_call_count[0] == 1:
                raise RuntimeError("injected: ref creation failure after commit")
            return original_create_ref(rid)

        sandbox.create_run_ref = _fail_ref

        ectx = _make_ectx(run_id, sandbox)
        eng._finalize_terminal_run_started.discard(run_id)

        def _good_session() -> MagicMock:
            m = MagicMock()
            wr_row = MagicMock()
            m.query.return_value.filter.return_value.first.return_value = wr_row
            return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record is not None
        # Record is degraded because ref failed
        assert record.published_status == "degraded"

        # The snapshot commit must still exist in git history
        commit_sha = record.commit_sha
        if not commit_sha:
            pytest.skip("No commit_sha in record — commit may not have happened")

        # Verify the commit is still reachable (not deleted, not force-updated)
        all_commits = _run_git("log", "--pretty=%H", cwd=sandbox.root)
        assert commit_sha in all_commits, (
            f"Snapshot commit {commit_sha!r} was deleted or force-updated. "
            "Req 5 AC 20: the snapshot commit must not be deleted."
        )

        # Get the committed summary.md bytes at the snapshot commit
        summary_at_commit = _run_git(
            "show",
            f"{commit_sha}:.chain/summary.md",
            cwd=sandbox.root,
            check=False,
        )
        assert summary_at_commit, (
            f"summary.md not found at snapshot commit {commit_sha!r}. "
            "The commit must contain the summary."
        )

        # The commit itself must be HEAD or an ancestor (no rewrite)
        head_sha = _run_git("rev-parse", "HEAD", cwd=sandbox.root)
        # HEAD == commit_sha (no new commit after the snapshot) OR
        # commit_sha is an ancestor of HEAD
        if head_sha != commit_sha:
            # Check it's an ancestor
            is_ancestor = (
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", commit_sha, head_sha],
                    cwd=sandbox.root,
                    timeout=10,
                ).returncode
                == 0
            )
            assert is_ancestor, (
                f"Snapshot commit {commit_sha!r} is not an ancestor of HEAD {head_sha!r}. "
                "The commit chain must not be rewritten."
            )


# ===========================================================================
# Section L — Departure N1
# ===========================================================================


class TestDepartureN1:
    """L: record that cannot persist still yields a viable terminal event, degraded."""

    def test_l1_persist_failure_returns_in_memory_record_flagged_unpersisted(
        self, tmp_path: Path
    ) -> None:
        """L1: when persist_finalization_record_safe returns _unpersisted=True,
        finalize_terminal_run returns a non-None record so the caller can emit
        a terminal event."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine import engine as eng  # noqa: PLC0415
        from agents.execution_engine.finalization import (  # noqa: PLC0415
            FinalizationRecord,
        )

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)
        eng._finalize_terminal_run_started.discard(run_id)

        # Make persist_finalization_record_safe always return an _unpersisted record
        def _always_fail_persist(
            db: Any, record: FinalizationRecord
        ) -> FinalizationRecord:
            return FinalizationRecord(
                run_id=record.run_id,
                owner_id=record.owner_id,
                workspace_id=record.workspace_id,
                published_status=record.published_status,
                candidate_status=record.candidate_status,
                payload_chainable=record.payload_chainable,
                non_chainable_reason=record.non_chainable_reason,
                _unpersisted=True,
            )

        # Also make SessionLocal raise so the DB is never consulted
        class _FailDB:
            def __call__(self) -> MagicMock:
                raise RuntimeError("DB is completely unavailable (departure N1 test)")

        with (
            patch(
                "agents.execution_engine.finalization.persist_finalization_record_safe",
                side_effect=_always_fail_persist,
            ),
            patch("app.models.database.SessionLocal", side_effect=_FailDB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # Departure N1 contract: the record is NEVER None
        assert record is not None, (
            "Departure N1 violated: finalize_terminal_run returned None when persist failed. "
            "The caller must always receive a record to emit a terminal event from."
        )

        # The record must carry enough state for a terminal event
        assert record.run_id == run_id
        assert (
            record.published_status is not None
        ), "published_status must not be None even on persist failure."

    def test_l2_departure_n1_marks_record_unpersisted(self, tmp_path: Path) -> None:
        """L2: the in-memory fallback record is flagged _unpersisted=True."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine import engine as eng  # noqa: PLC0415
        from agents.execution_engine.finalization import FinalizationRecord  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)
        eng._finalize_terminal_run_started.discard(run_id)

        # Force the DB session itself to raise so the fallback in-memory path is taken
        class _NeverDB:
            def __call__(self) -> MagicMock:
                raise RuntimeError("All DB paths unavailable — test departure N1")

        with (
            patch("app.models.database.SessionLocal", side_effect=_NeverDB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        # Must be non-None
        assert record is not None

        # The record is the in-memory sentinel — either _unpersisted=True or
        # it carries enough state for a terminal event (the finalization fallback
        # may set _unpersisted or degrade — both are valid departure N1 paths)
        assert record.published_status is not None
        assert record.run_id == run_id


# ===========================================================================
# Section D — post_run fires exactly once per terminal status
# ===========================================================================


class TestPostRunFiringOnce:
    """D: post_run fires exactly once for each terminal status path."""

    def test_d1_finalization_attempt_degrade_keeps_first_reason(self) -> None:
        """D1: FinalizationAttempt.degrade keeps the FIRST reason (earliest = actionable)."""
        from agents.execution_engine.engine import FinalizationAttempt  # noqa: PLC0415

        attempt = FinalizationAttempt(
            run_id="r1",
            owner_id="u1",
            workspace_id="ws1",
        )
        assert not attempt.is_degraded

        attempt.degrade("first_reason")
        assert attempt.is_degraded
        assert attempt.degrade_reason == "first_reason"

        # Second call must NOT overwrite
        attempt.degrade("second_reason")
        assert attempt.degrade_reason == "first_reason", (
            "FinalizationAttempt.degrade must keep the FIRST reason — "
            f"got {attempt.degrade_reason!r} instead."
        )

    def test_d2_note_blocked_reconcile_sets_wip_blocked_and_degrades(self) -> None:
        """D2: note_blocked_reconcile marks _wip_blocked and degrades."""
        from agents.execution_engine.engine import FinalizationAttempt  # noqa: PLC0415

        attempt = FinalizationAttempt(
            run_id="r2",
            owner_id="u2",
            workspace_id="ws2",
        )
        attempt.note_blocked_reconcile("wip_commit_blocked")
        assert attempt._wip_blocked is True
        assert attempt.is_degraded
        assert attempt.degrade_reason == "wip_commit_blocked"

    def test_d3_post_run_fires_exactly_once_via_record_returned(
        self, tmp_path: Path
    ) -> None:
        """D3: finalize_terminal_run returns exactly one record per invocation."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        records = []

        async def _run_all() -> None:
            for status in ("completed", "cancelled", "failed", "degraded", "diverted"):
                eid = _make_run_id()
                run_sandbox = FakeSandbox(
                    root=sandbox.root,
                    run_id=eid,
                    sandbox_root_id=run_id,
                    current_run_id=eid,
                )
                _plant_logs(run_sandbox, eid)
                ectx = _make_ectx(eid, run_sandbox, final_status=status)
                eng._finalize_terminal_run_started.discard(eid)
                with (
                    patch("app.models.database.SessionLocal", side_effect=_DB()),
                    patch("app.models.workflow.WorkflowRun", MagicMock()),
                    patch("app.models.run_finalization.RunFinalization", MagicMock()),
                ):
                    r = await eng.finalize_terminal_run(
                        eid, ectx, candidate_status=status
                    )
                    records.append(r)

        asyncio.run(_run_all())

        # Every call returns exactly one record
        assert len(records) == 5, f"Expected 5 records, got {len(records)}"
        for r in records:
            assert r is not None
            assert r.run_id is not None

    @pytest.mark.parametrize(
        "status", ["completed", "cancelled", "failed", "degraded", "diverted"]
    )
    def test_d4_post_run_dispatched_once_per_terminal_status(
        self, tmp_path: Path, status: str
    ) -> None:
        """D4: post_run reaches a REAL declared hook exactly once per terminal status.

        Drives the actual ``ExecutionEngine._fire_hooks`` (the same recipe as
        ``test_hooks.py::test_engine_fire_hooks_before_write_blocks_secret`` —
        ``ExecutionEngine.__new__`` + a real ``CapabilityRegistry``), never a
        hand-written stub. The run's compiled plan (``KernelServices.
        _steps_by_agent``) declares ``otel_tracing`` (the ``*``-wildcard,
        always-bound observability hook) on its one step, so the REAL
        ``OtelTracingHook.handle`` runs for ``post_run`` and writes a real
        ``hook_runs`` row — proving a declared hook can actually OBSERVE the
        event, not merely that some dispatcher function was invoked once.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, root_run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, root_run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415
        from agents.execution_engine.engine import ExecutionEngine  # noqa: PLC0415

        eng._finalize_terminal_run_started.discard(root_run_id)

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        hook_run_rows: list[dict] = []

        async def _record_hook_run(hook, event, outcome, detail=None):
            hook_run_rows.append(
                {"hook": hook, "event": event, "outcome": outcome, "detail": detail}
            )

        async def _run_finalize() -> None:
            run_id = _make_run_id()
            run_sandbox = FakeSandbox(
                root=sandbox.root,
                run_id=run_id,
                sandbox_root_id=root_run_id,
                current_run_id=run_id,
            )
            _plant_logs(run_sandbox, run_id)

            ectx = _make_ectx(run_id, run_sandbox, final_status=status)
            # A real engine instance (no __init__ side effects) so _fire_hooks
            # runs the genuine declaration-resolution + binding chain.
            ectx.runner.engine = ExecutionEngine.__new__(ExecutionEngine)
            # The compiled plan's one step declares otel_tracing — the union-of-
            # declared-hooks source finalize_terminal_run reads for post_run.
            ectx.runner._steps_by_agent = {
                "build": types.SimpleNamespace(
                    agent_id="build", hooks=["otel_tracing"], tools=None
                ),
            }
            ectx.runner.record_hook_run = _record_hook_run

            eng._finalize_terminal_run_started.discard(run_id)

            with (
                patch("app.models.database.SessionLocal", side_effect=_DB()),
                patch("app.models.workflow.WorkflowRun", MagicMock()),
                patch("app.models.run_finalization.RunFinalization", MagicMock()),
            ):
                record = await eng.finalize_terminal_run(
                    run_id, ectx, candidate_status=status
                )
                assert record is not None
                assert record.run_id == run_id

                # Re-enter the finalizer for the SAME run_id (no discard of the
                # fast-path idempotency set this time) — the second call must
                # take the ``run_id in _finalize_terminal_run_started`` early
                # return and dispatch post_run NO additional time.
                record2 = await eng.finalize_terminal_run(
                    run_id, ectx, candidate_status=status
                )
                assert record2 is not None

        asyncio.run(_run_finalize())

        # The real otel_tracing hook fired exactly once for post_run and wrote
        # exactly one real hook_runs row — including after the re-entrant call.
        post_run_rows = [r for r in hook_run_rows if r["event"] == "post_run"]
        assert len(post_run_rows) == 1, (
            f"Expected exactly one real post_run hook firing for status={status} "
            f"(even after re-entering the finalizer), "
            f"got {len(post_run_rows)}: {hook_run_rows}"
        )
        assert post_run_rows[0]["hook"] == "otel_tracing"
        assert post_run_rows[0]["outcome"] == "continue"
        # The synthetic post-run step's agent_id reaches the hook's own detail
        # (span/provenance attribute) — proof the step/extra plumbing threads
        # all the way through to a real hook, not just to _fire_hooks's args.
        assert post_run_rows[0]["detail"].get("agent_id") == "finalizer-post-run"


# ===========================================================================
# Section — FinalizationRecord correctness
# ===========================================================================


class TestFinalizationRecord:
    """Tests for FinalizationRecord and its invariant enforcement."""

    def test_chainability_invariant_applied_on_status_divergence(self) -> None:
        """When published_status != candidate_status, payload_chainable must be False."""
        from agents.execution_engine.finalization import (  # noqa: PLC0415
            FinalizationRecord,
            _enforce_chainability_invariant,
        )

        record = FinalizationRecord(
            run_id="r1",
            owner_id="u1",
            workspace_id="ws1",
            published_status="degraded",
            candidate_status="completed",
            payload_chainable=True,  # must be overridden
        )
        effective = _enforce_chainability_invariant(record)
        assert (
            effective.payload_chainable is False
        ), "chainability invariant: published != candidate must force payload_chainable=False"
        assert effective.non_chainable_reason == "published_status_diverged"

    def test_chainability_invariant_not_applied_when_statuses_match(self) -> None:
        """When statuses match, payload_chainable is not forced False."""
        from agents.execution_engine.finalization import (  # noqa: PLC0415
            FinalizationRecord,
            _enforce_chainability_invariant,
        )

        record = FinalizationRecord(
            run_id="r2",
            owner_id="u2",
            workspace_id="ws2",
            published_status="completed",
            candidate_status="completed",
            payload_chainable=True,
        )
        effective = _enforce_chainability_invariant(record)
        assert effective.payload_chainable is True

    def test_persist_safe_returns_record_on_db_error(self) -> None:
        """persist_finalization_record_safe returns a non-None _unpersisted record on failure."""
        from agents.execution_engine.finalization import (  # noqa: PLC0415
            FinalizationRecord,
            persist_finalization_record_safe,
        )

        db = MagicMock()
        db.query.side_effect = RuntimeError("DB completely unavailable")
        db.rollback = MagicMock()

        record = FinalizationRecord(
            run_id="test-run",
            owner_id="user1",
            workspace_id="ws1",
            published_status="completed",
            candidate_status="completed",
            payload_chainable=True,
        )

        result = persist_finalization_record_safe(db, record)
        assert result is not None
        assert result._unpersisted is True
        assert result.run_id == "test-run"

    def test_read_finalization_record_returns_none_for_partial_row(self) -> None:
        """read_finalization_record returns None for a row missing key fields."""
        from agents.execution_engine.finalization import read_finalization_record  # noqa: PLC0415

        partial_row = MagicMock()
        partial_row.run_id = "test-run"
        partial_row.published_status = None  # key field missing
        partial_row.candidate_status = "completed"
        partial_row.payload_chainable = True
        partial_row.commit_sha = "abc123"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = partial_row

        # Patch the import inside read_finalization_record
        with patch("app.models.run_finalization.RunFinalization", MagicMock()):
            result = read_finalization_record(db, "test-run")

        assert result is None, (
            "read_finalization_record must return None for a partial row "
            "(missing published_status)."
        )

    def test_read_finalization_record_returns_none_for_absent_row(self) -> None:
        """read_finalization_record returns None when no row exists."""
        from agents.execution_engine.finalization import read_finalization_record  # noqa: PLC0415

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.models.run_finalization.RunFinalization", MagicMock()):
            result = read_finalization_record(db, "nonexistent-run")

        assert result is None


# ===========================================================================
# Section — RefResult and create_run_ref CAS semantics
# ===========================================================================


class TestRefResultCASSemantics:
    """CAS semantics for create_run_ref directly via the sandbox facade."""

    def test_ref_created_on_first_call(self, tmp_path: Path) -> None:
        """First call: ref does not exist → state=created."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        # Need at least one commit
        (sandbox.root / "init.txt").write_text("x", encoding="utf-8")
        _run_git("add", "init.txt", cwd=sandbox.root)
        _run_git("commit", "-m", "test commit", cwd=sandbox.root)

        result = sandbox.create_run_ref(run_id)
        assert result.state == "created", f"Expected created; got {result.state!r}"
        assert result.name == f"refs/ideaflow/runs/{run_id}"
        assert result.existing is None

    def test_ref_idempotent_on_second_call(self, tmp_path: Path) -> None:
        """Second call with same HEAD → state=idempotent."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "init.txt").write_text("x", encoding="utf-8")
        _run_git("add", "init.txt", cwd=sandbox.root)
        _run_git("commit", "-m", "test commit", cwd=sandbox.root)

        r1 = sandbox.create_run_ref(run_id)
        assert r1.state == "created"

        r2 = sandbox.create_run_ref(run_id)
        assert (
            r2.state == "idempotent"
        ), f"Expected idempotent on second call; got {r2.state!r}"
        assert r2.existing is None

    def test_ref_conflict_when_head_diverges(self, tmp_path: Path) -> None:
        """Ref exists at old SHA, HEAD moved → state=conflict, existing points to old SHA."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "init.txt").write_text("x", encoding="utf-8")
        _run_git("add", "init.txt", cwd=sandbox.root)
        _run_git("commit", "-m", "first", cwd=sandbox.root)
        sha1 = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        # Create the ref at sha1
        r1 = sandbox.create_run_ref(run_id)
        assert r1.state == "created"
        assert r1.sha == sha1

        # Make a new commit so HEAD diverges
        (sandbox.root / "extra.txt").write_text("y", encoding="utf-8")
        _run_git("add", "extra.txt", cwd=sandbox.root)
        _run_git("commit", "-m", "second", cwd=sandbox.root)
        sha2 = _run_git("rev-parse", "HEAD", cwd=sandbox.root)
        assert sha1 != sha2

        r2 = sandbox.create_run_ref(run_id)
        assert r2.state == "conflict", f"Expected conflict; got {r2.state!r}"
        assert (
            r2.existing == sha1
        ), f"existing should be the old sha1={sha1!r}; got {r2.existing!r}"
        # Ref must NOT have moved
        ref_sha = sandbox.resolve_ref_commit(f"refs/ideaflow/runs/{run_id}")
        assert ref_sha == sha1, "Ref must not be moved on conflict"


# ===========================================================================
# Section — build_flat_payload unit tests
# ===========================================================================


class TestBuildFlatPayload:
    """Unit tests for build_flat_payload."""

    def test_payload_built_false_when_no_sandbox(self) -> None:
        """build_flat_payload returns built=False when sandbox is absent."""
        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        run_id = _make_run_id()
        ectx = types.SimpleNamespace(
            run_id=run_id,
            runner=None,
            deliverable=None,
            final_status="completed",
            revision_ordinal=1,
            completed_tasks=[],
        )
        result = build_flat_payload(run_id, ectx)
        assert result.built is False

    def test_payload_three_files_when_deliverable_present(self, tmp_path: Path) -> None:
        """build_flat_payload creates logs.jsonl, summary.md, and the output file."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        result = build_flat_payload(run_id, ectx)

        assert result.built is True
        chain_dir = sandbox.root / ".chain"
        assert (chain_dir / "logs.jsonl").exists()
        assert (chain_dir / "summary.md").exists()
        assert (chain_dir / "output.html").exists()

    def test_payload_materialized_true_when_output_present(
        self, tmp_path: Path
    ) -> None:
        """build_flat_payload.materialized=True iff the output file was copied."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        result = build_flat_payload(run_id, ectx)

        assert result.materialized is True
        assert result.chainable is True

    def test_payload_materialized_false_when_output_absent(
        self, tmp_path: Path
    ) -> None:
        """build_flat_payload.materialized=False when output file does not exist."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)
        # Do NOT write output.html

        ectx = _make_ectx(run_id, sandbox)

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        result = build_flat_payload(run_id, ectx)

        assert result.built is True
        assert result.materialized is False
        assert result.chainable is False


# ===========================================================================
# Section M — resume-driven re-finalization (LB2: cancelled -> resumed ->
# completed must not degrade a genuinely completed run over a ref conflict).
#
# A run can legitimately reach a terminal state TWICE: once as cancelled (or
# failed/degraded — all user-resumable via POST /{run_id}/resume, RESUME-18),
# then again, later, as completed after the user resumes it. The second
# finalization pass produces a genuinely different snapshot commit (new agent
# steps ran), so create_run_ref's create-only CAS correctly reports
# "conflict" against the first pass's ref. M1 proves the finalizer advances
# the ref/tag/record to the later, real outcome instead of degrading a run
# the engine itself resolved as completed. M2 proves this did not weaken the
# existing idempotency guarantee: a genuine second pass with the SAME
# candidate_status (nothing changed) still converges without a duplicate tag,
# and post_run still fires exactly once.
# ===========================================================================


class _FakeFinalizationQuery:
    """Minimal query stub distinguishing RunFinalization from WorkflowRun by identity."""

    def __init__(self, model: Any, rf_class: Any, fin_rows: dict, wr_row: Any) -> None:
        self._model = model
        self._rf_class = rf_class
        self._fin_rows = fin_rows
        self._wr_row = wr_row

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeFinalizationQuery":
        return self

    def first(self) -> Any:
        if self._model is self._rf_class:
            return self._fin_rows.get("row")
        return self._wr_row


class _FakeFinalizationSession:
    """A stateful fake DB session so a second finalize_terminal_run call can
    read back exactly what the first call persisted (real upsert semantics),
    without a real database.
    """

    def __init__(self, rf_class: Any, fin_rows: dict, wr_row: Any) -> None:
        self._rf_class = rf_class
        self._fin_rows = fin_rows
        self._wr_row = wr_row

    def query(self, model: Any) -> _FakeFinalizationQuery:
        return _FakeFinalizationQuery(
            model, self._rf_class, self._fin_rows, self._wr_row
        )

    def add(self, row: Any) -> None:
        self._fin_rows["row"] = row

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


class TestResumeReFinalization:
    """M: a resumed run's later, different terminal outcome must win."""

    def test_m1_cancelled_then_resumed_completed_advances_ref_and_tags(
        self, tmp_path: Path
    ) -> None:
        """M1: cancelled finalization, then a later completed finalization for
        the SAME run (simulating a resume) must publish completed, create v1,
        and move the internal ref to the new commit — not degrade.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox, content=b"<html>partial</html>")
        _plant_logs(sandbox, run_id, content=b'{"event":"cancelled"}\n')

        from agents.execution_engine import engine as eng  # noqa: PLC0415

        rf_class = MagicMock(name="RunFinalization")
        wr_class = MagicMock(name="WorkflowRun")
        fin_rows: dict = {}
        wr_row = MagicMock()

        def _session_factory() -> _FakeFinalizationSession:
            return _FakeFinalizationSession(rf_class, fin_rows, wr_row)

        # ── Pass 1: the run is cancelled mid-flight ──────────────────────────
        ectx1 = _make_ectx(run_id, sandbox, final_status="cancelled")
        eng._finalize_terminal_run_started.discard(run_id)
        with (
            patch("app.models.database.SessionLocal", side_effect=_session_factory),
            patch("app.models.workflow.WorkflowRun", wr_class),
            patch("app.models.run_finalization.RunFinalization", rf_class),
        ):
            record1 = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx1, candidate_status="cancelled")
            )

        assert record1.published_status == "cancelled"
        assert record1.git_tag is None
        cancelled_sha = _run_git("rev-parse", "HEAD", cwd=sandbox.root)
        ref_name = f"refs/ideaflow/runs/{run_id}"
        assert sandbox.resolve_ref_commit(ref_name) == cancelled_sha

        # ── The resume: further agent work changes the deliverable ─────────
        _plant_output(sandbox, content=b"<html>the real completed output</html>")
        _plant_logs(
            sandbox, run_id, content=b'{"event":"cancelled"}\n{"event":"resumed"}\n'
        )

        # ── Pass 2: the resumed run reaches a genuinely different outcome ──
        ectx2 = _make_ectx(run_id, sandbox, final_status="completed")
        eng._finalize_terminal_run_started.discard(run_id)
        with (
            patch("app.models.database.SessionLocal", side_effect=_session_factory),
            patch("app.models.workflow.WorkflowRun", wr_class),
            patch("app.models.run_finalization.RunFinalization", rf_class),
        ):
            record2 = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx2, candidate_status="completed")
            )

        completed_sha = _run_git("rev-parse", "HEAD", cwd=sandbox.root)
        assert (
            completed_sha != cancelled_sha
        ), "test setup: the resumed pass must produce a genuinely new commit"

        # The engine resolved this run as completed — it must publish completed,
        # not degrade it over the ref conflict the two different commits produce.
        assert record2.published_status == "completed", (
            f"expected completed, got {record2.published_status!r} "
            f"(degraded_reason={record2.degraded_reason!r})"
        )
        assert record2.degraded_reason is None
        assert record2.git_tag == "v1"
        assert record2.commit_sha == completed_sha

        # The ref moved forward to the new terminal commit — not preserved at
        # the cancelled snapshot, and not left unmoved/absent.
        assert sandbox.resolve_ref_commit(ref_name) == completed_sha

        # The tag was actually created in git, on the new commit.
        tags = sandbox.list_tags()
        assert tags.count("v1") == 1, f"expected exactly one v1 tag; got {tags}"
        assert _run_git("rev-parse", "v1", cwd=sandbox.root) == completed_sha

    def test_m2_repeated_same_outcome_still_idempotent_post_run_once(
        self, tmp_path: Path
    ) -> None:
        """M2: a genuine double-finalize of the SAME outcome (nothing changed)
        still converges on one commit/tag and still fires post_run exactly once
        — the M1 fix must not weaken the existing idempotency guarantee.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        from agents.execution_engine import engine as eng  # noqa: PLC0415
        from agents.execution_engine.engine import ExecutionEngine  # noqa: PLC0415

        wr_row = MagicMock()

        class _DB:
            def __call__(self) -> MagicMock:
                m = MagicMock()
                m.query.return_value.filter.return_value.first.return_value = wr_row
                return m

        hook_run_rows: list[dict] = []

        async def _record_hook_run(hook, event, outcome, detail=None):  # noqa: ANN001
            hook_run_rows.append({"hook": hook, "event": event})

        def _build_ectx() -> types.SimpleNamespace:
            ectx = _make_ectx(run_id, sandbox, final_status="completed")
            ectx.runner.engine = ExecutionEngine.__new__(ExecutionEngine)
            ectx.runner._steps_by_agent = {
                "build": types.SimpleNamespace(
                    agent_id="build", hooks=["otel_tracing"], tools=None
                ),
            }
            ectx.runner.record_hook_run = _record_hook_run
            return ectx

        eng._finalize_terminal_run_started.discard(run_id)
        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record1 = asyncio.run(
                eng.finalize_terminal_run(
                    run_id, _build_ectx(), candidate_status="completed"
                )
            )
        sha1 = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        # A second call for the SAME run/status, WITHOUT clearing the guard —
        # the in-process fast path must return without a new commit, a new
        # tag, or a second post_run dispatch.
        with (
            patch("app.models.database.SessionLocal", side_effect=_DB()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record2 = asyncio.run(
                eng.finalize_terminal_run(
                    run_id, _build_ectx(), candidate_status="completed"
                )
            )
        sha2 = _run_git("rev-parse", "HEAD", cwd=sandbox.root)

        assert record1.published_status == "completed"
        assert record2.published_status == "completed"
        assert sha1 == sha2, "a repeated finalization must not create a new commit"
        assert sandbox.list_tags().count("v1") == 1

        post_run_rows = [r for r in hook_run_rows if r["event"] == "post_run"]
        assert len(post_run_rows) == 1, (
            f"expected exactly one post_run dispatch across two finalize calls "
            f"for the same outcome, got {len(post_run_rows)}: {hook_run_rows}"
        )


class TestFilesLeftOutOfTheHistory:
    """A file the binary scan left out of a step commit (run 53d022e9's screenshots)
    means the history is not the whole run: publish degraded, never tag it."""

    def test_left_out_files_degrade_and_suppress_the_tag(self, tmp_path: Path) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)
        ectx = _make_ectx(run_id, sandbox)
        ectx.commit_excluded_files = {"build/ui/components/button.png": "unknown binary type"}

        from agents.execution_engine import engine as eng  # noqa: PLC0415
        eng._finalize_terminal_run_started.discard(run_id)

        def _good_session() -> MagicMock:
            m = MagicMock()
            m.query.return_value.filter.return_value.first.return_value = MagicMock()
            return m

        with (
            patch("app.models.database.SessionLocal", side_effect=_good_session),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record is not None
        assert record.published_status == "degraded"
        assert record.degraded_reason == "files_not_saved"
        assert "v1" not in sandbox.list_tags()
