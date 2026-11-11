"""AI Workflow Builder session endpoints against real PostgreSQL (task 22.3).

Covers Req 2.9, 2.10, 8.5, 12.6, 20.13, 20.14, 20.15, 31.2 and 49.4 through the
real router, ``BuilderStore`` and Alembic-migrated tables:

* create in both modes: a create session starts empty; an edit session stores the
  row's effective manifest as revision 0 (a ``custom`` base as stored, a base that
  is not ``custom`` with ``deliverable``, ``planner`` and ``clarify`` filled in from
  the base pipeline); an edit request for a workflow the caller does not own creates
  no session and no revision (Req 20.13 to 20.15);
* list: own sessions only, newest first, keyset pages (Req 2.8, 31.1);
* get: transcript with tool activity, latest draft, a newer unproposed revision,
  the running-turn snapshot and the linked-row change flag (Req 12.6);
* delete: rows and sandbox removed, a running turn stopped first, a foreign
  session left alone (Req 31.2, 31.3);
* link: owned workflow linked, foreign or missing workflow refused with the
  session unchanged (Req 2.9, 2.10);
* undo: stores an ``undo`` revision from the starting message's ``canvas_state``,
  refuses a stale request and a running turn (Req 8.5);
* retry: reuses the stored user message of the latest failed turn (G-01);
* cancel: ``cancelling`` for the live turn, ``not_running`` otherwise.

Only the model is faked. ``FakeTurnStarter`` replaces ``run_turn``: it parks an
asyncio task for each admitted turn and, when the turn is stopped, stores the end
state the real ``finalize_turn`` would store. Turn behaviour itself belongs to
``test_workflow_builder_turns_api.py`` (task 22.4).

Database: a private throwaway PostgreSQL database upgraded to Alembic head, from
the testcontainers server of ``tests/integration/conftest.py`` (Docker, errors at
setup without it) or from ``PYTEST_POSTGRES_ADMIN_URL``. Never SQLite. These tests
run on the Docker-capable CI runner; locally they only collect.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import agents.workflows.manifest as manifest_module
from agents.workflows.manifest import load_manifest
from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.api.workflow_builder import router
from app.api.workflow_builder.admission import (
    BuilderReadiness,
    get_builder_readiness,
    get_capacity_gate,
    get_turn_starter,
)
from app.api.workflow_builder.store import BuilderStore
from app.api.workflow_builder.turns import (
    LiveTurn,
    attach_task,
    get_live_turn,
    release_live_turn,
)
from app.core.config import settings
from app.core.dependencies import get_current_principal
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_builder import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_CANCELLED,
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_RUNNING,
    MESSAGE_STATUS_TOOL_OK,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

_API = "/api/workflow-builder"
_BASE_WITH_SETTINGS = "prototype"
_EMPTY_CANVAS: dict[str, Any] = {"steps": []}
_CANVAS_BEFORE: dict[str, Any] = {"steps": [{"id": "draft-a", "agent": "custom-agent"}]}
_CANVAS_AFTER: dict[str, Any] = {
    "steps": [
        {"id": "draft-a", "agent": "custom-agent"},
        {"id": "draft-b", "agent": "custom-agent"},
    ]
}
_WAIT_SECONDS = 5.0


# --- Fakes -----------------------------------------------------------------------------


class FakeTurnStarter:
    """Stands in for ``run_turn``: parks a task per turn and finalises it when stopped.

    Records each call so a test can check what the turn would have been given. When
    the task is cancelled for any reason except ``deleted`` it stores ``cancelled``,
    as ``finalize_turn`` does; a ``deleted`` turn stores nothing, because its rows
    are going away. The live turn is released either way.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.calls: list[tuple[LiveTurn, str, dict[str, Any]]] = []
        self.tasks: list[asyncio.Task[None]] = []

    def __call__(
        self, turn: LiveTurn, content: str, canvas_state: dict[str, Any]
    ) -> None:
        self.calls.append((turn, content, canvas_state))
        task = asyncio.get_running_loop().create_task(self._run(turn))
        self.tasks.append(task)
        attach_task(turn, task)

    async def _run(self, turn: LiveTurn) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if turn.stop_reason != "deleted":
                await asyncio.to_thread(self._finalize, turn)
        finally:
            release_live_turn(turn)

    def _finalize(self, turn: LiveTurn) -> None:
        with self._session_factory() as db:
            BuilderStore(db).finalize_assistant(
                turn.user_id,
                turn.turn_id,
                status=MESSAGE_STATUS_CANCELLED,
                stop_reason="cancelled",
            )


async def _cancel_all(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


# --- Harness ---------------------------------------------------------------------------


class ApiHarness:
    """The app under test, the database behind it and the caller switch."""

    def __init__(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        state: dict[str, Any],
        starter: FakeTurnStarter,
        sandbox_root: Path,
    ) -> None:
        self.client = client
        self.session_factory = session_factory
        self.starter = starter
        self.sandbox_root = sandbox_root
        self._state = state
        self._choice: dict[str, Any] | None = None

    @property
    def user(self) -> User:
        """The current caller."""
        user = self._state["user"]
        assert user is not None, "the test did not call act_as()"
        return user

    # --- callers and rows ---

    def new_user(self, tier: str = "enterprise") -> User:
        """Insert a ``users`` row (sessions reference it) and return it, detached."""
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=f"{user_id}@example.test",
            cognito_sub=f"sub-{user_id}",
            tier=tier,
        )
        with self.session_factory() as db:
            db.add(user)
            db.commit()
        return user

    def act_as(self, user: User) -> User:
        """Make ``user`` the caller of every following request."""
        self._state["user"] = user
        return user

    def add_workflow(
        self,
        user_id: str,
        *,
        name: str = "Saved workflow",
        base_pipeline_type: str = "custom",
        manifest_json: dict[str, Any] | None = None,
    ) -> str:
        """Insert a saved ``workflows`` row (``source="user"``) and return its id."""
        workflow_id = str(uuid.uuid4())
        with self.session_factory() as db:
            db.add(
                WorkflowDefinition(
                    id=workflow_id,
                    user_id=user_id,
                    owner_id=user_id,
                    workspace_id=user_id,
                    name=name,
                    agents="[]",
                    artifact_edges="[]",
                    source="user",
                    base_pipeline_type=base_pipeline_type,
                    manifest_json=manifest_json,
                )
            )
            db.commit()
        return workflow_id

    def set_workflow_manifest(self, workflow_id: str, manifest: dict[str, Any]) -> None:
        """Replace a saved row's manifest, as a save from the Composer would."""
        with self.session_factory() as db:
            db.execute(
                update(WorkflowDefinition)
                .where(WorkflowDefinition.id == workflow_id)
                .values(manifest_json=manifest)
            )
            db.commit()

    @contextmanager
    def store(self) -> Generator[BuilderStore, None, None]:
        """A ``BuilderStore`` on its own DB session, for seeding and reading rows."""
        with self.session_factory() as db:
            yield BuilderStore(db)

    @contextmanager
    def db(self) -> Generator[Session, None, None]:
        """A plain DB session for counting rows."""
        with self.session_factory() as db:
            yield db

    def count(self, model: type, **where: Any) -> int:
        """Count rows of ``model`` whose columns equal ``where``."""
        stmt = select(func.count()).select_from(model)
        for column, value in where.items():
            stmt = stmt.where(getattr(model, column) == value)
        with self.db() as db:
            return int(db.execute(stmt).scalar_one())

    # --- requests ---

    def choice(self) -> dict[str, Any]:
        """A model and effort the caller's tier may use, from ``GET /models``."""
        if self._choice is None:
            response = self.client.get(f"{_API}/models")
            assert response.status_code == 200, response.text
            body = response.json()
            model_id = body["default_model_id"]
            self._choice = {
                "model_id": model_id,
                "effort": body["default_efforts"].get(model_id),
            }
        return dict(self._choice)

    def create_session(self, **body: Any) -> dict[str, Any]:
        """``POST /sessions`` (create mode by default); assert 201 and return the body."""
        payload = {"mode": "create", **self.choice(), **body}
        response = self.client.post(f"{_API}/sessions", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    def get_session(self, session_id: str) -> dict[str, Any]:
        """``GET /sessions/{id}``; assert 200 and return the body."""
        response = self.client.get(f"{_API}/sessions/{session_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def send_message(
        self,
        session_id: str,
        *,
        content: str = "Build me a research workflow",
        canvas_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """``POST /messages``; assert 202 and return ``TurnAccepted``."""
        response = self.client.post(
            f"{_API}/sessions/{session_id}/messages",
            json={
                "content": content,
                "canvas_state": canvas_state or _EMPTY_CANVAS,
                "client_message_id": f"cid-{uuid.uuid4().hex[:16]}",
                **self.choice(),
            },
        )
        assert response.status_code == 202, response.text
        return response.json()

    # --- direct seeding through the store ---

    def seed_turn(
        self,
        user_id: str,
        session_id: str,
        *,
        status: str,
        canvas_state: dict[str, Any] | None = None,
        content: str = "Make the change",
        accepted_manifest: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Store one finished turn: user row, assistant row, optional accepted revision."""
        choice = self.choice()
        with self.store() as store:
            session = store.get_session(user_id, session_id)
            assert session is not None
            begun = store.begin_turn(
                user_id,
                session_id,
                content=content,
                canvas_state=canvas_state or _EMPTY_CANVAS,
                client_message_id=f"cid-{uuid.uuid4().hex[:16]}",
                model_id=choice["model_id"],
                effort=choice["effort"],
                skill_hash=str(session.skill_hash),
                first_message_title=content[:60],
            )
            turn_id = str(begun.assistant_message.id)
            revision: int | None = None
            if accepted_manifest is not None:
                row = store.insert_revision(
                    user_id,
                    session_id,
                    kind="accepted",
                    manifest=accepted_manifest,
                    manifest_hash=canonical_hash(accepted_manifest),
                    target_trust="user",
                    launch_needs=[],
                    source_turn_id=turn_id,
                    source_file="/workflows/draft.workflow.json",
                )
                revision = int(row.revision)  # type: ignore[arg-type]
            store.finalize_assistant(
                user_id,
                turn_id,
                status=status,
                outcome="draft" if revision is not None else None,
                stop_reason="error" if status == MESSAGE_STATUS_FAILED else None,
                error_code="turn_failed" if status == MESSAGE_STATUS_FAILED else None,
                revision=revision,
            )
            return {
                "turn_id": turn_id,
                "user_message_id": str(begun.user_message.id),
            }


def _wait_for(predicate: Callable[[], bool], timeout: float = _WAIT_SECONDS) -> bool:
    """Poll ``predicate`` until it is true or ``timeout`` seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _error_code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


# --- Fixtures --------------------------------------------------------------------------


@pytest.fixture
def api(
    builder_pg_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[ApiHarness, None, None]:
    """The builder router over real PostgreSQL, with a fake turn starter.

    Authentication, readiness, the capacity gate and the turn starter are
    overridden; the access dependency, routes, admission and store are real. The
    sandbox root is a folder under ``tmp_path``.
    """
    sandbox_root = tmp_path / "builder"
    monkeypatch.setattr(settings, "BUILDER_SANDBOX_ROOT", str(sandbox_root))

    session_factory: sessionmaker[Session] = sessionmaker(
        bind=builder_pg_engine, autoflush=False, expire_on_commit=False
    )
    starter = FakeTurnStarter(session_factory)
    readiness = BuilderReadiness()
    readiness.mark_ready()
    state: dict[str, Any] = {"user": None}

    def override_principal() -> tuple[User, Any]:
        user = state["user"]
        assert user is not None, "the test did not call act_as()"
        return user, principal_for(user)

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_principal] = override_principal
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_builder_readiness] = lambda: readiness
    app.dependency_overrides[get_capacity_gate] = lambda: (lambda _user: None)
    app.dependency_overrides[get_turn_starter] = lambda: starter

    with TestClient(app) as client:
        harness = ApiHarness(client, session_factory, state, starter, sandbox_root)
        try:
            yield harness
        finally:
            if starter.tasks:
                assert client.portal is not None
                client.portal.call(_cancel_all, starter.tasks)
            for turn, _content, _canvas in starter.calls:
                release_live_turn(turn)


# --- Create ----------------------------------------------------------------------------


def test_create_session_returns_empty_session_when_mode_is_create(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())

    body = api.create_session()

    assert body["mode"] == "create"
    assert body["workflow_id"] is None
    assert body["title"] == "New conversation"
    assert body["messages"] == []
    assert body["latest_draft"] is None
    assert body["latest_unproposed"] is None
    assert body["running_turn"] is None
    assert body["running"] is False
    assert body["target_trust"] == "user"
    assert str(body["skill_hash"]).startswith("sha256:")
    assert body["model_id"] == api.choice()["model_id"]
    with api.db() as db:
        row = db.get(WorkflowBuilderSession, body["id"])
        assert row is not None
        assert (row.user_id, row.owner_id, row.workspace_id) == (user.id,) * 3
    assert api.count(WorkflowBuilderDraft, session_id=body["id"]) == 0


def test_create_session_stores_revision_zero_when_edit_row_has_custom_base(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    manifest = {
        "steps": [{"id": "research", "agent": "market-research-agent"}],
        "planner": "skip",
    }
    workflow_id = api.add_workflow(
        user.id, name="Competitive research", manifest_json=manifest
    )

    body = api.create_session(mode="edit", workflow_id=workflow_id)

    assert body["mode"] == "edit"
    assert body["workflow_id"] == workflow_id
    assert body["title"] == "Edit: Competitive research"
    assert body["latest_draft"]["revision"] == 0
    assert body["latest_draft"]["kind"] == "seed"
    assert body["latest_draft"]["manifest"] == manifest
    assert body["linked_row_changed"] is False
    assert api.count(WorkflowBuilderDraft, session_id=body["id"]) == 1
    with api.db() as db:
        row = db.get(WorkflowBuilderSession, body["id"])
        assert row is not None
        assert row.linked_manifest_hash == canonical_hash(manifest)


def test_create_session_fills_base_settings_when_edit_row_base_is_not_custom(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    base = load_manifest(_BASE_WITH_SETTINGS, Path(manifest_module.__file__).parent)
    workflow_id = api.add_workflow(
        user.id, base_pipeline_type=_BASE_WITH_SETTINGS, manifest_json=None
    )

    body = api.create_session(mode="edit", workflow_id=workflow_id)

    seed = body["latest_draft"]
    assert seed["revision"] == 0
    assert seed["kind"] == "seed"
    assert seed["manifest"]["steps"] == []
    assert seed["manifest"]["deliverable"] == base.deliverable
    assert seed["manifest"]["planner"] == base.planner
    assert seed["manifest"]["clarify"] == base.clarify


def test_create_session_keeps_row_settings_when_edit_row_already_declares_them(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    base = load_manifest(_BASE_WITH_SETTINGS, Path(manifest_module.__file__).parent)
    assert base.planner != "skip", "pick a base whose planner differs from the row's"
    stored = {"steps": [], "planner": "skip"}
    workflow_id = api.add_workflow(
        user.id, base_pipeline_type=_BASE_WITH_SETTINGS, manifest_json=stored
    )

    manifest = api.create_session(mode="edit", workflow_id=workflow_id)["latest_draft"][
        "manifest"
    ]

    assert manifest["planner"] == "skip"
    assert manifest["deliverable"] == base.deliverable
    assert manifest["clarify"] == base.clarify


@pytest.mark.parametrize("target", ["other_users_row", "missing_row"])
def test_create_session_returns_404_and_stores_nothing_when_workflow_not_owned(
    api: ApiHarness, target: str
) -> None:
    owner = api.new_user()
    caller = api.act_as(api.new_user())
    workflow_id = (
        api.add_workflow(owner.id, manifest_json=_EMPTY_CANVAS)
        if target == "other_users_row"
        else str(uuid.uuid4())
    )

    response = api.client.post(
        f"{_API}/sessions",
        json={"mode": "edit", "workflow_id": workflow_id, **api.choice()},
    )

    assert response.status_code == 404
    assert _error_code(response) == "workflow_not_found"
    assert api.count(WorkflowBuilderSession, user_id=caller.id) == 0
    assert api.count(WorkflowBuilderDraft, user_id=caller.id) == 0


# --- List ------------------------------------------------------------------------------


def test_list_sessions_returns_own_sessions_newest_first_when_paged(
    api: ApiHarness,
) -> None:
    api.act_as(api.new_user())
    other_id = api.create_session()["id"]
    api.act_as(api.new_user())
    ids = [api.create_session()["id"] for _ in range(3)]

    first = api.client.get(f"{_API}/sessions", params={"limit": 2}).json()
    assert [item["id"] for item in first["items"]] == [ids[2], ids[1]]
    assert first["next_cursor"]
    second = api.client.get(
        f"{_API}/sessions", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()

    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None
    assert other_id not in [i["id"] for i in first["items"] + second["items"]]


def test_list_sessions_returns_422_when_cursor_is_malformed(api: ApiHarness) -> None:
    api.act_as(api.new_user())

    response = api.client.get(f"{_API}/sessions", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert _error_code(response) == "invalid_cursor"


# --- Get -------------------------------------------------------------------------------


def test_get_session_returns_transcript_and_drafts_when_session_has_a_turn(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    seeded = api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        canvas_state=_CANVAS_BEFORE,
        accepted_manifest=_CANVAS_AFTER,
    )
    with api.store() as store:
        store.insert_tool_row(
            user.id,
            session_id,
            seeded["turn_id"],
            status=MESSAGE_STATUS_TOOL_OK,
            content="ok",
            tool={
                "call_id": "call-1",
                "tool": "read_file",
                "kind": "read",
                "label": "Read file",
                "duration_ms": 5,
                "summary": "Read file.",
            },
        )

    body = api.get_session(session_id)

    user_message, assistant = body["messages"]
    assert (user_message["role"], assistant["role"]) == ("user", "assistant")
    assert user_message["id"] == seeded["user_message_id"]
    assert assistant["id"] == seeded["turn_id"]
    assert assistant["reply_to_message_id"] == seeded["user_message_id"]
    assert assistant["status"] == "completed"
    assert assistant["outcome"] == "draft"
    assert assistant["revision"] == 1
    assert [a["call_id"] for a in assistant["activity"]] == ["call-1"]
    assert body["latest_draft"]["revision"] == 1
    assert body["latest_draft"]["kind"] == "accepted"
    assert body["latest_draft"]["manifest"] == _CANVAS_AFTER
    assert body["latest_unproposed"] is None
    assert body["running_turn"] is None
    assert body["title"] == "Make the change"


def test_get_session_returns_unproposed_revision_when_it_is_newer_than_the_draft(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    seeded = api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        accepted_manifest=_CANVAS_BEFORE,
    )
    with api.store() as store:
        store.insert_revision(
            user.id,
            session_id,
            kind="unproposed",
            manifest=_CANVAS_AFTER,
            manifest_hash=canonical_hash(_CANVAS_AFTER),
            source_turn_id=seeded["turn_id"],
            source_file="/workflows/draft.workflow.json",
        )

    body = api.get_session(session_id)

    assert body["latest_draft"]["revision"] == 1
    assert body["latest_unproposed"]["revision"] == 2
    assert body["latest_unproposed"]["manifest"] == _CANVAS_AFTER


def test_get_session_omits_unproposed_revision_when_it_is_older_than_the_draft(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    with api.store() as store:
        store.insert_revision(
            user.id,
            session_id,
            kind="unproposed",
            manifest=_CANVAS_BEFORE,
            manifest_hash=canonical_hash(_CANVAS_BEFORE),
            source_file="/workflows/draft.workflow.json",
        )
    api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        accepted_manifest=_CANVAS_AFTER,
    )

    body = api.get_session(session_id)

    assert body["latest_draft"]["revision"] == 2
    assert body["latest_unproposed"] is None


def test_get_session_returns_running_turn_snapshot_when_a_turn_is_running(
    api: ApiHarness,
) -> None:
    api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    accepted = api.send_message(session_id)

    body = api.get_session(session_id)

    assert body["running"] is True
    assert body["running_turn"]["turn_id"] == accepted["turn_id"]
    assert body["running_turn"]["message_id"] == accepted["message_id"]
    assistant = body["messages"][-1]
    assert (assistant["id"], assistant["status"]) == (
        accepted["turn_id"],
        MESSAGE_STATUS_RUNNING,
    )


def test_get_session_flags_linked_row_changed_when_saved_row_edited_after_linking(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    workflow_id = api.add_workflow(user.id, manifest_json=_CANVAS_BEFORE)
    session_id = api.create_session(mode="edit", workflow_id=workflow_id)["id"]
    assert api.get_session(session_id)["linked_row_changed"] is False

    api.set_workflow_manifest(workflow_id, _CANVAS_AFTER)

    assert api.get_session(session_id)["linked_row_changed"] is True


# --- Delete ----------------------------------------------------------------------------


def test_delete_session_removes_rows_and_sandbox_when_session_is_idle(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        accepted_manifest=_CANVAS_AFTER,
    )
    sandbox = BuilderSandbox(user.id, session_id, root=api.sandbox_root)
    sandbox.ensure()
    assert sandbox.exists()
    kept_id = api.create_session()["id"]

    response = api.client.delete(f"{_API}/sessions/{session_id}")

    assert response.status_code == 204
    assert api.client.get(f"{_API}/sessions/{session_id}").status_code == 404
    assert api.count(WorkflowBuilderSession, id=session_id) == 0
    assert api.count(WorkflowBuilderMessage, session_id=session_id) == 0
    assert api.count(WorkflowBuilderDraft, session_id=session_id) == 0
    assert not sandbox.exists()
    assert api.get_session(kept_id)["id"] == kept_id


def test_delete_session_stops_running_turn_before_removing_rows_when_turn_running(
    api: ApiHarness,
) -> None:
    api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    accepted = api.send_message(session_id)
    assert get_live_turn(session_id) is not None

    response = api.client.delete(f"{_API}/sessions/{session_id}")

    assert response.status_code == 204
    assert get_live_turn(session_id) is None
    (task,) = api.starter.tasks
    assert task.done()
    assert api.count(WorkflowBuilderSession, id=session_id) == 0
    assert api.count(WorkflowBuilderMessage, id=accepted["turn_id"]) == 0


def test_delete_session_returns_404_and_keeps_data_when_session_belongs_to_other_user(
    api: ApiHarness,
) -> None:
    owner = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.seed_turn(owner.id, session_id, status=MESSAGE_STATUS_COMPLETED)
    api.act_as(api.new_user())

    response = api.client.delete(f"{_API}/sessions/{session_id}")

    assert response.status_code == 404
    assert _error_code(response) == "session_not_found"
    assert api.count(WorkflowBuilderSession, id=session_id) == 1
    assert api.count(WorkflowBuilderMessage, session_id=session_id) == 2


# --- Link ------------------------------------------------------------------------------


def test_link_session_links_workflow_when_caller_owns_it(api: ApiHarness) -> None:
    user = api.act_as(api.new_user())
    workflow_id = api.add_workflow(user.id, manifest_json=_CANVAS_BEFORE)
    session_id = api.create_session()["id"]

    response = api.client.post(
        f"{_API}/sessions/{session_id}/link", json={"workflow_id": workflow_id}
    )

    assert response.status_code == 200
    assert response.json()["id"] == session_id
    assert response.json()["workflow_id"] == workflow_id
    assert api.get_session(session_id)["workflow_id"] == workflow_id
    with api.db() as db:
        row = db.get(WorkflowBuilderSession, session_id)
        assert row is not None
        assert row.linked_manifest_hash == canonical_hash(_CANVAS_BEFORE)


@pytest.mark.parametrize("target", ["other_users_row", "missing_row"])
def test_link_session_returns_404_and_keeps_link_when_workflow_not_owned(
    api: ApiHarness, target: str
) -> None:
    owner = api.new_user()
    caller = api.act_as(api.new_user())
    own_workflow = api.add_workflow(caller.id, manifest_json=_CANVAS_BEFORE)
    session_id = api.create_session(mode="edit", workflow_id=own_workflow)["id"]
    workflow_id = (
        api.add_workflow(owner.id, manifest_json=_CANVAS_AFTER)
        if target == "other_users_row"
        else str(uuid.uuid4())
    )

    response = api.client.post(
        f"{_API}/sessions/{session_id}/link", json={"workflow_id": workflow_id}
    )

    assert response.status_code == 404
    assert _error_code(response) == "workflow_not_found"
    assert api.get_session(session_id)["workflow_id"] == own_workflow


# --- Undo ------------------------------------------------------------------------------


def test_undo_stores_undo_revision_from_starting_canvas_when_latest_is_accepted(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        canvas_state=_CANVAS_BEFORE,
        accepted_manifest=_CANVAS_AFTER,
    )

    response = api.client.post(
        f"{_API}/sessions/{session_id}/undo", json={"expected_revision": 1}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["revision"], body["kind"]) == (2, "undo")
    assert body["manifest"] == _CANVAS_BEFORE
    latest = api.get_session(session_id)["latest_draft"]
    assert (latest["revision"], latest["kind"]) == (2, "undo")
    assert latest["manifest"] == _CANVAS_BEFORE
    assert api.count(WorkflowBuilderDraft, session_id=session_id) == 2


@pytest.mark.parametrize("expected_revision", [1, 2])
def test_undo_returns_409_when_the_change_was_already_undone(
    api: ApiHarness, expected_revision: int
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        canvas_state=_CANVAS_BEFORE,
        accepted_manifest=_CANVAS_AFTER,
    )
    url = f"{_API}/sessions/{session_id}/undo"
    assert api.client.post(url, json={"expected_revision": 1}).status_code == 200

    response = api.client.post(url, json={"expected_revision": expected_revision})

    assert response.status_code == 409
    assert _error_code(response) == "undo_stale"
    assert api.count(WorkflowBuilderDraft, session_id=session_id) == 2


def test_undo_returns_409_and_stores_nothing_when_expected_revision_is_not_latest(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        canvas_state=_CANVAS_BEFORE,
        accepted_manifest=_CANVAS_AFTER,
    )

    response = api.client.post(
        f"{_API}/sessions/{session_id}/undo", json={"expected_revision": 7}
    )

    assert response.status_code == 409
    assert _error_code(response) == "undo_stale"
    assert api.count(WorkflowBuilderDraft, session_id=session_id) == 1


def test_undo_returns_409_when_latest_revision_is_the_edit_seed(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    workflow_id = api.add_workflow(user.id, manifest_json=_CANVAS_BEFORE)
    session_id = api.create_session(mode="edit", workflow_id=workflow_id)["id"]

    response = api.client.post(
        f"{_API}/sessions/{session_id}/undo", json={"expected_revision": 0}
    )

    assert response.status_code == 409
    assert _error_code(response) == "undo_stale"
    assert api.count(WorkflowBuilderDraft, session_id=session_id) == 1


def test_undo_returns_409_turn_running_when_a_turn_is_running(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_COMPLETED,
        canvas_state=_CANVAS_BEFORE,
        accepted_manifest=_CANVAS_AFTER,
    )
    api.send_message(session_id)

    response = api.client.post(
        f"{_API}/sessions/{session_id}/undo", json={"expected_revision": 1}
    )

    assert response.status_code == 409
    assert _error_code(response) == "turn_running"
    assert api.count(WorkflowBuilderDraft, session_id=session_id) == 1


# --- Retry -----------------------------------------------------------------------------


def test_retry_turn_reuses_user_message_when_latest_turn_failed(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    failed = api.seed_turn(
        user.id,
        session_id,
        status=MESSAGE_STATUS_FAILED,
        canvas_state=_CANVAS_BEFORE,
        content="Add a second step",
    )

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{failed['turn_id']}/retry"
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["message_id"] == failed["user_message_id"]
    assert body["turn_id"] != failed["turn_id"]
    assert body["replayed"] is False
    assert (
        api.count(WorkflowBuilderMessage, session_id=session_id, role=MESSAGE_ROLE_USER)
        == 1
    )
    assert (
        api.count(
            WorkflowBuilderMessage, session_id=session_id, role=MESSAGE_ROLE_ASSISTANT
        )
        == 2
    )
    with api.db() as db:
        retried = db.get(WorkflowBuilderMessage, body["turn_id"])
        assert retried is not None
        assert retried.status == MESSAGE_STATUS_RUNNING
        assert retried.reply_to_message_id == failed["user_message_id"]
        session = db.get(WorkflowBuilderSession, session_id)
        assert session is not None
        assert session.turn_count == 1
    (_turn, content, canvas_state) = api.starter.calls[-1]
    assert content == "Add a second step"
    assert canvas_state == _CANVAS_BEFORE
    assert api.get_session(session_id)["running"] is True


def test_retry_turn_returns_409_when_latest_turn_did_not_fail(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    completed = api.seed_turn(user.id, session_id, status=MESSAGE_STATUS_COMPLETED)

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{completed['turn_id']}/retry"
    )

    assert response.status_code == 409
    assert _error_code(response) == "retry_not_allowed"
    assert api.starter.calls == []
    assert (
        api.count(
            WorkflowBuilderMessage, session_id=session_id, role=MESSAGE_ROLE_ASSISTANT
        )
        == 1
    )


def test_retry_turn_returns_409_when_turn_is_not_the_latest(api: ApiHarness) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    older = api.seed_turn(user.id, session_id, status=MESSAGE_STATUS_FAILED)
    api.seed_turn(user.id, session_id, status=MESSAGE_STATUS_FAILED)

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{older['turn_id']}/retry"
    )

    assert response.status_code == 409
    assert _error_code(response) == "retry_not_allowed"
    assert api.starter.calls == []


def test_retry_turn_returns_409_turn_running_when_retry_is_repeated(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    failed = api.seed_turn(user.id, session_id, status=MESSAGE_STATUS_FAILED)
    url = f"{_API}/sessions/{session_id}/turns/{failed['turn_id']}/retry"
    assert api.client.post(url).status_code == 202

    response = api.client.post(url)

    assert response.status_code == 409
    assert _error_code(response) == "turn_running"
    assert len(api.starter.calls) == 1


# --- Cancel ----------------------------------------------------------------------------


def test_cancel_turn_returns_cancelling_and_stores_cancelled_when_turn_running(
    api: ApiHarness,
) -> None:
    api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    accepted = api.send_message(session_id)

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{accepted['turn_id']}/cancel"
    )

    assert response.status_code == 202
    assert response.json() == {"state": "cancelling"}
    assert _wait_for(lambda: api.get_session(session_id)["running"] is False)
    assistant = api.get_session(session_id)["messages"][-1]
    assert assistant["id"] == accepted["turn_id"]
    assert assistant["status"] == "cancelled"
    assert assistant["stop_reason"] == "cancelled"


def test_cancel_turn_returns_not_running_when_session_has_no_running_turn(
    api: ApiHarness,
) -> None:
    user = api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    finished = api.seed_turn(user.id, session_id, status=MESSAGE_STATUS_COMPLETED)

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{finished['turn_id']}/cancel"
    )

    assert response.status_code == 200
    assert response.json() == {"state": "not_running"}


def test_cancel_turn_leaves_turn_running_when_turn_id_is_not_the_running_one(
    api: ApiHarness,
) -> None:
    api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    api.send_message(session_id)

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{uuid.uuid4()}/cancel"
    )

    assert response.status_code == 200
    assert response.json() == {"state": "not_running"}
    assert api.get_session(session_id)["running"] is True


def test_cancel_turn_returns_404_and_leaves_turn_running_when_session_not_owned(
    api: ApiHarness,
) -> None:
    api.act_as(api.new_user())
    session_id = api.create_session()["id"]
    accepted = api.send_message(session_id)
    owner = api.user
    api.act_as(api.new_user())

    response = api.client.post(
        f"{_API}/sessions/{session_id}/turns/{accepted['turn_id']}/cancel"
    )

    assert response.status_code == 404
    assert _error_code(response) == "session_not_found"
    api.act_as(owner)
    assert api.get_session(session_id)["running"] is True
