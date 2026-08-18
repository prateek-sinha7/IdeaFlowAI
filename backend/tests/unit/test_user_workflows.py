"""Phase 21-01 — owner-scoped ``/api/user-workflows`` CRUD verify gate.

Pins the saved-workflow persistence spine: saved workflows are ``source="user"``
rows in the REUSED ``workflows`` table (REUSE-TABLE-INV12), owner-scoped, with
save-time validation that mirrors the launch predicates (SECURITY-REVALIDATE).
These are the verify gate for the threat-model ``mitigate`` rows:

* **T-21-01 (IDOR / ASVS V4):** GET/PATCH/DELETE ``/{id}`` filter
  ``id==:id AND user_id==current_user.id AND source=="user"`` — a cross-owner or
  missing id resolves to 404, never 403/leak (``test_cross_owner_*_is_404``). The
  list query additionally scopes ``source=="user"`` so a seeded ``source="file"``
  row and another user's row are excluded (``test_list_scopes_to_owner_user_rows``).
* **T-21-02 (Tampering):** POST re-validates ``base_pipeline_type`` /
  ``agent_ids`` / ``model_overrides`` with the SAME predicates the launch path
  uses — a bad value → 422 (the three ``test_post_rejects_*`` tests). Per-user
  name uniqueness is enforced at the API (``test_post_duplicate_name_rejected``).
* **T-21-05 (persistence integrity):** the insert stamps
  ``user_id=owner_id=workspace_id=current_user.id``, ``source="user"``,
  ``artifact_edges="[]"`` (``test_post_persists_owner_stamped_user_row``).

Plus a schema/migration test (``test_model_has_new_columns`` +
``test_migration_adds_then_drops_columns``) proving the 2 additive nullable
columns (ADDITIVE-MIGRATION) appear on the model and reverse cleanly offline.

Drives a FastAPI ``TestClient`` with ``get_current_user`` + ``get_db`` overridden
against an in-memory SQLite session (the ``test_runs_api.py`` harness) — no
Postgres.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_workflows import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition

# A valid custom composition (custom needs enterprise tier).
# CWF-001 D1: _AGENT_B is swot-analyst (consumes market-research-agent == _AGENT_A's
# produced type), so [_AGENT_A, _AGENT_B] is a valid producer-first chain that
# presorts to itself. report-generator (consumes documentation-agent, never produced)
# would now be correctly rejected as unsatisfiable by the compose-time guard.
_AGENT_A = "market-research-agent"
_AGENT_B = "swot-analyst"
_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — id + tier are read by the API."""

    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.tier = tier


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api(db_session):
    """Returns ``(client, state)`` — mutate ``state["user"]`` to switch principal."""
    app = FastAPI()
    app.include_router(router)

    state: dict = {"user": _FakeUser(id="owner")}

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


def _make_wf(db, *, wf_id="wf-1", user_id="owner", name="Seeded",
             source="user", agents='["market-research-agent"]', **kw):
    """Seed a WorkflowDefinition row directly (mirror ``_make_run``)."""
    import uuid
    from datetime import datetime, timezone

    row = WorkflowDefinition(
        id=wf_id or str(uuid.uuid4()),
        user_id=user_id,
        owner_id=user_id,
        workspace_id=user_id,
        name=name,
        agents=agents,
        artifact_edges="[]",
        source=source,
        base_pipeline_type=kw.get("base_pipeline_type", "custom"),
        model_overrides=kw.get("model_overrides"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _valid_body(**over):
    body = {
        "name": "Competitive research",
        "description": "research flow",
        "base_pipeline_type": "custom",
        "agent_ids": [_AGENT_A, _AGENT_B],
        "model_overrides": {_AGENT_A: _MODEL_ID},
    }
    body.update(over)
    return body


# --- POST: create + owner stamp -------------------------------------------


def test_post_persists_owner_stamped_user_row(api, db_session):
    client, _ = api
    r = client.post("/api/user-workflows", json=_valid_body())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["base_pipeline_type"] == "custom"
    assert data["agent_ids"] == [_AGENT_A, _AGENT_B]
    assert data["model_overrides"] == {_AGENT_A: _MODEL_ID}

    row = db_session.query(WorkflowDefinition).filter_by(id=data["id"]).first()
    assert row.source == "user"
    assert row.artifact_edges == "[]"
    # Self-id stamp (T-21-05).
    assert row.user_id == "owner"
    assert row.owner_id == "owner"
    assert row.workspace_id == "owner"


def test_post_persists_description_in_dedicated_column(api, db_session):
    """WR-03: ``description`` round-trips via the DEDICATED ``description`` column,
    NOT the overloaded ``constitution_ref`` (whose semantic is a workflow_memory
    key). Asserts the column carries the text AND ``constitution_ref`` stays NULL.
    """
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(description="A bespoke competitive-research flow"),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["description"] == "A bespoke competitive-research flow"

    row = db_session.query(WorkflowDefinition).filter_by(id=data["id"]).first()
    assert row.description == "A bespoke competitive-research flow"
    # The overload is gone — constitution_ref is NOT used for description.
    assert row.constitution_ref is None


def test_patch_updates_description_in_dedicated_column(api, db_session):
    """WR-03: PATCH-editing the description writes the dedicated column."""
    client, _ = api
    _make_wf(db_session, wf_id="d-row", user_id="owner", name="Desc", source="user")
    r = client.patch("/api/user-workflows/d-row", json={"description": "edited blurb"})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "edited blurb"

    row = db_session.query(WorkflowDefinition).filter_by(id="d-row").first()
    assert row.description == "edited blurb"
    assert row.constitution_ref is None


# --- POST: validation (save == launch) ------------------------------------


def test_post_rejects_unknown_base_pipeline_type(api):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(base_pipeline_type="not_a_real_pipeline"),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_disallowed_agent_id(api):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(agent_ids=["definitely-not-an-allowed-agent"]),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_unknown_model_id(api):
    client, _ = api
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(model_overrides={_AGENT_A: "not-a-real-model"}),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_override_targeting_non_member_agent(api):
    client, _ = api
    # Override key not in agent_ids → rejected (T-06-07 parity).
    r = client.post(
        "/api/user-workflows",
        json=_valid_body(agent_ids=[_AGENT_A], model_overrides={_AGENT_B: _MODEL_ID}),
    )
    assert r.status_code == 422, r.text


def test_post_rejects_empty_agent_ids(api):
    """WR-02: an empty ``agent_ids`` persists an unrunnable orphan row → 422.

    The subset check is trivially satisfied for ``[]`` (``rejected == []``), so
    the guard lives at the schema (``Field(min_length=1)``). The API is the
    security boundary even though the FE disables Save at zero agents.
    """
    client, _ = api
    r = client.post("/api/user-workflows", json=_valid_body(agent_ids=[]))
    assert r.status_code == 422, r.text


# --- CWF-001 D1: compose-time produces/consumes pre-sort + reject -----------


def test_post_reorders_consumer_first_to_producer_first(api, db_session):
    """A consumer-before-producer custom composition saves 201 with the persisted
    agent_ids reordered producer-first — so it can never launch into a runtime
    'Workflow DAG is unsatisfiable' death (the D1 repro, saved safely).

    KAN-112 cleared ``consumes``/``produces`` on the custom-utility pool
    (swot-analyst / market-research-agent among them) so that ANY subset of
    those agents composes freely — a deliberate product decision (custom
    composition is open by design), not a regression. ppt-composer /
    ppt-brief-analyst still carry a real produces/consumes edge (ppt-composer
    consumes the type ppt-brief-analyst produces), so they exercise the
    presort without relying on the now-intentionally-decoupled utility pair.
    """
    client, _ = api
    # ppt-composer consumes ppt-brief-analyst → producer must come first.
    body = {
        "name": "Consumer-first save",
        "base_pipeline_type": "custom",
        "agent_ids": ["ppt-composer", "ppt-brief-analyst"],
        "model_overrides": {},
    }
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["agent_ids"] == ["ppt-brief-analyst", "ppt-composer"]
    # And the PERSISTED row carries the producer-first order (not the sent order).
    row = db_session.query(WorkflowDefinition).filter_by(id=r.json()["id"]).first()
    import json as _json
    assert _json.loads(row.agents) == ["ppt-brief-analyst", "ppt-composer"]


def test_post_rejects_unsatisfiable_composition(api):
    """A genuinely-unsatisfiable set (ppt-composer alone consumes ppt-brief-analyst,
    which no selected agent produces) → 422 whose detail names the missing edge. No
    orphan row is created.

    See ``test_post_reorders_consumer_first_to_producer_first`` for why this uses
    ppt-composer/ppt-brief-analyst rather than the now-decoupled (KAN-112) custom
    utility pair.
    """
    client, _ = api
    body = {
        "name": "Unsatisfiable save",
        "base_pipeline_type": "custom",
        "agent_ids": ["ppt-composer"],
        "model_overrides": {},
    }
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "ppt-brief-analyst" in detail
    assert "produces it" in detail
    # No orphan row.
    assert client.get("/api/user-workflows").json() == []


def test_post_entitlement_gate_blocks_basic_tier(api):
    client, state = api
    state["user"] = _FakeUser(id="owner", tier="basic")  # custom needs enterprise
    r = client.post("/api/user-workflows", json=_valid_body())
    assert r.status_code == 403, r.text


def test_post_duplicate_name_rejected(api):
    client, _ = api
    assert client.post("/api/user-workflows", json=_valid_body(name="Dup")).status_code == 201
    r = client.post("/api/user-workflows", json=_valid_body(name="Dup"))
    assert r.status_code == 409, r.text


# --- GET list: owner + source scoping -------------------------------------


def test_list_scopes_to_owner_user_rows(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="mine", user_id="owner", name="Mine", source="user")
    _make_wf(db_session, wf_id="file", user_id="owner", name="File", source="file")
    _make_wf(db_session, wf_id="other", user_id="someone-else", name="Theirs", source="user")

    r = client.get("/api/user-workflows")
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert ids == {"mine"}  # file row + other user's row excluded


# --- IDOR → 404 ------------------------------------------------------------


def test_cross_owner_get_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="owned", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    assert client.get("/api/user-workflows/owned").status_code == 404


def test_cross_owner_patch_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="owned", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    r = client.patch("/api/user-workflows/owned", json={"name": "hijacked"})
    assert r.status_code == 404


def test_cross_owner_delete_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="owned", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    assert client.delete("/api/user-workflows/owned").status_code == 404


def test_get_missing_is_404(api):
    client, _ = api
    assert client.get("/api/user-workflows/nope").status_code == 404


# --- PATCH rename ----------------------------------------------------------


def test_patch_renames_own_row(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="r1", user_id="owner", name="Old", source="user")
    r = client.patch("/api/user-workflows/r1", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


# --- DELETE → 204 ----------------------------------------------------------


def test_delete_own_row_then_get_404(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="d1", user_id="owner", source="user")
    assert client.delete("/api/user-workflows/d1").status_code == 204
    assert client.get("/api/user-workflows/d1").status_code == 404


# --- Schema / migration (ADDITIVE-MIGRATION) ------------------------------


def test_model_has_new_columns():
    cols = set(WorkflowDefinition.__table__.columns.keys())
    assert "base_pipeline_type" in cols
    assert "model_overrides" in cols
    assert "description" in cols  # WR-03: dedicated description column
    # All nullable (additive, no constraint relaxation).
    assert WorkflowDefinition.__table__.columns["base_pipeline_type"].nullable
    assert WorkflowDefinition.__table__.columns["model_overrides"].nullable
    assert WorkflowDefinition.__table__.columns["description"].nullable


# --- T22: YAML export endpoint ---------------------------------------------


def test_yaml_export_returns_manifest_as_yaml(api, db_session):
    client, _ = api
    row = _make_wf(db_session, wf_id="y1", user_id="owner", source="user")
    row.manifest_json = {
        "steps": [{"agent_id": "market-research-agent", "skills": ["a"]}]
    }
    db_session.commit()

    r = client.get("/api/user-workflows/y1/workflow.yaml")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/yaml")

    import yaml as _yaml

    assert _yaml.safe_load(r.text) == row.manifest_json


def test_yaml_export_empty_manifest_returns_empty_document(api, db_session):
    client, _ = api
    _make_wf(db_session, wf_id="y2", user_id="owner", source="user")  # manifest_json is None

    r = client.get("/api/user-workflows/y2/workflow.yaml")
    assert r.status_code == 200, r.text
    assert r.text == ""


def test_yaml_export_cross_owner_is_404(api, db_session):
    client, state = api
    _make_wf(db_session, wf_id="y3", user_id="owner", source="user")
    state["user"] = _FakeUser(id="attacker")
    assert client.get("/api/user-workflows/y3/workflow.yaml").status_code == 404


# --- T23: attached_skills -> per-step migration (F-07 idempotency) ---------


def test_get_migrates_legacy_attached_skills_to_every_step(api, db_session):
    client, _ = api
    row = _make_wf(db_session, wf_id="m1", user_id="owner", source="user")
    row.attached_skills = [{"id": "skill-a", "name": "Skill A", "content": "..."}]
    row.manifest_json = {
        "steps": [
            {"agent_id": "market-research-agent"},
            {"agent_id": "swot-analyst"},
        ]
    }
    db_session.commit()

    r = client.get("/api/user-workflows/m1")
    assert r.status_code == 200, r.text

    row = db_session.query(WorkflowDefinition).filter_by(id="m1").first()
    assert row.manifest_json["steps"][0]["skills"] == ["skill-a"]
    assert row.manifest_json["steps"][1]["skills"] == ["skill-a"]
    # attached_skills is RETAINED, not dropped/nulled.
    assert row.attached_skills == [{"id": "skill-a", "name": "Skill A", "content": "..."}]


def test_get_migration_is_idempotent_on_second_read(api, db_session):
    """F-07: a second read must NOT re-append and double the skill list."""
    client, _ = api
    row = _make_wf(db_session, wf_id="m2", user_id="owner", source="user")
    row.attached_skills = [{"id": "skill-a", "name": "Skill A", "content": "..."}]
    row.manifest_json = {"steps": [{"agent_id": "market-research-agent"}]}
    db_session.commit()

    assert client.get("/api/user-workflows/m2").status_code == 200
    assert client.get("/api/user-workflows/m2").status_code == 200

    row = db_session.query(WorkflowDefinition).filter_by(id="m2").first()
    assert row.manifest_json["steps"][0]["skills"] == ["skill-a"]


def test_get_leaves_row_with_existing_per_step_skills_untouched(api, db_session):
    client, _ = api
    row = _make_wf(db_session, wf_id="m3", user_id="owner", source="user")
    row.attached_skills = [{"id": "skill-a", "name": "Skill A", "content": "..."}]
    row.manifest_json = {
        "steps": [
            {"agent_id": "market-research-agent", "skills": ["skill-b"]},
            {"agent_id": "swot-analyst"},
        ]
    }
    db_session.commit()

    assert client.get("/api/user-workflows/m3").status_code == 200

    row = db_session.query(WorkflowDefinition).filter_by(id="m3").first()
    # Untouched: neither step was rewritten by the migration.
    assert row.manifest_json["steps"][0]["skills"] == ["skill-b"]
    assert "skills" not in row.manifest_json["steps"][1]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known real bug in the already-shipped migration chain (not this "
        "test's 0021 assertion) — see CLAUDE.md's 'never edit an "
        "already-applied migration' rule, so this cannot be fixed here. "
        "Downgrading to '0020' walks every downgrade() from head down to "
        "0021 inclusive, which passes through 0029 then 0024. 0029 "
        "(alembic/versions/0029_enforce_seq_uniqueness_after_repair.py, "
        "commits f54cb775 / d2a87b7b) guardedly drops "
        "uq_run_events_scope_seq in its downgrade(); 0024's downgrade() "
        "(alembic/versions/0024_run_events_uniqueness.py) then tries to drop "
        "the SAME constraint unconditionally and raises KeyError, since "
        "downgrades run newest-first. See test_alembic.py::"
        "TestAlembicMigrations::test_downgrade_base_rolls_back_cleanly for "
        "the full analysis — same root cause, unrelated to 0021 itself."
    ),
)
def test_migration_adds_then_drops_columns():
    """Offline reversibility: 0021 adds the 2 cols on upgrade and removes them on
    downgrade (no Postgres) — proves ADDITIVE-MIGRATION reverses cleanly."""
    import os
    import tempfile

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    d = tempfile.mkdtemp()
    url = "sqlite:///" + os.path.join(d, "rev.db")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", "alembic")

    command.upgrade(cfg, "head")
    eng = create_engine(url)
    cols = {c["name"] for c in inspect(eng).get_columns("workflows")}
    assert {"base_pipeline_type", "model_overrides", "description"} <= cols

    # Downgrade to the revision immediately BEFORE the Phase-21 migration (0021)
    # so this asserts 0021's own reversibility regardless of any later migrations
    # appended after it (e.g. Phase 22's additive 0022). A bare "-1" would only
    # undo whatever the current head is, not the P21 migration under test.
    command.downgrade(cfg, "0020")
    eng2 = create_engine(url)
    cols2 = {c["name"] for c in inspect(eng2).get_columns("workflows")}
    assert not ({"base_pipeline_type", "model_overrides", "description"} & cols2)


# ---------------------------------------------------------------------------
# T36 (spec 012 R-27/R-29, AC-18) — the save contract accepts a step manifest
#
# Before T36 the canvas could compose a sub-agent tree and the API could read one
# back (T23), but nothing could WRITE one: `selections` is typed
# `dict[str, dict]`, and a manifest's `{"steps": [...]}` has a LIST value, so
# pydantic rejected it before any handler ran. `manifest` is a sibling field
# rather than a widening of `selections` — both persist into `manifest_json`,
# but they are different shapes with different validators, and telling them
# apart by sniffing is the ambiguity FINDING-02 records.
# ---------------------------------------------------------------------------


def _manifest_body(**over):
    """A POST body carrying a 012 step manifest instead of a selections map."""
    body = _valid_body()
    body.pop("selections", None)
    body["manifest"] = {
        "steps": [
            {"agent": _AGENT_A},
            {
                "agent": "custom-agent",
                "instance_id": "research-a",
                "name": "Research A",
                "prompt": "Investigate the market.",
                "skills": ["some-skill"],
            },
        ]
    }
    body.update(over)
    return body


def test_post_accepts_step_manifest_and_round_trips(api, db_session):
    """A manifest survives POST → column → GET unchanged (AC-18)."""
    client, _ = api
    r = client.post("/api/user-workflows", json=_manifest_body())
    assert r.status_code == 201, r.text
    data = r.json()
    # It comes back on `manifest`, and `selections` stays None — one column,
    # two shapes, never both populated.
    assert data["manifest"]["steps"][1]["instance_id"] == "research-a"
    assert data["manifest"]["steps"][1]["skills"] == ["some-skill"]
    assert data["selections"] is None

    row = db_session.query(WorkflowDefinition).filter_by(id=data["id"]).first()
    assert row.manifest_json["steps"][1]["name"] == "Research A"

    got = client.get(f"/api/user-workflows/{data['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["manifest"] == data["manifest"]


def test_post_accepts_synthetic_custom_agent_ids_when_manifest_present(api):
    """A composition of ONLY blank custom-agent instances (`agent-1`, `agent-2`,
    ...) must be savable — these ids are minted client-side
    (`generateInstanceId`) and never appear in `allowed_custom_agent_ids`, since
    they name no real `AGENT.md` on disk. Before this fix, every workflow built
    from the canvas's "+ Custom agent" affordance 422'd on save with
    "agent_ids not allowed for 'custom': [...]" — the coarse allow-list is the
    wrong check for a manifest-backed row; `_validated_manifest` (structural)
    plus the compiler's trust="user" checks at launch are the real boundary.
    """
    client, _ = api
    body = _manifest_body(agent_ids=["agent-1", "agent-2"], model_overrides=None)
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["agent_ids"] == ["agent-1", "agent-2"]


def test_post_rejects_manifest_and_selections_together(api):
    """Both fields write the same column — accepting both silently drops one."""
    client, _ = api
    body = _manifest_body()
    body["selections"] = {_AGENT_A: {"model": _MODEL_ID}}
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 422, r.text
    assert "mutually exclusive" in r.text


def test_post_rejects_hostile_instance_id(api):
    """F-02 at the earliest gate: instance_id becomes a filename and an agent id.

    `artifact_name` refuses these too, but that fires mid-run; refusing at SAVE
    means the user sees it while looking at the canvas.
    """
    client, _ = api
    for hostile in ("../../etc/passwd", "custom-agent:research-a", "Research-A", "-x"):
        body = _manifest_body()
        body["manifest"]["steps"][1]["instance_id"] = hostile
        r = client.post("/api/user-workflows", json=body, )
        assert r.status_code == 422, f"{hostile!r} was accepted: {r.text}"
        assert "instance_id" in r.text


def test_post_rejects_hostile_instance_id_nested_in_subagents(api):
    """The check recurses — a child node is exactly where a tree hides one."""
    client, _ = api
    body = _manifest_body()
    body["manifest"]["steps"][1]["subagents"] = {
        "mode": "parallel",
        "steps": [{"agent": "custom-agent", "instance_id": "../escape"}],
    }
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 422, r.text
    assert "instance_id" in r.text


def test_post_accepts_valid_depends_on_chain(api, db_session):
    """The happy path for the composer-derived edges (A1+A2 -> A -> B -> C).

    Backwards-only edges cannot cycle, so the compiler's `_validate_dag` accepts
    them and the manifest round-trips with `depends_on` intact.
    """
    client, _ = api
    body = _manifest_body()
    body["manifest"]["steps"] = [
        {"agent": "custom-agent", "instance_id": "step-a", "name": "A", "depends_on": []},
        {
            "agent": "custom-agent",
            "instance_id": "step-b",
            "name": "B",
            "depends_on": ["custom-agent:step-a"],
        },
    ]
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 201, r.text
    row = db_session.query(WorkflowDefinition).filter_by(id=r.json()["id"]).first()
    assert row.manifest_json["steps"][1]["depends_on"] == ["custom-agent:step-a"]


def test_post_rejects_dependency_cycle(api):
    """A cycle must never reach the DB — the compiler would refuse it at LAUNCH,
    which means the save 200s and the first run is what fails, long after the
    edit that caused it. `_compile_check_manifest` moves that to save time.
    """
    client, _ = api
    body = _manifest_body()
    body["manifest"]["steps"] = [
        {
            "agent": "custom-agent",
            "instance_id": "step-a",
            "name": "A",
            "depends_on": ["custom-agent:step-b"],
        },
        {
            "agent": "custom-agent",
            "instance_id": "step-b",
            "name": "B",
            "depends_on": ["custom-agent:step-a"],
        },
    ]
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 422, r.text
    assert "cycle" in r.text.lower(), r.text


def test_post_rejects_duplicate_instance_id(api):
    """Two steps minting the same `custom-agent:<instance_id>` collide in the
    compiled plan — the same duplicate-agent-id check `_validate_dag` runs.
    """
    client, _ = api
    body = _manifest_body()
    body["manifest"]["steps"] = [
        {"agent": "custom-agent", "instance_id": "twin", "name": "First"},
        {"agent": "custom-agent", "instance_id": "twin", "name": "Second"},
    ]
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 422, r.text
    assert "duplicate" in r.text.lower(), r.text


def test_patch_rejects_dependency_cycle(api, db_session):
    """The update path shares the same gate — a valid workflow must not be
    editable INTO an uncompilable one.
    """
    client, _ = api
    created = client.post("/api/user-workflows", json=_manifest_body())
    assert created.status_code == 201, created.text
    wid = created.json()["id"]

    r = client.patch(
        f"/api/user-workflows/{wid}",
        json={
            "manifest": {
                "steps": [
                    {
                        "agent": "custom-agent",
                        "instance_id": "step-a",
                        "depends_on": ["custom-agent:step-b"],
                    },
                    {
                        "agent": "custom-agent",
                        "instance_id": "step-b",
                        "depends_on": ["custom-agent:step-a"],
                    },
                ]
            }
        },
    )
    assert r.status_code == 422, r.text
    assert "cycle" in r.text.lower(), r.text


def test_post_rejects_empty_steps(api):
    client, _ = api
    body = _manifest_body()
    body["manifest"] = {"steps": []}
    r = client.post("/api/user-workflows", json=body)
    assert r.status_code == 422, r.text


def test_patch_replaces_the_manifest(api, db_session):
    """A manifest edit replaces the column outright."""
    client, _ = api
    created = client.post("/api/user-workflows", json=_manifest_body()).json()
    r = client.patch(
        f"/api/user-workflows/{created['id']}",
        json={"manifest": {"steps": [{"agent": _AGENT_A}]}},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["manifest"]["steps"]) == 1

    row = db_session.query(WorkflowDefinition).filter_by(id=created["id"]).first()
    assert len(row.manifest_json["steps"]) == 1


def test_selections_path_is_unaffected_by_the_new_field(api):
    """R-16 parity: a pre-012 selections save behaves exactly as before."""
    client, _ = api
    r = client.post("/api/user-workflows", json=_valid_body())
    assert r.status_code == 201, r.text
    assert r.json()["manifest"] is None
