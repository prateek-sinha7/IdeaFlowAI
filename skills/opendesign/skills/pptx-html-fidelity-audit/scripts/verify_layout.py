#!/usr/bin/env python3
"""
Verify a generated .pptx is shippable: canvas, bounds, footer rail, TEXT FIT,
and overlap.

Usage:
    python verify_layout.py <path/to/deck.pptx>
    python verify_layout.py <deck.pptx> --canvas-w 13.333 --canvas-h 7.5
    python verify_layout.py <deck.pptx> --content-max-y 6.70

Exits 0 on no violations, 1 on any violation. Prints one violation per line,
sorted by slide index:

    slide 3  shape 'Text 5' text needs 3.20" but the box is 1.20" tall
             ('Generic platforms were not designed for your regulatory…', 48pt Georgia)
    slide 11 shape 'note-paragraph' bottom 7.342" exceeds canvas 7.50"

Use this as the gate for "this deck is shippable". A deck that has not passed
this has not been checked, however clean it looks at zoom-out.

---------------------------------------------------------------------------
WHY THIS CHECKS TEXT FIT, AND WHY THAT IS THE POINT
---------------------------------------------------------------------------

The original version of this script checked shape GEOMETRY only — off-canvas,
footer rail, negative coordinates. It passed a deck whose every headline was
printed on top of its own body copy, because python-pptx reports the BOX, and a
box can be perfectly legal while the text inside it is three times too tall.
PowerPoint does not clip that text; it spills it over whatever is underneath.
That is what "the pptx has overlapping text" actually is, nearly every time.

So the fit is measured, not estimated. Each run's real font file is resolved and
FreeType (via Pillow — already a python-pptx dependency, no new install) gives
the true advance width of the text. The paragraph is word-wrapped at the shape's
inner width exactly as PowerPoint wraps it, line heights come from the font's own
ascent + descent, and the total is compared against the shape's inner height.

Two things PowerPoint honours, so this honours them too:

  * **Autofit.** A frame set to shrink text on overflow is not overflowing.
  * **word_wrap = False.** Such a frame does not wrap, so its text is one line
    and the failure mode is width, not height.

And one thing it refuses to do: guess. A font it cannot resolve on this machine
is reported UNVERIFIED rather than passed. A validator that quietly skips what it
cannot measure is worse than no validator, because it reports a clean run.

---------------------------------------------------------------------------
WHY THE CANVAS IS READ, NOT ASSERTED
---------------------------------------------------------------------------

This script used to assert a hard-coded 13.333" x 7.5" canvas. pptxgenjs's
DEFAULT layout is LAYOUT_16x9 = 10" x 5.625" — also 16:9, also correct, and what
you get if you never call defineLayout. So the very first line the tool printed
on a perfectly reasonable deck was a violation that was not one, and the agent
reading it concluded the tool was wrong about everything and shipped a deck with
28 real defects in it.

A validator that cries wolf gets ignored, and then it is worse than useless. The
canvas is now READ from the file and only its aspect ratio is checked. Pass
--canvas-w/--canvas-h when a specific size is genuinely required.

Footer / chrome shapes are exempt from the content rail. Two heuristics identify
them, in this order:

1. **By name** — any shape whose name contains "footer", "foot", "chrome",
   "page", or "pagination" (case-insensitive).
2. **By position** — any shape sitting in the bottom footer band. The band is a
   fraction of canvas height, so it scales with the deck instead of assuming a
   7.5" one.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.enum.text import MSO_AUTO_SIZE
except ImportError:
    sys.stderr.write(
        "python-pptx is required. Install with: pip install python-pptx\n"
    )
    sys.exit(2)

try:
    from PIL import ImageFont
except ImportError:  # pragma: no cover - Pillow ships with python-pptx
    ImageFont = None  # type: ignore[assignment]


FOOTER_NAME_HINTS = ("footer", "foot", "chrome", "page", "pagination")
EPS_IN = 0.005          # ignore sub-pixel overflows (~0.13mm)
EMU_PER_IN = 914400
EMU_PER_PT = 12700

# 16:9 is the only deck shape this pipeline produces. The tolerance is loose
# enough for 10x5.625 and 13.333x7.5 to both read as correct.
TARGET_ASPECT = 16 / 9
ASPECT_TOL = 0.02

# The footer band as a FRACTION of canvas height, so it scales with the deck.
# 0.80" of a 7.5" canvas — the opendesign template's chrome row.
FOOTER_BAND_FRAC = 0.80 / 7.5
CONTENT_RAIL_FRAC = 6.70 / 7.5

# A text box is allowed to be slightly over before it is called a violation.
# BOTH must be exceeded, because either one alone reports noise:
#   * the ratio alone flags a 0.10" page-number box needing 0.15" — a 50%
#     overflow of 0.05", which nothing on the slide can notice;
#   * the absolute alone flags a large box over by 0.09" that is genuinely fine.
# Line-height rounding also differs by a hair between FreeType and PowerPoint.
FIT_TOLERANCE = 1.05
FIT_MIN_OVERFLOW_IN = 0.09

# PowerPoint's default when a run declares no size.
DEFAULT_FONT_PT = 18.0
DEFAULT_FONT_NAME = "Calibri"


def emu_to_in(emu: int | None) -> float:
    return (emu or 0) / EMU_PER_IN


def is_footer_by_name(name: str) -> bool:
    n = (name or "").lower()
    return any(hint in n for hint in FOOTER_NAME_HINTS)


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

_FONT_DIRS = (
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    str(Path.home() / "Library/Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(Path.home() / ".fonts"),
    str(Path.home() / ".local/share/fonts"),
)

# Metric-compatible substitutes, bundled beside this script.
#
# Calibri does not exist on macOS and Arial does not exist on a bare Linux
# container, so a validator that only looks at host fonts reports UNVERIFIED for
# most of a real deck — and a check that cannot measure most of the deck is a
# check that passes broken decks. These four families are metric-compatible
# clones (Carlito was designed to match Calibri's metrics exactly, Liberation to
# match Arial and Times), which is precisely what they exist for: the LINE BREAKS
# and the text height come out the same, so the measurement is real rather than
# approximate. Bundling them makes the result identical on a laptop, a container
# and CI, with no LibreOffice and no host fonts at all.
_BUNDLED_DIR = Path(__file__).resolve().parent / "fonts"

# The pre-fetched .eot library (skills/opendesign/fonts/) render_pptx embeds
# fonts from before this check ever runs. A font in this library is safe for a
# different reason than _OFFICE_SAFE below — its BYTES travel with the file,
# so the recipient never needs it installed. Checked by slug, same
# normalisation the one-time download job and _embed_fonts() both use.
_EMBEDDABLE_FONTS_DIR = Path(__file__).resolve().parents[3] / "fonts"


def _is_embeddable(fam: str) -> bool:
    slug = re.sub(r"[^a-z0-9]+", "-", fam.lower()).strip("-")
    return (_EMBEDDABLE_FONTS_DIR / f"{slug}-Regular.eot").is_file()
_METRIC_CLONES: dict[str, str] = {
    "calibri": "Carlito",
    "carlito": "Carlito",
    "arial": "LiberationSans",
    "helvetica": "LiberationSans",
    "helveticaneue": "LiberationSans",
    "liberationsans": "LiberationSans",
    "timesnewroman": "LiberationSerif",
    "times": "LiberationSerif",
    "liberationserif": "LiberationSerif",
    # Georgia has no metric clone here. It is a serif of similar proportion, so
    # substituting Liberation Serif measures it CLOSE but not exactly — the
    # substitution is reported, and the caller applies extra slack for it.
    "georgia": "LiberationSerif",
    "cambria": "LiberationSerif",
    "garamond": "LiberationSerif",
}
# Families whose bundled stand-in is only APPROXIMATELY metric-compatible.
_APPROX_FAMILIES = frozenset({"georgia", "cambria", "garamond", "helveticaneue"})

# Fonts the RECIPIENT will have. This is a different question from "can this
# machine measure it", and the one that decides whether the deck looks right on
# someone else's laptop: a .pptx stores a font NAME, and PowerPoint substitutes
# whatever it likes when that name is missing — different widths, different
# weight, different everything.
#
# The source HTML decks pull their type from Google Fonts (DM Sans, Cormorant
# Garamond, Courier Prime), and transcribing those names into the pptx produces
# a file that renders correctly on exactly one machine: the one that built it.
#
# This list is the set that ships with Microsoft Office / Windows / macOS Office.
# `+mj-lt` / `+mn-lt` are the theme's major/minor latin fonts, which resolve to
# whatever the theme defines and are therefore always present.
_OFFICE_SAFE = frozenset({
    "+mj-lt", "+mn-lt",
    "arial", "arialblack", "arialnarrow",
    "bookantiqua", "bookmanoldstyle", "bodonimt",
    "calibri", "cambria", "candara", "centurygothic", "comicsansms",
    "consolas", "constantia", "corbel", "couriernew",
    "franklingothicbook", "franklingothicmedium",
    "garamond", "georgia", "gillsansmt", "impact",
    "lucidaconsole", "lucidasans", "palatinolinotype", "perpetua",
    "rockwell", "segoeui", "symbol", "tahoma", "timesnewroman",
    "trebuchetms", "verdana", "webdings", "wingdings",
    # Present on macOS Office and treated as safe by PowerPoint's own picker.
    "helvetica", "helveticaneue", "times", "couriernewps",
})

# For MEASUREMENT only: a font nobody can resolve still has to be measured, or
# the fit check silently does nothing on the very deck that needs it most. The
# stand-in is chosen by category from the family name, and the result is marked
# approximate so a borderline case is never called a defect.
_SERIF_HINTS = ("serif", "garamond", "georgia", "times", "roman", "playfair",
                "cormorant", "book", "merriweather", "lora", "spectral")
_MONO_HINTS = ("mono", "courier", "consol", "code", "typewriter")


def _category_clone(base: str) -> str:
    if any(h in base for h in _MONO_HINTS):
        return "LiberationSerif"      # no mono clone bundled; serif metrics are closer
    if any(h in base for h in _SERIF_HINTS):
        return "LiberationSerif"
    return "LiberationSans"

_font_index: dict[str, Path] | None = None
_font_cache: dict[tuple[str, bool, bool, float], tuple[object, bool]] = {}


def _index_fonts() -> dict[str, Path]:
    """Map a normalised font-file stem -> its path, once per process."""
    global _font_index
    if _font_index is not None:
        return _font_index
    index: dict[str, Path] = {}
    for d in _FONT_DIRS:
        root = Path(d)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in (".ttf", ".ttc", ".otf"):
                continue
            index.setdefault(path.stem.replace(" ", "").lower(), path)
    _font_index = index
    return index


def _style_suffixes(bold: bool, italic: bool) -> list[str]:
    if bold and italic:
        return ["bolditalic", "-bolditalic", "bi", "z"]
    if bold:
        return ["bold", "-bold", "bd"]
    if italic:
        return ["italic", "-italic", "i", "oblique"]
    return []


def _load_font(name: str, size_pt: float, bold: bool,
               italic: bool) -> tuple[object, bool]:
    """Resolve a family + style to a FreeType face.

    Returns ``(face, exact)``. ``exact`` is False when a bundled metric clone
    stood in for a family this machine does not have — the measurement is still
    real, it is just worth saying so.

    ``(None, False)`` means genuinely unmeasurable; the caller reports the shape
    UNVERIFIED rather than guessing.
    """
    if ImageFont is None:
        return None, False
    key = (name, bold, italic, size_pt)
    if key in _font_cache:
        return _font_cache[key]

    px = max(1, int(round(size_pt)))
    base = (name or DEFAULT_FONT_NAME).replace(" ", "").lower()
    suffixes = _style_suffixes(bold, italic)

    def _try(stem_root: str, search) -> object | None:
        for suffix in suffixes + [""]:
            path = search(stem_root + suffix)
            if path is None:
                continue
            try:
                return ImageFont.truetype(str(path), px)
            except OSError:
                continue
        return None

    # 1. The real font, if this machine has it.
    index = _index_fonts()
    face = _try(base, index.get)
    exact = face is not None

    # 2. The bundled metric clone — an exact one where the family has one, a
    #    same-category stand-in otherwise so the fit check still runs.
    if face is None:
        clone = _METRIC_CLONES.get(base) or _category_clone(base)
        if clone:
            def _bundled(stem: str) -> Path | None:
                # Bundled files are "Carlito-Bold.ttf"; a bare family needs
                # "-Regular".
                cand = _BUNDLED_DIR / f"{stem}.ttf"
                if cand.exists():
                    return cand
                cand = _BUNDLED_DIR / f"{stem}-Regular.ttf"
                return cand if cand.exists() else None

            face = _try(clone, _bundled)
            exact = False

    result = (face, exact)
    _font_cache[key] = result
    return result


# ---------------------------------------------------------------------------
# Text fit
# ---------------------------------------------------------------------------


def _run_props(run, para, shape_default_pt: float) -> tuple[float, str, bool, bool]:
    """(size_pt, font_name, bold, italic) for a run, walking the inheritance."""
    size = run.font.size or para.font.size
    size_pt = size.pt if size is not None else shape_default_pt
    name = run.font.name or para.font.name or DEFAULT_FONT_NAME
    return size_pt, name, bool(run.font.bold), bool(run.font.italic)


def _wrap_width(face, text: str) -> float:
    """Advance width of `text` in points (FreeType size is set in points)."""
    try:
        return float(face.getlength(text))
    except Exception:  # noqa: BLE001 - a face that cannot measure is unusable
        return 0.0


def _paragraph_height_pt(para, inner_w_pt: float, shape_default_pt: float,
                         wrap: bool) -> tuple[float, bool, float, bool, object, int]:
    """Height this paragraph needs, in points.

    Returns ``(height_pt, measurable, widest_line_pt, approximate)``.
    ``measurable`` is False when a run's font resolved to nothing at all — the
    caller reports UNVERIFIED rather than passing or failing it. ``approximate``
    is True when a family without an exact metric clone was stood in for, so the
    caller can widen its tolerance instead of reporting a borderline defect it
    cannot actually be sure of.
    """
    runs = [r for r in para.runs if r.text]
    if not runs:
        # An empty paragraph still occupies one line.
        return shape_default_pt * 1.2, True, 0.0, False, None, 1

    # Wrap the paragraph as ONE stream: PowerPoint wraps across run boundaries,
    # so measuring runs independently would over-count lines on mixed-style text.
    faces, sizes = [], []
    measurable = True
    approx = False
    for run in runs:
        size_pt, name, bold, italic = _run_props(run, para, shape_default_pt)
        face, exact = _load_font(name, size_pt, bold, italic)
        if face is None:
            measurable = False
        elif not exact:
            base = (name or "").replace(" ", "").lower()
            # An exact metric clone measures true; a same-category stand-in does
            # not, so widen the tolerance rather than report what we cannot know.
            if base in _APPROX_FAMILIES or base not in _METRIC_CLONES:
                approx = True
        faces.append(face)
        sizes.append(size_pt)

    if not measurable:
        return 0.0, False, 0.0, False, None, 0

    max_size = max(sizes)
    # Line box from the font's OWN metrics, not a 1.2 rule of thumb.
    tallest = faces[sizes.index(max_size)]
    ascent, descent = tallest.getmetrics()
    line_h = float(ascent + descent)

    # An EXACT line spacing shorter than the font's own line box makes
    # consecutive lines print through each other. This is the single most common
    # cause of "the pptx has overlapping text", and it is invisible to every
    # box-geometry check: the box is fine, the lines inside it collide.
    natural_line_h = line_h
    crushed = None
    spacing = para.line_spacing
    if isinstance(spacing, float):
        line_h *= spacing
        if line_h < natural_line_h * 0.92:
            crushed = (line_h, natural_line_h, max_size, "multiple")
    elif spacing is not None:                      # an exact Length
        line_h = spacing.pt
        if line_h < natural_line_h * 0.92:
            crushed = (line_h, natural_line_h, max_size, "exact")

    # Greedy wrap over the whole paragraph text, measuring each word in its own
    # run's face so a big word in a big font counts as big.
    words: list[tuple[str, object]] = []
    for run, face in zip(runs, faces):
        parts = run.text.split(" ")
        for i, w in enumerate(parts):
            if w or i == 0:
                words.append((w, face))

    lines = 1
    cur = 0.0
    widest = 0.0
    space_w = _wrap_width(faces[0], " ")
    for i, (word, face) in enumerate(words):
        w = _wrap_width(face, word)
        add = w if cur == 0.0 else space_w + w
        if wrap and inner_w_pt > 0 and cur + add > inner_w_pt and cur > 0:
            widest = max(widest, cur)
            lines += 1
            cur = w
        else:
            cur += add
    widest = max(widest, cur)

    height = lines * line_h
    if para.space_before is not None:
        height += para.space_before.pt
    if para.space_after is not None:
        height += para.space_after.pt
    # `lines` goes back to the caller because whether crushed spacing can collide
    # is a FRAME question, not a paragraph one — see _text_fit_violations.
    return height, True, widest, approx, crushed, lines


def _fonts_used(shape) -> set[str]:
    """Every font family named by this shape's runs, verbatim."""
    out: set[str] = set()
    if not shape.has_text_frame:
        return out
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if run.text:
                out.add(run.font.name or para.font.name or DEFAULT_FONT_NAME)
    return out


def _text_fit_violations(slide_no: int, shape) -> tuple[list[str], list[str]]:
    """(violations, unverified) for one shape's text frame."""
    tf = shape.text_frame
    if not tf.text.strip():
        return [], []

    name = shape.name or "<unnamed>"

    # TEXT_TO_FIT_SHAPE means PowerPoint shrinks the text to fit, so the frame
    # genuinely cannot overflow.
    #
    # SHAPE_TO_FIT_TEXT is NOT exempt, though it is tempting to treat it the same
    # way. It grows the SHAPE instead, and a shape that grows lands on whatever
    # sits below it or runs off the canvas — the overflow is real, it has just
    # moved. The stored height is what every other check here reasons about, so
    # measuring against it is also the only self-consistent choice.
    if tf.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE:
        return [], []

    inner_w_in = emu_to_in(shape.width) - emu_to_in(tf.margin_left) - emu_to_in(tf.margin_right)
    inner_h_in = emu_to_in(shape.height) - emu_to_in(tf.margin_top) - emu_to_in(tf.margin_bottom)
    inner_w_pt = inner_w_in * 72
    wrap = tf.word_wrap is not False

    total_pt = 0.0
    widest_pt = 0.0
    approximate = False
    total_lines = 0
    crushed_first = None
    for para in tf.paragraphs:
        h, measurable, widest, approx, crushed, lines = _paragraph_height_pt(
            para, inner_w_pt, DEFAULT_FONT_PT, wrap
        )
        approximate = approximate or approx
        total_lines += lines
        if crushed is not None and crushed_first is None:
            crushed_first = crushed
        if not measurable:
            sample = tf.text.strip().replace("\n", " ")[:40]
            return [], [
                f"slide {slide_no:<2} shape '{name}' UNVERIFIED — font not resolvable "
                f"on this machine ('{sample}…')"
            ]
        total_pt += h
        widest_pt = max(widest_pt, widest)

    violations: list[str] = []
    # Crushed spacing collides as soon as the FRAME holds more than one line —
    # which is not the same as a paragraph holding more than one line, and the
    # difference is the whole defect. This guard used to be `lines > 1` INSIDE
    # the paragraph, so a title split as three one-line paragraphs
    # ("Bespoke" / "Social" / "Platform", 72pt, 38pt leading) reported nothing:
    # each paragraph had a single line, and each printed straight through the
    # one after it.
    if crushed_first is not None and total_lines > 1:
        got, natural, size_pt, kind = crushed_first
        violations.append(
            f"slide {slide_no:<2} shape '{name}' line spacing is {got:.1f}pt "
            f"({kind}) but {size_pt:.0f}pt text needs {natural:.1f}pt — its "
            f"{total_lines} lines will print through each other"
        )
    # A family measured through an only-approximately-compatible stand-in gets
    # extra slack, so a borderline case is never reported as a defect this check
    # cannot actually be sure of. A gross overflow still fails either way.
    tol = FIT_TOLERANCE * (1.15 if approximate else 1.0)
    needed_in = total_pt / 72
    if (inner_h_in > 0
            and needed_in > inner_h_in * tol
            and needed_in - inner_h_in > FIT_MIN_OVERFLOW_IN):
        sample = tf.text.strip().replace("\n", " ")[:44]
        violations.append(
            f"slide {slide_no:<2} shape '{name}' text needs {needed_in:.2f}\" "
            f"but the box is {inner_h_in:.2f}\" tall — it will spill over whatever "
            f"is below it ('{sample}…')"
        )
    # A non-wrapping frame fails on width instead.
    if (not wrap and inner_w_pt > 0 and widest_pt > inner_w_pt * tol
            and (widest_pt - inner_w_pt) / 72 > FIT_MIN_OVERFLOW_IN):
        sample = tf.text.strip().replace("\n", " ")[:44]
        violations.append(
            f"slide {slide_no:<2} shape '{name}' text is {widest_pt / 72:.2f}\" wide "
            f"in a {inner_w_in:.2f}\" box and the frame does not wrap ('{sample}…')"
        )
    return violations, []


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


def _overlap_violations(slide_no: int, shapes) -> list[str]:
    """Text boxes whose rectangles intersect.

    Cheap, and it catches the class the fit check cannot: two correctly-sized
    boxes placed on top of one another.
    """
    boxes = []
    for s in shapes:
        if not s.has_text_frame or not s.text_frame.text.strip():
            continue
        if s.left is None or s.top is None:
            continue
        boxes.append((
            s.name or "<unnamed>",
            emu_to_in(s.left), emu_to_in(s.top),
            emu_to_in(s.left) + emu_to_in(s.width),
            emu_to_in(s.top) + emu_to_in(s.height),
        ))

    out: list[str] = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            n1, l1, t1, r1, b1 = boxes[i]
            n2, l2, t2, r2, b2 = boxes[j]
            ox = min(r1, r2) - max(l1, l2)
            oy = min(b1, b2) - max(t1, t2)
            if ox > EPS_IN and oy > EPS_IN:
                out.append(
                    f"slide {slide_no:<2} shapes '{n1}' and '{n2}' overlap by "
                    f"{ox:.2f}\" x {oy:.2f}\""
                )
    return out


# ---------------------------------------------------------------------------


def verify(path: Path, content_max_y: float | None, canvas_w: float | None,
           canvas_h: float | None, footer_zone_top: float | None,
           check_text: bool = True) -> tuple[list[str], list[str]]:
    """Return ``(violations, notes)`` for the deck at ``path``."""
    prs = Presentation(str(path))
    violations: list[str] = []
    notes: list[str] = []

    actual_w = emu_to_in(prs.slide_width)
    actual_h = emu_to_in(prs.slide_height)

    if canvas_w is not None and canvas_h is not None:
        # An explicitly REQUIRED size — the only case where a mismatch is a defect.
        if abs(actual_w - canvas_w) > EPS_IN or abs(actual_h - canvas_h) > EPS_IN:
            violations.append(
                f"canvas mismatch: file is {actual_w:.3f}\" x {actual_h:.3f}\", "
                f"required {canvas_w}\" x {canvas_h}\""
            )
    else:
        # Otherwise the canvas is whatever the deck chose; only its SHAPE matters.
        if actual_h <= 0:
            violations.append("canvas has zero height")
        else:
            aspect = actual_w / actual_h
            if abs(aspect - TARGET_ASPECT) > ASPECT_TOL:
                violations.append(
                    f"canvas is {actual_w:.3f}\" x {actual_h:.3f}\" "
                    f"(aspect {aspect:.3f}) — not 16:9"
                )
    canvas_w_eff, canvas_h_eff = actual_w, actual_h

    rail = content_max_y if content_max_y is not None else canvas_h_eff * CONTENT_RAIL_FRAC
    band_top = (
        footer_zone_top if footer_zone_top is not None
        else canvas_h_eff - (canvas_h_eff * FOOTER_BAND_FRAC)
    )

    unverified: list[str] = []
    # family -> (shape count, first slide it appears on)
    fonts_seen: dict[str, tuple[int, int]] = {}
    for i, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.top is None or shape.height is None:
                continue
            top = emu_to_in(shape.top)
            left = emu_to_in(shape.left)
            bottom = top + emu_to_in(shape.height)
            right = left + emu_to_in(shape.width)
            name = shape.name or "<unnamed>"

            # Off-canvas (hard fail for any shape).
            if bottom > canvas_h_eff + EPS_IN:
                violations.append(
                    f"slide {i:<2} shape '{name}' bottom {bottom:.3f}\" "
                    f"exceeds canvas {canvas_h_eff:.3f}\""
                )
            if right > canvas_w_eff + EPS_IN:
                violations.append(
                    f"slide {i:<2} shape '{name}' right {right:.3f}\" "
                    f"exceeds canvas width {canvas_w_eff:.3f}\""
                )
            if top < -EPS_IN:
                violations.append(
                    f"slide {i:<2} shape '{name}' top {top:.3f}\" is negative"
                )
            if left < -EPS_IN:
                violations.append(
                    f"slide {i:<2} shape '{name}' left {left:.3f}\" is negative"
                )

            for fam in _fonts_used(shape):
                count, first = fonts_seen.get(fam, (0, i))
                fonts_seen[fam] = (count + 1, first)

            # Does the TEXT fit its box? The check the geometry pass cannot make.
            if check_text and shape.has_text_frame:
                v, u = _text_fit_violations(i, shape)
                violations.extend(v)
                unverified.extend(u)

            # Footer rail (only enforced on content shapes).
            if is_footer_by_name(name) or top >= band_top - EPS_IN:
                continue
            if bottom > rail + EPS_IN:
                violations.append(
                    f"slide {i:<2} shape '{name}' bottom {bottom:.3f}\" "
                    f"crosses footer rail {rail:.2f}\""
                )

        violations.extend(_overlap_violations(i, slide.shapes))

    # ── Fonts the RECIPIENT will not have ─────────────────────────────────────
    # Reported once per family rather than once per shape: 125 identical lines
    # is not 125 problems, it is one problem, and a wall of them is how a
    # validator gets skimmed instead of read.
    for fam, (count, first) in sorted(fonts_seen.items(), key=lambda kv: -kv[1][0]):
        if fam.replace(" ", "").lower() in _OFFICE_SAFE or _is_embeddable(fam):
            continue
        violations.append(
            f"font '{fam}' is not a font PowerPoint ships with — used by {count} "
            f"shape(s), first on slide {first}. The recipient's PowerPoint will "
            f"substitute something else, so their deck will not look like yours. "
            f"Map it to the nearest safe family (Arial, Calibri, Georgia, "
            f"Times New Roman, Verdana, Tahoma, Trebuchet MS, Courier New, "
            f"Cambria, Garamond, Segoe UI)."
        )

    if unverified:
        # Not a note. The whole point of measuring is to be able to say the deck
        # is sound, and a shape nobody could measure has not been checked — the
        # last deck to ship broken had EVERY shape in this state and still exited
        # 0. If it cannot be measured, it cannot be approved.
        violations.extend(unverified)
    return violations, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", type=Path, help=".pptx file to verify")
    ap.add_argument("--content-max-y", type=float, default=None,
                    help="content rail in inches; default scales with the canvas")
    ap.add_argument("--canvas-w", type=float, default=None,
                    help="REQUIRED canvas width in inches; omit to accept any 16:9 canvas")
    ap.add_argument("--canvas-h", type=float, default=None,
                    help="REQUIRED canvas height in inches; omit to accept any 16:9 canvas")
    ap.add_argument("--footer-zone-top", type=float, default=None,
                    help="any shape with top >= this is treated as footer/chrome; "
                         "default scales with the canvas")
    ap.add_argument("--no-text-fit", action="store_true",
                    help="skip the text-fit check (geometry only)")
    args = ap.parse_args()

    if not args.path.exists():
        ap.error(f"file not found: {args.path}")

    violations, notes = verify(
        args.path, args.content_max_y, args.canvas_w, args.canvas_h,
        args.footer_zone_top, check_text=not args.no_text_fit,
    )
    if notes:
        sys.stderr.write("\n".join(notes) + "\n\n")
    if violations:
        sys.stderr.write("\n".join(violations) + "\n")
        sys.stderr.write(f"\n{len(violations)} violation(s) found in {args.path}\n")
        return 1
    sys.stderr.write(f"OK: 0 violations across all slides in {args.path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
