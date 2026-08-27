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

# Reserved sandbox prefix for the engine-owned run trace (R-23/R-24, spec 012).
# The engine writes ``.logs/run-logs.jsonl``; no agent has a tool that can
# append to it. Prefix-based exclusion (F-09) so a stray agent write anywhere
# under ``.logs/`` is dropped from the deliverable rather than corrupting the
# trace or leaking into the delivered artifact tree.
_LOGS_PREFIX = ".logs/"

# Reserved prefix for the pptx gate's evidence (spec 017): the validator report,
# the rendered slide images, and the exact source of each build attempt. Written
# by the tools, read by a human through the workspace view — never part of the
# delivered artifact, for the same reason ``.logs/`` is not.
_VERIFY_PREFIX = ".verify/"

# Reserved sandbox prefix for AGENT OUTPUTS — the text an agent streamed rather
# than wrote through ``write_file``. Until this existed the sandbox held only what
# an agent explicitly authored, so a step that just streamed prose left nothing on
# disk and the Workspace tab could not show it; its text survived only as the
# ``WorkflowRun.agent_outputs`` DB column that the Files tab renders.
#
# THIS PREFIX IS THE ONLY ONE THAT IS LISTED BUT NOT DELIVERED, and that asymmetry
# is the whole point. ``list_files`` (the Workspace tab) shows it; the deliverable
# walk below skips it. Without the skip, every agent transcript would be glued
# into ``serialize_sandbox_deliverable``'s output — i.e. into ``WorkflowRun.output``,
# the string the deliverable resolvers, the Files tab and AppBuilderPreview all
# parse — so a deck would come back with its own build transcripts inside it.
# INV-3: a golden run writes nothing here, so serialization stays byte-identical.
_AGENT_OUTPUTS_PREFIX = ".agents/"

# Caps for the workspace LISTING (spec 017 phase 2). A run sandbox is written by
# agents, so nothing bounds its file count or tree depth but the agent's own
# behaviour — a runaway loop can leave thousands of files behind. The listing
# endpoint is a UI convenience, not an archive: it stops at these and says so,
# rather than serving an unbounded response. The read endpoint has its own byte
# cap; these two bound the listing side.
_LIST_MAX_FILES = 500
_LIST_MAX_DEPTH = 12

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
        logger.debug("ensure %s", self.root)
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
        result = self._ws().write_file(relpath, content)  # type: ignore[attr-defined]
        logger.debug("write %s (%d chars)", relpath, len(content))
        return result

    def read(self, relpath: str) -> str | None:
        # Preserve the legacy contract: missing file → None (LocalWorkspace.read_file
        # raises on a missing file, so guard is_file() here to keep byte-parity).
        p = self.path_for(relpath)
        if not p.is_file():
            logger.debug("read %s -> (absent)", relpath)
            return None
        result = self._ws().read_file(relpath)  # type: ignore[attr-defined]
        logger.debug("read %s -> %d chars", relpath, len(result))
        return result

    def list_files(self) -> tuple[list[dict], bool]:
        """List the regular files in this sandbox as ``(files, truncated)``.

        Each entry is ``{"path": <posix relpath>, "size": <bytes>, "modified":
        <epoch seconds>}``, sorted by path. Returns ``([], False)`` when the run
        dir is absent — a TTL-swept run is EMPTY, not an error; the caller
        distinguishes the two by testing ``root`` itself.

        DIRECTORIES ARE NOT EMITTED, deliberately. The consumer builds its tree
        by splitting these paths, so a directory row would be data nothing reads
        — and the only case it would add (an empty directory) is one an agent
        cannot produce through ``write_file`` anyway.

        The reserved subtrees are excluded on the same grounds they are excluded
        from the deliverable: ``.uploads/`` is the owner's own upload staging
        (already listed by its manifest) and ``.logs/`` is the engine-owned run
        trace, surfaced through the audit view rather than as workspace files.

        ``os.walk`` does not follow symlinks, and ``is_file()`` drops dangling
        links, FIFOs and sockets — so a symlink planted in the sandbox cannot
        make this list, or later read, a file outside the run dir.
        """
        if not self.root.is_dir():
            return [], False
        files: list[dict] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = Path(dirpath).relative_to(self.root)
            depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)
            if depth >= _LIST_MAX_DEPTH:
                # Prune in place so os.walk does not descend further.
                if dirnames:
                    truncated = True
                dirnames[:] = []
            for name in sorted(filenames):
                full = Path(dirpath) / name
                if not full.is_file():
                    continue
                relpath = full.relative_to(self.root).as_posix()
                if relpath.startswith(_UPLOADS_PREFIX) or relpath.startswith(_LOGS_PREFIX):
                    continue
                if len(files) >= _LIST_MAX_FILES:
                    return sorted(files, key=lambda f: f["path"]), True
                try:
                    st = full.stat()
                except OSError:
                    continue
                files.append({"path": relpath, "size": st.st_size, "modified": st.st_mtime})
        return sorted(files, key=lambda f: f["path"]), truncated

    def audit_log(self, event: str, detail: dict) -> None:
        """Trace-only structured audit line (mirrors the reference tracer)."""
        logger.debug("audit_log %s %s", event, detail)

    def cleanup(self) -> None:
        """Remove the run dir (idempotent).

        OWNS the disk delete: ``LocalWorkspace.teardown()`` delegates HERE (never
        the reverse), so the sandbox<->workspace pair has exactly ONE rmtree owner
        and no teardown cycle. Both entry points — this facade and
        ``LocalSandboxRuntime.teardown(ws)`` — land on this single rmtree.
        """
        logger.debug("cleanup %s", self.root)

        def _on_rm_error(func, path, exc) -> None:
            # Windows marks files under a cloned .git tree read-only; clear the
            # bit and retry once before giving up on that entry (still swallowed
            # overall — cleanup stays best-effort/idempotent, matching the prior
            # `ignore_errors=True` contract).
            try:
                os.chmod(path, 0o700)
                func(path)
            except OSError:
                pass

        shutil.rmtree(self.root, ignore_errors=False, onexc=_on_rm_error)


def sweep_expired(
    *,
    ttl_hours: int | None = None,
    runs_root: str | None = None,
    protected_run_ids: set[str] | None = None,
) -> int:
    """Remove run dirs older than the TTL. Returns the count removed.

    D6 (KAN-139) hardening over the original implementation:

    1. **DB-backed protection set** (``protected_run_ids``): any run directory whose
       base name (the run_seg derived from the run_id) appears in this set is NEVER
       deleted, regardless of its mtime. Callers build this set from the union of
       non-terminal DB run IDs and the in-process ``_PIPELINE_QUEUES`` live registry
       so an active build run is always protected even if the directory mtime is stale
       (POSIX directory mtime does NOT advance when files inside are overwritten,
       e.g. prototype build ``edit_file`` path). When the argument is omitted (or
       ``None``) the protection set is empty — the pre-D6 behavior is preserved for
       test callers that do not pass DB context.

    2. **mtime as a second necessary condition only** (not sufficient alone): a run dir
       is eligible for deletion iff its mtime is past the cutoff AND its run_seg is
       NOT in ``protected_run_ids``. Either condition blocks deletion.

    Safe to call periodically (on pipeline completion or a timer). Walks exactly two
    levels: ``<RUNS_ROOT>/<user>/<run>``.
    """
    ttl_seconds = (ttl_hours if ttl_hours is not None else settings.RUN_DIR_TTL_HOURS) * 3600
    root = Path(runs_root or settings.RUNS_ROOT)
    if not root.is_dir():
        return 0
    cutoff = time.time() - ttl_seconds
    protected = protected_run_ids or set()
    removed = 0
    for user_dir in root.iterdir():
        if not user_dir.is_dir():
            continue
        for run_dir in user_dir.iterdir():
            try:
                if not run_dir.is_dir():
                    continue
                # D6: protection check BEFORE mtime check so a protected run is
                # never deleted even with a stale mtime (prototype build path).
                # run_dir.name is the run_seg derived from the run_id by _safe_segment;
                # exact match is correct because _safe_segment is injective for UUIDs.
                if run_dir.name in protected:
                    continue
                if run_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    if removed:
        logger.info("sandbox sweep: removed %d expired run dir(s) under %s", removed, root)
    return removed


# ---------------------------------------------------------------------------
# Streamed agent outputs — workspace-visible, never deliverable
# ---------------------------------------------------------------------------


def agent_output_relpath(
    *, index: int, agent_id: str, task_number: str = "", visit_count: int = 0
) -> str:
    """The sandbox path one agent invocation's streamed output is written to.

    ``index`` is the engine's own 0-based step position, and the filename is
    ONE-BASED: these names are read by a person in the Workspace tab, where a
    first step called ``00-`` reads as a numbering bug. Converted here, in the
    one function that owns the user-facing name, so the call site keeps passing
    the engine's value unmodified.

    ``.agents/{index+1:02d}-{agent_id}.md``, with the loop identity appended when
    the same step runs more than once — a task-loop agent and a revisited step
    both complete repeatedly, and a bare per-agent name would let pass 2 silently
    overwrite pass 1. Mirrors the ``task_number``/``visit_count`` pair the engine
    already carries on ``agent_complete``: both are omitted when absent/zero, so
    the single-shot case (every golden run) stays the short form.
    """
    stem = f"{index + 1:02d}-{_safe_segment(agent_id, fallback='agent')}"
    if task_number:
        stem += f"-t{_safe_segment(str(task_number), fallback='0')}"
    if visit_count:
        stem += f"-p{int(visit_count)}"
    return f"{_AGENT_OUTPUTS_PREFIX}{stem}.md"


def write_agent_output(
    sandbox: object,
    *,
    index: int,
    agent_id: str,
    name: str,
    output: str,
    task_number: str = "",
    visit_count: int = 0,
) -> str | None:
    """Persist one agent's streamed output into the run sandbox. Best-effort.

    Returns the relative path written, or ``None`` when there was nothing to write
    or the write failed. NEVER raises: this runs on the completion path of a step
    that has already succeeded, and a full disk or a read-only volume must not
    turn a finished agent into a failed run. The UI stream is unaffected either
    way — this is an additional record, not the transport.

    ``sandbox`` is duck-typed (the engine's runner supplies it and it can be
    ``None`` on harness paths), so the ``write`` attribute is probed rather than
    assumed.
    """
    if not output or not output.strip():
        return None
    writer = getattr(sandbox, "write", None)
    if not callable(writer):
        return None
    relpath = agent_output_relpath(
        index=index, agent_id=agent_id, task_number=task_number, visit_count=visit_count
    )
    header = f"# {name or agent_id}\n\n"
    try:
        writer(relpath, header + output)
    except Exception:  # noqa: BLE001 — see the never-raises contract above
        logger.warning("could not persist agent output for %s", agent_id, exc_info=True)
        return None
    return relpath


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


def is_deliverable_relpath(
    relpath: str, *, exclude: frozenset[str] | Iterable[str] = None  # type: ignore[assignment]
) -> bool:
    """Is ``relpath`` part of what the run DELIVERED, as opposed to how it worked?

    The single definition of that question. ``_collect_deliverable_relpaths``
    applies it while walking, and the workspace API applies it per listed file
    so the UI can group Deliverables without re-deriving the rule — and without
    a copy of ``_DELIVERABLE_EXCLUDE`` in TypeScript that drifts from this one.

    Excluded are the four reserved subtrees (owner uploads, the engine's run
    trace, a gate tool's evidence, and the streamed agent outputs) plus anything
    matching ``exclude`` by full relative path OR by basename.
    """
    exclude_set = frozenset(_DELIVERABLE_EXCLUDE if exclude is None else exclude)
    if relpath.startswith(
        (_UPLOADS_PREFIX, _LOGS_PREFIX, _VERIFY_PREFIX, _AGENT_OUTPUTS_PREFIX)
    ):
        return False
    return relpath not in exclude_set and relpath.rsplit("/", 1)[-1] not in exclude_set


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
            # The reserved subtrees (uploads UPLD-01, the engine run trace, a
            # gate's evidence, the streamed agent outputs) and the exclude set
            # are all applied by is_deliverable_relpath — one definition, so the
            # workspace API cannot drift from the walk. Dormant on golden runs
            # (no such dirs → identical output, INV-3).
            if not is_deliverable_relpath(relpath, exclude=exclude_set):
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
