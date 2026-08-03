"""Charts as hand-emitted SVG: no library, no CDN, no canvas.

A charting library was never an option — the pages must open from `file://`
with nothing external — but the constraint turned out to be the right shape
anyway. These five primitives are a few dozen lines each, they inherit the
page's theme through CSS custom properties instead of baking colours in, and
they print.

Two rules every primitive keeps:

- Colour is never the only signal, and every plotted value is also emitted as
  text (a `<title>`, a label, or the table beside it) — a chart nobody can read
  aloud is a chart that hides data.
- Degenerate input renders sanely. Zero points, one point, every value equal,
  and `None` gaps are all normal here, not edge cases.
"""

from __future__ import annotations

from html import escape

# One coordinate space for every chart, scaled by the browser via viewBox.
WIDTH = 720
HEIGHT = 220
PAD_LEFT = 44
PAD_RIGHT = 12
PAD_TOP = 12
PAD_BOTTOM = 28

# Score-band colours are shared with the CSS so a pill and a cell agree.
BAND_HIGH = 90.0
BAND_MID = 70.0


def band_class(value) -> str:
    """`high` / `mid` / `low` for a 0-100 score — the one place that rule lives."""
    if value is None:
        return "flat"
    if value >= BAND_HIGH:
        return "high"
    if value >= BAND_MID:
        return "mid"
    return "low"


def _svg(body: str, *, height: int = HEIGHT, label: str = "") -> str:
    """Wrap chart geometry in a labelled, responsive `<svg>`."""
    return (
        f'<svg class="chart" viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-label="{escape(label)}" preserveAspectRatio="xMidYMid meet">{body}</svg>'
    )


def _empty(message: str) -> str:
    """An honest empty state — never an axis with nothing on it."""
    return f'<p class="muted small">{escape(message)}</p>'


def _scale(values, *, floor: float = 0.0, ceiling: float | None = None):
    """A (min, max) window that never collapses to zero height."""
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return floor, floor + 1.0
    low = min(numbers + [floor]) if floor is not None else min(numbers)
    high = ceiling if ceiling is not None else max(numbers)
    if high - low < 1e-9:
        high = low + 1.0
    return low, high


# ── line series ───────────────────────────────────────────────────────────


def line_chart(points, *, label: str, references=(), y_max: float | None = 100.0) -> str:
    """A chronological series, with optional horizontal reference lines.

    `points` is [(caption, value)]. A `None` value breaks the line rather than
    being drawn as zero — a run that produced no grade is not a run that scored
    nothing.
    """
    if not points:
        return _empty("no runs to plot yet")
    low, high = _scale([value for _, value in points], floor=0.0, ceiling=y_max)
    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    plot_h = HEIGHT - PAD_TOP - PAD_BOTTOM
    step = plot_w / max(1, len(points) - 1) if len(points) > 1 else 0

    def x_of(index: int) -> float:
        return PAD_LEFT + (index * step if len(points) > 1 else plot_w / 2)

    def y_of(value: float) -> float:
        return PAD_TOP + plot_h - ((float(value) - low) / (high - low)) * plot_h

    parts = [_axes(low, high)]
    for name, value in references:
        if value is None:
            continue
        y = y_of(value)
        parts.append(
            f'<line class="refline" x1="{PAD_LEFT}" y1="{y:.1f}" '
            f'x2="{WIDTH - PAD_RIGHT}" y2="{y:.1f}"><title>'
            f"{escape(str(name))}: {float(value):.1f}</title></line>"
        )
        parts.append(
            f'<text x="{WIDTH - PAD_RIGHT}" y="{y - 4:.1f}" text-anchor="end">'
            f"{escape(str(name))} {float(value):.1f}</text>"
        )

    segment: list[str] = []
    for index, (name, value) in enumerate(points):
        if value is None:
            if len(segment) > 1:
                parts.append(f'<polyline class="series" points="{" ".join(segment)}" />')
            segment = []
            continue
        x, y = x_of(index), y_of(value)
        segment.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<circle class="point" cx="{x:.1f}" cy="{y:.1f}" r="3">'
            f"<title>{escape(str(name))}: {float(value):.1f}</title></circle>"
        )
    if len(segment) > 1:
        parts.append(f'<polyline class="series" points="{" ".join(segment)}" />')

    for index, (name, _) in enumerate(points):
        if len(points) > 12 and index % max(1, len(points) // 8) != 0:
            continue
        parts.append(
            f'<text x="{x_of(index):.1f}" y="{HEIGHT - 8}" text-anchor="middle">'
            f"{escape(str(name)[:9])}</text>"
        )
    return _svg("".join(parts), label=label)


def _axes(low: float, high: float) -> str:
    """A left axis with three labelled ticks — enough to read, not to clutter."""
    plot_h = HEIGHT - PAD_TOP - PAD_BOTTOM
    parts = [
        f'<line class="axis" x1="{PAD_LEFT}" y1="{PAD_TOP}" '
        f'x2="{PAD_LEFT}" y2="{PAD_TOP + plot_h}" />',
        f'<line class="axis" x1="{PAD_LEFT}" y1="{PAD_TOP + plot_h}" '
        f'x2="{WIDTH - PAD_RIGHT}" y2="{PAD_TOP + plot_h}" />',
    ]
    for fraction in (0.0, 0.5, 1.0):
        value = low + (high - low) * fraction
        y = PAD_TOP + plot_h - fraction * plot_h
        parts.append(
            f'<text x="{PAD_LEFT - 6}" y="{y + 3:.1f}" text-anchor="end">{value:.0f}</text>'
        )
    return "".join(parts)


# ── bars ──────────────────────────────────────────────────────────────────


def bar_chart(rows, *, label: str, maximum: float | None = 100.0) -> str:
    """Horizontal bars, one per (name, value). Ordering is the caller's business.

    The left gutter is sized to the longest label rather than fixed: a fixed
    gutter clipped `design_system_coherence` down to "herence", which reads as
    a rendering fault and hides which dimension the bar belongs to.
    """
    rows = [(name, value) for name, value in rows]
    if not rows:
        return _empty("nothing to chart")
    high = maximum if maximum is not None else max(
        [float(value) for _, value in rows if value is not None] or [1.0]
    )
    labels = [str(name) for name, _ in rows]
    # ~5.6px per character at the 10px chart font, clamped so one very long
    # name cannot squeeze the bars into nothing.
    gutter = int(min(190, max(70, max(len(text) for text in labels) * 5.6 + 10)))
    value_column = 46
    row_h = 22
    height = PAD_TOP + len(rows) * row_h + 10
    plot_w = WIDTH - gutter - PAD_RIGHT - value_column
    parts = []
    for index, (name, value) in enumerate(rows):
        y = PAD_TOP + index * row_h
        parts.append(
            f'<text x="{gutter - 8}" y="{y + 13}" text-anchor="end">'
            f"{esc_label(str(name), gutter)}<title>{escape(str(name))}</title></text>"
        )
        if value is None:
            parts.append(f'<text x="{gutter + 4}" y="{y + 13}">—</text>')
            continue
        width = max(1.0, (float(value) / high) * plot_w) if high else 1.0
        parts.append(
            f'<rect class="bar" x="{gutter}" y="{y + 4}" width="{width:.1f}" '
            f'height="{row_h - 9}" rx="2" opacity="{_opacity(value, high)}">'
            f"<title>{escape(str(name))}: {float(value):.1f}</title></rect>"
        )
        parts.append(
            f'<text x="{gutter + width + 6:.1f}" y="{y + 13}">{float(value):.1f}</text>'
        )
    return _svg("".join(parts), height=height, label=label)


def esc_label(text: str, gutter: int) -> str:
    """A label that fits its gutter, ellipsised rather than silently cut off."""
    room = max(4, int((gutter - 12) / 5.6))
    shown = text if len(text) <= room else text[: room - 1] + "…"
    return escape(shown)


def _opacity(value: float, high: float) -> str:
    """Weaker values render lighter — a second, redundant encoding of the same fact."""
    if not high:
        return "1"
    ratio = max(0.0, min(1.0, float(value) / high))
    return f"{0.35 + 0.65 * ratio:.2f}"


# ── distribution strip ────────────────────────────────────────────────────


def distribution(values, *, label: str) -> str:
    """A one-line spread: every value as a tick, min/median/max called out."""
    numbers = sorted(float(value) for value in values if value is not None)
    if not numbers:
        return _empty("no scores")
    height = 44
    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    low, high = min(numbers + [0.0]), 100.0
    parts = [
        f'<line class="axis" x1="{PAD_LEFT}" y1="30" x2="{WIDTH - PAD_RIGHT}" y2="30" />'
    ]
    for value in numbers:
        x = PAD_LEFT + ((value - low) / (high - low or 1)) * plot_w
        parts.append(
            f'<line class="series" x1="{x:.1f}" y1="14" x2="{x:.1f}" y2="30">'
            f"<title>{value:.1f}</title></line>"
        )
    middle = numbers[len(numbers) // 2]
    parts.append(
        f'<text x="{PAD_LEFT}" y="42">min {numbers[0]:.0f}</text>'
        f'<text x="{WIDTH / 2}" y="42" text-anchor="middle">median {middle:.0f}</text>'
        f'<text x="{WIDTH - PAD_RIGHT}" y="42" text-anchor="end">max {numbers[-1]:.0f}</text>'
    )
    return _svg("".join(parts), height=height, label=label)


# ── grade band track ──────────────────────────────────────────────────────


def band_track(score: float | None, bands, *, fail_grade: str = "F") -> str:
    """The A++..F scale with this run's position marked on it.

    Takes the bands from `grades.GRADE_BANDS` rather than restating them, so
    the picture cannot drift from the arithmetic.
    """
    height = 52
    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    parts = [
        f'<rect x="{PAD_LEFT}" y="18" width="{plot_w}" height="12" rx="6" '
        f'fill="var(--panel-2)" />'
    ]
    ordered = sorted(bands, key=lambda pair: pair[0])
    edges = [(0.0, fail_grade)] + [(float(threshold), letter) for threshold, letter in ordered]
    for threshold, letter in edges:
        x = PAD_LEFT + (threshold / 100.0) * plot_w
        parts.append(f'<line class="axis" x1="{x:.1f}" y1="18" x2="{x:.1f}" y2="30" />')
        parts.append(f'<text x="{x + 2:.1f}" y="42">{escape(letter)}</text>')
    if score is not None:
        x = PAD_LEFT + (max(0.0, min(100.0, float(score))) / 100.0) * plot_w
        parts.append(
            f'<polygon points="{x - 5:.1f},10 {x + 5:.1f},10 {x:.1f},18" '
            f'fill="var(--ink)"><title>this run: {float(score):.1f}</title></polygon>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="8" text-anchor="middle">{float(score):.1f}</text>'
        )
    return _svg("".join(parts), height=height, label="grade scale")


# ── heatmap cells ─────────────────────────────────────────────────────────


def heat_style(value: float | None) -> str:
    """Inline background for one heatmap cell, themed and redundant with its text.

    Emitted as a style attribute rather than a class because the intensity is
    continuous; the cell always carries its number too, so colour is decoration.
    """
    if value is None:
        return "background: var(--panel-2); color: var(--muted);"
    ratio = max(0.0, min(1.0, float(value) / 100.0))
    if value >= BAND_HIGH:
        return f"background: color-mix(in srgb, var(--ok-bg) {35 + 65 * ratio:.0f}%, transparent);"
    if value >= BAND_MID:
        return "background: color-mix(in srgb, var(--warn-bg) 70%, transparent);"
    return f"background: color-mix(in srgb, var(--bad-bg) {100 - 45 * ratio:.0f}%, transparent);"
