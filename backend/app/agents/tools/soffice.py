"""app/agents/tools/soffice.py — the one LibreOffice invocation (spec 019, FR-041).

Two callers need to turn an Office file into a PDF: the document materialiser
(`pdf_tools`, for `.docx` / `.xlsx` / `.pptx` uploads) and spec 017's deck check
(`pptx_tools._render_slides`, to prove a generated `.pptx` opens at all). They
share this module rather than each spawning their own subprocess, because two
copies of an invocation drift and the one that drifts is the one nobody reads.

Environment divergence is the thing to know here (FR-027a). A developer machine
usually has LibreOffice from Homebrew, so conversions really happen; the built
image installs it only if `backend/Dockerfile` says so. `available()` answers
that question honestly instead of letting a missing binary read as a pass.

Never raises. Every failure — absent binary, timeout, crash, refusal to open —
comes back as text naming which one it was.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# The 180s spec 017 already uses. A conversion that has not finished by then is
# hung on a dialog no one can click, not slow.
CONVERT_TIMEOUT_SECONDS = 180

# Formats this project accepts for conversion. LibreOffice reads far more (.doc,
# .odt, .rtf, …); widening what the platform ingests is a security decision and
# belongs in run_files.py's allowlist, not here (FR-040).
CONVERTIBLE_SUFFIXES = frozenset({".docx", ".xlsx", ".pptx"})


def find_binary() -> str | None:
    """Absolute path to soffice, or None when LibreOffice is not installed."""
    return shutil.which("soffice") or shutil.which("libreoffice")


def available() -> bool:
    """True when a conversion could actually run here."""
    return find_binary() is not None


def unavailable_message(what: str) -> str:
    """The one wording for 'no converter here', so both callers say the same thing."""
    return (
        f"cannot convert {what} — LibreOffice is not installed in this environment. "
        f"Install it (the `soffice` binary) to enable Office document support; "
        f"PDF uploads are unaffected."
    )


def convert_to_pdf(
    src: Path,
    out_dir: Path,
    timeout: int = CONVERT_TIMEOUT_SECONDS,
) -> tuple[Path | None, str]:
    """Convert `src` to a PDF in `out_dir`. Returns (pdf_path, "") or (None, message).

    Each call gets its OWN LibreOffice profile directory (FR-032). A shared
    profile is not concurrency-safe: two soffice processes against one profile
    race, and the loser exits successfully having produced nothing — which reads
    as "conversion produced no output" and sends you looking at the document.
    The materialiser's process pool makes that collision reachable, so this is
    not a theoretical precaution.
    """
    soffice = find_binary()
    if soffice is None:
        return None, unavailable_message(src.name)

    if not src.is_file():
        return None, f"cannot convert {src.name} — file not found"

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"cannot convert {src.name} — output directory unusable: {exc}"

    profile = Path(tempfile.mkdtemp(prefix=f"soffice-{uuid.uuid4().hex[:8]}-"))
    try:
        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--norestore",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(src),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, (
            f"cannot convert {src.name} — LibreOffice did not finish within {timeout}s "
            f"and was killed. A conversion this slow is usually blocked on a dialog "
            f"(a password prompt, a repair prompt) that headless mode cannot answer."
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"cannot convert {src.name} — LibreOffice failed to start: {exc}"
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    produced = out_dir / f"{src.stem}.pdf"
    if not produced.is_file():
        message = (
            f"cannot convert {src.name} — LibreOffice could not open it. A file no "
            f"renderer will open is corrupt or password-protected; the authoring "
            f"application will refuse it too."
        )
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        if detail:
            message += f" Converter said: {detail}"
        return None, message

    return produced, ""
