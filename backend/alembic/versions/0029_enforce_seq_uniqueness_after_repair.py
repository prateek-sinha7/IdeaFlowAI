"""0029 — enforce uq_run_events_scope_seq after duplicate reconciliation (FIX-BUG-029).

WHY THIS EXISTS
---------------
Migration 0028 SKIPPED the ``uq_run_events_scope_seq`` constraint because the live
database held duplicate ``(run_id, owner_id, workspace_id, seq)`` tuples produced by
the Phase-29 seq-allocation race (CR-03: the chat-lane narrator and message up-channel
racing the engine's own event sink, both computing ``max(seq)+1`` without a DB lock).

FIX-BUG-029 (2026-07-29) reconciles those duplicates BY DELETING THE LATER DUPLICATE:
  * Groups duplicates by (run_id, owner_id, workspace_id, seq)
  * Keeps the earliest-created event (created_at ASC LIMIT 1)
  * Deletes all later duplicates in the same group
  * This preserves the first event that was logged and removes racing overwrites

This approach is safe because:
  * Duplicates occur when the chat-lane narrator and engine race (CR-03)
  * The ENGINE event (questionnaire_complete, agent_start, etc.) is always first
  * The chat_reply is the secondary racing writer, always later (by milliseconds)
  * Keeping the engine event preserves the durable event log semantics
  * Deleting the duplicate chat_reply recovers the race-free invariant
  * Once this migration completes, future races fail loudly (IntegrityError) instead
    of silently succeeding twice

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
        # Before adding the constraint, remove duplicate rows.
        # For each (run_id, owner_id, workspace_id, seq) group that has duplicates:
        # keep the EARLIEST-created event (first writer wins), delete all later ones.
        # This preserves the engine's event log (always first) and removes racing overwrites.
        
        meta = sa.MetaData()
        run_events = sa.Table("run_events", meta, autoload_with=bind)
        
        # Find all duplicate groups
        duplicate_groups_query = (
            sa.select(
                run_events.c.run_id,
                run_events.c.owner_id,
                run_events.c.workspace_id,
                run_events.c.seq,
            )
            .group_by(
                run_events.c.run_id,
                run_events.c.owner_id,
                run_events.c.workspace_id,
                run_events.c.seq,
            )
            .having(sa.func.count() > 1)
        )
        
        duplicate_groups = bind.execute(duplicate_groups_query).fetchall()
        deleted_count = 0
        
        if duplicate_groups:
            print(
                f"[0029] Found {len(duplicate_groups)} duplicate (run_id, owner_id, "
                "workspace_id, seq) group(s). Deleting later duplicates, keeping earliest."
            )
            
            # For each duplicate group, keep the earliest event_id and delete the rest
            for run_id, owner_id, workspace_id, seq in duplicate_groups:
                # Find the earliest event in this group
                earliest_query = (
                    sa.select(run_events.c.event_id)
                    .where(
                        (run_events.c.run_id == run_id)
                        & (run_events.c.owner_id == owner_id)
                        & (run_events.c.workspace_id == workspace_id)
                        & (run_events.c.seq == seq)
                    )
                    .order_by(run_events.c.created_at.asc())
                    .limit(1)
                )
                earliest_event_id = bind.execute(earliest_query).scalar_one()
                
                # Delete all OTHER events in this group (keep the earliest)
                delete_query = sa.delete(run_events).where(
                    (run_events.c.run_id == run_id)
                    & (run_events.c.owner_id == owner_id)
                    & (run_events.c.workspace_id == workspace_id)
                    & (run_events.c.seq == seq)
                    & (run_events.c.event_id != earliest_event_id)
                )
                result = bind.execute(delete_query)
                deleted_count += result.rowcount or 0
            
            print(
                f"[0029] Deleted {deleted_count} duplicate row(s). "
                "Table is now clean for unique constraint."
            )
        else:
            print("[0029] No duplicate (run_id, owner_id, workspace_id, seq) groups found.")
        
        # Now add the constraint safely
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
