"""Selectors present on every signed-in screen.

Area-specific selectors do NOT belong here — they live in
`suites/<area>/locators.py`, beside the tests that use them. This file is only
for the chrome that wraps all of them: nav, account menu, toasts, the realtime
connection banner.
"""

# Named `shell` and not `selectors` deliberately: `selectors` is a stdlib module
# (asyncio imports it), and a file of that name on the rootdir shadows it.

SIDEBAR = '[data-testid="sidebar"]'
ACCOUNT_MENU = '[data-testid="account-menu"]'

# DashboardLayout's affordance when the realtime connection drops. The run page
# streams over that connection, so this is what a user meets when a run appears
# to stall — see 12-shell-nav.
RECONNECT = 'button:has-text("Reconnect")'
