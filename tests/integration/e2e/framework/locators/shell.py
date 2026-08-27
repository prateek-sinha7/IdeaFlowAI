"""The chrome that wraps every signed-in screen.

Area-specific selectors do NOT belong here — they live in
`framework/locators/<area>.py`. This is only nav, the account menu, toasts and
the realtime-connection banner.

Named `shell` and not `selectors` deliberately: `selectors` is a stdlib module
(asyncio imports it), and a file of that name on the rootdir shadows it.

**Use `nav(page, "Library")`, never `button:text-is("Library")`.** Each nav item
is `<button><span>Library</span></button>`, and Playwright's `:text-is` matches
the DEEPEST element holding the text — the span — so the button selector
silently returns zero matches. `get_by_role` resolves the accessible name up the
tree and matches correctly.
"""

NAV_ITEMS = ["Home", "Library", "My Workflows"]

ACCOUNT_MENU = '[aria-label="Account menu"]'
NOTIFICATIONS = '[aria-label="Notifications"]'
LOG_OUT = 'button[role="menuitem"]:has-text("Log out")'

# DashboardLayout's affordance when the realtime connection drops. The run page
# streams over that connection, so this is what a user meets when a run appears
# to stall — see 12-shell-nav.
RECONNECT = 'button:has-text("Reconnect")'


def nav(page, label: str):
    """A top-nav item, by accessible name."""
    return page.get_by_role("button", name=label, exact=True)


# The active item is marked with aria-current="page" — nothing else in the
# header carries it, so it doubles as "which screen am I on" for a test.
CURRENT = 'nav button[aria-current="page"]'

MENU = '[role="menu"]'
MENU_ITEMS = [
    "Account Settings",
    "Analytics",
    "Run History",
    "Dark mode",
    "Log out",
]
ADMIN_MENU_ITEM = "Admin Dashboard"

# Menu-item routes. `/history` is NOT a route and 404s — never derive one from
# the label.
MENU_ROUTES = {
    "Account Settings": "/settings/profile",
    "Analytics": "/analytics",
    "Run History": "/runs",
    "Admin Dashboard": "/admin",
}

NOTIFICATIONS_HEADING = "Notifications"
NO_NOTIFICATIONS = "No notifications yet"
NOTIFICATIONS_HINT = "Pipeline completions will appear here"


def menu_item(page, label: str):
    """One account-menu entry, by role and exact name.

    Located by role and clicked directly: a plain text click on these is
    documented as intermittently failing, Analytics worst of all.
    """
    return page.get_by_role("menuitem", name=label, exact=True)
