"""Builder startup, turn start and shutdown (design 3.1.6, tasks 16.10).

* :func:`builder_startup` runs in the app lifespan before "Backend ready". It
  checks the skill package (a failure marks the builder unavailable and logs one
  ERROR, G-21), checks the builder model catalog (a failure raises, so the
  process stops, Req 41.8), sweeps Turns a restart left ``running``, logs the
  storage report, installs the real Turn starter and sets readiness. A failed
  sweep also marks the builder unavailable, because a row left ``running`` would
  answer 409 for its Session until the next restart.
* :func:`start_turn_task` is the ``TurnStarter`` that admission calls. It runs
  :func:`~app.api.workflow_builder.turns.run_turn` in a background task.
* :func:`stop_builder_turns` is the first step of
  ``shutdown_run_infrastructure()`` [pending G-17].
* :func:`stop_user_turns_from_worker` stops a deleted account's Turns from the
  admin route, which runs in a worker thread.

The sweep starts no Turn and makes no model call (Req 22.5). Logs carry ids,
counts and byte sizes only, never message text or manifests (Req 42.4).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

from anyio import from_thread

from agents.capabilities.model_catalog import ModelCatalog
from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.draft_tool import MAX_MANIFEST_BYTES
from app.agents.workflow_builder.events import StopReason
from app.agents.workflow_builder.model_catalog_view import assert_builder_catalog_valid
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.skill_package import SKILL_DIR, missing_files
from app.api.workflow_builder.admission import (
    BuilderReadiness,
    get_builder_readiness,
    set_turn_starter,
)
from app.api.workflow_builder.reporting import log_storage_report, storage_report
from app.api.workflow_builder.store import BuilderStore, LatestRevisions
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnRequest,
    attach_task,
    get_event_bus,
    get_live_turn,
    release_live_turn,
    run_turn,
    status_for_stop,
    stop_all,
    stop_user_turns,
)
from app.core.config import settings
from app.models.database import SessionLocal
from app.models.workflow_builder import (
    DRAFT_KIND_UNPROPOSED,
    WorkflowBuilderMessage,
)

__all__ = [
    "SweepResult",
    "builder_startup",
    "start_turn_task",
    "stop_builder_turns",
    "stop_user_turns_from_worker",
    "sweep_interrupted_turns",
]

logger = logging.getLogger("app.api.workflow_builder.lifecycle")

_WORKFLOWS_VIRTUAL: Final = "/workflows"
_MANIFEST_SUFFIX: Final = ".workflow.json"
# Skill problems are listed in the one ERROR line; more than this are counted.
_MAX_LISTED_PROBLEMS: Final = 10

#: Opens a Session_Store on its own database session for one blocking call.
type BuilderStoreScope = Callable[[], AbstractContextManager[BuilderStore]]


@contextmanager
def _open_builder_store() -> Iterator[BuilderStore]:
    """Open a Session_Store on its own database session and close it afterwards."""
    db = SessionLocal()
    try:
        yield BuilderStore(db)
    finally:
        db.close()


# --- Startup sweep --------------------------------------------------------------------


class SweepStore(Protocol):
    """The Session_Store calls the startup sweep makes (``BuilderStore`` fits)."""

    def list_running_assistant_rows(self) -> list[WorkflowBuilderMessage]:
        """List every user's assistant rows still ``running``."""
        ...

    def get_latest_revisions(self, user_id: str, session_id: str) -> LatestRevisions:
        """Return the newest revision of each kind."""
        ...

    def insert_revision(  # noqa: PLR0913 - mirrors BuilderStore.insert_revision
        self,
        user_id: str,
        session_id: str,
        *,
        kind: str,
        manifest: dict[str, Any],
        manifest_hash: str,
        source_turn_id: str | None = None,
        source_file: str | None = None,
    ) -> Any:
        """Insert an ``unproposed`` revision."""
        ...

    def mark_running_interrupted(self, *, ended_at: datetime | None = None) -> int:
        """Mark every running assistant row ``interrupted`` / ``restart``."""
        ...


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What the startup sweep did.

    Attributes:
        interrupted: Assistant rows marked ``interrupted`` with reason ``restart``.
        revisions_stored: Unproposed revisions stored from sandbox files.
    """

    interrupted: int
    revisions_stored: int


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive datetime as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _newest_manifest_file(sandbox: BuilderSandbox, since: datetime) -> Path | None:
    """Return the newest ``*.workflow.json`` under ``/workflows/`` written since ``since``.

    Symlinks are neither followed nor read. ``None`` when there is no such file.
    """
    workflows = sandbox.path_for(_WORKFLOWS_VIRTUAL)
    if not workflows.is_dir():
        return None
    root = workflows.resolve()
    threshold = _as_utc(since).timestamp()
    best: tuple[float, Path] | None = None
    for folder, _dirs, names in os.walk(root, followlinks=False):
        for name in names:
            if not name.endswith(_MANIFEST_SUFFIX):
                continue
            path = Path(folder) / name
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified >= threshold and (best is None or modified > best[0]):
                best = (modified, path)
    return best[1] if best is not None else None


def _known_hashes(latest: LatestRevisions) -> set[str]:
    """Return the manifest hashes of the newest revision of every kind."""
    return {
        str(rev.manifest_hash)
        for rev in (latest.seed, latest.accepted, latest.undo, latest.unproposed)
        if rev is not None
    }


def _store_unproposed(
    store: SweepStore, row: WorkflowBuilderMessage, sandbox_root: Path | None
) -> bool:
    """Store the swept Turn's newest manifest file as an unproposed revision.

    Returns True when a revision was stored. Nothing is stored when the Session
    has no file written since the Turn started, when the file is not a JSON
    object, or when a revision already holds the same manifest (so a repeated
    sweep adds nothing).
    """
    user_id = str(row.user_id)
    session_id = str(row.session_id)
    sandbox = BuilderSandbox(user_id, session_id, root=sandbox_root)
    started = row.started_at or row.created_at
    path = _newest_manifest_file(sandbox, started)  # type: ignore[arg-type]
    if path is None:
        return False
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(manifest, dict):
        return False
    digest = canonical_hash(manifest)
    if digest in _known_hashes(store.get_latest_revisions(user_id, session_id)):
        return False
    relative = path.resolve().relative_to(
        sandbox.path_for(_WORKFLOWS_VIRTUAL).resolve()
    )
    store.insert_revision(
        user_id,
        session_id,
        kind=DRAFT_KIND_UNPROPOSED,
        manifest=manifest,
        manifest_hash=digest,
        source_turn_id=str(row.id),
        source_file=f"{_WORKFLOWS_VIRTUAL}/{relative.as_posix()}",
    )
    return True


def sweep_interrupted_turns(
    store: SweepStore, *, sandbox_root: str | Path | None = None
) -> SweepResult:
    """Mark Turns a restart left ``running`` as ``interrupted`` (Req 22.2 to 22.5).

    For each running assistant row, the newest ``*.workflow.json`` in the
    Session's ``/workflows/`` folder with a modification time at or after the
    Turn's start is stored as an unproposed revision. Revisions are stored before
    the rows are marked, so a crash in between repeats the work on the next start
    without duplicating a revision. A failure on one row is logged and does not
    stop the others. No Turn is started and no model is called.

    Args:
        store: The Session_Store (``BuilderStore`` or its fake).
        sandbox_root: Builder sandbox root. ``None`` uses the configured one.

    Returns:
        The number of rows marked and revisions stored.
    """
    root = None if sandbox_root is None else Path(sandbox_root)
    stored = 0
    for row in store.list_running_assistant_rows():
        try:
            if _store_unproposed(store, row, root):
                stored += 1
        except Exception:  # noqa: BLE001 - one bad session must not stop the sweep
            logger.warning(
                "unproposed revision not stored in sweep session=%s turn=%s",
                row.session_id,
                row.id,
                exc_info=True,
            )
    interrupted = store.mark_running_interrupted()
    return SweepResult(interrupted=interrupted, revisions_stored=stored)


# --- Startup checks -------------------------------------------------------------------


def _skill_package_problems(skill_dir: Path) -> list[str]:
    """Return what is wrong with the skill at ``skill_dir`` (empty when fine)."""
    return [f"missing {path}" for path in missing_files(skill_dir)]


def _verify_skill_package() -> bool:
    """Check the skill's required files exist. Log one ERROR and return False if not."""
    try:
        problems = _skill_package_problems(SKILL_DIR)
    except OSError as exc:
        problems = [f"cannot read the skill package ({type(exc).__name__})"]
    if not problems:
        return True
    shown = "; ".join(problems[:_MAX_LISTED_PROBLEMS])
    extra = len(problems) - _MAX_LISTED_PROBLEMS
    logger.error(
        "workflow builder unavailable: skill at %s is incomplete "
        "(%d problem(s)): %s%s",
        SKILL_DIR,
        len(problems),
        shown,
        f"; and {extra} more" if extra > 0 else "",
    )
    return False


def _run_sweep(scope: BuilderStoreScope) -> SweepResult:
    """Run the sweep on its own database session. Blocking."""
    with scope() as store:
        return sweep_interrupted_turns(store)


def _log_storage(scope: BuilderStoreScope) -> None:
    """Build and log the storage report on its own database session. Blocking."""
    with scope() as store:
        log_storage_report(storage_report(store))


async def builder_startup(
    *,
    store_scope: BuilderStoreScope = _open_builder_store,
    readiness: BuilderReadiness | None = None,
) -> None:
    """Prepare the builder for serving. Runs in the lifespan before "Backend ready".

    In order: verify the skill package, check the model catalog, sweep, log the
    storage report, install the Turn starter and set readiness. The lifespan ends
    before uvicorn accepts a connection, so no message or stream is served before
    the sweep is done [G-17].

    Args:
        store_scope: Opens a Session_Store for one blocking call.
        readiness: The readiness holder; defaults to the process-wide one.

    Raises:
        RuntimeError: The builder model catalog is inconsistent (Req 41.8). The
            process must not start.
    """
    holder = readiness if readiness is not None else get_builder_readiness()
    holder.mark_unavailable()

    skill_ok = await asyncio.to_thread(_verify_skill_package)
    assert_builder_catalog_valid(ModelCatalog().list())  # raises: stops the process

    sweep_ok = True
    try:
        swept = await asyncio.to_thread(_run_sweep, store_scope)
        logger.info(
            "workflow builder sweep: interrupted=%d unproposed_revisions=%d",
            swept.interrupted,
            swept.revisions_stored,
        )
    except Exception as exc:  # noqa: BLE001 - any failure makes the builder unavailable
        # Type only: a database error text can carry connection details.
        logger.error(
            "workflow builder unavailable: startup sweep failed (%s)",
            type(exc).__name__,
        )
        logger.debug("startup sweep failure detail", exc_info=True)
        sweep_ok = False

    try:
        await asyncio.to_thread(_log_storage, store_scope)
    except Exception as exc:  # noqa: BLE001 - the report is advisory
        logger.warning("builder storage report not logged (%s)", type(exc).__name__)
        logger.debug("storage report failure detail", exc_info=True)

    set_turn_starter(start_turn_task)
    if skill_ok and sweep_ok:
        holder.mark_ready()
        logger.info("workflow builder ready")


# --- Turn start -----------------------------------------------------------------------


def start_turn_task(turn: LiveTurn, content: str, canvas_state: dict[str, Any]) -> None:
    """Run ``run_turn`` for an admitted message in a background task.

    This is the ``TurnStarter`` that admission calls with the registered live
    Turn. The task outlives the request (Req 21.5). It is attached to the Turn so
    a stop cancels it.

    Must be called on the event loop.
    """
    task = asyncio.get_running_loop().create_task(
        run_turn(turn, TurnRequest(content=content, canvas_state=canvas_state)),
        name=f"workflow-builder-turn-{turn.turn_id}",
    )
    attach_task(turn, task)
    task.add_done_callback(lambda done: _on_turn_task_done(turn, done))


# Held so a pending orphan write is not garbage collected.
_ORPHAN_TASKS: set[asyncio.Task[None]] = set()


def _on_turn_task_done(turn: LiveTurn, task: asyncio.Task[None]) -> None:
    """Close the books on a task that ended without reaching ``finalize_turn``.

    A task cancelled before its first step never enters ``run_turn``, so nothing
    stores its end and its row would stay ``running``, answering 409 until the
    next restart. This stores the end instead. A Turn stopped with ``deleted``
    stores nothing because its rows are going away.
    """
    if turn.finalizing or get_live_turn(turn.session_id) is not turn:
        return
    release_live_turn(turn)
    reason = turn.stop_reason
    if reason == "deleted":
        return
    status = status_for_stop(
        reason or ("cancelled" if task.cancelled() else None), failed=True
    )
    orphan = asyncio.get_running_loop().create_task(
        asyncio.to_thread(_finalize_orphan_row, turn, status, reason)
    )
    _ORPHAN_TASKS.add(orphan)
    orphan.add_done_callback(_ORPHAN_TASKS.discard)


def _finalize_orphan_row(
    turn: LiveTurn, status: str, reason: StopReason | None
) -> None:
    """Write the end of a Turn that never ran. Blocking; runs in a worker thread."""
    try:
        with _open_builder_store() as store:
            store.finalize_assistant(
                turn.user_id, turn.turn_id, status=status, stop_reason=reason
            )
    except Exception as exc:  # noqa: BLE001 - the next startup sweep catches the row
        logger.warning(
            "builder turn that never ran not finalised turn=%s (%s)",
            turn.turn_id,
            type(exc).__name__,
        )


# --- Shutdown and account deletion ----------------------------------------------------


async def stop_builder_turns(reason: StopReason = "shutdown") -> None:
    """Stop every running Turn, wait briefly for their rows, then close the streams.

    The first step of ``shutdown_run_infrastructure()`` [pending G-17], because
    uvicorn allows only 5 s. New messages are refused from here on (not ready).
    Each live Turn stops with ``reason`` and is given
    ``BUILDER_SHUTDOWN_PERSIST_SECONDS`` to store ``interrupted``. Whatever is not
    stored in time is caught by the next startup sweep. The Session streams are
    closed afterwards, also when stopping the Turns failed.

    Args:
        reason: The stop reason; a shutdown uses ``shutdown``.
    """
    get_builder_readiness().mark_unavailable()
    try:
        await stop_all(
            reason, persist_seconds=settings.BUILDER_SHUTDOWN_PERSIST_SECONDS
        )
    finally:
        get_event_bus().close_all()


def stop_user_turns_from_worker(user_id: str) -> int:
    """Stop a user's live Turns from a request worker thread.

    The admin delete route is a sync handler, so it runs in a worker thread.
    Cancelling an asyncio task is not thread-safe, so the stop is handed to the
    event loop. Called outside a worker thread (no loop to hand it to), it stops
    the Turns directly.

    Returns:
        The number of live Turns the user had.
    """
    try:
        return from_thread.run_sync(stop_user_turns, user_id)
    except RuntimeError:
        return stop_user_turns(user_id)
