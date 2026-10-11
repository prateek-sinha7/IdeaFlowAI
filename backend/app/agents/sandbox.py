"""app/agents/sandbox.py — per-user/per-run disk sandbox for the deepagents filesystem.

Each pipeline run gets an isolated directory ``<RUNS_ROOT>/<user>/<run>/`` on the
persistent runs volume. The deepagents disk filesystem backend is rooted here, so
one user's run can never read or write another's files, and a ``..`` traversal
cannot escape the run dir. Finished runs are swept after ``RUN_DIR_TTL_HOURS``.

This is the user-based workspace isolation requirement, implemented on real disk.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.agents.runtime.local import RefResult

# ── Cross-platform exclusive file-locking primitives ────────────────────────
# The existing _manifest_lock in run_files.py uses fcntl.flock which silently
# no-ops on Windows (fcntl is None there). The family lock MUST hold on both
# platforms (Requirement 10 AC 1-2), so we use the OS-native primitive on each:
#   Linux/macOS — fcntl.flock with LOCK_EX | LOCK_NB (non-blocking so we can
#                 implement a timed poll loop ourselves)
#   Windows    — msvcrt.locking with msvcrt.LK_NBLCK (non-blocking, same reason)
# On both platforms we poll at _FAMILY_LOCK_POLL_S intervals until the timeout
# expires, then raise FamilyLockTimeout.  A blocking acquire with a wall-clock
# signal/alarm would be neater but is not portable and not available in
# async-context code.

if sys.platform == "win32":
    import msvcrt as _msvcrt  # type: ignore[import]  # Windows only

    _fcntl = None
else:
    import fcntl as _fcntl  # type: ignore[import]  # Unix only

    _msvcrt = None  # type: ignore[assignment]

_FAMILY_LOCK_POLL_S: float = 0.05  # poll cadence: 50 ms

logger = logging.getLogger("app.agents.sandbox")

# Default deliverable exclusion set — the engine writes ``PLANNER.md`` as an
# internal planning artifact, so it must not appear in the deliverable string
# the FilesTab / AppBuilderPreview parse. (Mirrors the now-removed legacy
# ``AgentWorkspace._INTERNAL_FILES``; the byte-oracle for this serialisation is
# pinned by ``tests/agents/test_sandbox_deliverable.py``.)
#
# Requirement 9: ``.git`` (bare directory name), ``.gitignore`` (bare filename),
# and ``skills`` (bare directory name) are also excluded from the deliverable.
# ``is_deliverable_relpath`` checks both the full relative path AND the basename,
# so these bare names drop the entries regardless of where in the tree they sit.
_DELIVERABLE_EXCLUDE: frozenset[str] = frozenset(
    {
        "PLANNER.md",  # engine planning artifact
        ".git",  # git repository metadata — Requirement 9
        ".gitignore",  # git configuration file — Requirement 9
        "skills",  # staged skill bodies must not ship in user deliverables — Requirement 9
        # family_lock's lock file (see _family_lock_path): it sits in the
        # revision-root dir, which IS a root run's sandbox, so an upload (which
        # takes the lock) otherwise ships an empty `.family.lock` block.
        ".family.lock",
    }
)

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

# Reserved sandbox prefix for the engine-owned run trace (Requirement 24).
# The engine writes ``.logs/{run_id}.jsonl`` (one file per run so that
# multiple revisions sharing a sandbox do not clobber each other); no agent
# has a tool that can append to it. Prefix-based exclusion (F-09) so a stray
# agent write anywhere under ``.logs/`` is dropped from the deliverable rather
# than corrupting the trace or leaking into the delivered artifact tree.
_LOGS_PREFIX = ".logs/"

# Reserved prefix for the pptx gate's evidence (spec 017): the validator report,
# the rendered slide images, and the exact source of each build attempt. Written
# by the tools, read by a human through the workspace view — never part of the
# delivered artifact, for the same reason ``.logs/`` is not.
_VERIFY_PREFIX = ".verify/"

# Reserved sandbox prefix for browser-based agent outputs (screenshots and page
# captures). These files are evidence for the human through the workspace view —
# never part of the deliverable, just like .verify/ files.
_BROWSER_PREFIX = ".browser/"

# Reserved sandbox prefix for materialised document pages (spec 019). The extracted
# pages and their rendered images are evidence for the human through the workspace
# view — never part of the deliverable, just like .verify/ and .browser/ files.
# Layout is .extract/{format}/{slug}/pages/NN/ — the format is a directory level,
# so a .docx and a .pdf of the same name cannot collide.
_EXTRACT_PREFIX = ".extract/"

# Reserved sandbox prefix for AGENT OUTPUTS — the text an agent streamed rather
# than wrote through ``write_file``. Until this existed the sandbox held only what
# an agent explicitly authored, so a step that just streamed prose left nothing on
# disk and the Workspace tab could not show it; its text survived only as the
# ``WorkflowRun.agent_outputs`` DB column that the Files tab renders.
#
# LISTED-BUT-NOT-DELIVERED: ``list_files`` (the Workspace tab) shows it; the
# deliverable walk below skips it. Without the skip, every agent transcript would
# be glued into ``serialize_sandbox_deliverable``'s output — i.e. into
# ``WorkflowRun.output``, the string the deliverable resolvers, the Files tab and
# AppBuilderPreview all parse — so a deck would come back with its own build
# transcripts inside it.
# INV-3: a golden run writes nothing here, so serialization stays byte-identical.
_AGENT_OUTPUTS_PREFIX = ".agents/"

# Reserved sandbox prefixes for git metadata and staged skill bodies (Requirement 9).
# Files under ``.git/`` are git internals — never part of the user's deliverable.
# Files under ``skills/`` are skill bodies staged for agent use — they must not
# ship inside user deliverables (pre-existing gap closed by Requirement 9).
# These are handled as PREFIX checks inside ``is_deliverable_relpath`` (same
# pattern as the other reserved subtrees) rather than as bare names in
# ``_DELIVERABLE_EXCLUDE``, because the basename check in that set only catches
# a file literally named ``.git`` or ``skills`` at the root — it cannot match
# ``.git/config`` or ``skills/writing/SKILL.md``.
_GIT_PREFIX = ".git/"
_SKILLS_PREFIX = "skills/"

# Reserved sandbox prefix for the structured CHAIN PAYLOAD written by the engine
# on the ``post_run`` terminal path (Requirement 20). Contents per run:
# ``.chain/{run_id}/summary.md``, the final deliverable copy, and ``logs/``
# holding the run log and agent transcripts.
#
# LISTED-BUT-NOT-DELIVERED — the same asymmetry as ``.agents/``:
# ``list_files`` shows it in the Workspace tab; the deliverable walk skips it so
# chain payload directories never appear in ``WorkflowRun.output`` or the zip.
# The single-file read endpoint serves it (it is NOT blocked), so the Workspace
# tab can read individual files inside ``.chain/``.
# INV-3: a golden run writes nothing here, so serialization stays byte-identical.
_CHAIN_PREFIX = ".chain/"

# Reserved sandbox prefix for the CONTEXT DIRECTORY written at sandbox open
# before step 1 (Requirement 23). Contains everything the run was given:
# OpenDesign material under ``.context/design/`` (design-system.md, craft.md,
# and template/ holding SKILL.md and the seed/reference files), and
# ``selections.json`` at the ``.context/`` root holding the wizard choices.
# For a chained run the source's ``.chain/{run_id}/`` is also copied here so
# ``.context/`` is the single place an agent looks for its inputs.
#
# LISTED-BUT-NOT-DELIVERED — same asymmetry as ``.agents/`` and ``.chain/``:
# ``list_files`` shows it in the Workspace tab; the deliverable walk skips it.
# ``.gitignore`` already covers it (task 2.2: seeded at git init time).
# INV-3: a golden run writes nothing here, so serialization stays byte-identical.
_CONTEXT_PREFIX = ".context/"

# ── Reserved-path registry (V2-Q7, Requirement 18) ───────────────────────────
#
# THE single canonical set of reserved sandbox paths. Every enforcement point
# (Git ignore seeding, Git staging, deliverable walk, ``list_files``, zip/archive
# route, public-share output, ``WorkflowRun.output``, agent file tools, and
# cross-run seed/context providers) MUST derive its exclusions from this one
# registry — never keep its own independent literal list.
#
# Adding a reserved path is a single edit here; the enforcement points pick it
# up automatically once task 2.2 wires them to the registry.
#
# ``conversation_history/`` is the only entry that was absent from the individual
# ``_*_PREFIX`` constants above — proof of the drift the registry exists to prevent.
# ``.chain-legacy/`` is the v2 addition for the relocated legacy nested payloads.
RESERVED_PATHS: frozenset[str] = frozenset(
    {
        ".uploads/",
        ".logs/",
        ".verify/",
        ".browser/",
        ".agents/",
        ".chain/",
        ".context/",
        "skills/",
        "conversation_history/",
        ".chain-legacy/",  # v2 addition — relocated legacy nested payloads
        ".extract/",  # materialised PDF/docx pages (019-pdf-extraction):
        # listed in the Workspace tab, never delivered — without
        # it every extracted page is glued into WorkflowRun.output.
    }
)

# The ONLY reserved prefix an authorized AGENT TOOL may READ.
# `.context/` is listed here because Requirement 8 AC 7 requires it to be
# "readable to authorized agents". `.chain/` is deliberately NOT here:
# Requirement 4 AC 10 and Requirement 18 AC 6 grant it read-visibility through
# the authorized Workspace surfaces (listing + reads at an authorized version
# ref) only — not through agent tools. Requirement 18 AC 8 requires a test to
# prove an agent tool cannot reach `.chain/`. Writes to any RESERVED_PATHS entry
# are refused unconditionally.
#
# `.agents/` was added 2026-09-11. The Q4 prompt migration (GAPS.md §0.2, the
# owner's decision, which that document states overrides both the original spec
# text and what v2 built) makes an upstream agent's output reach the next agent
# as a FILE at `.agents/NN-<agent-id>.md` instead of pasted into its message.
# 81 migrated `AGENT.md` reading guides name that path. Until this entry existed
# the guard refused every one of those reads, so the migration was inert: agents
# were told to read a directory they were categorically forbidden to open, and
# the live `ppt_v2` run that exposed it produced no deliverable at all because
# its composer could not reach the spec. This grants READ only — the write guard
# above refuses `write_file`/`edit_file`/`create_directory` for ANY reserved
# prefix regardless of this set, so `.agents/` stays engine-written.
# `.uploads/` was added at the same time and for the same reason: GAPS.md §0.2
# delivers the user's uploaded documents as `.uploads/<file>` plus a `.txt`
# sidecar for the agent to READ, replacing the old behaviour of pasting every
# document's full text into the message of every agent that declared them. The
# app_builder, dotnet and mulesoft guides already name that path.
AGENT_READABLE_RESERVED: frozenset[str] = frozenset(
    {
        ".context/",
        ".agents/",
        ".uploads/",
    }
)

# Excluded from listing, deliverable walk, deliverable counting, zip, and public
# share — but NOT a "reserved subtree" in the RESERVED_PATHS sense. These are
# Git internals that must be invisible to the product layer without needing the
# full engine-reservation treatment (no agent tool guard, no gitignore seeding,
# no cross-run seed guard is needed because Git already prevents writing them via
# its own mechanics). Kept separate so enforcement points that need BOTH sets can
# use ``RESERVED_PATHS | GIT_METADATA_PATHS`` while the family-lock and seeding
# logic can stay cleanly scoped to ``RESERVED_PATHS``.
GIT_METADATA_PATHS: frozenset[str] = frozenset(
    {
        ".git/",
        ".gitignore",
    }
)

# ── Pre-computed enforcement sets derived from the registries (V2-Q7) ────────
#
# These are computed ONCE at module import time from RESERVED_PATHS and
# GIT_METADATA_PATHS so every enforcement point pays no per-call overhead.
# All paths with trailing "/" are prefix guards; those without are exact guards.

# Combined prefix + exact sets for the DELIVERABLE walk (serialize, count, is_deliverable).
# Excludes every RESERVED_PATHS entry and every GIT_METADATA_PATHS entry — none of
# those appear in the deliverable.
_DELIVERABLE_EXCLUDED_PREFIXES: tuple[str, ...] = tuple(
    sorted(p for p in RESERVED_PATHS | GIT_METADATA_PATHS if p.endswith("/"))
)
_DELIVERABLE_EXCLUDED_EXACT: frozenset[str] = frozenset(
    p for p in RESERVED_PATHS | GIT_METADATA_PATHS if not p.endswith("/")
)

# Sets for the WORKSPACE LISTING (list_files). Same as the deliverable sets EXCEPT
# that .chain/, .context/, and .agents/ are deliberately VISIBLE in the listing
# (Requirement 4 AC 10, Requirement 8 AC 7) — they appear in the Workspace tab but
# are excluded from the deliverable walk.
# `.verify/` is visible too (spec 017 viewable media): render_pptx's PNG/PDF
# verdict evidence is the artifact a reviewer opens the Workspace tab to see.
# It stays excluded from the deliverable and remains write-reserved.
_LISTING_VISIBLE: frozenset[str] = frozenset(
    {".chain/", ".context/", ".agents/", ".verify/"}
)
_LISTING_EXCLUDED_PREFIXES: tuple[str, ...] = tuple(
    sorted(
        p
        for p in (RESERVED_PATHS - _LISTING_VISIBLE) | GIT_METADATA_PATHS
        if p.endswith("/")
    )
)
_LISTING_EXCLUDED_EXACT: frozenset[str] = frozenset(
    p
    for p in (RESERVED_PATHS - _LISTING_VISIBLE) | GIT_METADATA_PATHS
    if not p.endswith("/")
)


def payload_allowlist(output_basename: str) -> frozenset[str]:
    """Return the exact three normalized paths that the engine may force-stage.

    This is the ONLY exception to ``RESERVED_PATHS``: the engine is allowed to
    force-stage these three exact paths and no others.  The exception is expressed
    as an exact-path allowlist — never a ``.chain`` prefix match — so arbitrary or
    nested ``.chain`` content is never staged even when a caller passes it
    explicitly (Requirement 4 AC 11 and AC 14, V2-Q7).

    ``output_basename`` is the safe basename declared by the compiled deliverable
    (Requirement 4 AC 3).  It is validated here so a misconfigured workflow cannot
    produce a stale or colliding allowlist entry:

    - Must not contain a path separator (``/`` or ``\\``).
    - Must not be ``.`` or ``..``.
    - Must not collide case-insensitively with the two reserved payload names
      ``logs.jsonl`` or ``summary.md``.

    Raises ``ValueError`` on any violation so the caller sees a clear error at
    finalization time rather than silently staging a bad path.

    Lives in the registry block (rather than with the payload builder in task 5.2)
    because task 4.4 (wave 8) needs it before the payload builder exists.
    """
    if "/" in output_basename or "\\" in output_basename:
        raise ValueError(
            f"payload_allowlist: output_basename contains a path separator: {output_basename!r}"
        )
    if output_basename in (".", ".."):
        raise ValueError(
            f"payload_allowlist: output_basename must not be '.' or '..': {output_basename!r}"
        )
    lower = output_basename.lower()
    if lower in ("logs.jsonl", "summary.md"):
        raise ValueError(
            f"payload_allowlist: output_basename collides with a reserved payload name: "
            f"{output_basename!r}"
        )
    return frozenset(
        {
            ".chain/logs.jsonl",
            ".chain/summary.md",
            f".chain/{output_basename}",
        }
    )


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


# ── Revision-family lock (sandbox-git-versioning-v2, Requirement 10) ─────────
#
# One cross-process lock per revision family, keyed by (user_id, revision_root_id).
# It serializes every operation that mutates a shared revision sandbox:
#
#   - revision admission        (run_commands.py _mint_revision_row)
#   - shared-root sandbox open  (engine _execute_impl)
#   - dirty-tree recovery       (finalize_terminal_run step 1)
#   - file uploads              (run_files.py upload_files — Requirement 10 AC 9)
#   - restore                   (POST /api/runs/{id}/restore — task 8.1)
#   - terminal finalization     (finalize_terminal_run)
#
# **Lock file location.**  The lock file lives at
#   <RUNS_ROOT>/<user_seg>/<revision_root_seg>/.family.lock
# inside the revision-root directory so it is cleaned up automatically by TTL
# sweeping of the sandbox.  The parent directory is created on demand (the lock
# acquisition ensures the directory exists before opening the file descriptor).
#
# **Cross-platform exclusive locking.**
# - Linux / macOS: ``fcntl.flock(fd, LOCK_EX | LOCK_NB)`` → EWOULDBLOCK when busy.
# - Windows:       ``msvcrt.locking(fd, LK_NBLCK, 1)`` → OSError when busy.
# On both platforms the primitive is non-blocking and we poll at
# ``_FAMILY_LOCK_POLL_S`` (50 ms) intervals until the caller-supplied or default
# timeout expires, then raise ``FamilyLockTimeout``.
#
# **Lock order (documented single order, never reversed):**
#   family lock  →  per-sandbox manifest lock (run_files.py _manifest_lock)
# No path may acquire the manifest lock first and then block on the family lock.
#
# **Timeout.**  Every acquisition path MUST go through ``family_lock``; no call
# site may pass ``timeout_s=None`` in production paths because that would allow
# unbounded blocking.  The default is ``settings.FAMILY_LOCK_TIMEOUT_S`` (120 s).


class FamilyLockTimeout(TimeoutError):
    """Raised when the family lock could not be acquired within the timeout.

    Callers should surface this as a generic retryable refusal to the client,
    consistent with the Requirement 10 AC 10 upload-admission table row
    "terminal finalization holds the lock → rejected with a generic retryable
    reason".  The lock key (user_id, revision_root_id) must NOT be included in
    any client-visible message to avoid enumerating internal path structure.
    """

    def __init__(self, user_seg: str, root_seg: str, timeout_s: float) -> None:
        super().__init__(
            f"family lock not acquired within {timeout_s:.1f}s "
            f"(key={user_seg!r}/{root_seg!r})"
        )
        self.timeout_s = timeout_s


def _family_lock_path(
    user_seg: str, root_seg: str, runs_root: str | None = None
) -> Path:
    """Return the absolute path of the family lock file for ``(user_seg, root_seg)``.

    The lock file is created inside the revision-root directory so it is
    cleaned up automatically when the sandbox is swept by the TTL sweeper.
    ``runs_root`` defaults to ``settings.RUNS_ROOT`` when omitted.
    """
    base = Path(runs_root or settings.RUNS_ROOT).resolve()
    return base / user_seg / root_seg / ".family.lock"


def _try_acquire_fd(fd: int) -> bool:
    """Attempt a non-blocking exclusive lock on *fd*.

    Returns ``True`` on success, ``False`` when the lock is held by another
    process.  Never raises except on an unexpected OS error.
    """
    if _fcntl is not None:
        # Linux / macOS: flock with LOCK_EX | LOCK_NB
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    else:
        # Windows: msvcrt.locking(fd, LK_NBLCK, nbytes)
        # We lock exactly 1 byte at position 0.  Reset file-pointer to 0 first
        # (required by msvcrt.locking) and restore it afterwards so the fd stays
        # at the beginning for the unlock.
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)  # type: ignore[union-attr]
            return True
        except OSError:
            return False


def _release_fd(fd: int) -> None:
    """Release the exclusive lock held on *fd*.  Best-effort; never raises."""
    try:
        if _fcntl is not None:
            _fcntl.flock(fd, _fcntl.LOCK_UN)
        else:
            os.lseek(fd, 0, os.SEEK_SET)
            _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)  # type: ignore[union-attr]
    except OSError:
        pass  # unlock is best-effort — the fd will be closed immediately after


@contextlib.contextmanager
def family_lock(
    user_id: str,
    revision_root_id: str,
    *,
    timeout_s: float | None = None,
    runs_root: str | None = None,
):
    """Cross-process exclusive lock for one revision family.

    Keyed by ``(user_id, revision_root_id)``.  The lock serializes every
    operation that mutates the shared revision sandbox directory.

    **Lock order** — ALWAYS acquire the family lock **before** the per-sandbox
    manifest lock (``run_files._manifest_lock``).  Acquiring in the reverse
    order risks deadlock.

    Parameters
    ----------
    user_id:
        The run owner's id (the same value passed to ``RunSandbox``).
    revision_root_id:
        The revision-root run id (the *physical sandbox* id, i.e. the result
        of ``resolve_revision_root``).
    timeout_s:
        Maximum seconds to wait for the lock.  Defaults to
        ``settings.FAMILY_LOCK_TIMEOUT_S`` (120 s).  Passing ``0`` means
        one non-blocking attempt only.  The ceiling is explicit and
        non-negotiable — ``FamilyLockTimeout`` is raised on expiry, never
        silently proceeding unlocked.
    runs_root:
        Override the sandbox root.  Defaults to ``settings.RUNS_ROOT``.
        Exposed for testing only; production code omits this argument.

    Raises
    ------
    FamilyLockTimeout
        When the lock cannot be acquired within *timeout_s* seconds.
    OSError
        On an unexpected filesystem error (e.g. the lock directory is
        unreadable or the filesystem does not support locking primitives).
    """
    if timeout_s is None:
        timeout_s = float(settings.FAMILY_LOCK_TIMEOUT_S)

    user_seg = _safe_segment(user_id, fallback="anonymous")
    root_seg = _safe_segment(revision_root_id, fallback="root")
    lock_path = _family_lock_path(user_seg, root_seg, runs_root)

    # Ensure the parent directory (the revision-root sandbox dir) exists before
    # we try to create the lock file inside it.  mode=0o700 matches RunSandbox.ensure().
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + timeout_s
        acquired = False
        while True:
            if _try_acquire_fd(fd):
                acquired = True
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(_FAMILY_LOCK_POLL_S, remaining))

        if not acquired:
            raise FamilyLockTimeout(user_seg, root_seg, timeout_s)

        logger.debug("family_lock acquired key=%s/%s", user_seg, root_seg)
        try:
            yield
        finally:
            _release_fd(fd)
            logger.debug("family_lock released key=%s/%s", user_seg, root_seg)
    finally:
        os.close(fd)


class RunSandbox:
    """An isolated on-disk workspace for one pipeline run — a thin ``Workspace`` facade.

    ``root`` = ``<RUNS_ROOT>/<user>/<run>/``. Create it with :meth:`ensure`,
    resolve paths inside it with :meth:`path_for` (rejects escapes), remove it
    with :meth:`cleanup`.

    D-02 refold (RUNTIME-02, move-don't-copy): the consumed surface
    (``__init__(user_id, run_id)`` / ``ensure`` / ``root`` / ``path_for`` / ``read``
    / ``write`` / ``cleanup``) survives BYTE-FOR-BYTE so every call site is
    untouched, but the bespoke per-run disk read/write/cleanup logic is DELEGATED
    to a ``Workspace(has_git=True, exec=off)`` provisioned by the
    ``LocalSandboxRuntime`` (09-01). One ``Workspace`` abstraction now serves both
    artifact (``has_git=True``, default) and repo workspaces
    — there is NO ``if repo:`` engine fork. ``RunSandbox`` keeps the traversal-proof
    disk PRIMITIVES (``root`` resolution + ``path_for``) because the ``Workspace``
    impl itself reuses them (``LocalWorkspace`` is constructed FROM this sandbox);
    the facade's ``read``/``write``/``cleanup`` route through that Workspace so the
    disk IO lives in ONE place.

    Task 4.1 (Requirement 11): ``has_git`` defaults ``True`` — every sandbox is a git
    repository and fan-out uses worktree isolation. Pass ``has_git=False`` only when
    ``git init`` has failed; the ``sub_sandbox`` isolation path remains intact as the
    fallback (dormant under the global default).
    """

    def __init__(
        self,
        user_id: str,
        sandbox_root_id: str,
        *,
        current_run_id: str | None = None,
        runs_root: str | None = None,
        has_git: bool = True,
    ) -> None:
        # Task 3.4 (sandbox-git-versioning-v2, Requirement 3): split physical
        # sandbox identity from logical run identity (V2-Q4).
        #
        # ``sandbox_root_id`` names the ON-DISK DIRECTORY.  Every revision in a
        # family shares the same physical sandbox, so they all pass the same root id
        # here — the directory never changes.
        #
        # ``current_run_id`` is the LOGICAL RUN being executed.  It drives the
        # per-run paths (.logs/, .verify/, .browser/) so each revision keeps its
        # own unambiguous trace.  Defaults to ``sandbox_root_id`` so a root-only
        # (non-revision) run is byte-identical to the old single-id behavior —
        # INV-3 (characterization goldens) is preserved.
        _current_run_id = (
            current_run_id if current_run_id is not None else sandbox_root_id
        )

        self.user_seg = _safe_segment(user_id, fallback="anonymous")
        self.run_seg = _safe_segment(sandbox_root_id, fallback="run")

        # ``self.run_id`` is a backward-compat alias for the CURRENT (logical) run id.
        # Callers that do ``sandbox.run_id`` to pass to AgentContext, RunTrace, etc.
        # get the current run id, not the sandbox root id.  This is the same value
        # that was always stored as ``run_id`` before the split — the difference only
        # arises when ``current_run_id != sandbox_root_id`` (i.e. a revision run).
        self.run_id: str = _current_run_id

        # Store both ids for callers that need to distinguish them (e.g. the engine
        # building RunTrace vs. choosing the sandbox directory).
        self.sandbox_root_id: str = sandbox_root_id
        self.current_run_id: str = _current_run_id

        self.user_id = user_id
        base = Path(runs_root or settings.RUNS_ROOT).resolve()
        self.base = base
        # Physical directory is keyed on ``sandbox_root_id`` — all revisions in a
        # family share it (V2-Q1 / Requirement 2 AC 1).
        self.root = (base / self.user_seg / self.run_seg).resolve()
        # Defence in depth: the resolved run dir must stay under RUNS_ROOT even if
        # the sanitiser is ever weakened. ``is_relative_to`` is separator-aware, so
        # containment holds on both POSIX ("/") and Windows ("\\") — a plain
        # ``startswith(base + "/")`` string check falsely rejects every path on
        # Windows.
        if not self.root.is_relative_to(base):
            raise ValueError(f"sandbox root escaped RUNS_ROOT: {self.root}")
        # Task 4.1 (Requirement 11): has_git defaults True so every sandbox is a
        # git repo and fan-out uses worktree isolation. When git init fails the
        # caller may re-construct with has_git=False to fall back to sub_sandbox
        # isolation — that path stays intact, just dormant under the default.
        self.has_git: bool = has_git
        # The delegated Workspace facade (lazily built so the disk root exists first
        # and to avoid the local.py import cycle). has_git is threaded in on build.
        self._workspace: object | None = None

    def _ws(self) -> object:
        """The Workspace this sandbox delegates disk IO to.

        Built lazily (and cached) from THIS sandbox so the single ``LocalWorkspace``
        disk impl (09-01) owns read/write — move-don't-copy. The import is local to
        sidestep the ``local.py`` → ``sandbox.py`` import cycle. ``has_git`` is
        threaded from the sandbox so the workspace's fan-out isolation scope
        (worktree vs sub_sandbox) reflects the sandbox's git state.
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
                has_git=self.has_git,
            )
        return self._workspace

    # ── Per-run path helpers (Requirement 24) ────────────────────────────────
    # All writers for run logs, validator evidence, and browser artifacts MUST
    # derive their paths from these properties so every shared-sandbox revision
    # writes into its own sub-directory and never clobbers another run's data.

    @property
    def run_log_path(self) -> Path:
        """Absolute path of this run's JSONL trace file: ``.logs/{current_run_id}.jsonl``.

        Derives from ``current_run_id`` (the logical run), NOT from
        ``sandbox_root_id`` (the directory key). Multiple revisions sharing a
        physical sandbox each produce a distinct path — fixes D2 (Requirement 3
        AC 3, V2-Q4). When ``current_run_id == sandbox_root_id`` (a root run
        with no explicit revision id) the path is identical to the old behavior,
        preserving INV-3.
        """
        return self.root / ".logs" / f"{self.current_run_id}.jsonl"

    @property
    def verify_dir(self) -> Path:
        """Absolute path of this run's validator evidence directory: ``.verify/{current_run_id}/``.

        Derives from ``current_run_id`` so each revision in a shared sandbox
        keeps its own evidence directory (Requirement 3 AC 4, V2-Q4).
        """
        return self.root / ".verify" / self.current_run_id

    @property
    def browser_dir(self) -> Path:
        """Absolute path of this run's browser artifacts directory: ``.browser/{current_run_id}/``.

        Derives from ``current_run_id`` so each revision in a shared sandbox
        keeps its own browser artifacts (Requirement 3 AC 4, V2-Q4).
        """
        return self.root / ".browser" / self.current_run_id

    def ensure(self) -> Path:
        """Create the run dir (parents, mode 0700) and return it."""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass  # best-effort on filesystems that don't honour chmod
        self._repoint_latest()
        logger.debug("ensure %s", self.root)
        return self.root

    def _repoint_latest(self) -> None:
        """Keep ``<base>/<user>/.latest`` pointing at the most recent run dir.

        TODO: Remove — temporary local-dev hack, same category as
        ``_seed_from_prior_run`` in app/api/run_commands.py (seed a prior run's
        files into a new sandbox). Both exist only so local iteration is cheap.

        Run ids are fresh uuid4s, so every launch lands in a directory nobody can
        predict — this gives one stable path to reach the newest one instead.
        Staging sandboxes are excluded: they are transient upload holding pens
        that are deleted at ingest, never runs. Purely a convenience link, so
        every failure here is swallowed — it must never break a run.
        """
        if self.run_seg.startswith("staged-"):
            return
        # Dot-prefixed so it sorts to the TOP of a listing — a plain "latest"
        # sorts after every uuid-named run dir and is missed at the bottom.
        link = self.root.parent / ".latest"
        if link.resolve(strict=False) == self.root:
            return
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(self.root.name)  # relative: survives moving RUNS_ROOT
        except OSError:
            pass

    def path_for(self, relpath: str) -> Path:
        """Resolve ``relpath`` inside the sandbox, rejecting any escape."""
        candidate = (self.root / str(relpath).lstrip("/")).resolve()
        # Separator-aware containment (see __init__): correct on Windows and POSIX.
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"path escapes run sandbox: {relpath!r}")
        return candidate

    def write(self, relpath: str, content: str) -> Path:
        # Delegate to the Workspace (LocalWorkspace.write_file) — the single
        # disk-write impl. It mkdir(parents)s + writes UTF-8 under the
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

        The reserved subtrees ``.uploads/`` and ``.logs/`` are excluded on the
        same grounds they are excluded from the deliverable: ``.uploads/`` is the
        owner's own upload staging (already listed by its manifest) and ``.logs/``
        is the engine-owned run trace, surfaced through the audit view rather than
        as workspace files.

        ``.agents/`` (agent transcripts), ``.chain/`` (engine chain payload), and
        ``.context/`` (what the run was given — design material and selections) are
        listed here but excluded from the deliverable walk — they appear in the
        Workspace tab but never in the deliverable zip or ``WorkflowRun.output``.

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
                # Derive exclusions from the canonical registry (V2-Q7, Requirement 18
                # AC 2). Uses pre-computed module-level sets from RESERVED_PATHS and
                # GIT_METADATA_PATHS. .chain/, .context/, and .agents/ are DELIBERATELY
                # VISIBLE in the Workspace listing (Requirement 4 AC 10, Requirement 8
                # AC 7). All other reserved paths and git metadata are excluded.
                if relpath.startswith(_LISTING_EXCLUDED_PREFIXES):
                    continue
                if relpath in _LISTING_EXCLUDED_EXACT:
                    continue
                if len(files) >= _LIST_MAX_FILES:
                    return sorted(files, key=lambda f: f["path"]), True
                try:
                    st = full.stat()
                except OSError:
                    continue
                files.append(
                    {"path": relpath, "size": st.st_size, "modified": st.st_mtime}
                )
        return sorted(files, key=lambda f: f["path"]), truncated

    def is_dirty(self) -> bool:
        """Return ``True`` when the sandbox working tree has uncommitted changes.

        Delegates to ``LocalWorkspace.is_dirty`` via duck-typing — the same getattr
        pattern as ``commit_all``.  When ``has_git=False`` the sandbox has no git
        repo, so the tree is always "clean" from the caller's perspective — returns
        ``False`` immediately.

        Never raises: the underlying ``LocalWorkspace.is_dirty`` is best-effort
        (git errors → ``False``), and an absent ``LocalWorkspace`` (no ``_ws``) also
        returns ``False``.  Callers use this to guard a ``commit_all`` call and must
        not assume a ``True`` result means the subsequent commit will produce output
        (the window between the probe and the commit may allow another committer, but
        this is only the engine calling it so the window is effectively zero).

        Used by the wip-commit paths (Requirement 26 AC 1, Requirement 27 AC 1).
        """
        if not self.has_git:
            return False
        try:
            return self._ws().is_dirty()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — best-effort probe
            return False

    def commit_all(
        self,
        message: str,
        *,
        paths: list[str] | None = None,
        force_add: frozenset[str] | None = None,
    ) -> str:
        """Stage and commit all working-tree changes, gated on ``has_git``.

        Delegates to ``LocalWorkspace.commit_all`` — the single disk-commit impl.
        Returns the commit SHA string on success, or ``""`` when there is nothing
        to commit or when ``has_git=False``.

        ``paths`` and ``force_add`` are forwarded to ``LocalWorkspace.commit_all``
        (Requirement 4 AC 11 / Requirement 18 AC 5):
        - ``paths``: when given, stages only those specific paths instead of ``-A``.
        - ``force_add``: exactly the three-path frozenset from ``payload_allowlist``;
          each entry is force-staged before the main staging pass.

        ``has_git=False`` path: returns ``""`` immediately — no git repo, nothing
        to commit, no warning. Callers that check the return value receive the
        same sentinel as a no-change commit on a real repo, which is correct.

        ``has_git=True`` path with no-change result: distinguishes two cases that
        are indistinguishable at the call site (Requirement 10 AC 5):

        - ``.git/`` is absent: the sandbox is not a git repository even though
          ``has_git`` is True.  This indicates a provisioning failure — the caller
          and the ops team need to see it.
        - ``.git/`` is present: the commit ran but found nothing to stage.  This is
          unusual at a step boundary (every step should write at least one file) and
          warrants a warning, but is less alarming than a missing repo.

        Both cases emit a ``logger.warning`` so the distinction surfaces in
        structured logs and the ops team can tell them apart.

        A real Git failure raises ``GitCommandError`` (from ``LocalWorkspace``) and
        is never swallowed — Requirement 10 AC 7.
        """
        if not self.has_git:
            return ""

        result = self._ws().commit_all(message, paths=paths, force_add=force_add)  # type: ignore[attr-defined]

        if result.no_change:
            # Distinguish "not a git repo" from "nothing to commit" (Req 10 AC 5).
            if not (self.root / ".git").is_dir():
                logger.warning(
                    "commit_all: sandbox is not a git repo (has_git=True) "
                    "run=%s/%s message=%r",
                    self.user_seg,
                    self.run_seg,
                    message,
                )
            else:
                logger.warning(
                    "commit_all: nothing to commit (empty diff at step boundary) "
                    "run=%s/%s message=%r",
                    self.user_seg,
                    self.run_seg,
                    message,
                )
            return ""

        return result.sha

    def git_gc_auto(self) -> None:
        """Run ``git gc --auto`` — fire-and-forget, gated on ``has_git`` (Req 35).

        Delegates to ``LocalWorkspace.git_gc_auto``.  When ``has_git=False`` the
        sandbox has no git repo, so the call is a silent no-op (matching the
        ``commit_all`` gating pattern).  Never raises.
        """
        if not self.has_git:
            return
        self._ws().git_gc_auto()  # type: ignore[attr-defined]

    def create_tag(self, name: str) -> str:
        """Create a git tag named ``name`` on HEAD (Requirement 15).

        Delegates to ``LocalWorkspace.create_tag`` via ``getattr`` duck-typing —
        the same pattern as ``commit_all`` and ``allocate_worktree``.  NOT added
        to the Workspace Protocol (three import-linter contracts hold that port
        shut for the ECS swap).

        Raises when ``has_git=False`` — there is no git repo to tag.  Raises on
        any git failure (duplicate tag, no commits yet, etc.) — a tag creation
        failure must be visible, never swallowed (Requirement 15).

        Returns the tag name on success.
        """
        if not self.has_git:
            raise RuntimeError(
                f"create_tag called on a non-git sandbox (has_git=False) for tag={name!r}"
            )
        fn = getattr(self._ws(), "create_tag", None)
        if fn is None:
            raise AttributeError("create_tag not available on the underlying workspace")
        return fn(name)  # type: ignore[no-any-return]

    def list_tags(self) -> list[str]:
        """List all git tags in the sandbox (Requirement 15).

        Delegates to ``LocalWorkspace.list_tags`` via ``getattr`` duck-typing.
        NOT added to the Workspace Protocol.

        Returns a sorted list of tag name strings.  Returns ``[]`` when
        ``has_git=False`` or when the underlying workspace does not support tag
        listing (best-effort, non-raising — callers such as the ref-validation
        gate receive an empty allow-list and correctly reject every ref).
        """
        if not self.has_git:
            return []
        fn = getattr(self._ws(), "list_tags", None)
        if fn is None:
            return []
        try:
            return fn()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def create_run_ref(self, run_id: str) -> "RefResult":
        """Create the internal run ref ``refs/ideaflow/runs/{run_id}`` on HEAD.

        Delegates to ``LocalWorkspace.create_run_ref`` via ``getattr`` duck-typing —
        same pattern as ``create_tag`` / ``list_tags``.  NOT added to the
        ``Workspace`` Protocol.

        Implements create-only compare-and-set semantics (V2-Q3 / Requirement 5
        AC 3 step 7):
        - Absent  → create and return ``state="created"``.
        - Present, same commit → return ``state="idempotent"`` (no write).
        - Present, different commit → return ``state="conflict"`` (no move).

        Raises ``RuntimeError`` when ``has_git=False``.  Raises ``ValueError``
        on an invalid ``run_id``.  Raises on unexpected git failure.
        """
        if not self.has_git:
            raise RuntimeError(
                f"create_run_ref called on a non-git sandbox (has_git=False) "
                f"for run_id={run_id!r}"
            )
        fn = getattr(self._ws(), "create_run_ref", None)
        if fn is None:
            raise AttributeError(
                "create_run_ref not available on the underlying workspace"
            )
        return fn(run_id)  # type: ignore[no-any-return]

    def advance_run_ref(
        self, run_id: str, *, expected_sha: str, new_sha: str
    ) -> "RefResult":
        """Move the internal run ref from ``expected_sha`` to ``new_sha`` (CAS).

        Delegates to ``LocalWorkspace.advance_run_ref`` via ``getattr``
        duck-typing — same pattern as ``create_run_ref``.  NOT added to the
        ``Workspace`` Protocol.

        Reserved for the finalizer's legitimate-resume path (Requirement 5 AC
        23/24): a run that already finalized as a resumable status
        (cancelled/failed/degraded) and was later resumed to a different
        terminal outcome.  Raises ``RuntimeError`` when ``has_git=False``.
        Raises ``ValueError`` on an invalid ``run_id``.  Raises on a failed
        CAS (the ref no longer points at ``expected_sha``).
        """
        if not self.has_git:
            raise RuntimeError(
                f"advance_run_ref called on a non-git sandbox (has_git=False) "
                f"for run_id={run_id!r}"
            )
        fn = getattr(self._ws(), "advance_run_ref", None)
        if fn is None:
            raise AttributeError(
                "advance_run_ref not available on the underlying workspace"
            )
        return fn(run_id, expected_sha=expected_sha, new_sha=new_sha)  # type: ignore[no-any-return]

    def resolve_ref_commit(self, run_id: str) -> str | None:
        """Return the commit SHA that ``refs/ideaflow/runs/{run_id}`` points to.

        Delegates to ``LocalWorkspace.resolve_ref_commit`` via ``getattr``
        duck-typing.  NOT added to the ``Workspace`` Protocol.

        Returns ``None`` when the ref does not exist or when ``has_git=False``.
        Raises ``ValueError`` on an invalid ``run_id``.
        """
        if not self.has_git:
            return None
        fn = getattr(self._ws(), "resolve_ref_commit", None)
        if fn is None:
            return None
        return fn(run_id)  # type: ignore[no-any-return]

    def has_internal_run_ref(self, run_id: str) -> bool:
        """Return ``True`` if ``refs/ideaflow/runs/{run_id}`` exists.

        Delegates to ``LocalWorkspace.has_internal_run_ref`` via ``getattr``
        duck-typing.  NOT added to the ``Workspace`` Protocol.

        Returns ``False`` when ``has_git=False`` or when the underlying workspace
        does not support the method.  Raises ``ValueError`` on an invalid ``run_id``.
        """
        if not self.has_git:
            return False
        fn = getattr(self._ws(), "has_internal_run_ref", None)
        if fn is None:
            return False
        return fn(run_id)  # type: ignore[no-any-return]

    def git_init_sandbox(self) -> None:
        """Initialise the sandbox as a git repository with an initial commit.

        Delegates to ``LocalWorkspace.git_init_sandbox`` — idempotent: if
        ``.git/`` already exists the call is a no-op (Requirement 6 AC 1).
        Called once per run by the engine immediately after ``sandbox.ensure()``
        (Requirement 6 / task 4.1 wiring in ``engine.py``).

        When ``has_git=False`` the sandbox is intentionally non-git — skip
        silently (same gating pattern as ``commit_all``).  Never raises:
        a git-init failure is logged as a warning and the run continues
        (best-effort, matching the engine's own error-handling wrapper).
        """
        if not self.has_git:
            return
        fn = getattr(self._ws(), "git_init_sandbox", None)
        if fn is None:
            logger.warning(
                "git_init_sandbox: underlying workspace does not support git init "
                "(run=%s/%s) — commits will fail",
                self.user_seg,
                self.run_seg,
            )
            return
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — best-effort, must never raise
            logger.warning(
                "git_init_sandbox failed run=%s/%s: %s — continuing without git",
                self.user_seg,
                self.run_seg,
                exc,
            )
            # Reflect reality (Task 3.6, sandbox-git-versioning-v2, Requirement 3).
            # The engine's own fallback flips has_git only when this call RAISES,
            # which it never does — so without this the sandbox kept claiming
            # has_git=True over a failed init, and the finalizer degraded every
            # otherwise-clean run on ref/tag creation instead of taking the no-git
            # path the has_git=False branches exist for.
            self.has_git = False

    def list_files_at_ref(self, ref: str) -> list[str]:
        """Return the list of file relpaths tracked at ``ref`` (Requirement 17 AC2).

        Delegates to ``LocalWorkspace.list_files_at_ref`` via duck-typing.
        ``ref`` must be pre-validated by the caller (Requirement 16).
        Returns ``[]`` when not available or any error occurs.
        """
        fn = getattr(self._ws(), "list_files_at_ref", None)
        if fn is None:
            return []
        try:
            return fn(ref)  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, non-raising
            return []

    def file_sizes_at_ref(self, ref: str) -> dict[str, int]:
        """Return ``{relpath: byte size}`` for the blobs tracked at ``ref``.

        Sibling of ``list_files_at_ref`` — that one is pinned to ``list[str]`` by
        its callers, so sizes arrive alongside it rather than widening it.

        Delegates to ``LocalWorkspace.file_sizes_at_ref`` via duck-typing.
        ``ref`` must be pre-validated by the caller (Requirement 16).
        Returns ``{}`` when not available or any error occurs.
        """
        fn = getattr(self._ws(), "file_sizes_at_ref", None)
        if fn is None:
            return {}
        try:
            return fn(ref)  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, non-raising
            return {}

    def read_file_at_ref(self, ref: str, relpath: str) -> bytes:
        """Return raw bytes of ``relpath`` at ``ref`` (Requirement 17 AC2).

        Delegates to ``LocalWorkspace.read_file_at_ref`` via duck-typing.
        ``ref`` must be pre-validated by the caller (Requirement 16).
        Raises ``AttributeError`` when not available, or ``CalledProcessError``
        from the underlying git call.
        """
        fn = getattr(self._ws(), "read_file_at_ref", None)
        if fn is None:
            raise AttributeError(
                "read_file_at_ref not available on the underlying workspace"
            )
        return fn(ref, relpath)  # type: ignore[no-any-return]

    def archive_at_ref(self, ref: str) -> bytes:
        """Build an in-memory zip of the sandbox at ``ref`` (Requirement 17 AC2).

        Delegates to ``LocalWorkspace.archive_at_ref`` via duck-typing.
        ``ref`` must be pre-validated by the caller (Requirement 16).
        Raises ``AttributeError`` when not available, or ``CalledProcessError``
        from the underlying git call.
        """
        fn = getattr(self._ws(), "archive_at_ref", None)
        if fn is None:
            raise AttributeError(
                "archive_at_ref not available on the underlying workspace"
            )
        return fn(ref)  # type: ignore[no-any-return]

    def audit_log(self, event: str, detail: dict) -> None:
        """Trace-only structured audit line (mirrors the reference tracer)."""
        logger.debug("audit_log %s %s", event, detail)

    # ── Byte and index helper delegations (task 5.6 / Requirement 4, 6, 10) ─
    # Pattern mirrors create_tag / list_tags: delegate via getattr duck-typing to
    # LocalWorkspace — NOT on the Workspace Protocol.

    def read_bytes(self, relpath: str) -> bytes:
        """Read raw bytes from a file in the sandbox.

        Delegates to ``LocalWorkspace.read_bytes`` via duck-typing.
        Raises ``FileNotFoundError`` if the file is absent.
        Raises ``AttributeError`` when the underlying workspace does not support it.
        """
        fn = getattr(self._ws(), "read_bytes", None)
        if fn is None:
            raise AttributeError("read_bytes not available on the underlying workspace")
        return fn(relpath)  # type: ignore[no-any-return]

    def read_bytes_at_ref(self, ref: str, relpath: str) -> bytes:
        """Return raw bytes of ``relpath`` at ``ref``.

        Delegates to ``LocalWorkspace.read_file_at_ref`` via duck-typing.
        ``ref`` must be pre-validated by the caller (Requirement 16).
        Raises ``AttributeError`` when not available.
        """
        fn = getattr(self._ws(), "read_file_at_ref", None)
        if fn is None:
            raise AttributeError(
                "read_file_at_ref not available on the underlying workspace"
            )
        return fn(ref, relpath)  # type: ignore[no-any-return]

    def list_prefix(self, prefix: str) -> list[str]:
        """List all tracked paths that start with ``prefix`` (live working tree).

        Delegates to ``LocalWorkspace.list_prefix`` via duck-typing.
        Best-effort: returns ``[]`` when not available or on any error.
        """
        if not self.has_git:
            return []
        fn = getattr(self._ws(), "list_prefix", None)
        if fn is None:
            return []
        try:
            return fn(prefix)  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def staged_entries(self) -> list[str]:
        """Return the list of relpaths currently staged in the index.

        Delegates to ``LocalWorkspace.staged_entries`` via duck-typing.
        Best-effort: returns ``[]`` when not available or on any error.
        """
        if not self.has_git:
            return []
        fn = getattr(self._ws(), "staged_entries", None)
        if fn is None:
            return []
        try:
            return fn()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def stage_exact(self, paths: list[str]) -> None:
        """Stage exactly the listed paths with ``git add --force -- <paths>``.

        Delegates to ``LocalWorkspace.stage_exact`` via duck-typing.
        Raises when ``has_git=False`` or when the underlying workspace does not
        support it.  A staging failure must be visible.
        """
        if not self.has_git:
            raise RuntimeError(
                f"stage_exact called on a non-git sandbox (has_git=False) run={self.run_id!r}"
            )
        fn = getattr(self._ws(), "stage_exact", None)
        if fn is None:
            raise AttributeError(
                "stage_exact not available on the underlying workspace"
            )
        fn(paths)

    def head_commit(self) -> str:
        """Return the current HEAD commit SHA.

        Delegates to ``LocalWorkspace.head_commit`` via duck-typing.
        Returns ``""`` when ``has_git=False``, no commits yet, or on any error.
        """
        if not self.has_git:
            return ""
        fn = getattr(self._ws(), "head_commit", None)
        if fn is None:
            return ""
        try:
            return fn()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort
            return ""

    def reset_index(self) -> None:
        """Reset the index back to HEAD without touching the working tree.

        Delegates to ``LocalWorkspace.reset_index`` via duck-typing.
        Raises when ``has_git=False`` or when the underlying workspace does not
        support it.
        """
        if not self.has_git:
            raise RuntimeError(
                f"reset_index called on a non-git sandbox (has_git=False) run={self.run_id!r}"
            )
        fn = getattr(self._ws(), "reset_index", None)
        if fn is None:
            raise AttributeError(
                "reset_index not available on the underlying workspace"
            )
        fn()

    def git_rm_cached(self, relpath: str) -> None:
        """Remove a file from the index only (not the working tree).

        Delegates to ``LocalWorkspace.git_rm_cached`` via duck-typing.
        Best-effort: no-op when ``has_git=False``, not available, or not tracked.
        """
        if not self.has_git:
            return
        fn = getattr(self._ws(), "git_rm_cached", None)
        if fn is None:
            return
        try:
            fn(relpath)
        except Exception:  # noqa: BLE001 — best-effort, no-op if not tracked
            pass

    def tracked_chain_paths(self) -> list[str]:
        """List all tracked paths under ``.chain/``.

        Delegates to ``LocalWorkspace.tracked_chain_paths`` via duck-typing.
        Returns ``[]`` when ``has_git=False`` or on any error.
        """
        if not self.has_git:
            return []
        fn = getattr(self._ws(), "tracked_chain_paths", None)
        if fn is None:
            return []
        try:
            return fn()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return []

    def atomic_replace_dir(self, src: Path, dst: Path) -> None:
        """Atomically replace ``dst`` with ``src`` on both POSIX and Windows.

        Delegates to ``LocalWorkspace.atomic_replace_dir`` via duck-typing.
        Raises ``AttributeError`` when not available; propagates any OS error.
        """
        fn = getattr(self._ws(), "atomic_replace_dir", None)
        if fn is None:
            raise AttributeError(
                "atomic_replace_dir not available on the underlying workspace"
            )
        fn(src, dst)

    def atomic_context_install(self, src: Path) -> None:
        """Atomically install ``src`` directory as ``.context/`` in this sandbox.

        Delegates to ``LocalWorkspace.atomic_context_install`` via duck-typing.
        Raises ``AttributeError`` when not available; propagates any OS error.
        """
        fn = getattr(self._ws(), "atomic_context_install", None)
        if fn is None:
            raise AttributeError(
                "atomic_context_install not available on the underlying workspace"
            )
        fn(src)

    def detect_persistent_git_state(self) -> dict:
        """Detect leftover git state files from a prior crash.

        Delegates to ``LocalWorkspace.detect_persistent_git_state`` via
        ``getattr`` duck-typing — same pattern as ``create_tag`` / ``list_tags``.
        NOT added to the ``Workspace`` Protocol.

        Returns ``{"state": "clean", "file": None, "sha": None}`` when
        ``has_git=False``, when the underlying workspace does not support the
        method, or when no persistent state is found.  Never raises.
        """
        if not self.has_git:
            return {"state": "clean", "file": None, "sha": None}
        fn = getattr(self._ws(), "detect_persistent_git_state", None)
        if fn is None:
            return {"state": "clean", "file": None, "sha": None}
        try:
            return fn()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return {"state": "clean", "file": None, "sha": None}

    def reconcile_persistent_git_state(self, state: dict) -> str:
        """Reconcile leftover git state from a prior crash.

        Delegates to ``LocalWorkspace.reconcile_persistent_git_state`` via
        ``getattr`` duck-typing — same pattern as ``create_tag`` / ``list_tags``.
        NOT added to the ``Workspace`` Protocol.

        Returns ``"already_clean"`` when ``has_git=False`` or when the underlying
        workspace does not support the method.  Returns ``"reconcile_failed"`` on
        any error.  Never raises.
        """
        if not self.has_git:
            return "already_clean"
        fn = getattr(self._ws(), "reconcile_persistent_git_state", None)
        if fn is None:
            return "already_clean"
        try:
            return fn(state)  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001 — best-effort, must never raise
            return "reconcile_failed"

    def materialize_tree_at_ref(self, ref: str) -> "object":
        """Materialize the tracked tree at ``ref`` into the working directory.

        Delegates to ``LocalWorkspace.materialize_tree_at_ref`` via ``getattr``
        duck-typing — same pattern as ``create_tag`` / ``list_tags``.
        NOT added to the ``Workspace`` Protocol.

        ``ref`` MUST be pre-validated by the caller (e.g. confirmed to be a
        known tag via ``list_tags()`` before being passed here) — a free-form
        revspec must NEVER reach a git subprocess without prior validation
        (Requirement 9 AC 2 / task 8.1 gating contract).

        Returns a :class:`~app.agents.runtime.local.MaterializeResult` on success.

        Raises:
            AttributeError: when the underlying workspace does not support the
                method (task 8.3 not yet landed).
            GitCommandError: propagated from ``LocalWorkspace.materialize_tree_at_ref``
                on any git subprocess failure — never swallowed here.
        """
        from app.agents.runtime.local import MaterializeResult as _MR  # noqa: PLC0415

        if not self.has_git:
            # No git repo — treat as no-change (the working tree already matches
            # itself, there is nothing to restore).
            return _MR(status="no_change", commit_sha="")
        fn = getattr(self._ws(), "materialize_tree_at_ref", None)
        if fn is None:
            raise AttributeError(
                "materialize_tree_at_ref is not available on the underlying workspace "
                "(task 8.3 not yet implemented)"
            )
        # Propagate GitCommandError — the caller (restore_version) must NOT
        # proceed to commit when the working-tree state is uncertain.
        return fn(ref)  # type: ignore[no-any-return]

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
    ttl_seconds = (
        ttl_hours if ttl_hours is not None else settings.RUN_DIR_TTL_HOURS
    ) * 3600
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
        logger.info(
            "sandbox sweep: removed %d expired run dir(s) under %s", removed, root
        )
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
    relpath: str,
    *,
    exclude: frozenset[str] | Iterable[str] = None,  # type: ignore[assignment]
) -> bool:
    """Is ``relpath`` part of what the run DELIVERED, as opposed to how it worked?

    The single definition of that question. ``_collect_deliverable_relpaths``
    applies it while walking, and the workspace API applies it per listed file
    so the UI can group Deliverables without re-deriving the rule — and without
    a copy of ``_DELIVERABLE_EXCLUDE`` in TypeScript that drifts from this one.

    Excluded are all RESERVED_PATHS (the canonical registry), GIT_METADATA_PATHS,
    and anything matching ``exclude`` by full relative path OR by basename.
    Every enforcement point derives from the same two frozensets — no independent
    literal lists (Requirement 18 AC 2, V2-Q7).
    """
    exclude_set = frozenset(_DELIVERABLE_EXCLUDE if exclude is None else exclude)
    # Use the module-level pre-computed sets derived from RESERVED_PATHS and
    # GIT_METADATA_PATHS (V2-Q7, Requirement 18 AC 2). No independent literal list.
    if relpath.startswith(_DELIVERABLE_EXCLUDED_PREFIXES):
        return False
    if relpath in _DELIVERABLE_EXCLUDED_EXACT:
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


# ---------------------------------------------------------------------------
# ReadOnlySandbox — read-only handle on another run's revision-root sandbox
# ---------------------------------------------------------------------------


class ReadOnlySandbox:
    """A read-only handle on another run's revision-root sandbox.

    Provides no write surface — no ``write``, no ``commit_all``, no ``ensure``,
    no ``cleanup``, no ``git_init_sandbox``.  Designed for cross-run reads such
    as the chain-context installer that needs to read a source run's payload
    without any risk of mutating it (Requirement 6, 10).

    The underlying ``RunSandbox`` is constructed with the caller-supplied ids and
    is never initialized: the physical directory must already exist on disk.  No
    ``ensure()`` is called.

    Exposed read surface:
        - ``root`` — the sandbox root ``Path``
        - ``read(relpath)`` — read a file as text (``str | None``)
        - ``read_bytes(relpath)`` — read a file as raw bytes
        - ``list_files()`` — list sandbox files
        - ``list_prefix(prefix)`` — list tracked paths under a prefix
        - ``read_file_at_ref(ref, relpath)`` / ``read_bytes_at_ref(ref, relpath)``
          — read a file at a specific git ref
        - ``list_files_at_ref(ref)`` — list tracked paths at a ref
        - ``list_tags()`` — list git tags
    """

    def __init__(
        self,
        user_id: str,
        sandbox_root_id: str,
        *,
        runs_root: str | None = None,
    ) -> None:
        # Build a RunSandbox purely for its path/read machinery.  We never call
        # ensure() on it, so it will not create the directory; it must already
        # exist (the caller is reading an existing source run's sandbox).
        self._inner = RunSandbox(
            user_id,
            sandbox_root_id,
            runs_root=runs_root,
        )

    @property
    def root(self) -> Path:
        """The sandbox root directory path."""
        return self._inner.root

    def read(self, relpath: str) -> str | None:
        """Read a file from the sandbox as text.

        Returns ``None`` if the file is absent or unreadable.
        """
        return self._inner.read(relpath)

    def read_bytes(self, relpath: str) -> bytes | None:
        """Read a file from the sandbox as raw bytes.

        Returns ``None`` if the file is absent or unreadable (unlike
        ``RunSandbox.read_bytes`` which raises ``FileNotFoundError``).
        """
        try:
            return self._inner.read_bytes(relpath)
        except (FileNotFoundError, AttributeError, OSError):
            return None

    def list_files(self) -> tuple[list[dict], bool]:
        """List files in the sandbox (mirrors ``RunSandbox.list_files``)."""
        return self._inner.list_files()

    def list_prefix(self, prefix: str) -> list[str]:
        """List all tracked paths starting with ``prefix`` (live working tree).

        Best-effort: returns ``[]`` on any error.
        """
        return self._inner.list_prefix(prefix)

    def read_file_at_ref(self, ref: str, relpath: str) -> bytes:
        """Return raw bytes of ``relpath`` at git ``ref``.

        ``ref`` must be pre-validated by the caller (Requirement 16).
        """
        return self._inner.read_file_at_ref(ref, relpath)

    def read_bytes_at_ref(self, ref: str, relpath: str) -> bytes:
        """Alias for ``read_file_at_ref`` — kept for naming symmetry with ``read_bytes``."""
        return self._inner.read_bytes_at_ref(ref, relpath)

    def list_files_at_ref(self, ref: str) -> list[str]:
        """Return the list of file relpaths tracked at ``ref``.

        ``ref`` must be pre-validated by the caller (Requirement 16).
        Best-effort: returns ``[]`` on any error.
        """
        return self._inner.list_files_at_ref(ref)

    def list_tags(self) -> list[str]:
        """List all git tags in the sandbox.

        Best-effort: returns ``[]`` on any error.
        """
        return self._inner.list_tags()

    def resolve_ref_commit(self, ref: str) -> str | None:
        """Return the commit SHA that ``ref`` resolves to, or ``None`` if absent.

        Accepts any valid git ref — a tag name (``v1``), a full internal ref
        (``refs/ideaflow/runs/{run_id}``), or any other refname present in the
        repository.  The ref must be pre-validated by the caller (Requirement 16):
        this method performs a pure rev-parse, not a ref-list membership check.

        Returns ``None`` when:
          - the sandbox has no git checkout (``has_git=False``)
          - the underlying workspace does not expose the low-level git runner
          - the ref does not exist in the repository

        Never raises (best-effort — callers such as ``KernelServices.resolved_or_refuse``
        treat ``None`` as a refusal, Requirement 6 AC 3).
        """
        if not self._inner.has_git:
            return None
        ws = self._inner._ws()  # type: ignore[attr-defined]  # duck-type, not Protocol
        git_fn = getattr(ws, "_git", None)
        if git_fn is None:
            return None
        import subprocess  # noqa: PLC0415

        try:
            sha = git_fn("rev-parse", ref).strip()
            return sha if sha else None
        except subprocess.CalledProcessError:
            return None
        except Exception:  # noqa: BLE001 — best-effort, must not raise
            return None


# ---------------------------------------------------------------------------
# Legacy chain payload — relocation and read path (task 6.7, Requirement 7)
# ---------------------------------------------------------------------------
#
# Pre-v2 runs stored their chain payload at ``.chain/{run_id}/`` (a nested
# directory layout).  V2 uses a flat ``.chain/`` with exactly three engine-owned
# files.  This block handles:
#
#   1.  ``LegacySelection`` — a typed description of a selected legacy payload.
#   2.  ``relocate_legacy_payloads(sandbox_root)`` — atomically migrates any
#       ``.chain/{run_id}/`` directories to ``.chain-legacy/{run_id}/``, so that
#       ``.chain/`` contains no directory entry after migration.  Called at
#       sandbox open before the first v2 flat payload is installed.
#   3.  ``_validate_ref_against_tags(tag, src)`` — exact-match guard for a
#       stored tag against the source sandbox's visible tag list.  Re-uses the
#       same contract as ``run_files._validate_ref``; putting it here avoids a
#       circular import and lets the legacy read path share it.
#   4.  ``select_legacy_payload(src, source_run_id, declared_output_basename)``
#       — locates the legacy payload for a given source run id, validates the
#       nested ``summary.md``, and returns a ``LegacySelection``.
#   5.  ``install_legacy_chain_context(sel, dest_dir)`` — byte-copies the
#       selected legacy files into ``dest_dir`` (normally ``.context/`` inside
#       the receiving run's sandbox).

# UUID pattern used to detect legacy nested-payload directories.
# A pre-v2 run_id is always a UUID (hex digits and hyphens, exactly the same
# format ``LocalWorkspace._validate_run_id`` accepts).
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LegacySelection:
    """A validated legacy chain payload selection (task 6.7 / Requirement 7).

    Produced by ``select_legacy_payload`` and consumed by
    ``install_legacy_chain_context``.  Describes a pre-v2 nested chain payload
    that has been located, validated, and is ready to be byte-copied into the
    receiving run's ``.context/`` directory.

    Attributes
    ----------
    ref:
        The ``git_tag`` stored on the source ``WorkflowRun`` row, or ``None``
        when the legacy source was never tagged (an untagged terminal run is
        still eligible per Requirement 7 AC 11).
    base:
        The prefix under which the payload files live — either
        ``.chain-legacy/{source_run_id}/`` (preferred) or
        ``.chain/{source_run_id}/`` (unmigrated fallback).
    files:
        Map of flat ``.context/`` destination basename →
        source relpath inside *this* sandbox.  Always exactly three keys:
        ``"summary.md"``, ``"logs.jsonl"``, and the declared output basename.
    reason_class:
        Provenance label emitted to the audit row (Requirement 7 AC 7 /
        Requirement 19 AC 1).  Always ``"legacy-live-nested"`` for payloads
        read from a live nested directory.
    is_legacy:
        Always ``True``.  Discriminator used by ``install_chain_context`` so
        the shared tail (``mark_chain_context_installed`` + the
        ``chain_payload_installed`` audit write) can unambiguously tell the two
        selection types apart.
    """

    ref: str | None  # stored git_tag; None for untagged legacy
    base: str  # .chain-legacy/{id}/ or .chain/{id}/
    files: dict[str, str]  # flat .context/ name → source relpath
    reason_class: str  # "legacy-live-nested"
    is_legacy: bool = True


def _validate_ref_against_tags(tag: str, src: "ReadOnlySandbox") -> None:
    """Exact-match ``tag`` against the source sandbox's visible tag list.

    Implements the same gate that ``run_files._validate_ref`` provides for the
    ref-browse and restore endpoints (Requirement 9 AC 2 / Requirement 16):
    before any Git subprocess receives the stored tag, confirm it exists in the
    sandbox's own ``list_tags()`` output.  An exact-match failure raises
    ``ValueError`` with a generic (non-enumerating) message.

    Why a generic message?  The tag is the stored ``WorkflowRun.git_tag`` value
    — owned data — so a mismatch indicates a corrupted row or a tag that was
    manually deleted, not a user input error.  The message says which tag was
    rejected without listing what tags exist, so it does not aid enumeration
    of another owner's tags.

    This helper lives in ``sandbox.py`` (rather than being imported from
    ``run_files.py``) to avoid a circular import: ``run_files.py`` imports
    ``RunSandbox`` from this module, so importing back would close a cycle.

    Parameters
    ----------
    tag:
        The tag name to validate.  Must be a non-empty string.
    src:
        The ``ReadOnlySandbox`` of the source run.

    Raises
    ------
    ValueError:
        When ``tag`` is empty, or when it is not found in ``src.list_tags()``.
    """
    if not tag:
        raise ValueError("_validate_ref_against_tags: empty tag name rejected")
    if tag not in src.list_tags():
        raise ValueError(
            f"_validate_ref_against_tags: tag {tag!r} not found in the "
            f"source sandbox's visible tag list (Requirement 16 exact-match gate)"
        )


def _parse_legacy_summary_run_id(content: bytes) -> str | None:
    """Extract the ``run_id`` field from a legacy (or any) ``summary.md``.

    Legacy ``summary.md`` files are simple Markdown/YAML-like text produced by
    the pre-v2 engine.  The run-id line has one of two formats:

    - ``run_id: <uuid>``  (the v1 key)
    - ``run_id: <uuid>``  anywhere in the document

    We parse the first matching line case-insensitively.  Any non-matching
    ``summary.md`` (missing the key, unreadable bytes) returns ``None`` so the
    caller can skip to the next fallback base.

    Returns
    -------
    str | None
        The extracted UUID string, or ``None`` if not found or unparseable.
    """
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — corrupt bytes → skip
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("run_id:"):
            value = stripped[len("run_id:") :].strip()
            # Accept only UUID-shaped values to avoid accepting an injected
            # multi-line value or a markdown table row.
            if _UUID_RE.fullmatch(value):
                return value
    return None


def relocate_legacy_payloads(sandbox_root: "Path") -> int:
    """Atomically relocate pre-v2 nested chain payloads before the first v2 write.

    Scans ``.chain/`` for immediate subdirectories whose names are UUIDs
    (``{run_id}``).  For each one, atomically copies it to
    ``.chain-legacy/{run_id}/`` and then removes the original source only after
    the destination is durable.

    **Atomicity contract (Requirement 7 AC 1-2):**

    - Bytes are preserved: ``shutil.copytree`` copies the full directory tree
      byte-for-byte into ``.chain-legacy/{run_id}/``.
    - Source is removed only after the destination is durable (the copy
      completed without error).
    - An existing ``.chain-legacy/{run_id}/`` is **never overwritten silently**:
      if the destination already exists, the relocation for that entry is skipped
      (it was already migrated by a previous call or placed there manually).

    After this call ``.chain/`` contains no UUID-named subdirectory
    (Requirement 7 AC 3).  The function is idempotent: calling it again on an
    already-migrated sandbox performs zero relocations.

    Parameters
    ----------
    sandbox_root:
        The physical sandbox root directory (``RunSandbox.root``).  If it does
        not exist, or if ``.chain/`` is absent, the function returns 0 immediately
        without creating any directory.

    Returns
    -------
    int
        Number of directories relocated.  0 when nothing was moved.
    """
    chain_dir = sandbox_root / ".chain"
    legacy_dir = sandbox_root / ".chain-legacy"

    if not chain_dir.is_dir():
        return 0  # no .chain/ directory — nothing to migrate

    relocated = 0
    try:
        entries = list(chain_dir.iterdir())
    except OSError:
        return 0  # cannot list .chain/ — skip silently, never raise

    for entry in entries:
        if not entry.is_dir():
            continue  # flat files are v2 payload files — do not touch
        if not _UUID_RE.fullmatch(entry.name):
            continue  # not a UUID-named subdirectory — skip

        destination = legacy_dir / entry.name
        if destination.exists():
            # Already migrated (or manually placed) — skip silently to avoid
            # overwriting durable legacy data (Requirement 7 AC 2).
            # Still remove the stale source so .chain/ ends up clean.
            try:
                shutil.rmtree(str(entry), ignore_errors=True)
            except OSError:
                pass
            continue

        # ── Atomic copy-then-remove sequence ────────────────────────────────
        # Step 1: create .chain-legacy/ if it does not exist yet.
        try:
            legacy_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "relocate_legacy_payloads: cannot create .chain-legacy/ "
                "in sandbox=%s: %s — skipping entry %s",
                sandbox_root,
                exc,
                entry.name,
            )
            continue

        # Step 2: copy bytes to the destination.
        try:
            shutil.copytree(str(entry), str(destination))
        except Exception as exc:  # noqa: BLE001 — copy failure → skip this entry
            logger.warning(
                "relocate_legacy_payloads: copy %s → %s failed: %s — "
                "skipping (source preserved)",
                entry,
                destination,
                exc,
            )
            # Remove a partial destination to avoid a corrupt .chain-legacy entry.
            try:
                shutil.rmtree(str(destination), ignore_errors=True)
            except OSError:
                pass
            continue

        # Step 3: destination is durable — remove the original source.
        try:
            shutil.rmtree(str(entry), ignore_errors=True)
        except OSError as exc:
            # Copy succeeded but removal failed.  This is non-fatal: the source
            # will be skipped on the next call (destination already exists).
            logger.warning(
                "relocate_legacy_payloads: removed copy %s → %s but could "
                "not remove source: %s (non-fatal — destination is durable)",
                entry,
                destination,
                exc,
            )

        relocated += 1
        logger.info(
            "relocate_legacy_payloads: migrated %s → %s",
            entry,
            destination,
        )

    return relocated


def select_legacy_payload(
    src: "ReadOnlySandbox",
    source_run_id: str,
    declared_output_basename: str,
) -> "LegacySelection | None":
    """Locate and validate a legacy nested chain payload for ``source_run_id``.

    Implements Requirement 7 AC 5-12.  This function is called **pre-mint** (in
    the admission gate before the receiving ``WorkflowRun`` row is created) so
    that provenance is settled before any persisted edge is written.

    **Fallback order (AC 5) — exactly these two locations, nothing else:**

    1. ``.chain-legacy/{source_run_id}/``   (migrated)
    2. ``.chain/{source_run_id}/``           (unmigrated live nested)

    Never falls back to: the live flat ``.chain/``, another run's nested
    directory, the latest tag, an ordinal-derived tag, or ``HEAD``.

    **Validation (AC 6):**

    For each candidate base, the function reads ``{base}summary.md`` and
    verifies that its ``run_id:`` field matches ``source_run_id``.  A corrupt
    or mismatched ``summary.md`` causes that base to be skipped.

    **File selection (AC 6):**

    Exactly three files are selected:

    - ``summary.md``
    - ``logs.jsonl``  at ``{base}logs/{source_run_id}.jsonl``
    - the declared output at ``{base}{declared_output_basename}``

    Agent transcripts (``{base}logs/*.md``) are deliberately ignored.

    **Tag validation (AC 10):**

    This function does NOT read ``WorkflowRun.git_tag`` directly — the caller
    is responsible for passing the tag through
    ``_validate_ref_against_tags(tag, src)`` **before** calling this function
    when a tag exists.  That validation must happen before any git subprocess
    runs.  This function never calls any git subprocess.

    **No terminality check here (AC 11):**

    The caller's admission gate (``source_is_terminal``) already ensures the
    source is terminal.  Adding a second terminality check here would create the
    "two gates that must agree" defect class this design exists to remove.

    Parameters
    ----------
    src:
        A ``ReadOnlySandbox`` rooted at the source run's revision-root sandbox.
    source_run_id:
        The UUID string of the source run.
    declared_output_basename:
        The safe output basename declared by the compiled deliverable (from
        ``DeliverableSpec.name``).  Must not be ``"summary.md"`` or
        ``"logs.jsonl"`` (the caller ensures this via ``payload_allowlist``
        validation at compile time).

    Returns
    -------
    LegacySelection | None
        A validated ``LegacySelection`` when a readable payload is found, or
        ``None`` when both fallback locations lack a valid ``summary.md`` with
        the correct ``run_id`` field.  ``None`` tells the caller to raise
        ``ChainRefused("source_payload_missing")`` per AC 8.
    """
    fallback_bases = (
        f".chain-legacy/{source_run_id}/",
        f".chain/{source_run_id}/",
    )

    for base in fallback_bases:
        # Check that at least one file exists under this base (cheap existence
        # check — avoids trying to read summary.md on an absent base).
        if not src.list_prefix(base):
            continue

        # Read and validate summary.md.
        summary_relpath = f"{base}summary.md"
        summary_bytes = src.read_bytes(summary_relpath)
        if summary_bytes is None:
            continue  # summary.md absent or unreadable — try next base

        extracted_run_id = _parse_legacy_summary_run_id(summary_bytes)
        if extracted_run_id is None:
            logger.debug(
                "select_legacy_payload: summary.md at %s has no parseable run_id — "
                "skipping base %s",
                summary_relpath,
                base,
            )
            continue  # corrupt summary — try next base

        if extracted_run_id != source_run_id:
            logger.debug(
                "select_legacy_payload: summary.md run_id=%r != expected=%r — "
                "skipping base %s",
                extracted_run_id,
                source_run_id,
                base,
            )
            continue  # run_id mismatch — try next base

        # Build the three-file selection map (AC 6).
        # Agent transcripts at {base}logs/*.md are ignored.
        logs_relpath = f"{base}logs/{source_run_id}.jsonl"
        output_relpath = f"{base}{declared_output_basename}"

        return LegacySelection(
            ref=None,  # ref is set by the caller after _validate_ref_against_tags
            base=base,
            files={
                "summary.md": summary_relpath,
                "logs.jsonl": logs_relpath,
                declared_output_basename: output_relpath,
            },
            reason_class="legacy-live-nested",
        )

    # Neither fallback location yielded a valid summary.md — no payload found.
    return None


def install_legacy_chain_context(
    sel: "LegacySelection",
    src: "ReadOnlySandbox",
    dest_dir: "Path",
) -> None:
    """Byte-copy a validated legacy selection into ``dest_dir``.

    Implements Requirement 7 AC 6 (byte copy of all selected files) and
    Requirement 6 AC 8 (files read and written as bounded byte streams, not
    UTF-8 strings).

    ``dest_dir`` is normally ``.context/`` inside the receiving run's sandbox.
    Files are written with their flat ``sel.files`` key as the basename —
    ``summary.md``, ``logs.jsonl``, and ``{declared_output_basename}`` — and
    the content is the raw bytes read from the source sandbox.

    **Absent source file handling:**

    When a file listed in ``sel.files`` is absent or unreadable in ``src``,
    the function:

    - Writes an empty file in its place (rather than omitting it entirely),
      so the receiving run always receives a complete, consistent three-file
      set.
    - Logs a warning so operators can diagnose a partially swept legacy payload.

    This matches the "degrade explicitly" requirement of AC 8: the receiving run
    sees a well-formed context with possibly empty content rather than seeing
    a KeyError or a missing file that might be mistaken for a provider bug.

    Parameters
    ----------
    sel:
        A validated ``LegacySelection`` produced by ``select_legacy_payload``.
    src:
        The source run's ``ReadOnlySandbox``.  All reads go through this handle
        — no direct filesystem access is performed here so the traversal-proof
        path guard is always engaged.
    dest_dir:
        The destination directory.  Created (parents included) if it does not
        exist.  Individual file writes use ``Path.write_bytes`` so content is
        preserved verbatim without any encoding transformation.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    for flat_name, src_relpath in sel.files.items():
        dest_file = dest_dir / flat_name

        content: bytes = b""
        raw = src.read_bytes(src_relpath)
        if raw is None:
            logger.warning(
                "install_legacy_chain_context: source file %r absent or unreadable "
                "in sandbox root=%s — writing empty placeholder",
                src_relpath,
                src.root,
            )
        else:
            content = raw

        try:
            dest_file.write_bytes(content)
        except OSError as exc:
            logger.error(
                "install_legacy_chain_context: failed to write %s: %s",
                dest_file,
                exc,
            )
            raise
