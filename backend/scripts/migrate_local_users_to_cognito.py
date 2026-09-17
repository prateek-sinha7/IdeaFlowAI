"""Link or invite local users onto Cognito ahead of migration 0038.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 1). Adapted from ``migrate_users_to_cognito.py`` (kept for historical
reference) per the brief: non-destructive by default, with
``--report``/``--link``/``--invite`` verbs instead of a single ``--apply``.

WHY THIS SCRIPT USES RAW SQL, NOT THE ``User`` MODEL
------------------------------------------------------
Migration 0038 drops ``users.password_hash``/``users.auth_provider`` and
makes ``cognito_sub`` NOT NULL — and 0038's own pre-flight check REFUSES to
run while any row has ``cognito_sub IS NULL``. So this script's job is to
run BEFORE 0038, against whichever pre-0038 schema shape a given
environment happens to have (some environments may already be past 0031,
which is where ``cognito_sub``/``auth_provider`` were added as nullable).
Because ``app/models/user.py`` has already been updated to the POST-0038
ORM shape (it is the target model for the code that ships alongside this
script), importing that model here would be wrong for the schema this
script actually needs to read. Raw SQL via a plain engine connection reads
whatever columns actually exist on `users` at run time, which is the only
way to be correct on both sides of 0038.

VERBS
-----
* ``--report`` (default, read-only): lists every ``users`` row with
  ``cognito_sub IS NULL``, plus (if the column still exists)
  ``auth_provider <> 'cognito'``. On a fresh database with no ``users`` table,
  reports that there is nothing to migrate and exits successfully.
* ``--link``: for each such row, looks up a pool user by email
  (``ListUsers`` filter) and, if found, writes its ``sub`` back onto
  ``cognito_sub``. Never creates a pool user.
* ``--invite``: for rows ``--link`` could not resolve, calls
  ``AdminCreateUser`` (invitation, temporary password — never a
  permanent one) plus the tier/admin group membership implied by the row's
  local ``tier``/``is_admin`` projection, then links the new ``sub``.

Both ``--link`` and ``--invite`` default to dry-run; pass ``--apply`` to
actually write. Never prints a password or any other secret — invitation
delivery is handled by Cognito's own ``DesiredDeliveryMediums=[EMAIL]``, not
by this script.

DEPLOY GATE (``--report --fail-on-unlinked``)
---------------------------------------------
``--report`` alone always exits 0, which makes it useless to a pipeline.
``--fail-on-unlinked`` makes it exit 1 when any row still needs attention,
while staying read-only. ``.github/scripts/remote-deploy.sh`` runs it in the
NEW backend image after ``docker compose pull`` and before ``up -d``: the
container entrypoint runs ``alembic upgrade head`` under ``set -eu``, so
without this gate an unlinked row turns into a backend that never binds its
port, a five-minute health-gate timeout and an image rollback, instead of a
fast failure that names the offending rows while the old stack keeps serving.
Running it from the new image (not the host) is deliberate: the image whose
migrations are about to run is the authority on what those migrations require.

USAGE (from backend/)
----------------------
    uv run python scripts/migrate_local_users_to_cognito.py --report
    uv run python scripts/migrate_local_users_to_cognito.py --report --fail-on-unlinked
    uv run python scripts/migrate_local_users_to_cognito.py --link --apply
    uv run python scripts/migrate_local_users_to_cognito.py --invite --apply
"""

from __future__ import annotations

import argparse
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

import sqlalchemy as sa  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from app.core import cognito  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.entitlements import ADMIN_GROUP, group_for_tier  # noqa: E402
from app.models.database import engine  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1


def _legacy_columns(conn) -> set[str]:
    inspector = sa.inspect(conn)
    return {c["name"] for c in inspector.get_columns("users")}


def _unlinked_rows(conn, columns: set[str]) -> list[dict]:
    """Rows needing attention: cognito_sub IS NULL, or (pre-0038 schema
    only) auth_provider <> 'cognito'."""
    select_cols = ["id", "email", "tier", "is_admin", "cognito_sub"]
    if "auth_provider" in columns:
        select_cols.append("auth_provider")

    where_clauses = ["cognito_sub IS NULL"]
    if "auth_provider" in columns:
        where_clauses.append("auth_provider <> 'cognito'")
    where_sql = " OR ".join(where_clauses)

    rows = conn.execute(
        sa.text(f"SELECT {', '.join(select_cols)} FROM users WHERE {where_sql}")
    ).mappings()
    return [dict(r) for r in rows]


def _write_link(row_id: str, sub: str, columns: set[str]) -> None:
    """Record a row as Cognito-linked.

    Writes ``auth_provider = 'cognito'`` alongside ``cognito_sub`` whenever the
    pre-0038 column still exists. Both fields are load-bearing: migration
    0038's pre-flight rejects a row that is not ``auth_provider='cognito'``
    just as firmly as one with a NULL ``cognito_sub``. Writing only the sub
    left a row that this script reported as still needing attention and that
    0038 still refused, with no verb able to resolve it.
    """
    assignments = ["cognito_sub = :sub"]
    if "auth_provider" in columns:
        assignments.append("auth_provider = 'cognito'")

    with engine.begin() as conn:
        conn.execute(
            sa.text(f"UPDATE users SET {', '.join(assignments)} WHERE id = :id"),
            {"sub": sub, "id": row_id},
        )


def _assert_pool_configured() -> str | None:
    missing = [
        name
        for name, value in (
            ("COGNITO_USER_POOL_ID", settings.COGNITO_USER_POOL_ID),
            ("COGNITO_CLIENT_ID", settings.COGNITO_CLIENT_ID),
            ("COGNITO_CLIENT_SECRET", settings.COGNITO_CLIENT_SECRET),
        )
        if not value
    ]
    if missing:
        return (
            f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} unset. "
            "Check /etc/velocityai/app.env / the SSM secrets-loader allowlist."
        )
    return None


def _find_pool_sub_by_email(email: str) -> str | None:
    """Look up an existing pool user's sub by email, or None if absent."""
    try:
        return cognito.admin_get_user_sub(email)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
            return None
        raise


def cmd_report(fail_on_unlinked: bool = False) -> int:
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        if "users" not in set(inspector.get_table_names()):
            print(
                "\nCognito link status — no users table yet. "
                "This is a fresh database; there are no local users to migrate.\n"
            )
            return EXIT_OK
        columns = _legacy_columns(conn)
        rows = _unlinked_rows(conn, columns)

    print(f"\nCognito link status — {len(rows)} row(s) need attention.\n")
    if not rows:
        print("Every local row already has a linked cognito_sub. Nothing to do.")
        return EXIT_OK

    for row in rows:
        extra = f" auth_provider={row['auth_provider']!r}" if "auth_provider" in row else ""
        print(
            f"  {row['id']}  {row['email']}  tier={row['tier']}  "
            f"is_admin={bool(row['is_admin'])}  cognito_sub={row['cognito_sub']!r}"
            f"{extra}"
        )

    print(
        "\nNext: --link (adopt an existing pool user by email) then --invite "
        "(create+invite anyone still unlinked)."
    )

    if fail_on_unlinked:
        print(
            f"\nFAIL: {len(rows)} row(s) are not cleanly Cognito-linked, so "
            "migration 0038 will refuse to apply. Resolve them with --link / "
            "--invite before deploying.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    return EXIT_OK


def cmd_link(apply: bool) -> int:
    config_error = _assert_pool_configured()
    if config_error:
        print(f"ERROR: {config_error}", file=sys.stderr)
        return EXIT_FAILED

    with engine.connect() as conn:
        columns = _legacy_columns(conn)
        rows = _unlinked_rows(conn, columns)

    if not rows:
        print("Nothing to link.")
        return EXIT_OK

    print(f"\nLink — {'APPLY' if apply else 'DRY RUN'}\n")
    linked = 0
    conflicts: list[tuple[str, str, str]] = []
    for row in rows:
        sub = _find_pool_sub_by_email(row["email"])
        if sub is None:
            print(f"  SKIP (not in pool):  {row['email']}")
            continue

        # Re-pointing an already-linked row at a DIFFERENT pool identity is an
        # account-takeover primitive, so it fails closed here exactly as
        # core/provisioning.py::_link_or_refuse does at runtime. Reached only
        # because a row can be listed for a non-'cognito' auth_provider while
        # already carrying a sub — resolving that must not silently rewrite
        # which principal the row belongs to.
        existing = row["cognito_sub"]
        if existing is not None and existing != sub:
            conflicts.append((row["email"], existing, sub))
            print(
                f"  REFUSED (sub mismatch): {row['email']} is linked to "
                f"{existing} but the pool returned {sub}",
                file=sys.stderr,
            )
            continue

        print(f"  LINK:                {row['email']} -> cognito_sub={sub}")
        if apply:
            _write_link(row["id"], sub, columns)
            linked += 1

    if not apply:
        print(f"\nDRY RUN — nothing written. {len(rows)} candidate row(s).")
    else:
        print(f"\nLinked {linked} row(s).")

    if conflicts:
        print(
            f"\n{len(conflicts)} row(s) REFUSED on a cognito_sub mismatch. Resolve "
            "each deliberately (see docs/runbooks/admin-recovery.md) — this script "
            "will not choose which principal owns the row.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    return EXIT_OK


def cmd_invite(apply: bool) -> int:
    config_error = _assert_pool_configured()
    if config_error:
        print(f"ERROR: {config_error}", file=sys.stderr)
        return EXIT_FAILED

    with engine.connect() as conn:
        columns = _legacy_columns(conn)
        rows = _unlinked_rows(conn, columns)

    still_unlinked = [r for r in rows if r["cognito_sub"] is None]
    if not still_unlinked:
        print("Nothing to invite — every row already has a cognito_sub. Run --link first?")
        return EXIT_OK

    print(f"\nInvite — {'APPLY' if apply else 'DRY RUN'}\n")
    invited = 0
    failures: list[tuple[str, str]] = []
    for row in still_unlinked:
        existing_sub = _find_pool_sub_by_email(row["email"])
        if existing_sub is not None:
            print(
                f"  SKIP (already in pool, run --link instead): {row['email']} "
                f"sub={existing_sub}"
            )
            continue

        groups = [group_for_tier(row["tier"])]
        if row["is_admin"]:
            groups.append(ADMIN_GROUP)
        print(f"  INVITE:              {row['email']} -> groups={'+'.join(groups)}")

        if not apply:
            continue

        try:
            resp = cognito.admin_create_user(
                row["email"], desired_delivery_mediums=["EMAIL"]
            )
            sub = next(
                attr["Value"]
                for attr in resp["User"]["Attributes"]
                if attr["Name"] == "sub"
            )
            for group in groups:
                cognito.admin_add_user_to_group(row["email"], group)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            failures.append((row["email"], f"Cognito {code}"))
            print(f"  FAILED  {row['email']}: Cognito {code}", file=sys.stderr)
            continue

        _write_link(row["id"], sub, columns)
        invited += 1
        print(f"  OK      {row['email']} -> cognito_sub={sub} (invitation sent)")

    if not apply:
        print(f"\nDRY RUN — nothing written. {len(still_unlinked)} candidate row(s).")
    else:
        print(f"\nInvited {invited}/{len(still_unlinked)} row(s).")
        if failures:
            print(f"\n{len(failures)} FAILURE(S):", file=sys.stderr)
            for email, reason in failures:
                print(f"  {email}: {reason}", file=sys.stderr)
            return EXIT_FAILED
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/migrate_local_users_to_cognito.py",
        description=(
            "Link or invite local users onto Cognito ahead of migration 0038. "
            "Non-destructive by default (--report); pass --apply with --link "
            "or --invite to actually write."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--report", action="store_true", help="list rows needing attention (default)"
    )
    group.add_argument(
        "--link",
        action="store_true",
        help="adopt an existing pool user's sub by email match",
    )
    group.add_argument(
        "--invite",
        action="store_true",
        help="AdminCreateUser + group membership for rows --link could not resolve",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write (default: dry run, prints the plan only)",
    )
    parser.add_argument(
        "--fail-on-unlinked",
        action="store_true",
        help=(
            "with --report: exit non-zero when any row still needs attention, "
            "so a deploy/CI step can gate on it (read-only either way)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.link:
        return cmd_link(apply=args.apply)
    if args.invite:
        return cmd_invite(apply=args.apply)
    return cmd_report(fail_on_unlinked=args.fail_on_unlinked)


if __name__ == "__main__":
    raise SystemExit(main())
