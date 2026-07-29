"""How every number and table in this package looks, in one module.

Pure formatting: takes values, returns strings, prints nothing and knows
nothing about grading. Both consumers use it — the terminal (`grade_runner`)
and the run folder's REPORT.md (`markdown_report`) — so a style lives once.
"""

from __future__ import annotations

DASH = "—"
TICK = "✅"
CROSS = "❌"

# One trailing column whose width is not fixed, appended after two spaces.
FLEXIBLE = 0


# ── values ────────────────────────────────────────────────────────────────


def number(value, places: int = 2) -> str:
    """A rate or statistic to `places` decimals — `1.00`, `0.92`, or a dash."""
    if value is None:
        return DASH
    return f"{value:.{places}f}" if isinstance(value, float) else str(value)


def score(value) -> str:
    """A judge score without false precision: `85.5` and `74`, never `85.50`."""
    if value is None:
        return DASH
    return f"{value:g}"


def tokens(count) -> str:
    """Token counts as `6.2k`, because five significant digits are never read."""
    count = count or 0
    if count < 1000:
        return str(count)
    return f"{count / 1000:.1f}k"


def negative(value) -> str:
    """`correct/total` for expect:fail rows, or a dash when there are none."""
    if not value or not value.get("total"):
        return DASH
    return f"{value['correct']}/{value['total']}"


def flag(value) -> str:
    """A tri-state boolean as a tick, a cross, or a dash for unknown."""
    if value is True:
        return TICK
    if value is False:
        return CROSS
    return DASH


def model_label(spec, *, unset: str = DASH) -> str:
    """`provider/model` for a model spec, or the honest name for an unset one."""
    provider = (spec or {}).get("provider")
    model = (spec or {}).get("model")
    if not provider and not model:
        return unset
    return f"{provider or 'implicit'}/{model or 'default'}"


def short_hash(digest) -> str:
    """A sha256 shortened to its first 12 hex characters."""
    if not digest:
        return DASH
    return str(digest).replace("sha256:", "")[:12]


def plural(count, noun: str, suffix: str = "s") -> str:
    """`1 row`, `3 rows` — a count and its noun, agreeing.

    "1 rows selected" is the kind of detail that makes a tool read like a
    draft, and it appeared in three places because each one built the string
    itself.
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}{suffix}"


def truncate(text, limit: int = 160) -> str:
    """Collapse to one line of at most `limit` characters, ellipsis included.

    Used wherever a value shares a line with others — an exception that wraps
    destroys the column alignment that makes a table readable.
    """
    if not text:
        return ""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# ── layout ────────────────────────────────────────────────────────────────


def rule(title: str, width: int = 88) -> str:
    """A titled horizontal rule, so a run's phases are visually separable."""
    return f"\n{title} {'─' * max(0, width - len(title) - 1)}"


def table(columns: list[tuple[str, int, str]], rows: list[list]) -> list[str]:
    """A fixed-width table as lines: header first, then one line per row.

    `columns` is `(header, width, align)` with align `<` or `>`. A width of
    FLEXIBLE marks the trailing column, which is left-aligned after two spaces
    and never padded — that is where a verdict or a note belongs.
    """
    return [_row(columns, [header for header, _, _ in columns])] + [
        _row(columns, values) for values in rows
    ]


def _row(columns: list[tuple[str, int, str]], values: list) -> str:
    """One table line, each value padded to its column's width and alignment."""
    cells = []
    for (_, width, align), value in zip(columns, values):
        text = "" if value is None else str(value)
        cells.append(f"  {text}" if width == FLEXIBLE else f"{text:{align}{width}}")
    return "  " + "".join(cells).rstrip()


def md_table(headers: list[str], rows: list[list], aligns: str = "") -> list[str]:
    """A markdown table as lines. `aligns` is one char per column: `l` or `r`."""
    aligns = aligns.ljust(len(headers), "l")
    separator = ["---:" if align == "r" else "---" for align in aligns]
    return [
        _md_row(headers),
        _md_row(separator),
        *[_md_row(values) for values in rows],
    ]


def _md_row(values: list) -> str:
    """One markdown row, with any `|` in a value escaped so it cannot split it."""
    cells = [str(DASH if value is None else value).replace("|", "\\|") for value in values]
    return "| " + " | ".join(cells) + " |"
