"""Selectors for screens/05-saved-workflows.feature.md.

**A card body has no click handler.** `SavedWorkflowsPage` puts `onClick` on the
actions menu and on `Run workflow`, and on nothing else — so `/workflows/{id}`,
the read-only detail view, is reachable by URL alone. Clicking a card does
nothing at all, which is why S-05-06 deep-links rather than clicking.

`Workflow actions` repeats once per card. Every use here scopes to the card by
its title first; an unscoped click opens whichever menu is first in DOM order,
and the menu's last item is Delete.
"""

from __future__ import annotations

import re

HEADING = "My Workflows"
SUBTITLE = "Your saved custom workflows — launch, manage and reuse them."

CARD = "div.bg-surface-card.group"
SEARCH = 'input[name="saved-workflows-search"]'
NEW_WORKFLOW = 'button:has-text("New workflow")'
ACTIONS = '[aria-label="Workflow actions"]'
RUN_WORKFLOW = 'button:has-text("Run workflow")'

MENU_ITEMS = ["Edit", "Rename", "Duplicate", "Delete"]

# The detail view. Both are ANCHORS with real hrefs — unlike the run-history
# rows, which are div[role="button"] with no URL at all (D-14).
EDIT = 'a[href$="/edit"]'
RUN = 'a[href$="/run"]'

# The composer's primary action for a SAVED row. A built-in offers "Save as my
# version" instead — see 04-composer-canvas.
SAVE_WORKFLOW = 'button:has-text("Save workflow")'
SAVE_AS_MY_VERSION = 'button:has-text("Save as my version")'

# The Advanced modal's override control. Note the direction: the BASE steps are
# what the panel shows, and this switches to the user's saved version.
# A <label>, not a button: the control is a switch, and the label is what
# carries the text.
USE_MY_VERSION = 'label:has-text("Use my version")'

# A fixture that exists in every seeded database: an override of the ppt
# built-in whose roster (4) disagrees with its launch panel (3) — D-05.
OVERRIDE_TITLE = "My presentation"
OVERRIDE_AGENT_IDS = ["report-generator", "ppt-brief-analyst", "ppt-composer", "ppt-validator"]
# The same steps on the canvas, under their display names. One manifest, two
# vocabularies; a test must not expect one on the other's screen.
OVERRIDE_DISPLAY_NAMES = ["Executive Reporting", "Presentation Strategist", "Deck Engineer", "Deck QA"]


def card(page, title: str):
    """One card, scoped by its title."""
    return page.locator(CARD).filter(has_text=title).first


def stat(page, label: str) -> int:
    """`"31 workflows"` -> 31. The number and its label are separate nodes."""
    text = page.evaluate("() => document.body.innerText")
    m = re.search(rf"(\d[\d,]*)\s*\n?\s*{re.escape(label)}", text)
    assert m, f"no {label!r} stat on the page"
    return int(m.group(1).replace(",", ""))


def agent_count(text: str) -> int | None:
    """`"4 agents"` off a card's text."""
    m = re.search(r"(\d+)\s+agents?\b", text)
    return int(m.group(1)) if m else None
