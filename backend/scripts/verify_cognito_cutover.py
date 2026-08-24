"""Verify a Cognito cutover, and reconcile the two identity stores.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 5 steps 5-6, plus the
reconciliation report the risk register calls for at R7).

This is the gate that decides whether an environment is safe to advance to
step 7 (``AUTH_ALLOW_LEGACY_JWT=false``). It exits non-zero if ANY check
fails, so it can be dropped straight into a pipeline as a release gate.

CHECKS
------
  C1  Zero unmapped Cognito users
        SELECT count(*) FROM users WHERE auth_provider='cognito'
                                     AND cognito_sub IS NULL   -> 0
      A Cognito-provider row without a ``cognito_sub`` can never be resolved
      by ``core/identity.py::resolve_principal`` — that user simply cannot log
      in. This is the single most important post-provisioning assertion.

  C2  Exactly one local (break-glass) admin
      The break-glass design (§5.6) is only worth its retained attack surface
      if there is exactly one of it. Zero means no recovery path from a
      Cognito outage; more than one means several standing weaknesses.

  C3  No Cognito user retains a local password hash
      A leftover ``password_hash`` on a Cognito row is a second, unmanaged
      credential for that identity, outside the pool's policy/MFA/lockout.

  C4  Local-store -> pool reconciliation  (requires --check-pool)
      Every ``auth_provider='cognito'`` row has a live pool user, and its
      ``cognito_sub`` still matches. Catches the R14 delete/recreate case
      (``sub`` reuse) and orphaned local rows.

  C5  Pool -> local-store reconciliation  (requires --check-pool)
      Every pool user has a local row. An orphaned POOL user can authenticate
      against Cognito but has no local identity, so it 401s at
      ``resolve_principal`` — invisible unless you look.

USAGE (from backend/)
---------------------
    # DB-only checks (fast, no AWS calls):
    uv run python scripts/verify_cognito_cutover.py

    # Full reconciliation against the live pool:
    uv run python scripts/verify_cognito_cutover.py --check-pool

Read-only. This script never writes to either store — it reports, and leaves
remediation to a human, because every failure mode here has more than one
defensible fix.
"""
import argparse
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from app.core.config import settings  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"


class Report:
    """Collects check outcomes so every check runs even after one fails.

    Running all checks (rather than short-circuiting) matters here: an
    operator mid-cutover wants the complete picture in one pass, not to
    discover a second problem only after fixing the first.
    """

    def __init__(self) -> None:
        self.failed = False

    def record(self, status: str, check: str, detail: str) -> None:
        if status == _FAIL:
            self.failed = True
        print(f"  [{status}] {check}: {detail}")


def _check_db(db, report: Report) -> None:
    print("\nDatabase checks")

    # --- C1: zero unmapped Cognito users ---
    unmapped = (
        db.query(User)
        .filter(User.auth_provider == "cognito", User.cognito_sub.is_(None))
        .all()
    )
    if unmapped:
        report.record(
            _FAIL,
            "C1 unmapped-cognito-users",
            f"{len(unmapped)} row(s) have auth_provider='cognito' but no cognito_sub "
            f"and therefore CANNOT log in: {', '.join(u.email for u in unmapped)}",
        )
    else:
        report.record(_PASS, "C1 unmapped-cognito-users", "0 unmapped rows")

    # --- C2: exactly one local admin ---
    local_admins = (
        db.query(User)
        .filter(User.auth_provider == "local", User.is_admin.is_(True))
        .all()
    )
    if len(local_admins) == 1:
        report.record(
            _PASS,
            "C2 break-glass-admin",
            f"exactly one local admin ({local_admins[0].email})",
        )
    elif not local_admins:
        report.record(
            _FAIL,
            "C2 break-glass-admin",
            "NO local admin exists — there is no recovery path if Cognito is "
            "unreachable. Run scripts/create_break_glass_admin.py.",
        )
    else:
        report.record(
            _FAIL,
            "C2 break-glass-admin",
            f"{len(local_admins)} local admins exist, expected exactly 1: "
            f"{', '.join(u.email for u in local_admins)}",
        )

    # --- C3: no Cognito user retains a local password ---
    with_hash = (
        db.query(User)
        .filter(User.auth_provider == "cognito", User.password_hash.isnot(None))
        .all()
    )
    if with_hash:
        report.record(
            _FAIL,
            "C3 residual-password-hash",
            f"{len(with_hash)} Cognito row(s) still carry a local password_hash "
            f"(a second credential outside pool policy): "
            f"{', '.join(u.email for u in with_hash)}",
        )
    else:
        report.record(_PASS, "C3 residual-password-hash", "0 residual hashes")

    # --- Informational inventory ---
    total = db.query(User).count()
    cognito_count = db.query(User).filter(User.auth_provider == "cognito").count()
    local_count = db.query(User).filter(User.auth_provider == "local").count()
    print(
        f"\n  inventory: {total} users total "
        f"({cognito_count} cognito, {local_count} local)"
    )


def _check_pool(db, report: Report) -> None:
    print("\nPool reconciliation")

    if not settings.COGNITO_USER_POOL_ID:
        report.record(
            _FAIL,
            "C4/C5 pool-reconciliation",
            "COGNITO_USER_POOL_ID is unset — cannot reach the pool. Check "
            "/etc/velocityai/app.env (the secrets-loader allowlist must "
            "include the COGNITO_* names).",
        )
        return

    from botocore.exceptions import ClientError

    from app.core import cognito

    # --- C4: every local Cognito row resolves to a live pool user ---
    local_rows = db.query(User).filter(User.auth_provider == "cognito").all()
    missing_in_pool: list[str] = []
    sub_mismatch: list[str] = []

    for user in local_rows:
        try:
            pool_sub = cognito.admin_get_user_sub(user.email)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "UserNotFoundException":
                missing_in_pool.append(user.email)
                continue
            raise
        if user.cognito_sub and pool_sub != user.cognito_sub:
            # R14: the pool user was deleted and recreated, so the local row
            # points at a principal that no longer exists.
            sub_mismatch.append(user.email)

    if missing_in_pool:
        report.record(
            _FAIL,
            "C4 orphaned-local-rows",
            f"{len(missing_in_pool)} local row(s) have no pool user: "
            f"{', '.join(missing_in_pool)}",
        )
    else:
        report.record(
            _PASS, "C4 orphaned-local-rows", f"all {len(local_rows)} local rows resolve"
        )

    if sub_mismatch:
        report.record(
            _FAIL,
            "C4b cognito-sub-drift",
            f"{len(sub_mismatch)} row(s) have a stale cognito_sub (pool user was "
            f"deleted and recreated): {', '.join(sub_mismatch)}",
        )
    else:
        report.record(_PASS, "C4b cognito-sub-drift", "no sub drift")

    # --- C5: every pool user has a local row ---
    known_emails = {u.email.lower() for u in db.query(User).all()}
    orphaned_pool_users: list[str] = []
    pool_users = cognito.list_pool_users()
    pool_total = len(pool_users)
    for pool_user in pool_users:
        email = next(
            (
                a["Value"]
                for a in pool_user.get("Attributes", [])
                if a["Name"] == "email"
            ),
            pool_user.get("Username", ""),
        )
        if email.lower() not in known_emails:
            orphaned_pool_users.append(email)

    if orphaned_pool_users:
        report.record(
            _FAIL,
            "C5 orphaned-pool-users",
            f"{len(orphaned_pool_users)} pool user(s) have no local row and will "
            f"401 after authenticating: {', '.join(orphaned_pool_users)}",
        )
    else:
        report.record(
            _PASS, "C5 orphaned-pool-users", f"all {pool_total} pool users mapped"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-pool",
        action="store_true",
        help="Also reconcile against the live Cognito pool (makes AWS API calls).",
    )
    args = parser.parse_args()

    print("Cognito cutover verification")
    print(f"  AUTH_PROVIDER         = {settings.AUTH_PROVIDER}")
    print(f"  AUTH_ALLOW_LEGACY_JWT = {settings.AUTH_ALLOW_LEGACY_JWT}")
    print(f"  BREAK_GLASS_ENABLED   = {settings.BREAK_GLASS_ENABLED}")
    print(f"  COGNITO_USER_POOL_ID  = {settings.COGNITO_USER_POOL_ID or '(unset)'}")

    report = Report()
    db = SessionLocal()
    try:
        _check_db(db, report)
        if args.check_pool:
            _check_pool(db, report)
        else:
            print("\nPool reconciliation")
            print(f"  [{_SKIP}] C4/C5: pass --check-pool to reconcile against AWS")
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR during verification: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        db.close()

    print("")
    if report.failed:
        print("RESULT: FAILED — do NOT set AUTH_ALLOW_LEGACY_JWT=false yet.")
        return EXIT_FAILED

    print("RESULT: PASSED — steps 5 and 6 satisfied.")
    if settings.AUTH_ALLOW_LEGACY_JWT:
        print(
            "  Next: once outstanding legacy tokens have aged out "
            "(<= ACCESS_TOKEN_EXPIRE_HOURS), set AUTH_ALLOW_LEGACY_JWT=false "
            "for this environment (step 7)."
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
