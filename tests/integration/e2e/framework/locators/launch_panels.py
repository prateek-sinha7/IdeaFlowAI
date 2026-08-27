"""Selectors for screens/03-launch-panels.feature.md.

Two different shells reach the same launch:

  **Wizard** — `/create/ppt`, `/create/prototype`. Tabs, a template gallery,
  category pills. Carries `tab-*` testids and its own search field.
  **Simple panel** — every other `/create/<workflow>`. A brief and four buttons,
  and **no testids at all**, so its controls are matched on visible text.

The two wizards deliberately do NOT share a search field name: ppt uses
`ppt-template-search`, prototype uses `template-search`. S-03-05 pins that so a
page object cannot quietly unify them.
"""

# ── shared ───────────────────────────────────────────────────────────────────

BRIEF = 'textarea[name="brief"]'
ATTACH_FILE = 'button:has-text("+ Attach file")'
FILE_INPUT = 'input[type="file"]'
BACK_TO_DASHBOARD = '[aria-label="Back to dashboard"]'

RUN_WORKFLOW = 'button:has-text("Run workflow")'
SAVE_WORKFLOW = 'button:has-text("Save workflow")'
SAVE_AS_MY_VERSION = 'button:has-text("Save as my version")'

# `Advanced <N> agents` and `Review gates <state>` are one button each, label and
# value together. The count in the label must equal the roster the modal lists —
# a useful invariant, and D-05 suggests it does not always hold for an override.
ADVANCED = 'button:has-text("Advanced")'
REVIEW_GATES = 'button:has-text("Review gates")'

# ── the wizard ───────────────────────────────────────────────────────────────

TAB_TEMPLATE = '[data-testid="tab-template"]'
TAB_DESIGN_SYSTEM = '[data-testid="tab-design-system"]'
TAB_DISCOVERY = '[data-testid="tab-discovery"]'

PPT_SEARCH = 'input[name="ppt-template-search"]'
PROTOTYPE_SEARCH = 'input[name="template-search"]'

PPT_CATEGORIES = [
    "All", "Pitch Deck", "Business", "Tech", "Editorial", "Creative",
    "Minimal", "Custom",
]

# A template tile is the only button containing a preview <iframe>. Matching on
# its label instead also catches the "Pitch Deck" CATEGORY PILL — `has-text` is a
# case-insensitive substring, so "DECK" matches "Pitch Deck" — and the tile count
# would then include pills.
TEMPLATE_TILE = "button:has(iframe)"


def category_pill(name: str) -> str:
    return f'button:text-is("{name}")'


# ── headings and eyebrows ────────────────────────────────────────────────────

PPT_HEADING = "Configure your presentation"
SIMPLE_HEADING = "Provide the brief"

# ── the Advanced roster ──────────────────────────────────────────────────────
#
# NOT a `role="dialog"`. Advanced opens the full workflow CANVAS, rendering one
# `canvas-node-wrap-<agent>` per roster agent — and that count is the invariant
# the `Advanced <N> agents` label has to match.

ADVANCED_HEADING = "Advanced Workflow Configuration"
CANVAS_VIEW = '[data-testid="canvas-view"]'
CANVAS_NODE = '[data-testid^="canvas-node-wrap-"]'

# `Cancel`, not Escape. The overlay is `fixed inset-0 z-50` and swallows the
# key — see D-22. There is also an icon-only close button in the corner, but it
# carries NO aria-label, no title and no testid, so its only handle is a CSS
# class. That is D-23; use Cancel until it has an accessible name.
CANVAS_CANCEL = 'button:text-is("Cancel")'
