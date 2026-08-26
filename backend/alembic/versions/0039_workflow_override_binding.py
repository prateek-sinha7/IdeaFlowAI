"""Add the user-override binding columns to ``workflows`` (spec 016).

A user edits a built-in workflow (``ppt``) on the canvas and saves it; from then
on THEIR ``ppt`` is the edited one, on the detail page and at launch, until they
switch it off. This migration adds the three columns that binding needs.

  * ``overrides_pipeline_type`` (String, nullable) — the BUILT-IN id this row
    overrides (``"ppt"``). NULL on every existing row and on every ordinary
    "save as a new workflow", which is what keeps the mechanism inert for
    everyone who has not opted in.
  * ``override_enabled`` (Boolean, not null, server_default false) — the
    checkbox. Read by BOTH the read endpoints and the launch resolve so the
    screen and the run can never disagree about which plan is in force.
  * ``base_version`` (Integer, nullable) — the base manifest's ``version`` at
    save time, so a later "the original has changed since you customised it"
    notice has something to compare against. Nullable because it is meaningless
    for a non-override row.

WHY NOT REUSE ``base_pipeline_type``: it already means "which entitlement key
applies / what did I start from". A user may legitimately hold several saved
workflows with ``base_pipeline_type = "ppt"`` that are ordinary copies, not
overrides — overloading it would make "which one wins" undefined.

WHY NOT KEY ON ``name``: it is renamable via PATCH (the override would silently
detach), its uniqueness is an API-level check-then-insert with no DB constraint
(``app/api/user_workflows.py`` — two concurrent saves both pass), and "the same
name as ppt" is ambiguous between ``manifest.name``, ``display_name`` and the id.
Only the id is stable.

The partial unique index is what makes "save once, or overwrite always" a
DATABASE guarantee rather than a racy pre-check: at most one override row per
(user, built-in). It is partial so the millions of rows with a NULL
``overrides_pipeline_type`` do not collide with each other.

ADDITIVE ONLY: no new table, no alter of an existing column, no constraint on
existing data. ``batch_alter_table`` for SQLite portability (the 0027/0038
pattern).
"""

from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflows") as b:
        b.add_column(sa.Column("overrides_pipeline_type", sa.String(), nullable=True))
        b.add_column(
            sa.Column(
                "override_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        b.add_column(sa.Column("base_version", sa.Integer(), nullable=True))

    # Partial unique index: one override per (user, built-in). The WHERE clause
    # is dialect-specific but the same predicate on both engines we target;
    # without it every NULL-override row would contend for a single slot per
    # user on SQLite, which does treat NULLs as distinct but only for a plain
    # unique index — the partial form states the intent explicitly and is what
    # Postgres needs.
    op.create_index(
        "uq_workflows_user_override",
        "workflows",
        ["user_id", "overrides_pipeline_type"],
        unique=True,
        sqlite_where=sa.text("overrides_pipeline_type IS NOT NULL"),
        postgresql_where=sa.text("overrides_pipeline_type IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflows_user_override", table_name="workflows")
    with op.batch_alter_table("workflows") as b:
        b.drop_column("base_version")
        b.drop_column("override_enabled")
        b.drop_column("overrides_pipeline_type")
