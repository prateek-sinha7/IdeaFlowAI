"""Unit tests for builder lifecycle (task 16.10): the restart sweep, the startup
unavailable paths and the shutdown step order.

Collaborators are ``InMemoryBuilderStore``, a ``tmp_path`` sandbox root and recording
stubs for the skill-package check, the catalog check and the storage report. No
database, network or model is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.api.workflow_builder import lifecycle, turns
from app.api.workflow_builder.admission import BuilderReadiness
from app.api.workflow_builder.turns import LiveTurn, attach_task, register_live_turn
from app.core.config import settings
from app.models.workflow_builder import (
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_RUNNING,
    WorkflowBuilderMessage,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore

MODEL = "eu.anthropic.claude-sonnet-5-5"
USER_ID = "user-1"
MANIFEST = {"id": "wf", "steps": [{"id": "a", "agent": "custom-agent"}]}


@pytest.fixture
def store() -> InMemoryBuilderStore:
    return InMemoryBuilderStore()


@pytest.fixture(autouse=True)
def _clear_live_turns() -> Iterator[None]:
    yield
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()


def _new_session(store: InMemoryBuilderStore) -> str:
    return str(
        store.create_session(USER_ID, **BuilderSessionFactory.create_kwargs()).id
    )


def _begin(
    store: InMemoryBuilderStore,
    session_id: str,
    client_message_id: str = "client-msg-0001",
) -> WorkflowBuilderMessage:
    """Store a turn and leave its assistant row ``running``."""
    begun = store.begin_turn(
        USER_ID,
        session_id,
        content="hi",
        canvas_state=None,
        client_message_id=client_message_id,
        model_id=MODEL,
        effort=None,
        skill_hash="h",
    )
    return begun.assistant_message


def _write_file(
    root: Path,
    session_id: str,
    name: str,
    text: str,
    *,
    mtime: float,
) -> Path:
    path = BuilderSandbox(USER_ID, session_id, root=root).path_for(f"/workflows/{name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _started(row: WorkflowBuilderMessage) -> float:
    return lifecycle._as_utc(row.started_at).timestamp()  # type: ignore[arg-type]


def _unproposed(store: InMemoryBuilderStore, session_id: str) -> Any:
    return store.get_latest_revisions(USER_ID, session_id).unproposed


# --- sweep_interrupted_turns ------------------------------------------------------------


def test_sweep_marks_running_rows_interrupted_with_restart_and_leaves_others(
    store: InMemoryBuilderStore, tmp_path: Path
) -> None:
    session_id = _new_session(store)
    done = _begin(store, session_id)
    store.finalize_assistant(USER_ID, str(done.id), status=MESSAGE_STATUS_COMPLETED)
    running = _begin(store, session_id, "client-msg-0002")

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert result == lifecycle.SweepResult(interrupted=1, revisions_stored=0)
    assert (running.status, running.stop_reason) == (
        MESSAGE_STATUS_INTERRUPTED,
        "restart",
    )
    assert done.status == MESSAGE_STATUS_COMPLETED
    assert store.get_running_turn(USER_ID, session_id) is None


def test_sweep_returns_zero_and_touches_nothing_when_no_row_is_running(
    store: InMemoryBuilderStore, tmp_path: Path
) -> None:
    _new_session(store)

    assert lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path) == (
        lifecycle.SweepResult(0, 0)
    )


def test_sweep_starts_no_turn(store: InMemoryBuilderStore, tmp_path: Path) -> None:
    _begin(store, _new_session(store))

    lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert turns._LIVE_TURNS == {}
    assert turns._TURN_TASKS == set()


def test_sweep_stores_newest_manifest_file_written_since_turn_start_as_unproposed(
    store: InMemoryBuilderStore, tmp_path: Path
) -> None:
    session_id = _new_session(store)
    row = _begin(store, session_id)
    start = _started(row)
    older = {"steps": [{"id": "old", "agent": "custom-agent"}]}
    _write_file(
        tmp_path, session_id, "a.workflow.json", json.dumps(older), mtime=start + 1
    )
    _write_file(
        tmp_path, session_id, "b.workflow.json", json.dumps(MANIFEST), mtime=start + 5
    )

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert result.revisions_stored == 1
    stored = _unproposed(store, session_id)
    assert stored.manifest == MANIFEST
    assert stored.manifest_hash == canonical_hash(MANIFEST)
    assert stored.source_turn_id == str(row.id)
    assert stored.source_file == "/workflows/b.workflow.json"


def test_sweep_stores_nothing_when_the_only_file_predates_the_turn(
    store: InMemoryBuilderStore, tmp_path: Path
) -> None:
    session_id = _new_session(store)
    row = _begin(store, session_id)
    _write_file(
        tmp_path,
        session_id,
        "a.workflow.json",
        json.dumps(MANIFEST),
        mtime=_started(row) - 60,
    )

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert (result.interrupted, result.revisions_stored) == (1, 0)
    assert _unproposed(store, session_id) is None


@pytest.mark.parametrize(
    "text",
    ["{not json", "[1, 2]", '"text"', ""],
    ids=["invalid", "list", "string", "empty"],
)
def test_sweep_stores_nothing_when_file_is_not_a_json_object(
    store: InMemoryBuilderStore, tmp_path: Path, text: str
) -> None:
    session_id = _new_session(store)
    row = _begin(store, session_id)
    _write_file(tmp_path, session_id, "a.workflow.json", text, mtime=_started(row) + 1)

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert (result.interrupted, result.revisions_stored) == (1, 0)
    assert _unproposed(store, session_id) is None


def test_sweep_ignores_files_that_are_not_workflow_manifests_or_are_too_large(
    store: InMemoryBuilderStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = _new_session(store)
    row = _begin(store, session_id)
    start = _started(row)
    _write_file(
        tmp_path, session_id, "notes.json", json.dumps(MANIFEST), mtime=start + 1
    )
    _write_file(
        tmp_path, session_id, "big.workflow.json", json.dumps(MANIFEST), mtime=start + 2
    )
    monkeypatch.setattr(lifecycle, "MAX_MANIFEST_BYTES", 10)

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert result.revisions_stored == 0
    assert _unproposed(store, session_id) is None


def test_sweep_stores_nothing_when_a_revision_already_holds_the_same_manifest(
    store: InMemoryBuilderStore, tmp_path: Path
) -> None:
    session_id = _new_session(store)
    row = _begin(store, session_id)
    store.insert_revision(
        USER_ID,
        session_id,
        kind="accepted",
        manifest=MANIFEST,
        manifest_hash=canonical_hash(MANIFEST),
        target_trust="user",
        source_turn_id=str(row.id),
    )
    _write_file(
        tmp_path,
        session_id,
        "a.workflow.json",
        json.dumps(MANIFEST),
        mtime=_started(row) + 1,
    )

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert (result.interrupted, result.revisions_stored) == (1, 0)
    assert _unproposed(store, session_id) is None


def test_sweep_adds_nothing_the_second_time_it_runs(
    store: InMemoryBuilderStore, tmp_path: Path
) -> None:
    session_id = _new_session(store)
    row = _begin(store, session_id)
    _write_file(
        tmp_path,
        session_id,
        "a.workflow.json",
        json.dumps(MANIFEST),
        mtime=_started(row) + 1,
    )

    first = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)
    second = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert first == lifecycle.SweepResult(1, 1)
    assert second == lifecycle.SweepResult(0, 0)


class _FailingFor(InMemoryBuilderStore):
    """A store whose revision lookup fails for one session."""

    def __init__(self, bad_session_id: str | None = None) -> None:
        super().__init__()
        self.bad_session_id = bad_session_id

    def get_latest_revisions(self, user_id: str, session_id: str) -> Any:
        if session_id == self.bad_session_id:
            raise RuntimeError("boom")
        return super().get_latest_revisions(user_id, session_id)


def test_sweep_continues_with_other_rows_when_one_row_fails(tmp_path: Path) -> None:
    store = _FailingFor()
    bad, good = _new_session(store), _new_session(store)
    store.bad_session_id = bad
    bad_row, good_row = _begin(store, bad), _begin(store, good)
    for sid, row in ((bad, bad_row), (good, good_row)):
        _write_file(
            tmp_path,
            sid,
            "a.workflow.json",
            json.dumps(MANIFEST),
            mtime=_started(row) + 1,
        )

    result = lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    store.bad_session_id = None  # let the assertions read the stored revisions
    assert result == lifecycle.SweepResult(interrupted=2, revisions_stored=1)
    assert _unproposed(store, good) is not None
    assert _unproposed(store, bad) is None


def test_sweep_does_not_mark_rows_when_the_listing_fails(tmp_path: Path) -> None:
    store = InMemoryBuilderStore()
    row = _begin(store, _new_session(store))

    def broken() -> list[Any]:
        raise RuntimeError("db down")

    store.list_running_assistant_rows = broken  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        lifecycle.sweep_interrupted_turns(store, sandbox_root=tmp_path)

    assert row.status == MESSAGE_STATUS_RUNNING


# --- _verify_skill_package --------------------------------------------------------------


def test_verify_skill_package_returns_true_and_logs_nothing_when_no_problems(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(lifecycle, "_skill_package_problems", lambda root: [])

    with caplog.at_level(logging.ERROR, logger=lifecycle.logger.name):
        assert lifecycle._verify_skill_package() is True

    assert caplog.records == []


def test_verify_skill_package_logs_one_error_and_returns_false_when_problems(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        lifecycle, "_skill_package_problems", lambda root: ["missing a", "differs b"]
    )

    with caplog.at_level(logging.ERROR, logger=lifecycle.logger.name):
        assert lifecycle._verify_skill_package() is False

    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert "missing a; differs b" in record.getMessage()
    assert "(2 problem(s))" in record.getMessage()


def test_verify_skill_package_lists_ten_problems_and_counts_the_rest(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        lifecycle, "_skill_package_problems", lambda root: [f"p{i}" for i in range(13)]
    )

    with caplog.at_level(logging.ERROR, logger=lifecycle.logger.name):
        lifecycle._verify_skill_package()

    message = caplog.records[0].getMessage()
    assert "p9" in message and "p10" not in message
    assert "and 3 more" in message


def test_verify_skill_package_returns_false_when_the_package_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def unreadable(root: Path) -> list[str]:
        raise PermissionError("secret path detail")

    monkeypatch.setattr(lifecycle, "_skill_package_problems", unreadable)

    with caplog.at_level(logging.ERROR, logger=lifecycle.logger.name):
        assert lifecycle._verify_skill_package() is False

    assert "PermissionError" in caplog.records[0].getMessage()
    assert "secret path detail" not in caplog.records[0].getMessage()


# --- builder_startup --------------------------------------------------------------------


class _Startup:
    """Recording stubs for everything ``builder_startup`` reaches outside the store."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, store: InMemoryBuilderStore
    ) -> None:
        self.calls: list[str] = []
        self.store = store
        self.readiness = BuilderReadiness()
        self.readiness.mark_ready()  # startup must clear this first
        self.skill_ok = True
        self.catalog_error: Exception | None = None
        self.report_error: Exception | None = None
        monkeypatch.setattr(lifecycle, "_verify_skill_package", self._verify)
        monkeypatch.setattr(lifecycle, "assert_builder_catalog_valid", self._catalog)
        monkeypatch.setattr(lifecycle, "storage_report", lambda s: "report")
        monkeypatch.setattr(lifecycle, "log_storage_report", self._report)
        monkeypatch.setattr(lifecycle, "set_turn_starter", self._starter)
        monkeypatch.setattr(
            lifecycle, "_run_sweep", self._sweep_wrapper(lifecycle._run_sweep)
        )

    def _verify(self) -> bool:
        self.calls.append("skill")
        return self.skill_ok

    def _catalog(self, entries: object) -> None:
        self.calls.append("catalog")
        if self.catalog_error is not None:
            raise self.catalog_error

    def _report(self, report: object) -> None:
        self.calls.append("report")
        if self.report_error is not None:
            raise self.report_error

    def _starter(self, starter: object) -> None:
        self.calls.append("starter")
        assert starter is lifecycle.start_turn_task

    def _sweep_wrapper(self, real: Any) -> Any:
        def run(scope: Any) -> Any:
            self.calls.append("sweep")
            return real(scope)

        return run

    @contextmanager
    def scope(self) -> Iterator[InMemoryBuilderStore]:
        yield self.store

    async def run(self) -> None:
        await lifecycle.builder_startup(
            store_scope=self.scope, readiness=self.readiness
        )


@pytest.fixture
def startup(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryBuilderStore, tmp_path: Path
) -> _Startup:
    # The sweep looks for manifest files under the sandbox root; keep it in tmp_path.
    monkeypatch.setattr(settings, "BUILDER_SANDBOX_ROOT", str(tmp_path))
    return _Startup(monkeypatch, store)


async def test_builder_startup_runs_steps_in_order_and_marks_ready(
    startup: _Startup,
) -> None:
    await startup.run()

    assert startup.calls == ["skill", "catalog", "sweep", "report", "starter"]
    assert startup.readiness.is_ready is True


async def test_builder_startup_sweeps_running_rows_before_marking_ready(
    startup: _Startup, store: InMemoryBuilderStore
) -> None:
    row = _begin(store, _new_session(store))

    await startup.run()

    assert row.status == MESSAGE_STATUS_INTERRUPTED
    assert startup.readiness.is_ready is True


async def test_builder_startup_stays_unavailable_but_still_sweeps_when_skill_package_fails(
    startup: _Startup, store: InMemoryBuilderStore
) -> None:
    startup.skill_ok = False
    row = _begin(store, _new_session(store))

    await startup.run()

    assert startup.readiness.is_ready is False
    assert row.status == MESSAGE_STATUS_INTERRUPTED
    assert startup.calls == ["skill", "catalog", "sweep", "report", "starter"]


async def test_builder_startup_raises_and_skips_the_sweep_when_catalog_is_invalid(
    startup: _Startup, store: InMemoryBuilderStore
) -> None:
    startup.catalog_error = RuntimeError("builder catalog inconsistent")
    row = _begin(store, _new_session(store))

    with pytest.raises(RuntimeError, match="inconsistent"):
        await startup.run()

    assert startup.readiness.is_ready is False
    assert startup.calls == ["skill", "catalog"]
    assert row.status == MESSAGE_STATUS_RUNNING


async def test_builder_startup_stays_unavailable_and_logs_type_only_when_sweep_fails(
    startup: _Startup, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> list[Any]:
        raise RuntimeError("password=hunter2 host=db.internal")

    startup.store.list_running_assistant_rows = broken  # type: ignore[method-assign]

    with caplog.at_level(logging.ERROR, logger=lifecycle.logger.name):
        await startup.run()

    assert startup.readiness.is_ready is False
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "RuntimeError" in errors[0].getMessage()
    assert "hunter2" not in caplog.text
    assert startup.calls[-2:] == ["report", "starter"]  # the rest of startup still ran


async def test_builder_startup_stays_ready_when_the_storage_report_fails(
    startup: _Startup, caplog: pytest.LogCaptureFixture
) -> None:
    startup.report_error = OSError("disk detail")

    with caplog.at_level(logging.WARNING, logger=lifecycle.logger.name):
        await startup.run()

    assert startup.readiness.is_ready is True
    assert "OSError" in caplog.text
    assert "disk detail" not in caplog.text


# --- stop_builder_turns: shutdown step order --------------------------------------------


class _Bus:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def close_all(self) -> None:
        self._calls.append("close_all")


class _Shutdown:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[str] = []
        self.stop_all_args: tuple[str, float] | None = None
        self.stop_all_error: Exception | None = None
        self.ready_during_stop: bool | None = None
        self.readiness = BuilderReadiness()
        self.readiness.mark_ready()
        monkeypatch.setattr(lifecycle, "get_builder_readiness", lambda: self.readiness)
        monkeypatch.setattr(lifecycle, "get_event_bus", lambda: _Bus(self.calls))
        monkeypatch.setattr(lifecycle, "stop_all", self._stop_all)

    async def _stop_all(self, reason: str, *, persist_seconds: float) -> None:
        self.calls.append("stop_all")
        self.stop_all_args = (reason, persist_seconds)
        self.ready_during_stop = self.readiness.is_ready
        if self.stop_all_error is not None:
            raise self.stop_all_error


@pytest.fixture
def shutdown(monkeypatch: pytest.MonkeyPatch) -> _Shutdown:
    return _Shutdown(monkeypatch)


async def test_stop_builder_turns_refuses_new_work_then_stops_turns_then_closes_streams(
    shutdown: _Shutdown,
) -> None:
    await lifecycle.stop_builder_turns()

    assert shutdown.calls == ["stop_all", "close_all"]
    assert shutdown.ready_during_stop is False  # unavailable before any turn stops
    assert shutdown.readiness.is_ready is False
    assert shutdown.stop_all_args == (
        "shutdown",
        settings.BUILDER_SHUTDOWN_PERSIST_SECONDS,
    )


async def test_stop_builder_turns_passes_the_given_reason_through(
    shutdown: _Shutdown,
) -> None:
    await lifecycle.stop_builder_turns("deleted")

    assert shutdown.stop_all_args is not None
    assert shutdown.stop_all_args[0] == "deleted"


async def test_stop_builder_turns_closes_streams_and_raises_when_stopping_fails(
    shutdown: _Shutdown,
) -> None:
    shutdown.stop_all_error = RuntimeError("stop failed")

    with pytest.raises(RuntimeError, match="stop failed"):
        await lifecycle.stop_builder_turns()

    assert shutdown.calls == ["stop_all", "close_all"]
    assert shutdown.readiness.is_ready is False


async def test_stop_builder_turns_stops_a_live_turn_with_the_shutdown_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = BuilderReadiness()
    monkeypatch.setattr(lifecycle, "get_builder_readiness", lambda: readiness)
    monkeypatch.setattr(lifecycle, "get_event_bus", lambda: _Bus([]))
    monkeypatch.setattr(settings, "BUILDER_SHUTDOWN_PERSIST_SECONDS", 0.5)
    live = LiveTurn("s-1", "t-1", "um-1", USER_ID, MODEL, None)
    register_live_turn(live)
    task = asyncio.get_running_loop().create_task(asyncio.sleep(30))
    attach_task(live, task)

    await lifecycle.stop_builder_turns()

    assert live.stop_reason == "shutdown"
    assert task.cancelled()


# --- shutdown_run_infrastructure calls the builder first ---------------------------------


@pytest.fixture
def run_shutdown(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Run-transport shutdown with recording stubs; returns the shared call log."""
    from app.api import run_commands, run_shutdown as run_shutdown_mod

    log: list[str] = []

    async def close_checkpointer() -> None:
        log.append("checkpointer")

    monkeypatch.setattr(
        "app.agents.checkpointer.close_checkpointer", close_checkpointer
    )
    monkeypatch.setattr(run_shutdown_mod.settings, "SHUTDOWN_STOP_RUNS", False)
    monkeypatch.setattr(run_commands, "_CONCIERGE_STREAM_TASKS", set())
    return log


async def test_shutdown_run_infrastructure_stops_builder_turns_before_other_steps(
    monkeypatch: pytest.MonkeyPatch, run_shutdown: list[str]
) -> None:
    from app.api import run_commands, run_shutdown as run_shutdown_mod

    async def concierge() -> None:
        run_shutdown.append("concierge")

    async def stop_builder_turns() -> None:
        run_shutdown.append("builder")

    monkeypatch.setattr(lifecycle, "stop_builder_turns", stop_builder_turns)
    run_commands._CONCIERGE_STREAM_TASKS.add(
        asyncio.get_running_loop().create_task(concierge())
    )

    summary = await run_shutdown_mod.shutdown_run_infrastructure()

    assert run_shutdown == ["builder", "concierge", "checkpointer"]
    assert summary["builder_turns_stopped"] is True


async def test_shutdown_run_infrastructure_continues_when_builder_step_fails(
    monkeypatch: pytest.MonkeyPatch, run_shutdown: list[str]
) -> None:
    from app.api import run_shutdown as run_shutdown_mod

    async def stop_builder_turns() -> None:
        raise RuntimeError("password=hunter2")

    monkeypatch.setattr(lifecycle, "stop_builder_turns", stop_builder_turns)

    summary = await run_shutdown_mod.shutdown_run_infrastructure()

    assert summary["builder_turns_stopped"] is False
    assert "builder_turns: RuntimeError" in summary["errors"]
    assert "hunter2" not in str(summary["errors"])
    assert run_shutdown == ["checkpointer"]
    assert summary["checkpointer_closed"] is True
