"""Selectors and row parsing for screens/06-run-history.feature.md.

**This page has zero `data-testid` attributes** (D-14), so everything here is
built on the one stable hook it does offer: each row is a
`div[role="button"]` whose `aria-label` reads `Open <brief excerpt>, <status>`.
That is enough to count rows, scope a per-row control, and read a row's status
without depending on table order or on copy that a restyle would change.

`[aria-label^="Open "]` on its own returns one MORE element than there are runs.
Keep the `div[role="button"]` prefix — an off-by-one here reads as a filter
disagreeing with its own chip.

The sort buttons carry `aria-label`s that do not match their visible text
("Longest" is `Sort by duration`), and an aria-label wins over text content when
the accessible name is computed. `get_by_role("button", name="Longest")` matches
nothing.
"""

from __future__ import annotations

import re

HEADING = "Run History"

ROW = 'div[role="button"][aria-label^="Open "]'
SEARCH = 'input[name="history-search"]'
REFRESH = '[aria-label="Refresh run history"]'
AUTO_REFRESH = 'select[aria-label="Auto-refresh interval"]'
RUN_ACTIONS = '[aria-label="Run actions"]'

# Visible label -> accessible name. Never derive one from the other.
SORTS = {
    "Newest": "Sort by recent",
    "Longest": "Sort by duration",
    "Tokens": "Sort by tokens",
}

# Chip label -> the value routes.runHistory() puts in `?type=`. "Presentation"
# is `ppt`; guessing `presentation` produces D-15's silent empty list.
TYPE_PARAMS = {
    "User Stories": "user_stories",
    "Presentation": "ppt",
    "Prototype": "prototype",
    "App Builder": "app_builder",
    "Custom": "custom",
}

EMPTY_FILTER = "No runs match this filter"

_SUFFIX = {"K": 1_000, "M": 1_000_000}


def chip(page, label: str):
    """A type filter, matched on its label prefix — the count is in the label."""
    return page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}\s*\d"))


def chip_count(page, label: str) -> int:
    text = chip(page, label).first.inner_text().replace("\n", " ")
    m = re.search(r"(\d+)\s*$", text.strip())
    assert m, f"the {label!r} chip carries no count: {text!r}"
    return int(m.group(1))


def total(page) -> int:
    """The `<N> runs` headline count."""
    m = re.search(r"(\d[\d,]*)\s+runs?\b", page.evaluate("() => document.body.innerText"))
    assert m, "the run count is missing"
    return int(m.group(1).replace(",", ""))


def rows(page) -> list[str]:
    """Every row's aria-label — `Open <brief excerpt>, <status>`."""
    return page.locator(ROW).evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")


def status_of(label: str) -> str:
    """The status out of a row's aria-label. `Open hello, completed` -> completed."""
    return label.rsplit(",", 1)[-1].strip().lower()


def group_counts(page) -> list[int]:
    """The count beside each date group header — TODAY 2, EARLIER THIS WEEK 48.

    Read out of the rendered text: the headers carry no hook of their own, which
    is the same D-14 gap that forces the row selector above.
    """
    text = page.evaluate("() => document.body.innerText")
    return [
        int(n)
        for _, n in re.findall(r"^([A-Z][A-Z ]{2,30})\n(\d+)$", text, re.MULTILINE)
    ]


def duration_seconds(text: str) -> float | None:
    """`"12m 54s"` -> 774. None when the row shows no duration."""
    m = re.search(r"(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)", text)
    if not m or not any(m.groups()):
        return None
    h, mi, s = (int(g or 0) for g in m.groups())
    return h * 3600 + mi * 60 + s


def tokens(text: str) -> float | None:
    """`"965.5K"` -> 965_500. None when the row shows no token total.

    Anchored to a WHOLE LINE: the count is its own `<p>`, always one decimal
    place (`formatTokenCount` is `toFixed(1)`), while the brief above it is
    free text. A loose search reads "Design a pricing page for a B2B analytics
    product" as 2 billion tokens — and that row carries no count at all.
    """
    m = re.search(r"^(\d+\.\d)([KM])$", text, re.MULTILINE)
    if not m:
        return None
    return float(m.group(1)) * _SUFFIX[m.group(2)]


def age_minutes(text: str) -> float | None:
    """`"3h ago"` -> 180. Bigger means older."""
    m = re.search(r"(\d+)\s*([mhd])\s+ago", text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return n * {"m": 1, "h": 60, "d": 1440}[unit]


def row_texts(page) -> list[str]:
    return page.locator(ROW).evaluate_all("els => els.map(e => e.innerText)")


def segments(page) -> list[list[str]]:
    """Row texts split into their date groups, in document order.

    **Sorting is applied WITHIN a group, not across the list.** A run from today
    that took 5 minutes still sits above one from last week that took 45, so a
    monotonic check over the flat list fails on correctly-ordered data. The
    group headers give the segment sizes; rows follow them in order.
    """
    sizes, texts = group_counts(page), row_texts(page)
    out, start = [], 0
    for size in sizes:
        out.append(texts[start : start + size])
        start += size
    if start < len(texts):  # a group whose header did not parse
        out.append(texts[start:])
    return [seg for seg in out if seg]
