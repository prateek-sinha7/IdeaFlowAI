"""0017 — additive repositories table + workspaces.repo_id FK (Phase 9 / RUNTIME-03, D-11).

Adds the owner/workspace-scoped ``repositories`` table the repo workflows persist
one row into per repo run, and wires the (already-present, nullable) ``workspaces.repo_id``
column to it with an additive foreign key.

  * ``repositories`` — one row per repo bound to a run; carries ``owner_id`` +
    ``workspace_id`` (both NOT NULL, AUTHZ-01) so the ``ScopedStore`` default-deny
    filter scopes every read. ``provider`` is a free ``String`` (``github`` /
    ``gitlab`` / ``local``) — NO ``sa.Enum`` (R-G: additive + reversible, consistent
    with the free-String ``kind`` / ``runtime`` on ``workspaces``).
  * ``workspaces.repo_id`` — already a nullable ``String`` from 0014 (the "Phase 9
    forward field"); 0017 only adds the FK constraint → ``repositories.id``. The
    target table is created FIRST in this same migration so the FK target exists.
  * ``mcp_credentials`` — per-owner scoped + encrypted MCP server credential (09-05 /
    MCP-02); carries ``owner_id`` + ``workspace_id`` (both NOT NULL, AUTHZ-01) so the
    ``ScopedStore`` default-deny filter scopes every read. The secret is Fernet-encrypted
    (``encrypted_secret``), never plaintext — the ``UserGithubCredential`` PAT precedent.

``workspaces.kind`` is already a free ``String`` (``0014:88``), so ``kind='repo'``
rows need NO additive widening — they just work.

ADDITIVE ONLY (Q3, INV-3): no existing table is altered destructively. Sequenced
after 0016 (down_revision="0016") — the head chain stays unbroken. ``downgrade()``
drops the FK then the table (fully reversible; mirror of ``0014:236``
``op.drop_table("workspaces")``). The named FK constraint keeps the downgrade
deterministic across SQLite (batch) + Postgres.
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Named so the downgrade can drop it deterministically (and SQLite batch can target it).
_REPO_FK = "fk_workspaces_repo_id_repositories"


def upgrade() -> None:
    # repositories created FIRST so the workspaces.repo_id FK target exists.
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        # Free String (NO sa.Enum): 'github' | 'gitlab' | 'local'.
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("default_branch", sa.String(), nullable=False),
        sa.Column("auth_ref", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Wire the already-present nullable workspaces.repo_id to repositories.id.
    # Use a batch op so the ALTER is portable to SQLite (no native ADD CONSTRAINT).
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.create_foreign_key(
            _REPO_FK, "repositories", ["repo_id"], ["id"]
        )

    # mcp_credentials — per-owner scoped + encrypted MCP server credential (09-05 /
    # MCP-02). Owner/workspace-scoped (both NOT NULL, AUTHZ-01) so the ScopedStore
    # default-deny filter scopes every read; the secret is Fernet-encrypted, never
    # plaintext. `server` is a free String (the catalog mcp_server name) — NO sa.Enum.
    op.create_table(
        "mcp_credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("server", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Drop the mcp_credentials table, then the FK, then the repositories table —
    # clean reverse (mirror of 0014:236).
    op.drop_table("mcp_credentials")
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_constraint(_REPO_FK, type_="foreignkey")
    op.drop_table("repositories")
