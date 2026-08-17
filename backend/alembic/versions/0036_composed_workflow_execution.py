"""0036 — composed workflow execution: saved-agent library, per-workflow
skills/hooks, and durable per-run gate selection.

MERGE NOTE (2026-08-17, dev -> feature/cognito-login). This revision was
authored as ``0031`` with ``down_revision = "0030"``, but the cognito-login side
had independently taken ``0031`` (``0031_cognito_identity_and_token_validity``)
off the same ``0030`` parent and continued through ``0032``-``0035``. Alembic
therefore reported "Revision 0031 is present more than once" and two heads.
Re-homed to ``0036`` on top of ``0035`` rather than reverting either side, which
restores a single linear head. Order-independent: the cognito chain touches only
``users`` / ``user_api_keys``, while this revision touches only ``workflows``,
the new ``user_agents`` table and ``workflow_runs`` — no overlap, so applying it
last is equivalent to applying it at 0031.

The single migration for the ``feat/composed-workflow-execution`` branch. It
supersedes three separate revisions that were consolidated before merge
(saved-workflow skills/hooks, the ``user_agents`` table, and the run-level gate
selection) so the branch adds exactly one link to the chain.

ADDITIVE ONLY. Two nullable columns on ``workflows``, two on nothing else, one
new table, one nullable column on ``workflow_runs``. No existing column, type or
constraint is altered, so every pre-existing row keeps its current behaviour.
Sequenced after 0035 (single-head chain) and reversible in full.

Contents
--------

1. ``workflows.attached_skills`` / ``workflows.attached_hooks`` (JSON, nullable)

   Mirrors the ``attached_skills``/``attached_hooks`` shape the launch path
   already uses (``list[dict] | None``, each dict carrying ``{id?, name,
   content?}`` for skills / ``{name, ...}`` for hooks — see the launch body in
   ``app/api/run_commands.py``). A saved workflow (``source="user"`` row) can now
   persist the skills/hooks it was created with, so reopening it round-trips the
   attachment instead of silently dropping it.

2. ``user_agents`` (new table)

   A ``custom-agent`` instance composed on the workflow canvas (spec 012) exists
   only inside that one workflow's manifest — its ``display_name``, ``prompt``
   and ``skills`` are per-step fields. This table lets a user keep one and drop
   it into a later workflow from their agent library.

   A NEW TABLE rather than more columns on ``workflows``: Phase 21 reused
   ``workflows`` for saved workflows because a saved workflow IS a workflow (same
   manifest shape, same launch path). A saved agent is not, and shares none of
   those columns — overloading the table would add a nullable-column cluster plus
   a discriminator to rows that never take the workflow code paths. See the model
   docstring in ``app/models/user_agent.py``. Carries ``owner_id``/``workspace_id``
   per the project rule that every new table does.

3. ``workflow_runs.gate_agent_ids_json`` (JSON, nullable)

   ``gate_agent_ids`` is the per-run selection of which agents pause for the Human
   review gate, overriding the static ``gate: Human_Gate`` declarations in
   AGENT.md. It is passed to ``execute()`` at launch and lived only in memory on
   the ``ExecutionContext``.

   The resume tier (``resume_run`` / ``_drive_resumed_stream``) rebuilds that
   context from the ``workflow_runs`` row, so anything not on the row is lost. The
   observable failure: launch a run with ``gate_agent_ids: ["writer"]`` (writer
   declares no static gate), let the backend restart while the run sits at the
   gate, submit ``redo`` with revision text — on resume ``_should_gate`` falls back
   to the static set, ``writer`` is not in it, the gate-reentry sentinel
   reconstructs the stale output but never re-opens the gate, and the pending redo
   plus the user's revision text are discarded silently. The run completes with
   the pre-revision content and nothing in the event stream says so.

   THREE-VALUED: NULL = use the static AGENT.md defaults; ``[]`` = no gates this
   run; a non-empty list = gate exactly these. JSON (not ARRAY) so NULL and ``[]``
   stay distinct. Written at run creation; read back by ``resume_run`` before
   calling ``_drive_resumed_stream``. Nullable → every legacy row stays NULL →
   ``gate_agent_ids=None`` on resume, the pre-fix behaviour (INV-3 byte/event
   parity). Mirrors 0027 exactly, including ``batch_alter_table`` for SQLite
   portability.
"""

from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # (1) Saved-workflow skills/hooks.
    with op.batch_alter_table("workflows") as b:
        b.add_column(sa.Column("attached_skills", sa.JSON(), nullable=True))
        b.add_column(sa.Column("attached_hooks", sa.JSON(), nullable=True))

    # (2) Saved custom agents.
    op.create_table(
        "user_agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # AUTHZ-01 — nullable to match the shape every other owned row uses;
        # the API stamps both to the creating user and the read filter keys on
        # user_id.
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        # list[str] of skill IDS — same shape as Step.skills, NOT the
        # {id,name,content} payload used by run-level attached_skills.
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # The owner-scoped list is the only hot read.
    op.create_index("ix_user_agents_user", "user_agents", ["user_id"])

    # (3) Durable per-run gate selection.
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("gate_agent_ids_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Reverse order of upgrade(). Each drop is guarded the way 0028/0029 are, so
    # a partially-applied upgrade still downgrades cleanly instead of raising
    # part-way and leaving the schema stranded (the failure mode 0024's unguarded
    # downgrade still exhibits — see tests/unit/test_alembic.py).
    _bind = op.get_bind()
    _tables = set(sa.inspect(_bind).get_table_names())

    if "workflow_runs" in _tables:
        _cols = {c["name"] for c in sa.inspect(_bind).get_columns("workflow_runs")}
        if "gate_agent_ids_json" in _cols:
            with op.batch_alter_table("workflow_runs") as b:
                b.drop_column("gate_agent_ids_json")

    if "user_agents" in _tables:
        op.drop_index("ix_user_agents_user", table_name="user_agents")
        op.drop_table("user_agents")

    if "workflows" in _tables:
        _cols = {c["name"] for c in sa.inspect(_bind).get_columns("workflows")}
        with op.batch_alter_table("workflows") as b:
            if "attached_hooks" in _cols:
                b.drop_column("attached_hooks")
            if "attached_skills" in _cols:
                b.drop_column("attached_skills")
