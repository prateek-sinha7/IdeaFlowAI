"""Create (or rotate) the single break-glass local-password admin.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §5.6, Phase 5 step 4 — Decision 12).

WHY THIS EXISTS
---------------
After cutover Cognito is the credential authority, which makes Cognito
availability a hard dependency for every NEW login. A prolonged Cognito
control-plane outage would otherwise lock operators out of their own system.
The break-glass account is exactly one ``users`` row with
``auth_provider='local'`` and a bcrypt ``password_hash``, whose login path
never touches Cognito.

This is a deliberate trade: a small amount of retained attack surface (the
local credential code path stays reachable, permanently — see the plan's
"architectural consequence to accept explicitly") in exchange for incident
recoverability.

THE SINGLE-ROW INVARIANT
------------------------
The value of this account depends on there being exactly ONE of it. Two
break-glass admins is two standing weaknesses and no clearer ownership. This
script therefore REFUSES to create a second local admin, and
``verify_cognito_cutover.py`` asserts the same invariant independently.

HYGIENE REQUIREMENTS (not enforceable by code — your responsibility)
--------------------------------------------------------------------
  * Documented owner and documented rotation cadence.
  * Password stored in an approved secret store. NEVER in ``.tfvars``, never
    in an SSM ``String`` parameter, never in git.
  * A CloudWatch metric filter on the auth log alarming on ANY successful
    break-glass login, routed to SNS. A break-glass login is by definition an
    incident signal; if it fires and nobody is paged, the control is theatre.

USAGE (from backend/)
---------------------
    BREAK_GLASS_EMAIL=ops-breakglass@example.com \\
    BREAK_GLASS_PASSWORD='<from your secret store>' \\
      uv run python scripts/create_break_glass_admin.py

    # Rotate the password on the existing account:
    BREAK_GLASS_EMAIL=... BREAK_GLASS_PASSWORD='<new>' \\
      uv run python scripts/create_break_glass_admin.py --rotate

The password is read from the environment, never from an argument, so it does
not land in shell history or the process table via argv.
"""
import argparse
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from datetime import datetime, timezone  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

# Long enough that the account is not the weakest link in the system. This is
# intentionally stricter than the 8-char legacy floor and matches the Cognito
# pool policy, so the break-glass credential is never the softer target.
MIN_PASSWORD_LENGTH = 16


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Rotate the password on the EXISTING break-glass account instead of refusing.",
    )
    args = parser.parse_args()

    email = (os.environ.get("BREAK_GLASS_EMAIL") or "").strip().lower()
    password = os.environ.get("BREAK_GLASS_PASSWORD") or ""

    if not email:
        print("ERROR: BREAK_GLASS_EMAIL is not set.", file=sys.stderr)
        return EXIT_ERROR
    if len(password) < MIN_PASSWORD_LENGTH:
        # Never echo the password or its length-as-given in a way that leaks it.
        print(
            f"ERROR: BREAK_GLASS_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    db = SessionLocal()
    try:
        existing_local_admins = (
            db.query(User)
            .filter(User.auth_provider == "local", User.is_admin.is_(True))
            .all()
        )

        # --- Enforce the single-row invariant, fail closed. ---
        others = [u for u in existing_local_admins if u.email.lower() != email]
        if others:
            print(
                "REFUSED: a different local-password admin already exists "
                f"({', '.join(u.email for u in others)}). The break-glass design "
                "permits exactly ONE (plan §5.6). Remove or convert the other "
                "account first, or re-run with BREAK_GLASS_EMAIL set to it.",
                file=sys.stderr,
            )
            return EXIT_REFUSED

        target = next(
            (u for u in existing_local_admins if u.email.lower() == email), None
        )

        if target is not None and not args.rotate:
            print(
                f"REFUSED: break-glass admin {email} already exists. "
                "Re-run with --rotate to change its password.",
                file=sys.stderr,
            )
            return EXIT_REFUSED

        now = datetime.now(timezone.utc)

        if target is not None:
            target.password_hash = hash_password(password)
            # Stamping password_changed_at blanket-revokes every token this
            # account previously held (core/identity.py's generalized check).
            target.password_changed_at = now
            target.tokens_valid_from = now
            db.commit()
            print(f"Rotated break-glass admin password: {email}")
            _print_hygiene_reminder()
            return EXIT_OK

        # An account may already exist for this email as a COGNITO user (e.g.
        # it was provisioned normally first). Converting it would silently
        # remove someone's Cognito identity — refuse and make the operator
        # choose a dedicated address instead.
        clash = db.query(User).filter(User.email == email).one_or_none()
        if clash is not None:
            print(
                f"REFUSED: {email} already exists with auth_provider="
                f"'{clash.auth_provider}'. Use a dedicated address for the "
                "break-glass account rather than converting a real user.",
                file=sys.stderr,
            )
            return EXIT_REFUSED

        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                auth_provider="local",
                is_admin=True,
                tier="enterprise",
                password_changed_at=now,
            )
        )
        db.commit()
        print(f"Created break-glass admin: {email}")
        _print_hygiene_reminder()
        return EXIT_OK

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Message carries the email at most, never the password.
        print(f"ERROR: failed to create/rotate the break-glass admin: {exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        db.close()


def _print_hygiene_reminder() -> None:
    print("")
    print("REMAINING MANUAL STEPS (this script cannot do these for you):")
    print("  1. Store the password in the approved secret store. Not in git,")
    print("     not in *.tfvars, not in an SSM String parameter.")
    print("  2. Record the documented owner and rotation cadence.")
    print("  3. Verify the CloudWatch metric filter + SNS alarm fires on a")
    print("     break-glass login. Test it — an untested alarm is not a control.")
    print("  4. Confirm BREAK_GLASS_ENABLED=true in this environment's config.")


if __name__ == "__main__":
    raise SystemExit(main())
