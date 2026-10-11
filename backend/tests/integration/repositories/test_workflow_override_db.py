"""tests/integration/repositories/test_workflow_override_db.py — override lookup against a real DB.

``resolve_override`` / ``find_override`` / ``override_steps`` driven over an in-memory
SQLite session. Split out of ``tests/unit/test_workflow_override.py``: the ``db``
fixture opens a real database connection, which the unit I/O guard
(``tests/unit/conftest.py``) correctly refuses. The pure plan-merge tests stay in the
unit module. Test bodies are byte-identical to their originals.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api._workflow_override import (
    find_override,
    override_steps,
    resolve_override,
)
from app.models.database import Base
from app.models.workflow_definition import WorkflowDefinition


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed(
    db,
    *,
    wf_id,
    user_id="owner",
    overrides=None,
    enabled=False,
    manifest=None,
    source="user",
):
    row = WorkflowDefinition(
        id=wf_id,
        user_id=user_id,
        owner_id=user_id,
        workspace_id=user_id,
        name=wf_id,
        agents="[]",
        artifact_edges="[]",
        source=source,
        base_pipeline_type="ppt",
        overrides_pipeline_type=overrides,
        override_enabled=enabled,
        manifest_json=manifest,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def test_returns_none_when_user_has_no_override(db):
    """The entire existing population takes this branch — it must stay None."""
    assert resolve_override(db, _FakeUser("owner"), "ppt") is None


def test_returns_the_enabled_override(db):
    _seed(db, wf_id="ov", overrides="ppt", enabled=True)
    row = resolve_override(db, _FakeUser("owner"), "ppt")
    assert row is not None and row.id == "ov"


def test_disabled_override_is_invisible(db):
    """A switched-off override must read exactly as if the row did not exist —
    otherwise the checkbox would be decorative and the run would use it anyway."""
    _seed(db, wf_id="ov", overrides="ppt", enabled=False)
    assert resolve_override(db, _FakeUser("owner"), "ppt") is None


def test_never_returns_another_users_override(db):
    """AUTHZ-01: user_id is in the filter, so a cross-owner row is unreachable."""
    _seed(db, wf_id="theirs", user_id="someone-else", overrides="ppt", enabled=True)
    assert resolve_override(db, _FakeUser("owner"), "ppt") is None


def test_scoped_to_the_named_pipeline(db):
    _seed(db, wf_id="ov", overrides="prototype", enabled=True)
    assert resolve_override(db, _FakeUser("owner"), "ppt") is None


def test_ignores_a_file_sourced_row(db):
    _seed(db, wf_id="f", overrides="ppt", enabled=True, source="file")
    assert resolve_override(db, _FakeUser("owner"), "ppt") is None


def test_empty_pipeline_type_resolves_to_none(db):
    _seed(db, wf_id="ov", overrides="ppt", enabled=True)
    assert resolve_override(db, _FakeUser("owner"), "") is None


def test_find_override_sees_a_disabled_row(db):
    """The read endpoints need this so a switched-off override still renders its
    (unticked) checkbox instead of vanishing with no way back on."""
    _seed(db, wf_id="ov", overrides="ppt", enabled=False)
    row = find_override(db, _FakeUser("owner"), "ppt")
    assert row is not None and row.id == "ov"


def test_find_override_is_still_owner_scoped(db):
    _seed(db, wf_id="theirs", user_id="someone-else", overrides="ppt", enabled=True)
    assert find_override(db, _FakeUser("owner"), "ppt") is None


@pytest.mark.parametrize(
    "manifest",
    [None, {}, {"steps": None}, {"steps": []}, {"steps": "nope"}, "not-a-dict"],
    ids=["null", "empty", "steps-null", "steps-empty", "steps-str", "not-dict"],
)
def test_unusable_manifest_reads_as_no_override(db, manifest):
    """A malformed row degrades to the file manifest rather than propagating a
    broken plan — reachable only by hand-editing the DB, but cheap to guard."""
    row = _seed(db, wf_id="ov", overrides="ppt", enabled=True, manifest=manifest)
    assert override_steps(row) is None


def test_override_steps_returns_the_list(db):
    steps = [{"agent": "ppt-brief-analyst"}]
    row = _seed(
        db, wf_id="ov", overrides="ppt", enabled=True, manifest={"steps": steps}
    )
    assert override_steps(row) == steps
