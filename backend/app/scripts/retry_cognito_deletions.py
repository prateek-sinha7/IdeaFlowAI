"""Retry the ``AdminDeleteUser`` half of a user delete that failed at Cognito.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 3, Decision 6): *"the delete ordering, pending_cognito_deletions retry
command (scripts/retry_cognito_deletions.py)."*

Why this lives under ``app/scripts/`` and not ``backend/scripts/``
------------------------------------------------------------------
Same reasoning as ``app/scripts/reconcile_cognito_users.py`` (recorded in
``MERGE_NOTES.md`` §8): ``backend/Dockerfile`` COPYs only ``app/``, ``agents/``
and ``alembic/`` into the runtime image, so nothing under ``backend/scripts/``
exists on a deployed box. This script needs BOTH the live production database
(to read/clear ``pending_cognito_deletions``) and the live Cognito pool — both
of which are only reachable from inside the running backend container, since
nobody holds direct database or EC2/SSH access to any environment. Invoke it
the same way ``recover_admin.py`` used to be invoked, and the way
``reconcile_cognito_users.py`` is invoked today:

    docker compose exec backend python -m app.scripts.retry_cognito_deletions --report
    docker compose exec backend python -m app.scripts.retry_cognito_deletions --apply

over an SSM Session Manager shell, or scripted through the same
``.github/actions/ssm-run`` composite action ``cognito-reconcile.yml`` uses, if
a dedicated workflow is ever wanted. Not wired to one yet — pending rows should
be rare (most ``AdminDeleteUser`` calls succeed first try), so an
operator-invoked script is proportionate for now; ``reconcile_cognito_users.py``
graduated to its own workflow because that check runs routinely, not because a
script under ``app/scripts/`` requires one.

Why a pending row can exist at all
-----------------------------------
``api/admin.py::delete_user`` disables the pool user, deletes every local
dependent row and the ``User`` row itself INSIDE one transaction, and only
THEN calls the final ``AdminDeleteUser`` (see
``core/cognito_admin.py::delete_user``'s docstring for the full ordering and
why disable-before-delete makes this safe). If that last call fails —
throttling, a transient AWS error, a network blip — the local delete has
ALREADY committed. There is nothing left to roll back, and no local user row
to retry the delete "from": the account is gone locally and disabled at the
provider, which is a correctly-locked-out state either way. The only
outstanding work is finishing the pool-side cleanup, which this script does.

USAGE (inside the backend container)
-------------------------------------
    # Report what's pending, make no changes:
    python -m app.scripts.retry_cognito_deletions --report

    # Retry every pending row, remove the ones that now succeed:
    python -m app.scripts.retry_cognito_deletions --apply

    # Give up on rows that have failed too many times (default: 10) and
    # report them for manual console cleanup instead of retrying forever:
    python -m app.scripts.retry_cognito_deletions --apply --max-attempts 10
"""

import argparse
import time

from botocore.exceptions import ClientError

from app.core import cognito
from app.core.config import settings
from app.models.database import SessionLocal
from app.models.pending_cognito_deletion import PendingCognitoDeletion

EXIT_OK = 0
EXIT_CANNOT_RUN = 1

DEFAULT_MAX_ATTEMPTS = 10

#: Ceiling on the pause between retries, in seconds. Five minutes: long enough
#: to ride out an AWS throttle window, short enough that a run draining a few
#: rows still finishes inside the workflow's 15-minute timeout.
BACKOFF_CAP_SECONDS = 300


def backoff_seconds(attempt: int) -> int:
    """Seconds to wait after a FAILED attempt number ``attempt`` (1-based).

    ``min(2 * attempt, 300)`` — arithmetic growth, capped. Note the label
    "exponential backoff" is a misnomer for this curve: doubling the ATTEMPT
    NUMBER is linear (2s, 4s, 6s, 8s…), not exponential. The previous
    implementation used ``2 ** (attempt - 1)``, which really was exponential and
    reached the 300s cap by attempt 10; this reaches it only at attempt 150, so
    with ``--max-attempts 3`` the realistic waits are 2s, 4s and 6s.

    That is the intended trade for this job: the pending queue is drained by a
    scheduled run every day, so a row that fails today gets its real backoff from
    the 24-hour gap between runs, not from this sleep. The sleep only needs to
    avoid hammering AdminDeleteUser within a single pass.
    """
    return min(2 * attempt, BACKOFF_CAP_SECONDS)


def _try_delete(cognito_sub: str) -> str | None:
    """Attempt ``AdminDeleteUser`` by the row's ``cognito_sub``. Error code or None.

    Uses ``cognito_sub`` as ``Username`` -- not email, which this table never
    stores (only its hash). ``cognito.admin_delete_user`` accepts either
    identifier on this pool (``username_attributes = ["email"]`` means
    Cognito's canonical ``Username`` equals ``sub``), so this resolves exactly
    like every other JIT/reconciliation path that identifies a user by ``sub``
    alone -- see ``core/cognito.py::admin_get_user``'s docstring for the alias
    contract this relies on.
    """
    try:
        cognito.admin_delete_user(cognito_sub)
        return None
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UserNotFoundException":
            return None
        return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.retry_cognito_deletions",
        description="Retry AdminDeleteUser for rows in pending_cognito_deletions.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--report", action="store_true", help="List pending rows; write nothing."
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Retry AdminDeleteUser for every pending row under --max-attempts.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=(
            f"Stop retrying (and flag for manual cleanup) a row past this many "
            f"attempts. Default {DEFAULT_MAX_ATTEMPTS}."
        ),
    )
    args = parser.parse_args(argv)

    print("Pending Cognito deletion retry")
    print(f"  COGNITO_USER_POOL_ID = {settings.COGNITO_USER_POOL_ID or '(unset)'}")
    print(f"  mode                 = {'apply' if args.apply else 'report'}")

    if not settings.COGNITO_USER_POOL_ID:
        print(
            "\nCOGNITO_USER_POOL_ID is unset — cannot reach the pool. Check "
            "/etc/velocityai/app.env (the secrets-loader allowlist must include "
            "the COGNITO_* names)."
        )
        return EXIT_CANNOT_RUN

    db = SessionLocal()
    try:
        pending = (
            db.query(PendingCognitoDeletion)
            .order_by(PendingCognitoDeletion.created_at)
            .all()
        )

        if not pending:
            print("\nNothing pending.")
            return EXIT_OK

        retryable = [p for p in pending if p.attempts < args.max_attempts]
        exhausted = [p for p in pending if p.attempts >= args.max_attempts]

        print(f"\n{len(pending)} row(s) pending ({len(exhausted)} exhausted retries)")

        if exhausted:
            print("\nEXHAUSTED — needs manual console cleanup:")
            for row in exhausted:
                print(
                    f"  {row.id}  user_id_snapshot={row.user_id_snapshot} "
                    f"cognito_sub={row.cognito_sub} attempts={row.attempts} "
                    f"last_error={row.last_error}"
                )

        if not args.apply:
            if retryable:
                print(f"\n--report mode: {len(retryable)} row(s) WOULD be retried.")
                for row in retryable:
                    print(
                        f"  {row.id}  user_id_snapshot={row.user_id_snapshot} "
                        f"cognito_sub={row.cognito_sub} attempts={row.attempts}"
                    )
            return EXIT_OK

        succeeded = 0
        still_failing = 0
        last_index = len(retryable) - 1
        for index, row in enumerate(retryable):
            error_code = _try_delete(row.cognito_sub)
            row.attempts += 1
            if error_code is None:
                print(f"  OK      {row.id} (cognito_sub={row.cognito_sub})")
                db.delete(row)
                succeeded += 1
            else:
                row.last_error = error_code
                print(
                    f"  FAILED  {row.id} (cognito_sub={row.cognito_sub}): "
                    f"{error_code} (attempt {row.attempts})"
                )
                still_failing += 1
            db.commit()

            # Back off only after a FAILURE, and never after the final row.
            # The previous version slept after EVERY row, successes included, so
            # a queue of healthy deletions paid the whole backoff ladder for
            # nothing and could push a large drain past the workflow timeout.
            # The wait is also scaled by the row that JUST failed, not by the
            # next one, which is the only attempt count actually known here.
            if error_code is not None and index < last_index:
                delay = backoff_seconds(row.attempts)
                print(f"  Waiting {delay}s before the next row...")
                time.sleep(delay)

        print(
            f"\n{succeeded} resolved, {still_failing} still pending, "
            f"{len(exhausted)} exhausted"
        )
        return EXIT_OK if still_failing == 0 else EXIT_CANNOT_RUN
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
