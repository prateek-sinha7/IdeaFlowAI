"""Selectors and timings for screens/19-toasts-and-dialogs.feature.md.

**Two toast families, two timeouts.** An admin toast clears after 3500ms; a
run-completion toast after 7000ms. A shared wait helper must be parameterised —
a hard-coded 7000 makes every admin assertion flaky-slow, and a hard-coded 3500
makes every completion assertion flaky-fast.
"""

ADMIN_TIMEOUT_MS = 3500
RUN_TIMEOUT_MS = 7000

# Toasts carry no testid; they are the live region the app announces through.
TOAST = '[role="status"], [role="alert"], [aria-live="polite"] >> visible=true'

RUN_COMPLETED = "Run completed"
OPEN = "Open"

ADMIN_MESSAGES = {
    "grant": "Admin access granted",
    "revoke": "Admin access removed",
    "tier": "Tier updated to",
    "create": "created",
    "delete": "User deleted",
}

# ── the delete-user confirm ──────────────────────────────────────────────────

DELETE_DIALOG = "Delete user?"
DELETE_WARNING = "cannot be undone"
CANCEL = 'button:text-is("Cancel")'
CONFIRM_DELETE = 'button:text-is("Delete")'
