#!/usr/bin/env python3
"""Create the initial administrator on a freshly deployed environment.

WHY THIS EXISTS
---------------
Self-registration is disabled (``/api/auth/register`` always 403s) and the only
other user-creation path (``/api/admin/users``) requires an *already
authenticated* administrator. A brand-new environment therefore has no way in.
The previous answer was to log into the VM and seed a user by hand, which does
not work when nobody is allowed onto production hosts.

This command closes that gap as a one-shot, deploy-time step run INSIDE the
backend container (see ``.github/scripts/remote-deploy.sh`` §12), after
``alembic upgrade head`` and after the health gate.

THE INVARIANT — deliberately narrow
-----------------------------------
    users table has zero rows  -> create exactly one administrator
    users table has any row    -> do nothing, successfully

"Any row", not "no admin exists". Consequences, all intentional:

* an existing user is never modified, promoted, or re-hashed;
* a database with users but no admin is NOT backfilled — that is a recovery
  scenario and belongs in an audited break-glass procedure, not in a step that
  runs unattended on every deploy;
* deleting the last administrator does not silently re-open bootstrap.

CONCURRENCY
-----------
``COUNT`` followed by ``INSERT`` is a race: two callers can both observe an
empty table. The insert path therefore takes a PostgreSQL table lock first (see
``_lock_users_table``), which also serialises against the plain inserts issued
by ``/api/admin/users``. The unique index on ``users.email`` cannot substitute
for this — it protects one email, not the global "no user existed" invariant.

SECRET HANDLING
---------------
The password arrives on stdin and nowhere else: not an argv element (visible in
``ps``), not an environment variable (visible in ``docker inspect`` and
inherited by subprocesses), not a temp file. It is hashed immediately and never
logged, echoed, or included in an error message.

Modes / exit codes — the contract remote-deploy.sh §12 branches on:

    --check-only
        0   at least one user exists; bootstrap not needed
        10  users table is empty; bootstrap is required
        1   database or runtime error

    --email <addr> --password-stdin
        0   administrator created, OR another process got there first
        1   validation, database, or runtime error
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.database import SessionLocal
from app.models.user import User

logger = logging.getLogger("bootstrap_admin")

SessionFactory = Callable[[], Session]

# Exit codes. 10 is deliberately not 1: remote-deploy.sh has to tell "the
# database is empty, go fetch credentials" apart from "something broke", and a
# shared non-zero code would make a genuine failure look like a bootstrap
# request (and vice versa).
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BOOTSTRAP_REQUIRED = 10

# Stricter than the 8-character floor on /api/admin/users. This credential is
# minted by a pipeline, stored in a secret manager, and typed by a human at most
# once, so there is no usability argument for a short one.
MIN_PASSWORD_LENGTH = 16

# The initial operator needs the full entitlement set; tier is a free-form
# string on the model, so this is the one place the bootstrap value is written.
INITIAL_ADMIN_TIER = "enterprise"


def configure_logging() -> None:
    """Send our own records to stdout, leaving stderr for real failures.

    ``force=True`` because importing ``app.*`` pulls in modules that may have
    already configured the root logger; without it this call would be a no-op
    and the records would follow whatever handler got there first.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="[bootstrap-admin] %(message)s",
        stream=sys.stdout,
        force=True,
    )


def _users_exist(session: Session) -> bool:
    """True if the users table has at least one row.

    ``LIMIT 1`` rather than ``COUNT(*)``: the question is existence, and this
    stops at the first row instead of scanning the table.
    """
    return session.query(User.id).limit(1).first() is not None


def _lock_users_table(session: Session) -> None:
    """Serialise the check-then-insert against every other writer.

    ``SHARE ROW EXCLUSIVE`` conflicts with itself AND with the ordinary
    ``INSERT`` locks taken by ``/api/admin/users``, so a second bootstrap (or a
    concurrent admin-created user) blocks here and then loses the re-check
    below. A PostgreSQL advisory lock would only coordinate with other callers
    that agreed to take the same advisory lock, which the API does not.

    Non-PostgreSQL backends have no equivalent statement. Production is always
    PostgreSQL (see the local-setup rules); the branch exists so the
    check-then-insert logic can be exercised on in-memory SQLite in the unit
    suite. Real lock behaviour is covered by the opt-in PostgreSQL suite.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    else:
        logger.debug("dialect %r has no table lock — skipping", dialect)


def _normalise_email(email: object) -> str | None:
    """Return a lowercased, trimmed address, or None if it is unusable.

    Accepts ``object`` because the value reaches here from argparse and from
    callers that may pass ``None``; an ``AttributeError`` on a missing argument
    would surface as a stack trace mid-deploy instead of a clear exit 1.
    """
    if not isinstance(email, str):
        return None
    normalised = email.strip().lower()
    if not normalised:
        return None
    # Deliberately not a full RFC 5322 validation: this is a typo guard for a
    # value an operator sets once. The address is only ever compared for
    # equality at login, so anything the operator can also type into the login
    # form is acceptable.
    local, _, domain = normalised.partition("@")
    if not local or not domain or "." not in domain:
        return None
    return normalised


def check_only(session_factory: SessionFactory | None = None) -> int:
    """Report whether bootstrap is required, without writing anything.

    Called first by the deploy script so the password is fetched from SSM ONLY
    when it is actually needed — on the overwhelmingly common redeploy path the
    secret is never decrypted, never transported, and never handled.
    """
    factory = session_factory or SessionLocal
    try:
        session = factory()
        try:
            if _users_exist(session):
                logger.info("users table is already initialized — bootstrap not needed")
                return EXIT_OK
            logger.info("users table is empty — bootstrap required")
            return EXIT_BOOTSTRAP_REQUIRED
        finally:
            session.close()
    except Exception as exc:
        # Broad by design: this is a process boundary. Every failure mode —
        # unreachable database, missing table because migrations did not run,
        # driver error — has to become the documented exit code, because the
        # deploy script branches on that number. A traceback on stderr would
        # tell remote-deploy.sh nothing it can act on.
        logger.error("could not determine users table state: %s", exc)
        return EXIT_ERROR


def create_admin(
    email: object,
    password: object,
    session_factory: SessionFactory | None = None,
) -> int:
    """Create the initial administrator if, and only if, no user exists.

    Validation happens before the database is touched so a malformed input
    cannot leave a transaction open. The whole insert path is one transaction:
    lock, re-check, hash, insert, commit.
    """
    normalised_email = _normalise_email(email)
    if normalised_email is None:
        logger.error("invalid administrator email address — refusing to bootstrap")
        return EXIT_ERROR

    # Length is reported, the value never is.
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        logger.error(
            "administrator password must be at least %d characters",
            MIN_PASSWORD_LENGTH,
        )
        return EXIT_ERROR

    factory = session_factory or SessionLocal
    try:
        session = factory()
    except Exception as exc:
        # See check_only: at a process boundary the exit code is the contract.
        logger.error("could not open a database session: %s", exc)
        return EXIT_ERROR

    cognito_sub: str | None = None
    try:
        _lock_users_table(session)

        # Re-check while holding the lock. A caller that blocked above lands
        # here after the winner committed, sees the row, and no-ops.
        if _users_exist(session):
            logger.info(
                "users table is already initialized — another process bootstrapped it first"
            )
            session.rollback()
            return EXIT_OK

        # created_at / updated_at are intentionally omitted: the model's own
        # column defaults supply them, so this row is stamped exactly like
        # every other user instead of by a second, divergent code path.
        #
        # COGNITO-MIGRATION-PLAN §7 Phase 3 ("Bootstrap admin — Critical
        # path"): when Cognito is the active provider, this is the ONLY way
        # into a fresh environment (self-registration is 403'd; the normal
        # POST /api/admin/users path itself requires an already-authenticated
        # admin). So the pool user + flowin-admins membership are provisioned
        # HERE, inside the same locked section, before the local row commits
        # — a failure on either side leaves NO row (see the except branch's
        # compensating pool-user delete) rather than a half-bootstrapped
        # environment. `AUTH_PROVIDER != "cognito"` (the default) is
        # byte-identical to the pre-migration behaviour — every existing test
        # in this module runs with the default settings and is unaffected.
        if settings.AUTH_PROVIDER.lower() == "cognito":
            cognito_sub = _bootstrap_cognito_admin(normalised_email, password)

        session.add(
            User(
                email=normalised_email,
                password_hash=None if cognito_sub else hash_password(password),
                cognito_sub=cognito_sub,
                auth_provider="cognito" if cognito_sub else "local",
                tier=INITIAL_ADMIN_TIER,
                is_admin=True,
            )
        )
        session.commit()
        logger.info("initial administrator created: %s", normalised_email)
        return EXIT_OK
    except Exception as exc:
        # Rollback before anything else: this releases the table lock, so a
        # concurrent caller blocked on it proceeds instead of waiting out the
        # deploy. The message carries the email at most, never the password.
        session.rollback()
        if cognito_sub is not None:
            _compensate_delete_cognito_admin(normalised_email)
        logger.error("failed to create the initial administrator: %s", exc)
        return EXIT_ERROR
    finally:
        session.close()


def _bootstrap_cognito_admin(email: str, password: str) -> str:
    """Provision the pool user + flowin-admins membership for the initial admin.

    Uses ``AdminSetUserPassword(..., Permanent=True)`` so the account is
    immediately usable with the given password, with no forced
    NEW_PASSWORD_REQUIRED challenge — this is the credential that gets
    someone into a brand-new environment, so it must work on the first try
    with no additional interactive step. Returns the pool user's ``sub``
    (from ``AdminCreateUser``'s response attributes) to store as
    ``users.cognito_sub``.
    """
    from app.core import cognito
    from app.core.entitlements import ADMIN_GROUP

    create_resp = cognito.admin_create_user(email)
    cognito.admin_set_user_password(email, password, permanent=True)
    cognito.admin_add_user_to_group(email, ADMIN_GROUP)
    return next(
        attr["Value"]
        for attr in create_resp["User"]["Attributes"]
        if attr["Name"] == "sub"
    )


def _compensate_delete_cognito_admin(email: str) -> None:
    """Best-effort cleanup of an orphaned pool user after a local-commit failure."""
    from app.core import cognito

    try:
        cognito.admin_delete_user(email)
    except Exception:  # noqa: BLE001 - best-effort; already in an error path
        logger.error("failed to compensate-delete the orphaned Cognito admin %s", email)


def _read_password_from_stdin() -> str | None:
    """Read one line of secret material from stdin.

    Only the trailing newline is removed. ``rstrip()`` with no argument would
    also eat meaningful trailing whitespace from a generated password, silently
    storing a hash of something the operator cannot reproduce.
    """
    try:
        line = sys.stdin.readline()
    except Exception as exc:
        # The exception message is safe to log here: a read failure happens
        # before any secret material exists in this process.
        logger.error("could not read the password from stdin: %s", exc)
        return None
    if not line:
        logger.error("no password received on stdin")
        return None
    return line.removesuffix("\n").removesuffix("\r")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.bootstrap_admin",
        description="Create the initial administrator when the users table is empty.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="report whether bootstrap is required (0 = no, 10 = yes) and write nothing",
    )
    parser.add_argument(
        "--email",
        help="email address for the initial administrator",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin (required with --email; never pass it as an argument)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging()

    if args.check_only:
        # Guard against a caller that means "check" but also hands over
        # credentials — silently ignoring them would hide a scripting mistake
        # that leaves an environment un-bootstrapped.
        if args.email or args.password_stdin:
            logger.error("--check-only cannot be combined with --email/--password-stdin")
            return EXIT_ERROR
        return check_only()

    if not args.email or not args.password_stdin:
        logger.error("both --email and --password-stdin are required to create an administrator")
        parser.print_usage(sys.stderr)
        return EXIT_ERROR

    password = _read_password_from_stdin()
    if password is None:
        return EXIT_ERROR

    return create_admin(args.email, password)


if __name__ == "__main__":
    sys.exit(main())
