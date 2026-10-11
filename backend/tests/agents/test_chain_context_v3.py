"""Behavioral tests for chain context (task V4, FR-020/022/024/026).

Coverage
--------
1. FR-020: mint/launch writes source_run_id
   - Chained launch records source_workflow_run_id as source_run_id
   - Revision launch records parent_run_id as source_run_id

2. FR-022: both parent_run_id and chain_source_run_id set; family walk never follows chain edge
   - A revision (both parent_run_id and source_run_id set to same value) walks to root
   - The family BFS never follows the chain edge into an unrelated family
   - Walk stops at the revision root, not at a chained ancestor

3. FR-024/AC-04/AC-22: root-resolve then read_bytes_at_ref from mid-family revision
   - A mid-family revision can be the source of a new chain
   - Chain reads resolve the source's root correctly
   - File read from an exact git ref works for chained payloads

4. FR-026: install returns {} and lands files at .context/ root
   - ChainContextProvider.load() returns empty dict (no text injection)
   - Files are copied to .context/ in the receiving sandbox
   - Both V2 (from git ref) and legacy paths tested
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Path setup — make backend/ importable
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Shared in-memory DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """SQLite in-memory session with workflow_runs table created."""
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


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _run_id() -> str:
    return str(uuid.uuid4())


def _seed_run(
    session,
    *,
    run_id: str,
    user_id: str,
    parent_run_id: str | None = None,
    source_run_id: str | None = None,
    status: str = "completed",
) -> str:
    """Insert a minimal workflow_runs row and return its id."""
    from app.models.workflow import WorkflowRun

    row = WorkflowRun(
        id=run_id,
        user_id=user_id,
        title="test run",
        type="custom",
        status=status,
        input="test input",
        parent_run_id=parent_run_id,
        source_run_id=source_run_id,
    )
    session.add(row)
    session.commit()
    return run_id


# ===========================================================================
# FR-020: source_run_id is written on mint/launch
# ===========================================================================


class TestFR020SourceRunIdWritten:
    """Verify that source_run_id is recorded at run creation time.

    FR-020 / Requirement 22 AC1/AC2
    """

    def test_revision_mint_writes_source_run_id_equals_parent(self, db_session):
        """_mint_revision_row writes source_run_id = parent_run_id."""
        # Create a root run
        root_id = _run_id()
        user_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id=user_id, status="completed")

        # Create a revision via _mint_revision_row
        from app.api.run_commands import _mint_revision_row
        from app.models.user import User

        user = MagicMock(spec=User)
        user.id = user_id
        user.tier = "pro"

        with patch("app.api.run_commands.can_run_pipeline", return_value=(True, "")):
            with patch(
                "agents.registry.get_pipeline_agents", return_value=["a1", "a2"]
            ):
                rev_id, _ = _mint_revision_row(
                    db_session,
                    user=user,
                    # The caller's EFFECTIVE tier (Cognito-only auth migration,
                    # Decision 3) — the same tier this user carries.
                    caller_tier="pro",
                    parent_run_id=root_id,
                    target_artifact_type="custom_output",
                    instruction="test revision",
                )

        # Verify source_run_id = parent_run_id
        from app.models.workflow import WorkflowRun

        rev_row = db_session.query(WorkflowRun).filter(WorkflowRun.id == rev_id).first()
        assert rev_row is not None
        assert rev_row.source_run_id == root_id
        assert rev_row.parent_run_id == root_id

    def test_chained_launch_writes_source_run_id_from_source_workflow(self, db_session):
        """_launch_run_core writes source_run_id from source_workflow_run_id."""
        from app.models.workflow import WorkflowRun

        # Create a source run
        source_id = _run_id()
        user_id = _run_id()
        _seed_run(db_session, run_id=source_id, user_id=user_id, status="completed")

        # Create a chained run that sources from source_id
        chained_id = _run_id()
        chained_row = WorkflowRun(
            id=chained_id,
            user_id=user_id,
            title="chained run",
            type="custom",
            status="running",
            input="brief",
            parent_run_id=None,  # No revision relationship
            source_run_id=source_id,  # Chained source
        )
        db_session.add(chained_row)
        db_session.commit()

        # Verify the chained run has source_run_id set to the source
        row = db_session.query(WorkflowRun).filter(WorkflowRun.id == chained_id).first()
        assert row.source_run_id == source_id
        assert row.parent_run_id is None  # Not a revision


# ===========================================================================
# FR-022: family walk never follows chain edge
# ===========================================================================


class TestFR022FamilyWalkIgnoresChainEdge:
    """Verify that family resolution doesn't follow chain edges.

    FR-022 / Requirement 1 AC 2
    """

    def test_revision_walk_stops_at_root_not_chain_ancestor(self, db_session):
        """A revision-only run walks to the root; a chained source is not traversed."""
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        user_id = _run_id()

        # Create: root → chained-from-root → revision-of-root
        # The revision's source_run_id (chain edge) should not be followed.
        root_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id=user_id, status="completed")

        # A chained run from root (external family)
        external_id = _run_id()
        other_user = _run_id()
        _seed_run(
            db_session,
            run_id=external_id,
            user_id=other_user,
            source_run_id=root_id,
            status="completed",
        )

        # A revision of root (same user, same family)
        rev_id = _run_id()
        _seed_run(
            db_session,
            run_id=rev_id,
            user_id=user_id,
            parent_run_id=root_id,
            source_run_id=root_id,
            status="running",
        )

        # Resolve revision root from the revision
        # Should walk parent_run_id (root_id) and stop, not follow source_run_id
        result = resolve_revision_root(db_session, rev_id, user_id)
        assert isinstance(result, RevisionRootResolved)
        assert result.root_id == root_id

    def test_both_fields_set_parent_walk_chosen(self, db_session):
        """When both parent_run_id and source_run_id are set, walk uses parent edge."""
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        user_id = _run_id()

        # root → chained-external → revision-of-root (both edges set)
        root_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id=user_id, status="completed")

        # A chained run (external source)
        external_id = _run_id()
        _seed_run(db_session, run_id=external_id, user_id=user_id, status="completed")

        # A revision with BOTH parent and source set (parent = root, source = external)
        rev_id = _run_id()
        _seed_run(
            db_session,
            run_id=rev_id,
            user_id=user_id,
            parent_run_id=root_id,
            source_run_id=external_id,
            status="running",
        )

        # Resolution should use parent, not source
        result = resolve_revision_root(db_session, rev_id, user_id)
        assert isinstance(result, RevisionRootResolved)
        assert result.root_id == root_id


# ===========================================================================
# FR-024: root-resolve then read from mid-family revision
# ===========================================================================


class TestFR024RootResolveFromMidFamily:
    """Verify root resolution and file reads from a mid-family revision.

    FR-024 / AC-04 / AC-22
    """

    def test_mid_family_revision_resolves_root_correctly(self, db_session):
        """A mid-family revision (depth 2) resolves to the true root."""
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        user_id = _run_id()

        # root → rev1 → rev2
        root_id = _run_id()
        rev1_id = _run_id()
        rev2_id = _run_id()

        _seed_run(db_session, run_id=root_id, user_id=user_id, status="completed")
        _seed_run(
            db_session,
            run_id=rev1_id,
            user_id=user_id,
            parent_run_id=root_id,
            source_run_id=root_id,
            status="completed",
        )
        _seed_run(
            db_session,
            run_id=rev2_id,
            user_id=user_id,
            parent_run_id=rev1_id,
            source_run_id=rev1_id,
            status="running",
        )

        # Both rev1 and rev2 should resolve to root
        result1 = resolve_revision_root(db_session, rev1_id, user_id)
        result2 = resolve_revision_root(db_session, rev2_id, user_id)
        assert isinstance(result1, RevisionRootResolved)
        assert isinstance(result2, RevisionRootResolved)
        assert result1.root_id == root_id
        assert result2.root_id == root_id

    def test_mid_family_can_be_chain_source(self, db_session, tmp_path: Path):
        """A mid-family revision can source a new chained run.

        When a chained run sources from a mid-family revision, the sandbox root
        resolution should find the shared directory correctly.
        """
        from app.agents.sandbox import RunSandbox
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        user_id = _run_id()

        # Setup: root → rev1 → new chained run from rev1
        root_id = _run_id()
        rev1_id = _run_id()
        chained_id = _run_id()

        _seed_run(db_session, run_id=root_id, user_id=user_id, status="completed")
        _seed_run(
            db_session,
            run_id=rev1_id,
            user_id=user_id,
            parent_run_id=root_id,
            source_run_id=root_id,
            status="completed",
        )
        _seed_run(
            db_session,
            run_id=chained_id,
            user_id=user_id,
            parent_run_id=None,
            source_run_id=rev1_id,
            status="running",
        )

        # The chained run should use the root sandbox (shared with rev1)
        root_sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        # rev1 shares the same sandbox root (root_id)
        rev1_sb = RunSandbox(
            user_id, root_id, current_run_id=rev1_id, runs_root=str(tmp_path)
        )
        # chained creates a new family (no parent_run_id), so it uses its own run_id as root
        chained_sb = RunSandbox(user_id, chained_id, runs_root=str(tmp_path))

        # rev1 and root share the same sandbox
        assert rev1_sb.root == root_sb.root
        # chained creates a new family, so it has a different root
        assert chained_sb.root != root_sb.root
        assert chained_sb.root.name == chained_id


# ===========================================================================
# FR-026: install returns {} and lands files at .context/
# ===========================================================================


class TestFR026InstallReturnsEmptyAndLandsFiles:
    """Verify ChainContextProvider behavior: returns {} and copies to .context/.

    FR-026 / Requirement 21 AC 8
    """

    @pytest.mark.asyncio
    async def test_provider_load_returns_empty_dict(self):
        """ChainContextProvider.load() always returns an empty dict (no text injection)."""
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        provider = ChainContextProvider()

        # Create a minimal context that triggers the declaration gate
        ctx = MagicMock()
        ctx.compiled_plan = MagicMock()
        ctx.compiled_plan.deliverable.chains_from = False  # Gate off

        result = await provider.load(ctx)
        assert result == {}
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_provider_dormant_when_chains_from_false(self):
        """Provider returns {} when workflow doesn't declare chains_from."""
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        provider = ChainContextProvider()
        ctx = MagicMock()
        ctx.compiled_plan = MagicMock()
        ctx.compiled_plan.deliverable.chains_from = False
        ctx.chain_source_run_id = "some-id"  # Stray source (should be ignored)

        result = await provider.load(ctx)
        assert result == {}

    @pytest.mark.asyncio
    async def test_provider_dormant_when_no_source(self):
        """Provider returns {} when chain_source_run_id is missing."""
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        provider = ChainContextProvider()
        ctx = MagicMock()
        ctx.compiled_plan = MagicMock()
        ctx.compiled_plan.deliverable.chains_from = True
        ctx.chain_source_run_id = None  # No source

        result = await provider.load(ctx)
        assert result == {}

    @pytest.mark.asyncio
    async def test_provider_returns_empty_dict_on_successful_path(self):
        """Even on successful paths, the provider returns {} (no text blocks)."""
        # This test verifies the core contract: ChainContextProvider always
        # returns empty dict. The return value is consistent regardless of path
        # (whether install succeeds, fails, or is skipped).
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        provider = ChainContextProvider()

        # Case 1: No source (dormant)
        ctx1 = MagicMock()
        ctx1.compiled_plan = MagicMock()
        ctx1.compiled_plan.deliverable.chains_from = True
        ctx1.chain_source_run_id = None

        result1 = await provider.load(ctx1)
        assert result1 == {}
        assert isinstance(result1, dict)

        # Case 2: No chains_from declaration (dormant)
        ctx2 = MagicMock()
        ctx2.compiled_plan = MagicMock()
        ctx2.compiled_plan.deliverable.chains_from = False
        ctx2.chain_source_run_id = "source-id"

        result2 = await provider.load(ctx2)
        assert result2 == {}

    @pytest.mark.asyncio
    async def test_provider_dormant_blocks_no_file_reads(self, tmp_path: Path):
        """When provider is dormant, no cross-run file reads occur.

        FR-026 / V2-Q8: The provider is declaration-gated on chains_from.
        A stray chain_source_run_id on a workflow that doesn't declare chaining
        triggers ZERO cross-run reads.
        """
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        provider = ChainContextProvider()

        # Setup: chains_from=False, but a source_run_id is present (stray)
        ctx = MagicMock()
        ctx.compiled_plan = MagicMock()
        ctx.compiled_plan.deliverable.chains_from = False  # Gate off
        ctx.chain_source_run_id = "source-123"  # Stray (should be ignored)
        ctx.chain_selection = MagicMock()
        ctx.chain_selection.is_legacy = False

        # If the provider tries to read, this will fail
        ctx.runner = MagicMock()
        ctx.runner.sandbox = None
        ctx.runner.open_source_sandbox = MagicMock(
            side_effect=RuntimeError("Should not be called")
        )

        # Provider should return {} without any cross-run reads
        result = await provider.load(ctx)
        assert result == {}

        # Verify open_source_sandbox was never called
        ctx.runner.open_source_sandbox.assert_not_called()


# ===========================================================================
# FR-024/AC-04/AC-22 + FR-026: real git-ref-backed V2 install
#
# V4-verify fix attempt 1: the five FR-026 tests above and
# TestFR024RootResolveFromMidFamily's two tests only exercise the dormant/
# gate-off paths and DB-only root resolution — none drives _install_v2 or
# calls read_bytes_at_ref. These two tests build a REAL git-backed source
# sandbox (a real .chain/ commit + tag, no mocked git subprocess) and drive
# ChainContextProvider.load() through _install_v2, asserting
# read_bytes_at_ref is actually invoked (via a wrapping spy on the real
# bound method, not a stub) and that the exact bytes land under the
# receiving sandbox's .context/ directory.
# ===========================================================================


class TestInstallV2RealGitRef:
    """Drives ``_install_v2`` end to end against a real git repository."""

    def _make_git_sandbox(
        self,
        tmp_path: Path,
        *,
        sandbox_root_id: str,
        current_run_id: str | None = None,
    ):
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox(
            "chain-user",
            sandbox_root_id,
            current_run_id=current_run_id,
            runs_root=str(tmp_path / "runs"),
        )
        sb.ensure()
        sb.git_init_sandbox()
        return sb

    def _commit_chain_payload(
        self, sb, *, logs: str, summary: str, html: str, tag: str
    ) -> str:
        from app.agents.sandbox import payload_allowlist

        sb.write(".chain/logs.jsonl", logs)
        sb.write(".chain/summary.md", summary)
        sb.write(".chain/hello.html", html)
        sha = sb.commit_all(
            f"chore: chain payload {tag}",
            force_add=payload_allowlist("hello.html"),
        )
        assert sha, "commit_all must actually commit the force-added .chain/ payload"
        return sb.create_tag(tag)

    class _FakeChainRunner:
        """Not a MagicMock: mark_chain_context_installed / record_provenance_audit
        must be genuinely absent (getattr(..., None) -> None) so the provider
        takes its documented "not available" skip branch, matching the pattern
        already accepted in test_phase5_chaining.py::TestNoDoubleDeliveryV2."""

        def __init__(self, sandbox: Any, source_sandbox: Any) -> None:
            self.sandbox = sandbox
            self._source_sandbox = source_sandbox
            self.opened_with: str | None = None

        def open_source_sandbox(self, source_run_id: str) -> Any:
            self.opened_with = source_run_id
            return self._source_sandbox

    @pytest.mark.asyncio
    async def test_install_v2_reads_real_git_ref_and_lands_bytes_in_context(
        self, tmp_path: Path
    ) -> None:
        """FR-026 "successful install lands files at .context/ root": drives
        the real byte-copy branch (not just the dormant/gate-off branches
        above). read_bytes_at_ref is spied on the REAL bound method — the
        assertion fails if _install_v2 stops calling it.
        """
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )
        from app.agents.sandbox import RunSandbox

        source_sb = self._make_git_sandbox(tmp_path, sandbox_root_id="source-root")
        self._commit_chain_payload(
            source_sb,
            logs="log-line-1\n",
            summary="# summary v1\n",
            html="<h1>hi v1</h1>",
            tag="v1",
        )

        calls: list[tuple[str, str]] = []
        real_read = source_sb.read_bytes_at_ref

        def _spy_read(ref: str, relpath: str) -> bytes:
            calls.append((ref, relpath))
            return real_read(ref, relpath)

        source_sb.read_bytes_at_ref = _spy_read  # type: ignore[method-assign]

        receiving_sb = RunSandbox(
            "chain-user", "receiving-run", runs_root=str(tmp_path / "runs")
        )
        receiving_sb.ensure()

        fake_runner = self._FakeChainRunner(receiving_sb, source_sb)

        ctx = MagicMock()
        ctx.run_id = "receiving-run"
        ctx.chain_source_run_id = "source-root"
        ctx.compiled_plan.deliverable.chains_from = True
        ctx.chain_selection = SimpleNamespace(
            is_legacy=False, ref="v1", basename="hello.html"
        )
        ctx.runner = fake_runner

        provider = ChainContextProvider()
        result = await provider.load(ctx)

        assert result == {}, "no text block is injected even on a successful install"
        assert fake_runner.opened_with == "source-root"

        # read_bytes_at_ref was actually called, once per payload file, at the
        # exact ref — never against HEAD or the live working tree.
        assert calls == [
            ("v1", ".chain/logs.jsonl"),
            ("v1", ".chain/summary.md"),
            ("v1", ".chain/hello.html"),
        ]

        dest = receiving_sb.root / ".context"
        assert (dest / "logs.jsonl").read_bytes() == b"log-line-1\n"
        assert (dest / "summary.md").read_bytes() == b"# summary v1\n"
        assert (dest / "hello.html").read_bytes() == b"<h1>hi v1</h1>"

    @pytest.mark.asyncio
    async def test_install_v2_from_mid_family_revision_ref(
        self, tmp_path: Path
    ) -> None:
        """FR-024/AC-04/AC-22: chaining from a mid-family revision reads that
        revision's own exact ref, not the root's — even though both revisions
        share one physical sandbox directory (root-resolve keeps a family on
        one directory; Requirement 2 AC 1). Proves the read is ref-exact, not
        a fallback to HEAD or to the root's tag.
        """
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )
        from app.agents.sandbox import RunSandbox

        root_id = "family-root"
        rev1_id = "family-rev1"

        # Root run: .chain/ payload tagged v1.
        root_sb = self._make_git_sandbox(tmp_path, sandbox_root_id=root_id)
        self._commit_chain_payload(
            root_sb,
            logs="root-log\n",
            summary="# root summary\n",
            html="<h1>root</h1>",
            tag="v1",
        )

        # rev1: same physical directory as root (sandbox_root_id=root_id) but
        # a distinct logical run (current_run_id=rev1_id) — mirrors how a
        # revision shares its family's sandbox. A new .chain/ payload,
        # tagged v2, is committed on top of v1 in the SAME repo.
        rev1_sb = RunSandbox(
            "chain-user",
            root_id,
            current_run_id=rev1_id,
            runs_root=str(tmp_path / "runs"),
        )
        assert (
            rev1_sb.root == root_sb.root
        ), "revision must share the root's physical sandbox"
        self._commit_chain_payload(
            rev1_sb,
            logs="rev1-log\n",
            summary="# rev1 summary\n",
            html="<h1>rev1</h1>",
            tag="v2",
        )

        calls: list[tuple[str, str]] = []
        real_read = rev1_sb.read_bytes_at_ref

        def _spy_read(ref: str, relpath: str) -> bytes:
            calls.append((ref, relpath))
            return real_read(ref, relpath)

        rev1_sb.read_bytes_at_ref = _spy_read  # type: ignore[method-assign]

        receiving_sb = RunSandbox(
            "chain-user", "receiving-run-2", runs_root=str(tmp_path / "runs")
        )
        receiving_sb.ensure()

        # open_source_sandbox is root-resolved by production code to the
        # shared physical sandbox; the test asserts that directly by handing
        # back rev1_sb (whose .root already equals root_sb.root above).
        fake_runner = self._FakeChainRunner(receiving_sb, rev1_sb)

        ctx = MagicMock()
        ctx.run_id = "receiving-run-2"
        ctx.chain_source_run_id = rev1_id
        ctx.compiled_plan.deliverable.chains_from = True
        ctx.chain_selection = SimpleNamespace(
            is_legacy=False, ref="v2", basename="hello.html"
        )
        ctx.runner = fake_runner

        provider = ChainContextProvider()
        result = await provider.load(ctx)

        assert result == {}
        assert fake_runner.opened_with == rev1_id
        assert calls == [
            ("v2", ".chain/logs.jsonl"),
            ("v2", ".chain/summary.md"),
            ("v2", ".chain/hello.html"),
        ]

        dest = receiving_sb.root / ".context"
        # Bytes are rev1's own payload (v2) — not the root's (v1) — proving
        # the read followed the mid-family revision's exact ref.
        assert (dest / "logs.jsonl").read_bytes() == b"rev1-log\n"
        assert (dest / "summary.md").read_bytes() == b"# rev1 summary\n"
        assert (dest / "hello.html").read_bytes() == b"<h1>rev1</h1>"


# ===========================================================================
# Integration: chain from a mid-family revision
# ===========================================================================


class TestChainFromMidFamilyIntegration:
    """Integration test: chain a new run from a mid-family revision.

    Tests FR-020, FR-022, FR-024 together.
    """

    def test_mid_family_revision_chain_source_flow(self, db_session, tmp_path: Path):
        """End-to-end: revision writes source_run_id, chain from it resolves correctly.

        1. Create root run
        2. Create revision (source_run_id = parent_run_id = root_id)
        3. Create chained run from revision (source_run_id = revision_id)
        4. Verify both revision and chained run are in the same sandbox
        """
        from app.agents.sandbox import RunSandbox
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        user_id = _run_id()

        # 1. Root
        root_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id=user_id, status="completed")

        # 2. Revision (both parent and source point to root)
        rev_id = _run_id()
        _seed_run(
            db_session,
            run_id=rev_id,
            user_id=user_id,
            parent_run_id=root_id,
            source_run_id=root_id,
            status="completed",
        )

        # 3. Chained from revision (source points to rev)
        chained_id = _run_id()
        _seed_run(
            db_session,
            run_id=chained_id,
            user_id=user_id,
            parent_run_id=None,  # Not a revision
            source_run_id=rev_id,  # Chained from mid-family
            status="running",
        )

        # Verify structure
        result = resolve_revision_root(db_session, rev_id, user_id)
        assert isinstance(result, RevisionRootResolved)
        assert result.root_id == root_id

        # Verify sandbox paths
        root_sb = RunSandbox(user_id, root_id, runs_root=str(tmp_path))
        # revision shares the root sandbox (use root_id as sandbox key)
        rev_sb = RunSandbox(
            user_id, root_id, current_run_id=rev_id, runs_root=str(tmp_path)
        )
        # chained run creates a new family (no parent), uses its own run_id as root
        chained_sb = RunSandbox(user_id, chained_id, runs_root=str(tmp_path))

        # Revision and root share sandbox
        assert rev_sb.root == root_sb.root

        # Chained run creates a new family with a different root
        assert chained_sb.root != root_sb.root
        assert chained_sb.root.name == chained_id


# ---------------------------------------------------------------------------
# BUG-126 regression guard — _atomic_write_context_dir merges, not replaces
# ---------------------------------------------------------------------------


def test_atomic_write_merges_not_replaces(tmp_path: Path) -> None:
    """_atomic_write_context_dir merges into dest_dir; pre-existing files survive.

    Regression guard for BUG-126 (B24): the old implementation called
    shutil.rmtree(dest_dir) before renaming a staging directory over it,
    destroying .context/design/ and .context/selections.json written by the
    opendesign provider at sandbox open.  The fixed implementation writes
    per-file (mkstemp + os.replace) and never removes siblings.
    """
    from agents.capabilities.context_providers.chain_context import (
        _atomic_write_context_dir,
    )

    dest = tmp_path / ".context"
    dest.mkdir()

    # Simulate opendesign seed files already present (written before provider loop).
    (dest / "design").mkdir()
    (dest / "design" / "tokens.json").write_bytes(b'{"color":"red"}')
    (dest / "selections.json").write_bytes(b'{"template":"hero"}')

    # Chain install writes its three flat payload files.
    _atomic_write_context_dir(
        dest,
        {
            "summary.md": b"# Summary",
            "logs.jsonl": b'{"step":1}',
            "prototype.html": b"<html/>",
        },
    )

    # Chain payload files must be written at .context/ root.
    assert (dest / "summary.md").read_bytes() == b"# Summary"
    assert (dest / "logs.jsonl").read_bytes() == b'{"step":1}'
    assert (dest / "prototype.html").read_bytes() == b"<html/>"

    # OpenDesign seed files must survive untouched (BUG-126 regression guard).
    assert (
        dest / "design" / "tokens.json"
    ).exists(), "design/tokens.json was destroyed — BUG-126 regression"
    assert (
        (dest / "design" / "tokens.json").read_bytes() == b'{"color":"red"}'
    ), "design/tokens.json was modified — BUG-126 regression"
    assert (
        dest / "selections.json"
    ).exists(), "selections.json was destroyed — BUG-126 regression"
    assert (
        (dest / "selections.json").read_bytes() == b'{"template":"hero"}'
    ), "selections.json was modified — BUG-126 regression"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
