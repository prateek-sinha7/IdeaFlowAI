"""Selectors for screens/01-auth.feature.md.

Mirrors that spec's `**Selectors:**` line. When a selector moves it moves here
once, not in every test that used it.
"""

# ── the sign-in form ─────────────────────────────────────────────────────────

EMAIL = 'input[type="email"]'
PASSWORD = 'input[type="password"]'
SIGN_IN = 'button:has-text("Sign in")'

WELCOME_HEADING = "Welcome back"
FORM_SUBTITLE = "Sign in to continue building with your AI delivery agents."
INVITE_ONLY_FOOTER = "Access is by invitation. Contact your administrator for an account."
EXPIRED_BANNER = "Your session expired. Please sign in again."
REDIRECTING = "Redirecting…"

# The marketing rail. Static, but asserted so a challenge screen can be shown to
# render in the SAME shell — a verification step that looks like a different app
# reads as a phishing page (S-01-19).
RAIL_EYEBROW = "AI DELIVERY, ORCHESTRATED"
RAIL_HEADING = "Ship faster with your agent workforce."

# ── the account menu (AppHeader) ─────────────────────────────────────────────

ACCOUNT_MENU = '[aria-label="Account menu"]'
LOG_OUT = 'button[role="menuitem"]:has-text("Log out")'

# ── after sign-in ────────────────────────────────────────────────────────────

# The dashboard heading is the assertion that sign-in actually COMPLETED, rather
# than merely navigated: the URL changes before the page has data.
DASHBOARD_HEADING = "What would you like to build today?"
