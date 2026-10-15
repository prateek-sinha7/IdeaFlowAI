"""tests/agents/test_revision_ordinal_v3.py — GAPS §1 P0 #4 (FR-036 / FR-013).

One counting rule for both the git tag ordinal and the API's ``revision_index``:
a run's 1-based position among ALL family members ordered by creation,
regardless of status — the same walk ``_owned_family_members`` in
``app/api/runs.py`` performs for the ``revision_index`` field.

Before this fix, ``_compute_revision_ordinal`` counted only ``completed``
ancestors while ``revision_index`` counted every family member. A
completed -> failed -> completed family therefore tagged its third run
``v2`` while the API/UI showed ``v3``. This file proves:

  1. ``_compute_revision_ordinal`` now counts every ancestor (regardless of
     status) — the failed revision still consumes an ordinal.
  2. That count matches ``GET /api/runs/{id}/family``'s ``revision_index`` on
     the SAME mixed-status family.
  3. ``finalize_terminal_run`` tags the third (completed) run ``v3`` and never
     calls ``_compute_revision_ordinal`` itself — it reads the value already
     stamped onto ``ectx.revision_ordinal`` at launch (spec: "no DB access
     from inside the finalizer").
  4. The failed run in that same family gets no tag at all.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))

from tests.agents.test_finalizer_v2 import (  # noqa: E402
    FakeSandbox,
    _git_init,
    _make_ectx,
    _plant_logs,
    _plant_output,
)

from app.api.runs import router  # noqa: E402
from app.core.dependencies import get_current_user  # noqa: E402
from app.models.database import Base, get_db  # noqa: E402
from app.models.workflow import WorkflowRun  # noqa: E402

_USER_ID = "test-user-v2"  # matches test_finalizer_v2._make_ectx's owner_id
_BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeUser:
    def __init__(self, id: str) -> None:
        self.id = id


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


def _seed_run(
    db,
    *,
    run_id: str,
    parent_run_id: str | None = None,
    status: str = "completed",
    created_offset: int = 0,
    user_id: str = _USER_ID,
) -> None:
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=user_id,
            title=f"revision ordinal fixture {run_id}",
            type="prototype",
            status=status,
            input="build me a thing",
            owner_id=user_id,
            workspace_id="ws-1",
            parent_run_id=parent_run_id,
            created_at=_BASE_TS + timedelta(seconds=created_offset),
        )
    )
    db.commit()


def _seed_mixed_family(db) -> tuple[str, str, str]:
    """completed -> failed -> completed, chronological (root, rev1, rev2)."""
    root_id, rev1_id, rev2_id = (f"ord-{uuid.uuid4()}" for _ in range(3))
    _seed_run(db, run_id=root_id, status="completed", created_offset=0)
    _seed_run(
        db, run_id=rev1_id, parent_run_id=root_id, status="failed", created_offset=10
    )
    _seed_run(
        db, run_id=rev2_id, parent_run_id=rev1_id, status="completed", created_offset=20
    )
    return root_id, rev1_id, rev2_id


# ---------------------------------------------------------------------------
# 1. _compute_revision_ordinal — the counting rule itself
# ---------------------------------------------------------------------------


class TestComputeRevisionOrdinalCountingRule:
    def test_failed_ancestor_still_consumes_an_ordinal(self, db_session) -> None:
        """completed -> failed -> completed: the third run is ordinal 3, not 2.

        Before the fix, ``_compute_revision_ordinal`` skipped the failed
        ancestor (it counted only ``completed`` ancestors), so the third run
        computed ordinal 2 — diverging from ``revision_index`` (which counts
        every family member).
        """
        from agents.execution_engine.engine import _compute_revision_ordinal

        root_id, rev1_id, rev2_id = _seed_mixed_family(db_session)

        assert _compute_revision_ordinal(root_id, db_session) == 1
        assert _compute_revision_ordinal(rev1_id, db_session) == 2
        assert _compute_revision_ordinal(rev2_id, db_session) == 3

    def test_all_completed_family_unchanged(self, db_session) -> None:
        """Sanity: an all-completed family still counts 1, 2, 3 (no regression)."""
        from agents.execution_engine.engine import _compute_revision_ordinal

        root_id, rev1_id, rev2_id = (f"ord-{uuid.uuid4()}" for _ in range(3))
        _seed_run(db_session, run_id=root_id, status="completed", created_offset=0)
        _seed_run(
            db_session,
            run_id=rev1_id,
            parent_run_id=root_id,
            status="completed",
            created_offset=10,
        )
        _seed_run(
            db_session,
            run_id=rev2_id,
            parent_run_id=rev1_id,
            status="completed",
            created_offset=20,
        )

        assert _compute_revision_ordinal(rev2_id, db_session) == 3

    def test_sibling_revisions_both_parented_on_root_get_sequential_ordinals(
        self, db_session
    ) -> None:
        """GAPS T6: two SIBLING revisions (both ``parent_run_id`` = the root,
        neither the other's parent — created by revising the already-completed
        root twice, not by revising a revision) must NOT collide on the same
        ordinal.

        Before this fix, ``_compute_revision_ordinal`` walked the ancestor
        CHAIN: both siblings have exactly one ancestor (the root), so both
        computed ordinal 2 — this is byte-for-byte the live collision
        (root ``7a56140b…``, siblings ``f767bcb9…`` tagged v2 and
        ``226bf862…`` also computing v2 and colliding). Counting family-wide
        creation order instead gives the second sibling the next FREE number.
        """
        from agents.execution_engine.engine import _compute_revision_ordinal

        root_id, sib1_id, sib2_id = (f"ord-{uuid.uuid4()}" for _ in range(3))
        _seed_run(db_session, run_id=root_id, status="completed", created_offset=0)
        _seed_run(
            db_session,
            run_id=sib1_id,
            parent_run_id=root_id,
            status="completed",
            created_offset=10,
        )
        _seed_run(
            db_session,
            run_id=sib2_id,
            parent_run_id=root_id,
            status="completed",
            created_offset=20,
        )

        assert _compute_revision_ordinal(root_id, db_session) == 1
        assert _compute_revision_ordinal(sib1_id, db_session) == 2
        assert _compute_revision_ordinal(sib2_id, db_session) == 3


# ---------------------------------------------------------------------------
# 2. GET /api/runs/{id}/family — the SAME rule, independently computed
# ---------------------------------------------------------------------------


class TestRevisionIndexMatchesEngineOrdinal:
    def test_revision_index_matches_compute_revision_ordinal_on_mixed_family(
        self, db_session
    ) -> None:
        from agents.execution_engine.engine import _compute_revision_ordinal

        root_id, rev1_id, rev2_id = _seed_mixed_family(db_session)

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _FakeUser(id=_USER_ID)
        app.dependency_overrides[get_db] = lambda: db_session
        client = TestClient(app)

        body = client.get(f"/api/runs/{root_id}/family").json()
        by_id = {m["id"]: m for m in body["members"]}

        assert by_id[root_id]["revision_index"] == _compute_revision_ordinal(
            root_id, db_session
        )
        assert by_id[rev1_id]["revision_index"] == _compute_revision_ordinal(
            rev1_id, db_session
        )
        assert by_id[rev2_id]["revision_index"] == _compute_revision_ordinal(
            rev2_id, db_session
        )
        assert by_id[rev2_id]["revision_index"] == 3


# ---------------------------------------------------------------------------
# 3. finalize_terminal_run: tags v3 on the third run (from ectx, not the DB),
#    and the failed run in the same family gets no tag at all.
# ---------------------------------------------------------------------------


class TestFinalizerTagsFromContextNotFromDb:
    def _finalize(self, run_id: str, ectx, *, candidate_status: str):
        from agents.execution_engine import engine as eng

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
                eng.finalize_terminal_run(
                    run_id, ectx, candidate_status=candidate_status
                )
            )

    def test_third_run_tags_v3_and_finalizer_never_recomputes_the_ordinal(
        self, tmp_path: Path, db_session
    ) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine import engine as eng

        root_id, rev1_id, rev2_id = _seed_mixed_family(db_session)
        # What launch-time execute() would have computed and stamped onto
        # ectx.revision_ordinal for the third run, BEFORE the finalizer runs.
        ordinal = eng._compute_revision_ordinal(rev2_id, db_session)
        assert ordinal == 3

        repo = tmp_path / root_id
        repo.mkdir(parents=True)
        _git_init(repo)
        sandbox = FakeSandbox(
            root=repo,
            run_id=rev2_id,
            sandbox_root_id=root_id,
            current_run_id=rev2_id,
        )
        _plant_output(sandbox)
        _plant_logs(sandbox, rev2_id)
        ectx = _make_ectx(rev2_id, sandbox, revision_ordinal=ordinal)

        with patch.object(eng, "_compute_revision_ordinal") as spy_ordinal:
            record = self._finalize(rev2_id, ectx, candidate_status="completed")
            spy_ordinal.assert_not_called()

        assert record.git_tag == "v3", f"expected v3, got {record.git_tag!r}"
        assert "v3" in sandbox.list_tags()

    def test_failed_run_in_same_family_gets_no_tag(
        self, tmp_path: Path, db_session
    ) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        root_id, rev1_id, _rev2_id = _seed_mixed_family(db_session)

        repo = tmp_path / root_id
        repo.mkdir(parents=True)
        _git_init(repo)
        sandbox = FakeSandbox(
            root=repo,
            run_id=rev1_id,
            sandbox_root_id=root_id,
            current_run_id=rev1_id,
        )
        _plant_output(sandbox)
        _plant_logs(sandbox, rev1_id)
        ectx = _make_ectx(rev1_id, sandbox, final_status="failed", revision_ordinal=2)

        record = self._finalize(rev1_id, ectx, candidate_status="failed")

        assert record.git_tag is None
        assert sandbox.list_tags() == []


# ---------------------------------------------------------------------------
# 4. GAPS §1 T1 — drive the REAL finalization path (execute()/_execute_impl,
#    not a hand-built ectx) over a family of 3 real completed runs sharing one
#    sandbox. Every test above constructs ``ectx`` directly via ``_make_ectx``
#    with ``revision_ordinal`` already set — none of them touch the actual
#    launch-time code that stamps ``ectx.revision_ordinal`` inside
#    ``_execute_impl``. That code had its own bug, invisible to those tests:
#    the block computed the ordinal and wrote ``ectx.revision_ordinal = ...``
#    BEFORE ``ectx = ExecutionContext(...)`` existed in the function, so every
#    real (API) revision launch raised ``UnboundLocalError``, was swallowed by
#    a bare ``except Exception``, and silently fell back to the default
#    ordinal of 1 — confirmed via a live run's log ("cannot access local
#    variable 'ectx'"). The finalizer then tried tag "v1" for every completed
#    revision, collided with the root's own v1, and the run published
#    degraded with no tag. This class is the only one in the file that would
#    have failed against that bug (and did, pre-fix — see the journal).
# ---------------------------------------------------------------------------


class TestSequentialTagsAcrossRealFinalization:
    def test_three_completed_revisions_tag_v1_v2_v3(self) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.sandbox import RunSandbox  # noqa: PLC0415
        from app.models.database import SessionLocal as _RealSessionLocal  # noqa: PLC0415
        from app.models.user import User  # noqa: PLC0415
        from tests.agents._scripted_model import _drive  # noqa: PLC0415

        # ``_drive`` hardcodes ``user_id="harness-user"`` — its owner_id, and
        # the ``RunSandbox`` disk key, must match.
        _owner = "harness-user"
        # Plain UUIDs (no prefix): finalize_terminal_run's internal run-ref
        # namespace (refs/ideaflow/runs/<run_id>) requires hex digits and
        # hyphens only.
        root_id, rev1_id, rev2_id = (str(uuid.uuid4()) for _ in range(3))

        # ``_execute_impl`` resolves the shared sandbox root and computes the
        # ordinal via its OWN short-lived ``SessionLocal()`` calls — the real,
        # hermetic per-test-process DB conftest.py pins (not the isolated
        # in-memory ``db_session`` the other classes in this file use), so
        # rows must be seeded there for the engine to see them.
        # ``workflow_runs.user_id`` FKs to ``users.id`` — seed (once; a
        # shared fixed id may already exist from another test in this
        # process) before inserting any WorkflowRun row.
        real_db = _RealSessionLocal()
        try:
            if real_db.query(User).filter(User.id == _owner).first() is None:
                real_db.add(
                    User(
                        id=_owner,
                        email=f"{_owner}@test.local",
                        cognito_sub=str(uuid.uuid4()),
                    )
                )
                real_db.commit()
            # GAPS T6: distinct created_offset per row — the family-wide
            # counting rule (BFS down from root, sorted by (created_at, id))
            # falls back to the ``id`` tiebreak on a tie, and these ids are
            # random UUIDs, so three rows sharing one timestamp made this
            # test's outcome depend on UUID luck instead of the intended
            # chain order. Invisible under the old ancestor-CHAIN rule (which
            # never reads created_at at all) — newly reached, not newly
            # caused, by this fix (S3 journal precedent).
            _seed_run(
                real_db,
                run_id=root_id,
                parent_run_id=None,
                user_id=_owner,
                created_offset=0,
            )
            _seed_run(
                real_db,
                run_id=rev1_id,
                parent_run_id=root_id,
                user_id=_owner,
                created_offset=10,
            )
            _seed_run(
                real_db,
                run_id=rev2_id,
                parent_run_id=rev1_id,
                user_id=_owner,
                created_offset=20,
            )
        finally:
            real_db.close()

        for run_id, parent_run_id in (
            (root_id, None),
            (rev1_id, root_id),
            (rev2_id, rev1_id),
        ):
            drive_kwargs = {"pipeline_run_id": run_id}
            if parent_run_id:
                drive_kwargs["parent_run_id"] = parent_run_id
            # ``offline_db=False``: keep the real hermetic SessionLocal seeded
            # above in place. The harness default swaps in a no-database seam,
            # under which root resolution and the finalizer's tag DB mapping
            # both fail and every run publishes ``degraded``.
            events = asyncio.run(_drive("custom", offline_db=False, **drive_kwargs))

            completes = [e for e in events if e.get("type") == "pipeline_complete"]
            assert (
                len(completes) == 1
            ), f"run {run_id}: expected exactly 1 pipeline_complete, got {completes}"
            published = completes[0]["data"].get("published_status", "completed")
            assert published == "completed", (
                f"run {run_id} did not complete cleanly (published_status="
                f"{published!r}) — the tag assertions below would be moot"
            )

        sandbox = RunSandbox(_owner, root_id)
        tags = sorted(sandbox.list_tags())
        assert tags == ["v1", "v2", "v3"], (
            f"expected exactly v1, v2, v3 with no gaps/reuse — got {tags}. "
            "A collision here (e.g. only ['v1']) means a revision's ordinal "
            "silently fell back to the default and collided with an "
            "existing tag instead of being threaded from launch."
        )

        # Each tag's commit TREE (not a diff against its parent — see the S3
        # journal's documented false-negative from using `git show
        # --name-only` on byte-identical content) holds that run's
        # deliverable.
        for tag in ("v1", "v2", "v3"):
            files = sandbox.list_files_at_ref(tag)
            assert (
                ".chain/output.md" in files
            ), f"tag {tag}: deliverable missing from the commit tree ({files})"


# ---------------------------------------------------------------------------
# 5. GAPS T6 — the family-wide counting rule, driven end to end over SIBLING
#    revisions (both parented directly on the root — "open the root run and
#    revise it" twice, in sequence, the real product path — not a chain).
#    ``TestSequentialTagsAcrossRealFinalization`` above (and every other real
#    run in this file) builds a CHAIN (root -> rev1 -> rev2, each parented on
#    the run before it), which is exactly why it kept passing while the real
#    product collided: an ancestor-chain walk and a family-wide walk agree on
#    a chain, and only diverge on siblings. This class is the only one that
#    would have caught the live bug.
# ---------------------------------------------------------------------------


class TestSequentialTagsAcrossSiblingRevisions:
    def test_two_sibling_revisions_tag_v1_v2_v3_not_v1_v2_v2(self) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        from app.agents.sandbox import RunSandbox  # noqa: PLC0415
        from app.models.database import SessionLocal as _RealSessionLocal  # noqa: PLC0415
        from app.models.user import User  # noqa: PLC0415
        from tests.agents._scripted_model import _drive  # noqa: PLC0415

        _owner = "harness-user"
        root_id, sib1_id, sib2_id = (str(uuid.uuid4()) for _ in range(3))

        real_db = _RealSessionLocal()
        try:
            if real_db.query(User).filter(User.id == _owner).first() is None:
                real_db.add(
                    User(
                        id=_owner,
                        email=f"{_owner}@test.local",
                        cognito_sub=str(uuid.uuid4()),
                    )
                )
                real_db.commit()
            _seed_run(real_db, run_id=root_id, parent_run_id=None, user_id=_owner)
            # Both siblings parented directly on the ROOT — NOT on each other.
            _seed_run(
                real_db,
                run_id=sib1_id,
                parent_run_id=root_id,
                user_id=_owner,
                created_offset=10,
            )
            _seed_run(
                real_db,
                run_id=sib2_id,
                parent_run_id=root_id,
                user_id=_owner,
                created_offset=20,
            )
        finally:
            real_db.close()

        for run_id, parent_run_id in (
            (root_id, None),
            (sib1_id, root_id),
            (sib2_id, root_id),  # sibling of sib1, NOT its child
        ):
            drive_kwargs = {"pipeline_run_id": run_id}
            if parent_run_id:
                drive_kwargs["parent_run_id"] = parent_run_id
            # ``offline_db=False`` — see TestSequentialTagsAcrossRealFinalization
            # above: the engine must use the real hermetic DB seeded here.
            events = asyncio.run(_drive("custom", offline_db=False, **drive_kwargs))

            completes = [e for e in events if e.get("type") == "pipeline_complete"]
            assert (
                len(completes) == 1
            ), f"run {run_id}: expected exactly 1 pipeline_complete, got {completes}"
            published = completes[0]["data"].get("published_status", "completed")
            assert published == "completed", (
                f"run {run_id} did not complete cleanly (published_status="
                f"{published!r}) — the tag assertions below would be moot"
            )

        sandbox = RunSandbox(_owner, root_id)
        tags = sorted(sandbox.list_tags())
        assert tags == ["v1", "v2", "v3"], (
            f"expected exactly v1, v2, v3 with no gaps/reuse — got {tags}. "
            "Two v2s (or a v2 collision degrading the second sibling untagged) "
            "means the ordinal is still counting the ancestor CHAIN instead of "
            "the family-wide creation order — both siblings have exactly one "
            "ancestor (the root), so a chain-depth count collides them."
        )
