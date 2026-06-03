"""app/agents/sandbox.py — per-user/per-run disk sandbox for the deepagents filesystem.

Each pipeline run gets an isolated directory ``<RUNS_ROOT>/<user>/<run>/`` on the
persistent runs volume. The deepagents disk filesystem backend is rooted here, so
one user's run can never read or write another's files, and a ``..`` traversal
cannot escape the run dir. Finished runs are swept after ``RUN_DIR_TTL_HOURS``.

This is the user-based workspace isolation requirement, implemented on real disk.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("app.agents.sandbox")

# Map any user/run identifier to ONE safe path segment. user_id is a UUID or an
# email; run_id is a UUID. We allow [A-Za-z0-9._-] and replace everything else, so
# an identifier can never introduce a path separator or a traversal sequence.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_segment(value: str, *, fallback: str) -> str:
    seg = _UNSAFE.sub("_", (value or "").strip())
    seg = seg.strip(".")  # ".", ".." → "" so they can never be a segment
    return (seg or fallback)[:128]


class RunSandbox:
    """An isolated on-disk workspace for one pipeline run.

    ``root`` = ``<RUNS_ROOT>/<user>/<run>/``. Create it with :meth:`ensure`,
    resolve paths inside it with :meth:`path_for` (rejects escapes), remove it
    with :meth:`cleanup`.
    """

    def __init__(self, user_id: str, run_id: str, *, runs_root: str | None = None) -> None:
        self.user_seg = _safe_segment(user_id, fallback="anonymous")
        self.run_seg = _safe_segment(run_id, fallback="run")
        base = Path(runs_root or settings.RUNS_ROOT).resolve()
        self.base = base
        self.root = (base / self.user_seg / self.run_seg).resolve()
        # Defence in depth: the resolved run dir must stay under RUNS_ROOT even if
        # the sanitiser is ever weakened.
        if self.root != base and not str(self.root).startswith(str(base) + "/"):
            raise ValueError(f"sandbox root escaped RUNS_ROOT: {self.root}")

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
        if candidate != self.root and not str(candidate).startswith(str(self.root) + "/"):
            raise ValueError(f"path escapes run sandbox: {relpath!r}")
        return candidate

    def write(self, relpath: str, content: str) -> Path:
        p = self.path_for(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def read(self, relpath: str) -> str | None:
        p = self.path_for(relpath)
        return p.read_text(encoding="utf-8") if p.is_file() else None

    def cleanup(self) -> None:
        """Remove the run dir (idempotent)."""
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
