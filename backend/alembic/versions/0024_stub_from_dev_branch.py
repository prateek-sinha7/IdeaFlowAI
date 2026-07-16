"""0024 — stub to reconcile dev-branch migration applied to local DB.

This revision was applied to the local dev.db from a merged dev-branch commit
that is not yet present in this working branch. The stub has an empty upgrade
so running ``alembic upgrade head`` on a DB already at 0024 is a safe no-op;
it only matters for Alembic's internal revision graph so the chain 0023→0024→0025
is resolvable. The actual schema change from 0024 will be present in the dev
branch; this stub is removed when the branches merge.
"""

from alembic import op  # noqa: F401

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty — the real 0024 from the dev branch already applied its changes.
    pass


def downgrade() -> None:
    # Empty — nothing to reverse for a stub.
    pass
