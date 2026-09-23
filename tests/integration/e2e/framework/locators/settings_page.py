"""Selectors for screens/09-settings.feature.md.

Named `settings_page` and not `settings`: `framework.settings` is the suite's
own configuration module, and a second `settings` on the import path is a
confusion nobody needs at 2am.

**The tab testids do not match their route segments.** `tab-model` addresses
`/settings/ai-model` and `tab-limits` addresses `/settings/usage`. TABS below is
the mapping; never derive one from the other.

The three password fields carry NO `name` and no `id` — only a placeholder — so
they are addressed by placeholder rather than by a bare `input[type=password]`,
which would silently pick whichever one came first in the DOM.
"""

HEADING = "Account Settings"
SUBTITLE = (
    "Profile, model preference, usage limits, your agent constitution "
    "and sign-in security."
)

# (testid, visible label, route). Order is the strip's own order — Security sits
# last because it absorbed the retired standalone /settings/security page.
TABS = [
    ("tab-profile", "Profile", "/settings/profile"),
    ("tab-model", "AI Model", "/settings/ai-model"),
    ("tab-limits", "Usage & Limits", "/settings/usage"),
    ("tab-constitution", "Constitution", "/settings/constitution"),
    ("tab-security", "Security", "/settings/security"),
]


def tab(testid: str) -> str:
    return f'[data-testid="{testid}"]'


# ── Profile ──────────────────────────────────────────────────────────────────

CURRENT_PASSWORD = 'input[placeholder="Enter current password"]'
NEW_PASSWORD = 'input[placeholder="At least 8 characters"]'
CONFIRM_PASSWORD = 'input[placeholder="Re-enter new password"]'
CHANGE_PASSWORD = 'button:has-text("Change Password")'

# Client-side refusals, before the request is ever made.
ALL_FIELDS_REQUIRED = "All fields are required"
PASSWORDS_DO_NOT_MATCH = "New passwords do not match"

# ── AI Model ─────────────────────────────────────────────────────────────────

MODEL_SELECT = 'select[name="default-model"]'
SAVE_MODEL = 'button:has-text("Save")'
MODEL_NOTE = (
    "The default reasoning model applied across all your runs. Individual "
    "agents can still override this in the workflow composer."
)
SYSTEM_DEFAULT = ""  # the empty option value — "System Default (Claude Haiku 4.5)"

# ── Usage & Limits ───────────────────────────────────────────────────────────

MANAGE_PLAN = 'button:has-text("Manage plan")'
DELIVERABLE_ACCESS = "DELIVERABLE ACCESS"

# ── Constitution ─────────────────────────────────────────────────────────────

CONSTITUTION = 'textarea[name="constitution"]'
SAVE_CONSTITUTION = 'button:has-text("Save constitution")'
CONSTITUTION_CEILING = 4000

# ── Security ─────────────────────────────────────────────────────────────────

SECURITY_INTRO = "Add a second step to sign-in so a stolen password isn't enough on its own."
NOT_AVAILABLE = "Not available for this account"
# Retired copy (ISS-404): it claimed external credential management for an
# account whose password this application itself stores. Kept as the needle the
# ISS-404 regression test asserts is GONE, not as expected text.
EXTERNALLY_MANAGED = (
    "This account's credentials are managed outside the application, so "
    "two-factor authentication is configured separately."
)
LOCAL_ACCOUNT_NO_MFA = (
    "This is a local account, so there are no second-factor methods to manage "
    "here. Its password is stored by this application and can be changed from "
    "the Profile tab."
)
NO_METHODS = "No two-factor methods are enabled for this environment yet."
RECOVERY_NOTE = (
    "Because sign-in codes go to your email address, password resets are "
    "handled by an administrator rather than by email."
)
EMAIL_CODES = "Email codes"
AUTHENTICATOR = "Authenticator app"

# CSS uppercases the section captions; the DOM text is title case. Matching the
# spec's rendered "PASSWORD" finds nothing — Playwright reads textContent, which
# text-transform never touches.
PASSWORD_SECTION = "Password"

# Only rendered while there IS a constitution: it is the restore path for an
# account that started empty, since Save is disabled for blank content.
CLEAR_CONSTITUTION = 'button:has-text("Clear")'
