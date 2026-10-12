"""The seeded QA accounts.

Provisioned by `backend/scripts/seed_test_users.py`. That script reads the same
`E2E_BASE_PASSWORD` variable this file does — overriding it in one place and not
the other is the obvious way to get four confusing auth failures.
"""

from __future__ import annotations

import os

PASSWORD = os.environ.get("E2E_BASE_PASSWORD", "Velocity!Dev2026")

ADMIN = "admin@velocity.ai"
ENTERPRISE = "enterprise@velocity.ai"
PRO = "pro@velocity.ai"
BASIC = "basic@velocity.ai"

BY_ROLE = {
    "admin": ADMIN,
    "enterprise": ENTERPRISE,
    "pro": PRO,
    "basic": BASIC,
}

# The key the app writes on a successful sign-in. Read it as a BOOLEAN in tests
# — never return the value, it would land verbatim in the run's steps.json.
AUTH_TOKEN_KEY = "auth_token"
