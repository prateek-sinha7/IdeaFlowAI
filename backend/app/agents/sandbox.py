"""app/agents/sandbox.py — per-user/per-run disk sandbox for the deepagents filesystem.

Each pipeline run gets an isolated directory ``<RUNS_ROOT>/<user>/<run>/`` on the
persistent runs volume. The deepagents disk filesystem backend is rooted here, so
one user's run can never read or write another's files, and a ``..`` traversal
cannot escape the run dir. Finished runs are swept after ``RUN_DIR_TTL_HOURS``.

This is the user-based workspace isolation requirement, implemented on real disk.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from collections.abc import Iterable
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("app.agents.sandbox")

# Default deliverable exclusion set — the engine writes ``PLANNER.md`` as an
# internal planning artifact, so it must not appear in the deliverable string
# the FilesTab / AppBuilderPreview parse. (Mirrors the now-removed legacy
# ``AgentWorkspace._INTERNAL_FILES``; the byte-oracle for this serialisation is
# pinned by ``tests/agents/test_sandbox_deliverable.py``.)
_DELIVERABLE_EXCLUDE: frozenset[str] = frozenset({"PLANNER.md"})

# Reserved sandbox prefix for owner-uploaded documents (UPLD-01). Files the
# ``POST /api/runs/{id}/files`` endpoint lands here — the raw upload, its
# extracted-text ``.txt`` sidecar, and ``manifest.json`` — exist ONLY so agents
# can ``read_file`` them and 30-02's ``uploaded_files`` context provider can
# surface their text as sticky context. They are NEVER part of the deliverable
# the FilesTab / AppBuilderPreview parse, so the whole subtree is excluded from
# the deliverable walk (prefix-aware, alongside the exact-name exclude below).
# INV-3: a golden run writes nothing under ``.uploads/``, so this exclusion is
# dormant and ``serialize_sandbox_deliverable`` stays byte-identical.
_UPLOADS_PREFIX = ".uploads/"

# Sentinel emitted when no deliverable files exist — kept byte-identical to the
# legacy deliverable format so the engine produces the same ``WorkflowRun.output``
# string from the on-disk sandbox.
_EMPTY_SENTINEL = "(no files written)"

# Map any user/run identifier to ONE safe path segment. user_id is a UUID or an
# email; run_id is a UUID. We allow [A-Za-z0-9._-] and replace everything else, so
# an identifier can never introduce a path separator or a traversal sequence.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_segment(value: str, *, fallback: str) -> str:
    seg = _UNSAFE.sub("_", (value or "").strip())
    seg = seg.strip(".")  # ".", ".." → "" so they can never be a segment
    return (seg or fallback)[:128]


class RunSandbox:
    """An isolated on-disk workspace for one pipeline run — a thin ``Workspace`` facade.

    ``root`` = ``<RUNS_ROOT>/<user>/<run>/``. Create it with :meth:`ensure`,
    resolve paths inside it with :meth:`path_for` (rejects escapes), remove it
    with :meth:`cleanup`.

    D-02 refold (RUNTIME-02, move-don't-copy): the consumed surface
    (``__init__(user_id, run_id)`` / ``ensure`` / ``root`` / ``path_for`` / ``read``
    / ``write`` / ``cleanup``) survives BYTE-FOR-BYTE so every call site is
    untouched, but the bespoke per-run disk read/write/cleanup logic is DELEGATED
    to a ``Workspace(has_git=False, exec=off)`` provisioned by the
    ``LocalSandboxRuntime`` (09-01). One ``Workspace`` abstraction now serves both
    artifact (``has_git=False``, here) and repo (``has_git=True``, 09-04) workspaces
    — there is NO ``if repo:`` engine fork. ``RunSandbox`` keeps the traversal-proof
    disk PRIMITIVES (``root`` resolution + ``path_for``) because the ``Workspace``
    impl itself reuses them (``LocalWorkspace`` is constructed FROM this sandbox);
    the facade's ``read``/``write``/``cleanup`` route through that Workspace so the
    disk IO lives in ONE place.
    """

    def __init__(self, user_id: str, run_id: str, *, runs_root: str | None = None) -> None:
        self.user_seg = _safe_segment(user_id, fallback="anonymous")
        self.run_seg = _safe_segment(run_id, fallback="run")
        base = Path(runs_root or settings.RUNS_ROOT).resolve()
        self.base = base
        self.root = (base / self.user_seg / self.run_seg).resolve()
        # Defence in depth: the resolved run dir must stay under RUNS_ROOT even if
        # the sanitiser is ever weakened. ``is_relative_to`` is separator-aware, so
        # containment holds on both POSIX ("/") and Windows ("\\") — a plain
        # ``startswith(base + "/")`` string check falsely rejects every path on
        # Windows.
        if not self.root.is_relative_to(base):
            raise ValueError(f"sandbox root escaped RUNS_ROOT: {self.root}")
        # The delegated has_git=False / exec=off Workspace facade (lazily built so
        # the disk root exists first and to avoid the local.py import cycle).
        self._workspace: object | None = None

    def _ws(self) -> object:
        """The has_git=False, exec=off ``Workspace`` this sandbox delegates disk IO to.

        Built lazily (and cached) from THIS sandbox so the single ``LocalWorkspace``
        disk impl (09-01) owns read/write — move-don't-copy. The import is local to
        sidestep the ``local.py`` → ``sandbox.py`` import cycle.
        """
        if self._workspace is None:
            from app.agents.runtime.local import (
                LocalExecutionPolicy,
                LocalWorkspace,
            )

            self.ensure()  # the Workspace roots at the ensured run dir
            self._workspace = LocalWorkspace(
                owner_id=self.user_seg,
                workspace_id=self.run_seg,
                runtime=None,  # no provisioning runtime for the facade path
                policy=LocalExecutionPolicy(exec=False, network=False, secrets=[]),
                sandbox=self,
            )
        return self._workspace

    def ensure(self) -> Path:
        """Create the run dir (parents, mode 0700) and return it."""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass  # best-effort on filesystems that don't honour chmod
        return self.root

    def path_for(self, relpath: str) -> Path:
        """Resolve ``relpath`` inside the sandbox, rejecting any escape."""
        candidate = (self.root / str(relpath).lstrip("/")).resolve()
        # Separator-aware containment (see __init__): correct on Windows and POSIX.
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"path escapes run sandbox: {relpath!r}")
        return candidate

    def write(self, relpath: str, content: str) -> Path:
        # Delegate to the has_git=False Workspace (LocalWorkspace.write_file) — the
        # single disk-write impl. It mkdir(parents)s + writes UTF-8 under the
        # traversal-proof path_for, identical to the legacy inline body.
        return self._ws().write_file(relpath, content)  # type: ignore[attr-defined]

    def read(self, relpath: str) -> str | None:
        # Preserve the legacy contract: missing file → None (LocalWorkspace.read_file
        # raises on a missing file, so guard is_file() here to keep byte-parity).
        p = self.path_for(relpath)
        if not p.is_file():
            return None
        return self._ws().read_file(relpath)  # type: ignore[attr-defined]

    def cleanup(self) -> None:
        """Remove the run dir (idempotent).

        OWNS the disk delete: ``LocalWorkspace.teardown()`` delegates HERE (never
        the reverse), so the sandbox<->workspace pair has exactly ONE rmtree owner
        and no teardown cycle. Both entry points — this facade and
        ``LocalSandboxRuntime.teardown(ws)`` — land on this single rmtree.
        """
        shutil.rmtree(self.root, ignore_errors=True)


def sweep_expired(*, ttl_hours: int | None = None, runs_root: str | None = None) -> int:
    """Remove run dirs older than the TTL (by mtime). Returns the count removed.

    Safe to call periodically (on pipeline completion or a timer). Walks exactly
    two levels: ``<RUNS_ROOT>/<user>/<run>``.
    """
    ttl_seconds = (ttl_hours if ttl_hours is not None else settings.RUN_DIR_TTL_HOURS) * 3600
    root = Path(runs_root or settings.RUNS_ROOT)
    if not root.is_dir():
        return 0
    cutoff = time.time() - ttl_seconds
    removed = 0
    for user_dir in root.iterdir():
        if not user_dir.is_dir():
            continue
        for run_dir in user_dir.iterdir():
            try:
                if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    if removed:
        logger.info("sandbox sweep: removed %d expired run dir(s) under %s", removed, root)
    return removed


# ---------------------------------------------------------------------------
# Deliverable serialisation — the disk deliverable format
# ---------------------------------------------------------------------------
#
# The deliverable is the ``WorkflowRun.output`` string the frontend FilesTab /
# AppBuilderPreview parse: one ```` ```filename: <path>\n<content>\n``` ````
# block per deliverable file, sorted by path, joined by a blank line, with the
# sentinel ``"(no files written)"`` when empty. This reproduces the legacy
# (now-removed) in-memory code-gen serialiser BYTE-FOR-BYTE; the byte-oracle is
# pinned by ``tests/agents/test_sandbox_deliverable.py``.
#
# In the Phase-3 cutover the native ``deepagents`` ``write_file`` tool lands
# those same files on the run sandbox disk instead. These helpers walk that
# directory and reproduce the SAME string BYTE-FOR-BYTE so the deliverable the
# UI receives is unchanged. They are isolated and additive — Task #42 wires them
# into the engine; nothing here imports the engine, factory, or workspace.


def _collect_deliverable_relpaths(
    root: Path, exclude: frozenset[str] | Iterable[str]
) -> list[str]:
    """Walk ``root`` and return the POSIX relative paths of deliverable files.

    A *deliverable* is any regular file under ``root`` whose relative path is
    NOT excluded. Exclusion matches BOTH the full POSIX relative path AND the
    basename, so an excluded name (e.g. ``"PLANNER.md"``) is dropped wherever it
    appears in the tree. The result is sorted by relative path.

    Sort note: ``to_final_output()`` does ``sorted(deliverable.items())`` —
    i.e. it sorts by its dict keys, which are sanitised relative paths (POSIX
    separators, no leading slash). Sorting these relative-POSIX strings with the
    same default ``str`` ordering yields the identical sequence (verified
    empirically in the Task-#40 test for any set of paths that survive a
    round-trip through the filesystem), so the emitted blocks are in the same
    order as the in-memory path. ``os.walk`` order itself is irrelevant — we
    always re-sort.
    """
    exclude_set = frozenset(exclude)
    relpaths: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        dir_ = Path(dirpath)
        for name in filenames:
            full = dir_ / name
            # ``os.walk`` yields directory entries; only emit regular files
            # (skip symlinks-to-dirs, FIFOs, sockets, dangling symlinks). This
            # also means an excluded *directory* name is never matched here —
            # exclusion is by file path/basename, exactly like the workspace.
            if not full.is_file():
                continue
            relpath = full.relative_to(root).as_posix()
            # Prefix-aware exclusion for the reserved uploads subtree (UPLD-01):
            # every raw upload + ``.txt`` sidecar + ``manifest.json`` lives under
            # ``.uploads/`` and must never surface as a deliverable file. Dormant
            # on golden runs (no ``.uploads/`` dir → identical output, INV-3).
            if relpath.startswith(_UPLOADS_PREFIX):
                continue
            if relpath in exclude_set or name in exclude_set:
                continue
            relpaths.append(relpath)
    relpaths.sort()
    return relpaths


def serialize_sandbox_deliverable(
    root: str | Path,
    *,
    exclude: frozenset[str] | Iterable[str] = _DELIVERABLE_EXCLUDE,
) -> str:
    """Serialise the files written into a run sandbox as the deliverable string.

    Disk analogue of ``AgentWorkspace.to_final_output()``: walks ``root``
    recursively, collects every regular file as a path relative to ``root``
    (POSIX separators), drops files matching ``exclude`` (by relative path AND
    by basename), sorts by relative path, and returns each as a
    ```` ```filename: {relpath}\n{content}\n``` ```` block joined by ``"\n\n"``.
    Returns ``"(no files written)"`` when there are no deliverable files —
    byte-identical to ``to_final_output()`` so the Phase-3 engine produces the
    same ``WorkflowRun.output`` from disk that it does from the in-memory
    workspace today (the UI-identical invariant).

    Files are read as raw bytes and decoded as UTF-8 with newline translation
    DISABLED (``Path.read_bytes().decode("utf-8")``, not ``Path.read_text``).
    This is deliberate and load-bearing for byte-equivalence: ``read_text``
    applies universal-newline translation on read (any ``\\r`` / ``\\r\\n`` →
    ``\\n``), which would silently mutate a file whose content contains carriage
    returns and diverge from the in-memory ``AgentWorkspace`` (which stores the
    agent's string verbatim). Reading raw bytes reproduces exactly what was
    written, so a CRLF-bearing deliverable round-trips byte-for-byte.

    A file that cannot be decoded as UTF-8 (binary) or cannot be read at all
    (e.g. a race-deleted file) is **skipped** — never raises, never emits a
    partial/garbled block. The in-memory path only ever holds ``str`` content
    written via the text-only ``write_file`` tool, so a well-formed code-gen run
    never hits this branch; the guard is purely defensive for stray non-text
    artifacts.

    Args:
        root: The sandbox run directory (``RunSandbox.root``). A non-existent or
            empty directory yields the empty sentinel.
        exclude: File names/relative paths to omit from the deliverable.
            Defaults to ``{"PLANNER.md"}`` (the engine's internal planning
            artifact), matching ``AgentWorkspace._INTERNAL_FILES``.

    Returns:
        The ``filename:``-block deliverable string, or ``"(no files written)"``.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return _EMPTY_SENTINEL

    parts: list[str] = []
    for relpath in _collect_deliverable_relpaths(root_path, exclude):
        try:
            # Raw bytes + explicit decode (NOT read_text): preserves \r / \r\n
            # exactly, so the round-trip is byte-identical to the in-memory
            # string. See the docstring's "Files are read as raw bytes" note.
            content = (root_path / relpath).read_bytes().decode("utf-8")
        except (OSError, ValueError, UnicodeDecodeError):
            # Unreadable or non-UTF-8 (binary) file: skip gracefully rather than
            # crash the whole deliverable or emit a corrupt block.
            logger.warning(
                "sandbox deliverable: skipping unreadable/non-UTF-8 file %r", relpath
            )
            continue
        parts.append(f"```filename: {relpath}\n{content}\n```")

    if not parts:
        return _EMPTY_SENTINEL
    return "\n\n".join(parts)


def count_sandbox_deliverables(
    root: str | Path,
    *,
    exclude: frozenset[str] | Iterable[str] = _DELIVERABLE_EXCLUDE,
) -> int:
    """Count deliverable files under ``root`` — disk analogue of ``file_count()``.

    Counts regular files (excluding ``exclude``, by relative path AND basename),
    matching ``AgentWorkspace.file_count()``. Unlike
    :func:`serialize_sandbox_deliverable`, this does NOT read file contents, so
    a binary/unreadable file is still counted (it exists as a deliverable);
    ``file_count()`` likewise counts every non-internal key regardless of
    content. A non-existent directory counts as 0.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return 0
    return len(_collect_deliverable_relpaths(root_path, exclude))
