"""Selectors for screens/04-composer-canvas.feature.md.

One component serves three routes, and **the Save label is the only thing that
distinguishes them**: `Save workflow` writes in place, `Save as copy` cannot.
Asserting merely that "a save button exists" passes in all three modes and
catches nothing — ADR-0014's guarantee is that a built-in is never overwritable.

Node testids are keyed by AGENT ID (`canvas-node-ppt-composer`); the per-node
control aria-labels are keyed by DISPLAY NAME (`Rename Deck QA Agent`). Both
live on the same node. Prefer the testid — it survives a rename, which is
exactly what S-04-09 changes underfoot.

Badges are uppercased by CSS. The DOM text is `Core`, not `CORE`.
"""

from __future__ import annotations

import re

HEADER_SUMMARY = '[data-testid="composer-header-summary"]'
CANVAS = '[data-testid="canvas-view"]'
BRIEF_NODE = '[data-testid="canvas-brief"]'
EDGE = '[data-testid="canvas-edge"]'
BACK = '[aria-label="Back"]'

SAVE_WORKFLOW = 'button:text-is("Save workflow")'
SAVE_AS_COPY = 'button:text-is("Save as copy")'
RUN_ONCE = 'button:has-text("Run once")'

SIMPLE = 'button:text-is("Simple")'
CANVAS_TAB = 'button:text-is("Canvas")'

# One per insert slot — four of them on a three-node canvas, one on an empty
# composer. Always take `.first` unless a specific slot is the point.
ADD_AGENT = '[aria-label="Add agent"]'
ADD_TO_PLAN = 'button:has-text("+ Add")'

# The rename control opens a page-level input, NOT one inside the node.
AGENT_RENAME = 'input[name="agent-rename"]'

# Run once carries an advisory title while the brief is too short. It is not
# `disabled` — see D-29.
RUN_GATE_TITLE = "Add a brief first"
RAIL_WORKFLOW = 'button:text-is("Workflow")'
RAIL_AGENT = 'button:text-is("Agent")'
AGENT_SUBTABS = ["Overview", "Skills", "Hooks", "Tools", "Config"]
AGENT_NAME = 'input[name="agent-name"]'

WORKFLOW_NAME = 'input[name="workflow-name"]'
WORKFLOW_DESCRIPTION = 'input[name="workflow-description"]'
BRIEF = 'textarea[name="brief"]'
DELIVERABLE_STRATEGY = 'select[name="deliverable-strategy"]'
# Select by VALUE: the option text carries its own summary ("Streamed text —
# agent's raw output"), so a label match on the strategy name alone fails.
STRATEGY_VALUES = {
    "Streamed text": "streamed_text",
    "Single file": "single_file",
    "Serialized sandbox": "serialized_sandbox",
}
OUTPUT_FILENAME = 'input[name="output-filename"]'
OUTPUT_FORMAT = 'select[name="output-format"]'

SWITCHES = ["Smart planning", "Confirm requirements first", "Internet access"]

RUN_GATE_HINT = "3 more characters to enable Run"
LAST_STEP_GUARD = (
    "The last step's output is this workflow's deliverable (output.md). Adding a "
    "step after it would replace output.md with the new step's output — insert "
    "it before another step instead."
)

STRATEGY_HELPERS = {
    "Streamed text": "uses the agent's raw output",
    "Single file": "reads back one named file from the workspace",
    "Serialized sandbox": "zips the whole workspace",
}

# The ppt built-in, as the canvas renders it. Note "Executive Reporting" is NOT
# here: the built-in has three steps; the saved override "My presentation" has
# four. That difference is D-05.
PPT_AGENT_IDS = ["ppt-brief-analyst", "ppt-composer", "ppt-validator"]
PPT_DISPLAY_NAMES = ["Presentation Strategist", "Deck Engineer", "Deck QA"]


def node(agent_id: str) -> str:
    return f'[data-testid="canvas-node-{agent_id}"]'


def move_earlier(agent_id: str) -> str:
    return f'[data-testid="canvas-move-earlier-{agent_id}"]'


def move_later(agent_id: str) -> str:
    return f'[data-testid="canvas-move-later-{agent_id}"]'


def rename(agent_id: str) -> str:
    return f'[data-testid="canvas-rename-{agent_id}"]'


def remove(display_name: str) -> str:
    """No testid for remove — only the display-name aria-label."""
    return f'[aria-label="Remove {display_name} Agent"]'


def switch(page, label: str):
    return page.locator(f'button[role="switch"][aria-label="{label}"]')


def agent_count(page) -> int:
    """The `N agents` the header summary reports."""
    m = re.search(r"(\d+)\s+agents?", page.locator(HEADER_SUMMARY).inner_text())
    assert m, "the header summary reports no agent count"
    return int(m.group(1))


def node_order(page) -> list[str]:
    """Agent ids in the order the canvas draws them, top to bottom.

    Read from the wrapper testids and sorted by their rendered position: the
    canvas is absolutely positioned, so DOM order is not visual order.
    """
    return page.evaluate(
        """() => [...document.querySelectorAll('[data-testid^="canvas-node-wrap-"]')]
             .map(e => ({ id: e.dataset.testid.replace('canvas-node-wrap-', ''),
                          y: e.getBoundingClientRect().top }))
             .sort((a, b) => a.y - b.y)
             .map(e => e.id)"""
    )


def wait_for_nodes(page, expected: int | None = None) -> list[str]:
    """Block until the canvas has drawn its agent nodes, then return their order.

    The header summary and the BRIEF node both render before any agent node
    does, so a test that starts reading as soon as those appear captures an
    empty roster and then compares it against a full one after a reload.
    """
    if expected == 0:
        return []
    page.wait_for_function(
        "n => { const c = document.querySelectorAll('[data-testid^=\"canvas-node-wrap-\"]').length;"
        "      return n === null ? c > 0 : c === n; }",
        arg=expected,
    )
    return node_order(page)


def wait_for_order(page, expected: list[str], timeout_ms: int = 10_000) -> None:
    """Poll until the canvas draws its nodes in `expected` order.

    A reorder animates, so reading straight after the click catches the nodes
    mid-flight and reports the previous order as though nothing happened.
    """
    deadline = timeout_ms
    while deadline > 0:
        if node_order(page) == expected:
            return
        page.wait_for_timeout(250)
        deadline -= 250
    raise AssertionError(f"order is {node_order(page)}, expected {expected}")
