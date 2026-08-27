"""Selectors for screens/07-run-detail.feature.md.

**The Steps tab's testid is `tab-thinking`.** Legacy naming, still live — use
the testid, never the label.

The chat lane is well covered by testids; the Workspace tab has none at all and
is selected on visible text (recorded in GAPS.md § Workspace tab).
"""

from __future__ import annotations

import re

# ── the chat lane ────────────────────────────────────────────────────────────

LANE = '[data-testid="execution-chat-lane"]'
BACK = '[data-testid="lane-back"]'
RUN_TYPE = '[data-testid="lane-run-type"]'
RUN_STATUS = '[data-testid="lane-run-status"]'
RUN_TITLE = '[data-testid="lane-run-title"]'
RUN_META = '[data-testid="lane-run-meta"]'
TRANSCRIPT = '[data-testid="chat-lane-transcript"]'
MESSAGE = '[data-testid="chat-message"]'
PIPELINE_MINI = '[data-testid="lane-pipeline-mini"]'
DELIVERABLE = '[data-testid="lane-deliverable"]'
COMPOSER = '[data-testid="chat-composer"]'
COMPOSER_INPUT = 'textarea[name="run-chat-message"]'
SEND = '[data-testid="chat-send"]'
ATTACHMENTS = '[data-testid="chat-attachments"]'

ANSWER_IN_STEPS = "Answer in Steps"

# ── the result pane ──────────────────────────────────────────────────────────

HEADER = '[data-testid="run-header"]'

# (testid, label, url suffix). Steps is `tab-thinking`.
TABS = [
    ("tab-preview", "Preview", ""),
    ("tab-thinking", "Steps", "/steps"),
    ("tab-files", "Files", "/files"),
    ("tab-workspace", "Workspace", "/workspace"),
    ("tab-audit", "Audit", "/audit"),
]

RENDERER_SWITCH = '[data-testid="renders-as-switch"]'
RENDERER_PILL = '[data-testid="renderer-pill"]'

# ── Steps ────────────────────────────────────────────────────────────────────

AGENT_ROW = '[data-testid="steps-agent-row"]'
STARTING_POINT = "Starting point"

# ── Files ────────────────────────────────────────────────────────────────────

FINAL_OUTPUT = "FINAL OUTPUT"
AGENT_OUTPUTS = "AGENT OUTPUTS"
RUN_INPUT = "RUN INPUT"
DOWNLOAD_ALL = 'button:has-text("Download All")'

# ── Workspace ────────────────────────────────────────────────────────────────

WORKSPACE_EMPTY = "Select a file to view it."

# The pane buttons carry their count on a second line ("Artifacts\n13"), so an
# exact-text match finds nothing — and `get_by_role("button", name=...)` finds
# nothing either, because the count span leaves these with no usable accessible
# name at all. Filtering the element's own text is what works.
# No `\b` after the label: `has_text` matches textContent, which concatenates
# the count with no separator ("Artifacts13"), so a word boundary there never
# holds.
ARTIFACTS_PANE = re.compile(r"^Artifacts")
ALL_FILES_PANE = re.compile(r"^All files")


def pane(page, which):
    """One of the Workspace rail's two panes, by its label."""
    return page.locator("button").filter(has_text=which).first
DOWNLOAD_WORKSPACE = 'button:has-text("Download all")'

# ── Audit ────────────────────────────────────────────────────────────────────

AUDIT_PILL = '[data-testid="audit-records-pill"]'
AUDIT_FILTERS = {
    "All": '[data-testid="audit-filter-all"]',
    "Governance": '[data-testid="audit-filter-gov"]',
    "Security": '[data-testid="audit-filter-sec"]',
    "Activity": '[data-testid="audit-filter-act"]',
}


def tab(testid: str) -> str:
    return f'[data-testid="{testid}"]'


def steps_progress(text: str) -> tuple[int, int] | None:
    """`"5 / 5 agents · 12m 54s"` -> (5, 5).

    The first number is what was DISPATCHED and the second is the roster.
    `3 / 5` is correct on a conditional run, not a bug: two branches were
    skipped.
    """
    m = re.search(r"(\d+)\s*/\s*(\d+)\s+agents", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def counts(text: str, unit: str) -> int | None:
    """`"7 files available"` -> 7, `"1 deliverable"` -> 1."""
    m = re.search(rf"(\d[\d,]*)\s+{unit}", text)
    return int(m.group(1).replace(",", "")) if m else None


def filter_count(page, label: str) -> int | None:
    text = page.locator(AUDIT_FILTERS[label]).inner_text().replace("\n", " ")
    m = re.search(r"(\d[\d,]*)", text)
    return int(m.group(1).replace(",", "")) if m else None
