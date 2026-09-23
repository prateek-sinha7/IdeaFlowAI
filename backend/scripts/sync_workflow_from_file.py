#!/usr/bin/env python3
"""
Sync a workflow from disk YAML into the database.

The database copy of a saved workflow (id from --workflow-id) may drift from its
source workflow.yaml file. This script re-reads the file and writes it back into
the database row's manifest_json column, verbatim, restoring parity.

The endpoint POST /api/user-workflows/{id}/sync-from-file does the same operation
through the API; this script is for offline sync by an operator.

Usage (from backend/):
    python scripts/sync_workflow_from_file.py --workflow-id <id> --yaml-path <path>
    python scripts/sync_workflow_from_file.py --workflow-id <id> --yaml-path <path> --apply

Exit Codes:
    0   — Success (dry-run shows diff, --apply persists it)
    1   — Validation error (YAML parse, missing workflow, etc.)
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Make app importable + run from backend/.
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

import yaml
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _load_yaml_file(yaml_path: str) -> dict:
    """Load and parse a YAML file; raise FileNotFoundError or yaml.YAMLError."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {yaml_path}")
    content = path.read_text(encoding="utf-8")
    return yaml.safe_load(content) or {}


def _get_db() -> Session:
    """Get a database session."""
    from app.models.database import SessionLocal
    return SessionLocal()


def _get_workflow_row(db: Session, workflow_id: str):
    """Fetch a user workflow row by id; raise ValueError if not found."""
    from app.models.workflow_definition import WorkflowDefinition

    row = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == workflow_id)
        .first()
    )
    if not row:
        raise ValueError(f"No workflow found with id={workflow_id!r}")
    return row


def _flatten_diff_value(value: object) -> str:
    """Render a leaf value for diff display."""
    _DIFF_MISSING = object()
    if value is _DIFF_MISSING:
        return "<absent>"
    if isinstance(value, str):
        return repr(value) if len(value) <= 80 else f"<str len={len(value)}>"
    if isinstance(value, (dict, list)):
        return f"<{type(value).__name__} len={len(value)}>"
    return repr(value)


def _flatten_diff(a: object, b: object, path: str = "") -> list[str]:
    """Recursive structural diff of two trees."""
    _DIFF_MISSING = object()

    if a == b:
        return []
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            out.extend(
                _flatten_diff(
                    a.get(key, _DIFF_MISSING),
                    b.get(key, _DIFF_MISSING),
                    f"{path}.{key}" if path else str(key),
                )
            )
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        for i in range(max(len(a), len(b))):
            av = a[i] if i < len(a) else _DIFF_MISSING
            bv = b[i] if i < len(b) else _DIFF_MISSING
            out.extend(_flatten_diff(av, bv, f"{path}[{i}]"))
        return out
    return [f"{path}: {_flatten_diff_value(a)} != {_flatten_diff_value(b)}"]


def _diff_manifest_dicts(old: dict | None, new: dict) -> list[str]:
    """Structural diff of manifest_json (old DB value) vs new file value."""
    return _flatten_diff(old or {}, new)


def sync_workflow(workflow_id: str, yaml_path: str, apply: bool = False) -> int:
    """
    Load workflow.yaml, compute diff vs DB row, optionally persist.

    Returns 0 on success, 1 on error.
    """
    try:
        # Load YAML file
        logging.info(f"Loading {yaml_path}")
        new_manifest = _load_yaml_file(yaml_path)

        if not isinstance(new_manifest, dict):
            logging.error(f"YAML must be a dict, got {type(new_manifest).__name__}")
            return 1

        # Connect to DB
        db = _get_db()
        try:
            # Fetch workflow row
            row = _get_workflow_row(db, workflow_id)
            logging.info(f"Found workflow {workflow_id} (name={row.name!r})")

            # Compute diff
            old_manifest = row.manifest_json if isinstance(row.manifest_json, dict) else None
            diff = _diff_manifest_dicts(old_manifest, new_manifest)

            # Print summary
            if diff:
                logging.info(f"Diff: {len(diff)} field(s) will change")
                for line in diff:
                    print(f"  {line}")
            else:
                logging.info("No changes (manifests already match)")

            # Apply if requested
            if apply:
                row.manifest_json = new_manifest
                db.commit()
                logging.info(f"Persisted {workflow_id}")
            else:
                logging.info("(dry-run; use --apply to persist)")

            return 0

        finally:
            db.close()

    except FileNotFoundError as e:
        logging.error(f"File error: {e}")
        return 1
    except yaml.YAMLError as e:
        logging.error(f"YAML parse error: {e}")
        return 1
    except ValueError as e:
        logging.error(str(e))
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--workflow-id",
        required=True,
        help="Workflow ID to sync",
    )
    parser.add_argument(
        "--yaml-path",
        required=True,
        help="Path to workflow.yaml file",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually persist changes (default: dry-run)",
    )

    args = parser.parse_args()
    return sync_workflow(args.workflow_id, args.yaml_path, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
