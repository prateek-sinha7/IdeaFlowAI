"""Resolve a user's override of a built-in workflow (spec 016).

ONE rule, ONE place. Three call sites read it — ``list_workflows``,
``get_workflow`` and the run launch — and they must agree, because the screen
showing plan A while the run executes plan B is the failure mode this whole
feature has to avoid.

The row is looked up by the BUILT-IN PIPELINE ID (``overrides_pipeline_type``),
never by name: a name is renamable (the override would silently detach), its
uniqueness is an API-level check-then-insert with no DB constraint, and "the
same name as ppt" is ambiguous between ``manifest.name``, ``display_name`` and
the id. A partial unique index on ``(user_id, overrides_pipeline_type)``
(migration 0039) guarantees at most one row per pair, so ``.first()`` here is
"the" override, not "an arbitrary" one.

OWNERSHIP (AUTHZ-01 / INV-8, default-deny). ``user_id`` is in the filter, so a
cross-owner row is unreachable by construction — matching the ``_owned``
IDOR-to-404 posture in ``app/api/user_workflows.py``. There is no id in the
caller's hands to probe with, so there is nothing to leak.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition


def resolve_override(
    db: Session, user: User, pipeline_type: str
) -> WorkflowDefinition | None:
    """The caller's ENABLED override row for ``pipeline_type``, or ``None``.

    ``None`` for every user who has never saved one — which is the entire
    existing population — so each call site's current behaviour IS the ``None``
    branch and stays byte-identical.

    ``override_enabled`` is part of the filter, not a field the caller checks
    afterwards: a disabled override must be invisible to the resolve path
    exactly as if the row did not exist. Callers that need to know a DISABLED
    row exists (the detail endpoint, to render the checkbox unticked) use
    ``find_override`` below instead.
    """
    if not pipeline_type:
        return None
    return (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.user_id == user.id,
            WorkflowDefinition.source == "user",
            WorkflowDefinition.overrides_pipeline_type == pipeline_type,
            WorkflowDefinition.override_enabled.is_(True),
        )
        .first()
    )


def find_override(
    db: Session, user: User, pipeline_type: str
) -> WorkflowDefinition | None:
    """The caller's override row for ``pipeline_type`` REGARDLESS of enabled state.

    The read endpoints need this to render the checkbox in the right position:
    a user who saved an override and then switched it off must still see the
    box (unticked), not an empty screen with no way to switch it back on.

    Never use this to decide which plan RUNS — that is ``resolve_override``.
    """
    if not pipeline_type:
        return None
    return (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.user_id == user.id,
            WorkflowDefinition.source == "user",
            WorkflowDefinition.overrides_pipeline_type == pipeline_type,
        )
        .first()
    )


def list_overrides(db: Session, user: User) -> dict[str, WorkflowDefinition]:
    """Every override the caller owns, keyed by the built-in id it overrides.

    ONE query for the whole listing endpoint. Resolving per-id there would issue
    a query per built-in (~15) on a page that until now issued none at all.
    Enabled and disabled rows are both returned — the caller decides which
    distinction it needs, the same split as ``resolve_override`` vs
    ``find_override``.
    """
    rows = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.user_id == user.id,
            WorkflowDefinition.source == "user",
            WorkflowDefinition.overrides_pipeline_type.isnot(None),
        )
        .all()
    )
    return {r.overrides_pipeline_type: r for r in rows}


def override_steps(row: WorkflowDefinition | None) -> list | None:
    """The override's manifest steps, or ``None`` when there is nothing usable.

    Guards the shape at the boundary so no call site has to: a row whose
    ``manifest_json`` is NULL, is not a dict, or carries no non-empty ``steps``
    list is treated as "no override". A saved row can only reach that state by
    hand-editing the DB, and degrading to the file manifest is strictly safer
    than propagating a malformed plan.
    """
    if row is None:
        return None
    manifest = row.manifest_json
    if not isinstance(manifest, dict):
        return None
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    return steps
