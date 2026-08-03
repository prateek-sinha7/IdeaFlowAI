#!/usr/bin/env python3
"""
Post-deployment user verification script.

Runs on the EC2 instance after deployment to ensure required admin and
enterprise users exist in the database. Creates them if missing.

Uses the backend's own SQLAlchemy models and security functions for consistency.

Preconditions:
  - Python 3.10+ available with the backend dependencies installed
  - DATABASE_URL environment variable set (or sourced from /etc/velocityai/app.env)
  - Postgres running
  - Backend code available for import (sys.path includes /opt/velocityai/backend)

Invocation via SSM (from CI/CD post-deploy):
  aws ssm send-command \
    --document-name AWS-RunShellScript \
    --instance-ids i-<instance-id> \
    --region <region> \
    --parameters 'commands=["bash -c \"cd /opt/velocityai && python3 /opt/velocityai/infra/scripts/post-deploy-verify-users.py\""]'

Or manually on the box:
  cd /opt/velocityai && python3 infra/scripts/post-deploy-verify-users.py
"""

import os
import sys
import logging
from datetime import datetime, timezone
import uuid

# ── Configure logging ───────────────────────────────────────────────────────
logging.basicConfig(
    format="[post-deploy-verify-users] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_env_file(path: str) -> None:
    """Load environment variables from a .env file (simple key=value parsing)."""
    if not os.path.isfile(path):
        return
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Strip surrounding quotes if present
                    value = value.strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")


def main():
    """Main entry point."""
    try:
        # ── 1. Load environment ─────────────────────────────────────────
        # Try to load /etc/velocityai/app.env first (deployed config)
        load_env_file("/etc/velocityai/app.env")

        # Fallback: look for backend/.env in the project
        load_env_file("backend/.env")

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            logger.error(
                "DATABASE_URL not set. Set it in environment or /etc/velocityai/app.env"
            )
            return 1

        logger.info("DATABASE_URL loaded")

        # ── 2. Add backend to sys.path so we can import app modules ──────
        backend_path = os.path.abspath("backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)

        # ── 3. Import backend models and security ───────────────────────
        try:
            from app.models.user import User
            from app.models.database import SessionLocal
            from app.core.security import hash_password
        except ImportError as e:
            logger.error(
                f"Failed to import backend modules: {e}\n"
                f"Ensure you're running from the project root or that backend dependencies are installed."
            )
            return 1

        # ── 4. Create database session ──────────────────────────────────
        try:
            logger.info("Connecting to database...")
            session = SessionLocal()
            # Quick connectivity check
            session.execute("SELECT 1")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return 1

        # ── 5. Check/create admin user ──────────────────────────────────
        logger.info("Checking for admin user...")
        try:
            admin_user = session.query(User).filter(User.is_admin == True).first()
            if admin_user:
                logger.info(f"✓ Admin user exists: {admin_user.email}")
            else:
                logger.warning("✗ No admin user found — creating one...")
                admin_email = "admin@velocityai.local"
                admin_password = os.getenv("ADMIN_PASSWORD", uuid.uuid4().hex[:16])
                admin_user = User(
                    id=str(uuid.uuid4()),
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    is_admin=True,
                    tier="enterprise",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(admin_user)
                session.commit()
                logger.info(f"✓ Admin user created: {admin_email}")
                logger.info(f"  Temporary password (store securely): {admin_password}")
        except Exception as e:
            logger.error(f"Error checking/creating admin user: {e}", exc_info=True)
            session.rollback()
            return 1

        # ── 6. Check/create enterprise user ────────────────────────────
        logger.info("Checking for enterprise user...")
        try:
            enterprise_user = (
                session.query(User).filter(User.tier == "enterprise")
                .filter(User.is_admin == False)
                .first()
            )
            if enterprise_user:
                logger.info(f"✓ Enterprise user exists: {enterprise_user.email}")
            else:
                logger.warning("✗ No non-admin enterprise user found — creating one...")
                enterprise_email = "enterprise@velocityai.local"
                enterprise_password = os.getenv(
                    "ENTERPRISE_PASSWORD", uuid.uuid4().hex[:16]
                )
                enterprise_user = User(
                    id=str(uuid.uuid4()),
                    email=enterprise_email,
                    password_hash=hash_password(enterprise_password),
                    is_admin=False,
                    tier="enterprise",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(enterprise_user)
                session.commit()
                logger.info(f"✓ Enterprise user created: {enterprise_email}")
                logger.info(f"  Temporary password (store securely): {enterprise_password}")
        except Exception as e:
            logger.error(f"Error checking/creating enterprise user: {e}", exc_info=True)
            session.rollback()
            return 1

        logger.info("Post-deployment user verification complete")
        session.close()
        return 0

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
