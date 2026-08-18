"""Engine-owned JSONL trace writer (R-23).

``RunLog`` writes ``<sandbox_root>/.logs/run-logs.jsonl`` — one JSON object per
line, append-only. It is instantiated and called by the engine only; no agent
tool exposes it. A logging failure (unwritable dir, serialization error, full
disk) must never fail a run — every method here swallows its own exceptions
and logs a warning instead of raising.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class RunLog:
    """Append-only JSONL trace writer scoped to one run's sandbox."""

    def __init__(self, sandbox_root: Path | None) -> None:
        # A run can legitimately have no sandbox (see `_run_agent`, which is
        # driven sandbox-less by several suites). Tracing is best-effort, so a
        # missing root disables the log rather than failing the run — the same
        # contract as the try/except in `write`.
        self._path = Path(sandbox_root) / ".logs" / "run-logs.jsonl" if sandbox_root else None

    def write(self, event: str, **fields: object) -> None:
        """Append one JSON object line. Never raises."""
        if self._path is None:
            return
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **fields,
            }
            line = json.dumps(entry, default=repr)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:  # noqa: BLE001 — logging must never fail a run
            logger.warning("RunLog.write failed for event %r: %s", event, exc)
