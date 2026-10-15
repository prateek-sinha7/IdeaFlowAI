"""ISS-1099 — ScopedStore.update_wave_run_merge_state must persist the merge outcome.

The method calls the deleted ``self._acquire()`` (authz.py), so it raises
AttributeError and no wave_runs merge_* column is ever written.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register every table
from app.models.database import Base
from app.models.wave_run import WaveRun
from agents.authz import ScopedStore


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


@pytest.mark.issue("ISS-1099")
def test_update_wave_run_merge_state_persists_columns_owner_scoped():
    """ISS-1099 — owner writes the four merge columns; another owner is a no-op."""
    session = _session()
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=session)
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=session)

    async def go():
        await alice.record_wave_run(
            "run-1", step="build", wave_index=0, task_ids=["a"], status="completed"
        )
        kwargs = dict(
            step_id="build",
            merge_state="clean",
            merge_applied='["a"]',
            merge_conflicts="[]",
            merge_strategy="git_3way",
        )
        # cross-owner caller must not touch alice's row (and must not raise)
        await mallory.update_wave_run_merge_state(
            "run-1", **{**kwargs, "merge_state": "evil"}
        )
        row = session.query(WaveRun).filter(WaveRun.run_id == "run-1").one()
        assert row.merge_state is None
        await alice.update_wave_run_merge_state("run-1", **kwargs)
        session.refresh(row)
        return row

    row = asyncio.run(go())
    assert (
        row.merge_state,
        row.merge_applied,
        row.merge_conflicts,
        row.merge_strategy,
    ) == (
        "clean",
        '["a"]',
        "[]",
        "git_3way",
    )


@pytest.mark.issue("ISS-1099")
def test_scopedstore_methods_only_use_attributes_that_exist():
    """ISS-1099 — every self._x a ScopedStore method uses must exist on the class."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(ScopedStore)))
    instance_attrs = {"_owner_id", "_workspace_id", "_session"}  # set in __init__
    missing = {
        n.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "self"
        and n.attr.startswith("_")
        and not n.attr.startswith("__")
        and n.attr not in instance_attrs
        and not hasattr(ScopedStore, n.attr)
    }
    assert not missing, f"ScopedStore uses undefined attributes: {sorted(missing)}"
