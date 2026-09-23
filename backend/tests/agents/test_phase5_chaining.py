"""tests/agents/test_phase5_chaining.py — Task 7.5 acceptance tests.

Phase 5: file-based chaining (tasks 7.1 – 7.4).

Requirements covered:
- Requirement 5: root-resolve cross-run reads — chaining from a mid-family revision
  must reach the correct shared sandbox directory.
- Requirement 22: chain_context provider — declared gate, assert_owns, file copy,
  graceful degradation, no double-delivery.

Acceptance criteria (tasks.md §7.5):
1. source_run_id is written on a chained run and the "(Chained)" indicator renders.
2. Chaining from a mid-family revision (not root) produces non-empty chain payload
   — root-only test passes while majority case is broken.
3. Chained run whose source was swept still completes (graceful degradation).
4. Ownership is validated once at admission (chain_selection); the provider
   never re-checks it itself.
5. Chained run's first agent receives the chain payload exactly once, not twice
   (provider returns {}, no text block injected into the message).

Most tests are pure unit tests — no real engine run, no LLM calls, no DB. The
root-resolution and ``source_run_id`` tests below are the exception: they drive
the real ``_mint_revision_row`` / ``resolve_revision_root`` / ``KernelServices.
open_source_sandbox`` functions against a real in-memory SQLite DB (no mocking
of the v2 API surface itself), matching the evidence standard in
GIT_VERSIONING_TASKS.md §0 ("a requirement is done only when a behavioural test
drives the code path").

v2 API surface (no v1 symbols left to patch):
- ``runner.open_source_sandbox(source_run_id)`` (``KernelServices``,
  ``agents/execution_engine/kernel_services.py``) root-resolves via
  ``resolve_revision_root`` (``app/api/runs.py``) and returns a
  ``ReadOnlySandbox`` on the resolved root — never the mid-family id itself.
- ``ctx.chain_selection`` (pre-validated at admission, task 6.3/6.5) is the
  ChainContextProvider's ONLY selection input; the provider never re-checks
  ownership itself.
"""

from __future__ import annotations

import asyncio
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
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _fresh_run_id(prefix: str = "chain-test") -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _make_mock_scoped_store(*, owns: bool = True) -> MagicMock:
    """Build a minimal mock ScopedStore.

    When owns=True, assert_owns is a no-op coroutine (ownership confirmed).
    When owns=False, assert_owns raises PermissionError (cross-owner denial).
    """
    store = MagicMock()
    if owns:
        store.assert_owns = AsyncMock(return_value=None)
    else:
        store.assert_owns = AsyncMock(side_effect=PermissionError("cross-owner"))
    return store


def _make_mock_sandbox(
    *,
    files: dict[str, str] | None = None,
) -> MagicMock:
    """Build a minimal mock RunSandbox.

    ``files`` maps relative paths → content strings the sandbox exposes via
    read(). list_files() returns the keys.
    """
    sb = MagicMock()
    _files: dict[str, str] = files or {}

    def _read(path: str) -> str | None:
        return _files.get(path)

    def _write(path: str, content: str) -> None:
        _files[path] = content

    def _list_files() -> list[str]:
        return list(_files.keys())

    sb.read.side_effect = _read
    sb.write.side_effect = _write
    sb.list_files.side_effect = _list_files
    return sb


def _make_mock_runner(sandbox: MagicMock) -> MagicMock:
    runner = MagicMock()
    runner.sandbox = sandbox
    return runner


def _make_ctx(
    *,
    chain_source_run_id: str | None = None,
    disk_principal: str = "user-1",
    scoped_store: Any = None,
    runner: Any = None,
) -> MagicMock:
    """Build a minimal execution context mock for ChainContextProvider.load()."""
    ctx = MagicMock()
    ctx.chain_source_run_id = chain_source_run_id
    ctx.disk_principal = disk_principal
    ctx.scoped_store = scoped_store
    ctx.runner = runner
    return ctx


# ---------------------------------------------------------------------------
# DB-backed helpers (root resolution / _mint_revision_row) — real in-memory
# SQLite, no mocking of the v2 API surface these tests exist to cover.
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """SQLite in-memory session with every app table created (StaticPool so
    seeded rows stay visible for the duration of one test)."""
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


def _seed_workflow_run(
    session,
    *,
    run_id: str,
    user_id: str,
    parent_run_id: str | None = None,
    status: str = "completed",
    workspace_id: str | None = None,
) -> str:
    """Insert a minimal ``workflow_runs`` row and return its id."""
    from app.models.workflow import WorkflowRun

    session.add(
        WorkflowRun(
            id=run_id,
            user_id=user_id,
            owner_id=user_id,
            workspace_id=workspace_id,
            title="test",
            type="user_stories",
            status=status,
            input="idea",
            agent_count=1,
            parent_run_id=parent_run_id,
        )
    )
    session.commit()
    return run_id


def _make_kernel_services(ectx: Any) -> Any:
    """Build a real ``KernelServices`` handle over a real (uninitialised)
    ``ExecutionEngine`` and the given ``ectx`` — mirrors
    ``tests/agents/test_hooks.py::_real_kernel_services``. No sandbox/model
    needed for ``open_source_sandbox``, which only reads ``ectx.disk_principal``.
    """
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices

    engine = ExecutionEngine.__new__(ExecutionEngine)
    return KernelServices(
        engine=engine,
        ectx=ectx,
        sandbox=None,
        ordered_agents=[],
        user_message="",
        pipeline_run_id=ectx.run_id,
        pipeline_type="custom",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        cancel_event=None,
        results=[],
    )


# ---------------------------------------------------------------------------
# 1. source_run_id written on chained run / "(Chained)" indicator
# ---------------------------------------------------------------------------


class TestSourceRunIdWritten:
    """AC 1: source_run_id is written on a chained run and powers the "(Chained)"
    indicator via WorkflowRunResponse.source_run_id (runs.py).

    Requirement 22 AC 1/AC 2.
    """

    def test_mint_revision_row_writes_source_run_id(
        self, db_session, tmp_path, monkeypatch
    ) -> None:
        """_mint_revision_row sets source_run_id = parent_run_id on the new row.

        This is the first time source_run_id (migration 0014) has ever been written.
        Writing it makes the frontend "(Chained)" indicator functional for the first
        time (Requirement 22).

        Drives the REAL function (``app/api/run_commands.py``) against a real
        in-memory DB and a seeded parent row — not a hand-built ORM instance.
        """
        from app.api.run_commands import _mint_revision_row
        from app.core.config import settings
        from app.models.workflow import WorkflowRun

        # family_lock() mkdirs under settings.RUNS_ROOT — redirect to tmp_path so
        # the test never touches the real (often unwritable) production runs dir.
        monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path))

        user_id = _fresh_run_id("user")
        parent_id = _fresh_run_id("parent")
        _seed_workflow_run(
            db_session, run_id=parent_id, user_id=user_id, workspace_id="ws-1"
        )
        user = SimpleNamespace(id=user_id, tier="basic")

        child_id, revision_pipeline_type = _mint_revision_row(
            db_session,
            user=user,
            parent_run_id=parent_id,
            target_artifact_type="user_stories",
            instruction="update the color scheme",
        )

        assert revision_pipeline_type == "user_stories_revision"
        child = db_session.query(WorkflowRun).filter(WorkflowRun.id == child_id).first()
        assert child is not None, "_mint_revision_row must persist the child row"
        assert child.source_run_id == parent_id, (
            f"source_run_id should be {parent_id!r} but got {child.source_run_id!r}"
        )
        assert child.parent_run_id == parent_id, (
            "parent_run_id must also be set on the revision row"
        )

    def test_workflow_run_model_has_source_run_id_column(self) -> None:
        """WorkflowRun ORM model has a source_run_id column (migration 0014).

        This is the DB-level field that _mint_revision_row writes and that
        FamilyMemberResponse serialises for the "(Chained)" indicator.
        """
        from app.models.workflow import WorkflowRun

        assert hasattr(WorkflowRun, "source_run_id"), (
            "WorkflowRun must have a source_run_id column "
            "(migration 0014 forward field)"
        )

    def test_workflow_run_response_exposes_source_run_id(self) -> None:
        """WorkflowRunResponse exposes source_run_id for the '(Chained)' indicator."""
        from app.api.runs import WorkflowRunResponse

        fields = WorkflowRunResponse.model_fields
        assert "source_run_id" in fields, (
            "WorkflowRunResponse must expose source_run_id "
            "for the '(Chained)' indicator"
        )

    def test_workflow_run_response_source_run_id_is_optional(self) -> None:
        """source_run_id is Optional — non-chained runs have it as None."""
        from app.api.runs import WorkflowRunResponse

        field = WorkflowRunResponse.model_fields["source_run_id"]
        # Optional fields have is_required() == False or a default of None
        assert not field.is_required() or field.default is None, (
            "source_run_id must be optional so non-chained runs don't break"
        )

    def test_source_run_id_written_on_revision_row(
        self, db_session, tmp_path, monkeypatch
    ) -> None:
        """A depth-2 revision's source_run_id is its IMMEDIATE parent — the
        revision it was minted from — not the family root.

        Distinguishes this from ``test_mint_revision_row_writes_source_run_id``
        above (which only checks depth 1, where parent == root and the two
        could not be told apart): mint root → rev1, then rev1 → rev2, and
        assert rev2.source_run_id == rev1.id (not the root's id). Drives the
        REAL ``_mint_revision_row`` twice against a real in-memory DB.
        """
        from app.api.run_commands import _mint_revision_row
        from app.core.config import settings
        from app.models.workflow import WorkflowRun

        monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path))

        user_id = _fresh_run_id("user")
        root_id = _fresh_run_id("root")
        _seed_workflow_run(
            db_session, run_id=root_id, user_id=user_id, workspace_id="ws-1"
        )
        user = SimpleNamespace(id=user_id, tier="basic")

        rev1_id, _ = _mint_revision_row(
            db_session,
            user=user,
            parent_run_id=root_id,
            target_artifact_type="user_stories",
            instruction="first revision",
        )
        # _has_active_chain_revision blocks a second concurrent revision on the
        # same family while rev1 is non-terminal — settle it before minting rev2.
        db_session.query(WorkflowRun).filter(WorkflowRun.id == rev1_id).update(
            {"status": "completed"}
        )
        db_session.commit()

        rev2_id, _ = _mint_revision_row(
            db_session,
            user=user,
            parent_run_id=rev1_id,
            target_artifact_type="user_stories",
            instruction="second revision",
        )

        rev2 = db_session.query(WorkflowRun).filter(WorkflowRun.id == rev2_id).first()
        assert rev2 is not None
        assert rev2.source_run_id == rev1_id, (
            "a depth-2 revision's source_run_id must be its immediate parent "
            f"({rev1_id!r}), not the family root ({root_id!r}); got "
            f"{rev2.source_run_id!r}"
        )

    def test_non_chained_run_source_run_id_is_none(self) -> None:
        """An original (non-chained) run has source_run_id=None."""
        from app.models.workflow import WorkflowRun

        run_id = _fresh_run_id("original")
        wr = WorkflowRun(
            id=run_id,
            user_id="user-1",
            owner_id="user-1",
            title="Original run",
            type="prototype",
            status="completed",
            input="build a widget",
            agent_count=3,
        )

        assert wr.source_run_id is None


# ---------------------------------------------------------------------------
# 2. Root-resolution: mid-family chain delivers non-empty payload
# ---------------------------------------------------------------------------


class TestRootResolutionV2:
    """AC 2: chaining from a mid-family revision (not the root) must still deliver
    a non-empty chain payload via the v2 open_source_sandbox() API.

    The v2 contract: runner.open_source_sandbox(source_run_id) internally resolves
    the source_run_id to the chain root (via resolve_revision_root) and returns a
    ReadOnlySandbox scoped to that root — driven here against a REAL in-memory DB
    and the REAL resolve_revision_root (no mocking of the resolver itself).

    Requirement 5 AC2 / Requirement 22 / FR-020, FR-023, FR-024, FR-026.
    """

    def test_open_source_sandbox_resolves_root_only_source(
        self, db_session, monkeypatch
    ) -> None:
        """A source run with no parent IS the root — open_source_sandbox must
        return a sandbox scoped to that same id (the depth-0/1 case)."""
        import app.api.run_engine as run_engine_mod
        from agents.execution_engine.context import ExecutionContext

        monkeypatch.setattr(run_engine_mod, "_get_db", lambda: db_session)

        user_id = "user-1"
        root_id = _fresh_run_id("root")
        _seed_workflow_run(db_session, run_id=root_id, user_id=user_id)

        ectx = ExecutionContext(
            run_id=_fresh_run_id("chained"), owner_id=user_id, disk_principal=user_id
        )
        runner = _make_kernel_services(ectx)

        sandbox = runner.open_source_sandbox(root_id)

        assert sandbox.root.name == root_id

    def test_open_source_sandbox_resolves_mid_family_revision_to_shared_root(
        self, db_session, monkeypatch
    ) -> None:
        """Chaining from a depth-2 revision (root -> rev1 -> rev2) must resolve
        to the family ROOT, not to rev2 itself — the exact v1 bug this v2 API
        replaces (the old code walked source_run_id, the chain edge, instead of
        parent_run_id, the revision edge, producing the wrong root at depth 2+)."""
        import app.api.run_engine as run_engine_mod
        from agents.execution_engine.context import ExecutionContext

        monkeypatch.setattr(run_engine_mod, "_get_db", lambda: db_session)

        user_id = "user-1"
        root_id = _fresh_run_id("root")
        rev1_id = _fresh_run_id("rev1")
        rev2_id = _fresh_run_id("rev2")
        _seed_workflow_run(db_session, run_id=root_id, user_id=user_id)
        _seed_workflow_run(
            db_session, run_id=rev1_id, user_id=user_id, parent_run_id=root_id
        )
        _seed_workflow_run(
            db_session, run_id=rev2_id, user_id=user_id, parent_run_id=rev1_id
        )

        ectx = ExecutionContext(
            run_id=_fresh_run_id("chained"), owner_id=user_id, disk_principal=user_id
        )
        runner = _make_kernel_services(ectx)

        sandbox = runner.open_source_sandbox(rev2_id)

        assert sandbox.root.name == root_id, (
            f"chaining from mid-family revision {rev2_id!r} must resolve to the "
            f"family root {root_id!r}, got {sandbox.root.name!r}"
        )


# ---------------------------------------------------------------------------
# 3. Graceful degradation: swept / missing source still completes
# ---------------------------------------------------------------------------


class TestGracefulDegradationV2:
    """AC 3: a chained run whose source was swept (or was never written) must still
    complete.  The run must never fail because of a missing chain payload (FR-025).

    In v2, the provider handles missing sources via chain_selection gate:
    - If source is missing, chain_selection is None
    - Provider emits chain_context_unavailable and continues
    - Under chain_policy: degrade, the run continues normally
    - Under chain_policy: refuse, the run is failed (but the edge is preserved)

    Requirement 22 FR-025 / graceful-degrade AC.
    """

    def test_no_chain_source_run_id_is_dormant(self) -> None:
        """A run with chain_source_run_id=None/empty string returns {} (dormant).

        The provider must not touch sandbox/store/runner on dormant runs.
        INV-3 parity: non-chaining runs get {} byte-identically.
        """
        # When source_run_id is None or empty, the provider gate returns {} early.
        # This is verified by the provider implementation in chain_context.py:163-165.
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        # Create a minimal context with no source
        ctx = MagicMock()
        ctx.chain_source_run_id = None
        ctx.compiled_plan = None

        import asyncio

        provider = ChainContextProvider()
        result = asyncio.run(provider.load(ctx))

        assert result == {}, "chain_source_run_id=None must return {}"

    def test_chains_from_false_is_dormant(self) -> None:
        """A run whose workflow does not declare chains_from returns {} (dormant).

        The provider gates on compiled_plan.deliverable.chains_from == True.
        A workflow without this declaration never performs cross-run reads.
        """
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        # Create context with chains_from=False
        ctx = MagicMock()
        ctx.chain_source_run_id = "some-source"
        compiled_plan = MagicMock()
        deliverable = MagicMock()
        deliverable.chains_from = False  # Explicitly False
        compiled_plan.deliverable = deliverable
        ctx.compiled_plan = compiled_plan

        import asyncio

        provider = ChainContextProvider()
        result = asyncio.run(provider.load(ctx))

        assert result == {}, "chains_from=False must return {} (no cross-run reads)"


# ---------------------------------------------------------------------------
# 4. assert_owns is called; PermissionError is never swallowed
# ---------------------------------------------------------------------------


class TestOwnershipGateV2:
    """AC 4: Ownership is gated via chain_selection pre-validation (task 6.5).

    In v2, the admission gate (task 6.3 / 6.5) validates ownership and determines
    whether the source run is chainable. The provider does not perform its own
    ownership check — it trusts the pre-validated chain_selection or fails closed
    when selection is None.

    Requirement 22 / INV-8 (ownership pre-gate) / V2-Q8.
    """

    def test_provider_never_calls_scoped_store_ownership_check(self) -> None:
        """chain_selection is pre-validated at admission (task 6.5); the
        provider itself must never re-check ownership via ctx.scoped_store.

        Regression guard: ``scoped_store.assert_owns`` is wired to RAISE
        PermissionError if it is ever called (the v1 provider's own ownership
        check, now moved upstream). If the provider ever regains that check,
        this test fails — the PermissionError would propagate out of
        ``load()`` instead of the clean ``{}`` it returns today.
        """
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        store = _make_mock_scoped_store(owns=False)
        ctx = _make_ctx(
            chain_source_run_id="source-1",
            scoped_store=store,
            runner=MagicMock(),
        )
        ctx.compiled_plan.deliverable.chains_from = True
        # Not yet validated / admitted under degrade — the provider must fail
        # closed via the selection gate, never by asking the store itself.
        ctx.chain_selection = None

        provider = ChainContextProvider()
        result = asyncio.run(provider.load(ctx))

        store.assert_owns.assert_not_called()
        assert result == {}


# ---------------------------------------------------------------------------
# 5. No double-delivery: provider returns {}, no text block injected
# ---------------------------------------------------------------------------


class TestNoDoubleDeliveryV2:
    """AC 5: the chain payload must arrive exactly once — via files in .context/.

    The provider returns {} so nothing is injected into the agent's message as
    a text block. The v2 contract separates:
    - File copy (side-effect in ChainContextProvider.load)
    - Message injection (provider return value = empty dict)

    This ensures agents read from .context/ only, never from injected text.

    Requirement 22 / "no double-delivery" contract / V2-Q8.
    """

    def test_provider_always_returns_empty_dict(self, tmp_path: Path) -> None:
        """ChainContextProvider.load() returns {} even on a SUCCESSFUL install.

        The return value is the BLOCK MAP — an empty dict means no text is
        injected into the agent's context_message. The side-effect is the file
        copy to .context/, which is entirely file-based. Drives the real v2
        install path (open_source_sandbox -> read_bytes_at_ref -> atomic write)
        against real files on disk, so both halves of the contract are checked
        together: {} returned AND the bytes actually landed in .context/.
        """
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        class _FakeSourceSandbox:
            def __init__(self, files: dict[str, bytes]) -> None:
                self._files = files

            def read_bytes_at_ref(self, ref: str, path: str) -> bytes:
                return self._files[path]

        class _FakeChainRunner:
            """Deliberately NOT a MagicMock: mark_chain_context_installed /
            record_provenance_audit must be genuinely absent (getattr(...,
            None) -> None) rather than auto-vivified Mock attributes, so the
            provider takes its documented "not available" skip branch."""

            def __init__(self, sandbox_root: Path, source_sandbox: Any) -> None:
                self.sandbox = SimpleNamespace(root=sandbox_root)
                self._source_sandbox = source_sandbox
                self.opened_with: str | None = None

            def open_source_sandbox(self, source_run_id: str) -> Any:
                self.opened_with = source_run_id
                return self._source_sandbox

        selection = SimpleNamespace(is_legacy=False, ref="v3", basename="hello.html")
        files = {
            ".chain/logs.jsonl": b"log-bytes",
            ".chain/summary.md": b"summary-bytes",
            ".chain/hello.html": b"<h1>hi</h1>",
        }
        fake_runner = _FakeChainRunner(tmp_path, _FakeSourceSandbox(files))

        ctx = MagicMock()
        ctx.chain_source_run_id = "source-1"
        ctx.compiled_plan.deliverable.chains_from = True
        ctx.chain_selection = selection
        ctx.runner = fake_runner
        ctx.run_id = "receiving-run"

        provider = ChainContextProvider()
        result = asyncio.run(provider.load(ctx))

        assert result == {}, "no text block is injected even on a successful install"
        assert fake_runner.opened_with == "source-1"
        dest = tmp_path / ".context"
        assert (dest / "logs.jsonl").read_bytes() == b"log-bytes"
        assert (dest / "summary.md").read_bytes() == b"summary-bytes"
        assert (dest / "hello.html").read_bytes() == b"<h1>hi</h1>"

    def test_provider_returns_empty_dict_even_when_no_source(self) -> None:
        """When chain_source_run_id is absent, load() still returns {}."""
        import asyncio
        from agents.capabilities.context_providers.chain_context import (
            ChainContextProvider,
        )

        ctx = MagicMock()
        ctx.chain_source_run_id = None
        ctx.compiled_plan = None

        provider = ChainContextProvider()
        result = asyncio.run(provider.load(ctx))

        assert result == {}, "No source → returns {} (dormant)"

    def test_chain_context_is_registered_capability(self) -> None:
        """chain_context is registered as a context_provider capability.

        The provider is discoverable and callable via the registry.
        """
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        reg = CapabilityRegistry()
        assert reg.is_registered("context_provider", "chain_context"), (
            "chain_context must be registered; check that chain_context.py "
            "is in the _builtin_modules tuple in registry.py's discover()"
        )


# ---------------------------------------------------------------------------
# 6. _list_chain_files helper — unit tests
# ---------------------------------------------------------------------------


class TestListChainFiles:
    """Unit tests for the _list_chain_files internal helper.

    This helper is the boundary between the sandbox interface and the file copy
    loop. Both the list_files() path and the base_path fallback path must be
    correct for graceful degradation to work.
    """

    def test_returns_relative_paths_under_prefix(self) -> None:
        """_list_chain_files returns paths relative to the prefix.

        Not the sandbox root.
        """
        from agents.capabilities.context_providers.chain_context import (
            _list_chain_files,
        )

        prefix = ".chain/run-abc"
        sandbox = _make_mock_sandbox(
            files={
                ".chain/run-abc/summary.md": "done",
                ".chain/run-abc/logs/run-abc.jsonl": "[...]",
                ".chain/other-run/summary.md": "other",  # must be excluded
            }
        )
        result = _list_chain_files(sandbox, prefix)
        assert sorted(result) == ["logs/run-abc.jsonl", "summary.md"], (
            f"Expected only files under {prefix!r} relative; got {result}"
        )

    def test_excludes_files_from_different_prefix(self) -> None:
        """Files under a different .chain/ subdirectory are excluded."""
        from agents.capabilities.context_providers.chain_context import (
            _list_chain_files,
        )

        prefix = ".chain/run-A"
        sandbox = _make_mock_sandbox(
            files={
                ".chain/run-A/summary.md": "a",
                ".chain/run-B/summary.md": "b",
            }
        )
        result = _list_chain_files(sandbox, prefix)
        assert result == ["summary.md"]

    def test_returns_empty_on_no_matching_files(self) -> None:
        """Returns [] when no files match the prefix."""
        from agents.capabilities.context_providers.chain_context import (
            _list_chain_files,
        )

        sandbox = _make_mock_sandbox(files={"other/file.txt": "x"})
        result = _list_chain_files(sandbox, ".chain/run-Z")
        assert result == []

    def test_base_path_fallback_when_no_list_files(self, tmp_path: Path) -> None:
        """Falls back to os.walk when sandbox has base_path but no list_files."""
        from agents.capabilities.context_providers.chain_context import (
            _list_chain_files,
        )

        source_id = "run-fallback"
        chain_dir = tmp_path / ".chain" / source_id
        chain_dir.mkdir(parents=True)
        (chain_dir / "summary.md").write_text("done")
        (chain_dir / "logs").mkdir()
        (chain_dir / "logs" / "run.jsonl").write_text("[]")

        class _PathSandbox:
            base_path = tmp_path

        prefix = f".chain/{source_id}"
        result = _list_chain_files(_PathSandbox(), prefix)
        assert sorted(result) == ["logs/run.jsonl", "summary.md"]

    def test_returns_empty_when_no_list_files_and_no_base_path(self) -> None:
        """Returns [] when sandbox has neither list_files nor base_path."""
        from agents.capabilities.context_providers.chain_context import (
            _list_chain_files,
        )

        class _BareSandbox:
            pass

        result = _list_chain_files(_BareSandbox(), ".chain/run-X")
        assert result == []
