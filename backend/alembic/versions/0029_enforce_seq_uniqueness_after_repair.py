"""0029 — enforce uq_run_events_scope_seq after duplicate reconciliation (FIX-BUG-029).

WHY THIS EXISTS
---------------
Migration 0028 SKIPPED the ``uq_run_events_scope_seq`` constraint because the live
database held duplicate ``(run_id, owner_id, workspace_id, seq)`` tuples produced by
the Phase-29 seq-allocation race (CR-03: the chat-lane narrator and message up-channel
racing the engine's own event sink, both computing ``max(seq)+1`` without a DB lock).

FIX-BUG-029 (2026-07-29) reconciled those duplicates:
  * Identified 3 duplicate groups in run_id=fd11d076-a007-4b90-a511-9514d8ca2034
  * Deleted the chat_reply rows (the secondary racing writer)
  * Kept the engine events (questionnaire_complete, clarification_limit_reached, agent_start)
  * Verified all duplicates are now gone

Now that the table is clean, this revision applies the missing constraint so any future
racing insert fails LOUDLY (IntegrityError → 409/500, recoverable via retry) instead of
silently succeeding twice. The ``ScopedStore.append_event_next_seq`` allocator catches
the error and retries, ensuring the DURABLE log never holds a duplicate seq.

ADDITIVE ONLY / IDEMPOTENT
--------------------------
The constraint is added only if not already present (guarded by inspector check, the
0014 precedent). A database already at 0029 (or past it) sees this as a no-op.

SCOPE = (run_id, owner_id, workspace_id)
The constraint mirrors ``ScopedStore.read_events`` scoping (owner_id + workspace_id).
A cross-owner store's default-deny read sees an empty tail and restarts seq under its
own principal (T-29-10-1) — a different scope, not a collision — so the constraint must
not span owners.

DOWNGRADE
---------
Drops the constraint (reversible, consistent with 0024/0025 drop semantics).
"""

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if the constraint already exists (idempotent for already-upgraded databases)
    existing_uniques = {
        uc["name"] for uc in inspector.get_unique_constraints("run_events")
    }

    if "uq_run_events_scope_seq" not in existing_uniques:
        # Safe to add unconditionally now: duplicates have been reconciled (FIX-BUG-029)
        with op.batch_alter_table("run_events") as b:
            b.create_unique_constraint(
                "uq_run_events_scope_seq",
                ["run_id", "owner_id", "workspace_id", "seq"],
            )
        print(
            "[0029] Successfully added uq_run_events_scope_seq constraint after "
            "duplicate reconciliation (FIX-BUG-029)."
        )
    else:
        print("[0029] uq_run_events_scope_seq already exists (idempotent).")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_uniques = {
        uc["name"] for uc in inspector.get_unique_constraints("run_events")
    }

    if "uq_run_events_scope_seq" in existing_uniques:
        with op.batch_alter_table("run_events") as b:
            b.drop_constraint("uq_run_events_scope_seq", type_="unique")
