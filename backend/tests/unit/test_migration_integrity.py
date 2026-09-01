"""Migration-chain integrity guards (no database required).

These tests cover three failure modes that Alembic itself cannot detect, all of
which have either already happened in this project or are one merge away.

1. RETROACTIVE EDIT OF A RELEASED REVISION.
   ``alembic_version`` stores a revision ID, never a content hash. Editing a
   revision that a database has already applied means the edit is never executed
   there — ``upgrade head`` sees the stamped ID and exits 0 — while any database
   built after the edit picks it up. The two diverge silently and permanently.
   Idempotent DDL does not help: the code never runs.

2. DUPLICATE REVISION IDS. Two branches taking the same number makes Alembic
   keep one file, drop the other from the graph, and report multiple heads. This
   project hit it twice (0031 re-homed to 0036, 0032 re-homed to 0037).

3. MULTIPLE HEADS. ``alembic upgrade head`` then fails outright, and because
   ``docker-entrypoint.sh`` runs it under ``set -eu`` before ``exec uvicorn``,
   the container crash-loops rather than reporting a failed deploy step.

The single-head assertion previously existed only incidentally, as a trailing
line inside two tests named after unrelated revisions (0016 and 0023) in
``test_migrations.py``. It is promoted here so it cannot be lost to a refactor
of either.

The real enforcement lives in ``scripts/migration_guard.py`` so it is runnable
as a standalone pre-merge check; this module imports it rather than
reimplementing the logic, so the CI step and the test can never disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ is not a package and is not on sys.path under pytest's rootdir
# (backend/), so make the guard importable the same way alembic/env.py makes the
# backend root importable.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import migration_guard  # noqa: E402  (deliberate post-sys.path import)


class TestMigrationChainIntegrity:
    def test_no_duplicate_revision_ids(self) -> None:
        """Scanning must not raise — ``scan_versions`` fails on a duplicate ID."""
        revisions = migration_guard.scan_versions()
        assert revisions, "no revision files discovered — check versions/ path"

    def test_exactly_one_head(self) -> None:
        """The chain must converge on a single head.

        Two heads mean ``alembic upgrade head`` raises "Multiple head revisions
        are present" and the backend container crash-loops on boot.
        """
        assert migration_guard.cmd_check_heads() == 0, (
            "migration chain does not have exactly one head — see captured "
            "stderr for the head list and the re-homing rule"
        )

    def test_released_revisions_are_unmodified(self) -> None:
        """No released revision's logic may change, and new ones must be pinned.

        Failure means one of two things, both actionable:

        * a released migration was edited — revert it and add a forward repair
          revision instead (revision 0028 is the worked example), or
        * a new migration was added without updating the lock — run
          ``uv run python scripts/migration_guard.py --update`` and commit
          ``alembic/versions.lock`` alongside the migration.
        """
        current = migration_guard.scan_versions()
        pinned = migration_guard.load_lock()

        assert pinned, (
            "alembic/versions.lock is missing or empty. Create the baseline: "
            "uv run python scripts/migration_guard.py --update"
        )

        modified = sorted(
            rev
            for rev, entry in current.items()
            if rev in pinned and entry["logic_sha256"] != pinned[rev]["logic_sha256"]
        )
        assert not modified, (
            f"released migration(s) {modified} were edited. Alembic records only "
            "revision IDs, so this edit can NEVER reach a database already "
            "stamped at or past them — fresh databases would get the new "
            "behaviour and existing ones would not. Revert, and add a new "
            "revision at the tip guarded with migration_helpers."
        )

        removed = sorted(set(pinned) - set(current))
        assert not removed, (
            f"released migration(s) {removed} were deleted. Every database that "
            'recorded those IDs will fail with "Can\'t locate revision" on the '
            "next upgrade."
        )

        unpinned = sorted(set(current) - set(pinned))
        assert not unpinned, (
            f"new migration(s) {unpinned} are not pinned in versions.lock. Run "
            "`uv run python scripts/migration_guard.py --update` and commit the "
            "lock file in the same change, or the guard silently stops covering "
            "them."
        )


class TestFingerprintSemantics:
    """The fingerprint must track behaviour, not formatting.

    If it tripped on comments and whitespace, the override path would be used
    routinely and would stop being a signal — so these properties are load
    bearing for the guard being trusted rather than bypassed.
    """

    def test_docstring_and_comment_changes_do_not_change_fingerprint(self) -> None:
        before = migration_guard.logic_fingerprint(
            '"""Original docstring."""\n'
            "def upgrade():\n"
            "    # add the column\n"
            "    op.add_column('t', c)\n"
        )
        after = migration_guard.logic_fingerprint(
            '"""Rewritten docstring with much more detail."""\n'
            "def upgrade():\n"
            "    # a totally different comment\n"
            "    op.add_column('t', c)\n"
        )
        assert before == after, (
            "documentation edits must not trip the guard, or reviewers will "
            "reach for --allow-modified as a matter of routine"
        )

    def test_formatting_changes_do_not_change_fingerprint(self) -> None:
        assert migration_guard.logic_fingerprint(
            "def upgrade():\n    op.add_column('t',   c)\n"
        ) == migration_guard.logic_fingerprint(
            'def upgrade():\n    op.add_column("t", c)\n'
        )

    def test_logic_change_does_change_fingerprint(self) -> None:
        """The case that matters: a real DDL change must be detected."""
        nullable = migration_guard.logic_fingerprint(
            "def upgrade():\n"
            "    op.add_column('users', sa.Column('x', sa.Text(), nullable=True))\n"
        )
        not_nullable = migration_guard.logic_fingerprint(
            "def upgrade():\n"
            "    op.add_column('users', sa.Column('x', sa.Text(), nullable=False))\n"
        )
        assert nullable != not_nullable

    def test_docstring_only_function_body_stays_parseable(self) -> None:
        """Stripping the docstring from a docstring-only body must not break unparse.

        ``def downgrade(): '''no-op'''`` is a real shape in this repo (revision
        0028's downgrade), so the stripper has to substitute ``pass`` rather than
        leave an empty body that ``ast.unparse`` rejects.
        """
        digest = migration_guard.logic_fingerprint(
            'def downgrade():\n    """Intentionally a no-op."""\n'
        )
        assert len(digest) == 64

    def test_unparseable_revision_is_rejected(self) -> None:
        with pytest.raises(SyntaxError):
            migration_guard.logic_fingerprint("def upgrade(:\n  pass\n")
