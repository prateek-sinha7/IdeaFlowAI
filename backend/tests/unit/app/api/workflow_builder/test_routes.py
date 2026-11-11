"""Unit tests for the builder REST routes (task 16.5, design 3.2.1).

The router is mounted on a minimal app with its dependencies overridden:
``InMemoryBuilderStore`` for the store, a fake database session for the saved
workflow lookups, a recording turn starter, and a recording event bus. No
database, filesystem, network or model is used.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.workflow_builder.canonical import canonical_hash
from app.api.workflow_builder import routes, turns
from app.api.workflow_builder.admission import (
    BuilderAccess,
    get_admission_clock,
    get_capacity_gate,
    get_turn_starter,
    require_builder_access,
)
from app.api.workflow_builder.store import get_builder_store
from app.api.workflow_builder.turns import LiveTurn, register_live_turn
from app.core.config import settings
from app.models.database import get_db
from app.models.workflow_builder import MESSAGE_STATUS_FAILED
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore

MODEL = "eu.anthropic.claude-sonnet-5-5"
USER_ID = "u-1"
OTHER_USER_ID = "u-2"
BASE = "/api/workflow-builder"
CANVAS = {"steps": [{"id": "a", "agent": "custom-agent"}]}
MANIFEST = {"steps": [{"id": "a", "agent": "custom-agent", "prompt": "Write."}]}
_EDIT_BODY = {
    "mode": "edit",
    "workflow_id": "wf-1",
    "model_id": MODEL,
    "effort": "medium",
}


class _Starter:
    """A turn starter that records the turns it was asked to run."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(
        self, turn: LiveTurn, content: str, canvas_state: dict[str, Any]
    ) -> None:
        self.calls.append((turn.turn_id, content, canvas_state))


class _Bus:
    """An event bus that records what the routes publish and close."""

    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []
        self.closed: list[tuple[str, Any]] = []

    def publish(self, session_id: str, event: Any) -> None:
        self.published.append((session_id, event))

    def close_session(self, session_id: str, final: Any) -> None:
        self.closed.append((session_id, final))


class _Query:
    def __init__(self, rows: list[Any], criteria: list[Any]) -> None:
        self._rows = rows
        self._criteria = criteria

    def filter(self, *criteria: Any) -> _Query:
        self._criteria.extend(criteria)
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeDb:
    """Answers every ``query(...).filter(...).first()`` with the first saved row."""

    def __init__(self, *rows: Any) -> None:
        self.rows = list(rows)
        self.criteria: list[Any] = []

    def query(self, _model: object) -> _Query:
        return _Query(self.rows, self.criteria)

    def filtered_on(self, column: str, value: Any) -> bool:
        """True when a ``column == value`` criterion was applied to the lookup."""
        return any(
            getattr(getattr(c, "left", None), "key", None) == column
            and getattr(getattr(c, "right", None), "value", None) == value
            for c in self.criteria
        )


class _Sandbox:
    """Stands in for ``BuilderSandbox`` so a delete touches no disk."""

    deleted: list[tuple[str, str]] = []

    def __init__(self, user_id: str, session_id: str) -> None:
        self._ids = (user_id, session_id)

    def delete_session(self) -> None:
        _Sandbox.deleted.append(self._ids)


def _workflow_row(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": "wf-1",
        "name": "My workflow",
        "user_id": USER_ID,
        "source": "user",
        "manifest_json": MANIFEST,
        "base_pipeline_type": "custom",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Env:
    """One test's collaborators and helpers for setting up stored turns."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = InMemoryBuilderStore()
        self.starter = _Starter()
        self.bus = _Bus()
        self.db = _FakeDb()
        self.user_id = USER_ID
        self.clock = lambda: datetime.now(UTC)
        _Sandbox.deleted = []
        monkeypatch.setattr(routes, "get_event_bus", lambda: self.bus)
        monkeypatch.setattr(routes, "BuilderSandbox", _Sandbox)
        monkeypatch.setattr(routes, "_current_skill_hash", lambda: "skill-hash-1")

    def client(self) -> TestClient:
        app = FastAPI()
        app.include_router(routes.router)
        user = SimpleNamespace(id=self.user_id, preferred_model=None)
        access = BuilderAccess(
            user=user,  # type: ignore[arg-type]
            principal=SimpleNamespace(),  # type: ignore[arg-type]
            tier="enterprise",
        )
        overrides = app.dependency_overrides
        overrides[require_builder_access] = lambda: access
        overrides[get_builder_store] = lambda: self.store
        overrides[get_db] = lambda: self.db
        overrides[get_turn_starter] = lambda: self.starter
        overrides[get_capacity_gate] = lambda: (lambda _user: None)
        overrides[get_admission_clock] = lambda: self.clock
        return TestClient(app)

    def new_session(self, user_id: str = USER_ID, **overrides: Any) -> str:
        kwargs = BuilderSessionFactory.create_kwargs(**overrides)
        return str(self.store.create_session(user_id, **kwargs).id)

    def run_turn(
        self,
        session_id: str,
        *,
        status: str | None,
        client_message_id: str = "client-msg-0001",
        canvas_state: dict[str, Any] | None = CANVAS,
        model_id: str = MODEL,
    ) -> tuple[str, str]:
        """Store one turn and end it with ``status`` (``None`` leaves it running)."""
        begun = self.store.begin_turn(
            USER_ID,
            session_id,
            content="Make a workflow",
            canvas_state=canvas_state,
            client_message_id=client_message_id,
            model_id=model_id,
            effort="medium",
            skill_hash="skill-hash-1",
        )
        turn_id = str(begun.assistant_message.id)
        if status is not None:
            self.store.finalize_assistant(USER_ID, turn_id, status=status)
        return turn_id, str(begun.user_message.id)

    def accept_revision(
        self, session_id: str, turn_id: str, manifest: dict[str, Any]
    ) -> int:
        row = self.store.insert_revision(
            USER_ID,
            session_id,
            kind="accepted",
            manifest=manifest,
            manifest_hash=canonical_hash(manifest),
            target_trust="user",
            source_turn_id=turn_id,
        )
        return int(row.revision)  # type: ignore[arg-type]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> _Env:
    return _Env(monkeypatch)


@pytest.fixture(autouse=True)
def _clear_live_turns() -> Iterator[None]:
    yield
    turns._LIVE_TURNS.clear()


def _live(session_id: str, turn_id: str, *, user_id: str = USER_ID) -> LiveTurn:
    live = LiveTurn(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id="um-1",
        user_id=user_id,
        model_id=MODEL,
        effort=None,
    )
    register_live_turn(live)
    return live


def _code(response: Any) -> str:
    return response.json()["detail"]["code"]


# --- GET /models ------------------------------------------------------------------------


def test_list_models_returns_chat_list_with_default_and_efforts(env: _Env) -> None:
    response = env.client().get(f"{BASE}/models")

    assert response.status_code == 200
    body = response.json()
    ids = [m["id"] for m in body["models"]]
    assert ids
    assert body["default_model_id"] in ids
    assert set(body["default_efforts"]) == set(ids)


# --- POST /sessions: create and edit-mode seeding ---------------------------------------


def test_create_session_stores_empty_session_without_seed_when_create_mode(
    env: _Env,
) -> None:
    response = env.client().post(
        f"{BASE}/sessions",
        json={"mode": "create", "model_id": MODEL, "effort": "medium"},
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["mode"], body["workflow_id"], body["title"]) == (
        "create",
        None,
        "New conversation",
    )
    assert body["skill_hash"] == "skill-hash-1"
    assert body["latest_draft"] is None
    row = env.store.get_session(USER_ID, body["id"])
    assert row is not None and row.model_id == MODEL


def test_create_session_returns_422_and_stores_nothing_when_model_not_allowed(
    env: _Env,
) -> None:
    response = env.client().post(
        f"{BASE}/sessions", json={"mode": "create", "model_id": "no-such-model"}
    )

    assert response.status_code == 422
    assert _code(response) == "model_not_allowed"
    assert env.store.list_sessions(USER_ID).items == ()


def test_create_session_seeds_revision_zero_from_the_row_when_edit_mode(
    env: _Env,
) -> None:
    env.db = _FakeDb(_workflow_row())

    response = env.client().post(
        f"{BASE}/sessions",
        json=_EDIT_BODY,
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["mode"], body["workflow_id"]) == ("edit", "wf-1")
    assert body["title"] == "Edit: My workflow"
    assert body["target_trust"] == "db"  # enterprise may run custom
    assert body["latest_draft"]["revision"] == 0
    assert body["latest_draft"]["kind"] == "seed"
    assert body["latest_draft"]["manifest"] == MANIFEST
    assert body["linked_row_changed"] is False
    row = env.store.get_session(USER_ID, body["id"])
    assert row is not None
    assert row.linked_manifest_hash == canonical_hash(MANIFEST)
    assert env.db.filtered_on("user_id", USER_ID)  # ownership is part of the lookup
    assert env.db.filtered_on("source", "user")


def test_create_session_returns_404_and_stores_nothing_when_workflow_not_owned(
    env: _Env,
) -> None:
    env.db = _FakeDb()  # the owner-scoped lookup finds no row

    response = env.client().post(
        f"{BASE}/sessions",
        json={**_EDIT_BODY, "workflow_id": "wf-9"},
    )

    assert response.status_code == 404
    assert _code(response) == "workflow_not_found"
    assert env.store.list_sessions(USER_ID).items == ()


def test_create_session_cuts_the_edit_title_to_sixty_characters(env: _Env) -> None:
    env.db = _FakeDb(_workflow_row(name="N" * 100))

    response = env.client().post(
        f"{BASE}/sessions",
        json=_EDIT_BODY,
    )

    assert response.json()["title"] == ("Edit: " + "N" * 100)[:60]


def test_create_session_rejects_edit_mode_without_workflow_id(env: _Env) -> None:
    response = env.client().post(
        f"{BASE}/sessions", json={"mode": "edit", "model_id": MODEL}
    )

    assert response.status_code == 422
    assert env.store.list_sessions(USER_ID).items == ()


# --- effective_manifest -----------------------------------------------------------------


def test_effective_manifest_uses_the_stored_step_manifest_as_a_copy() -> None:
    row = _workflow_row()

    result = routes.effective_manifest(row)  # type: ignore[arg-type]

    assert result == MANIFEST
    result["steps"].append("changed")
    assert row.manifest_json == MANIFEST


@pytest.mark.parametrize("stored", [None, {}, {"a1": {"model": "m"}}, "text"])
def test_effective_manifest_starts_from_empty_canvas_when_no_step_manifest(
    stored: Any,
) -> None:
    row = _workflow_row(manifest_json=stored)

    assert routes.effective_manifest(row) == {"steps": []}  # type: ignore[arg-type]


def test_effective_manifest_adds_base_defaults_only_for_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_base_pipeline_defaults",
        lambda base: {
            "deliverable": {"strategy": "file", "name": "base.md"},
            "planner": "base-planner",
            "clarify": {"mode": "ask", "defaults": []},
        },
    )
    row = _workflow_row(
        manifest_json={**MANIFEST, "planner": "mine"}, base_pipeline_type="prototype"
    )

    result = routes.effective_manifest(row)  # type: ignore[arg-type]

    assert result["planner"] == "mine"
    assert result["deliverable"] == {"strategy": "file", "name": "base.md"}
    assert result["clarify"] == {"mode": "ask", "defaults": []}


def test_effective_manifest_loads_no_base_when_base_is_custom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(base: str) -> dict[str, Any]:
        raise AssertionError("a custom base must not load a base manifest")

    monkeypatch.setattr(routes, "_base_pipeline_defaults", fail)

    assert routes.effective_manifest(_workflow_row()) == MANIFEST  # type: ignore[arg-type]


def test_base_pipeline_defaults_returns_empty_when_base_manifest_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("gone")

    monkeypatch.setattr("agents.workflows.manifest.load_manifest", broken)

    assert routes._base_pipeline_defaults("prototype") == {}


# --- GET / list / link / delete ---------------------------------------------------------


def test_get_session_returns_transcript_in_order(env: _Env) -> None:
    session_id = env.new_session()
    env.run_turn(session_id, status="completed")

    response = env.client().get(f"{BASE}/sessions/{session_id}")

    assert response.status_code == 200
    assert [m["role"] for m in response.json()["messages"]] == ["user", "assistant"]


def test_get_session_returns_404_when_session_belongs_to_other_user(env: _Env) -> None:
    session_id = env.new_session(OTHER_USER_ID)

    response = env.client().get(f"{BASE}/sessions/{session_id}")

    assert response.status_code == 404
    assert _code(response) == "session_not_found"


def test_get_session_flags_linked_row_changed_when_saved_manifest_differs(
    env: _Env,
) -> None:
    session_id = env.new_session(
        workflow_id="wf-1", linked_manifest_hash=canonical_hash(MANIFEST)
    )
    env.db = _FakeDb(_workflow_row(manifest_json={"steps": []}))

    response = env.client().get(f"{BASE}/sessions/{session_id}")

    assert response.json()["linked_row_changed"] is True


def test_list_sessions_returns_422_when_cursor_is_invalid(env: _Env) -> None:
    response = env.client().get(f"{BASE}/sessions", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert _code(response) == "invalid_cursor"


def test_link_session_stores_hash_of_owned_workflow(env: _Env) -> None:
    session_id = env.new_session()
    env.db = _FakeDb(_workflow_row())

    response = env.client().post(
        f"{BASE}/sessions/{session_id}/link", json={"workflow_id": "wf-1"}
    )

    assert response.status_code == 200
    row = env.store.get_session(USER_ID, session_id)
    assert row is not None
    assert (row.workflow_id, row.linked_manifest_hash) == (
        "wf-1",
        canonical_hash(MANIFEST),
    )


def test_link_session_returns_404_and_leaves_link_when_workflow_not_owned(
    env: _Env,
) -> None:
    session_id = env.new_session()

    response = env.client().post(
        f"{BASE}/sessions/{session_id}/link", json={"workflow_id": "wf-9"}
    )

    assert response.status_code == 404
    assert _code(response) == "workflow_not_found"
    row = env.store.get_session(USER_ID, session_id)
    assert row is not None and row.workflow_id is None


def test_delete_session_stops_turn_removes_rows_and_sandbox_and_closes_streams(
    env: _Env,
) -> None:
    session_id = env.new_session()
    turn_id, _ = env.run_turn(session_id, status=None)
    live = _live(session_id, turn_id)

    response = env.client().delete(f"{BASE}/sessions/{session_id}")

    assert response.status_code == 204
    assert live.stop_reason == "deleted"
    assert env.store.get_session(USER_ID, session_id) is None
    assert _Sandbox.deleted == [(USER_ID, session_id)]
    assert [(sid, type(ev).__name__) for sid, ev in env.bus.closed] == [
        (session_id, "SessionDeleted")
    ]


def test_delete_session_returns_404_and_changes_nothing_when_session_not_owned(
    env: _Env,
) -> None:
    session_id = env.new_session(OTHER_USER_ID)
    live = _live(session_id, "t-1", user_id=OTHER_USER_ID)

    response = env.client().delete(f"{BASE}/sessions/{session_id}")

    assert response.status_code == 404
    assert env.store.get_session(OTHER_USER_ID, session_id) is not None
    assert live.stop_reason is None
    assert _Sandbox.deleted == []
    assert env.bus.closed == []


# --- POST /sessions/{id}/undo -----------------------------------------------------------


def _accepted_turn(env: _Env) -> tuple[str, str, int]:
    """A session whose latest AI change started from ``CANVAS``: (session, turn, rev)."""
    session_id = env.new_session()
    turn_id, _ = env.run_turn(session_id, status="completed", canvas_state=CANVAS)
    return session_id, turn_id, env.accept_revision(session_id, turn_id, MANIFEST)


def _undo(env: _Env, session_id: str, expected: int) -> Any:
    return env.client().post(
        f"{BASE}/sessions/{session_id}/undo", json={"expected_revision": expected}
    )


def test_undo_stores_undo_revision_from_starting_canvas_and_publishes_draft_restored(
    env: _Env,
) -> None:
    session_id, turn_id, revision = _accepted_turn(env)

    response = _undo(env, session_id, revision)

    assert response.status_code == 200
    body = response.json()
    assert (body["kind"], body["revision"]) == ("undo", revision + 1)
    assert body["manifest"] == CANVAS
    assert body["source_turn_id"] == turn_id
    stored = env.store.get_latest_revisions(USER_ID, session_id).undo
    assert stored is not None and stored.undo_of_revision == revision
    [(published_to, event)] = env.bus.published
    assert published_to == session_id
    assert (type(event).__name__, event.revision, event.manifest) == (
        "DraftRestored",
        revision + 1,
        CANVAS,
    )


def _assert_undo_refused_as_stale(env: _Env, session_id: str, expected: int) -> None:
    before = env.store.get_latest_revisions(USER_ID, session_id)

    response = _undo(env, session_id, expected)

    assert response.status_code == 409
    assert _code(response) == "undo_stale"
    assert env.store.get_latest_revisions(USER_ID, session_id) == before
    assert env.bus.published == []


@pytest.mark.parametrize("offset", [-1, 1])
def test_undo_returns_409_when_expected_revision_is_not_the_latest(
    env: _Env, offset: int
) -> None:
    session_id, _turn_id, revision = _accepted_turn(env)

    _assert_undo_refused_as_stale(env, session_id, revision + offset)


def test_undo_returns_409_when_a_newer_unproposed_revision_exists(env: _Env) -> None:
    session_id, _turn_id, revision = _accepted_turn(env)
    env.store.insert_revision(
        USER_ID,
        session_id,
        kind="unproposed",
        manifest=MANIFEST,
        manifest_hash=canonical_hash(MANIFEST),
    )

    _assert_undo_refused_as_stale(env, session_id, revision)


def test_undo_returns_409_when_the_change_was_already_undone(env: _Env) -> None:
    session_id, _turn_id, revision = _accepted_turn(env)
    assert _undo(env, session_id, revision).status_code == 200
    env.bus.published.clear()

    _assert_undo_refused_as_stale(env, session_id, revision)
    _assert_undo_refused_as_stale(env, session_id, revision + 1)


def test_undo_returns_409_when_only_the_seed_revision_exists(env: _Env) -> None:
    session_id = env.new_session(seed_manifest=MANIFEST, seed_manifest_hash="h")

    _assert_undo_refused_as_stale(env, session_id, 0)


def test_undo_returns_409_when_starting_message_has_no_canvas_state(env: _Env) -> None:
    session_id = env.new_session()
    turn_id, _ = env.run_turn(session_id, status="completed", canvas_state=None)
    revision = env.accept_revision(session_id, turn_id, MANIFEST)

    _assert_undo_refused_as_stale(env, session_id, revision)


def test_undo_returns_409_turn_running_when_a_turn_is_stored_as_running(
    env: _Env,
) -> None:
    session_id, _turn_id, revision = _accepted_turn(env)
    env.run_turn(session_id, status=None, client_message_id="client-msg-0002")

    response = _undo(env, session_id, revision)

    assert response.status_code == 409
    assert _code(response) == "turn_running"


def test_undo_returns_409_turn_running_when_a_live_turn_is_registered(
    env: _Env,
) -> None:
    session_id, _turn_id, revision = _accepted_turn(env)
    _live(session_id, "t-live")

    response = _undo(env, session_id, revision)

    assert response.status_code == 409
    assert _code(response) == "turn_running"
    assert env.bus.published == []


def test_undo_returns_404_when_session_belongs_to_other_user(env: _Env) -> None:
    session_id = env.new_session(OTHER_USER_ID)

    response = _undo(env, session_id, 1)

    assert response.status_code == 404
    assert _code(response) == "session_not_found"


def test_undo_returns_422_when_expected_revision_is_negative(env: _Env) -> None:
    session_id = env.new_session()

    assert _undo(env, session_id, -1).status_code == 422


# --- POST /sessions/{id}/turns/{turn_id}/retry ------------------------------------------


def _retry(env: _Env, session_id: str, turn_id: str) -> Any:
    return env.client().post(f"{BASE}/sessions/{session_id}/turns/{turn_id}/retry")


def test_retry_starts_new_turn_on_the_same_user_message_when_latest_turn_failed(
    env: _Env,
) -> None:
    session_id = env.new_session()
    failed_id, user_message_id = env.run_turn(session_id, status=MESSAGE_STATUS_FAILED)

    response = _retry(env, session_id, failed_id)

    assert response.status_code == 202
    body = response.json()
    assert body["turn_id"] != failed_id
    assert body["message_id"] == user_message_id
    assert body["replayed"] is False
    rows = env.store.list_messages(USER_ID, session_id)
    assert [r.role for r in rows] == ["user", "assistant", "assistant"]
    assert env.starter.calls == [(body["turn_id"], "Make a workflow", CANVAS)]


@pytest.mark.parametrize(
    "status", ["completed", "cancelled", "timed_out", "interrupted"]
)
def test_retry_returns_409_when_latest_turn_did_not_fail(
    env: _Env, status: str
) -> None:
    session_id = env.new_session()
    turn_id, _ = env.run_turn(session_id, status=status)

    response = _retry(env, session_id, turn_id)

    assert response.status_code == 409
    assert _code(response) == "retry_not_allowed"
    assert env.starter.calls == []


def test_retry_returns_409_when_the_failed_turn_is_not_the_latest(env: _Env) -> None:
    session_id = env.new_session()
    old_id, _ = env.run_turn(session_id, status=MESSAGE_STATUS_FAILED)
    env.run_turn(session_id, status="completed", client_message_id="client-msg-0002")

    response = _retry(env, session_id, old_id)

    assert response.status_code == 409
    assert _code(response) == "retry_not_allowed"
    assert len(env.store.list_messages(USER_ID, session_id)) == 4


def test_retry_returns_409_when_turn_id_names_no_turn_of_the_session(env: _Env) -> None:
    session_id = env.new_session()
    env.run_turn(session_id, status=MESSAGE_STATUS_FAILED)

    assert _code(_retry(env, session_id, "no-such-turn")) == "retry_not_allowed"


def test_retry_returns_409_when_the_original_message_has_no_canvas_state(
    env: _Env,
) -> None:
    session_id = env.new_session()
    turn_id, _ = env.run_turn(
        session_id, status=MESSAGE_STATUS_FAILED, canvas_state=None
    )

    assert _code(_retry(env, session_id, turn_id)) == "retry_not_allowed"


def test_retry_returns_409_turn_running_when_a_turn_is_running(env: _Env) -> None:
    session_id = env.new_session()
    running_id, _ = env.run_turn(session_id, status=None)

    response = _retry(env, session_id, running_id)

    assert response.status_code == 409
    assert _code(response) == "turn_running"


def test_retry_runs_the_same_admission_checks_as_a_new_message(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = env.new_session()
    failed_id, _ = env.run_turn(session_id, status=MESSAGE_STATUS_FAILED)
    monkeypatch.setattr(settings, "BUILDER_MAX_TURNS_PER_SESSION", 0)

    response = _retry(env, session_id, failed_id)

    assert response.status_code == 409
    assert _code(response) == "session_turn_limit"
    assert len(env.store.list_messages(USER_ID, session_id)) == 2


def test_retry_returns_422_when_the_original_model_is_no_longer_allowed(
    env: _Env,
) -> None:
    session_id = env.new_session()
    turn_id, _ = env.run_turn(session_id, status=MESSAGE_STATUS_FAILED, model_id="gone")

    response = _retry(env, session_id, turn_id)

    assert response.status_code == 422
    assert _code(response) == "model_not_allowed"


def test_retry_returns_404_when_session_belongs_to_other_user(env: _Env) -> None:
    session_id = env.new_session(OTHER_USER_ID)

    assert _retry(env, session_id, "t-1").status_code == 404


# --- POST /sessions/{id}/turns/{turn_id}/cancel -----------------------------------------


def _cancel(env: _Env, session_id: str, turn_id: str) -> Any:
    return env.client().post(f"{BASE}/sessions/{session_id}/turns/{turn_id}/cancel")


def test_cancel_returns_202_cancelling_and_stops_the_live_turn(env: _Env) -> None:
    session_id = env.new_session()
    live = _live(session_id, "t-1")

    response = _cancel(env, session_id, "t-1")

    assert response.status_code == 202
    assert response.json() == {"state": "cancelling"}
    assert live.stop_reason == "cancelled"


def test_cancel_returns_200_not_running_when_the_session_has_no_live_turn(
    env: _Env,
) -> None:
    session_id = env.new_session()

    response = _cancel(env, session_id, "t-1")

    assert response.status_code == 200
    assert response.json() == {"state": "not_running"}


def test_cancel_returns_200_not_running_when_turn_id_is_not_the_live_turn(
    env: _Env,
) -> None:
    session_id = env.new_session()
    live = _live(session_id, "t-1")

    response = _cancel(env, session_id, "t-other")

    assert (response.status_code, response.json()) == (200, {"state": "not_running"})
    assert live.stop_reason is None


def test_cancel_returns_200_not_running_when_turn_is_already_storing_its_end(
    env: _Env,
) -> None:
    session_id = env.new_session()
    live = _live(session_id, "t-1")
    live.finalizing = True

    response = _cancel(env, session_id, "t-1")

    assert (response.status_code, response.json()) == (200, {"state": "not_running"})
    assert live.stop_reason is None


def test_cancel_is_harmless_when_repeated(env: _Env) -> None:
    session_id = env.new_session()
    live = _live(session_id, "t-1")

    first = _cancel(env, session_id, "t-1")
    second = _cancel(env, session_id, "t-1")

    assert (first.status_code, second.status_code) == (202, 202)
    assert live.stop_reason == "cancelled"


def test_cancel_returns_404_and_leaves_turn_when_session_belongs_to_other_user(
    env: _Env,
) -> None:
    session_id = env.new_session(OTHER_USER_ID)
    live = _live(session_id, "t-1", user_id=OTHER_USER_ID)

    response = _cancel(env, session_id, "t-1")

    assert response.status_code == 404
    assert _code(response) == "session_not_found"
    assert live.stop_reason is None
