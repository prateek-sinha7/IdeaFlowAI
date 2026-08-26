"""Spec 016 — user overrides of built-in workflows.

Two units, tested here because they are the whole security and correctness
surface of the feature:

* ``app.api._workflow_override`` — the owner-scoped lookup every call site
  shares. The screen and the run MUST agree about which plan is in force, and
  they only can if they resolve through one function.
* ``agents.execution_engine.overrides.merge_override_steps`` — the merge that
  takes ONLY ``steps`` from the DB and leaves every workflow-level field
  (deliverable, context_providers, clarify, planner) coming from the file
  manifest.

The cache-identity test is the load-bearing one: ``compile_for_run`` is
``lru_cache(maxsize=None)`` and its result is shared across every user and run,
so a merge that mutated it would leak one user's customisation into everybody
else's runs until process restart.
"""

from __future__ import annotations

import dataclasses
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


def _seed(db, *, wf_id, user_id="owner", overrides=None, enabled=False,
          manifest=None, source="user"):
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


# ── resolve_override ─────────────────────────────────────────────────────────


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


# ── find_override ────────────────────────────────────────────────────────────


def test_find_override_sees_a_disabled_row(db):
    """The read endpoints need this so a switched-off override still renders its
    (unticked) checkbox instead of vanishing with no way back on."""
    _seed(db, wf_id="ov", overrides="ppt", enabled=False)
    row = find_override(db, _FakeUser("owner"), "ppt")
    assert row is not None and row.id == "ov"


def test_find_override_is_still_owner_scoped(db):
    _seed(db, wf_id="theirs", user_id="someone-else", overrides="ppt", enabled=True)
    assert find_override(db, _FakeUser("owner"), "ppt") is None


# ── override_steps ───────────────────────────────────────────────────────────


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
    row = _seed(db, wf_id="ov", overrides="ppt", enabled=True,
                manifest={"steps": steps})
    assert override_steps(row) == steps


def test_override_steps_of_none_is_none():
    assert override_steps(None) is None


# ── merge_override_steps ─────────────────────────────────────────────────────
#
# `ppt` is the real fixture on purpose: it is the workflow this feature exists
# for, and it is the one whose workflow-level capabilities (deliverable `ppt`,
# context_provider `opendesign`) are NOT user-allowed. A merge that sourced
# those from the override would fail to compile — these tests prove it doesn't.


@pytest.fixture
def ppt_compiled():
    from agents.execution_engine.engine import compile_for_run

    return compile_for_run("ppt")


@pytest.fixture
def registry():
    from agents.execution_engine.engine import _CAPABILITY_REGISTRY

    return _CAPABILITY_REGISTRY


def _steps(*instance_ids):
    return [
        {
            "agent": "custom-agent",
            "instance_id": iid,
            "name": iid,
            "prompt": f"You are {iid}.",
            "tools": {"read_files": False, "write_files": False, "exec": False},
        }
        for iid in instance_ids
    ]


def test_merge_does_not_mutate_the_cached_plan(ppt_compiled, registry):
    """THE load-bearing test.

    compile_for_run is lru_cache(maxsize=None), so its CompiledWorkflow is
    shared across every user and run in the process. A merge that mutated it
    would leak one user's customisation into everyone else's runs until restart.
    """
    from agents.execution_engine.engine import compile_for_run
    from agents.execution_engine.overrides import merge_override_steps

    before_ids = [s.agent_id for s in ppt_compiled.steps]
    merged = merge_override_steps(ppt_compiled, _steps("mine"), registry)

    # The cached object is untouched...
    assert [s.agent_id for s in ppt_compiled.steps] == before_ids
    assert [s.agent_id for s in compile_for_run("ppt").steps] == before_ids
    # ...and the result is a different object carrying the override.
    assert merged is not ppt_compiled
    assert [s.agent_id for s in merged.steps] != before_ids


def test_merge_keeps_every_workflow_level_field_from_the_file(ppt_compiled, registry):
    """deliverable `ppt` and context_provider `opendesign` are NOT user_allowed.
    They survive only because they are never sourced from the override."""
    from agents.execution_engine.overrides import merge_override_steps

    merged = merge_override_steps(ppt_compiled, _steps("mine"), registry)

    assert merged.deliverable.strategy == ppt_compiled.deliverable.strategy == "ppt"
    assert merged.deliverable.name == ppt_compiled.deliverable.name
    assert merged.context_providers == ppt_compiled.context_providers
    assert "opendesign" in merged.context_providers
    assert merged.planner == ppt_compiled.planner
    assert merged.clarify.mode == ppt_compiled.clarify.mode
    assert list(merged.clarify.defaults) == list(ppt_compiled.clarify.defaults)
    assert merged.id == ppt_compiled.id


def test_merge_applies_the_override_steps(ppt_compiled, registry):
    from agents.execution_engine.overrides import merge_override_steps

    merged = merge_override_steps(ppt_compiled, _steps("one", "two"), registry)
    assert len(merged.steps) == 2


def test_empty_steps_returns_the_file_plan_unchanged(ppt_compiled, registry):
    from agents.execution_engine.overrides import merge_override_steps

    assert merge_override_steps(ppt_compiled, [], registry) is ppt_compiled


def test_a_not_user_allowed_gate_is_rejected(ppt_compiled, registry):
    """`security` is registered user_allowed=False. A row smuggling one must be
    refused by the trust gate and the run must fall back to the file plan."""
    from agents.execution_engine.overrides import merge_override_steps

    bad = _steps("mine")
    bad[0]["gates"] = ["security"]
    assert merge_override_steps(ppt_compiled, bad, registry) is ppt_compiled


def test_a_malformed_step_list_falls_back_to_the_file_plan(ppt_compiled, registry):
    from agents.execution_engine.overrides import merge_override_steps

    assert merge_override_steps(ppt_compiled, ["not-a-step"], registry) is ppt_compiled
