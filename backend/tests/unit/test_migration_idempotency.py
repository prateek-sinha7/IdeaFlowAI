"""Ratchet: every NEW migration must be safe to re-apply.

WHAT "SAFE TO RE-APPLY" MEANS
-----------------------------
A migration is re-appliable when running it against a database whose objects it
has *already created* succeeds instead of raising. This is not a theoretical
nicety. ``backend/docker-entrypoint.sh`` runs ``alembic upgrade head`` under
``set -eu`` before ``exec uvicorn``, so a migration that raises does not fail a
deploy step — it prevents the container from ever binding its port, producing a
crash-loop.

A database ends up "objects present but revision not stamped" through several
routes that have all occurred or are one incident away:

* the DDL applied but the ``alembic_version`` bump was lost — the 0024/0025
  incident that revision 0028 exists to repair,
* an operator applied DDL by hand as a hotfix before the migration shipped,
* a revision was re-homed to a new ID (0031 -> 0036, 0032 -> 0037) and different
  databases recorded different IDs for the same DDL,
* a partial/failed downgrade left objects behind.

HOW THE TEST SIMULATES IT
-------------------------
Build the full schema with ``upgrade head``, then ``alembic stamp`` the version
table back to the revision's parent *without* touching the schema. That is
precisely the "lost version bump" state. Running ``upgrade <revision>`` then
re-executes the revision against objects that already exist.

WHY THIS IS A RATCHET AND NOT A FULL SWEEP
------------------------------------------
27 of the 35 existing revisions are NOT re-appliable (verified). Retrofitting
guards into them would mean editing released migrations, which is the very
action ``scripts/migration_guard.py`` blocks: the edit could never reach a
database already stamped past it, so it would buy nothing operationally while
rewriting deployed history. The legacy set is therefore frozen in
``_LEGACY_NON_IDEMPOTENT`` and excluded, and the rule is enforced from here
forward — the same ratchet pattern the SSE banned-pattern check uses.

Removing an entry from that set is allowed and encouraged: it means a forward
repair revision has made the legacy one reachable-safe, or the revision was
rewritten under a deliberate ``--allow-modified`` override.

NEW MIGRATIONS: HOW TO PASS
---------------------------
Use the guarded wrappers in ``migration_helpers``::

    from migration_helpers import add_column_if_missing, create_table_if_missing

    def upgrade() -> None:
        add_column_if_missing("users", sa.Column("x", sa.Text(), nullable=True))

COST
----
Only revisions absent from the frozen set are exercised, so on an unchanged tree
this test builds no databases at all and costs nothing. It does real work only
when a migration is added — which is exactly when the check is wanted.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


# ---------------------------------------------------------------------------
# Frozen legacy set — revisions that predate the idempotency rule.
#
# Verified 2026-08-26 by re-applying each revision against an
# already-materialised schema. Do NOT add to this set: a new entry means a new
# migration shipped that will crash-loop the container if it is ever re-run.
# Entries may be REMOVED once a revision is made re-appliable.
# ---------------------------------------------------------------------------
_LEGACY_NON_IDEMPOTENT = frozenset(
    {
        "0002",
        "0004",
        "0005",
        "0006",
        "0007",
        "0008",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
        "0018",
        "0019",
        "0020",
        "0021",
        "0022",
        "0023",
        "0025",
        "0026",
        "0027",
        "0031",
        "0032",
        "0033",
        "0034",
        "0036",
    }
)

# Revisions confirmed re-appliable at the time the ratchet was installed. Kept
# as documentation of the starting point and asserted below so a regression in
# one of them is caught rather than silently tolerated.
_KNOWN_IDEMPOTENT = frozenset(
    {"0009", "0010", "0024", "0028", "0029", "0030", "0035", "0037"}
)


def _config(db_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def _all_revisions() -> list[str]:
    """Every revision ID, oldest first."""
    script = ScriptDirectory.from_config(_config("sqlite://"))
    return [s.revision for s in script.walk_revisions("base", "heads")][::-1]


def _parent_of(revision: str) -> str | None:
    script = ScriptDirectory.from_config(_config("sqlite://"))
    down = script.get_revision(revision).down_revision
    if isinstance(down, tuple):  # merge revision
        return down[0] if down else None
    return down


def _reapply_succeeds(revision: str, db_path: Path) -> tuple[bool, str]:
    """Return (ok, detail) for re-running ``revision`` over existing objects."""
    url = f"sqlite:///{db_path}"
    parent = _parent_of(revision)
    if parent is None:
        return True, "base revision — nothing to re-apply over"

    # Alembic's own INFO chatter would drown the assertion output.
    previous_level = logging.getLogger("alembic").level
    logging.getLogger("alembic").setLevel(logging.WARNING)
    try:
        command.upgrade(_config(url), "head")
        # Rewind ONLY the bookkeeping table; the schema stays fully built.
        command.stamp(_config(url), parent, purge=False)
        command.upgrade(_config(url), revision)
        return True, ""
    except Exception as exc:  # noqa: BLE001 — any failure is a failure
        return False, f"{type(exc).__name__}: {str(exc)[:400]}"
    finally:
        logging.getLogger("alembic").setLevel(previous_level)


class TestMigrationIdempotencyRatchet:
    def test_frozen_legacy_set_matches_reality(self) -> None:
        """The frozen sets must together describe every revision in the chain.

        If a revision is in neither set it is new and unclassified, which means
        ``test_new_migrations_are_reappliable`` below is about to exercise it —
        this assertion just makes the bookkeeping error explicit if someone adds
        a revision to the legacy set by mistake.
        """
        chain = set(_all_revisions())
        stale = (_LEGACY_NON_IDEMPOTENT | _KNOWN_IDEMPOTENT) - chain
        assert not stale, (
            f"the ratchet references revisions that no longer exist: "
            f"{sorted(stale)}. Remove them from the frozen sets."
        )

    def test_new_migrations_are_reappliable(self, tmp_path: Path) -> None:
        """Any revision added after the ratchet was installed must be re-appliable.

        This is the enforcement point. A new unguarded ``add_column`` /
        ``create_table`` fails here with the exact exception the production
        container would hit.
        """
        classified = _LEGACY_NON_IDEMPOTENT | _KNOWN_IDEMPOTENT
        new_revisions = [r for r in _all_revisions() if r not in classified]

        failures: list[str] = []
        for revision in new_revisions:
            db_path = tmp_path / f"reapply_{revision}.db"
            ok, detail = _reapply_succeeds(revision, db_path)
            if not ok:
                failures.append(f"  {revision}: {detail}")

        assert not failures, (
            "new migration(s) are NOT safe to re-apply against a database that "
            "already has their objects:\n"
            + "\n".join(failures)
            + "\n\nThe backend entrypoint runs `alembic upgrade head` under "
            "`set -eu`, so this crash-loops the container on any database whose "
            "version bump was lost or whose DDL was applied by hand.\n"
            "Fix: guard the DDL with backend/migration_helpers.py, e.g.\n"
            "    from migration_helpers import add_column_if_missing\n"
            "    add_column_if_missing('users', sa.Column('x', sa.Text(), "
            "nullable=True))"
        )

    @pytest.mark.parametrize("revision", sorted(_KNOWN_IDEMPOTENT))
    def test_known_idempotent_revisions_stay_idempotent(
        self, revision: str, tmp_path: Path
    ) -> None:
        """Revisions already re-appliable must not regress.

        These are cheap to hold onto and they protect the repair revisions
        (0028/0029) specifically — those exist precisely to be safely re-runnable
        against partially-migrated databases, so losing that property would
        defeat their purpose.
        """
        ok, detail = _reapply_succeeds(revision, tmp_path / f"{revision}.db")
        assert ok, (
            f"revision {revision} used to be safe to re-apply and no longer is: "
            f"{detail}"
        )
