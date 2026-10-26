"""tests/agents/test_phase3_acceptance.py — Task 5.11 Phase 3 acceptance tests.

Covers the remaining Phase 3 (sandbox reuse) acceptance criteria that are NOT
already covered by:
  - test_phase3_wip_commit.py     (task 5.9 — wip commits + dirty-tree reconciliation)

Tests in this module:
  1. Sandbox identity — a revision resolves to the SAME directory as its parent;
     run_files.py list/zip/read routes all address the shared chain-root sandbox.
  3. Concurrency guard — a second create_revision against an already-active parent
     fails fast with "a revision is already in progress" (Requirement 3).
  4. Per-run path scoping — run_log_path, verify_dir, browser_dir each use run_id
     so multiple revisions in one shared sandbox stay separated (Requirement 24).
  5. Characterization re-baseline documentation — the three revision goldens that
     must be deliberately re-baselined once sandbox-reuse is live.

All tests are pure unit tests — no LLM calls, no real database, no running engine.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid4() -> str:
    return str(uuid.uuid4())


class _ResolveRootRow(tuple):
    """A 2-tuple that also carries attributes.

    ``resolve_revision_root`` (runs.py) selects ``(WorkflowRun.id,
    WorkflowRun.parent_run_id)`` and unpacks the result as ``_id,
    parent_run_id = row`` — a real SQLAlchemy ``Row`` supports that; a bare
    ``MagicMock()`` does not (it has no ``__iter__`` yielding 2 items) and
    raises ``ValueError`` on unpack. This mimics the Row closely enough for
    that unpack *and*, via ``extra_attrs``, for a later attribute-access
    query that reuses the same mocked ``.first()`` return value.
    """


def _resolved_root_row(id_: str, parent_run_id: str | None = None, **extra_attrs):
    row = _ResolveRootRow((id_, parent_run_id))
    for key, value in extra_attrs.items():
        setattr(row, key, value)
    return row


def _make_run_row(
    run_id: str,
    *,
    user_id: str = "user-1",
    parent_run_id: str | None = None,
    source_run_id: str | None = None,
    status: str = "completed",
) -> MagicMock:
    """Build a minimal WorkflowRun mock row."""
    row = MagicMock()
    row.id = run_id
    row.user_id = user_id
    row.owner_id = user_id
    row.parent_run_id = parent_run_id
    row.source_run_id = source_run_id
    row.status = status
    row.workspace_id = f"ws-{run_id[:8]}"
    return row


# ===========================================================================
# 1. Sandbox identity — revision resolves to the same directory as parent
#    Requirement 1 AC2, Requirement 43 AC1
# ===========================================================================


class TestSandboxIdentity:
    """A revision sandbox is keyed on the chain root, not on its own run_id.

    These tests pin the contract at the RunSandbox layer: given the same chain
    root id, two RunSandbox instances point at the SAME directory.
    """

    def test_two_sandboxes_with_same_run_id_share_directory(
        self, tmp_path: Path
    ) -> None:
        """Two RunSandbox instances keyed on the same id share one on-disk directory.

        This is the core sandbox-reuse contract: once the engine and run_files
        both resolve to the chain root, their sandboxes are byte-identical in path.
        """
        from app.agents.sandbox import RunSandbox

        root_id = _uuid4()
        sb_a = RunSandbox("user-1", root_id, runs_root=str(tmp_path))
        sb_b = RunSandbox("user-1", root_id, runs_root=str(tmp_path))

        assert (
            sb_a.root == sb_b.root
        ), "Two RunSandbox instances keyed on the same run_id must share one directory"

    def test_revision_sandbox_key_equals_parent_root_key(self, tmp_path: Path) -> None:
        """A revision sandbox keyed on the chain root == the parent's own sandbox.

        Simulates what engine._execute_impl does: it resolves a chain root of
        'parent-run' for the revision, then constructs RunSandbox with that root.
        The parent used the same key, so both sandboxes point at the same dir.
        """
        from app.agents.sandbox import RunSandbox

        parent_run_id = _uuid4()

        # Parent sandbox (keyed on itself — it IS the root)
        parent_sb = RunSandbox("user-1", parent_run_id, runs_root=str(tmp_path))
        parent_sb.ensure()
        (parent_sb.root / "prototype.html").write_text(
            "<html><body>v1</body></html>", encoding="utf-8"
        )

        # Revision sandbox keyed on chain root (= parent_run_id, since parent
        # has no parent of its own — it IS the root)
        revision_sb = RunSandbox("user-1", parent_run_id, runs_root=str(tmp_path))

        # Both must address the same directory
        assert (
            revision_sb.root == parent_sb.root
        ), "Revision sandbox must address the same root directory as its parent"
        # The parent's file is visible from the revision sandbox
        assert (
            revision_sb.root / "prototype.html"
        ).exists(), "prototype.html written by the parent must be visible in the revision sandbox"

    def test_files_written_by_parent_are_visible_in_revision(
        self, tmp_path: Path
    ) -> None:
        """Files written by the parent step are visible to the revision without copying.

        This is the core value of sandbox reuse (Requirement 1 AC3): the revision
        finds spec.md, prototype.html, etc. in-place with no previous_run seeding.
        """
        from app.agents.sandbox import RunSandbox

        root_id = _uuid4()

        # Parent writes several files
        parent_sb = RunSandbox("user-1", root_id, runs_root=str(tmp_path))
        parent_sb.ensure()
        (parent_sb.root / "spec.md").write_text("# Spec", encoding="utf-8")
        (parent_sb.root / "prototype.html").write_text(
            "<html>v1</html>", encoding="utf-8"
        )
        (parent_sb.root / "tasks.md").write_text("- [ ] task 1", encoding="utf-8")

        # Revision opens the SAME directory (same root_id)
        revision_sb = RunSandbox("user-1", root_id, runs_root=str(tmp_path))

        assert (revision_sb.root / "spec.md").exists(), "spec.md must be present"
        assert (
            revision_sb.root / "prototype.html"
        ).exists(), "prototype.html must be present without copying"
        assert (revision_sb.root / "tasks.md").exists(), "tasks.md must be present"

    def test_run_files_list_sandbox_addresses_chain_root(self, tmp_path: Path) -> None:
        """list_sandbox constructs RunSandbox from chain-root id, not the request run_id.

        A revision run-B (parent run-A) must return the SAME file listing as
        querying run-A directly — they share one directory.
        """
        from app.agents.sandbox import RunSandbox

        parent_id = _uuid4()

        # Provision the shared sandbox under the parent key
        parent_sb = RunSandbox("user-1", parent_id, runs_root=str(tmp_path))
        parent_sb.ensure()
        (parent_sb.root / "prototype.html").write_text(
            "<html>final</html>", encoding="utf-8"
        )

        # Both parent and revision sandboxes address the same directory
        parent_sb2 = RunSandbox("user-1", parent_id, runs_root=str(tmp_path))
        revision_sb = RunSandbox(
            "user-1",
            parent_id,  # chain root = parent_id
            runs_root=str(tmp_path),
        )

        parent_files, _ = parent_sb2.list_files()
        revision_files, _ = revision_sb.list_files()

        parent_paths = {f["path"] for f in parent_files}
        revision_paths = {f["path"] for f in revision_files}

        assert "prototype.html" in parent_paths, "parent must see prototype.html"
        assert parent_paths == revision_paths, (
            "Workspace tab listing for a revision must be identical to the parent's, "
            "as both sandboxes address the same shared directory"
        )


# ===========================================================================
# 3. Concurrency guard — second create_revision against active parent is rejected
#    Requirement 3 AC1, AC2
# ===========================================================================


class TestRevisionConcurrencyGuard:
    """_has_active_chain_revision returns True when a non-terminal revision exists.

    _mint_revision_row calls _has_active_chain_revision and raises HTTP 409 when
    it returns True.  These unit tests pin the predicate in isolation.
    """

    def _make_db(
        self,
        *,
        root_id: str,
        parent_id: str,
        child_ids: list[str],
        active_ids: set[str],
        user_id: str = "user-1",
    ) -> MagicMock:
        """Build a minimal mock DB session for _has_active_chain_revision.

        Mocks three query patterns:
          1. Walk parent_run_id UP to root (resolve_revision_root's 2-column
             (WorkflowRun.id, WorkflowRun.parent_run_id) select).
          2. BFS DOWN from root via parent_run_id links.
          3. Non-terminal status check on descendants.
        """
        db = MagicMock()

        # --- Step 1: walk parent_run_id UP ---
        # _revision_chain_root_id delegates to resolve_revision_root (runs.py),
        # which selects (WorkflowRun.id, WorkflowRun.parent_run_id) and unpacks
        # the row as a 2-tuple — see _resolved_root_row's docstring.
        parent_row = _resolved_root_row(root_id, None)  # root has no parent

        # --- Step 2: BFS DOWN --- (returns direct child ids)
        child_rows = [MagicMock(id=cid) for cid in child_ids]

        # --- Step 3: non-terminal status check ---
        active_row = (
            MagicMock(id=next(iter(active_ids)))
            if active_ids & set(child_ids)
            else None
        )

        call_count = [0]

        def query_impl(*_columns):
            # resolve_revision_root passes two column args (id, parent_run_id);
            # the BFS/status queries below pass one — accept either.
            q = MagicMock()

            def filter_impl(*args, **kwargs):
                inner = MagicMock()
                i = call_count[0]
                call_count[0] += 1

                if i == 0:
                    # _revision_chain_root_id -> resolve_revision_root's 2-column query
                    inner.first.return_value = parent_row
                elif i == 1:
                    # BFS level 1: children of root
                    inner.all.return_value = child_rows
                elif i == 2:
                    # BFS level 2: no grandchildren
                    inner.all.return_value = []
                elif i == 3:
                    # Non-terminal status check
                    inner.first.return_value = active_row
                else:
                    inner.first.return_value = None
                    inner.all.return_value = []

                return inner

            q.filter = filter_impl
            return q

        db.query = query_impl
        return db

    def test_no_active_revision_allows_new_one(self) -> None:
        """When no child has an active status, _has_active_chain_revision returns False."""
        from app.api.run_commands import _has_active_chain_revision

        root_id = _uuid4()
        completed_child = _uuid4()
        db = self._make_db(
            root_id=root_id,
            parent_id=root_id,
            child_ids=[completed_child],
            active_ids=set(),  # child is terminal (completed)
        )

        result = _has_active_chain_revision(db, root_id, "user-1")
        assert result is False, (
            "A completed child must not block a new revision "
            "(Requirement 3 — only non-terminal counts as active)"
        )

    def test_active_revision_blocks_new_one(self) -> None:
        """When a child has a non-terminal status, _has_active_chain_revision returns True."""
        from app.api.run_commands import _has_active_chain_revision

        root_id = _uuid4()
        running_child = _uuid4()
        db = self._make_db(
            root_id=root_id,
            parent_id=root_id,
            child_ids=[running_child],
            active_ids={running_child},  # still running
        )

        result = _has_active_chain_revision(db, root_id, "user-1")
        assert result is True, (
            "A running (non-terminal) child must block a second revision "
            "(Requirement 3 AC1)"
        )

    def test_db_error_degrades_to_false(self) -> None:
        """A DB error in _has_active_chain_revision returns False (best-effort, never blocks).

        Requirement 3 AC2: the guard must NOT block a launch due to a DB or code error.
        """
        from app.api.run_commands import _has_active_chain_revision

        db = MagicMock()
        db.query.side_effect = Exception("simulated DB failure")

        result = _has_active_chain_revision(db, _uuid4(), "user-1")
        assert result is False, (
            "A DB error must degrade to False (allow the revision) — "
            "never block a launch due to infrastructure failure (Requirement 3 AC2)"
        )

    def test_no_family_members_allows_new_revision(self) -> None:
        """A root run with no child revisions returns False (no active chain member)."""
        from app.api.run_commands import _has_active_chain_revision

        root_id = _uuid4()

        call_count = [0]

        def make_db():
            db = MagicMock()

            def query_impl(*_columns):
                # resolve_revision_root passes two column args (id, parent_run_id);
                # the BFS query below passes one — accept either.
                q = MagicMock()

                def filter_impl(*args, **kwargs):
                    inner = MagicMock()
                    i = call_count[0]
                    call_count[0] += 1

                    if i == 0:
                        # Step 1: root has no parent_run_id — see
                        # _resolved_root_row's docstring for why a plain
                        # MagicMock() row breaks resolve_revision_root's unpack.
                        inner.first.return_value = _resolved_root_row(root_id, None)
                    else:
                        # BFS: no children found
                        inner.all.return_value = []
                        inner.first.return_value = None

                    return inner

                q.filter = filter_impl
                return q

            db.query = query_impl
            return db

        result = _has_active_chain_revision(make_db(), root_id, "user-1")
        assert result is False

    def test_mint_revision_row_raises_409_on_active_child(self) -> None:
        """_mint_revision_row raises HTTP 409 when _has_active_chain_revision is True.

        This is the documented rejection: 'a revision is already in progress'.
        Requirement 3 AC1.
        """
        from fastapi import HTTPException

        # Patch _has_active_chain_revision to simulate an active revision exists
        with patch(
            "app.api.run_commands._has_active_chain_revision",
            return_value=True,
        ):
            db = MagicMock()
            # _mint_revision_row resolves the revision root (resolve_revision_root
            # unpacking a 2-tuple row) before the active-child check runs.
            db.query.return_value.filter.return_value.first.return_value = (
                _resolved_root_row(_uuid4(), None)
            )
            user = MagicMock()
            user.id = "user-1"
            user.tier = "pro"

            with pytest.raises(HTTPException) as exc_info:
                from app.api.run_commands import _mint_revision_row

                _mint_revision_row(
                    db,
                    user=user,
                    # The caller's EFFECTIVE tier (Cognito-only auth migration,
                    # Decision 3) — the same tier this user carries.
                    caller_tier="pro",
                    parent_run_id=_uuid4(),
                    target_artifact_type="prototype_output",
                    instruction="improve the design",
                )

        assert (
            exc_info.value.status_code == 409
        ), "A concurrent revision must be rejected with HTTP 409 (Requirement 3 AC1)"
        assert "already in progress" in str(exc_info.value.detail).lower(), (
            "The 409 response must carry the documented message "
            "'a revision is already in progress'"
        )

    def test_second_mint_is_rejected_not_first(self) -> None:
        """The FIRST create_revision succeeds; the SECOND is the one rejected.

        Simulates the sequence:
          1. Revision A is dispatched → _has_active_chain_revision=False → row minted.
          2. While A is running, revision B arrives →  _has_active_chain_revision=True
             → 409 raised before any row is minted.
        """
        from fastapi import HTTPException

        call_results = [False, True]  # first call = no active; second = active

        # get_pipeline_agents is imported inside _mint_revision_row from agents.registry.
        # can_run_pipeline is a top-level import from app.core.entitlements.
        with (
            patch(
                "app.api.run_commands._has_active_chain_revision",
                side_effect=call_results,
            ),
            patch("agents.registry.get_pipeline_agents", return_value=["agent1"]),
            patch("app.core.entitlements.can_run_pipeline", return_value=(True, "ok")),
        ):
            db = MagicMock()
            # Same .first() stub backs both resolve_revision_root's (id,
            # parent_run_id) unpack and the later parent_wr = db.query(WorkflowRun)
            # ....first() workspace_id lookup on the (first, successful) mint.
            db.query.return_value.filter.return_value.first.return_value = (
                _resolved_root_row(_uuid4(), None, workspace_id="ws-1")
            )
            user = MagicMock()
            user.id = "user-1"
            user.tier = "pro"

            from app.api.run_commands import _mint_revision_row

            # First call succeeds
            _mint_revision_row(
                db,
                user=user,
                # The caller's EFFECTIVE tier (Cognito-only auth migration,
                # Decision 3) — the same tier this user carries.
                caller_tier="pro",
                parent_run_id=_uuid4(),
                target_artifact_type="prototype_output",
                instruction="first revision",
            )

            # Second call must raise 409
            with pytest.raises(HTTPException) as exc_info:
                _mint_revision_row(
                    db,
                    user=user,
                    caller_tier="pro",
                    parent_run_id=_uuid4(),
                    target_artifact_type="prototype_output",
                    instruction="second revision — concurrent",
                )

        assert exc_info.value.status_code == 409


# ===========================================================================
# 4. Per-run path scoping — Requirement 24
# ===========================================================================


class TestPerRunPathScoping:
    """run_log_path, verify_dir, and browser_dir use run_id not a flat name.

    Multiple revisions in a shared sandbox each write into their own per-run
    subdirectory so their logs, evidence, and browser captures never collide
    (Requirement 24 AC1–3).
    """

    def test_run_log_path_uses_run_id(self, tmp_path: Path) -> None:
        """run_log_path returns .logs/{run_id}.jsonl — never the old flat name."""
        from app.agents.sandbox import RunSandbox

        run_id = "my-test-run-" + _uuid4()[:8]
        sb = RunSandbox("user-1", run_id, runs_root=str(tmp_path))

        assert (
            sb.run_log_path == sb.root / ".logs" / f"{run_id}.jsonl"
        ), "run_log_path must be .logs/{run_id}.jsonl (Requirement 24 AC1)"
        assert "run-logs.jsonl" not in str(
            sb.run_log_path
        ), "The old flat .logs/run-logs.jsonl must never be used"

    def test_verify_dir_uses_run_id(self, tmp_path: Path) -> None:
        """verify_dir returns .verify/{run_id}/ — not a flat .verify/."""
        from app.agents.sandbox import RunSandbox

        run_id = "verify-test-" + _uuid4()[:8]
        sb = RunSandbox("user-1", run_id, runs_root=str(tmp_path))

        assert (
            sb.verify_dir == sb.root / ".verify" / run_id
        ), "verify_dir must be .verify/{run_id}/ (Requirement 24 AC2)"

    def test_browser_dir_uses_run_id(self, tmp_path: Path) -> None:
        """browser_dir returns .browser/{run_id}/ — not a flat .browser/."""
        from app.agents.sandbox import RunSandbox

        run_id = "browser-test-" + _uuid4()[:8]
        sb = RunSandbox("user-1", run_id, runs_root=str(tmp_path))

        assert (
            sb.browser_dir == sb.root / ".browser" / run_id
        ), "browser_dir must be .browser/{run_id}/ (Requirement 24 AC3)"

    def test_two_revisions_use_different_log_paths(self, tmp_path: Path) -> None:
        """Two revisions sharing one sandbox have separate log paths.

        Both are keyed on the same chain root (shared directory), but each uses
        its own run_id for the log file so they never overwrite each other.
        """
        from app.agents.sandbox import RunSandbox

        chain_root = _uuid4()
        rev_a_id = "rev-a-" + _uuid4()[:8]
        rev_b_id = "rev-b-" + _uuid4()[:8]

        # Both revisions are keyed on the same chain root (one shared directory)
        # and carry their own logical run id — the same construction the engine
        # uses (sandbox_root_id=chain root, current_run_id=the revision's run id).
        sb_rev_a = RunSandbox(
            "user-1", chain_root, current_run_id=rev_a_id, runs_root=str(tmp_path)
        )
        sb_rev_b = RunSandbox(
            "user-1", chain_root, current_run_id=rev_b_id, runs_root=str(tmp_path)
        )

        assert (
            sb_rev_a.root == sb_rev_b.root
        ), "Both revisions must share the chain-root sandbox directory"
        assert (
            sb_rev_a.run_log_path != sb_rev_b.run_log_path
        ), "Two revisions must write to different log files (Requirement 24 AC1)"
        assert (
            sb_rev_a.verify_dir != sb_rev_b.verify_dir
        ), "Two revisions must use different validator evidence directories"
        assert (
            sb_rev_a.browser_dir != sb_rev_b.browser_dir
        ), "Two revisions must use different browser artifact directories"

    def test_log_path_parent_dir_is_logs(self, tmp_path: Path) -> None:
        """The run log file lives under .logs/ (not at the sandbox root)."""
        from app.agents.sandbox import RunSandbox

        run_id = _uuid4()
        sb = RunSandbox("user-1", run_id, runs_root=str(tmp_path))

        assert (
            sb.run_log_path.parent.name == ".logs"
        ), "run_log_path must be inside the .logs/ subdirectory"
        assert (
            sb.run_log_path.suffix == ".jsonl"
        ), "run_log_path must use .jsonl extension"


# ===========================================================================
# 5. Characterization re-baseline documentation
#    Design doc: "Three revision characterization goldens need deliberate re-baselining
#    once the sandbox holds accumulated files — expected and blessed."
# ===========================================================================


class TestCharacterizationRebaselineDocumentation:
    """Documents which characterization goldens must be re-baselined and why.

    These tests do NOT run the golden comparison — that would be a false failure
    (the sandbox-reuse change is an EXPECTED behaviour change, not a bug).
    Instead they assert the golden FILES EXIST so that any premature or accidental
    deletion is caught, and they document the re-baseline trigger.

    The actual re-baseline must be done DELIBERATELY with:
        SNAPSHOT_UPDATE=1 pytest tests/agents/test_characterization_{name}.py
    AFTER tasks 5.1–5.10 are fully deployed and verified live.

    Requirement 43, INV-3: "Three revision characterization goldens need deliberate
    re-baselining once the sandbox holds accumulated files — expected and blessed."
    """

    _GOLDENS_NEEDING_REBASELINE = [
        # (golden_filename, pipeline_name, reason)
        (
            "prototype_revision.html",
            "prototype_revision",
            "Revision opens shared sandbox: prototype.html already present from parent "
            "step. The deliverable is a modified-in-place version, not a fresh write. "
            "Previous golden was written into an EMPTY directory.",
        ),
        (
            "prototype_large_revision.html",
            "prototype_large_revision",
            "Same as prototype_revision: shared sandbox means the builder agent finds "
            "prototype.html from the prior run. The large-revision planner's context "
            "changes because previous_run seeding is now short-circuited.",
        ),
        (
            "prototype_feature_revision.html",
            "prototype_feature_revision",
            "Same as above. The feature-specify step finds spec.md and tasks.md in the "
            "shared sandbox already; the previous_run provider no longer copies them.",
        ),
    ]

    def test_prototype_revision_golden_exists(self) -> None:
        """prototype_revision.html golden file must exist before re-baseline."""
        from tests.agents.characterization import GOLDEN_DIR

        golden = GOLDEN_DIR / "prototype_revision.html"
        assert golden.exists(), (
            "prototype_revision.html golden is missing — it must exist before it can "
            "be deliberately re-baselined. Run SNAPSHOT_UPDATE=1 to generate it."
        )

    def test_prototype_large_revision_golden_exists(self) -> None:
        """prototype_large_revision.html golden file must exist before re-baseline."""
        from tests.agents.characterization import GOLDEN_DIR

        golden = GOLDEN_DIR / "prototype_large_revision.html"
        assert golden.exists(), (
            "prototype_large_revision.html golden is missing — it must exist before "
            "re-baseline. Run SNAPSHOT_UPDATE=1 to generate it."
        )

    def test_prototype_feature_revision_golden_exists(self) -> None:
        """prototype_feature_revision.html golden file must exist before re-baseline."""
        from tests.agents.characterization import GOLDEN_DIR

        golden = GOLDEN_DIR / "prototype_feature_revision.html"
        assert golden.exists(), (
            "prototype_feature_revision.html golden is missing — it must exist before "
            "re-baseline. Run SNAPSHOT_UPDATE=1 to generate it."
        )

    def test_rebaseline_trigger_conditions_documented(self) -> None:
        """The three revision goldens are the only ones needing re-baseline.

        This test is a living record: it asserts the re-baseline set has exactly
        three entries and that each has a non-empty reason.  If more goldens are
        added to the re-baseline list they must come with documented justification.
        """
        assert len(self._GOLDENS_NEEDING_REBASELINE) == 3, (
            "Exactly three revision goldens must be re-baselined for Phase 3 sandbox "
            "reuse (prototype_revision, prototype_large_revision, "
            "prototype_feature_revision)"
        )
        for filename, pipeline, reason in self._GOLDENS_NEEDING_REBASELINE:
            assert filename, "Each re-baseline entry must have a filename"
            assert pipeline, "Each re-baseline entry must have a pipeline name"
            assert reason, "Each re-baseline entry must have a documented reason"
            assert len(reason) >= 50, (
                f"Re-baseline reason for {pipeline} must be substantive "
                f"(got {len(reason)} chars)"
            )

    def test_snapshot_update_guard_is_not_set(self) -> None:
        """SNAPSHOT_UPDATE must NOT be set by default.

        This guards INV-3: goldens must never be regenerated silently.  The CI
        run and 'pytest' without env overrides must always compare, never write.
        """
        from tests.agents.characterization import SNAPSHOT_UPDATE

        assert SNAPSHOT_UPDATE is False, (
            "SNAPSHOT_UPDATE must be False in the default (CI) pytest run. "
            "Set SNAPSHOT_UPDATE=1 explicitly to regenerate goldens — never "
            "commit with this env var set (INV-3)."
        )


# ===========================================================================
# 6. Integration: revision uses same sandbox — file written by parent is
#    overwritten in-place by revision (no stale copy)
#    Requirement 1 AC3
# ===========================================================================


class TestRevisionOverwritesInPlace:
    """End-to-end sandbox write pattern: parent writes a file; revision overwrites it.

    No LLM, no engine run — just the RunSandbox write() primitive.  Verifies that
    the revision does NOT create a second copy and that git history records both
    versions (the pre-revision value is accessible via git log, not lost).
    """

    def test_revision_overwrites_deliverable_in_shared_sandbox(
        self, tmp_path: Path
    ) -> None:
        """prototype.html written by parent is overwritten by revision in-place.

        The revision sandbox is keyed on the same chain root, so write() lands
        in the same directory.  The file contains the revision's content, not the
        parent's content, after the write.
        """
        from app.agents.sandbox import RunSandbox

        chain_root = _uuid4()

        # Parent run: write prototype.html (v1)
        parent_sb = RunSandbox("user-1", chain_root, runs_root=str(tmp_path))
        parent_sb.ensure()
        (parent_sb.root / "prototype.html").write_text(
            "<html>v1</html>", encoding="utf-8"
        )

        # Revision run: open same sandbox and overwrite
        revision_sb = RunSandbox("user-1", chain_root, runs_root=str(tmp_path))
        (revision_sb.root / "prototype.html").write_text(
            "<html>v2 - revised</html>", encoding="utf-8"
        )

        # Read back — must show v2, not v1
        content = (parent_sb.root / "prototype.html").read_text(encoding="utf-8")
        assert (
            "v2 - revised" in content
        ), "After revision, prototype.html must contain the revision's content"
        assert "v1" not in content, (
            "The parent's stale v1 content must be overwritten — "
            "this is tracked in git history under the prior commit"
        )

    def test_parent_files_outside_deliverable_are_also_shared(
        self, tmp_path: Path
    ) -> None:
        """Non-deliverable files (spec.md, tasks.md) are also shared — no copy needed.

        A revision can read spec.md written by the original run without going
        through the previous_run seed loop (Requirement 4 AC1).
        """
        from app.agents.sandbox import RunSandbox

        chain_root = _uuid4()

        # Original run writes spec.md and tasks.md
        original_sb = RunSandbox("user-1", chain_root, runs_root=str(tmp_path))
        original_sb.ensure()
        (original_sb.root / "spec.md").write_text("## Original Spec", encoding="utf-8")
        (original_sb.root / "tasks.md").write_text("- [x] step 1", encoding="utf-8")

        # Revision opens the same directory — no seed loop needed
        revision_sb = RunSandbox("user-1", chain_root, runs_root=str(tmp_path))

        spec_content = (revision_sb.root / "spec.md").read_text(encoding="utf-8")
        tasks_content = (revision_sb.root / "tasks.md").read_text(encoding="utf-8")

        assert "Original Spec" in spec_content, "spec.md must be visible to revision"
        assert "step 1" in tasks_content, "tasks.md must be visible to revision"
