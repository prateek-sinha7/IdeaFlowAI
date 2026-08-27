"""Selectors for screens/08-library.feature.md.

**The card selector is `div.bg-surface-card.group`.** The spec recommends
`div.cursor-pointer.p-4`; that matches ZERO agent cards (they are `p-[17px]`)
and would silently report an empty grid. `.bg-surface-card` alone over-matches
by 10–14 per tab because layout chrome shares the class. `.group` is on every
card and on nothing else, and on all three tabs the count it returns equals the
tab's own badge.

Beta agents render with `cursor-not-allowed` rather than `cursor-pointer`, so
any selector built on the pointer class silently drops 30 of the 93.

Tab labels carry their count ("Agents  93"), so exact-text matching fails.
Address tabs by testid.
"""

import re

HEADING = "Library"
SEARCH = 'input[name="library-search"]'

# The one selector that equals the tab badge on every tab. See the module
# docstring before changing it.
CARD = "div.bg-surface-card.group"

TABS = [
    ("tab-agents", "Agents", None),
    ("tab-skills", "Skills", "skills"),
    ("tab-hooks", "Hooks", "hooks"),
]

AGENT_DRAWER = '[data-testid="agent-drawer"]'
DRAWER_TABS = ["Overview", "Skills", "Hooks", "Config"]
SYSTEM_PROMPT = 'button:has-text("Base AGENT.md prompt")'

# material-analyzer IS "Architecture Agent" — the slug is the agent id and need
# not resemble the display name.
AGENT_SLUG = "material-analyzer"
AGENT_NAME = "Architecture Agent"

HOOK_EVENTS = ["All", "PostToolUse", "PreToolUse", "SessionStart", "Stop"]

# The seven spec-014 conditional-gate fixtures with no agents behind them (D-04).
EMPTY_AGENT_CATEGORIES = [
    "Retry Loop",
    "Language Branch",
    "Spanish Greeter",
    "Dutch Greeter",
    "Workflow Handoff",
    "Human Handoff",
    "Human Gate",
]


def tab(testid: str) -> str:
    return f'[data-testid="{testid}"]'


def pill(page, label: str):
    """A category pill, matched on its label PREFIX.

    Every pill renders its label and its count in one button ("App Builder 15"),
    so an exact-text match never succeeds and a substring match on "PPT" also
    catches "PPT v2".
    """
    return page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}\s"))


def pill_count(page, label: str) -> int:
    """The number a pill reports, read off its own label."""
    text = pill(page, label).first.inner_text()
    m = re.search(r"(\d+)\s*$", text.replace("\n", " ").strip())
    assert m, f"the {label!r} pill carries no count: {text!r}"
    return int(m.group(1))


def badge_count(page, testid: str) -> int:
    """The number in a tab's badge — "Agents  93" -> 93."""
    text = page.locator(tab(testid)).inner_text()
    m = re.search(r"(\d+)", text.replace("\n", " "))
    assert m, f"the {testid} tab carries no count: {text!r}"
    return int(m.group(1))
