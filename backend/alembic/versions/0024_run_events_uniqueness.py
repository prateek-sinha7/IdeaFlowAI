"""0024 — additive per-run uniqueness backstops on run_events (Phase 29, CR-03).

Phase 29 adds a SECOND, concurrently-scheduled ``run_events`` writer per ``run_id``
— the chat up-channel (``chat_message``, ``POST /api/runs/{id}/messages``) and the
milestone narrator (``chat_reply``) — alongside the engine's own event sink. Both
allocate ``seq`` as read-``max(seq)+1``-then-write with no lock/constraint. That
races the engine sink (which stamps ``seq`` from its own in-memory counter) and, on
a double-submitted ``message_id``, itself:

  * two writers can compute the SAME ``seq`` before either commits → a duplicate
    ``(run_id, seq)`` silently lands, breaking the Last-Event-ID replay contract
    (``run_stream.py`` filters ``seq > after_seq`` — a shared seq permanently drops
    one row on any future reconnect past that cursor), and
  * a retried ``message_id`` can race past the "already exists" check twice → two
    ``chat_message`` rows for what D-01 promises is idempotent.

This adds two UNIQUE constraints so a racing insert fails LOUDLY (IntegrityError)
instead of silently succeeding twice; ``ScopedStore.append_event_next_seq`` catches
that and retries the seq / resolves the idempotent no-op:

  * ``uq_run_events_scope_event`` (run_id, owner_id, workspace_id, event_id)
    — idempotency backstop.
  * ``uq_run_events_scope_seq``   (run_id, owner_id, workspace_id, seq)
    — monotonic-seq backstop.

SCOPE = (run_id, owner_id, workspace_id): ``seq``/``event_id`` are unique WITHIN the
owner+workspace scope, mirroring ``ScopedStore.read_events`` (which filters owner_id +
workspace_id). A cross-owner store's default-deny read sees an empty tail and restarts
its own seq at 1 under its OWN principal (T-29-10-1) — a different scope, not a
collision — so the constraint must not span owners. The CR-03 race is between the run's
OWN engine sink and its OWN chat endpoint (identical owner+workspace) — caught here.

ADDITIVE ONLY (Q3, INV-3): no new table, no column alter. Within a scope the engine
sink is the sole writer of any given ``seq`` today (fresh runs use itertools.count;
resume seeds ``max(seq)+1``) and ``event_id`` is a per-run-unique uuid, so no existing
correct run holds a duplicate — the constraints add cleanly. The existing non-unique
``ix_run_events_run_seq`` index is LEFT in place (additive-only — never dropped).
Sequenced after 0023 (``down_revision="0023"``) — single-head chain. ``downgrade()``
drops both constraints inside a ``batch_alter_table`` (reversible, SQLite-portable via
the 0017/0021/0022/0023 batch idiom).
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("run_events") as b:
        b.create_unique_constraint(
            "uq_run_events_scope_event",
            ["run_id", "owner_id", "workspace_id", "event_id"],
        )
        b.create_unique_constraint(
            "uq_run_events_scope_seq",
            ["run_id", "owner_id", "workspace_id", "seq"],
        )


def downgrade() -> None:
    with op.batch_alter_table("run_events") as b:
        b.drop_constraint("uq_run_events_scope_seq", type_="unique")
        b.drop_constraint("uq_run_events_scope_event", type_="unique")
