"""Regression test for the workflow_artifacts -> workflow_runs foreign key.

The original production bug: the engine wrote artifacts keyed by a
``pipeline_run_id`` that did not match any ``workflow_runs.id``. Postgres raised
``ForeignKeyViolation``; SQLite (FK enforcement off) silently accepted it, so no
test caught it. These tests exercise the **DB path** (``use_db=True``) against an
FK-enforcing SQLite engine (see ``tests/conftest.py::fk_session``), so the same
violation now fails fast at the unit-test layer.
"""

from __future__ import annotations

import uuid

import pytest

from agents.artifact_store.store import ArtifactStore, ArtifactStoreWriteError
from app.models.user import User
from app.models.workflow import WorkflowRun


def _make_run(session) -> str:
    """Insert a User + WorkflowRun (with id == run id) and return the run id."""
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
    session.add(user)
    session.flush()  # populate user.id

    run_id = str(uuid.uuid4())
    session.add(
        WorkflowRun(
            id=run_id,
            user_id=user.id,
            type="prototype",
            input="build me a thing",
            agent_count=1,
        )
    )
    session.commit()
    return run_id


@pytest.mark.asyncio
async def test_store_succeeds_when_run_exists(fk_session):
    """A valid run id satisfies the FK — the artifact persists with version 1."""
    run_id = _make_run(fk_session)
    store = ArtifactStore(use_db=True)

    artifact_id = await store.store(
        run_id=run_id,
        artifact_type="prototype-specify",
        name="prototype-specify",
        content="<spec>hello</spec>",
        producing_agent_id="prototype-specify",
    )

    assert artifact_id
    fetched = await store.retrieve_version(artifact_id)
    assert fetched is not None
    assert fetched["workflow_run_id"] == run_id
    assert fetched["version"] == 1


@pytest.mark.asyncio
async def test_store_raises_when_run_missing(fk_session):
    """A run id with no matching workflow_runs row violates the FK.

    This is the exact shape of the original bug. With FK enforcement on, the
    insert fails and the store surfaces it as ArtifactStoreWriteError (per the
    Artifact_Store contract — callers must NOT mark the step complete).
    """
    store = ArtifactStore(use_db=True)

    with pytest.raises(ArtifactStoreWriteError):
        await store.store(
            run_id="missing-" + str(uuid.uuid4()),
            artifact_type="prototype-specify",
            name="prototype-specify",
            content="<spec>orphan</spec>",
            producing_agent_id="prototype-specify",
        )
