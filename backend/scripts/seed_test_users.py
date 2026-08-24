"""
Seed deterministic QA users for the live Playwright E2E suite.

Registration is 403-disabled and user creation is admin-only, so an automated
login needs out-of-band users. This script idempotently upserts one user per
tier (plus an admin) with a known password.

COGNITO MIGRATION (``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 5): this
script no longer writes ``password_hash`` unconditionally. It branches on
``settings.AUTH_PROVIDER``, exactly like ``app/api/admin.py::create_user`` and
``app/scripts/bootstrap_admin.py``, so seeded users are provisioned through the
SAME path real users are:

    AUTH_PROVIDER=local    -> local bcrypt hash (unchanged legacy behaviour)
    AUTH_PROVIDER=cognito  -> AdminCreateUser + AdminSetUserPassword(permanent)
                              + AdminAddUserToGroup(tier [+ admins])
                              -> local row with cognito_sub / auth_provider

Provisioning through the real path is the point: a QA user created by a
divergent code path would not exercise the credential flow under test, and
would silently drift from production semantics.

Usage (from backend/):
    uv run python scripts/seed_test_users.py
    E2E_BASE_PASSWORD=secret uv run python scripts/seed_test_users.py

Creates:
    qa-basic@flowinqa.com       (tier=basic)
    qa-pro@flowinqa.com         (tier=pro)
    qa-enterprise@flowinqa.com  (tier=enterprise)
    qa-admin@flowinqa.com       (tier=enterprise, is_admin=True)

Password for all: env E2E_BASE_PASSWORD or "flowin-e2e-pass".

NOTE on the Cognito path: the pool's password policy (12+ chars, mixed
case/digits/symbols) applies. The default "flowin-e2e-pass" does NOT satisfy
it, so set E2E_BASE_PASSWORD to a compliant value when AUTH_PROVIDER=cognito;
the script fails loudly with Cognito's own InvalidPasswordException rather than
silently creating an unusable account.

Safe to re-run: existing users are reconciled in place (password + tier +
group membership reset).
"""
import os
import sys

# Make app importable + run alembic-relative paths from backend/.
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from datetime import datetime, timezone  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

PASSWORD = os.environ.get("E2E_BASE_PASSWORD", "flowin-e2e-pass")

SEED_USERS = [
    {"email": "qa-basic@flowinqa.com", "tier": "basic", "is_admin": False},
    {"email": "qa-pro@flowinqa.com", "tier": "pro", "is_admin": False},
    {"email": "qa-enterprise@flowinqa.com", "tier": "enterprise", "is_admin": False},
    {"email": "qa-admin@flowinqa.com", "tier": "enterprise", "is_admin": True},
]

# Mirrors app/api/admin.py's write-path map. Duplicated deliberately rather
# than imported: this is an operational script that must keep working even if
# the admin router is refactored, and the mapping is a stable published
# contract (the Terraform module creates exactly these group names).
_TIER_TO_GROUP = {
    "basic": "flowin-tier-basic",
    "pro": "flowin-tier-pro",
    "enterprise": "flowin-tier-enterprise",
}


def _seed_local(db, spec: dict, pw_hash: str) -> str:
    """Legacy path: local bcrypt credential owned by this database."""
    user = db.query(User).filter(User.email == spec["email"]).one_or_none()
    if user is None:
        db.add(
            User(
                email=spec["email"],
                password_hash=pw_hash,
                tier=spec["tier"],
                is_admin=spec["is_admin"],
                auth_provider="local",
            )
        )
        return "created"
    user.password_hash = pw_hash
    user.tier = spec["tier"]
    user.is_admin = spec["is_admin"]
    user.auth_provider = "local"
    return "updated"


def _seed_cognito(db, spec: dict) -> str:
    """Cognito path: provision the pool user, then mirror it locally."""
    from botocore.exceptions import ClientError

    from app.core import cognito
    from app.core.entitlements import ADMIN_GROUP

    email = spec["email"]

    # --- Pool side (idempotent) ---
    cognito_sub: str | None = None
    try:
        create_resp = cognito.admin_create_user(email)
        cognito_sub = next(
            attr["Value"]
            for attr in create_resp["User"]["Attributes"]
            if attr["Name"] == "sub"
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "UsernameExistsException":
            raise
        # Already present from a previous run — read the sub back so the local
        # row can still be reconciled to the correct principal.
        cognito_sub = cognito.admin_get_user_sub(email)

    # Permanent so the seeded account is immediately usable — an E2E run cannot
    # answer a NEW_PASSWORD_REQUIRED challenge interactively.
    cognito.admin_set_user_password(email, PASSWORD, permanent=True)

    # Reconcile group membership: drop every other tier group so a re-run that
    # changes a seed user's tier doesn't leave them in two tier groups (where
    # the lower precedence would silently win).
    target_group = _TIER_TO_GROUP[spec["tier"]]
    for tier_name, group in _TIER_TO_GROUP.items():
        if group == target_group:
            continue
        try:
            cognito.admin_remove_user_from_group(email, group)
        except ClientError:
            pass  # not a member — nothing to remove
    cognito.admin_add_user_to_group(email, target_group)

    if spec["is_admin"]:
        cognito.admin_add_user_to_group(email, ADMIN_GROUP)
    else:
        try:
            cognito.admin_remove_user_from_group(email, ADMIN_GROUP)
        except ClientError:
            pass

    # --- Local side ---
    user = db.query(User).filter(User.email == email).one_or_none()
    now = datetime.now(timezone.utc)
    if user is None:
        db.add(
            User(
                email=email,
                password_hash=None,
                cognito_sub=cognito_sub,
                auth_provider="cognito",
                tier=spec["tier"],
                is_admin=spec["is_admin"],
                roles_synced_at=now,
            )
        )
        return "created"

    user.password_hash = None
    user.cognito_sub = cognito_sub
    user.auth_provider = "cognito"
    user.tier = spec["tier"]
    user.is_admin = spec["is_admin"]
    user.roles_synced_at = now
    # Any outstanding token predating this reconciliation must not survive a
    # tier/role change applied above.
    user.tokens_valid_from = now
    return "updated"


def main() -> int:
    use_cognito = settings.AUTH_PROVIDER.lower() == "cognito"

    if use_cognito and not settings.COGNITO_USER_POOL_ID:
        print(
            "ERROR: AUTH_PROVIDER=cognito but COGNITO_USER_POOL_ID is unset. "
            "Check /etc/velocityai/app.env (the SSM secrets-loader allowlist "
            "must include the COGNITO_* names).",
            file=sys.stderr,
        )
        return 1

    print(f"Seeding via the {'COGNITO' if use_cognito else 'LOCAL'} path.")

    db = SessionLocal()
    created, updated = 0, 0
    try:
        pw_hash = hash_password(PASSWORD) if not use_cognito else ""
        for spec in SEED_USERS:
            if use_cognito:
                action = _seed_cognito(db, spec)
            else:
                action = _seed_local(db, spec, pw_hash)
            if action == "created":
                created += 1
            else:
                updated += 1
            print(
                f"  {action}: {spec['email']} "
                f"(tier={spec['tier']}, admin={spec['is_admin']})"
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"ERROR seeding users: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"\nDone. {created} created, {updated} updated. Password: {PASSWORD!r}")
    print("Login: POST /api/auth/login {email, password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
