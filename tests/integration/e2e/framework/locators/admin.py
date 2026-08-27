"""Selectors for screens/11-admin.feature.md.

`/admin` bypasses the `[...view]` catch-all and renders its OWN shell — no app
nav, no account menu. Nothing about the shared chrome applies here, which is why
this has its own locator module rather than reusing `shell`.

The per-row controls are the one well-labelled part of the screen: each carries
an `aria-label` naming the user it acts on, so a row's controls can be addressed
without depending on table order.
"""

HEADING = "Admin Dashboard"
BADGE = "ADMIN"
SUBTITLE = "VelocityAI · User Management"

BACK_TO_APP = 'button:has-text("← Back to app")'
LOGOUT = 'button:text-is("Logout")'
ADD_USER = 'button:text-is("Add user")'
SEARCH = 'input[name="admin-user-search"]'

TILES = ["TOTAL USERS", "BASIC", "PRO", "ENTERPRISE", "ADMINS"]


def delete_user(email: str) -> str:
    return f'[aria-label="Delete {email}"]'


def grant_admin(email: str) -> str:
    return f'[aria-label="Grant admin access to {email}"]'


def revoke_admin(email: str) -> str:
    return f'[aria-label="Remove admin access from {email}"]'


def row(email: str) -> str:
    """The table row for one user, matched on the email it displays."""
    return f'tr:has-text("{email}")'
