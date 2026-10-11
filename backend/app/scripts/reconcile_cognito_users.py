"""Reconcile the local ``users`` table against the Cognito user pool.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 2). Cognito is the sole authentication authority and the local ``users``
row is a MAPPING plus an advisory projection — which means the two stores can
drift, and nothing on the request path notices most kinds of drift.

Why this lives under ``app/scripts/`` and not ``backend/scripts/``
------------------------------------------------------------------
The brief names the path ``scripts/reconcile_cognito_users.py``. It cannot go
there and still be runnable: ``backend/Dockerfile`` COPYs only ``app/``,
``agents/``, ``alembic/`` and one named thumbnail generator into the runtime
image, so nothing else under ``backend/scripts/`` exists on a deployed box. And
a deployed box is the ONLY place this can run — nobody holds EC2/SSH or direct
database access to any environment; the sole channel is SSM RunCommand from the
CI OIDC role (see ``.github/workflows/cognito-reconcile.yml``).

So it sits beside the package the image ships, invoked as
``python -m app.scripts.reconcile_cognito_users``, exactly as
``app/scripts/recover_admin.py`` was before Phase 1 deleted it. Same
``DATABASE_URL``, same ``app.env``, same Cognito config as the live
application — no second, divergent connection path. Recorded in
``MERGE_NOTES.md``.

How this differs from ``backend/scripts/verify_cognito_cutover.py``
------------------------------------------------------------------
That script is a one-time GATE: it answers "is this deployment safe to cut over"
and exits non-zero if not. This one is an ONGOING reconciler, meant to be run on
demand or on a schedule, and it can optionally REPAIR one specific class of
drift. They stay separate deliberately: a cutover gate that also mutated data
would be a bad thing to run twice, and a routine reconciler that exited non-zero
on informational findings would be a bad thing to schedule.

The three drift classes, and why they are treated so differently
---------------------------------------------------------------
1. **In the DB, absent or disabled in the pool.** The dangerous one. The local
   row still authorizes: ``resolve_principal`` resolves it, and any unexpired
   access token the user holds keeps working until its own ``exp`` (AWS documents
   that a Cognito access token stays offline-verifiable regardless of pool
   state). So deleting or disabling a user in the AWS console ALONE does not lock
   them out promptly. ``--fix-disabled`` closes that.

2. **In the pool, absent from the DB.** Purely INFORMATIONAL — and this is what
   Phase 2 changes. Before just-in-time provisioning such a user was an "orphan":
   able to authenticate against Cognito and unable to use the application, ever.
   It was a real defect to hunt down, and ``api/auth.py`` carried a dedicated
   audit reason for it. Their row is now created on first successful sign-in
   (``core/provisioning.py``), so the state is self-healing and reporting it is a
   courtesy rather than an alarm.

3. **Disabled in the pool, active in the DB.** A sub-case of (1), reported
   separately because the remedy differs: the account still exists, so the
   operator may be part-way through a deliberate suspension rather than cleaning
   up after a deletion.

Why ``--fix-disabled`` only ever disables
-----------------------------------------
It never re-ENABLES, never deletes a local row, and never creates one. Each of
those would be an authority inversion: re-enabling from pool state would undo a
deliberate local suspension, and deleting a local row would destroy everything
keyed on ``users.id`` (runs, chats, artifacts, API keys) on the strength of a
single API read. Disabling is the only repair that is both fail-safe and
reversible, and an operator reverses it through the audited admin surface.

USAGE
-----
    # On a deployed box, inside the backend container:
    python -m app.scripts.reconcile_cognito_users --report
    python -m app.scripts.reconcile_cognito_users --fix-disabled

Exit codes: 0 = ran successfully (whatever it found), 1 = could NOT run (no pool
configured, or the pool was unreachable). Findings are not failures — a non-zero
exit is reserved for "the check itself did not happen", so a red run always means
the same thing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.core.config import settings
from app.core.provisioning import STATUS_ACTIVE, STATUS_DISABLED
from app.models.database import SessionLocal
from app.models.user import User

EXIT_OK = 0
EXIT_CANNOT_RUN = 1


def _pool_index() -> dict[str, dict]:
    """Every pool user, indexed by ``sub``.

    Keyed on ``sub`` rather than email because ``sub`` is the join key the
    application actually uses (``users.cognito_sub``). An email-keyed index would
    silently mis-reconcile the sub-reuse case: a pool user deleted and recreated
    at the same address gets a NEW ``sub``, so email keying would call that pair
    "matched" when the local row in fact points at a principal that no longer
    exists.
    """
    from app.core import cognito

    index: dict[str, dict] = {}
    for row in cognito.list_pool_users():
        attributes = cognito.user_attributes(row)
        sub = attributes.get("sub")
        if sub:
            index[sub] = {
                "email": attributes.get("email", row.get("Username", "")),
                "enabled": bool(row.get("Enabled", True)),
            }
    return index


def _reconcile(db, *, fix_disabled: bool) -> bool:
    """Reconcile and return True if drift was found, False otherwise."""
    pool = _pool_index()
    local_users = db.query(User).all()
    local_subs = {u.cognito_sub for u in local_users if u.cognito_sub}

    missing_at_provider: list[User] = []
    disabled_at_provider: list[User] = []
    already_disabled_locally: list[User] = []

    for user in local_users:
        if user.status != STATUS_ACTIVE:
            already_disabled_locally.append(user)
            continue
        pool_user = pool.get(user.cognito_sub) if user.cognito_sub else None
        if pool_user is None:
            missing_at_provider.append(user)
        elif not pool_user["enabled"]:
            disabled_at_provider.append(user)

    unprovisioned = [
        (sub, info["email"]) for sub, info in pool.items() if sub not in local_subs
    ]

    print("\nACTIVE locally, NO live pool user (can still act — actionable)")
    if missing_at_provider:
        for user in missing_at_provider:
            print(f"  MISSING-AT-POOL      {user.id}  {user.email}")
    else:
        print("  none")

    print("\nACTIVE locally, DISABLED in the pool (actionable)")
    if disabled_at_provider:
        for user in disabled_at_provider:
            print(f"  DISABLED-AT-POOL     {user.id}  {user.email}")
    else:
        print("  none")

    print("\nIn the pool, no local row (informational — JIT provisions on login)")
    if unprovisioned:
        for sub, email in unprovisioned:
            print(f"  NOT-YET-PROVISIONED  {email}  (sub={sub})")
    else:
        print("  none")

    actionable = missing_at_provider + disabled_at_provider
    has_drift = bool(actionable or unprovisioned)

    print(f"\nAlready disabled locally: {len(already_disabled_locally)}")
    print(
        f"Totals: {len(local_users)} local row(s), {len(pool)} pool user(s), "
        f"{len(actionable)} actionable"
    )
    print(f"\n{'DRIFT' if has_drift else 'NO_DRIFT'}")

    if not fix_disabled:
        if actionable:
            print(
                f"\n--report mode: {len(actionable)} row(s) WOULD be disabled. "
                "Re-run with --fix-disabled to apply."
            )
        return has_drift

    if not actionable:
        print("\nNothing to fix.")
        return has_drift

    for user in actionable:
        user.status = STATUS_DISABLED
        # Advance the blanket-revocation cutoff in the SAME transaction as the
        # status flip. `status` stops the next credential RESOLUTION; this
        # additionally invalidates every token already issued, which is what
        # makes the disable effective on the paths that check the cutoff. Doing
        # one without the other is exactly the half-applied disable that the
        # status column exists to backstop.
        user.tokens_valid_from = datetime.now(timezone.utc)
        # Drop the stored refresh token too, so a silent POST /api/auth/refresh
        # cannot mint a fresh access token for an account just declared gone.
        user.encrypted_cognito_refresh_token = None
    db.commit()

    print(f"\nDisabled {len(actionable)} local row(s):")
    for user in actionable:
        print(f"  {user.id}  {user.email}")
    print(
        "\nThese users cannot authenticate until an admin re-enables them. "
        "Re-enable through the admin API, not this script — see the module "
        "docstring."
    )

    return has_drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.reconcile_cognito_users",
        description="Reconcile local users against the Cognito user pool.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--report", action="store_true", help="Report drift; write nothing."
    )
    mode.add_argument(
        "--fix-disabled",
        action="store_true",
        help=(
            "Report, and set users.status='disabled' on local rows Cognito "
            "confirms are absent or disabled. Never re-enables, never deletes."
        ),
    )
    args = parser.parse_args(argv)

    print("Cognito <-> local user reconciliation")
    print(f"  COGNITO_USER_POOL_ID = {settings.COGNITO_USER_POOL_ID or '(unset)'}")
    print(
        f"  mode                 = {'fix-disabled' if args.fix_disabled else 'report'}"
    )

    if not settings.COGNITO_USER_POOL_ID:
        print(
            "\nCOGNITO_USER_POOL_ID is unset — cannot reach the pool. Check "
            "/etc/velocityai/app.env (the secrets-loader allowlist must include "
            "the COGNITO_* names)."
        )
        return EXIT_CANNOT_RUN

    db = SessionLocal()
    try:
        _reconcile(db, fix_disabled=args.fix_disabled)
        # In --report mode, finding drift is not an error — it's informational.
        # The scheduled workflow will check for "DRIFT" in the output and fail the job if found.
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - reported, not raised; see docstring
        db.rollback()
        print(f"\nReconciliation could not complete: {exc}")
        return EXIT_CANNOT_RUN
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
