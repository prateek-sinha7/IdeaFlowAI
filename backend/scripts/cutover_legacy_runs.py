"""T021b — Cutover script: terminate in-flight legacy WorkflowRuns.

Run ONCE during the deployment window, before deleting the legacy runner files
(orchestrator_v2.py, od_runner.py, od_ppt_runner.py).

A "legacy" run is any WorkflowRun in a non-terminal status that was created by
the old runners (i.e. has no pipeline_run_id — that column is populated only by
the new Universal Execution_Engine). Such runs can never resume under the new
engine, so we mark them `cancelled` with an audit annotation rather than leaving
them stuck at `running` forever (FR-019).

Usage:
    python scripts/cutover_legacy_runs.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone  # noqa: E402

from agents.execution_engine.engine import NON_TERMINAL_RUN_STATUSES  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402
from app.models.workflow import WorkflowRun  # noqa: E402


def main(dry_run: bool = False) -> int:
    db = SessionLocal()
    try:
        # In-flight runs that the new engine cannot resume.
        stuck = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.status.in_(NON_TERMINAL_RUN_STATUSES))
            .all()
        )
        count = 0
        for wr in stuck:
            # A run created by the new engine has a pipeline_run_id; skip those
            # (Phase 3 adds the column — until then, all such runs are legacy).
            has_new_id = getattr(wr, "pipeline_run_id", None)
            if has_new_id:
                continue
            count += 1
            print(f"  {'[dry-run] ' if dry_run else ''}cancelling run {wr.id} "
                  f"(status={wr.status}, type={wr.type})")
            if not dry_run:
                wr.status = "cancelled"
                wr.error = "legacy_runner_cutover"
                wr.completed_at = datetime.now(timezone.utc)
        if not dry_run:
            db.commit()
        print(f"\n{'Would cancel' if dry_run else 'Cancelled'} {count} legacy in-flight run(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
