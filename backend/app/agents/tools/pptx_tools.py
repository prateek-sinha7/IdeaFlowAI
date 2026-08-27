"""app/agents/tools/pptx_tools.py — the three ``pptx`` tools (spec 017 / T2-T3).

`ppt_v2`'s fourth step authors PptxGenJS and calls these to build and check the
real ``.pptx``. Keeping the loop inside the step — rather than modelling it as a
conditional gate or a workflow branch — is the whole reason no engine change is
needed: every tool returns ACTIONABLE TEXT the agent can act on, so "it did not
compile" and "slide 5 crosses the footer" arrive the same way a human reviewer
would say them.

Two of the three wrap scripts in
``skills/opendesign/skills/pptx-html-fidelity-audit/scripts/`` rather than
reimplementing them.

``render_pptx`` VERIFIES what it builds and returns the violations instead of
"ok" when the deck is not shippable. That is not belt-and-braces over the
separate ``verify_pptx_layout`` tool — it is the correction for how this failed
in practice. A verdict delivered by a tool the agent chooses to call is a verdict
the agent can argue with, and one did: handed a violation it judged spurious, it
concluded "the layout is clean and correct" and shipped a deck whose every
headline printed through its own body copy. A gate inside the build has nothing
to overrule.

Sandbox binding: the factory binds these per run (``_resolve_custom_tool_keys``),
so ``_SANDBOX`` is set at bind time and every path goes through
``RunSandbox.path_for``, which is traversal-proof (``is_relative_to(root)``).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

PPTX_NAME = "presentation.pptx"
DECK_NAME = "presentation.html"

# Everything the gate saw, written where the run's own workspace browser shows
# it. A verdict you cannot inspect afterwards is a verdict you have to take on
# trust, and this gate has been wrong before — twice with a "clean" it could not
# justify. The report and the rendered slides are the evidence for the human.
VERIFY_DIR = ".verify"

# A slide in the composed deck is an element whose class list contains the exact
# token "slide" — `class="slide dark is-active"` counts, `class="slide-body"`
# does not. Counting the substring instead reports 41 slides for a 12-slide deck.
_HTML_SLIDE = re.compile(
    r"<(?:section|div|article)\b[^>]*class\s*=\s*([\"'])(.*?)\1", re.IGNORECASE
)

# CSS rotation used as a deliberate, repeated design motif (tilted badges/
# stamps/labels) — deliberately narrow (only the `rotate(Xdeg)` function, not
# any `transform:`) so a slide-transition or hover transform never counts.
_HTML_ROTATE = re.compile(r"rotate\(\s*-?[\d.]+\s*deg\s*\)", re.IGNORECASE)

# Bound by the factory at runner-composition time. Module-level because a
# LangChain @tool takes only the model's arguments — the sandbox is ambient
# per-run state, never something the model should be able to name.
_SANDBOX: Any = None

_AUDIT_SCRIPTS = (
    Path(__file__).resolve().parents[4]
    / "skills" / "opendesign" / "skills" / "pptx-html-fidelity-audit" / "scripts"
)

# Pre-fetched, pre-converted (one-time, offline) EOT files for every font used
# across the opendesign template library — see skills/opendesign/fonts/README.md.
# `render_pptx` embeds whichever of these the built deck actually uses, so the
# agent authoring the deck can write the REAL font name straight from
# deck-styles.json instead of always substituting to an Office-safe stand-in —
# the recipient's PowerPoint never needs the font installed, the bytes travel
# with the file, same approach the OpenDesign reference tool uses.
_FONTS_DIR = (
    Path(__file__).resolve().parents[4] / "skills" / "opendesign" / "fonts"
)


def bind_sandbox(sandbox: Any) -> None:
    """Point the tools at this run's sandbox. Called by the factory, not the model."""
    global _SANDBOX
    _SANDBOX = sandbox


# Deterministic, non-LLM-authored DOM walk. Runs in the rendered page, not the
# agent's imagination: reads real getComputedStyle for every visible element and
# keeps only the ones that carry a paint-relevant property (rotation, fill,
# border, shadow, text) or are SVG/IMG — a plain layout wrapper with nothing
# visual on it is noise the agent doesn't need. Rotation math mirrors the
# standard matrix-decomposition approach (atan2 on the 2x2 rotation/scale
# block), normalized to PptxGenJS's 0-359 range.
_EXTRACT_STYLES_JS = """
() => {
  function colorOf(str) {
    const m = str && str.match(/[\\d.]+/g);
    if (!m || m.length < 3) return null;
    const [r, g, b] = m;
    const a = m.length > 3 ? parseFloat(m[3]) : 1;
    if (a === 0) return null;
    const hex = [r, g, b].map(x => Math.round(parseFloat(x)).toString(16).padStart(2, '0')).join('');
    return { hex: hex.toUpperCase(), opacity: a };
  }
  function rotationOf(transformStr) {
    if (!transformStr || transformStr === 'none') return 0;
    const m = transformStr.match(/matrix\\(([^)]+)\\)/);
    if (!m) return 0;
    const v = m[1].split(',').map(parseFloat);
    if (v.length < 4) return 0;
    const deg = Math.round(Math.atan2(v[1], v[0]) * 180 / Math.PI);
    return ((deg % 360) + 360) % 360;
  }
  // Paginated decks (a JS slideshow toggling `display:none` on every slide but
  // the active one) hide 9 of 10 slides at extraction time — force every
  // `class~="slide"` container visible first, or 90% of the deck gets zero
  // ground truth. Matches the exact "slide" identification pptx_tools.py's own
  // _HTML_SLIDE regex uses server-side, so this stays consistent with the
  // slide-count check. Restored afterward so this is non-destructive.
  const slides = Array.from(document.querySelectorAll('[class~="slide"]'));
  const originalDisplay = new Map();
  slides.forEach(s => {
    originalDisplay.set(s, s.style.display);
    s.style.setProperty('display', 'block', 'important');
  });

  const elements = [];
  const walkRoot = slides.length > 0 ? slides : [document.body];
  const seen = new Set();
  walkRoot.forEach((root, slideIndex) => {
    root.querySelectorAll('*').forEach(el => {
      if (seen.has(el)) return;
      seen.add(el);
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;

      const rotation = rotationOf(cs.transform);
      const background = colorOf(cs.backgroundColor);
      const hasBorder = parseFloat(cs.borderTopWidth) > 0 || parseFloat(cs.borderLeftWidth) > 0
        || parseFloat(cs.borderRightWidth) > 0 || parseFloat(cs.borderBottomWidth) > 0;
      const borderRadiusPx = parseFloat(cs.borderTopLeftRadius) || 0;
      const hasShadow = !!(cs.boxShadow && cs.boxShadow !== 'none');
      const tag = el.tagName.toLowerCase();
      const isSvg = tag === 'svg';
      const isImg = tag === 'img';
      const directText = Array.from(el.childNodes)
        .some(n => n.nodeType === 3 && n.nodeValue.trim().length > 0);

      if (rotation === 0 && !background && !hasBorder && !hasShadow && !directText && !isSvg && !isImg) return;

      elements.push({
        slideIndex: slides.length > 0 ? slideIndex : null,
        tag,
        cls: typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal) || '',
        x: rect.left, y: rect.top, w: rect.width, h: rect.height,
        rotation,
        fontFamily: cs.fontFamily ? cs.fontFamily.split(',')[0].replace(/['\\"]/g, '').trim() : null,
        fontSizePx: parseFloat(cs.fontSize) || null,
        fontWeight: cs.fontWeight,
        fontStyle: cs.fontStyle,
        color: colorOf(cs.color),
        background,
        borderRadiusPx,
        hasBorder,
        hasShadow,
        text: directText ? el.textContent.trim().slice(0, 160) : null,
        isSvg,
        isImg,
      });
    });
  });

  // Restore whatever display value each slide had before we forced it visible —
  // this extraction must leave the live page exactly as it found it.
  slides.forEach(s => { s.style.display = originalDisplay.get(s) || ''; });

  return {
    viewportWidthPx: document.documentElement.clientWidth,
    viewportHeightPx: document.documentElement.clientHeight,
    slideCount: slides.length || 1,
    elements,
  };
}
"""


@tool
def extract_computed_styles() -> str:
    """Render presentation.html headlessly and dump every visible element's
    real computed style to .browser/deck-styles.json in the run workspace.

    Call this BEFORE authoring PptxGenJS code — read the file it writes and use
    its numbers for position, rotation, font, fill, border and shadow instead
    of estimating them from the HTML/CSS text. Rotation is already measured
    from the real render and normalized to 0-359, ready to pass straight into
    a shape's `rotate` option.

    Positions and sizes are in PIXELS relative to the rendered viewport
    (`viewportWidthPx`/`viewportHeightPx` are included) — convert to your
    canvas the same way you already convert `vw`:
    `(px / viewportWidthPx) * canvasWidthIn`.

    Returns an actionable message: how many elements were captured, or why
    extraction could not run.
    """
    if _SANDBOX is None:
        return "no run sandbox is bound — cannot render the deck."

    html_path = Path(_SANDBOX.path_for(DECK_NAME))
    if not html_path.is_file():
        return f"{DECK_NAME} does not exist yet — nothing to extract styles from."

    from app.agents.playwright_session import (
        get_session,
        resolve_url_policy,
        run_id_from_sandbox,
        run_sync,
    )

    run_id = run_id_from_sandbox(_SANDBOX)
    if not run_id:
        return "cannot extract run_id from context — style extraction unavailable."

    session = get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    policy_result = resolve_url_policy(DECK_NAME, _SANDBOX)
    if isinstance(policy_result, tuple) and policy_result[0] == "refused":
        return policy_result[1]
    resolved_url = policy_result

    try:
        context = run_sync(session.acquire("ppt-code-generator"))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"
        page = run_sync(context.new_page())
        try:
            run_sync(page.goto(resolved_url, wait_until="load", timeout=30000))
            result = run_sync(page.evaluate(_EXTRACT_STYLES_JS))
        finally:
            run_sync(page.close())
    except Exception as exc:  # noqa: BLE001 — actionable text, never a raise (FR-017 pattern)
        return f"style extraction failed: {exc}"

    if not isinstance(result, dict):
        return "style extraction returned an unexpected result — the deck may not have rendered."

    out_path = Path(_SANDBOX.path_for(".browser/deck-styles.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    n = len(result.get("elements", []))
    return (
        f"extracted computed styles for {n} element(s) to .browser/deck-styles.json "
        f"— read it before authoring PptxGenJS; its rotation/font/color/position "
        f"values are measured from the real render, not estimated."
    )


def _pptx_path() -> Path | None:
    if _SANDBOX is None:
        return None
    return Path(_SANDBOX.path_for(PPTX_NAME))


def _html_slide_count() -> int | None:
    """How many slides the source deck has, or None if it cannot be read."""
    if _SANDBOX is None:
        return None
    try:
        html = Path(_SANDBOX.path_for(DECK_NAME)).read_text(encoding="utf-8")
    except OSError:
        return None
    return sum(1 for m in _HTML_SLIDE.finditer(html) if "slide" in m.group(2).split())


def _pptx_slide_count(path: Path) -> int | None:
    try:
        from pptx import Presentation

        return len(Presentation(str(path)).slides._sldIdLst)
    except Exception:  # noqa: BLE001 — an unreadable deck is reported elsewhere
        return None


def _html_rotation_count() -> int:
    """How many `rotate(Xdeg)` declarations the source deck has. 0 if unreadable."""
    if _SANDBOX is None:
        return 0
    try:
        html = Path(_SANDBOX.path_for(DECK_NAME)).read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(_HTML_ROTATE.findall(html))


def _pptx_rotation_count(path: Path) -> int | None:
    try:
        from pptx import Presentation

        prs = Presentation(str(path))
        return sum(
            1
            for slide in prs.slides
            for shape in slide.shapes
            if getattr(shape, "rotation", 0)
        )
    except Exception:  # noqa: BLE001 — an unreadable deck is reported elsewhere
        return None


def _deck_styles_radius_count() -> int:
    """How many elements `extract_computed_styles()` measured with a real
    border-radius. 0 if that tool was never called or the file is unreadable —
    this gate only fires on ground truth it actually has, never a guess."""
    if _SANDBOX is None:
        return 0
    try:
        data = json.loads(Path(_SANDBOX.path_for(".browser/deck-styles.json")).read_text())
    except (OSError, ValueError):
        return 0
    return sum(1 for el in data.get("elements", []) if (el.get("borderRadiusPx") or 0) > 0)


_ROUNDED_AUTO_SHAPES = frozenset({
    "ROUNDED_RECTANGLE", "ROUND_1_RECTANGLE", "ROUND_2_DIAG_RECTANGLE",
    "ROUND_2_SAME_RECTANGLE", "OVAL",
})


def _pptx_rounded_shape_count(path: Path) -> int | None:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        prs = Presentation(str(path))
        count = 0
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.shape_type != MSO_SHAPE_TYPE.AUTO_SHAPE:
                    continue
                try:
                    if shape.auto_shape_type is not None and shape.auto_shape_type.name in _ROUNDED_AUTO_SHAPES:
                        count += 1
                except (ValueError, AttributeError):
                    continue
        return count
    except Exception:  # noqa: BLE001 — an unreadable deck is reported elsewhere
        return None


def _font_slug(name: str) -> str:
    """Same normalisation the one-time font-download job used for filenames."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _available_eot(font_name: str) -> Path | None:
    """The pre-fetched .eot for this font name, if the library has one."""
    if not font_name:
        return None
    path = _FONTS_DIR / f"{_font_slug(font_name)}-Regular.eot"
    return path if path.is_file() else None


def _pptx_fonts_used(path: Path) -> set[str]:
    """Every distinct font name any run in the built deck actually specifies."""
    try:
        from pptx import Presentation

        prs = Presentation(str(path))
        names: set[str] = set()
        for slide in prs.slides:
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.font.name:
                            names.add(run.font.name)
        return names
    except Exception:  # noqa: BLE001 — an unreadable deck is reported elsewhere
        return set()


def _embed_fonts(path: Path) -> int:
    """Embed the real font bytes for every font the deck uses that this
    project has a pre-fetched .eot for (skills/opendesign/fonts/). Rewrites
    the .pptx zip in place. Returns how many fonts were embedded — 0 if the
    deck used no font this library has, which is the common case and not an
    error.

    Never raises: embedding is an enhancement to a deck that already passed
    every other gate. A failure here must not turn a shippable deck into a
    blocked one — it just ships without the embedded fonts, same as before
    this existed.
    """
    try:
        to_embed = [
            (name, eot)
            for name in sorted(_pptx_fonts_used(path))
            if (eot := _available_eot(name)) is not None
        ]
        if not to_embed:
            return 0

        with zipfile.ZipFile(path, "r") as zin:
            entries = {info.filename: zin.read(info.filename) for info in zin.infolist()}

        presentation_xml = entries["ppt/presentation.xml"].decode("utf-8")
        rels_xml = entries["ppt/_rels/presentation.xml.rels"].decode("utf-8")
        content_types_xml = entries["[Content_Types].xml"].decode("utf-8")

        # 1. [Content_Types].xml — .fntdata needs a registered content type,
        #    or PowerPoint cannot resolve the new zip entries at all.
        if 'Extension="fntdata"' not in content_types_xml:
            content_types_xml = content_types_xml.replace(
                "</Types>",
                '<Default Extension="fntdata" ContentType="application/x-fontdata"/></Types>',
            )

        # 2. presentation.xml.rels — one relationship per embedded font,
        #    numbered past whatever rIds already exist.
        existing_ids = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels_xml)]
        next_id = max(existing_ids, default=0) + 1
        rel_entries = []
        font_font_ids = []
        for i, (name, eot) in enumerate(to_embed):
            rid = f"rId{next_id + i}"
            font_font_ids.append(rid)
            rel_entries.append(
                f'<Relationship Id="{rid}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font" '
                f'Target="fonts/font{i + 1}.fntdata"/>'
            )
        rels_xml = rels_xml.replace("</Relationships>", "".join(rel_entries) + "</Relationships>")

        # 3. presentation.xml — embedTrueTypeFonts="true" on the root element,
        #    plus one <p:embeddedFont> per font. Schema order places
        #    embeddedFontLst immediately before defaultTextStyle.
        if "embedTrueTypeFonts" not in presentation_xml:
            presentation_xml = presentation_xml.replace(
                "<p:presentation ", '<p:presentation embedTrueTypeFonts="true" ', 1
            )
        font_entries = "".join(
            f'<p:embeddedFont><p:font typeface="{name}"/><p:regular r:id="{rid}"/></p:embeddedFont>'
            for (name, _eot), rid in zip(to_embed, font_font_ids)
        )
        embedded_lst = f"<p:embeddedFontLst>{font_entries}</p:embeddedFontLst>"
        if "<p:defaultTextStyle>" in presentation_xml:
            presentation_xml = presentation_xml.replace(
                "<p:defaultTextStyle>", embedded_lst + "<p:defaultTextStyle>", 1
            )
        else:
            presentation_xml = presentation_xml.replace(
                "</p:presentation>", embedded_lst + "</p:presentation>", 1
            )

        entries["[Content_Types].xml"] = content_types_xml.encode("utf-8")
        entries["ppt/_rels/presentation.xml.rels"] = rels_xml.encode("utf-8")
        entries["ppt/presentation.xml"] = presentation_xml.encode("utf-8")
        for i, (_name, eot) in enumerate(to_embed):
            entries[f"ppt/fonts/font{i + 1}.fntdata"] = eot.read_bytes()

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
            for filename, data in entries.items():
                zout.writestr(filename, data)

        return len(to_embed)
    except Exception as exc:  # noqa: BLE001 — never block a shippable deck
        logger.warning("font embedding skipped (non-fatal): %s", exc)
        return 0


def _verify_dir() -> Path | None:
    if _SANDBOX is None:
        return None
    d = Path(_SANDBOX.path_for(VERIFY_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_attempt(code: str) -> None:
    """Keep each build's exact PptxGenJS source as .verify/attempt-NN.js.

    The run trace elides a 24 KB tool argument on purpose — a readable log beats
    a complete one nobody opens. The source still has to exist somewhere for a
    post-mortem, so it goes on disk beside the report instead of into the log.
    """
    d = _verify_dir()
    if d is None:
        return
    try:
        n = len(list(d.glob("attempt-*.js"))) + 1
        (d / f"attempt-{n:02d}.js").write_text(code, encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 — evidence is best-effort
        logger.warning("could not save the attempt source: %s", exc)


def _write_report(verdict: str, body: str) -> None:
    """Append this attempt's verdict + full report to <sandbox>/.verify/report.txt."""
    d = _verify_dir()
    if d is None:
        return
    try:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with (d / "report.txt").open("a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 72}\n{stamp}  {verdict}\n{'=' * 72}\n{body}\n")
    except OSError as exc:  # noqa: BLE001 — evidence is best-effort, never fatal
        logger.warning("could not write the verify report: %s", exc)


def _render_slides() -> tuple[str, int | None]:
    """Render the built deck to PNGs under <sandbox>/.verify/. Returns
    ``(message, page_count)``; ``page_count`` is None when nothing was rendered.

    Rendering is a REAL check, not decoration, and it is the only one here that
    exercises the file the way the recipient's app will: LibreOffice refusing to
    open a deck means PowerPoint will refuse it too, and a page count short of
    the slide count means slides silently vanished. The PNGs are for the human —
    the runner stringifies every tool result, so the model reads this summary,
    not the pixels.

    Absent tooling is reported, never treated as a pass.
    """
    d = _verify_dir()
    path = _pptx_path()
    if d is None or path is None or not path.is_file():
        return "no deck to render.", None
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return "not rendered — LibreOffice is not installed here.", None
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(d), str(path)],
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"not rendered — {exc}", None
    pdf = d / f"{path.stem}.pdf"
    if not pdf.is_file():
        return (
            "FAILED TO OPEN — LibreOffice could not load the deck. A file no "
            "renderer will open is corrupt; PowerPoint will refuse it too.",
            None,
        )
    if not shutil.which("pdftoppm"):
        return "converted, but pdftoppm is missing so no images were written.", None
    try:
        subprocess.run(
            [shutil.which("pdftoppm"), "-png", "-r", "60", str(pdf), str(d / "slide")],
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"converted, but images failed — {exc}", None
    pages = sorted(d.glob("slide-*.png"))
    return f"rendered {len(pages)} slide image(s) into {VERIFY_DIR}/.", len(pages)


def _run_audit(script: str, *args: str) -> tuple[int, str]:
    """Run one audit script on the built deck. Returns (exit_code, combined output)."""
    path = _pptx_path()
    if path is None:
        return 1, "no run sandbox is bound — the pptx tools are unavailable in this context."
    if not path.is_file():
        return 1, f"{PPTX_NAME} does not exist yet — call render_pptx first."
    proc = subprocess.run(
        [sys.executable, str(_AUDIT_SCRIPTS / script), str(path), *args],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


@tool
def render_pptx(pptxgenjs_code: str) -> str:
    """Build presentation.pptx from PptxGenJS source and save it to the run workspace.

    Pass the COMPLETE script. It must create `pres`, add every slide, and end with
    `return pres.write("nodebuffer");`. Do not use require/import — PptxGenJS is
    already in scope.

    The deck is VERIFIED before this returns. You will not get "ok" for a deck
    with overlapping text, text that does not fit its box, or shapes off the
    canvas — you get the violations, and you fix them and call this again.
    """
    path = _pptx_path()
    if path is None:
        return "no run sandbox is bound — cannot write the pptx."

    from app.services.pptx_export import generate_pptx_from_code

    try:
        data = generate_pptx_from_code(pptxgenjs_code, "Presentation")
    except Exception as exc:  # noqa: BLE001 — the message IS the retry signal
        # Deliberately surfaced verbatim rather than a generic failure: this
        # string is what the agent reads to fix its own code, so replacing it
        # with "generation failed" would make the retry loop blind.
        logger.info("render_pptx: generation failed — %s", exc)
        return f"FAILED — the code did not produce a pptx:\n{exc}"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    _save_attempt(pptxgenjs_code)

    # ── The gate ──────────────────────────────────────────────────────────────
    # Verification runs HERE, not in a separate tool the agent may or may not
    # call, because a separate tool is something to disagree with — and that is
    # exactly what happened: shown a violation it considered spurious, an agent
    # decided "the layout is clean and correct" and shipped a deck whose every
    # headline printed through its own body copy. There is nothing to overrule
    # if "ok" is only ever returned for a deck that passed.
    #
    # The file is still written first, deliberately: a deck with three fixable
    # violations is far more useful on disk than no deck at all, and the run's
    # single_file deliverable would otherwise have nothing to fall back to.
    # Slide count first: "transcribe every slide" is the one rule the layout
    # checks cannot express, because a deck that dropped eight slides is
    # geometrically perfect on the four it kept.
    want = _html_slide_count()
    got = _pptx_slide_count(path)
    if want and got is not None and got < want:
        msg = (
            f"BUILT but INCOMPLETE — {PPTX_NAME} has {got} slide(s) and the deck "
            f"has {want}. Transcribe every slide, in order, and call render_pptx "
            f"again."
        )
        _write_report("INCOMPLETE", msg)
        return msg

    # Rotation next, same reasoning as the slide count above: a deck can be
    # geometrically perfect and font-correct while every tilted badge/stamp/
    # label in the source HTML shipped dead straight — the layout audit has no
    # way to know the HTML wanted a shape rotated. Only fires on a REPEATED
    # motif (>= 3 CSS rotations) with ZERO rotation anywhere in the built deck,
    # so a single incidental decorative flourish is never forced — this is
    # for the case where a whole design language got flattened.
    html_rotated = _html_rotation_count()
    pptx_rotated = _pptx_rotation_count(path)
    if html_rotated >= 3 and pptx_rotated == 0:
        msg = (
            f"BUILT but MISSING ROTATION — the deck's HTML has {html_rotated} tilted "
            f"element(s) (`transform: rotate(Xdeg)`, a deliberate design motif) but "
            f"{PPTX_NAME} has none rotated. Re-read the html-deck-to-pptx skill's "
            f"Rotation section, add a `rotate:` option (0-359, converted from the "
            f"CSS degree) to the shapes/text boxes that were tilted in the HTML, "
            f"and call render_pptx again."
        )
        _write_report("MISSING ROTATION", msg)
        return msg

    # Same reasoning again, for rounded corners: extract_computed_styles()
    # already measured which elements are real "sticky note" cards/badges
    # (non-zero border-radius) — a skill instruction alone did not get this
    # used even once across 8 attempts in a real run, so it is a gate now,
    # not a suggestion. Fires only when there is a genuine repeated motif
    # (>= 3 measured radii) and the built deck used zero rounded shapes.
    html_radius = _deck_styles_radius_count()
    pptx_rounded = _pptx_rounded_shape_count(path)
    if html_radius >= 3 and pptx_rounded == 0:
        msg = (
            f"BUILT but MISSING ROUNDED CORNERS — deck-styles.json measured "
            f"{html_radius} element(s) with a real border-radius (cards, badges — "
            f"a deliberate design motif) but {PPTX_NAME} has none rounded. Use "
            f"`pres.ShapeType.roundRect` with `rectRadius` (inches, converted from "
            f"the element's borderRadiusPx) for those shapes instead of the default "
            f"rectangle, and call render_pptx again."
        )
        _write_report("MISSING ROUNDED CORNERS", msg)
        return msg

    code, out = _run_audit("verify_layout.py")
    if code != 0:
        _write_report("NOT SHIPPABLE", out)
        return (
            f"BUILT but NOT SHIPPABLE — {PPTX_NAME} was written ({len(data)} bytes) "
            f"and then verified. Fix these and call render_pptx again:\n{out}"
        )

    # ── Render LAST, on the candidate that would otherwise ship ───────────────
    # The cheap deterministic checks run on every attempt; this one runs once, on
    # the deck about to be called good. It is the only check that exercises the
    # file the way the recipient's app will — and the images it leaves behind are
    # how a human can see what the gate saw, instead of taking "clean" on trust.
    render_msg, pages = _render_slides()
    if pages is not None and got and pages < got:
        msg = (
            f"BUILT but slides went MISSING when rendered — the deck has {got} "
            f"slide(s) and only {pages} rendered. {render_msg}"
        )
        _write_report("SLIDES LOST ON RENDER", msg)
        return msg
    if "FAILED TO OPEN" in render_msg:
        _write_report("CORRUPT", render_msg)
        return f"BUILT but UNREADABLE — {render_msg} Rebuild it."

    # Embed real font bytes for whatever this deck used that the pre-fetched
    # library covers — after the render check, so this only ever touches a
    # file already confirmed to open. Silent no-op when nothing matches.
    embedded_count = _embed_fonts(path)
    final_bytes = path.stat().st_size if path.is_file() else len(data)
    font_note = (
        f" {embedded_count} font(s) embedded so the recipient sees the real "
        f"typeface without having it installed."
        if embedded_count
        else ""
    )

    _write_report("SHIPPABLE", f"{out}\n{render_msg}")
    return (
        f"ok — wrote and verified {PPTX_NAME} ({final_bytes} bytes, {got or '?'} "
        f"slides).{font_note} {render_msg} The report and images are in {VERIFY_DIR}/."
    )


@tool
def verify_pptx_layout() -> str:
    """Re-check the built presentation.pptx on its own.

    render_pptx already verifies what it builds, so you rarely need this — it is
    here to re-read the current verdict without rebuilding. Returns "clean" when
    the deck is shippable, or the specific violations (slide index, shape name,
    measurement) to fix and re-render.
    """
    code, out = _run_audit("verify_layout.py")
    if code == 0:
        return f"clean — no layout violations.\n{out}" if out else "clean — no layout violations."
    return f"VIOLATIONS — fix these and call render_pptx again:\n{out}"


@tool
def screenshot_pptx() -> str:
    """Render the built presentation.pptx to slide images in the run workspace.

    Use this when a violation does not match what you believe you wrote, or to
    confirm the deck opens at all. Writes `.verify/slide-NN.png` and reports how
    many slides rendered — a deck no renderer will open is corrupt, and a page
    count below the slide count means slides were lost.
    """
    msg, pages = _render_slides()
    _write_report("SCREENSHOT", msg)
    return msg


@tool
def extract_pptx_shapes() -> str:
    """Dump every shape in the built presentation.pptx with its real position and size.

    Ground truth for debugging a layout violation — what the file actually contains,
    not what the source intended.
    """
    code, out = _run_audit("extract_pptx.py")
    if code != 0 and not out:
        return "could not read the deck."
    return out or "no shapes found."
