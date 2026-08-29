"""Selectors and number-parsing for screens/10-analytics.feature.md.

Every figure on this screen moves with each run the suite itself starts, so the
scenarios assert RELATIONSHIPS — a split summing to its headline, a wider range
never reporting less — never absolute values.

The tiles carry no testids. They are headline/label pairs in the page text, so
the values are read out of the rendered text and parsed.
"""

from __future__ import annotations

import re

HEADING = "Analytics"
PIPELINE_FILTER = 'select[name="pipeline-filter"]'
MODEL_FILTER = 'select[name="model-filter"]'
CHART = '[aria-label^="Daily token usage"]'
BAR = '[data-testid="bar-chart-bar"]'
SUCCESS_RATE = '[aria-label^="Success rate"]'

RANGES = ["Today", "3d", "7d", "30d", "90d", "All"]


def range_button(name: str) -> str:
    return f'button:text-is("{name}")'


_SUFFIX = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def number(text: str) -> float:
    """`"68.9M"` -> 68_900_000, `"$37.06"` -> 37.06, `"248"` -> 248.

    The screen abbreviates large figures, so a raw int() cannot read them and a
    test comparing "3.4M" with "65.5M" as strings would compare lexically.
    """
    t = text.strip().replace(",", "").replace("$", "")
    m = re.match(r"^(-?[\d.]+)\s*([KMB])?", t)
    if not m:
        raise ValueError(f"not a figure: {text!r}")
    return float(m.group(1)) * _SUFFIX.get(m.group(2) or "", 1)


def _lines(page) -> list[str]:
    return [
        line.strip()
        for line in page.evaluate("() => document.body.innerText").splitlines()
        if line.strip()
    ]


def _read(page, label: str, offset: int) -> str:
    """One line relative to a tile's caption, waiting for the caption to exist.

    A re-render briefly removes the tiles from the tree, so reading immediately
    after a range change finds no caption at all. Waiting here — rather than
    raising — keeps that timing detail out of every test.
    """
    for _ in range(40):
        lines = _lines(page)
        if label in lines:
            idx = lines.index(label)
            if idx + offset < len(lines):
                return lines[idx + offset]
        page.wait_for_timeout(150)
    raise AssertionError(f"the {label} tile never appeared")


def tile(page, label: str) -> str:
    """The headline value under a tile's caption, once it has settled.

    The tiles are caption-then-value in document order with no wrapper to hook,
    so this reads the rendered text rather than the DOM.

    **Read twice.** Changing the range re-renders the tiles with no completion
    signal to wait on — no spinner, no aria-busy, and the chart is absent
    entirely on an empty range. Reading once catches the previous range's
    figures, which is how a monotonicity check ends up asserting 7d > 30d and
    reporting a product bug that is really a race.
    """
    previous = _read(page, label, 1)
    for _ in range(20):
        page.wait_for_timeout(150)
        current = _read(page, label, 1)
        if current == previous:
            return current
        previous = current
    return previous


def tile_sub(page, label: str) -> str:
    """The small print under a tile's headline — `"65.5M in · 3.4M out"`."""
    return _read(page, label, 2)


def select_range(page, name: str) -> None:
    """Click a range and wait for the tiles to stop moving."""
    page.click(range_button(name))
    tile(page, "TOTAL RUNS")


def runs_by_pipeline(page) -> dict[str, float]:
    """`{"PROTOTYPE": 41, ...}` — run counts per pipeline, deduplicated.

    The screen shows the same eight pipelines in three panels (by tokens, by
    cost, by runs), so every count appears three times. Summing a flat sweep of
    the page text therefore triples the real total and makes the breakdown look
    inconsistent with its own headline.

    Rows read `<n> runs · <tokens> <cost> <TYPE>` — the label follows its
    figures — and the first occurrence of each type is kept.
    """
    text = page.evaluate("() => document.body.innerText")
    out: dict[str, float] = {}
    for runs, label in re.findall(
        r"(\d[\d,]*)\s+runs?\b[^\n]*\n(?:[^\n]*\n){0,3}?([A-Z][A-Z0-9 ._&-]{2,40})\n", text
    ):
        out.setdefault(label.strip(), number(runs))
    return out


def model_runs(page, model_label: str) -> float:
    """The run count shown for one model in the "By Model" breakdown.

    ISS-288/289 — that panel is a simple `<label>\n<n> runs · ...` pair per
    model (unlike the pipeline breakdown, it carries no duplicate rows), so a
    direct regex against the model's own label is enough.
    """
    text = page.evaluate("() => document.body.innerText")
    m = re.search(rf"{re.escape(model_label)}\D*?(\d[\d,]*)\s+runs?\b", text)
    assert m, f"{model_label!r} not found in the By Model breakdown"
    return number(m.group(1))
