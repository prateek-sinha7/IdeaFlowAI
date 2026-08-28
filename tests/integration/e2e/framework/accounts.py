"""The seeded QA accounts.

Provisioned by `backend/scripts/seed_test_users.py`. That script reads the same
`E2E_BASE_PASSWORD` variable this file does — overriding it in one place and not
the other is the obvious way to get four confusing auth failures.
"""

from __future__ import annotations

import os

PASSWORD = os.environ.get("E2E_BASE_PASSWORD", "flowin-e2e-pass")

ADMIN = "qa-admin@flowinqa.com"
ENTERPRISE = "qa-enterprise@flowinqa.com"
PRO = "qa-pro@flowinqa.com"
BASIC = "qa-basic@flowinqa.com"

BY_ROLE = {
    "admin": ADMIN,
    "enterprise": ENTERPRISE,
    "pro": PRO,
    "basic": BASIC,
}

# The key the app writes on a successful sign-in. Read it as a BOOLEAN in tests
# — never return the value, it would land verbatim in the run's steps.json.
AUTH_TOKEN_KEY = "auth_token"
