"""Selectors for screens/01-auth.feature.md.

Mirrors that spec's `**Selectors:**` line. When a selector moves it moves here
once, not in every test that used it.
"""

EMAIL = 'input[type="email"]'
PASSWORD = 'input[type="password"]'
SIGN_IN = 'button:has-text("Sign in")'

WELCOME_HEADING = "Welcome back"
INVITE_ONLY_FOOTER = "Access is by invitation. Contact your administrator for an account."

# The dashboard is where a successful sign-in lands, so its heading is the
# assertion that the sign-in actually completed rather than merely navigated.
DASHBOARD_HEADING = "What would you like to build today?"
