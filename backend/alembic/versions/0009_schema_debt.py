"""Schema-debt audit — no-op migration (all columns already present)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-29

Audit result (T006):
  - users.tier              → added by 0005_add_user_tier.py          ✓ EXISTS
  - users.is_admin          → added by 0006_add_is_admin.py           ✓ EXISTS
  - users.preferred_model   → added by 0007_add_preferred_model.py    ✓ EXISTS
  - workflow_runs.model_id  → added by 0008_add_workflow_run_model_id.py ✓ EXISTS
  - workflow_runs.token_usage → added by 0004_add_token_usage.py      ✓ EXISTS

All schema-debt columns are already present in the database.
This migration is a no-op that documents the audit result and establishes
the revision chain for subsequent migrations (0010+).
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: all schema-debt columns already exist.
    # See module docstring for audit details.
    pass


def downgrade() -> None:
    # No-op: nothing was added.
    pass
