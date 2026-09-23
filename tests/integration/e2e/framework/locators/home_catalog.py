"""Selectors for screens/02-home-catalog.feature.md — HomeLaunchGrid.

The catalog carries **no testids**. Cards are `<button>` elements holding an
`<h2>` with the title, so every selector here is built from that structure plus
the one real handle the grid does expose: `aria-label="Inspect <title> details"`.
"""

HEADING = "What would you like to build today?"
COMING_SOON_HEADING = 'h3:has-text("Coming Soon")'
COMING_SOON_BADGE = "Coming Soon"
# Rendered "Jump back in" — the spec transcribed the small-caps STYLING,
# not the DOM text. Match what is in the markup.
JUMP_BACK_IN = "Jump back in"

# The recent-runs strip is the grid immediately AFTER the "Jump back in" label —
# a sibling of the label's wrapper, not a descendant. `xpath=..` from the label
# lands on that wrapper, so the grid is its following sibling.
RECENT_RUN = (
    'xpath=//span[normalize-space()="Jump back in"]'
    '/ancestor::div[1]/following-sibling::div[1]//button'
)


def card(title: str) -> str:
    """The launch button for one workflow, matched on its exact title.

    `text-is` and not `has-text`: "Pitch an idea" is a prefix of "Pitch an idea
    (v2)", so a substring match would return two cards and act on whichever
    came first in the DOM.
    """
    return f'button:has(h2:text-is("{title}"))'


def inspect(title: str) -> str:
    """The `i` affordance beside a card. Disabled on a beta card."""
    return f'[aria-label="Inspect {title} details"]'


def lock_badge(tier: str) -> str:
    """The entitlement badge. Cards are never hidden by tier — see D-09."""
    return f'text=Requires {tier} plan'


# The full launchable set, as the catalog shows it. Derived from
# `user_launchable: true AND is_beta: false` in the workflow manifests, which is
# exactly what HomeLaunchGrid renders outside the Coming Soon group.
LAUNCHABLE_TITLES = [
    "Pitch an idea",
    "Pitch an idea (v2)",
    "Build an interactive prototype",
    "Build an end-to-end application",
    "Generate product requirements",
    "Compose a custom workflow",
    "Retry Until It Passes",
    "Branch by Language",
    "Spanish Greeter",
    "Dutch Greeter",
    "Hand Off to Another Workflow",
    "Ask a Human, Then Hand Off",
    "Ask a Human, Then Decide",
]

# `user_launchable: true` but `is_beta: true` — listed under Coming Soon, greyed,
# and not clickable.
COMING_SOON_TITLES = [
    "MuleSoft to Spring Boot",
    ".NET to Azure",
    "Reverse engineer a codebase",
    "Sub-agents in parallel",
]
