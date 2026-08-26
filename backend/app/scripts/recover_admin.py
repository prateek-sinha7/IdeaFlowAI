"""Create-or-reset an administrator account. The way back in when nobody has host access.

WHY THIS EXISTS
---------------
``app/scripts/bootstrap_admin.py`` deliberately refuses to act unless the users
table is COMPLETELY EMPTY ("users table has any row -> do nothing,
successfully"). That invariant is correct — it stops an unattended deploy from
silently re-opening bootstrap or promoting an existing account — but it leaves a
real gap:

    an environment that HAS users, none of whose passwords anyone knows,
    is unreachable, and changing BOOTSTRAP_ADMIN_PASSWORD does not help
    because the deploy's --check-only gate skips bootstrap entirely.

That is a recovery scenario, and the bootstrap docstring says outright it
"belongs in an audited break-glass procedure". This is that procedure.

WHAT IT DOES, IDEMPOTENTLY
--------------------------
For one email address:

* creates the account if it does not exist, or RESETS its password if it does;
* promotes it to admin and gives it the ``enterprise`` tier;
* on ``AUTH_PROVIDER=cognito``, provisions/adopts the pool user, sets a
  PERMANENT password (no NEW_PASSWORD_REQUIRED challenge — a recovery
  credential must work on the first try) and adds BOTH the tier group and
  ``flowin-admins``, because ``effective_tier``/``effective_is_admin`` read
  ``cognito:groups`` and ignore the local columns entirely;
* on local auth, writes a bcrypt hash the normal way;
* stamps ``tokens_valid_from`` so every previously-issued token for the account
  is rejected (plan §5.3) — a recovery must not leave older sessions valid.

It NEVER deletes a user. Nothing here touches workflow runs, artifacts, chat
sessions, or any other row: ~9 tables carry a non-nullable FK to ``users.id``
with no cascade, so deleting users to "start clean" would either fail on those
constraints or take real data with it. Resetting a password achieves the same
access with none of that risk.

THE BREAK-GLASS INVARIANT — WHY A SUCCESSFUL LOGIN CAN STILL 401
----------------------------------------------------------------
``core/identity.py::_local_admin_credential_is_permitted`` fails CLOSED unless
exactly ONE ``auth_provider='local'`` admin exists. Note the asymmetry:
``POST /api/auth/login`` does NOT consult it, but ``resolve_principal`` — which
runs on every authenticated request — does. So with two or more local admins you
get a login that returns a token, followed by a 401 on the very next call, and
``break_glass_invariant_violated`` in the log. Resetting a password does not fix
that on its own.

``--demote-other-local-admins`` restores the invariant by clearing ``is_admin``
on every OTHER local admin (a privilege REDUCTION, never an escalation; the
accounts keep working as non-admins). ``--report`` tells you whether you need it.

SECRET HANDLING
---------------
The password arrives on stdin and nowhere else — not argv (visible in ``ps``),
not an environment variable (visible in ``docker inspect``, inherited by every
subprocess). Same doctrine as ``bootstrap_admin.py``. Nothing here logs, echoes,
or includes a password in an error message.

USAGE (inside the backend container — mirrors app/scripts/bootstrap_admin.py)
-------------------------------------------------------------------------------
    # Read-only: what state is this environment actually in?
    python -m app.scripts.recover_admin --report

    # Reset/create, password on stdin:
    printf '%s' "$PW" | python -m app.scripts.recover_admin \
        --email admin@example.com --password-stdin

    # ...and restore the single-local-admin invariant at the same time:
    printf '%s' "$PW" | python -m app.scripts.recover_admin \
        --email admin@example.com --password-stdin --demote-other-local-admins

Exit codes: 0 success, 1 failure.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import func

from app.core.config import settings
from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.core.security import hash_password
from app.models.database import SessionLocal
from app.models.user import User

EXIT_OK = 0
EXIT_FAILED = 1

# Matches bootstrap_admin.INITIAL_ADMIN_TIER: a recovered operator needs the
# full entitlement set, and `tier` is a free-form string on the model.
RECOVERY_TIER = "enterprise"

# The pool policy floor (12) is the binding constraint when Cognito is active;
# bootstrap_admin uses 16 for a pipeline-minted credential. Take the stricter of
# the two only when it costs nothing: this value is typed by a human at most
# once, so 12 is the floor we enforce and anything longer is welcome.
MIN_PASSWORD_LENGTH = 12


def _normalise_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalised = value.strip().lower()
    if not normalised:
        return None
    local, _, domain = normalised.partition("@")
    if not local or not domain or "." not in domain:
        return None
    return normalised


def _read_password_from_stdin() -> str | None:
    """One line from stdin; only the trailing newline is stripped.

    A bare ``rstrip()`` would eat meaningful trailing whitespace from a
    generated password, setting a credential the operator cannot reproduce.
    """
    line = sys.stdin.readline()
    if not line:
        print("ERROR: no password received on stdin", file=sys.stderr)
        return None
    return line.removesuffix("\n").removesuffix("\r")


def _cognito_active() -> bool:
    return settings.AUTH_PROVIDER.lower() == "cognito"


def report() -> int:
    """Print the environment's auth state. Read-only — writes nothing."""
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.email).all()
        local_admins = [
            u for u in users if u.auth_provider == "local" and bool(u.is_admin)
        ]

        print("\n=== auth configuration ===")
        print(f"  AUTH_PROVIDER          = {settings.AUTH_PROVIDER}")
        print(f"  AUTH_ALLOW_LEGACY_JWT  = {settings.AUTH_ALLOW_LEGACY_JWT}")
        print(f"  BREAK_GLASS_ENABLED    = {settings.BREAK_GLASS_ENABLED}")
        print(f"  ADMIN_MFA_REQUIRED     = {settings.ADMIN_MFA_REQUIRED}")
        print(f"  COGNITO_USER_POOL_ID   = {settings.COGNITO_USER_POOL_ID or '(unset)'}")
        print(f"  COGNITO_CLIENT_ID      = {'set' if settings.COGNITO_CLIENT_ID else '(unset)'}")
        print(f"  COGNITO_CLIENT_SECRET  = {'set' if settings.COGNITO_CLIENT_SECRET else '(unset)'}")

        print(f"\n=== users ({len(users)}) ===")
        if not users:
            print("  (none — bootstrap_admin WILL run on the next deploy)")
        else:
            print(f"  {'email':<38} {'provider':<9} {'pw_hash':<8} {'tier':<11} admin")
            for u in users:
                print(
                    f"  {u.email:<38} {u.auth_provider:<9} "
                    f"{('set' if u.password_hash else 'NULL'):<8} "
                    f"{u.tier:<11} {bool(u.is_admin)}"
                )

        print("\n=== diagnosis ===")
        if users:
            print(
                "  bootstrap_admin will NOT run (its invariant is 'any row -> do "
                "nothing'), so changing BOOTSTRAP_ADMIN_PASSWORD has no effect on "
                "these accounts. Use --email/--password-stdin below."
            )

        count = len(local_admins)
        if count == 1:
            print(f"  break-glass invariant OK: exactly 1 local admin ({local_admins[0].email})")
        elif count == 0:
            print(
                "  break-glass invariant VIOLATED: 0 local admins. No local recovery "
                "path exists if Cognito is unreachable (check C2)."
            )
        else:
            print(
                f"  break-glass invariant VIOLATED: {count} local admins "
                f"({', '.join(u.email for u in local_admins)}).\n"
                f"  Every local-admin credential is being REJECTED by "
                f"resolve_principal — a login can succeed and then 401 on the next\n"
                f"  request. Pass --demote-other-local-admins to restore it."
            )

        if _cognito_active():
            orphans = [
                u for u in users if u.auth_provider == "cognito" and not u.cognito_sub
            ]
            if orphans:
                print(
                    f"  {len(orphans)} cognito row(s) with NULL cognito_sub — these can "
                    f"NEVER log in (check C1): {', '.join(u.email for u in orphans)}"
                )
        else:
            print(
                f"  AUTH_PROVIDER is '{settings.AUTH_PROVIDER}', so login uses the LOCAL "
                f"bcrypt path for rows whose auth_provider is 'local'."
            )
        print("")
        return EXIT_OK
    finally:
        db.close()


def _provision_cognito(email: str, password: str) -> str:
    """Create-or-adopt the pool user, set a permanent password, set groups.

    Returns the pool ``sub``. Adopting an existing pool user is the normal
    recovery path (the account usually already exists), so
    ``UsernameExistsException`` is success, not failure.
    """
    from botocore.exceptions import ClientError

    from app.core import cognito

    try:
        resp = cognito.admin_create_user(email)
        sub = next(
            attr["Value"]
            for attr in resp["User"]["Attributes"]
            if attr["Name"] == "sub"
        )
        print(f"  created pool user {email}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "UsernameExistsException":
            raise
        sub = cognito.admin_get_user_sub(email)
        print(f"  adopted existing pool user {email}")

    # Permanent, so the recovery credential works on the first login with no
    # interactive challenge step.
    cognito.admin_set_user_password(email, password, permanent=True)
    # BOTH groups: on the Cognito path the group claim is the sole authority for
    # tier and admin. A pool user with only flowin-admins resolves to the
    # DEFAULT_TIER regardless of users.tier.
    cognito.admin_add_user_to_group(email, group_for_tier(RECOVERY_TIER))
    cognito.admin_add_user_to_group(email, ADMIN_GROUP)
    print(f"  set permanent password + groups "
          f"({group_for_tier(RECOVERY_TIER)}, {ADMIN_GROUP})")
    return sub


def recover(
    email: str,
    password: str,
    demote_other_local_admins: bool,
) -> int:
    cognito_active = _cognito_active()

    if cognito_active:
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
            print(
                f"ERROR: AUTH_PROVIDER=cognito but {', '.join(missing)} unset. "
                f"The Cognito SSM parameters may be missing from the on-host "
                f"secrets-loader allowlist — check /etc/velocityai/app.env.",
                file=sys.stderr,
            )
            return EXIT_FAILED

    db = SessionLocal()
    try:
        # ``.first()``, not ``.one()``: a case-duplicate address (e.g.
        # "Admin@x.com" and "admin@x.com" as two distinct rows — seen on dev,
        # both auth_provider='local' admins) means more than one row can match
        # this filter. Deliberately picks one deterministically and proceeds;
        # see the demote step below for why the OTHER one is not silently
        # skipped.
        matches = (
            db.query(User)
            .filter(func.lower(User.email) == email)
            .order_by(User.id)
            .all()
        )
        user = matches[0] if matches else None
        now = datetime.now(timezone.utc)

        print(f"\nRecovering administrator: {email}")
        print(f"  AUTH_PROVIDER = {settings.AUTH_PROVIDER}")

        cognito_sub: str | None = None
        if cognito_active:
            cognito_sub = _provision_cognito(email, password)

        if user is None:
            user = User(
                email=email,
                password_hash=None if cognito_active else hash_password(password),
                cognito_sub=cognito_sub,
                auth_provider="cognito" if cognito_active else "local",
                tier=RECOVERY_TIER,
                is_admin=True,
                password_changed_at=now,
                tokens_valid_from=now,
                roles_synced_at=now if cognito_active else None,
            )
            db.add(user)
            action = "CREATED"
        else:
            if cognito_active:
                user.cognito_sub = cognito_sub
                user.auth_provider = "cognito"
                # Required by check C3 — a retained hash is a second credential
                # outside the pool's policy/lockout/MFA.
                user.password_hash = None
                user.roles_synced_at = now
            else:
                user.auth_provider = "local"
                user.password_hash = hash_password(password)
            user.is_admin = True
            user.tier = RECOVERY_TIER
            user.password_changed_at = now
            # Invalidate every token minted before this reset (plan §5.3).
            user.tokens_valid_from = now
            action = "RESET"

        demoted: list[str] = []
        if demote_other_local_admins:
            # Excluded by row IDENTITY (user.id), not by re-matching the email.
            # A case-duplicate address (two distinct rows whose emails are
            # equal only under lower()) would otherwise be excluded from BOTH
            # the "target" and the "others" set — neither reset nor demoted —
            # leaving the invariant silently unrestored. Confirmed on dev:
            # GajeraSharadN@hexaware.com survived a --demote-other-local-admins
            # run as a second local admin because the old filter compared
            # lower(email) instead of id.
            others = (
                db.query(User)
                .filter(
                    User.auth_provider == "local",
                    User.is_admin.is_(True),
                    User.id != user.id,
                )
                .all()
            )
            for other in others:
                other.is_admin = False
                # Their outstanding tokens carried is_admin; force re-auth so the
                # demotion takes effect immediately rather than at expiry.
                other.tokens_valid_from = now
                demoted.append(other.email)

        db.commit()

        print(f"  {action}: {email} (tier={RECOVERY_TIER}, admin=True)")
        if demoted:
            print(
                f"  demoted {len(demoted)} other local admin(s) to non-admin: "
                f"{', '.join(demoted)}"
            )

        if len(matches) > 1:
            duplicate_ids = ", ".join(m.id for m in matches[1:])
            print(
                f"  NOTE: {len(matches)} rows share the address {email!r} case-"
                f"insensitively (ids: {user.id} [reset], {duplicate_ids} [untouched "
                f"other than any demotion above]). This script never merges or "
                f"deletes rows — decide by hand which one is canonical.",
                file=sys.stderr,
            )

        # Re-read the invariant AFTER committing, so what we report is the state
        # the running app will actually observe on the next request.
        local_admin_count = (
            db.query(func.count(User.id))
            .filter(User.auth_provider == "local", User.is_admin.is_(True))
            .scalar()
            or 0
        )
        print(f"\n  local admin count = {local_admin_count}")
        if not cognito_active and local_admin_count != 1:
            print(
                f"  WARNING: resolve_principal fails CLOSED unless exactly 1 local "
                f"admin exists. With {local_admin_count}, this account will log in "
                f"and then 401 on the next request.\n"
                f"  Re-run with --demote-other-local-admins.",
                file=sys.stderr,
            )
            return EXIT_FAILED

        print(f"\nDone. Log in at the app with {email} and the password supplied.")
        if cognito_active:
            print("  (Cognito path: permanent password, no challenge expected.)")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - process boundary
        db.rollback()
        # The message carries the email at most, never the password.
        print(f"ERROR: recovery failed for {email}: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/recover_admin.py",
        description=(
            "Create or reset an administrator account. Never deletes a user. "
            "With no --email, prints a read-only report."
        ),
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print the auth-state report and exit (read-only; the default with no --email)",
    )
    parser.add_argument("--email", help="the administrator address to create or reset")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin (required with --email)",
    )
    parser.add_argument(
        "--demote-other-local-admins",
        action="store_true",
        help=(
            "clear is_admin on every OTHER local admin, restoring the "
            "single-local-admin invariant that resolve_principal enforces"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.report or not args.email:
        if args.email:
            print("ERROR: --report cannot be combined with --email", file=sys.stderr)
            return EXIT_FAILED
        return report()

    email = _normalise_email(args.email)
    if email is None:
        print("ERROR: invalid email address", file=sys.stderr)
        return EXIT_FAILED

    if not args.password_stdin:
        print(
            "ERROR: --password-stdin is required with --email (a password must "
            "not be passed as an argument)",
            file=sys.stderr,
        )
        return EXIT_FAILED

    password = _read_password_from_stdin()
    if password is None:
        return EXIT_FAILED
    if len(password) < MIN_PASSWORD_LENGTH:
        # Length is reported; the value never is.
        print(
            f"ERROR: password must be at least {MIN_PASSWORD_LENGTH} characters",
            file=sys.stderr,
        )
        return EXIT_FAILED

    return recover(email, password, args.demote_other_local_admins)


if __name__ == "__main__":
    raise SystemExit(main())
