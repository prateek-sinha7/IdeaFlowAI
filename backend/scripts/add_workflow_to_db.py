#!/usr/bin/env python3
"""Store a workflow JSON file in the database as a saved workflow for one user.

The row is the same one ``POST /api/user-workflows`` creates (a ``source="user"``
row in the ``workflows`` table), owner-stamped to the target user, and the
manifest goes through the same validation the API runs before saving.

Accepted JSON shapes:

1. A bare manifest::

       {"steps": [ ... ], "capabilities": { ... }}

2. A save body, where the manifest sits under ``manifest``::

       {"name": "...", "description": "...", "base_pipeline_type": "custom",
        "manifest": {"steps": [ ... ]}}

The workflow name comes from ``--name``, then the JSON ``name`` key, then the
file name.

Usage (from backend/):
    uv run python scripts/add_workflow_to_db.py my_workflow.json
    uv run python scripts/add_workflow_to_db.py my_workflow.json --name "My Flow"
    uv run python scripts/add_workflow_to_db.py my_workflow.json --replace
    uv run python scripts/add_workflow_to_db.py my_workflow.json --dry-run

Exit codes: 0 stored (or dry-run OK), 1 error.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Resolve CLI paths against the caller's directory, then run from backend/ so
# ``.env`` and the ``app.*`` imports resolve (same setup as the other scripts).
_CALLER_CWD = Path.cwd()
_BACKEND_DIR = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_DIR)
sys.path.insert(0, str(_BACKEND_DIR))

DEFAULT_EMAIL = "gajerasharadn@hexaware.com"
DEFAULT_BASE_PIPELINE_TYPE = "custom"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("add_workflow_to_db")


def _load_json(path_arg: str) -> dict:
    """Read the workflow JSON file and return its top-level object."""
    path = Path(path_arg)
    if not path.is_absolute():
        path = _CALLER_CWD / path
    if not path.is_file():
        raise ValueError(f"No such file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("The JSON file must contain an object at the top level")
    return data


def _split_payload(data: dict, fallback_name: str) -> dict:
    """Split the JSON into name / description / base type / manifest."""
    manifest = data["manifest"] if isinstance(data.get("manifest"), dict) else data
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("The workflow JSON needs a non-empty 'steps' list")
    return {
        "name": str(data.get("name") or fallback_name).strip(),
        "description": data.get("description"),
        "base_pipeline_type": data.get("base_pipeline_type")
        or DEFAULT_BASE_PIPELINE_TYPE,
        # Only the manifest is stored; save-body metadata is not part of it.
        "manifest": manifest,
    }


def _agent_ids(manifest: dict) -> list[str]:
    """Step ids for the legacy ``agents`` column (mirrors the API's projection)."""
    ids: list[str] = []
    for step in manifest.get("steps") or []:
        if not isinstance(step, dict) or not step.get("agent"):
            continue
        instance_id = step.get("instance_id")
        ids.append(f"{step['agent']}:{instance_id}" if instance_id else step["agent"])
    return ids


def add_workflow(
    json_path: str,
    email: str,
    name: str | None,
    replace: bool,
    dry_run: bool,
) -> int:
    """Validate the workflow and store it for ``email``. Returns an exit code."""
    from fastapi import HTTPException

    from app.api.run_engine import _saved_row_trust
    from app.api.user_workflows import _validated_manifest
    from app.models.database import SessionLocal
    from app.models.user import User
    from app.models.workflow_definition import WorkflowDefinition

    try:
        data = _load_json(json_path)
        payload = _split_payload(data, Path(json_path).stem)
        if name:
            payload["name"] = name.strip()
        if not payload["name"] or len(payload["name"]) > 120:
            raise ValueError("Workflow name must be 1-120 characters")
    except ValueError as exc:
        logger.error(str(exc))
        return 1

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email.ilike(email.strip())).first()
        if user is None:
            logger.error("No user found with email %s", email)
            return 1

        # Same validation the API applies before it stores a manifest.
        try:
            manifest = _validated_manifest(
                payload["manifest"],
                f"workflow:{payload['name']}",
                trust=_saved_row_trust(user.tier),
            )
        except HTTPException as exc:
            logger.error("Manifest rejected: %s", exc.detail)
            return 1

        existing = (
            db.query(WorkflowDefinition)
            .filter(
                WorkflowDefinition.user_id == user.id,
                WorkflowDefinition.source == "user",
                WorkflowDefinition.name == payload["name"],
            )
            .first()
        )
        if existing is not None and not replace:
            logger.error(
                "%s already has a workflow named %r (id=%s). "
                "Use --replace to overwrite it or --name to pick another name.",
                user.email,
                payload["name"],
                existing.id,
            )
            return 1

        if dry_run:
            action = "replace" if existing is not None else "create"
            logger.info(
                "Dry run OK: would %s %r for %s (%d steps)",
                action,
                payload["name"],
                user.email,
                len(manifest["steps"]),
            )
            return 0

        if existing is not None:
            row = existing
            row.description = payload["description"]
            row.agents = json.dumps(_agent_ids(manifest))
            row.base_pipeline_type = payload["base_pipeline_type"]
            row.manifest_json = manifest
        else:
            row = WorkflowDefinition(
                user_id=user.id,
                owner_id=user.id,
                workspace_id=user.id,
                name=payload["name"],
                agents=json.dumps(_agent_ids(manifest)),
                artifact_edges="[]",
                description=payload["description"],
                source="user",
                base_pipeline_type=payload["base_pipeline_type"],
                manifest_json=manifest,
            )
            db.add(row)
        db.commit()
        logger.info(
            "Stored workflow %r for %s (id=%s, %d steps)",
            row.name,
            user.email,
            row.id,
            len(manifest["steps"]),
        )
        return 0
    except Exception:
        db.rollback()
        logger.exception("Failed to store workflow")
        return 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("json_file", help="Path to the workflow JSON file")
    parser.add_argument(
        "--name", help="Workflow name (default: JSON 'name' or file name)"
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Owner email (default: {DEFAULT_EMAIL})",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite the user's existing workflow with the same name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report without writing to the database",
    )
    args = parser.parse_args()
    return add_workflow(
        args.json_file, args.email, args.name, args.replace, args.dry_run
    )


if __name__ == "__main__":
    sys.exit(main())
