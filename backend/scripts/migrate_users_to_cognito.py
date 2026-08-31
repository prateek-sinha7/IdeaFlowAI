"""One-shot bulk migration of local (password_hash) users onto Cognito.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 5, ``infra/COGNITO-CUTOVER-RUNBOOK.md``
steps 5-7). The plan deliberately shipped NO bulk migration tool, because
Decision 5 assumed a greenfield production database — "a provisioning exercise
rather than a migration campaign". This script exists for the case that
assumption does not hold: an environment that already has
``auth_provider='local'`` rows from before the cutover.

WHY A CORRECT PASSWORD STOPS WORKING WITHOUT THIS
-------------------------------------------------
``api/auth.py::login`` branches on the PER-USER ``users.auth_provider`` column,
not on ``settings.AUTH_PROVIDER``. Flipping the setting to ``cognito`` changes
token verification and NEW-user provisioning, but leaves every existing row on
the local bcrypt path — so a user typing their (correct) *Cognito pool*
password is checked against their old local hash and gets
``reason="invalid_password"``. This script is what actually moves the rows.

PASSWORDS CANNOT BE CARRIED OVER
--------------------------------
Cognito has no API that accepts a bcrypt hash: ``AdminCreateUser`` does not
take one, and the CSV user-import job excludes passwords entirely. So every
migrated user necessarily gets a NEW credential. Two shapes, per user:

* the designated admin (``--admin-email``) gets a PERMANENT password, read from
  stdin, so it is usable immediately with no interactive step — this is the
  credential that gets an operator back into the environment;
* everyone else gets a generated TEMPORARY password, which forces Cognito's
  NEW_PASSWORD_REQUIRED challenge on first login so the user sets their own.
  ``POST /api/auth/login/challenge`` already handles that challenge.

(The third option, a ``UserMigration_Authentication`` Lambda trigger that
validates the old bcrypt hash and adopts the user lazily on first login, is the
only way to PRESERVE passwords. It is not implemented here: this pool has no
such trigger, and wiring one is a Terraform + Lambda change, not a script.)

THIS IS DESTRUCTIVE AND NOT REVERSIBLE BY A CONFIG FLIP
-------------------------------------------------------
Migrating a row sets ``password_hash = NULL``. That is required (check C3 —
a retained hash is a second credential outside pool policy), but it means
rolling ``AUTH_PROVIDER`` back to ``local`` will NOT restore these users'
ability to log in. The migration plan's §8 rollback table says exactly this.
**Snapshot the database before running with --apply.**

WHAT IS PRESERVED
-----------------
``users.id`` — the local UUID every foreign key references
(``WorkflowRun.user_id`` etc.). ``cognito_sub`` is a mapping column only, so
no run history, artifact, or workspace row is touched. Tier and admin flag are
carried into Cognito GROUPS, which are authoritative on the Cognito path.

SAFETY PROPERTIES
-----------------
* **Dry-run by default.** Writes nothing without ``--apply``.
* **Break-glass preserved.** ``--break-glass-email`` is left on the local path
  so §5.6's "exactly one local admin" invariant can hold afterwards. Migrating
  every admin would leave ZERO local admins, which fails check C2 (no recovery
  path if Cognito is unreachable).
* **Idempotent / resumable.** A pool user that already exists is ADOPTED (its
  ``sub`` is read back) rather than treated as an error, and each user commits
  independently — so a run interrupted halfway can simply be re-run.
* **Compensating delete.** If the local UPDATE fails for a pool user THIS run
  created, that pool user is deleted again, so no orphan is left behind
  (an orphan authenticates at Cognito then 401s at ``resolve_principal`` —
  risk R7, check C5).
* **Secrets never logged.** The admin password arrives on stdin only — never
  argv (visible in ``ps``), never an environment variable (visible in
  ``docker inspect``, inherited by subprocesses). Generated temporary passwords
  are printed ONCE to stdout because there is no other way to deliver them;
  redirect accordingly. No password is ever written to a log record.

USAGE (from backend/)
---------------------
    # 1. See the plan. Writes nothing.
    uv run python scripts/migrate_users_to_cognito.py \
        --admin-email 'admin@example.com' \
        --break-glass-email 'ops-breakglass@example.com'

    # 2. Apply. The admin password is the SAME value held as the
    #    BOOTSTRAP_ADMIN_PASSWORD GitHub Actions secret (SSM
    #    /velocityai/<env>/bootstrap/admin-password), and --admin-email is the
    #    BOOTSTRAP_ADMIN_EMAIL variable (SSM .../bootstrap/admin-email).
    #    Those two SSM parameters are deliberately NOT loaded into the
    #    container environment (bootstrap-ec2.sh skips the bootstrap/* prefix
    #    precisely so the password never sits in `docker inspect` output), so
    #    fetch on demand and pipe it in:
    aws ssm get-parameter --name /velocityai/dev/bootstrap/admin-password \
        --with-decryption --query Parameter.Value --output text \
      | uv run python scripts/migrate_users_to_cognito.py \
            --admin-email "$(aws ssm get-parameter \
                --name /velocityai/dev/bootstrap/admin-email \
                --query Parameter.Value --output text)" \
            --break-glass-email 'ops-breakglass@example.com' \
            --admin-password-stdin --apply

    # 3. Gate on the reconciliation report.
    uv run python scripts/verify_cognito_cutover.py --check-pool

Requires COGNITO_* configuration to be present even when AUTH_PROVIDER is still
``local`` (that is the normal pre-flip state — see runbook step 3).
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from datetime import datetime, timezone

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from botocore.exceptions import ClientError  # noqa: E402

from app.core import cognito  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.entitlements import ADMIN_GROUP, group_for_tier  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1

# The pool's policy is min length 12 with upper/lower/digit/symbol required
# (infra/terraform/modules/cognito; confirmed live in the runbook's dev status
# block). Generate comfortably past that floor.
_GENERATED_PASSWORD_LENGTH = 20
_SYMBOLS = "!@#$%^&*()-_=+"


def _generate_temporary_password() -> str:
    """A random password that satisfies the pool's complexity policy.

    Builds from one guaranteed character of each required class plus random
    fill, then shuffles — rejection-sampling a fully random string would
    occasionally emit one missing a class and fail with
    ``InvalidPasswordException`` partway through a migration.
    """
    alphabet = string.ascii_letters + string.digits + _SYMBOLS
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_SYMBOLS),
    ]
    fill = [
        secrets.choice(alphabet)
        for _ in range(_GENERATED_PASSWORD_LENGTH - len(required))
    ]
    chars = required + fill
    # SystemRandom.shuffle: `secrets` exposes no shuffle, and the default
    # `random` module is not cryptographically secure.
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _normalise_email(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalised = value.strip().lower()
    return normalised or None


def _read_password_from_stdin() -> str | None:
    """Read one line of secret material from stdin.

    Only the trailing newline is stripped — a bare ``rstrip()`` would silently
    eat meaningful trailing whitespace from a generated password, setting a
    credential the operator cannot reproduce. Mirrors
    ``app/scripts/bootstrap_admin.py::_read_password_from_stdin``.
    """
    line = sys.stdin.readline()
    if not line:
        print("ERROR: no password received on stdin", file=sys.stderr)
        return None
    return line.removesuffix("\n").removesuffix("\r")


def _assert_pool_configured() -> str | None:
    """Return an error string if the Cognito pool is not reachable-configured.

    Checked explicitly because ``AUTH_PROVIDER`` is normally still ``local``
    when this runs (runbook step 3 precedes step 4), and the boot guard
    ``_validate_cognito_config`` only fires when AUTH_PROVIDER is ``cognito``.
    Without this the first AWS call would fail with an opaque botocore error
    partway through.
    """
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
            "The Cognito SSM parameters may exist but be missing from the "
            "on-host secrets-loader allowlist (infra/scripts/bootstrap-ec2.sh) "
            "— check /etc/velocityai/app.env."
        )
    return None


def _provision_pool_user(
    email: str,
    tier: str,
    is_admin: bool,
    password: str,
    permanent: bool,
) -> tuple[str, bool]:
    """Create-or-adopt the pool user and set its groups. Returns (sub, created).

    ``created`` tells the caller whether THIS run created the pool user, which
    is what decides if a compensating delete is appropriate when the local
    UPDATE subsequently fails. Adopting a pre-existing pool user must never
    lead to deleting it — it may be someone else's working account.

    Group membership is applied idempotently: ``AdminAddUserToGroup`` is a
    no-op for a user already in the group, so re-running is safe.
    """
    created = False
    try:
        resp = cognito.admin_create_user(email)
        created = True
        sub = next(
            attr["Value"]
            for attr in resp["User"]["Attributes"]
            if attr["Name"] == "sub"
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "UsernameExistsException":
            raise
        # Already in the pool — adopt it. This is the resumable path: a
        # previous interrupted run may have created it, or the account may have
        # been provisioned out of band.
        sub = cognito.admin_get_user_sub(email)

    try:
        cognito.admin_set_user_password(email, password, permanent=permanent)
        cognito.admin_add_user_to_group(email, group_for_tier(tier))
        if is_admin:
            cognito.admin_add_user_to_group(email, ADMIN_GROUP)
    except Exception:
        # Own the cleanup for everything after a create WE performed: the
        # caller cannot know a pool user exists until this function returns.
        # Same reasoning as bootstrap_admin.py::_bootstrap_cognito_admin.
        if created:
            _compensate_delete(email)
        raise

    return sub, created


def _compensate_delete(email: str) -> None:
    """Best-effort removal of a pool user this run created. Never raises."""
    try:
        cognito.admin_delete_user(email)
    except Exception:  # noqa: BLE001 - already handling a failure
        print(
            f"  WARNING: could not compensate-delete orphaned pool user {email} "
            f"— run verify_cognito_cutover.py --check-pool and clean up by hand",
            file=sys.stderr,
        )
    else:
        print(f"  compensated: deleted partially provisioned pool user {email}")


def migrate(
    admin_email: str | None,
    admin_password: str | None,
    break_glass_email: str | None,
    migrate_others: bool,
    apply: bool,
) -> int:
    config_error = _assert_pool_configured()
    if config_error:
        print(f"ERROR: {config_error}", file=sys.stderr)
        return EXIT_FAILED

    db = SessionLocal()
    try:
        locals_ = (
            db.query(User)
            .filter(User.auth_provider == "local")
            .order_by(User.email)
            .all()
        )

        if not locals_:
            print("No auth_provider='local' users found — nothing to migrate.")
            return EXIT_OK

        # --- Partition -------------------------------------------------------
        to_migrate: list[User] = []
        skipped_break_glass: User | None = None
        skipped_others: list[User] = []

        for user in locals_:
            if break_glass_email and user.email.lower() == break_glass_email:
                skipped_break_glass = user
                continue
            is_designated_admin = (
                bool(admin_email) and user.email.lower() == admin_email
            )
            if not is_designated_admin and not migrate_others:
                skipped_others.append(user)
                continue
            to_migrate.append(user)

        # --- Plan ------------------------------------------------------------
        print(f"\nCognito user migration — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  pool                 = {settings.COGNITO_USER_POOL_ID}")
        print(f"  AUTH_PROVIDER        = {settings.AUTH_PROVIDER}")
        print(f"  local users found    = {len(locals_)}")
        print("")

        if skipped_break_glass is not None:
            print(
                f"  KEEP LOCAL (break-glass): {skipped_break_glass.email} "
                f"(admin={bool(skipped_break_glass.is_admin)})"
            )
        elif break_glass_email:
            print(
                f"  WARNING: --break-glass-email {break_glass_email} matched no "
                f"local user. Check C2 expects exactly one local admin to remain."
            )
        else:
            print(
                "  WARNING: no --break-glass-email given. If every local admin is "
                "migrated, ZERO local admins remain and check C2 fails — there "
                "would be no recovery path if Cognito is unreachable."
            )

        for user in skipped_others:
            print(f"  SKIP (--admin-only):      {user.email}")

        for user in to_migrate:
            role = (
                "PERMANENT password from stdin"
                if (admin_email and user.email.lower() == admin_email)
                else "generated TEMPORARY password (NEW_PASSWORD_REQUIRED)"
            )
            groups = [group_for_tier(user.tier)]
            if user.is_admin:
                groups.append(ADMIN_GROUP)
            print(
                f"  MIGRATE:                  {user.email} "
                f"[tier={user.tier} admin={bool(user.is_admin)}] "
                f"-> groups={'+'.join(groups)}, {role}"
            )

        if not to_migrate:
            print("\nNothing to migrate.")
            return EXIT_OK

        if not apply:
            print(
                f"\nDRY RUN — nothing was written. {len(to_migrate)} user(s) would be "
                f"migrated.\nRe-run with --apply to execute. SNAPSHOT THE DATABASE FIRST: "
                f"migrating clears password_hash, and that is not undone by reverting "
                f"AUTH_PROVIDER."
            )
            return EXIT_OK

        # --- Apply -----------------------------------------------------------
        print("\nApplying...")
        generated: list[tuple[str, str]] = []
        failures: list[tuple[str, str]] = []

        for user in to_migrate:
            email = user.email
            is_designated_admin = bool(admin_email) and email.lower() == admin_email
            if is_designated_admin:
                if admin_password is None:
                    # Unreachable via main() (which requires
                    # --admin-password-stdin alongside --apply + --admin-email);
                    # a real check rather than an `assert` so it still holds if
                    # this module is ever driven programmatically or under -O.
                    failures.append((email, "no admin password supplied"))
                    print(
                        f"  FAILED  {email}: no admin password supplied",
                        file=sys.stderr,
                    )
                    continue
                password, permanent = admin_password, True
            else:
                password, permanent = _generate_temporary_password(), False

            try:
                sub, created = _provision_pool_user(
                    email,
                    user.tier,
                    bool(user.is_admin),
                    password,
                    permanent,
                )
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                failures.append((email, f"Cognito {code}"))
                print(f"  FAILED  {email}: Cognito {code}", file=sys.stderr)
                continue
            except Exception as exc:  # noqa: BLE001 - per-user isolation
                failures.append((email, str(exc)))
                print(f"  FAILED  {email}: {exc}", file=sys.stderr)
                continue

            # Commit per user so an interrupted run is resumable rather than
            # all-or-nothing across an unbounded number of AWS round-trips.
            now = datetime.now(timezone.utc)
            try:
                user.cognito_sub = sub
                user.auth_provider = "cognito"
                # Required by check C3: a retained hash is a second credential
                # outside the pool's policy/MFA/lockout.
                user.password_hash = None
                user.roles_synced_at = now
                # Invalidate any outstanding legacy HS256 token for this user:
                # their local credential no longer exists, so sessions minted
                # against it must not keep working (plan §5.3).
                user.tokens_valid_from = now
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                if created:
                    _compensate_delete(email)
                failures.append((email, f"local commit failed: {exc}"))
                print(f"  FAILED  {email}: local commit failed: {exc}", file=sys.stderr)
                continue

            if is_designated_admin:
                print(
                    f"  OK      {email} -> cognito_sub={sub} (permanent password set)"
                )
            else:
                generated.append((email, password))
                print(
                    f"  OK      {email} -> cognito_sub={sub} (temporary password below)"
                )

        # --- Report ----------------------------------------------------------
        if generated:
            print(
                "\nTEMPORARY PASSWORDS — shown once, not stored anywhere. Deliver "
                "these over an approved channel; each user is forced to set their "
                "own on first login (NEW_PASSWORD_REQUIRED):"
            )
            for email, password in generated:
                print(f"  {email}  {password}")

        migrated_count = len(to_migrate) - len(failures)
        print(f"\nMigrated {migrated_count}/{len(to_migrate)} user(s).")

        if failures:
            print(f"\n{len(failures)} FAILURE(S):", file=sys.stderr)
            for email, reason in failures:
                print(f"  {email}: {reason}", file=sys.stderr)
            print(
                "\nRe-running is safe: an existing pool user is adopted rather than "
                "recreated.",
                file=sys.stderr,
            )

        print("\nNext: uv run python scripts/verify_cognito_cutover.py --check-pool")
        if settings.AUTH_PROVIDER.lower() != "cognito":
            print(
                f"NOTE: AUTH_PROVIDER is still '{settings.AUTH_PROVIDER}'. Migrated "
                f"users authenticate via Cognito ONLY once it is 'cognito' "
                f"(runbook step 4) — until then their login will fail, because "
                f"their local password_hash is now NULL."
            )

        return EXIT_FAILED if failures else EXIT_OK
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/migrate_users_to_cognito.py",
        description=(
            "One-shot migration of auth_provider='local' users onto Cognito. "
            "Dry-run unless --apply is given."
        ),
    )
    parser.add_argument(
        "--admin-email",
        help=(
            "the administrator to give a PERMANENT password (from stdin) so it "
            "is usable immediately — normally the BOOTSTRAP_ADMIN_EMAIL value"
        ),
    )
    parser.add_argument(
        "--admin-password-stdin",
        action="store_true",
        help=(
            "read the admin password from stdin (required with --apply + "
            "--admin-email; never pass a secret as an argument)"
        ),
    )
    parser.add_argument(
        "--break-glass-email",
        help=(
            "local admin to LEAVE on the local path, preserving the §5.6 "
            "'exactly one local admin' recovery account"
        ),
    )
    parser.add_argument(
        "--admin-only",
        action="store_true",
        help=(
            "migrate ONLY --admin-email; leave all other local users alone "
            "(default: migrate every local user except --break-glass-email)"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write. Without this the script only prints the plan.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    admin_email = _normalise_email(args.admin_email)
    break_glass_email = _normalise_email(args.break_glass_email)

    if args.admin_only and not admin_email:
        print("ERROR: --admin-only requires --admin-email", file=sys.stderr)
        return EXIT_FAILED

    if admin_email and break_glass_email and admin_email == break_glass_email:
        print(
            "ERROR: --admin-email and --break-glass-email are the same address. "
            "The break-glass account must STAY local; it cannot also be the "
            "Cognito admin.",
            file=sys.stderr,
        )
        return EXIT_FAILED

    admin_password: str | None = None
    if admin_email and args.apply:
        if not args.admin_password_stdin:
            print(
                "ERROR: --admin-password-stdin is required when applying with "
                "--admin-email (the password must not be passed as an argument)",
                file=sys.stderr,
            )
            return EXIT_FAILED
        admin_password = _read_password_from_stdin()
        if admin_password is None:
            return EXIT_FAILED
        # Matches the pool's minimum length so the failure is reported here
        # rather than as an InvalidPasswordException mid-migration.
        if len(admin_password) < 12:
            print(
                "ERROR: the admin password must be at least 12 characters to "
                "satisfy the pool policy",
                file=sys.stderr,
            )
            return EXIT_FAILED

    try:
        return migrate(
            admin_email=admin_email,
            admin_password=admin_password,
            break_glass_email=break_glass_email,
            migrate_others=not args.admin_only,
            apply=args.apply,
        )
    except Exception as exc:  # noqa: BLE001 - process boundary
        print(f"\nERROR during migration: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
