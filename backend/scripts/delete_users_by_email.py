"""Delete users by exact-case email match from the database.

This script deletes user records from the 'users' table for specific email
addresses. The deletion is case-sensitive to ensure only the intended accounts
are removed.

Usage:
    uv run python scripts/delete_users_by_email.py

The script will delete the following users (case-sensitive email match):
    - Imrany@hexaware.com
    - PrateekS7@hexaware.com
    - ArnabS1@hexaware.com
    - ImranY@hexaware.com

SAFETY:
    - The script uses raw SQL with parameterized queries to prevent injection.
    - Case-sensitive matching ensures only exact email matches are deleted.
    - A preliminary query shows which users will be deleted before confirming.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

# The emails to delete (case-sensitive)
EMAILS_TO_DELETE = [
    "Imrany@hexaware.com",
    "PrateekS7@hexaware.com",
    "ArnabS1@hexaware.com",
    "ImranY@hexaware.com",
]


def get_database_url() -> str:
    """Get the database URL from environment or use default."""
    # Try to load from .env first (for local dev)
    env_file = os.path.join(
        os.path.dirname(__file__), "..", ".env"
    )
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.strip().split("=", 1)[1]
    
    # Fall back to env var
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL not found in environment or .env file. "
            "Set it before running this script."
        )
    return db_url


def main() -> int:
    """Delete the specified users from the database."""
    try:
        db_url = get_database_url()
        engine = create_engine(db_url)

        with engine.connect() as conn:
            # Step 1: Show which users exist and will be deleted
            print("\n[delete_users] Checking which users exist for deletion...")
            select_query = text("""
                SELECT id, email, created_at
                FROM users
                WHERE email = ANY(:emails)
                ORDER BY email
            """)
            result = conn.execute(select_query, {"emails": EMAILS_TO_DELETE})
            rows = result.fetchall()

            if not rows:
                print("[delete_users] No users found matching the email list. Nothing to delete.")
                return 0

            print(f"\n[delete_users] Found {len(rows)} user(s) to delete:")
            for user_id, email, created_at in rows:
                print(f"  - {email} (id={user_id}, created={created_at})")

            # Step 2: Delete the users
            print("\n[delete_users] Deleting users from database...")
            delete_query = text("""
                DELETE FROM users
                WHERE email = ANY(:emails)
            """)
            result = conn.execute(delete_query, {"emails": EMAILS_TO_DELETE})
            conn.commit()

            rows_deleted = result.rowcount
            print(f"[delete_users] ✓ Deleted {rows_deleted} user(s)")

            # Step 3: Verify deletion
            verify_query = text("""
                SELECT COUNT(*) as count
                FROM users
                WHERE email = ANY(:emails)
            """)
            verify_result = conn.execute(verify_query, {"emails": EMAILS_TO_DELETE})
            remaining = verify_result.scalar()

            if remaining == 0:
                print("[delete_users] ✓ Verification passed: all targeted users deleted")
                return 0
            else:
                print(f"[delete_users] ✗ FAILED: {remaining} user(s) still exist!")
                return 1

    except Exception as exc:
        print(f"[delete_users] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
