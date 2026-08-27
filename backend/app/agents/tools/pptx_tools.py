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

import logging
import re
import shutil
import subprocess
import sys
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

# Bound by the factory at runner-composition time. Module-level because a
# LangChain @tool takes only the model's arguments — the sandbox is ambient
# per-run state, never something the model should be able to name.
_SANDBOX: Any = None

_AUDIT_SCRIPTS = (
    Path(__file__).resolve().parents[4]
    / "skills" / "opendesign" / "skills" / "pptx-html-fidelity-audit" / "scripts"
)


def bind_sandbox(sandbox: Any) -> None:
    """Point the tools at this run's sandbox. Called by the factory, not the model."""
    global _SANDBOX
    _SANDBOX = sandbox


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

    _write_report("SHIPPABLE", f"{out}\n{render_msg}")
    return (
        f"ok — wrote and verified {PPTX_NAME} ({len(data)} bytes, {got or '?'} "
        f"slides). {render_msg} The report and images are in {VERIFY_DIR}/."
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
