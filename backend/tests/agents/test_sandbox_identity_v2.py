"""tests/agents/test_sandbox_identity_v2.py

Behavioral tests for sandbox-git-versioning-v2, task 3.11.

Coverage (Requirements 2, 3, 10):
─────────────────────────────────
1. Identity — two ids, three logs
     Root plus two revisions in one physical sandbox produce three distinct
     ``.logs/{run_id}.jsonl`` files.  A depth-two revision shares its family
     root while a chain from that same revision receives a DIFFERENT sandbox root.

2. resolve_revision_root — failure taxonomy
     Self-parent cycle, two-node cycle, missing ancestor, cross-owner ancestry,
     and a null principal each produce ``RevisionRootUnresolved``.
     Each failure case has the expected ``reason`` string.
     The resolver NEVER falls back to the requested run id, NEVER selects the
     last unique node in a cycle, NEVER returns a partial root.

3. TTL sweep — protected-set contract
     An active descendant protects the family sandbox directory from sweeping.
     A gate-paused (non-terminal) descendant past the sandbox TTL is also
     protected — a durable pause is NOT treated as inactivity.
     A fully terminal and expired family IS swept.
     A resolver failure protects (fail closed — never delete on ambiguity).

4. Admission atomicity — concurrent revision launches
     Two concurrent revision launches against the same family root are
     serialized by the family lock; both cannot succeed simultaneously.

5. Lock order — family lock before manifest lock
     The documented lock order (family lock first, then the per-sandbox manifest
     lock) is the only safe ordering; the reverse deadlocks.

All tests use only SQLite in-memory (via SQLAlchemy) or the real filesystem in
``tmp_path``.  No LLM calls, no Docker, no network.

Requirements: 2, 3, 10
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Path setup — make ``backend/`` importable
# ---------------------------------------------------------------------------

import sys

_BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Shared in-memory DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """SQLite in-memory session with ``workflow_runs`` created.

    Uses StaticPool so the seeded rows are visible inside the same test.
    """
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
    status: str = "running",
) -> str:
    """Insert a minimal ``workflow_runs`` row and return its id."""
    from app.models.workflow import WorkflowRun

    row = WorkflowRun(
        id=run_id,
        user_id=user_id,
        title="test",
        type="prototype",
        status=status,
        input="idea",
        parent_run_id=parent_run_id,
        source_run_id=source_run_id,
    )
    session.add(row)
    session.commit()
    return run_id


# ===========================================================================
# 1. Identity — RunSandbox two-id split  (Requirement 3)
# ===========================================================================


class TestRunSandboxTwoIdSplit:
    """Verify that RunSandbox correctly separates sandbox_root_id (directory key)
    from current_run_id (per-run path key), so revisions in a shared sandbox do
    NOT clobber each other's ``.logs/``, ``.verify/``, or ``.browser/`` paths.

    Requirements: 3 AC 1–4
    """

    def test_root_run_log_path_is_under_sandbox_root_dir(self, tmp_path: Path) -> None:
        """A root run's log path embeds the sandbox root id in its filename."""
        from app.agents.sandbox import RunSandbox

        root_id = "root-run-aaa"
        sb = RunSandbox("user1", root_id, runs_root=str(tmp_path))

        # Physical directory is keyed on sandbox_root_id.
        assert sb.root == (tmp_path / "user1" / root_id).resolve()
        # Log path is .logs/{current_run_id}.jsonl — for a root run both ids
        # are the same.
        assert sb.run_log_path == sb.root / ".logs" / f"{root_id}.jsonl"

    def test_revision_log_path_uses_current_run_id(self, tmp_path: Path) -> None:
        """A revision sandbox produces a log path that contains current_run_id,
        NOT sandbox_root_id — fixes D2 (Requirement 3 AC 3)."""
        from app.agents.sandbox import RunSandbox

        root_id = "root-run-bbb"
        rev_id = "revision-run-ccc"
        sb = RunSandbox(
            "user1",
            root_id,
            current_run_id=rev_id,
            runs_root=str(tmp_path),
        )

        # Physical directory is still keyed on sandbox_root_id.
        assert sb.root == (tmp_path / "user1" / root_id).resolve()
        # Log path uses current_run_id.
        assert sb.run_log_path.name == f"{rev_id}.jsonl"
        assert root_id not in sb.run_log_path.name, (
            "run_log_path filename must use current_run_id, not sandbox_root_id"
        )

    def test_revision_verify_dir_uses_current_run_id(self, tmp_path: Path) -> None:
        """verify_dir must embed current_run_id (Requirement 3 AC 4)."""
        from app.agents.sandbox import RunSandbox

        root_id = "root-run-ddd"
        rev_id = "revision-run-eee"
        sb = RunSandbox(
            "user1",
            root_id,
            current_run_id=rev_id,
            runs_root=str(tmp_path),
        )

        assert sb.verify_dir.name == rev_id
        assert sb.verify_dir.parent == sb.root / ".verify"

    def test_revision_browser_dir_uses_current_run_id(self, tmp_path: Path) -> None:
        """browser_dir must embed current_run_id (Requirement 3 AC 4)."""
        from app.agents.sandbox import RunSandbox

        root_id = "root-run-fff"
        rev_id = "revision-run-ggg"
        sb = RunSandbox(
            "user1",
            root_id,
            current_run_id=rev_id,
            runs_root=str(tmp_path),
        )

        assert sb.browser_dir.name == rev_id
        assert sb.browser_dir.parent == sb.root / ".browser"

    def test_root_plus_two_revisions_produce_three_distinct_log_paths(
        self, tmp_path: Path
    ) -> None:
        """Root + 2 revisions all share one physical sandbox dir but each writes to a
        distinct ``.logs/{run_id}.jsonl`` path (Requirement 3 AC 7–8)."""
        from app.agents.sandbox import RunSandbox

        root_id = "root-000"
        rev1_id = "revision-001"
        rev2_id = "revision-002"

        root_sb = RunSandbox("user1", root_id, runs_root=str(tmp_path))
        rev1_sb = RunSandbox(
            "user1", root_id, current_run_id=rev1_id, runs_root=str(tmp_path)
        )
        rev2_sb = RunSandbox(
            "user1", root_id, current_run_id=rev2_id, runs_root=str(tmp_path)
        )

        # All three share the SAME physical directory.
        assert root_sb.root == rev1_sb.root == rev2_sb.root

        # But each has its own log path.
        log_paths = {
            root_sb.run_log_path,
            rev1_sb.run_log_path,
            rev2_sb.run_log_path,
        }
        assert len(log_paths) == 3, (
            "Root and two revisions must produce 3 distinct log paths; "
            f"got {log_paths}"
        )

        # Each log path is under the shared sandbox root.
        for lp in log_paths:
            assert lp.parent == root_sb.root / ".logs"

    def test_current_run_id_attribute_reflects_logical_run(
        self, tmp_path: Path
    ) -> None:
        """sandbox.run_id must expose current_run_id (the logical run), not
        sandbox_root_id, so callers such as AgentContext get the right id.
        (Requirement 3 AC 1: RunSandbox carries BOTH ids.  V2-Q4.)"""
        from app.agents.sandbox import RunSandbox

        root_id = "root-hhh"
        rev_id = "revision-iii"
        sb = RunSandbox(
            "user1", root_id, current_run_id=rev_id, runs_root=str(tmp_path)
        )

        # run_id is the backward-compat alias for the CURRENT (logical) run id.
        assert sb.run_id == rev_id
        assert sb.current_run_id == rev_id
        assert sb.sandbox_root_id == root_id


# ===========================================================================
# 2. resolve_revision_root — failure taxonomy  (Requirement 2)
# ===========================================================================


class TestResolveRevisionRoot:
    """Exercises every success and failure branch of resolve_revision_root.

    Requirements: 2 AC 1–12
    """

    def test_standalone_run_resolves_to_itself(self, db_session) -> None:
        """A run with no parent resolves to itself — it IS the revision root."""
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        run_id = _run_id()
        _seed_run(db_session, run_id=run_id, user_id="alice")

        result = resolve_revision_root(db_session, run_id, "alice")

        assert isinstance(result, RevisionRootResolved)
        assert result.root_id == run_id

    def test_single_hop_parent_resolves_to_root(self, db_session) -> None:
        """A revision whose parent has no grandparent resolves to the parent (root)."""
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        root_id = _run_id()
        rev_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id="alice")
        _seed_run(
            db_session, run_id=rev_id, user_id="alice", parent_run_id=root_id
        )

        result = resolve_revision_root(db_session, rev_id, "alice")

        assert isinstance(result, RevisionRootResolved)
        assert result.root_id == root_id

    def test_depth_two_revision_shares_family_root(self, db_session) -> None:
        """A depth-two revision (C → B → A) shares the same root as B.

        Requirement 2 AC 9: a depth-two revision shares its family root.
        """
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        root_id = _run_id()
        rev1_id = _run_id()
        rev2_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id="alice")
        _seed_run(
            db_session, run_id=rev1_id, user_id="alice", parent_run_id=root_id
        )
        _seed_run(
            db_session, run_id=rev2_id, user_id="alice", parent_run_id=rev1_id
        )

        result_rev1 = resolve_revision_root(db_session, rev1_id, "alice")
        result_rev2 = resolve_revision_root(db_session, rev2_id, "alice")

        assert isinstance(result_rev1, RevisionRootResolved)
        assert isinstance(result_rev2, RevisionRootResolved)
        # Both revisions must share the same root.
        assert result_rev1.root_id == root_id
        assert result_rev2.root_id == root_id

    def test_chain_from_depth_two_revision_is_different_root(
        self, db_session
    ) -> None:
        """A chained workflow from a depth-two revision receives a DIFFERENT root.

        V2-Q1 / Requirement 2 AC 2–3: source_run_id is NEVER followed when
        resolving the physical sandbox.  A chained workflow always starts a new
        sandbox, keyed on its OWN run id (since it has no parent_run_id).

        Requirement 2 AC 9: the chained run must have a different root than
        the source's revision family.
        """
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        # Revision family: root → rev1 → rev2
        root_id = _run_id()
        rev1_id = _run_id()
        rev2_id = _run_id()
        _seed_run(db_session, run_id=root_id, user_id="alice")
        _seed_run(
            db_session, run_id=rev1_id, user_id="alice", parent_run_id=root_id
        )
        _seed_run(
            db_session, run_id=rev2_id, user_id="alice", parent_run_id=rev1_id
        )

        # A chained workflow from rev2 — has source_run_id=rev2, NO parent_run_id.
        chain_id = _run_id()
        _seed_run(
            db_session,
            run_id=chain_id,
            user_id="alice",
            source_run_id=rev2_id,
            parent_run_id=None,  # explicitly no parent
        )

        # Resolve the chained run.
        chain_result = resolve_revision_root(db_session, chain_id, "alice")
        assert isinstance(chain_result, RevisionRootResolved)

        # The chained run resolves to ITSELF (it is its own root — no parent chain).
        assert chain_result.root_id == chain_id, (
            "A chained workflow with no parent_run_id must resolve to itself; "
            f"expected {chain_id!r}, got {chain_result.root_id!r}"
        )

        # The chained run's root is DIFFERENT from the revision family's root.
        assert chain_result.root_id != root_id, (
            "A chained workflow must have a DIFFERENT sandbox root from the "
            "source's revision family (V2-Q1)"
        )

    def test_resolver_walks_parent_run_id_not_source_run_id(
        self, db_session
    ) -> None:
        """Regression guard: if source_run_id is set, the resolver must NOT follow
        it when computing the revision root.  Only parent_run_id is the walk edge.
        (V2-Q1 / Requirement 2 AC 2)"""
        from app.api.runs import RevisionRootResolved, resolve_revision_root

        # Two completely separate root runs (different users would be the extreme
        # case, but here same user).
        source_root_id = _run_id()
        my_root_id = _run_id()
        _seed_run(db_session, run_id=source_root_id, user_id="alice")
        _seed_run(db_session, run_id=my_root_id, user_id="alice")

        # A run that chains FROM source_root_id but has parent_run_id=my_root_id.
        chained_rev_id = _run_id()
        _seed_run(
            db_session,
            run_id=chained_rev_id,
            user_id="alice",
            parent_run_id=my_root_id,   # the real parent / physical sandbox key
            source_run_id=source_root_id,  # the chain source — must be ignored
        )

        result = resolve_revision_root(db_session, chained_rev_id, "alice")

        assert isinstance(result, RevisionRootResolved)
        # Must follow parent_run_id to my_root_id, NOT source_run_id to source_root_id.
        assert result.root_id == my_root_id, (
            "Resolver must walk parent_run_id only; source_run_id must never "
            "influence sandbox identity (V2-Q1)"
        )

    # ------------------------------------------------------------------
    # Failure cases — all must produce RevisionRootUnresolved
    # ------------------------------------------------------------------

    def test_null_principal_is_refused(self, db_session) -> None:
        """A null or empty user_id must be refused before any DB query.
        Requirement 2 AC 4: owner-scoped by non-null user_id."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root

        run_id = _run_id()
        _seed_run(db_session, run_id=run_id, user_id="alice")

        for empty in ("", None):
            result = resolve_revision_root(db_session, run_id, empty)  # type: ignore[arg-type]
            assert isinstance(result, RevisionRootUnresolved), (
                f"Empty principal {empty!r} must produce RevisionRootUnresolved"
            )
            assert result.reason == "null_principal"

    def test_self_parent_cycle_produces_unresolved(self, db_session) -> None:
        """A run whose parent_run_id points to itself (self-cycle) must fail closed.
        Requirement 2 AC 10: NEVER select the last unique node on a cycle."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root
        from app.models.workflow import WorkflowRun

        run_id = _run_id()
        # Insert the row first without a parent, then update to create the cycle.
        _seed_run(db_session, run_id=run_id, user_id="alice")
        db_session.query(WorkflowRun).filter(
            WorkflowRun.id == run_id
        ).update({"parent_run_id": run_id})
        db_session.commit()

        result = resolve_revision_root(db_session, run_id, "alice")

        assert isinstance(result, RevisionRootUnresolved), (
            "A self-parent cycle must produce RevisionRootUnresolved"
        )
        assert result.reason == "cycle"
        assert result.repeated_node == run_id

    def test_two_node_cycle_produces_unresolved(self, db_session) -> None:
        """A ↔ B cycle: resolver must fail closed with reason='cycle'.
        Requirement 2 AC 10–12."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root
        from app.models.workflow import WorkflowRun

        run_a = _run_id()
        run_b = _run_id()

        # Seed A with B as parent, B with A as parent.
        _seed_run(db_session, run_id=run_a, user_id="alice")
        _seed_run(db_session, run_id=run_b, user_id="alice")
        db_session.query(WorkflowRun).filter(
            WorkflowRun.id == run_a
        ).update({"parent_run_id": run_b})
        db_session.query(WorkflowRun).filter(
            WorkflowRun.id == run_b
        ).update({"parent_run_id": run_a})
        db_session.commit()

        result = resolve_revision_root(db_session, run_a, "alice")

        assert isinstance(result, RevisionRootUnresolved)
        assert result.reason == "cycle"
        # repeated_node is the node that closed the loop.
        assert result.repeated_node in (run_a, run_b), (
            f"repeated_node must be one of the two cycle members; "
            f"got {result.repeated_node!r}"
        )
        # visited_count must be at least 1 (we entered at least one node).
        assert result.visited_count >= 1

    def test_missing_ancestor_produces_unresolved(self, db_session) -> None:
        """If the parent row does not exist, fail closed.
        Requirement 2 AC 5, AC 10–11."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root

        dangling_parent_id = _run_id()  # never inserted
        run_id = _run_id()
        _seed_run(
            db_session,
            run_id=run_id,
            user_id="alice",
            parent_run_id=dangling_parent_id,
        )

        result = resolve_revision_root(db_session, run_id, "alice")

        assert isinstance(result, RevisionRootUnresolved)
        assert result.reason == "missing_or_cross_owner"

    def test_cross_owner_ancestry_produces_unresolved(self, db_session) -> None:
        """Walking into a row owned by another user must fail closed.
        Requirement 2 AC 4–5, AC 10–12: cross-owner ancestry is refused."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root

        # root is owned by bob, not alice.
        bob_root_id = _run_id()
        alice_rev_id = _run_id()
        _seed_run(db_session, run_id=bob_root_id, user_id="bob")
        _seed_run(
            db_session,
            run_id=alice_rev_id,
            user_id="alice",
            parent_run_id=bob_root_id,
        )

        result = resolve_revision_root(db_session, alice_rev_id, "alice")

        assert isinstance(result, RevisionRootUnresolved)
        # The cross-owner row is indistinguishable from missing (defense: no info leak).
        assert result.reason == "missing_or_cross_owner"

    def test_cross_owner_refusal_does_not_expose_other_owners_run_id(
        self, db_session
    ) -> None:
        """The unresolved result must NOT expose the other owner's run id.
        Requirement 2 AC 12: client-visible response is generic and non-enumerating."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root

        bob_root_id = _run_id()
        alice_rev_id = _run_id()
        _seed_run(db_session, run_id=bob_root_id, user_id="bob")
        _seed_run(
            db_session,
            run_id=alice_rev_id,
            user_id="alice",
            parent_run_id=bob_root_id,
        )

        result = resolve_revision_root(db_session, alice_rev_id, "alice")

        assert isinstance(result, RevisionRootUnresolved)
        # The unresolved result must identify the REQUESTED run id (alice's), not
        # the other owner's bob_root_id.
        assert result.run_id == alice_rev_id, (
            "run_id on the failure result must be the originally requested run id, "
            "not an ancestor or cross-owner id"
        )

    def test_resolver_never_falls_back_to_requested_run_id_on_cycle(
        self, db_session
    ) -> None:
        """On a cycle the resolver must FAIL CLOSED — it must NOT fall back to
        returning the original run_id as the root.
        Requirement 2 AC 10: supersedes v1 Requirement 1 AC 4."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root
        from app.models.workflow import WorkflowRun

        run_id = _run_id()
        _seed_run(db_session, run_id=run_id, user_id="alice")
        db_session.query(WorkflowRun).filter(
            WorkflowRun.id == run_id
        ).update({"parent_run_id": run_id})
        db_session.commit()

        result = resolve_revision_root(db_session, run_id, "alice")

        # Must be an Unresolved — never a Resolved whose root_id == run_id.
        assert isinstance(result, RevisionRootUnresolved), (
            "Resolver MUST fail closed on a cycle; it must NOT fall back to "
            "returning the requested run id as a 'partial root' "
            "(Requirement 2 AC 10)"
        )

    def test_unresolved_visited_count_and_repeated_node_for_cycle(
        self, db_session
    ) -> None:
        """visited_count and repeated_node are populated for operator diagnostics.
        Requirement 2 AC 12."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root
        from app.models.workflow import WorkflowRun

        run_id = _run_id()
        _seed_run(db_session, run_id=run_id, user_id="alice")
        db_session.query(WorkflowRun).filter(
            WorkflowRun.id == run_id
        ).update({"parent_run_id": run_id})
        db_session.commit()

        result = resolve_revision_root(db_session, run_id, "alice")

        assert isinstance(result, RevisionRootUnresolved)
        assert result.visited_count >= 1, "visited_count must be populated"
        assert result.repeated_node is not None, "repeated_node must be set for a cycle"

    def test_unresolved_repeated_node_is_none_for_non_cycle_failures(
        self, db_session
    ) -> None:
        """For non-cycle failures (missing ancestor), repeated_node must be None.
        Requirement 2 AC 12."""
        from app.api.runs import RevisionRootUnresolved, resolve_revision_root

        run_id = _run_id()
        _seed_run(
            db_session,
            run_id=run_id,
            user_id="alice",
            parent_run_id=_run_id(),  # non-existent parent
        )

        result = resolve_revision_root(db_session, run_id, "alice")

        assert isinstance(result, RevisionRootUnresolved)
        assert result.repeated_node is None, (
            "repeated_node must be None for non-cycle failures"
        )


# ===========================================================================
# 3. TTL sweep — protected-set contract  (Requirement 2 AC 13–17)
# ===========================================================================


class TestTTLSweepProtectedSet:
    """Verify that sweep_expired respects the protection contract.

    The protection set here is passed directly as ``protected_run_ids`` —
    in production the sweeper builds this set by resolving revision roots of
    non-terminal runs.  These tests focus on sweep mechanics: the directory-name
    matching and the TTL logic.

    Requirements: 2 AC 13–17
    """

    def _make_old_dir(self, runs_root: Path, user: str, run_seg: str) -> Path:
        """Create a user/run directory whose mtime is far in the past (expired)."""
        from app.agents.sandbox import _safe_segment

        user_seg = _safe_segment(user, fallback="anonymous")
        run_dir = runs_root / user_seg / run_seg
        run_dir.mkdir(parents=True)
        # Force mtime to 1000 seconds ago — well past any TTL.
        old_time = time.time() - 1000
        import os

        os.utime(run_dir, (old_time, old_time))
        return run_dir

    def test_expired_terminal_family_is_swept(self, tmp_path: Path) -> None:
        """A fully terminal and TTL-expired family directory IS removed.
        Requirement 2 AC 17 (second assertion)."""
        from app.agents.sandbox import sweep_expired

        run_dir = self._make_old_dir(tmp_path, "user1", "run-terminal-001")

        removed = sweep_expired(
            ttl_hours=0,
            runs_root=str(tmp_path),
            protected_run_ids=set(),  # no protection
        )

        assert removed == 1
        assert not run_dir.exists(), "expired terminal sandbox must be swept"

    def test_active_descendant_protects_sandbox(self, tmp_path: Path) -> None:
        """An active (non-terminal) descendant's resolved root id is in the
        protected set, so the sandbox directory must NOT be swept.

        Requirement 2 AC 13–14: every non-terminal run protects the revision root.
        """
        from app.agents.sandbox import sweep_expired

        root_seg = "root-active-family"
        run_dir = self._make_old_dir(tmp_path, "user1", root_seg)

        # The protected set contains the run_seg of the family root
        # (which is the same string used as the directory name by RunSandbox).
        removed = sweep_expired(
            ttl_hours=0,
            runs_root=str(tmp_path),
            protected_run_ids={root_seg},
        )

        assert removed == 0
        assert run_dir.exists(), (
            "sandbox with an active descendant (protected root) must NOT be swept"
        )

    def test_gate_paused_descendant_protects_sandbox(self, tmp_path: Path) -> None:
        """A run durably paused at a human gate is non-terminal and protects
        the family sandbox, even when its sandbox mtime is past the TTL.

        Requirement 2 AC 14: a durable pause is NOT treated as inactivity.
        """
        from app.agents.sandbox import sweep_expired

        root_seg = "root-gate-paused-family"
        run_dir = self._make_old_dir(tmp_path, "user1", root_seg)

        # In production the protected set would include the root resolved from
        # the gate-paused descendant's parent chain.  Here we directly pass the
        # root segment to isolate the sweep mechanic.
        removed = sweep_expired(
            ttl_hours=0,
            runs_root=str(tmp_path),
            protected_run_ids={root_seg},
        )

        assert removed == 0
        assert run_dir.exists(), (
            "gate-paused (non-terminal) descendant must protect the sandbox"
        )

    def test_resolver_failure_protects_sandbox(self, tmp_path: Path) -> None:
        """A resolver failure (ambiguous or cyclic ancestry) must protect the
        sandbox — fail closed, never delete on ambiguity.

        Requirement 2 AC 15: the sweeper and the launch path use the same
        resolver; a resolver failure is PROTECTED.
        Requirement 2 AC 11: callers must treat RevisionRootUnresolved as
        PROTECTED (never deletable).
        """
        from app.agents.sandbox import sweep_expired

        # Simulate a resolver failure: in production the sweeper calls the resolver
        # and includes the root seg in the protected set on failure.  We model that
        # by including the root seg in the protected_run_ids — which is what a
        # correct sweeper implementation MUST do.
        root_seg = "root-cycle-ambiguous"
        run_dir = self._make_old_dir(tmp_path, "user1", root_seg)

        # Resolver failure → include in protected set rather than deleting.
        removed = sweep_expired(
            ttl_hours=0,
            runs_root=str(tmp_path),
            protected_run_ids={root_seg},
        )

        assert removed == 0
        assert run_dir.exists(), (
            "A resolver failure must protect the sandbox (fail closed — never delete "
            "on ambiguity, Requirement 2 AC 11, AC 15)"
        )

    def test_two_families_one_protected_one_swept(self, tmp_path: Path) -> None:
        """Two families; the protected one survives and the expired terminal one
        is swept.  Verifies both sweeping and protection work in one pass."""
        from app.agents.sandbox import sweep_expired

        protected_seg = "family-with-active-run"
        terminal_seg = "family-fully-terminal"

        protected_dir = self._make_old_dir(tmp_path, "user1", protected_seg)
        terminal_dir = self._make_old_dir(tmp_path, "user1", terminal_seg)

        removed = sweep_expired(
            ttl_hours=0,
            runs_root=str(tmp_path),
            protected_run_ids={protected_seg},
        )

        assert removed == 1
        assert protected_dir.exists(), "protected family must survive"
        assert not terminal_dir.exists(), "terminal expired family must be swept"


# ===========================================================================
# 4. Admission atomicity — concurrent revision launches  (Requirement 10 AC 2)
# ===========================================================================


class TestAdmissionAtomicityUnderFamilyLock:
    """Verify that the family lock serializes concurrent access to a shared
    revision sandbox; two concurrent acquisitions cannot overlap.

    Requirements: 10 AC 1–2
    """

    def test_family_lock_is_exclusive(self, tmp_path: Path) -> None:
        """Two threads trying to acquire the same family lock must serialize:
        only one can hold it at a time.  The second is either blocked (if it
        waits) or raises FamilyLockTimeout (if it uses a short timeout)."""
        from app.agents.sandbox import FamilyLockTimeout, family_lock

        user_id = "user-concurrent"
        root_id = "root-concurrent"

        lock_held_at: list[float] = []
        lock_released_at: list[float] = []
        errors: list[Exception] = []

        acquired_event = threading.Event()

        def holder() -> None:
            """Acquire the lock, signal, hold for 0.15 s, release."""
            try:
                with family_lock(
                    user_id,
                    root_id,
                    timeout_s=5.0,
                    runs_root=str(tmp_path),
                ):
                    lock_held_at.append(time.monotonic())
                    acquired_event.set()
                    time.sleep(0.15)
                    lock_released_at.append(time.monotonic())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def contender() -> None:
            """Wait for the holder to grab the lock, then try with a tight timeout."""
            acquired_event.wait(timeout=5.0)
            # Use a very short timeout — the holder is sleeping, so this must
            # either raise FamilyLockTimeout or succeed AFTER the holder releases.
            try:
                with family_lock(
                    user_id,
                    root_id,
                    timeout_s=0.05,  # 50 ms — holder sleeps 150 ms
                    runs_root=str(tmp_path),
                ):
                    lock_held_at.append(time.monotonic())
                    lock_released_at.append(time.monotonic())
            except FamilyLockTimeout:
                # Expected outcome: contender cannot acquire within 50 ms.
                pass
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=holder, daemon=True)
        t2 = threading.Thread(target=contender, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not errors, f"Unexpected errors during lock contention: {errors}"

        # Either the contender timed out (only 1 acquisition recorded by holder)
        # or it succeeded after the holder released (in which case the two
        # acquisition timestamps must be non-overlapping).
        if len(lock_held_at) == 2:
            # Both acquired at some point — must be sequential, not concurrent.
            # The second acquisition must start after the first release.
            first_released = lock_released_at[0]
            second_acquired = lock_held_at[1]
            assert second_acquired >= first_released, (
                "Second acquisition started before first release — locks overlapped! "
                "The family lock is not exclusive."
            )
        else:
            # Only the holder acquired — contender timed out as expected.
            assert len(lock_held_at) == 1

    def test_family_lock_different_families_do_not_block_each_other(
        self, tmp_path: Path
    ) -> None:
        """Two threads acquiring locks for DIFFERENT families (different root ids)
        must not block each other — the lock is keyed by (user_id, root_id)."""
        from app.agents.sandbox import family_lock

        acquired: list[str] = []
        errors: list[Exception] = []

        def grab_a() -> None:
            try:
                with family_lock(
                    "user1",
                    "root-A",
                    timeout_s=2.0,
                    runs_root=str(tmp_path),
                ):
                    acquired.append("A")
                    time.sleep(0.05)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def grab_b() -> None:
            try:
                with family_lock(
                    "user1",
                    "root-B",
                    timeout_s=2.0,
                    runs_root=str(tmp_path),
                ):
                    acquired.append("B")
                    time.sleep(0.05)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=grab_a, daemon=True)
        t2 = threading.Thread(target=grab_b, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        assert not errors, f"Unexpected errors: {errors}"
        assert set(acquired) == {"A", "B"}, (
            "Both different-family locks must be acquired independently"
        )

    def test_family_lock_timeout_raises_family_lock_timeout(
        self, tmp_path: Path
    ) -> None:
        """A timed-out lock acquisition raises FamilyLockTimeout (not silently
        proceeds unlocked).  Requirement 10 AC 2."""
        from app.agents.sandbox import FamilyLockTimeout, family_lock

        ready = threading.Event()
        hold_event = threading.Event()

        def holder() -> None:
            with family_lock(
                "user1",
                "root-timeout-test",
                timeout_s=5.0,
                runs_root=str(tmp_path),
            ):
                ready.set()
                hold_event.wait(timeout=5.0)  # hold until told to release

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        ready.wait(timeout=5.0)  # wait for holder to grab the lock

        with pytest.raises(FamilyLockTimeout):
            with family_lock(
                "user1",
                "root-timeout-test",
                timeout_s=0.01,  # 10 ms — way too short
                runs_root=str(tmp_path),
            ):
                pass  # must never reach here

        hold_event.set()
        t.join(timeout=5.0)

    def test_family_lock_is_reentrant_across_sequential_acquisitions(
        self, tmp_path: Path
    ) -> None:
        """The SAME thread can acquire the lock sequentially (after releasing),
        which is the idempotency re-entry pattern of the finalizer."""
        from app.agents.sandbox import family_lock

        for i in range(3):
            with family_lock(
                "user1",
                "root-sequential",
                timeout_s=2.0,
                runs_root=str(tmp_path),
            ):
                pass  # acquire and release; next iteration must succeed


# ===========================================================================
# 5. Lock order — family lock before manifest lock  (Requirement 10 AC 11)
# ===========================================================================


class TestLockOrder:
    """Verify the documented lock order: family lock FIRST, then per-sandbox
    manifest lock.

    Requirement 10 AC 11: "Lock ordering SHALL be single and documented:
    family lock first, then the per-sandbox manifest lock."

    This class tests that the documented ordering is the one in the codebase
    and demonstrates that the reverse order causes a deadlock (two threads each
    holding one lock while waiting for the other).
    """

    def test_family_lock_acquired_before_manifest_lock_succeeds(
        self, tmp_path: Path
    ) -> None:
        """Two threads following the correct order (family first, then a second
        per-file lock) should complete without deadlock."""
        from app.agents.sandbox import family_lock

        # We simulate the "manifest lock" with a plain threading.Lock; the key
        # insight is that BOTH threads acquire in the SAME order.
        manifest_lock = threading.Lock()
        results: list[str] = []
        errors: list[Exception] = []

        def _worker(thread_name: str) -> None:
            try:
                # Correct order: family lock first, manifest second.
                with family_lock(
                    "user1",
                    "root-order-test",
                    timeout_s=2.0,
                    runs_root=str(tmp_path),
                ):
                    with manifest_lock:
                        results.append(thread_name)
                        time.sleep(0.02)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=_worker, args=("T1",), daemon=True)
        t2 = threading.Thread(target=_worker, args=("T2",), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        assert not errors, f"Unexpected errors: {errors}"
        assert set(results) == {"T1", "T2"}, (
            "Both threads must complete when they follow the correct lock order"
        )

    def test_reverse_lock_order_causes_deadlock(self, tmp_path: Path) -> None:
        """DIAGNOSTIC: acquiring manifest first, then family, causes deadlock when
        two threads race.  This test verifies the deadlock scenario and is the
        behavioral proof of why the documented order matters.

        The test deliberately creates the deadlock, detects it via a timeout,
        and asserts the threads did NOT both complete (they got stuck).
        """
        from app.agents.sandbox import family_lock

        manifest_lock = threading.Lock()
        completed: list[str] = []

        # T1 grabs manifest_lock first, then tries family_lock.
        # T2 grabs family_lock first, then tries manifest_lock.
        # This is a classic ABBA deadlock.
        #
        # We use the timed family_lock and a timed manifest acquire to avoid an
        # infinite hang in the test runner; both threads will time out.

        t1_got_manifest = threading.Event()
        t2_got_family = threading.Event()

        def _t1_wrong_order() -> None:
            # Acquires manifest FIRST (wrong order).
            with manifest_lock:
                t1_got_manifest.set()
                # Wait for T2 to grab family lock before we try it.
                t2_got_family.wait(timeout=1.0)
                # Now try to acquire the family lock — T2 holds it, so we block.
                try:
                    from app.agents.sandbox import FamilyLockTimeout  # noqa: PLC0415

                    with family_lock(
                        "user1",
                        "root-deadlock-test",
                        timeout_s=0.1,
                        runs_root=str(tmp_path),
                    ):
                        completed.append("T1")
                except FamilyLockTimeout:
                    pass  # timed out as expected in the deadlock scenario

        def _t2_holds_family() -> None:
            # Acquires family FIRST (correct order, but T2 holds it while T1 holds
            # manifest — creating the cross-hold deadlock condition).
            from app.agents.sandbox import family_lock  # noqa: PLC0415

            with family_lock(
                "user1",
                "root-deadlock-test",
                timeout_s=2.0,
                runs_root=str(tmp_path),
            ):
                t2_got_family.set()
                # Wait for T1 to take the manifest lock.
                t1_got_manifest.wait(timeout=1.0)
                # Now try to acquire manifest — T1 holds it, T1 waits for family.
                acquired = manifest_lock.acquire(timeout=0.1)
                if acquired:
                    completed.append("T2")
                    manifest_lock.release()

        t1 = threading.Thread(target=_t1_wrong_order, daemon=True)
        t2 = threading.Thread(target=_t2_holds_family, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        # In a deadlock scenario neither thread completes.  We accept that one or
        # zero threads completed (depending on timing) but NOT both — that would
        # mean the test did not create the deadlock scenario.
        assert len(completed) < 2, (
            "The reverse-lock-order scenario should deadlock; both threads "
            "completing suggests the deadlock did not occur."
        )

    def test_correct_lock_order_constant_is_documented_in_module(self) -> None:
        """Structural check: the family_lock docstring documents the lock order
        (family first, manifest second) to prevent future regressions."""
        import inspect

        from app.agents.sandbox import family_lock

        doc = inspect.getdoc(family_lock) or ""
        # The docstring must mention both the order and the consequence.
        assert "family lock" in doc.lower() or "family" in doc.lower(), (
            "family_lock docstring must mention 'family lock'"
        )
        assert "manifest" in doc.lower(), (
            "family_lock docstring must mention 'manifest' lock to document the "
            "correct ordering (family first, manifest second)"
        )
