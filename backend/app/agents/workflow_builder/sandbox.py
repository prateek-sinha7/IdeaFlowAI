"""Per-session disk sandbox for the Workflow Builder agent.

Layout (design section 4.5)::

    <root>/<user segment>/<session segment>/
        canvas/current.workflow.json   written by the server at each turn start
        workflows/*.workflow.json      the agent's manifests (agent-writable)
        exports/                       export_manifest.py outputs
        large_tool_results/            deepagents eviction
        conversation_history/          deepagents summarization offload
        .tmp/<call id>/                one script call's temp folder

``<root>`` is ``BUILDER_SANDBOX_ROOT``, or ``<RUNS_ROOT>/_builder`` when that
setting is empty. Each sandbox is a plain folder: no git repository is created
(Req 20.5). Nothing here deletes on a timer or by age. A sandbox goes away only
through :meth:`BuilderSandbox.delete_session` or
:meth:`BuilderSandbox.delete_user`, and a script call's temp folder is removed by
the script runner when the call ends (Req 20.11, 31.5, 31.6).

The user and session segments pass through ``app.agents.sandbox._safe_segment``,
and every resolved path is checked with ``is_relative_to`` against the root, so
an identifier or a stored path can never leave the sandbox.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Protocol

from app.agents.sandbox import _safe_segment
from app.core.config import settings

__all__ = [
    "BUILDER_SUBDIR",
    "CANVAS_FILE",
    "SANDBOX_DIRS",
    "BuilderSandbox",
    "DraftLike",
    "SandboxPathError",
    "resolve_builder_root",
]

logger = logging.getLogger("app.agents.workflow_builder.sandbox")

# Folder under RUNS_ROOT used when BUILDER_SANDBOX_ROOT is empty. A future sweep
# of RUNS_ROOT must skip it (Q-41).
BUILDER_SUBDIR: Final = "_builder"

CANVAS_FILE: Final = "canvas/current.workflow.json"
_WORKFLOWS_DIR: Final = "workflows"
_TMP_DIR: Final = ".tmp"

# Folders created with the sandbox, relative to the session folder.
SANDBOX_DIRS: Final[tuple[str, ...]] = (
    "canvas",
    _WORKFLOWS_DIR,
    "exports",
    "large_tool_results",
    "conversation_history",
    _TMP_DIR,
)

_MANIFEST_SUFFIX: Final = ".workflow.json"
_DEFAULT_MANIFEST_NAME: Final = "draft"
_DIR_MODE: Final = 0o700


class SandboxPathError(ValueError):
    """A path resolved outside the sandbox, or outside the folder it must be in."""


class DraftLike(Protocol):
    """The part of a stored revision that :meth:`BuilderSandbox.rebuild` reads.

    Satisfied by the ``WorkflowBuilderDraft`` row and by the API's revision model.
    """

    @property
    def manifest(self) -> Mapping[str, Any]:
        """The full manifest."""
        ...

    @property
    def source_file(self) -> str | None:
        """Virtual sandbox path an unproposed revision came from."""
        ...


def resolve_builder_root(
    configured: str | None = None, runs_root: str | None = None
) -> Path:
    """Return the absolute root that holds every builder sandbox.

    Args:
        configured: ``BUILDER_SANDBOX_ROOT``. ``None`` reads the setting; an
            empty string selects the default.
        runs_root: ``RUNS_ROOT`` for the default. ``None`` reads the setting.

    Returns:
        ``configured`` resolved, or ``<runs_root>/_builder`` resolved.
    """
    value = settings.BUILDER_SANDBOX_ROOT if configured is None else configured
    if value and value.strip():
        return Path(value.strip()).resolve()
    base = settings.RUNS_ROOT if runs_root is None else runs_root
    return (Path(base) / BUILDER_SUBDIR).resolve()


def _user_dir(root: Path, user_id: str) -> Path:
    """Return the resolved user folder under ``root``, refusing an escape."""
    path = (root / _safe_segment(user_id, fallback="anonymous")).resolve()
    if not path.is_relative_to(root):
        raise SandboxPathError("user folder resolved outside the builder root")
    return path


def _remove_tree(path: Path) -> bool:
    """Delete ``path``; retry once; log and return ``False`` on failure."""
    if not path.exists():
        return True
    for attempt in (1, 2):
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            return True
        except OSError:
            logger.warning(
                "builder sandbox delete failed (attempt %d) path=%s",
                attempt,
                path.name,
                exc_info=True,
            )
        else:
            return True
    logger.error("builder sandbox could not be deleted path=%s", path.name)
    return False


class BuilderSandbox:
    """The on-disk sandbox of one builder session.

    Construction touches no disk. Call :meth:`ensure` or :meth:`rebuild` to
    create the folders.

    Attributes:
        root: The resolved builder root.
        user_seg: The safe folder name of the user.
        session_seg: The safe folder name of the session.
        path: The resolved session folder.
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        *,
        root: str | Path | None = None,
    ) -> None:
        """Bind the sandbox to a user and session.

        Args:
            user_id: The owning user's id.
            session_id: The builder session id.
            root: Builder root. ``None`` uses :func:`resolve_builder_root`, which
                reads ``BUILDER_SANDBOX_ROOT`` and ``RUNS_ROOT``.

        Raises:
            SandboxPathError: The session folder would resolve outside the root.
        """
        self.root = resolve_builder_root() if root is None else Path(root).resolve()
        self.user_seg = _safe_segment(user_id, fallback="anonymous")
        self.session_seg = _safe_segment(session_id, fallback="session")
        self._user_dir = _user_dir(self.root, user_id)
        self.path = (self._user_dir / self.session_seg).resolve()
        if not self.path.is_relative_to(self._user_dir):
            raise SandboxPathError("session folder resolved outside the user folder")

    def exists(self) -> bool:
        """Return whether the session folder is on disk."""
        return self.path.is_dir()

    def ensure(self) -> bool:
        """Create the session folder and its standard sub-folders.

        Returns:
            ``True`` when the session folder did not exist before the call.
        """
        created = not self.path.is_dir()
        for rel in SANDBOX_DIRS:
            self.path_for(rel).mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        return created

    def path_for(self, relative: str) -> Path:
        """Resolve a path inside the sandbox.

        Args:
            relative: A path relative to the session folder. A leading ``/`` is
                allowed, so virtual agent paths such as ``/workflows/a.json`` work.

        Returns:
            The resolved absolute path.

        Raises:
            SandboxPathError: The path resolves outside the session folder.
        """
        target = (self.path / relative.replace("\\", "/").lstrip("/")).resolve()
        if not target.is_relative_to(self.path):
            raise SandboxPathError("path resolved outside the sandbox")
        return target

    def call_temp_dir(self, call_id: str) -> Path:
        """Create and return the temp folder of one script call.

        The script runner removes the folder when the call ends. Ids that differ
        only in unsafe characters map to the same folder, so pass unique ids.

        Args:
            call_id: The tool-call id.

        Returns:
            ``<session>/.tmp/<safe call id>``.

        Raises:
            SandboxPathError: The folder would resolve outside ``.tmp``.
        """
        tmp_root = self.path_for(_TMP_DIR)
        target = (tmp_root / _safe_segment(call_id, fallback="call")).resolve()
        if not target.is_relative_to(tmp_root):
            raise SandboxPathError("call folder resolved outside .tmp")
        target.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        return target

    def rebuild(
        self,
        latest_draft: DraftLike | None,
        latest_unproposed: DraftLike | None,
    ) -> list[Path]:
        """Recreate a missing sandbox from the stored revisions (Req 20.12).

        Creates the folders, writes the latest seed, accepted or undo revision to
        ``workflows/<manifest id or "draft">.workflow.json``, and writes the
        latest unproposed revision back to its ``source_file``. Existing files
        with those names are overwritten.

        Args:
            latest_draft: The latest seed, accepted or undo revision, or ``None``.
            latest_unproposed: The latest unproposed revision, or ``None``.

        Returns:
            The files written, draft first.

        Raises:
            SandboxPathError: An unproposed revision's ``source_file`` is missing,
                resolves outside the sandbox, or is not under ``/workflows/``.
        """
        self.ensure()
        written: list[Path] = []
        if latest_draft is not None:
            name = _manifest_file_name(latest_draft.manifest)
            written.append(
                self._write_manifest(f"{_WORKFLOWS_DIR}/{name}", latest_draft)
            )
        if latest_unproposed is not None:
            written.append(
                self._write_manifest(
                    self._workflows_path(latest_unproposed.source_file),
                    latest_unproposed,
                )
            )
        return written

    def delete_session(self) -> bool:
        """Delete this session's folder, retrying once on failure.

        A failure is logged and never raised, so it cannot undo the database
        deletion that precedes it (design section 4.5).

        Returns:
            ``True`` when the folder is gone, ``False`` when it could not be removed.
        """
        return _remove_tree(self.path)

    @classmethod
    def delete_user(cls, user_id: str, *, root: str | Path | None = None) -> bool:
        """Delete every sandbox of a user (account deletion, Req 31.7).

        Args:
            user_id: The user's id.
            root: Builder root. ``None`` uses :func:`resolve_builder_root`.

        Returns:
            ``True`` when the user's folder is gone, ``False`` when it could not
            be removed. Failures are logged, not raised.

        Raises:
            SandboxPathError: The user folder would resolve outside the root.
        """
        resolved = resolve_builder_root() if root is None else Path(root).resolve()
        return _remove_tree(_user_dir(resolved, user_id))

    def _workflows_path(self, source_file: str | None) -> str:
        """Validate an unproposed revision's virtual path; return it relative."""
        if not source_file:
            raise SandboxPathError("unproposed revision has no source_file")
        target = self.path_for(source_file)
        workflows = self.path_for(_WORKFLOWS_DIR)
        if target == workflows or not target.is_relative_to(workflows):
            raise SandboxPathError("source_file is not under /workflows/")
        return target.relative_to(self.path).as_posix()

    def _write_manifest(self, relative: str, draft: DraftLike) -> Path:
        """Write ``draft.manifest`` as JSON at ``relative`` and return the path."""
        target = self.path_for(relative)
        target.parent.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        target.write_text(
            json.dumps(draft.manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target


def _manifest_file_name(manifest: Mapping[str, Any]) -> str:
    """Return ``<safe manifest id or "draft">.workflow.json``."""
    raw = manifest.get("id")
    stem = _safe_segment(
        raw if isinstance(raw, str) else "", fallback=_DEFAULT_MANIFEST_NAME
    )
    return f"{stem}{_MANIFEST_SUFFIX}"
