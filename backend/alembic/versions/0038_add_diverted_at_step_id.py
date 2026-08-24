"""Add diverted_at_step_id column to workflow_runs (R-20 / conditional gates).

The requirement's exact reciprocal text is '← Continued from {parent run},
step {step_id}', but no backend field carries a step id: RevisionFamilyView.tsx
documents that T29 does not write a step-id column and T32's pipeline_diverted
payload does not carry one either. This is a genuine backend-plus-frontend gap.

This migration adds ONE additive nullable String column to ``workflow_runs``:

  * ``diverted_at_step_id`` (String, nullable) — the step id at which a
    diverged/diverted run (child of parent_run_id via the conditional gate)
    was triggered. Frontend uses this to render the breadcrumb message.

ADDITIVE ONLY: no new table, no alter of existing columns, no constraint
changes. Nullable → every legacy run stays NULL (the frontend already has,
and after T42 will keep, a documented fallback for a null step id). Populated
by a later task (T41).
``batch_alter_table`` ensures SQLite portability (mirrors the 0027 pattern).

Authored as ``0033`` with ``down_revision = "0032"``. The cognito-login side
independently added its own ``0033`` (``0033_user_api_key_expiry``), so after
the merge two revisions claimed ``0033`` and alembic reported two heads —
``0034_mfa_verified_at``'s ``down_revision = "0033"`` was ambiguous between
them. Re-homed to ``0038`` at the END of the chain, the same way
``0036_composed_workflow_execution`` and ``0037_collapse_od_prototype_label``
were re-homed off ``0031``/``0032``. The migration is additive and order-
independent, so moving it later changes nothing about what it does.
"""

from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("diverted_at_step_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("diverted_at_step_id")
