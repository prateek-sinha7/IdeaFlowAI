"""
Seed deterministic QA users for the live Playwright E2E suite.

Registration is 403-disabled and user creation is admin-only, so an automated
login needs out-of-band users. This script idempotently upserts one user per
tier (plus an admin) with a known password, by direct DB insert via the app's
own password hasher.

Usage (from backend/, python3.11, no venv):
    python3.11 scripts/seed_test_users.py
    E2E_BASE_PASSWORD=secret python3.11 scripts/seed_test_users.py   # custom pw

Creates:
    qa-basic@flowin.test       (tier=basic)
    qa-pro@flowin.test         (tier=pro)
    qa-enterprise@flowin.test  (tier=enterprise)
    qa-admin@flowin.test       (tier=enterprise, is_admin=True)

Password for all: env E2E_BASE_PASSWORD or "flowin-e2e-pass".
Safe to re-run: existing users are updated in place (password + tier reset).
"""
import os
import sys

# Make app importable + run alembic-relative paths from backend/.
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from app.models.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.core.security import hash_password  # noqa: E402

PASSWORD = os.environ.get("E2E_BASE_PASSWORD", "flowin-e2e-pass")

SEED_USERS = [
    {"email": "qa-basic@flowin.test", "tier": "basic", "is_admin": False},
    {"email": "qa-pro@flowin.test", "tier": "pro", "is_admin": False},
    {"email": "qa-enterprise@flowin.test", "tier": "enterprise", "is_admin": False},
    {"email": "qa-admin@flowin.test", "tier": "enterprise", "is_admin": True},
]


def main() -> int:
    db = SessionLocal()
    created, updated = 0, 0
    try:
        pw_hash = hash_password(PASSWORD)
        for spec in SEED_USERS:
            user = db.query(User).filter(User.email == spec["email"]).one_or_none()
            if user is None:
                user = User(
                    email=spec["email"],
                    password_hash=pw_hash,
                    tier=spec["tier"],
                    is_admin=spec["is_admin"],
                )
                db.add(user)
                created += 1
                action = "created"
            else:
                user.password_hash = pw_hash
                user.tier = spec["tier"]
                user.is_admin = spec["is_admin"]
                updated += 1
                action = "updated"
            print(f"  {action}: {spec['email']} (tier={spec['tier']}, admin={spec['is_admin']})")
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
