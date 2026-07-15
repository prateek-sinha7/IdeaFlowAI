"""0025 — additive deep_link_nonces table (Phase 43, WR-02 nonce hardening).

The milestone narrator (``app/agents/chat_narrator.py``) stamps every ``chat_reply``
card with a single-use deep-link ``{target, nonce}`` so a replayed link can never
resolve twice (T-29-10-2). Phase 29 left the nonce store a PROCESS-GLOBAL in-memory
set (``_ISSUED_NONCES``): unbounded (grows without limit), unscoped (any caller could
consume any nonce — no owner check), and lost on restart. Before the narrator's live
call-site is exposed (A.4) that store is hardened to a DB-backed, owner+workspace-scoped,
single-use, bounded table.

  * ``deep_link_nonces`` — carries ``owner_id`` (NOT NULL, AUTHZ-01) + ``workspace_id``
    so the ``ScopedStore`` default-deny filter scopes every consume (T-43-03-SPOOF /
    T-43-03-IDOR: a nonce this owner never held resolves to nothing → False → 404, never
    leaks existence). ``nonce`` is the primary key (unique lookup + one row per issued
    link). ``consumed_at`` (nullable) is the TERMINAL state: a single-use consume marks it
    once (T-43-03-REPLAY: a second consume matches zero unconsumed rows → False), which
    also BOUNDS growth (consumed rows are terminal; no unbounded in-memory set —
    T-43-03-DOS). ``run_id`` / ``target`` are informational (no FK — the nonce is decoupled
    from run lifecycle so a TTL sweep can reap it independently, mirroring the run-artifact
    TTL pattern). ``created_at`` (NOT NULL) anchors that future TTL sweep.

Plus ``ix_deep_link_nonces_scope`` backing the owner+workspace-scoped consume lookup.

ADDITIVE ONLY (Q3, INV-3): a NEW table only — no existing table/column is altered.
Sequenced after 0024 (``down_revision="0024"``) — the head chain stays single-head.
``downgrade()`` drops the index then the table (fully reversible; mirror of the 0018
``op.create_table`` / ``op.drop_table`` idiom). Proven offline against in-memory SQLite
(upgrade head -> downgrade -1 -> upgrade head).
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deep_link_nonces",
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=True),    # AUTHZ-01 (scope)
        sa.Column("run_id", sa.String(), nullable=True),          # informational (no FK)
        sa.Column("target", sa.String(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),   # terminal (single-use)
        sa.Column("created_at", sa.DateTime(), nullable=False),   # TTL-sweep anchor
        sa.PrimaryKeyConstraint("nonce"),
    )
    op.create_index(
        "ix_deep_link_nonces_scope",
        "deep_link_nonces",
        ["owner_id", "workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_deep_link_nonces_scope", table_name="deep_link_nonces")
    op.drop_table("deep_link_nonces")
