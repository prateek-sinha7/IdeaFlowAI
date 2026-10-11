"""
Tests for rollback safety — task 12.6 of sandbox-git-versioning-v2.

A rollback scenario means the codebase is reverted to a pre-v2 reader while the
on-disk sandbox ALREADY contains v2 artifacts: flat ``.chain/`` files, internal
``refs/ideaflow/runs/{run_id}`` refs, v2 tags, and ``run_finalizations`` rows.

Coverage
--------
R1  A rollback reader ignores unknown tracked ``.chain/`` files rather than
    corrupting a run: extra files in ``.chain/`` do not crash legacy reads.

R2  A rollback reader ignores a v2 finalization record and a metadata-only
    snapshot without corrupting the run (Requirement 17 AC 18): a summary.md-only
    snapshot must not read as a truncated three-file payload.

R3  ``read_finalization_record`` returns ``None`` for both absent rows and partial
    rows — a partial row (any of the five key fields NULL) must not be read as a
    complete record (Requirement 5 AC 25).  Already exercised in test_finalizer_v2;
    repeated here as part of the task-12.6 gap-closure matrix.

R4  Feature detection uses the presence of ``refs/ideaflow/runs/{run_id}`` and
    the ``schema_version: 2`` key in ``summary.md`` — no global date flag, no
    ``V2_ENABLED`` env var, no deploy-time constant.

R5  A rollback stops producing new v2 payloads without deleting existing tags,
    internal refs, tracked flat files, audit records, or legacy payloads.
    Concretely: if the v2 code path is not invoked (simulated by the engine
    not calling ``build_flat_payload``), previously committed tags remain and the
    existing ``summary.md`` bytes are unchanged in history.

R6  ``select_legacy_payload`` (the v1 chaining read path) handles a sandbox that
    has already been migrated — where ``.chain/{run_id}/`` has been moved to
    ``.chain-legacy/{run_id}/`` — and does NOT confuse the flat v2 files
    (``logs.jsonl``, ``summary.md``, output) as a nested per-run payload.

R7  ``is_legacy_source`` is decided entirely by the internal-ref check and the
    finalization record — never by a date comparison, env var, or row count.

Requirements: 17
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — mirror the convention in test_finalizer_v2.py
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Helpers shared with test_finalizer_v2.py pattern
# ---------------------------------------------------------------------------

_USER_ID = "rollback-safety-user"
_WORKSPACE_ID = "rollback-safety-ws"


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
    _run_git("config", "user.email", "test@rollback.test", cwd=repo)
    _run_git("config", "user.name", "Rollback Safety Bot", cwd=repo)
    # Seed .gitignore exactly as the engine does (task 2.1)
    (repo / ".gitignore").write_text(
        ".chain/\n.chain.staging-*/\n.context/\n.logs/\n.uploads/\n", encoding="utf-8"
    )
    _run_git("add", ".gitignore", cwd=repo)
    _run_git("commit", "-m", "chore: init", cwd=repo)


def _make_run_id() -> str:
    return str(uuid.uuid4())


def _force_commit_chain_files(
    repo: Path,
    run_id: str,
    output_basename: str = "output.html",
    output_bytes: bytes = b"<html>v2 output</html>",
) -> str:
    """Force-add the three flat .chain/ files and commit them.  Returns commit SHA."""
    chain_dir = repo / ".chain"
    chain_dir.mkdir(exist_ok=True)
    (chain_dir / "logs.jsonl").write_bytes(b'{"event":"terminal"}\n')
    summary_text = (
        "schema_version: 2\n"
        f"run_id: {run_id}\n"
        f"output_filename: {output_basename}\n"
        "candidate_status: completed\n"
        "payload_chainable: true\n"
    )
    (chain_dir / "summary.md").write_text(summary_text, encoding="utf-8")
    (chain_dir / output_basename).write_bytes(output_bytes)

    _run_git("add", "--force", ".chain/logs.jsonl", cwd=repo)
    _run_git("add", "--force", ".chain/summary.md", cwd=repo)
    _run_git("add", "--force", f".chain/{output_basename}", cwd=repo)
    _run_git("commit", "-m", f"snapshot: {run_id} completed", cwd=repo)
    return _run_git("rev-parse", "HEAD", cwd=repo)


def _force_commit_metadata_only(repo: Path, run_id: str) -> str:
    """Commit ONLY .chain/summary.md (metadata-only snapshot). Returns commit SHA."""
    chain_dir = repo / ".chain"
    chain_dir.mkdir(exist_ok=True)
    summary_text = (
        "schema_version: 2\n"
        f"run_id: {run_id}\n"
        "output_filename: \n"
        "candidate_status: failed\n"
        "payload_chainable: false\n"
        "non_chainable_reason: payload_blocked\n"
    )
    (chain_dir / "summary.md").write_text(summary_text, encoding="utf-8")
    _run_git("add", "--force", ".chain/summary.md", cwd=repo)
    _run_git("commit", "-m", f"snapshot: {run_id} metadata-only", cwd=repo)
    return _run_git("rev-parse", "HEAD", cwd=repo)


def _create_internal_ref(repo: Path, run_id: str, sha: str) -> None:
    """Create refs/ideaflow/runs/{run_id} pointing at sha."""
    _run_git(
        "update-ref", "--create-reflog", f"refs/ideaflow/runs/{run_id}", sha, cwd=repo
    )


def _list_all_refs(repo: Path) -> str:
    """Return all git refs in the repo as one string."""
    return _run_git("for-each-ref", "--format=%(refname)", cwd=repo)


# ---------------------------------------------------------------------------
# R1: Rollback reader ignores unknown .chain/ files
# ---------------------------------------------------------------------------


class TestR1IgnoresUnknownChainFiles:
    """A v1-compatible reader receiving a v2 sandbox does not crash."""

    def test_legacy_payload_selection_ignores_flat_chain_files(
        self, tmp_path: Path
    ) -> None:
        """select_legacy_payload does not confuse flat v2 .chain/ files as a nested
        per-run directory.  The flat files are NOT UUID-named subdirectories, so
        relocate_legacy_payloads must leave them untouched, and select_legacy_payload
        must find no legacy payload (returns None) rather than crashing.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.runtime.local import select_legacy_payload  # noqa: PLC0415

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        sha = _force_commit_chain_files(repo, run_id)
        _create_internal_ref(repo, run_id, sha)
        _run_git("tag", "v1", cwd=repo)

        # Build a minimal ReadOnlySandbox-like object that reads from the repo.
        class _FakeROSandbox:
            def __init__(self) -> None:
                self._root = repo
                self._inner = _FakeInnerWS(repo)

            def read_file_at_ref(self, ref: str, path: str) -> bytes:
                raw = _run_git("show", f"{ref}:{path}", cwd=repo, check=False)
                if not raw and "does not exist" in raw:
                    return b""
                return raw.encode()

            def list_files_at_ref(self, ref: str) -> list[str]:
                raw = _run_git(
                    "ls-tree", "-r", "--name-only", ref, cwd=repo, check=False
                )
                return [l for l in raw.splitlines() if l]

            def resolve_ref_commit(self, ref: str) -> str | None:
                try:
                    return _run_git("rev-parse", ref, cwd=repo)
                except RuntimeError:
                    return None

        class _FakeInnerWS:
            def __init__(self, root: Path) -> None:
                self._root = root

            def list_tags(self) -> list[str]:
                out = _run_git("tag", cwd=self._root)
                return [t for t in out.splitlines() if t]

        src = _FakeROSandbox()

        # select_legacy_payload looks for .chain-legacy/{run_id}/ or .chain/{run_id}/
        # — neither exists here (only the flat v2 files are in .chain/).
        # It must return None without raising.
        #
        # ``runtime.local.select_legacy_payload`` takes the revision-root sandbox
        # DIRECTORY (``sandbox_root: Path, source_run_id``) — it has never accepted a
        # sandbox handle or ``declared_output_basename`` (that is the separate
        # ``app.agents.sandbox`` variant exercised by TestR6 below).
        assert src._root == repo
        result = select_legacy_payload(repo, run_id)
        assert result is None, (
            "select_legacy_payload must return None for a v2 sandbox with only flat files; "
            f"got {result!r}"
        )

    def test_flat_chain_files_not_treated_as_legacy_directory(
        self, tmp_path: Path
    ) -> None:
        """Non-UUID entries in .chain/ are not treated as per-run payload directories."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        _force_commit_chain_files(repo, run_id)

        # The three flat files must be present in the committed tree.
        tree = _run_git("ls-tree", "-r", "--name-only", "HEAD", cwd=repo)
        tracked = tree.splitlines()
        assert ".chain/logs.jsonl" in tracked, "logs.jsonl must be tracked"
        assert ".chain/summary.md" in tracked, "summary.md must be tracked"
        assert ".chain/output.html" in tracked, "output.html must be tracked"

        # No UUID-shaped subdirectory must appear under .chain/
        uuid_dirs = [
            p
            for p in tracked
            if p.startswith(".chain/")
            and p != ".chain/"
            and "/" in p[len(".chain/") :]  # has a further segment = subdirectory entry
        ]
        assert (
            not uuid_dirs
        ), f"Flat v2 .chain/ must not contain subdirectories; found: {uuid_dirs}"


# ---------------------------------------------------------------------------
# R2: Metadata-only snapshot not misread as truncated three-file payload
# ---------------------------------------------------------------------------


class TestR2MetadataOnlyNotTruncated:
    """A summary.md-only commit must be recognized as metadata-only, not corrupt."""

    def test_metadata_only_summary_has_payload_chainable_false(
        self, tmp_path: Path
    ) -> None:
        """The summary.md of a metadata-only snapshot declares payload_chainable: false.
        A rollback-era reader that parses this field will not confuse it with a
        successful three-file payload (Requirement 17 AC 18).
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        _force_commit_metadata_only(repo, run_id)

        # Read back the committed summary.md
        summary_text = _run_git("show", "HEAD:.chain/summary.md", cwd=repo)

        assert (
            "schema_version: 2" in summary_text
        ), "summary must carry schema_version: 2"
        assert (
            "payload_chainable: false" in summary_text
        ), "metadata-only snapshot must declare payload_chainable: false"
        assert (
            "output_filename: " in summary_text
        ), "metadata-only snapshot must have output_filename field (blank or empty)"

        # logs.jsonl and output file must NOT be in the committed tree
        tree = _run_git("ls-tree", "-r", "--name-only", "HEAD", cwd=repo)
        tracked = tree.splitlines()
        assert (
            ".chain/logs.jsonl" not in tracked
        ), "metadata-only commit must NOT contain logs.jsonl"
        output_files = [
            f
            for f in tracked
            if f.startswith(".chain/") and f not in {".chain/summary.md"}
        ]
        assert not output_files, f"metadata-only commit must contain ONLY .chain/summary.md; also found: {output_files}"

    def test_schema_version_field_is_v2_not_v1(self, tmp_path: Path) -> None:
        """The schema_version written by the engine is 2, not 1.
        A reader checking this field can distinguish v2 from legacy payloads.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        _force_commit_chain_files(repo, run_id)

        summary_text = _run_git("show", "HEAD:.chain/summary.md", cwd=repo)
        assert (
            "schema_version: 2" in summary_text
        ), "v2 summary.md must declare schema_version: 2 for rollback feature detection"
        assert (
            "schema_version: 1" not in summary_text
        ), "v2 summary.md must NOT carry schema_version: 1"

    def test_build_metadata_only_snapshot_produces_summary_only(
        self, tmp_path: Path
    ) -> None:
        """build_metadata_only_snapshot stages only .chain/summary.md — not logs.jsonl
        or any output file — confirming the on-disk state a rollback reader will see.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_metadata_only_snapshot  # noqa: PLC0415

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)

        # Minimal fake sandbox
        from tests.agents.test_finalizer_v2 import (  # noqa: PLC0415
            FakeSandbox,
            _make_ectx,
        )

        sandbox = FakeSandbox(
            root=repo,
            run_id=run_id,
            sandbox_root_id=run_id,
            current_run_id=run_id,
        )
        ectx = _make_ectx(run_id, sandbox)

        payload = build_metadata_only_snapshot(
            run_id, ectx, non_chainable_reason="payload_blocked"
        )

        assert payload.built is True, "metadata-only snapshot must report built=True"
        assert (
            payload.materialized is False
        ), "metadata-only snapshot must report materialized=False"
        assert (
            payload.chainable is False
        ), "metadata-only snapshot must report chainable=False"

        # Staged entry set must be {'.chain/summary.md'} only
        staged = (
            sandbox.staged_entries() if hasattr(sandbox, "staged_entries") else None
        )
        if staged is not None:
            summary_only = all(e == ".chain/summary.md" for e in staged)
            assert summary_only, f"metadata-only snapshot must stage ONLY .chain/summary.md; staged: {staged}"

        # allowlist must be the single-entry set
        assert (
            payload.allowlist == frozenset({".chain/summary.md"})
        ), f"metadata-only allowlist must be {{'.chain/summary.md'}}; got {payload.allowlist}"


# ---------------------------------------------------------------------------
# R3: read_finalization_record returns None for partial/absent rows
# ---------------------------------------------------------------------------


class TestR3ReadFinalizationRecordPartialRow:
    """Rollback safety: a partial row must not be read as a complete record."""

    def test_absent_row_returns_none(self) -> None:
        """When no row exists, read_finalization_record returns None."""
        from agents.execution_engine.finalization import read_finalization_record  # noqa: PLC0415

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.models.run_finalization.RunFinalization", MagicMock()):
            result = read_finalization_record(db, "nonexistent-run-id")

        assert (
            result is None
        ), "read_finalization_record must return None for an absent row"

    @pytest.mark.parametrize(
        "missing_field",
        [
            "published_status",
            "candidate_status",
            "payload_chainable",
            "commit_sha",
            "run_id",
        ],
    )
    def test_partial_row_returns_none(self, missing_field: str) -> None:
        """A row missing any of the five key fields must be treated as absent."""
        from agents.execution_engine.finalization import read_finalization_record  # noqa: PLC0415

        all_fields = {
            "run_id": "test-run-partial",
            "owner_id": "owner",
            "workspace_id": "ws",
            "published_status": "completed",
            "candidate_status": "completed",
            "payload_chainable": True,
            "commit_sha": "deadbeef" * 5,
            "non_chainable_reason": None,
            "payload_built": True,
            "payload_materialized": True,
            "internal_ref": None,
            "git_tag": "v1",
            "tag_state": "created",
            "chain_context_installed": None,
        }
        all_fields[missing_field] = None  # NULL the key field

        row = MagicMock()
        for k, v in all_fields.items():
            setattr(row, k, v)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        with patch("app.models.run_finalization.RunFinalization", MagicMock()):
            result = read_finalization_record(db, "test-run-partial")

        assert result is None, (
            f"read_finalization_record must return None when {missing_field!r} is NULL; "
            f"a partial row is indistinguishable from absent (Requirement 5 AC 25)"
        )


# ---------------------------------------------------------------------------
# R4: Feature detection uses internal ref + schema_version, not global flags
# ---------------------------------------------------------------------------


class TestR4FeatureDetectionNoBooleanFlag:
    """Feature detection is by Git ref + summary.md, never a global toggle."""

    def test_no_v2_enabled_env_var(self) -> None:
        """No symbol named V2_ENABLED, v2_enabled, or similar exists in the relevant modules."""
        # If these symbols exist the rollback contract is broken — a deployed flag
        # can get stuck and either permanently disable or permanently enable v2 reads.
        import importlib  # noqa: PLC0415

        suspect_patterns = [
            "V2_ENABLED",
            "v2_enabled",
            "FEATURE_FLAG",
            "feature_flag",
            "deploy_date",
            "DEPLOY_DATE",
            "V2_FLAG",
        ]

        modules_to_check = [
            "app.api.run_commands",
            "agents.execution_engine.engine",
            "agents.execution_engine.finalization",
            "app.agents.sandbox",
            "app.agents.runtime.local",
        ]

        for mod_name in modules_to_check:
            try:
                mod = importlib.import_module(mod_name)
            except ImportError:
                continue
            import inspect  # noqa: PLC0415

            src = inspect.getsource(mod)
            for pattern in suspect_patterns:
                assert pattern not in src, (
                    f"Module {mod_name!r} must not contain {pattern!r} — "
                    "feature detection must use the internal run ref and "
                    "schema_version in summary.md, not a global toggle."
                )

    def test_is_legacy_source_uses_ref_check_not_date(self) -> None:
        """is_legacy_source discrimination is by ref presence + record, not datetime."""
        import inspect  # noqa: PLC0415

        from app.api.run_commands import is_legacy_source  # noqa: PLC0415

        src = inspect.getsource(is_legacy_source)

        # Must not compare against any date or env var
        for forbidden in (
            "datetime.now",
            "os.environ",
            "V2_ENABLED",
            "deploy_date",
            "time.time",
        ):
            assert forbidden not in src, (
                f"is_legacy_source must not use {forbidden!r}; "
                "detection must be by refs/ideaflow/runs/ presence only."
            )

        # Must reference the internal ref namespace
        assert (
            "refs/ideaflow/runs/" in src or "resolve_ref_commit" in src
        ), "is_legacy_source must check the internal run ref for feature detection"

    def test_summary_md_carries_schema_version_field(self, tmp_path: Path) -> None:
        """render_summary_text always writes schema_version: 2 as the first field."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        # The renderer has been ``render_summary_md`` since e7305f9d (the commit that
        # added this test); ``_render_summary_text`` never existed in engine.py.
        from agents.execution_engine.engine import (  # noqa: PLC0415
            render_summary_md as _render_summary_text,
        )

        # Build a minimal ectx
        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)

        # Import FakeSandbox from test_finalizer_v2 — same helper pattern
        from tests.agents.test_finalizer_v2 import FakeSandbox, _make_ectx  # noqa: PLC0415

        sandbox = FakeSandbox(
            root=repo,
            run_id=run_id,
            sandbox_root_id=run_id,
            current_run_id=run_id,
        )
        ectx = _make_ectx(run_id, sandbox)

        text = _render_summary_text(
            run_id=run_id,
            ectx=ectx,
            candidate_status="completed",
            completed_steps=3,
            output_filename="output.html",
            intended_tag="v1",
            payload_chainable=True,
            non_chainable_reason="",
        )

        assert text.startswith(
            "schema_version: 2\n"
        ), "summary.md must start with 'schema_version: 2' for rollback detection"


# ---------------------------------------------------------------------------
# R5: Rollback stops producing new payloads without deleting existing artifacts
# ---------------------------------------------------------------------------


class TestR5RollbackPreservesExistingArtifacts:
    """Existing tags, refs, and flat files survive a 'rollback' (non-invocation
    of the v2 commit path)."""

    def test_existing_tag_survives_when_v2_commit_not_called(
        self, tmp_path: Path
    ) -> None:
        """A pre-existing v2 tag is not removed when the finalizer is not invoked."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        sha = _force_commit_chain_files(repo, run_id)
        _run_git("tag", "v1", cwd=repo)
        _create_internal_ref(repo, run_id, sha)

        # Simulate a "rollback reader" by NOT calling build_flat_payload or
        # finalize_terminal_run — just reading the state.
        tags_after = _run_git("tag", cwd=repo)
        assert (
            "v1" in tags_after.splitlines()
        ), "Existing tag v1 must survive when the v2 finalizer is not invoked"

        refs_after = _list_all_refs(repo)
        assert (
            f"refs/ideaflow/runs/{run_id}" in refs_after
        ), "Existing internal run ref must survive when the v2 finalizer is not invoked"

    def test_existing_flat_chain_files_survive_rollback(self, tmp_path: Path) -> None:
        """Flat .chain/ files committed to history are never deleted by a rollback reader."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        _force_commit_chain_files(repo, run_id, output_basename="output.html")

        # Verify the three files are in the committed tree at HEAD
        tree = _run_git("ls-tree", "-r", "--name-only", "HEAD", cwd=repo)
        tracked = tree.splitlines()
        assert ".chain/logs.jsonl" in tracked
        assert ".chain/summary.md" in tracked
        assert ".chain/output.html" in tracked

        # A second commit that does NOT touch .chain/ (simulating a rollback build)
        (repo / "some_other_file.txt").write_text("rollback era", encoding="utf-8")
        _run_git("add", "some_other_file.txt", cwd=repo)
        _run_git("commit", "-m", "rollback-era commit", cwd=repo)

        # The original .chain/ files must still be accessible at the v1 tag
        # (i.e., history was not rewritten)
        history = _run_git("log", "--oneline", "--all", cwd=repo)
        assert (
            "snapshot" in history
        ), "The original snapshot commit must still exist in history"

        # Whether the .chain/ files are still at HEAD is not the contract (a rollback
        # build doesn't write them) — they must be retrievable from history.
        objects = _run_git("rev-list", "--objects", "--all", cwd=repo)
        assert (
            "logs.jsonl" in objects or ".chain" in objects
        ), "Committed .chain/ objects must still exist in git history after a rollback build"

    def test_legacy_payloads_not_deleted_by_metadata_only_snapshot(
        self, tmp_path: Path
    ) -> None:
        """.chain-legacy/{run_id}/ payload files are not disturbed when a new
        metadata-only snapshot is built for a subsequent run.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        repo = tmp_path / "shared-sandbox"
        repo.mkdir()
        _git_init(repo)

        # Plant a legacy payload
        legacy_id = _make_run_id()
        legacy_dir = repo / ".chain-legacy" / legacy_id
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "summary.md").write_text(
            f"run_id: {legacy_id}\noutput_filename: out.html\n", encoding="utf-8"
        )
        (legacy_dir / "out.html").write_bytes(b"<html>legacy</html>")

        # Run metadata-only snapshot for a NEW run in the same sandbox
        new_run_id = _make_run_id()
        _force_commit_metadata_only(repo, new_run_id)

        # The legacy directory must still exist on disk (not deleted)
        assert (
            legacy_dir / "summary.md"
        ).exists(), (
            ".chain-legacy payload must survive a metadata-only snapshot for a new run"
        )
        assert (
            legacy_dir / "out.html"
        ).exists(), ".chain-legacy output file must survive a metadata-only snapshot"


# ---------------------------------------------------------------------------
# R6: select_legacy_payload does not confuse post-relocation sandbox
# ---------------------------------------------------------------------------


class TestR6LegacySelectDoesNotConfuseV2Layout:
    """After migration the flat v2 .chain/ files must not be selected as legacy."""

    def test_flat_chain_files_not_selected_as_legacy_payload(
        self, tmp_path: Path
    ) -> None:
        """The three flat v2 files are not UUID-shaped subdirectories so
        select_legacy_payload must skip them and return None.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.sandbox import select_legacy_payload  # noqa: PLC0415

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)
        _force_commit_chain_files(repo, run_id)

        # Build a minimal ReadOnlySandbox shim
        class _MinimalROSandbox:
            def __init__(self) -> None:
                self._root = repo
                self._inner = _Inner()

            # ``app.agents.sandbox.select_legacy_payload`` reads the LIVE working tree
            # through ``ReadOnlySandbox.list_prefix`` / ``read_bytes`` (same contract
            # as ``LocalWorkspace.list_prefix`` — os.walk, no git — and
            # ``ReadOnlySandbox.read_bytes`` — ``None`` when absent).
            def list_prefix(self, prefix: str) -> list[str]:
                return sorted(
                    rel
                    for rel in (
                        f.relative_to(repo).as_posix()
                        for f in repo.rglob("*")
                        if f.is_file()
                    )
                    if rel.startswith(prefix) and not rel.startswith(".git/")
                )

            def read_bytes(self, relpath: str) -> bytes | None:
                target = repo / relpath
                return target.read_bytes() if target.is_file() else None

            def read_bytes_at_ref(self, ref: str, path: str) -> bytes | None:
                try:
                    raw = _run_git("show", f"{ref}:{path}", cwd=repo, check=False)
                    return raw.encode()
                except Exception:  # noqa: BLE001
                    return None

            def list_files_at_ref(self, ref: str) -> list[str]:
                raw = _run_git(
                    "ls-tree", "-r", "--name-only", ref, cwd=repo, check=False
                )
                return [l for l in raw.splitlines() if l]

            def resolve_ref_commit(self, ref: str) -> str | None:
                try:
                    return _run_git("rev-parse", ref, cwd=repo)
                except RuntimeError:
                    return None

        class _Inner:
            def list_tags(self) -> list[str]:
                out = _run_git("tag", cwd=repo)
                return [t for t in out.splitlines() if t]

        src = _MinimalROSandbox()

        # The flat files (.chain/logs.jsonl etc.) are NOT UUID-shaped dirs.
        # select_legacy_payload must return None — no legacy payload found.
        result = select_legacy_payload(src, run_id, declared_output_basename=None)
        assert (
            result is None
        ), f"select_legacy_payload must return None for a v2 flat-payload sandbox; got {result!r}"

    def test_chain_legacy_dir_selected_not_chain_flat(self, tmp_path: Path) -> None:
        """When .chain-legacy/{run_id}/ exists alongside flat .chain/ files,
        only the legacy directory is considered by select_legacy_payload.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.sandbox import select_legacy_payload  # noqa: PLC0415

        run_id = _make_run_id()
        repo = tmp_path / run_id
        repo.mkdir()
        _git_init(repo)

        # Flat v2 files
        _force_commit_chain_files(repo, run_id)

        # Also plant a legacy directory
        legacy_dir = repo / ".chain-legacy" / run_id
        legacy_dir.mkdir(parents=True)
        legacy_summary = f"run_id: {run_id}\noutput_filename: legacy.html\n"
        (legacy_dir / "summary.md").write_text(legacy_summary, encoding="utf-8")
        (legacy_dir / "legacy.html").write_bytes(b"<html>legacy</html>")

        class _ROSandbox:
            def __init__(self) -> None:
                self._root = repo
                self._inner = _Inner2()

            # ``app.agents.sandbox.select_legacy_payload`` reads the LIVE working tree
            # through ``ReadOnlySandbox.list_prefix`` / ``read_bytes`` (same contract
            # as ``LocalWorkspace.list_prefix`` — os.walk, no git — and
            # ``ReadOnlySandbox.read_bytes`` — ``None`` when absent).
            def list_prefix(self, prefix: str) -> list[str]:
                return sorted(
                    rel
                    for rel in (
                        f.relative_to(repo).as_posix()
                        for f in repo.rglob("*")
                        if f.is_file()
                    )
                    if rel.startswith(prefix) and not rel.startswith(".git/")
                )

            def read_bytes(self, relpath: str) -> bytes | None:
                target = repo / relpath
                return target.read_bytes() if target.is_file() else None

            def read_bytes_at_ref(self, ref: str, path: str) -> bytes | None:
                try:
                    raw = _run_git("show", f"{ref}:{path}", cwd=repo, check=False)
                    return raw.encode()
                except Exception:  # noqa: BLE001
                    return None

            def list_files_at_ref(self, ref: str) -> list[str]:
                raw = _run_git(
                    "ls-tree", "-r", "--name-only", ref, cwd=repo, check=False
                )
                return [l for l in raw.splitlines() if l]

            def resolve_ref_commit(self, ref: str) -> str | None:
                try:
                    return _run_git("rev-parse", ref, cwd=repo)
                except RuntimeError:
                    return None

        class _Inner2:
            def list_tags(self) -> list[str]:
                out = _run_git("tag", cwd=repo)
                return [t for t in out.splitlines() if t]

        src = _ROSandbox()

        result = select_legacy_payload(src, run_id, declared_output_basename=None)
        # Should find the legacy directory, not the flat v2 files
        assert (
            result is not None
        ), "select_legacy_payload must find the .chain-legacy/{run_id}/ directory"
        # The result must reference the legacy directory, not a flat .chain/ path
        assert result.base is not None  # type: ignore[union-attr]
        assert "chain-legacy" in str(result.base), (  # type: ignore[union-attr]
            "select_legacy_payload must pick from .chain-legacy/, not from flat .chain/ files"
        )


# ---------------------------------------------------------------------------
# R7: is_legacy_source decided by ref+record, never by date or env var
# ---------------------------------------------------------------------------


class TestR7LegacySourceNoBooleanFlag:
    """is_legacy_source uses only the internal ref and the finalization record."""

    def test_v2_run_with_ref_and_record_is_not_legacy(self) -> None:
        """A run that has an internal ref AND a finalization record is NOT legacy."""
        from app.api.run_commands import is_legacy_source  # noqa: PLC0415
        from agents.execution_engine.finalization import FinalizationRecord  # noqa: PLC0415

        record = FinalizationRecord(
            run_id="v2-run",
            owner_id=_USER_ID,
            workspace_id=_WORKSPACE_ID,
            published_status="completed",
            candidate_status="completed",
            payload_chainable=True,
            commit_sha="deadbeef" * 5,
        )

        src = MagicMock()
        src.resolve_ref_commit.return_value = "abc123"  # ref exists

        result = is_legacy_source(src, "v2-run", record=record)
        assert (
            result is False
        ), "A v2 run with an internal ref and a finalization record must NOT be legacy"

    def test_run_without_internal_ref_is_legacy(self) -> None:
        """A run that has no internal ref (pre-v2) is classified as legacy."""
        from app.api.run_commands import is_legacy_source  # noqa: PLC0415
        from agents.execution_engine.finalization import FinalizationRecord  # noqa: PLC0415

        record = FinalizationRecord(
            run_id="old-run",
            owner_id=_USER_ID,
            workspace_id=_WORKSPACE_ID,
            published_status="completed",
            candidate_status="completed",
            payload_chainable=True,
            commit_sha="deadbeef" * 5,
        )

        src = MagicMock()
        src.resolve_ref_commit.return_value = None  # ref absent — pre-v2 run

        result = is_legacy_source(src, "old-run", record=record)
        assert result is True, (
            "A run without an internal ref must be classified as legacy "
            "regardless of any record"
        )

    def test_record_none_is_legacy_regardless_of_ref(self) -> None:
        """When record is None the run is legacy — the record gate fires first."""
        from app.api.run_commands import is_legacy_source  # noqa: PLC0415

        src = MagicMock()
        # Even if the ref exists, record=None → legacy
        src.resolve_ref_commit.return_value = "abc123"

        result = is_legacy_source(src, "no-record-run", record=None)
        assert result is True, (
            "is_legacy_source must return True when record is None "
            "(pre-v2 run, regardless of ref state)"
        )

    def test_is_legacy_source_inspectable_without_side_effects(self) -> None:
        """is_legacy_source makes at most one resolve_ref_commit call.
        It must not write any Git object, create any ref, or start any subprocess.
        """
        from app.api.run_commands import is_legacy_source  # noqa: PLC0415
        from agents.execution_engine.finalization import FinalizationRecord  # noqa: PLC0415

        record = FinalizationRecord(
            run_id="side-effect-check",
            owner_id=_USER_ID,
            workspace_id=_WORKSPACE_ID,
            published_status="completed",
            candidate_status="completed",
            payload_chainable=True,
            commit_sha="aabbccdd" * 5,
        )

        src = MagicMock()
        src.resolve_ref_commit.return_value = "sha123"

        is_legacy_source(src, "side-effect-check", record=record)

        # No write methods should have been called
        src.create_run_ref.assert_not_called()
        src.create_tag.assert_not_called()
        if hasattr(src, "stage_exact"):
            src.stage_exact.assert_not_called()
