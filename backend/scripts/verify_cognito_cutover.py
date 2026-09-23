"""Verify the Cognito-only cutover, and reconcile the two identity stores.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 1). Cognito is the sole authentication authority now — there is no
local/break-glass admin and no ``AUTH_PROVIDER``/``AUTH_ALLOW_LEGACY_JWT``
dual-accept window to gate on. This script's checks were rewritten to match:
the break-glass and residual-password-hash checks are gone (there is no
local credential path for either to find), and C1 now simply asserts every
row has a linked ``cognito_sub``.

CHECKS
------
  C1  Zero unmapped users   (DATA)
        SELECT count(*) FROM users WHERE cognito_sub IS NULL   -> 0
      A row without a ``cognito_sub`` can never be resolved by
      ``core/identity.py::resolve_principal`` — that user simply cannot log
      in. This is the single most important post-provisioning assertion.

  C2  Local-credential columns are gone   (SCHEMA, Phase 2)
      ``users`` no longer has ``password_hash`` or ``auth_provider``,
      ``cognito_sub`` is NOT NULL, and ``status`` exists. C1 is a data check
      and passes happily against a schema that still carries the local-auth
      columns — which is precisely the state of a box whose image was updated
      but whose ``alembic upgrade head`` did not run. In that state the ORM
      model and the table disagree and C1 has verified nothing.

  C3  Alembic head matches this code   (Phase 2)
      Exactly one stamped revision, equal to ``EXPECTED_ALEMBIC_HEAD``. Makes
      C2's failure actionable by naming the revision the database is parked on,
      and independently catches the two-heads condition that crash-loops the
      container (``docker-entrypoint.sh`` runs the upgrade under ``set -eu``).

  C6  Every tier round-trips through a Cognito group   (Phase 2)
      Phase 2 made ``cognito:groups`` the sole entitlement authority, so a tier
      with no group of its own is no longer a latent inconsistency — it is a
      silent entitlement DOWNGRADE to the fail-closed default. ``hexaware`` was
      in exactly that state (``MERGE_NOTES.md`` §2).

  C4  Local-store -> pool reconciliation  (requires --check-pool)
      Every row has a live pool user, and its ``cognito_sub`` still matches.
      Catches the sub-reuse case (pool user deleted and recreated) and
      orphaned local rows.

  C5  Pool -> local-store reconciliation  (requires --check-pool)
      Every pool user has a local row.

      NOTE (Phase 2): this is now INFORMATIONAL in nature, though still
      reported as a failure by this script because a cutover gate should be
      strict. Just-in-time provisioning (``core/provisioning.py``) creates the
      missing row on the user's first successful sign-in, so a pool user
      without one is no longer permanently locked out — the state is
      self-healing. For ONGOING monitoring prefer
      ``app/scripts/reconcile_cognito_users.py``, which classifies this case as
      informational and does not fail on it.

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


#: The Alembic head this build of the application expects. Restated here rather
#: than derived from ``alembic/versions/`` on disk: the point of C3 is to catch a
#: box running MIGRATIONS that do not match its CODE, and reading the head off
#: the same checkout the code came from would make the check tautological — it
#: would agree with itself no matter what the database says.
EXPECTED_ALEMBIC_HEAD = "0050"


def _check_db(db, report: Report) -> None:
    print("\nDatabase checks")

    # SCHEMA checks run BEFORE the data check, and the ordering is load-bearing
    # rather than cosmetic. C1 queries through the ORM, whose `User` model
    # includes post-0038 columns (`status`, and a NOT NULL `cognito_sub`). Run
    # against a database that has NOT been migrated, that SELECT raises
    # OperationalError on the missing column — so the operator would get
    # "ERROR during verification" plus a stack trace instead of C2's actionable
    # "migration 0038 has not been applied". The unmigrated database is exactly
    # the case this script exists to diagnose, so it must not be the case that
    # crashes it.
    schema_ok = _check_schema(db, report)

    # --- C1: zero unmapped users (data) ---
    if not schema_ok:
        report.record(
            _SKIP,
            "C1 unmapped-users",
            "skipped — the schema checks above failed, so the ORM cannot query "
            "this database. Fix the schema first.",
        )
    else:
        unmapped = db.query(User).filter(User.cognito_sub.is_(None)).all()
        if unmapped:
            report.record(
                _FAIL,
                "C1 unmapped-users",
                f"{len(unmapped)} row(s) have no cognito_sub and therefore CANNOT "
                f"log in: {', '.join(u.email for u in unmapped)}",
            )
        else:
            report.record(_PASS, "C1 unmapped-users", "0 unmapped rows")

    _check_tier_groups(report)

    # --- Informational inventory ---
    if schema_ok:
        total = db.query(User).count()
        disabled = db.query(User).filter(User.status != "active").count()
        print(f"\n  inventory: {total} users total ({disabled} not active)")


def _check_schema(db, report: Report) -> bool:
    """C2/C3. Returns whether the schema is migrated far enough for ORM queries.

    Reflection, not queries: asking about the SHAPE is the point, and a SELECT
    against a dropped or missing column raises rather than reports.
    """
    import sqlalchemy as sa

    inspector = sa.inspect(db.get_bind())
    schema_ok = True

    # --- C2: the local-credential columns are GONE (schema) ---
    # Phase 2 addition. C1 is a DATA check and passes happily on a schema that
    # still carries the local-auth columns — which is not a hypothetical
    # mismatch: it is exactly the state of a box whose image was updated but
    # whose `alembic upgrade head` did not run. A surviving `password_hash`
    # column means the migration did not apply, so the ORM model and the table
    # disagree and nothing else here has actually been verified.
    if "users" not in inspector.get_table_names():
        report.record(_FAIL, "C2 local-credential-columns", "the users table is absent")
        schema_ok = False
    else:
        columns = {c["name"] for c in inspector.get_columns("users")}
        residual = sorted({"password_hash", "auth_provider"} & columns)
        if residual:
            report.record(
                _FAIL,
                "C2 local-credential-columns",
                f"users still has {', '.join(residual)} — migration 0038 has NOT "
                f"been applied to this database, so the schema does not match the "
                f"code that is running.",
            )
            # Any C2 failure means the table predates 0038, so the ORM model
            # (which has post-0038 columns) cannot query it. Flag it so C1 is
            # SKIPPED with an explanation rather than raising -- see the ordering
            # note in _check_db.
            schema_ok = False
        else:
            report.record(
                _PASS,
                "C2 local-credential-columns",
                "password_hash and auth_provider are gone",
            )

        # `cognito_sub` NOT NULL is the schema-level counterpart to C1: C1 proves
        # no such row exists TODAY, this proves none can be created tomorrow.
        sub_column = next(
            (c for c in inspector.get_columns("users") if c["name"] == "cognito_sub"),
            None,
        )
        if sub_column is None:
            report.record(
                _FAIL, "C2b cognito-sub-not-null", "users has no cognito_sub column"
            )
            schema_ok = False
        elif sub_column.get("nullable", True):
            report.record(
                _FAIL,
                "C2b cognito-sub-not-null",
                "cognito_sub is still NULLABLE — 0038 has not been applied, so a "
                "row that can never log in can still be inserted.",
            )
            schema_ok = False
        else:
            report.record(_PASS, "C2b cognito-sub-not-null", "cognito_sub is NOT NULL")

        if "status" not in columns:
            report.record(
                _FAIL,
                "C2c status-column",
                "users has no status column — the disabled-account gate in "
                "core/identity.py::resolve_principal cannot be enforced.",
            )
            schema_ok = False
        else:
            report.record(_PASS, "C2c status-column", "status column present")

    # --- C3: Alembic head matches what this code expects ---
    # Phase 2 addition, and the check that makes C2's failure message actionable:
    # C2 can only say "the migration did not run", this says which revision the
    # database is actually parked on.
    stamped = db.execute(
        sa.text("SELECT version_num FROM alembic_version")
    ).scalars().all()
    if len(stamped) != 1:
        report.record(
            _FAIL,
            "C3 alembic-head",
            f"expected exactly one stamped revision, found {len(stamped)}: "
            f"{stamped or '(none)'}. Two heads make `alembic upgrade head` fail, "
            f"which crash-loops the container (docker-entrypoint.sh runs it under "
            f"`set -eu`).",
        )
    elif stamped[0] != EXPECTED_ALEMBIC_HEAD:
        report.record(
            _FAIL,
            "C3 alembic-head",
            f"database is at {stamped[0]}, this code expects "
            f"{EXPECTED_ALEMBIC_HEAD}. Run `alembic upgrade head`.",
        )
    else:
        report.record(_PASS, "C3 alembic-head", f"at {EXPECTED_ALEMBIC_HEAD}")

    return schema_ok


def _check_tier_groups(report: Report) -> None:
    """C6. Every tier in the catalog must round-trip through a Cognito group.

    Phase 2 made ``cognito:groups`` the sole entitlement authority, which turns a
    missing tier->group mapping from a latent inconsistency into a silent
    entitlement DOWNGRADE: a user on a group-less tier resolves to the
    fail-closed default and loses everything that tier was supposed to grant.
    ``hexaware`` was in exactly that state before Phase 2 (``MERGE_NOTES.md``
    §2), so this is worth an assertion rather than a comment.

    Purely a code-level check — no database involved — which is why it runs even
    when the schema checks fail.
    """
    from app.core.entitlements import (
        TIER_PIPELINES,
        group_for_tier,
        resolve_tier_from_groups,
    )

    unmappable = [
        tier
        for tier in TIER_PIPELINES
        if resolve_tier_from_groups([group_for_tier(tier)]) != tier
    ]
    if unmappable:
        report.record(
            _FAIL,
            "C6 tier-group-round-trip",
            f"tier(s) {', '.join(sorted(unmappable))} have no Cognito group of "
            f"their own, so a user on them resolves to the default tier. Add the "
            f"group to entitlements._TIER_GROUP_PRECEDENCE AND to "
            f"infra/terraform/modules/cognito.",
        )
    else:
        report.record(
            _PASS,
            "C6 tier-group-round-trip",
            f"all {len(TIER_PIPELINES)} tiers round-trip through a group",
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

    # --- C4: every local row resolves to a live pool user ---
    local_rows = db.query(User).all()
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
            # The pool user was deleted and recreated, so the local row
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
        print("RESULT: FAILED")
        return EXIT_FAILED

    print("RESULT: PASSED")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
