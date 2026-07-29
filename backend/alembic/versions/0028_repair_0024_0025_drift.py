"""0028 — idempotent repair of the 0024/0025 schema drift.

WHY THIS EXISTS
---------------
The dev database reported ``alembic_version = 0025`` while NONE of the DDL from
0024 or 0025 had actually been applied. Because Alembic resumes from the stamped
revision, ``upgrade head`` went straight 0025 → 0026 → 0027 and will NEVER
revisit 0024/0025 — the version table reads "fully migrated" while four objects
are permanently absent:

  * ``deep_link_nonces``            (table, 0025)  — actively raising
    ``UndefinedTable`` on every milestone-card persist, silently disabling the
    deep-link nonce store (``app/agents/chat_narrator.py`` → ``ScopedStore``).
  * ``ix_deep_link_nonces_scope``   (index, 0025)
  * ``uq_run_events_scope_event``   (unique constraint, 0024) — the run_events
    idempotency backstop.
  * ``uq_run_events_scope_seq``     (unique constraint, 0024) — the monotonic-seq
    backstop.

Re-stamping backwards is NOT a viable repair: ``stamp 0023 && upgrade head``
re-runs 0026/0027 against columns that already exist (hard failure), and
``downgrade`` through 0024/0025 tries to drop objects that were never created.
So the repair is expressed forward, as this revision.

IDEMPOTENT BY CONSTRUCTION
--------------------------
Every step is guarded by a live-connection existence check via
``sa.inspect(bind)`` (the 0014 ``op.get_bind()`` precedent — "additive
migrations must be defensive against partial application"). A database where
0024/0025 applied correctly — stage/prod may well be correct — sees this
revision as a NO-OP rather than a duplicate-object error. That matters
operationally: ``backend/docker-entrypoint.sh`` runs ``alembic upgrade head``
under ``set -eu``, so a raising migration crash-loops the container instead of
booting.

ADDITIVE ONLY / NO DATA LOSS
----------------------------
``CREATE TABLE`` + ``CREATE INDEX`` + ``ADD CONSTRAINT`` only. No DROP, no
UPDATE, no DELETE, no backfill, no table rewrite. Existing rows are never read
for mutation, so deliverables stay byte-identical (INV-3).

``uq_run_events_scope_seq`` IS CONDITIONAL — AND WHY
----------------------------------------------------
``run_events`` currently holds duplicate ``(run_id, owner_id, workspace_id, seq)``
tuples, and the count GROWS with each new run (observed 3 → 6 → 9 groups inside
~40 minutes), so these are not historical debris: the chat-lane ``seq``
allocator is racing live, and the absent 0024 constraint is what has been
masking it. Observed shape — a ``chat_reply`` and a second event claiming one
``seq``::

    seq 6 | chat_reply             | 12:55:43.776
    seq 6 | questionnaire_complete | 12:56:15.868

Adding the constraint unconditionally would therefore (a) fail outright on any
database holding duplicates, crash-looping the backend, or (b) once past that,
convert a live silent collision into a hard ``IntegrityError`` on a user path.
Neither is an acceptable deploy-time outcome, and de-duplicating would mean
deleting or rewriting rows — excluded by the no-data-loss requirement.

So this revision adds ``uq_run_events_scope_seq`` ONLY when the table is already
clean, and otherwise SKIPS it with a loud warning. The constraint is then
self-healing: once the ``seq`` allocator is fixed and the affected rows are
reconciled deliberately (tracked separately — NOT this migration's job), the
next ``upgrade head``… will not re-run this revision, so that follow-up must add
the constraint in its own revision. This migration's contract is narrower and
honest: repair everything repairable without touching a single row of data.

``downgrade()`` is deliberately a no-op — see its docstring.
"""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


# (run_id, owner_id, workspace_id, seq) — the 0024 monotonic-seq scope.
_SEQ_COLS = ["run_id", "owner_id", "workspace_id", "seq"]
# (run_id, owner_id, workspace_id, event_id) — the 0024 idempotency scope.
_EVENT_COLS = ["run_id", "owner_id", "workspace_id", "event_id"]


def _duplicate_group_count(bind, columns: list[str]) -> int:
    """Count value-groups in ``run_events`` that would violate a UNIQUE on ``columns``.

    Zero means the constraint can be added cleanly. Built with SQLAlchemy core so
    it runs on both Postgres (production) and SQLite (the offline migration tests).
    """
    meta = sa.MetaData()
    run_events = sa.Table("run_events", meta, autoload_with=bind)
    cols = [run_events.c[name] for name in columns]
    grouped = (
        sa.select(*cols)
        .group_by(*cols)
        .having(sa.func.count() > 1)
        .subquery()
    )
    return bind.execute(
        sa.select(sa.func.count()).select_from(grouped)
    ).scalar_one()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- 0025: deep_link_nonces table -------------------------------------
    # Column shape mirrors 0025 EXACTLY (and the DeepLinkNonce ORM model in
    # app/models/run_event.py) so a repaired database is indistinguishable from
    # one that migrated cleanly.
    if "deep_link_nonces" not in inspector.get_table_names():
        op.create_table(
            "deep_link_nonces",
            sa.Column("nonce", sa.String(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),     # AUTHZ-01
            sa.Column("workspace_id", sa.String(), nullable=True),  # AUTHZ-01 (scope)
            sa.Column("run_id", sa.String(), nullable=True),        # informational (no FK)
            sa.Column("target", sa.String(), nullable=True),
            sa.Column("consumed_at", sa.DateTime(), nullable=True), # terminal (single-use)
            sa.Column("created_at", sa.DateTime(), nullable=False), # TTL-sweep anchor
            sa.PrimaryKeyConstraint("nonce"),
        )

    # --- 0025: ix_deep_link_nonces_scope ----------------------------------
    # Re-inspect: the table may have just been created above, and an inspector
    # caches its view of the schema.
    existing_indexes = {
        ix["name"] for ix in sa.inspect(bind).get_indexes("deep_link_nonces")
    }
    if "ix_deep_link_nonces_scope" not in existing_indexes:
        op.create_index(
            "ix_deep_link_nonces_scope",
            "deep_link_nonces",
            ["owner_id", "workspace_id"],
        )

    # --- 0024: the two run_events uniqueness backstops --------------------
    existing_uniques = {
        uc["name"] for uc in inspector.get_unique_constraints("run_events")
    }

    # Idempotency backstop — verified clean, so added unconditionally (still
    # guarded for the already-correct-database case).
    if "uq_run_events_scope_event" not in existing_uniques:
        dupes = _duplicate_group_count(bind, _EVENT_COLS)
        if dupes:
            # Defensive: event_id duplicates should be impossible (per-run uuid).
            # If they ever exist, skip rather than crash-loop the backend.
            print(
                "[0028] SKIPPING uq_run_events_scope_event — "
                f"{dupes} duplicate (run_id, owner_id, workspace_id, event_id) "
                "group(s) present. Reconcile them, then add the constraint in a "
                "follow-up revision."
            )
        else:
            with op.batch_alter_table("run_events") as b:
                b.create_unique_constraint("uq_run_events_scope_event", _EVENT_COLS)

    # Monotonic-seq backstop — CONDITIONAL. See the module docstring: duplicates
    # are being produced live by a racing seq allocator, and de-duplicating would
    # mean losing or rewriting rows.
    if "uq_run_events_scope_seq" not in existing_uniques:
        dupes = _duplicate_group_count(bind, _SEQ_COLS)
        if dupes:
            print(
                "[0028] SKIPPING uq_run_events_scope_seq — "
                f"{dupes} duplicate (run_id, owner_id, workspace_id, seq) group(s) "
                "present. This is the live chat-lane seq-allocation race that the "
                "missing 0024 constraint has been masking. Fix the allocator and "
                "reconcile the affected rows, then add this constraint in its own "
                "revision. Deliberately NOT failing the deploy: the backend "
                "entrypoint runs `alembic upgrade head` under `set -eu`."
            )
        else:
            with op.batch_alter_table("run_events") as b:
                b.create_unique_constraint("uq_run_events_scope_seq", _SEQ_COLS)


def downgrade() -> None:
    """Intentionally a no-op.

    This revision REPAIRS objects that 0024/0025 already own. Dropping them here
    would mean a ``downgrade`` past 0028 leaves a database that 0024/0025 can
    never recreate (they are stamped as applied) — reintroducing exactly the
    drift this revision exists to fix. The 0024/0025 ``downgrade()`` bodies
    remain the correct place to remove these objects.
    """
    pass
