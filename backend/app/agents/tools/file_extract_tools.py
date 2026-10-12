"""app/agents/tools/file_extract_tools.py — document materialisation tools (spec 019).

Materialise an uploaded document into a folder of pages an agent can work with:
layout-aware text with @[[image-N.png]] placeholders in reading order, and one cropped
image per picture that preserves the annotation arrows the embedded image loses.

ONE ENTRY POINT FOR EVERY FORMAT (FR-039). `extract_text` takes a .pdf, .docx, .xlsx,
.pptx, .html or .htm and the agent never learns which one needed a converter: an Office
file is turned into a PDF by LibreOffice (see `soffice.py`), cached as
.extract/{format}/{slug}/source.pdf, and then runs through exactly the same materialiser.
An .html/.htm file is opened in a headless browser (or, if none can launch, read
statically) and materialised screen by screen — see `html_extract.py` (spec 021). There
is no second extractor and no second on-disk layout — an agent that must know a
document's container format in order to pick a tool has been handed the implementation
as an interface.

The four tools:
  - extract_text(path, pages="") — materialise a document into .extract/{format}/{slug}/pages/NN/
  - file_info(path="") — inventory every upload or inspect one document
  - file_find(query, path="", limit=50) — search the materialised text layer
  - file_page_image(path, page) — render a full page for diagram-heavy layouts

A CONVERTED DOCUMENT'S PAGE NUMBERS ARE LIBREOFFICE'S, NOT WORD'S (FR-035). A .docx has
no fixed pagination until something paginates it, so every string citing a page for a
converted document says where that page number came from.

Sandbox binding: the factory binds these per run (_resolve_custom_tool_keys), so _SANDBOX
is set at bind time and every path goes through RunSandbox.path_for (traversal-proof).

PDF libraries are imported LAZILY, inside the functions that use them — the factory
imports this module at composition time and must not pull pdfminer into every run.

Never-raise discipline: every public entry point returns a readable string on failure.
A tool that raises kills the step.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import json
import logging
import os
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.agents.tools import soffice

logger = logging.getLogger(__name__)

# Tool key constants — emitted by the documents capability provider (spec 019)
EXTRACT_TEXT = "extract_text"
FILE_INFO = "file_info"
FILE_FIND = "file_find"
FILE_PAGE_IMAGE = "file_page_image"

# Uploads prefix — files the POST /api/runs/{id}/files endpoint lands here.
_UPLOADS_PREFIX = ".uploads/"

# Reserved prefix materialised documents live under; mirrors sandbox._EXTRACT_PREFIX
# (deliverable-excluded there, FR-018).
_EXTRACT_PREFIX = ".extract/"

# THREE ROUTES, ONE ENTRY POINT (FR-044).
#   text      -> the content comes straight back in the tool result; nothing is
#                written, because materialising a .txt into pages of itself is
#                work that buys the agent nothing.
#   paged     -> materialised into .extract/{format}/{slug}/; the receipt names
#                document.md and the content stays on disk. A large document's
#                text does not fit in a tool result, which is why this exists.
#   anything else -> refused in readable text. No blind conversion attempt: the
#                upload allow-list is what decides which bytes reach this process
#                (FR-040), and LibreOffice is a large C++ parser to aim at
#                unknown input.
_TEXT_FORMATS = frozenset({"txt", "md", "csv", "json"})
_PAGED_FORMATS = frozenset({"pdf", "docx", "xlsx", "pptx"})
# .html and .htm both land in ONE format directory ("html", spec 021 §6.1) and take
# their own browser/static route — never the pdfium pipeline _PAGED_FORMATS drives.
_HTML_FORMATS = frozenset({"html", "htm"})
_SUPPORTED_FORMATS = _TEXT_FORMATS | _PAGED_FORMATS | _HTML_FORMATS
_CONVERTED_FORMATS = frozenset({"docx", "xlsx", "pptx"})

# A plain-text file is returned inline, so it needs a ceiling the paged route does
# not: a 5 MB CSV would otherwise land whole in one tool result.
_TEXT_INLINE_MAX_CHARS = 100_000

# NO PAGE CAP, deliberately (FR-034). A client's 1000-page PDF is real content,
# not an abuse case, and refusing it would be the tool failing at its own job.
# Measured on the screenshot-heavy reference document — the worst case for size,
# since text-only pages are far smaller:
#     204 KB/page      ->  1000 pages ~= 0.19 GB on disk
#     1.7s / 21 pages  ->  ~83s sequential, ~25s once the process pool engages
# above _PARALLEL_PAGE_THRESHOLD. Resume (the folder IS the state) means an
# interrupted 1000-page run continues rather than restarting, and `pages=` lets a
# caller work in slices by choice instead of by refusal.
#
# Page count above which the receipt MENTIONS that `pages=` exists. Purely
# advisory — nothing is ever refused for being large.
_LARGE_DOCUMENT_PAGES = 100


def _doc_rel(source_format: str, slug: str) -> str:
    """The sandbox-relative directory for one materialised document.

    .extract/{format}/{slug}/ — the format is a directory level rather than a
    slug suffix, so `.extract/pdf/report/` and `.extract/docx/report/` are
    different documents by construction (FR-030), and `.extract/docx/` reads as
    "every Word document this run has materialised".
    """
    return f"{_EXTRACT_PREFIX}{source_format}/{slug}"


def _format_of(filename: str) -> str:
    """Lowercase extension without the dot ("report.DOCX" -> "docx")."""
    return os.path.splitext(filename)[1].lstrip(".").lower()


def _canonical_format(fmt: str) -> str:
    """.html and .htm share ONE format directory: "html" (spec 021 §6.1).

    Every other format directory is its own extension, unchanged.
    """
    return "html" if fmt in _HTML_FORMATS else fmt


def _pagination_note(converted_by: str | None) -> str:
    """The FR-035 caveat, or "" for a native PDF.

    Word and LibreOffice do not agree on where page 4 begins. Citing a converted
    document's page number without saying whose pagination it is repeats FR-022's
    defect in a new costume.
    """
    if not converted_by:
        return ""
    return (
        f"\nNOTE: this document was converted by {converted_by}; page numbers are "
        f"the converter's pagination, which the authoring application may not share."
    )


# Fragment merge gap (points) — images this close vertically with overlapping x ranges
# are merged into one picture (FR-005a).
_FRAGMENT_MERGE_GAP = 2.0

# How close two glyph runs must be before pdfplumber calls them ONE word.
# pdfplumber's default of 3.0 is tuned for prose, where a 3pt gap really is one
# word. A converted SPREADSHEET breaks that assumption: a right-aligned number
# ends flush against the next column's left-aligned value, so "46445" and "Yes"
# arrive as the single token "46445Yes" — a value that does not exist in the
# workbook. Measured on the reference documents: 1.5 separates those columns and
# leaves prose byte-identical (15,072 chars on the 21-page PDF at every tolerance
# from 3.0 down to 1.0), so this costs nothing to tighten.
_WORD_X_TOLERANCE = 1.5


# Module state — bound by the factory at run-entry.
_SANDBOX: Any = None


def bind_sandbox(sandbox: Any) -> None:
    """Bind the per-run sandbox (called by the factory at composition time)."""
    global _SANDBOX
    _SANDBOX = sandbox


def _resolve_path(relpath: str) -> tuple[Path | None, str]:
    """Resolve an uploads-relative path through RunSandbox.path_for.

    Returns (Path, "") on success, or (None, error_string) on failure.
    Rejects traversal attempts ("../../etc/passwd") and absolute paths.
    """
    if _SANDBOX is None:
        return None, "document tools not bound to a run sandbox (internal error)"

    # `/.uploads/x.pdf` and `.uploads/x.pdf` both resolve. A leading slash is
    # stripped rather than refused, matching every other sandbox-bound tool
    # (`sandbox.path_for`, `runtime.local`) — and matching what `ls`/`glob` HAND
    # BACK, which is where agents pick the slash form up in the first place.
    # Refusing it made two tool contracts disagree inside one run: observed live,
    # a planner burned 12 extract_text calls cycling spellings and materialised
    # nothing.
    #
    # This is a spelling rule, not the security boundary. Containment is enforced
    # by `path_for`, which resolves the path and rejects anything escaping the
    # run root — `../../etc/passwd` is still refused, and `/etc/passwd` now
    # resolves to `<run root>/etc/passwd`, which does not exist.
    relpath = str(relpath).lstrip("/")

    try:
        # path_for is traversal-proof: it resolves the path and rejects escapes.
        candidate = _SANDBOX.path_for(relpath)
        return candidate, ""
    except ValueError as e:
        return None, f"path rejected: {e}"


def _missing_source_message(relpath: str, base_error: str) -> str:
    """Explain a missing source PDF, distinguishing a wiped workspace from a
    document that was never uploaded (FR-021).

    A resumed run can lose .uploads/ while .extract/ survives. Saying only "path
    is not a file" sends the agent looking for an upload that will never come,
    when every page it needs is already materialised beside it.
    """
    filename = os.path.basename(relpath)
    rel = _doc_rel(_canonical_format(_format_of(filename)), _slug_from_filename(filename))
    doc_dir, err = _resolve_path(rel)
    if err or doc_dir is None or not (doc_dir / "manifest.json").is_file():
        return base_error
    return (
        f"{base_error} — but its materialised pages survive at {rel}/. "
        f"The source document is gone from this workspace (a resumed run), not "
        f"missing because it was never uploaded. Read {rel}/document.md, or search "
        f"with file_find; re-materialising is impossible without the source."
    )


def _read_bytes(relpath: str) -> tuple[bytes | None, str]:
    """Read bytes from an uploads-relative path.

    Returns (bytes, "") on success, or (None, error_string) on failure.
    """
    candidate, err = _resolve_path(relpath)
    if err:
        return None, err

    try:
        if not candidate.is_file():
            return None, f"path is not a file: {relpath}"
        with open(candidate, "rb") as f:
            return f.read(), ""
    except (OSError, IOError) as e:
        return None, f"failed to read {relpath}: {e}"


def _list_uploads() -> tuple[list[str], str]:
    """List uploaded PDFs in the sandbox in sorted order.

    Returns (list[filename], "") on success, or ([], error_string) on failure.
    """
    if _SANDBOX is None:
        return [], "document tools not bound to a run sandbox (internal error)"

    try:
        uploads_path = _SANDBOX.path_for(_UPLOADS_PREFIX)
    except ValueError:
        # path_for rejects the path (should never happen with a constant prefix)
        return [], "uploads directory not accessible"

    if not uploads_path.is_dir():
        return [], ""  # No uploads directory — empty list, no error.

    try:
        # List all files in .uploads/, filter to .pdf files, sort by name.
        pdfs = []
        for entry in os.listdir(uploads_path):
            full_path = uploads_path / entry
            if full_path.is_file() and _format_of(entry) in _SUPPORTED_FORMATS:
                pdfs.append(entry)
        return sorted(pdfs), ""
    except (OSError, IOError) as e:
        return [], f"failed to list uploads: {e}"


def _slug_from_filename(filename: str) -> str:
    """Derive a filesystem-safe slug from an upload filename.

    "Inland Marine Creating a Quote 2.pdf" → "inland-marine-creating-a-quote-2"

    The extension is NOT in the slug: the format is its own directory level
    (.extract/{format}/{slug}/), which is what keeps "report.docx" and
    "report.pdf" apart. Without one of those two mechanisms they name the same
    folder, each extract sees the other's source_sha256, calls the folder stale
    and re-materialises — alternating forever (FR-030).

    Rules:
      - Convert to lowercase
      - Drop the file extension
      - Replace non-alphanumeric chars (except '-') with '-'
      - Strip leading/trailing '-' and collapse runs
    """
    base = os.path.splitext(filename)[0]

    # Lowercase
    base = base.lower()

    # Replace non-alphanumeric (except '-') with '-'
    base = re.sub(r"[^a-z0-9-]", "-", base)

    # Strip leading/trailing '-' and collapse consecutive '-' into one
    base = re.sub(r"-+", "-", base).strip("-")

    return base


def _list_all_uploads() -> tuple[list[tuple[str, bool]], str]:
    """List all uploaded files in the sandbox in sorted order.

    Returns (list[(filename, supported)], "") on success, or ([], error) on failure.
    `supported` is True for any format these tools can materialise — a .docx is
    readable here even though it reaches the materialiser through a converter.
    """
    if _SANDBOX is None:
        return [], "document tools not bound to a run sandbox (internal error)"

    try:
        uploads_path = _SANDBOX.path_for(_UPLOADS_PREFIX)
    except ValueError:
        # path_for rejects the path (should never happen with a constant prefix)
        return [], "uploads directory not accessible"

    if not uploads_path.is_dir():
        return [], ""  # No uploads directory — empty list, no error.

    try:
        # List all files in .uploads/, with their readability status
        files = []
        for entry in os.listdir(uploads_path):
            full_path = uploads_path / entry
            if full_path.is_file():
                files.append((entry, _format_of(entry) in _SUPPORTED_FORMATS))
        return sorted(files, key=lambda x: x[0]), ""
    except (OSError, IOError) as e:
        return [], f"failed to list uploads: {e}"


# Threshold for text-layer detection (characters per page) — FR-009a
_TEXT_LAYER_THRESHOLD = 100


def file_info(path: str = "") -> str:
    """Inventory every upload or inspect one document.

    With no path: list all uploads in sorted order, marking which are PDFs.
    A run with no uploads says so explicitly rather than returning an empty list.

    With a path: report page count, per-page text-layer verdict, character density,
    image count, encryption state, metadata, outline, and estimated token cost.

    Never materialises anything.

    Returns readable text describing the document(s) or an error message.
    """
    # Empty path: inventory mode
    if not path or path.strip() == "":
        uploads, err = _list_all_uploads()
        if err:
            return err

        if not uploads:
            return "No uploads in this run."

        # Build inventory report
        lines = ["Uploads in this run:\n"]
        for filename, is_pdf in uploads:
            fmt = _format_of(filename)
            if fmt in _TEXT_FORMATS:
                status = "✓ plain text — extract_text returns its content directly"
            elif fmt in _PAGED_FORMATS:
                status = "✓ extract_text materialises it into .extract/"
            elif fmt in _HTML_FORMATS:
                status = "✓ extract_text materialises it into .extract/, screen by screen"
            else:
                status = "✗ unsupported — these tools read " + ", ".join(
                    "." + f for f in sorted(_SUPPORTED_FORMATS)
                )
            lines.append(f"  • {filename} — {status}")

        return "\n".join(lines)

    # Path provided: profile mode
    profile_format = _format_of(os.path.basename(path))
    if profile_format in _TEXT_FORMATS:
        raw, err = _read_bytes(path)
        if err or raw is None:
            return _missing_source_message(path, err)
        text = raw.decode("utf-8", errors="replace")
        return (
            f"{os.path.basename(path)} — plain text (.{profile_format})\n"
            f"  {len(text):,} characters, {len(text.splitlines()):,} lines\n"
            f"  No pages, no images, nothing to materialise. extract_text returns "
            f"its content directly."
        )

    pdf_bytes, err = _read_bytes(path)
    if err:
        return err

    # Lazy-import PDF libraries only when needed
    try:
        import io
        import pypdf
        import pdfplumber
    except ImportError as e:
        return f"PDF libraries unavailable: {e}"

    try:
        # Parse with pypdf for structure, metadata, outline, encryption
        try:
            pdf_reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        except Exception as e:
            return f"Failed to read PDF: {e}"

        page_count = len(pdf_reader.pages)

        # Check encryption state
        encryption_state = "not encrypted"
        try:
            if pdf_reader.is_encrypted:
                # Try to decrypt with empty password
                if pdf_reader.decrypt(""):
                    encryption_state = "encrypted (openable with empty password)"
                else:
                    encryption_state = "encrypted (locked)"
        except Exception:
            encryption_state = "encrypted (unparseable)"

        # Extract metadata
        metadata = {}
        try:
            meta = pdf_reader.metadata
            if meta:
                if meta.get("/Author"):
                    metadata["author"] = meta["/Author"]
                if meta.get("/Producer"):
                    metadata["producer"] = meta["/Producer"]
                if meta.get("/CreationDate"):
                    metadata["created"] = meta["/CreationDate"]
                if meta.get("/ModDate"):
                    metadata["modified"] = meta["/ModDate"]
        except Exception:
            pass

        # Extract outline (table of contents)
        outline_count = 0
        try:
            outline = pdf_reader.outline
            outline_count = len(outline) if outline else 0
        except Exception:
            outline_count = 0

        # Now use pdfplumber for text and image analysis (per-page)

        page_summaries = []
        total_chars = 0
        total_images = 0

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
            for page_num, page in enumerate(doc.pages, 1):
                # Count text characters
                text = page.extract_text() or ""
                char_count = len(text)
                total_chars += char_count

                # Determine text layer verdict
                has_text = char_count >= _TEXT_LAYER_THRESHOLD
                text_verdict = (
                    "text layer present" if has_text else "minimal/no text layer"
                )

                # Count images
                image_count = len(page.images) if page.images else 0
                total_images += image_count

                page_summaries.append(
                    {
                        "page": page_num,
                        "chars": char_count,
                        "text_verdict": text_verdict,
                        "images": image_count,
                    }
                )

        # Estimate token cost: 1 token ~= 4 characters
        estimated_tokens = total_chars // 4

        # Build the report
        lines = [f"Document: {os.path.basename(path)}\n"]
        lines.append(f"Pages: {page_count}")
        lines.append(f"Encryption: {encryption_state}")
        lines.append(f"Outline: {outline_count} entries\n")

        # Metadata
        if metadata:
            lines.append("Metadata:")
            for key, value in sorted(metadata.items()):
                lines.append(f"  {key}: {value}")
            lines.append("")

        # Per-page summary with character counts and threshold
        lines.append("Per-page text analysis:\n")
        for summary in page_summaries:
            lines.append(
                f"  Page {summary['page']:2d}: {summary['chars']:4d} chars [threshold: {_TEXT_LAYER_THRESHOLD}] {summary['text_verdict']}, "
                f"{summary['images']} image(s)"
            )

        # Totals
        lines.append("")
        lines.append("Totals:")
        lines.append(f"  Total characters: {total_chars:,}")
        lines.append(f"  Total images: {total_images:,}")
        lines.append(f"  Estimated tokens to read: ~{estimated_tokens:,}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error analyzing PDF: {e}"


# ---------------------------------------------------------------------------
# T3 — reading order, fragment merge, crop geometry (FR-004, FR-004a, FR-005,
# FR-005a, FR-005b). Position and pixels come from pdfplumber + the pypdfium2
# render ONLY — pypdf disagrees with pdfplumber on image count (67 vs 66 on
# the real document), so indices from the two libraries are not portable.
#
# No dedupe (research.md R-01): perfect dedupe saves ~2% of image tokens and
# its only exact form (hashing the embedded stream) collapses the same
# screenshot bearing different annotations — a correctness bug, not a saving.
# ---------------------------------------------------------------------------


def _merge_image_fragments(images: list[dict]) -> list[dict]:
    """Merge adjacent image bboxes into one picture (FR-005a).

    Two boxes are the same picture if their vertical gap is <= _FRAGMENT_MERGE_GAP
    points AND their x-ranges overlap. Measured on the real document: page 2's
    image 4 ends at bottom=671.0 and image 5 begins at top=671.0 — one screenshot
    stored as two XObjects, split at an arbitrary seam.

    Each input dict needs x0/x1/top/bottom (pdfplumber image bbox keys). Returns
    merged dicts with the same keys plus "parts" (source-object count).
    """
    if not images:
        return []

    ordered = sorted(images, key=lambda i: (i["top"], i["x0"]))
    merged = [dict(ordered[0], parts=1)]
    for im in ordered[1:]:
        prev = merged[-1]
        gap = im["top"] - prev["bottom"]
        x_overlap = min(prev["x1"], im["x1"]) - max(prev["x0"], im["x0"])
        if gap <= _FRAGMENT_MERGE_GAP and x_overlap > 0:
            prev["bottom"] = max(prev["bottom"], im["bottom"])
            prev["x0"] = min(prev["x0"], im["x0"])
            prev["x1"] = max(prev["x1"], im["x1"])
            prev["parts"] += 1
        else:
            merged.append(dict(im, parts=1))
    return merged


def _reading_order_items(page: Any) -> list[tuple[float, str, Any]]:
    """Interleave a pdfplumber page's text lines and merged images by vertical position.

    Text lines come from page.extract_words(), grouped by rounded "top" (FR-004).
    Image bboxes come from page.images, run through _merge_image_fragments first.
    Returns (top, kind, payload) sorted by top — kind is "text" (payload: joined
    line string) or "image" (payload: merged image dict). On a tie, text sorts
    before image (stable sort, text appended to the list first).
    """
    lines: dict[float, list[str]] = {}
    for w in page.extract_words(x_tolerance=_WORD_X_TOLERANCE):
        lines.setdefault(round(w["top"], 0), []).append(w["text"])

    raw_images = [
        {"x0": im["x0"], "x1": im["x1"], "top": im["top"], "bottom": im["bottom"]}
        for im in (page.images or [])
    ]
    merged_images = _merge_image_fragments(raw_images)

    items: list[tuple[float, str, Any]] = []
    for top, words in lines.items():
        items.append((top, "text", " ".join(words)))
    for im in merged_images:
        items.append((im["top"], "image", im))
    items.sort(key=lambda x: x[0])
    return items


def _crop_box_for_image(
    image: dict,
    page_width: float,
    page_height: float,
    render_width: int,
    render_height: int,
) -> tuple[int, int, int, int]:
    """Scale a pdfplumber image bbox (PDF points) into render pixel coordinates.

    The box locates a crop of the RENDERED page (FR-005) — never the embedded
    image, which is missing the vector annotation overlays (arrows, circles)
    drawn on top of it. Clamped to the render's pixel bounds.
    """
    sx = render_width / page_width
    sy = render_height / page_height
    x0 = max(0, int(round(image["x0"] * sx)))
    top = max(0, int(round(image["top"] * sy)))
    x1 = min(render_width, int(round(image["x1"] * sx)))
    bottom = min(render_height, int(round(image["bottom"] * sy)))
    return (x0, top, x1, bottom)


def _materialize_page(page: Any, render: Any, out_dir: Path) -> dict:
    """Build one page's text.md and image-N.png crops, in reading order (T3/T4 boundary).

    `out_dir` is whatever directory the caller wants the files written into — T4
    owns temp-dir + os.rename atomicity, so this function never decides where a
    page directory finally lives.

    Each image placeholder carries the audit comment `<!-- WxH, N source object(s) -->`
    (FR-004a). No dedupe is performed (research.md R-01) — every merged picture on
    the page is cropped and saved.

    Returns a receipt dict: text_md, images (filenames written, in order), chars,
    raw_images (count before merge), merged_images (count after merge).
    """
    items = _reading_order_items(page)

    md_parts: list[str] = []
    image_names: list[str] = []
    chars = 0
    idx = 0
    raw_count = 0

    for _, kind, payload in items:
        if kind == "text":
            md_parts.append(payload)
            chars += len(payload)
            continue

        raw_count += payload["parts"]
        idx += 1
        name = f"image-{idx}.png"
        box = _crop_box_for_image(
            payload, page.width, page.height, render.width, render.height
        )
        crop = render.crop(box)
        crop.save(out_dir / name)

        parts = payload["parts"]
        noun = "source object" if parts == 1 else "source objects"
        md_parts.append(
            f"\n@[[{name}]]  <!-- {crop.width}x{crop.height}, {parts} {noun} -->\n"
        )
        image_names.append(name)

    text_md = "\n".join(md_parts)
    (out_dir / "text.md").write_text(text_md)

    return {
        "text_md": text_md,
        "images": image_names,
        "chars": chars,
        "raw_images": raw_count,
        "merged_images": idx,
    }


# ---------------------------------------------------------------------------
# T4 — materialise: temp-dir -> rename, resume, manifest (FR-003, FR-006,
# FR-007, FR-007a, FR-007b, FR-008).
# ---------------------------------------------------------------------------

_RENDER_SCALE = 2.0

# Bytes-per-image-token divisor, matching the reference implementation's
# estimate (crop.width * crop.height // 750) — used only for the receipt's
# "estimated tokens to read whole", never to gate anything.
_PIXELS_PER_IMAGE_TOKEN = 750

# ── Sharding (SHARDING.md) ───────────────────────────────────────────────────
# A shard is "what one agent can read in one pass". Computed HERE, mechanically,
# from tokens this extraction actually measured — not estimated by an agent from
# a format average, and not left to a model to divide.
#
# ``_SHARD_RESERVE_TOKENS`` is the correction the pricing tables do not carry: a
# run measured an agent that read NOTHING still spending 12,856 tokens on its
# system prompt, tool schemas, task block and tool-call history. Sharding to the
# raw safe budget overruns by exactly that much.
_SHARD_SAFE_BUDGET = 120_000  # Haiku 4.5: 60% of a 200K window
_SHARD_RESERVE_TOKENS = 15_000  # measured agent overhead, rounded up
_SHARD_PAGE_CAP = 100  # API cap on pages/images per request <1M context

#: Safe budget (60% of context) per reading model. Haiku is the default because
#: it is the cheapest per page and the only model on both Bedrock paths; the rest
#: are here so switching model is a parameter, not an edit. Figures from
#: MODEL_PRICING.md — Sonnet 5 / Opus 5 are Messages-endpoint only.
_SHARD_SAFE_BUDGETS: dict[str, int] = {
    "haiku-4.5": 120_000,
    "sonnet-4.5": 120_000,
    "opus-4.5": 120_000,
    "sonnet-4.6": 600_000,
    "opus-4.6": 600_000,
    "sonnet-5": 600_000,
    "opus-5": 600_000,
    "fable-5.1": 600_000,
}
_SHARD_DEFAULT_MODEL = "haiku-4.5"


def _build_shards(
    slug: str,
    source_format: str,
    pages: list[int],
    page_tokens: dict[int, int],
    *,
    model: str = _SHARD_DEFAULT_MODEL,
    page_cap: int = _SHARD_PAGE_CAP,
    reserve: int = _SHARD_RESERVE_TOKENS,
) -> list[dict]:
    """Pack a document's pages into shards one agent can each read in one pass.

    Greedy first-fit in page order: pages stay contiguous, so a shard is always a
    readable page RANGE rather than a scattered set. A single page larger than the
    whole budget still gets its own shard — refusing to emit it would silently drop
    content; the oversized shard is flagged instead.

    ``model`` selects the safe budget (default Haiku 4.5); an unknown name falls
    back to the default rather than guessing a window, since guessing high would
    build shards no agent can actually read. ``page_cap`` is the per-request page
    ceiling and ``reserve`` the agent's own overhead — both parameters so a
    different model or a measured-larger overhead needs no code change.

    Returns [] for a document with no complete pages (nothing to shard).
    """
    safe_budget = _SHARD_SAFE_BUDGETS.get(
        model, _SHARD_SAFE_BUDGETS[_SHARD_DEFAULT_MODEL]
    )
    usable = safe_budget - reserve
    shards: list[dict] = []
    current: list[int] = []
    current_tokens = 0

    def flush() -> None:
        if not current:
            return
        shard_id = f"{slug}-s{len(shards) + 1:02d}"
        shards.append(
            {
                "id": shard_id,
                "slug": slug,
                "format": source_format,
                "pages": list(current),
                "page_range": f"{current[0]}-{current[-1]}"
                if len(current) > 1
                else str(current[0]),
                "est_tokens": current_tokens,
                "source": f"{_doc_rel(source_format, slug)}/pages/",
                "out": f"shards/{shard_id}/",
                # True when ONE page alone exceeds the budget — the shard is emitted
                # anyway (dropping the page would lose content silently) but an agent
                # reading it should expect to be squeezed.
                "over_budget": current_tokens > usable,
            }
        )

    for n in pages:
        cost = page_tokens.get(n, 0)
        would_exceed = current and (current_tokens + cost > usable)
        at_page_cap = len(current) >= page_cap
        if would_exceed or at_page_cap:
            flush()
            current, current_tokens = [], 0
        current.append(n)
        current_tokens += cost
    flush()
    return shards


# ---------------------------------------------------------------------------
# T17 — parallel materialisation (FR-013, FR-013a, FR-013b, FR-014).
#
# ProcessPoolExecutor ONLY, never a thread: pdfplumber gains 0.99x on 4 threads
# (pure Python, GIL-bound) and pypdfium2 rendering across threads CRASHES THE
# PROCESS (measured: exit 133, SIGTRAP, no traceback) because PDFium is not
# thread-safe. In the backend that kills the worker and every concurrent run
# on it.
#
# Each worker opens the document ONCE for its whole contiguous page range —
# per-page tasks are dominated by re-opening the file and do not scale.
# ---------------------------------------------------------------------------

_PARALLEL_WORKER_COUNT = 4
_PARALLEL_PAGE_THRESHOLD = (
    30  # process spawn is a fixed cost a small doc never earns back
)


def _split_into_ranges(page_numbers: list[int], worker_count: int) -> list[list[int]]:
    """Split a sorted page-number list into up to `worker_count` contiguous chunks."""
    if not page_numbers:
        return []
    chunk_size = -(-len(page_numbers) // worker_count)  # ceil division
    return [
        page_numbers[i : i + chunk_size]
        for i in range(0, len(page_numbers), chunk_size)
    ]


def _materialize_page_range(
    pdf_bytes: bytes, page_numbers: list[int], pages_dir: str
) -> dict[int, dict]:
    """Materialise one contiguous page range in its own process.

    Opens both `pdfplumber` and `pypdfium2` documents ONCE for the whole range
    (not once per page). Runs in a fresh interpreter (`ProcessPoolExecutor`),
    so module state (`_SANDBOX`) is never touched here — `pages_dir` is a plain
    absolute path string, safe to pickle across the process boundary.

    Returns {page_number: receipt} for every page in `page_numbers`.
    """
    import io
    import uuid

    import pdfplumber
    import pypdfium2 as pdfium

    pages_dir_path = Path(pages_dir)
    pl_doc = pdfplumber.open(io.BytesIO(pdf_bytes))
    fium_doc = pdfium.PdfDocument(pdf_bytes)
    receipts: dict[int, dict] = {}
    try:
        for page_num in page_numbers:
            page = pl_doc.pages[page_num - 1]
            render = fium_doc[page_num - 1].render(scale=_RENDER_SCALE).to_pil()
            tmp_dir = pages_dir_path / f".tmp-{page_num:02d}-{uuid.uuid4().hex}"
            tmp_dir.mkdir(parents=True)
            receipt = _materialize_page(page, render, tmp_dir)
            final_dir = pages_dir_path / f"{page_num:02d}"
            os.rename(tmp_dir, final_dir)  # atomic: this dir exists iff complete
            receipts[page_num] = receipt
    finally:
        fium_doc.close()
        pl_doc.close()
    return receipts


def _materialize_parallel_sync(
    pdf_bytes: bytes, page_numbers: list[int], pages_dir: Path
) -> dict[int, dict]:
    """Blocking: fan `page_numbers` out across `_PARALLEL_WORKER_COUNT` processes.

    FR-014 — off the event loop. These tools are plain sync callables (the same
    contract as `pptx_tools.py` and `playwright.py`), and the runtime already
    executes a sync tool in a worker thread, so waiting on `future.result()`
    here never touches the run's loop. An `asyncio.run()` wrapper around this
    would not add that guarantee and would REMOVE it: `asyncio.run` raises
    inside a thread that already owns a loop, so the parallel branch would
    return an error and materialise nothing. The sequential branch below
    blocks the same way, deliberately.
    """
    ranges = _split_into_ranges(page_numbers, _PARALLEL_WORKER_COUNT)
    receipts: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=_PARALLEL_WORKER_COUNT) as executor:
        futures = [
            executor.submit(_materialize_page_range, pdf_bytes, rng, str(pages_dir))
            for rng in ranges
        ]
        for future in futures:
            receipts.update(future.result())
    return receipts


def _converted_pdf(relpath: str, doc_dir: Path) -> tuple[bytes | None, str | None, str]:
    """Return (pdf_bytes, converted_by, "") for an Office source, or (None, None, error).

    The conversion is cached at .extract/{format}/{slug}/source.pdf and obeys the same
    folder-is-the-state rule as a page directory (FR-028): LibreOffice writes into
    a temp directory and the result is moved into place with one atomic rename, so
    source.pdf exists only if the conversion finished. A second extract reuses it
    and never pays soffice's startup again.
    """
    import shutil
    import uuid

    cached = doc_dir / "source.pdf"
    if cached.is_file():
        try:
            return cached.read_bytes(), "libreoffice", ""
        except OSError as exc:
            return None, None, f"failed to read the cached conversion: {exc}"

    src, err = _resolve_path(relpath)
    if err or src is None:
        return None, None, err or "could not resolve the source document"

    try:
        doc_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, None, f"cannot create {doc_dir.name}: {exc}"

    staging = doc_dir / f".convert-{uuid.uuid4().hex}"
    try:
        produced, err = soffice.convert_to_pdf(src, staging)
        if err or produced is None:
            return None, None, err or "conversion produced no output"
        os.replace(produced, cached)
    except OSError as exc:
        return None, None, f"conversion failed: {exc}"
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    try:
        return cached.read_bytes(), "libreoffice", ""
    except OSError as exc:
        return None, None, f"failed to read the conversion: {exc}"


def _iter_document_dirs(extract_root: Path) -> list[tuple[str, str, Path]]:
    """Every materialised document under .extract/, as (format, slug, dir), sorted.

    The tree is two levels deep now — .extract/{format}/{slug}/ — so a caller that
    walks one level finds format directories and no manifests. Sorted so a run
    holding several documents composes the same way twice.
    """
    found: list[tuple[str, str, Path]] = []
    try:
        for fmt_dir in sorted(p for p in extract_root.iterdir() if p.is_dir()):
            if fmt_dir.name.startswith("."):
                continue
            for doc_dir in sorted(p for p in fmt_dir.iterdir() if p.is_dir()):
                if doc_dir.name.startswith("."):
                    continue
                if (doc_dir / "manifest.json").is_file():
                    found.append((fmt_dir.name, doc_dir.name, doc_dir))
    except OSError:
        return []
    return found


def _load_manifest(manifest_path: Path) -> dict | None:
    """Read manifest.json, or None if it is absent or unparsable."""
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return None


def _parse_pages_selector(pages: str, page_count: int) -> tuple[list[int], str]:
    """Parse a "1,3,5-8" page selector into a sorted list of page numbers.

    Empty string means every page. Returns (page_numbers, "") on success, or
    ([], error_string) on a malformed or out-of-range selector.
    """
    if not pages or not pages.strip():
        return list(range(1, page_count + 1)), ""

    result: set[int] = set()
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, _, hi_s = part.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                return [], f"invalid page range: {part!r}"
            if lo < 1 or hi > page_count or lo > hi:
                return [], f"page range out of bounds (1-{page_count}): {part!r}"
            result.update(range(lo, hi + 1))
        else:
            try:
                n = int(part)
            except ValueError:
                return [], f"invalid page number: {part!r}"
            if n < 1 or n > page_count:
                return [], f"page {n} out of bounds (1-{page_count})"
            result.add(n)
    return sorted(result), ""


# A bare placeholder ref — no "/" — is relative to its own page directory.
# Rewritten to {slug}/-relative form when folded into document.md.
_DOC_REF_RE = re.compile(r"@\[\[([^\]/]+)\]\]")


def _write_if_changed(path: Path, content: str) -> None:
    """Write content only if it differs from what is already on disk.

    Keeps mtimes stable on a no-op resume run (contract: "rewrites nothing").
    """
    if path.is_file():
        try:
            if path.read_text() == content:
                return
        except OSError:
            pass
    path.write_text(content)


def _inline_text(relpath: str, filename: str, source_format: str) -> str:
    """Return a plain-text upload's content directly (FR-044).

    Nothing is written to .extract/. A .txt, .md, .csv or .json is already the
    thing an agent wanted, so paginating it into a folder of itself would add a
    directory, a manifest and a second read for no gain.
    """
    raw, err = _read_bytes(relpath)
    if err or raw is None:
        return _missing_source_message(relpath, err)

    text = raw.decode("utf-8", errors="replace")
    header = f"{filename} (.{source_format}, {len(text):,} characters) — full text follows.\n"
    if len(text) > _TEXT_INLINE_MAX_CHARS:
        keep = text[:_TEXT_INLINE_MAX_CHARS]
        return (
            f"{filename} (.{source_format}, {len(text):,} characters) — TRUNCATED to the "
            f"first {_TEXT_INLINE_MAX_CHARS:,}. Use read_file on {relpath} to page through "
            f"the rest.\n\n{keep}"
        )
    return header + "\n" + text


async def extract_text(path: str, pages: str = "", file_type: str = "") -> str:
    """Materialise a document into .extract/{format}/{slug}/pages/NN/.

    Accepts .pdf, .docx, .xlsx, .pptx, .html and .htm through ONE entry point; an
    Office file is converted to PDF by LibreOffice first, an HTML file is opened in
    a headless browser (spec 021). Use `pages` ("1-5", "3") to limit work on large
    paged documents — HTML materialises every screen in one pass; there is no
    partial-page selection for it. Returns a receipt naming the materialised pages.
    """
    filename = os.path.basename(path)
    fmt = file_type.strip().lower().lstrip(".") if file_type else _format_of(filename)
    if fmt in _HTML_FORMATS:
        # HTML never touches pdfium — kept OUTSIDE _locked_call/_PDFIUM_LOCK so a
        # slow browser extraction never blocks a concurrent PDF materialisation
        # (spec 021 R-07: the HTML route is a new branch, the PDF/Office routes
        # stay byte-identical).
        return await asyncio.to_thread(_extract_html_sync, path, file_type)
    # The materialiser is CPU/subprocess-heavy and SYNCHRONOUS. The runtime
    # invokes tool callables on the event loop, so running it inline starves
    # the whole server (observed live: four concurrent extract_text calls froze
    # every API route for 10+ minutes). to_thread keeps the loop breathing —
    # and _PDFIUM_LOCK keeps those threads OUT of pdfium concurrently: pdfium
    # is not thread-safe, and five parallel readers rendering at once crashed
    # the server with SIGBUS inside FPDF_RenderPageBitmap (observed live).
    return await asyncio.to_thread(
        _locked_call, _extract_text_sync, path, pages, file_type
    )


#: Serialises every in-process pdfium/pdfplumber materialisation. pdfium is NOT
#: thread-safe — concurrent FPDF_* calls from tool worker threads corrupt memory
#: (SIGBUS, observed). The >30-page parallel branch is unaffected: its workers
#: are separate PROCESSES, each with its own pdfium.
_PDFIUM_LOCK = threading.Lock()


def _locked_call(fn, *args):
    with _PDFIUM_LOCK:
        return fn(*args)


def _extract_text_sync(path: str, pages: str = "", file_type: str = "") -> str:
    """Materialise a document into .extract/{format}/{slug}/pages/NN/ (FR-003, FR-006, FR-007,
    FR-007a, FR-007b, FR-008, FR-026, FR-039).

    Accepts .pdf, .docx, .xlsx and .pptx through ONE entry point. An Office file is
    converted to PDF by LibreOffice once, cached as source.pdf beside the pages, and
    then materialised by exactly the same code as a native PDF — the caller never
    learns which happened.

    THE FORMAT IS THE PARAMETER THE WHOLE ROUTE TURNS ON. It picks the destination
    (.extract/{file_type}/{slug}/) and decides whether a conversion runs at all;
    everything after that is the one PDF materialiser, unchanged. It is normally
    read off the filename; `file_type` overrides it for an upload whose extension
    is missing or wrong. The override is trusted: it names the destination
    directory and picks the route, so declaring a PDF as "docx" really does send
    it through LibreOffice and file it under .extract/docx/. LibreOffice is
    permissive enough to convert it anyway, so the result is a misfiled document
    rather than a failure — the parameter is an escape hatch for a mis-named
    upload, not a content check.

    Each page is built in a temp directory under pages/ and moved into place
    with a single os.rename — a page directory exists only if it is complete,
    by construction; there is no marker file and nothing to interpret. Resume
    is set(range(1, page_count+1)) - set(existing page dirs): the folder IS
    the state, so a missing or deleted page is simply redone (bias to redo —
    FR-007b). A source_sha256 mismatch under the same filename means a
    re-upload replaced the document, so the whole folder is discarded before
    resuming (FR-008).

    `pages` selects which pages to materialise ("" = all, "1,3,5-8" = a
    subset); already-complete pages in the selection are skipped.

    `file_type` is "pdf", "docx", "xlsx" or "pptx"; empty means "read it off the
    filename", which is right for every normal upload.

    Returns a receipt — pages processed, pages skipped, image counts before
    and after merge, character count, estimated tokens to read the whole
    document — and never page content.
    """
    if _SANDBOX is None:
        return "document tools not bound to a run sandbox (internal error)"

    filename = os.path.basename(path)
    supported = ", ".join("." + f for f in sorted(_SUPPORTED_FORMATS))

    # Belt-and-suspenders: html/htm is routed to _extract_html_sync by the async
    # extract_text() entry point and must never reach this function — the PDF/
    # Office branch below would otherwise hand it to LibreOffice as if it were a
    # convertible Office format (it is in _SUPPORTED_FORMATS for file_info's
    # inventory listing, but it is not in _PAGED_FORMATS or _TEXT_FORMATS).
    early_format = (file_type.strip().lower().lstrip(".") if file_type else _format_of(filename))
    if early_format in _HTML_FORMATS:
        return (
            f"{filename} is HTML — call extract_text (the async entry point), not "
            f"_extract_text_sync directly (internal error: html reached the PDF/Office pipeline)."
        )

    if file_type:
        source_format = file_type.strip().lower().lstrip(".")
        if source_format not in _SUPPORTED_FORMATS:
            return (
                f"cannot extract {filename}: file_type={file_type!r} is not a supported "
                f"format. Supported: {supported}."
            )
    else:
        source_format = _format_of(filename)
        if source_format not in _SUPPORTED_FORMATS:
            return (
                f"cannot extract {filename}: .{source_format or '(no extension)'} is not a "
                f"supported format. Supported: {supported}. If the extension is missing or "
                f"wrong, pass file_type explicitly."
            )

    if source_format in _TEXT_FORMATS:
        return _inline_text(path, filename, source_format)

    source_bytes, err = _read_bytes(path)
    if err:
        return _missing_source_message(path, err)

    slug = _slug_from_filename(filename)
    # FR-029: hash the UPLOADED bytes, never a PDF derived from them. What changes
    # on a re-upload under the same name is the .docx, and that is what has to
    # invalidate the folder.
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    doc_dir, err = _resolve_path(_doc_rel(source_format, slug))
    if err:
        return err
    pages_dir = doc_dir / "pages"
    manifest_path = doc_dir / "manifest.json"
    document_path = doc_dir / "document.md"

    import io
    import shutil
    import uuid
    from datetime import datetime, timezone

    manifest = _load_manifest(manifest_path)
    if manifest is not None and manifest.get("source_sha256") != source_sha256:
        # Same filename, different bytes: the folder is stale (FR-008). This must
        # happen BEFORE the conversion cache is consulted, or a stale source.pdf
        # would be reused for the new document.
        shutil.rmtree(doc_dir, ignore_errors=True)
        manifest = None

    # FR-026/FR-028: one conversion, cached; a PDF skips this entirely.
    if source_format == "pdf":
        pdf_bytes, converted_by = source_bytes, None
    else:
        pdf_bytes, converted_by, err = _converted_pdf(path, doc_dir)
        if err or pdf_bytes is None:
            return err or f"could not convert {filename}"

    try:
        import pdfplumber
        import pypdfium2 as pdfium
        from PIL import Image
    except ImportError as e:
        return f"PDF libraries unavailable: {e}"

    try:
        pl_doc = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as e:
        return f"failed to read PDF: {e}"

    try:
        page_count = len(pl_doc.pages)
    except Exception as e:
        pl_doc.close()
        return f"failed to read PDF: {e}"

    requested, sel_err = _parse_pages_selector(pages, page_count)
    if sel_err:
        pl_doc.close()
        return sel_err

    doc_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Clear out any stray temp dirs left by a crashed prior run — they were
    # never renamed into place, so they hold no completed page and are safe
    # to discard.
    for entry in os.listdir(pages_dir):
        if entry.startswith(".tmp-"):
            shutil.rmtree(pages_dir / entry, ignore_errors=True)

    existing = {
        int(entry)
        for entry in os.listdir(pages_dir)
        if entry.isdigit() and (pages_dir / entry).is_dir()
    }
    to_build = sorted(n for n in requested if n not in existing)
    skipped = sorted(n for n in requested if n in existing)

    manifest_pages: dict[str, dict] = dict((manifest or {}).get("pages", {}))

    run_raw = 0
    run_merged = 0

    if len(to_build) > _PARALLEL_PAGE_THRESHOLD:
        # Above the threshold: each worker opens the document once for its own
        # contiguous page range (ProcessPoolExecutor — never a thread; see the
        # T17 block above _materialize_page_range).
        try:
            page_receipts = _materialize_parallel_sync(pdf_bytes, to_build, pages_dir)
        except Exception as e:
            pl_doc.close()
            return f"failed to materialise pages in parallel: {e}"

        for page_num in to_build:
            receipt = page_receipts.get(page_num)
            if receipt is None:
                continue  # a worker's page did not complete; swept + redone next run
            manifest_pages[str(page_num)] = {
                "images": receipt["images"],
                "chars": receipt["chars"],
                "raw_images": receipt["raw_images"],
                "merged_images": receipt["merged_images"],
            }
            run_raw += receipt["raw_images"]
            run_merged += receipt["merged_images"]
    else:
        fium_doc = None
        if to_build:
            try:
                fium_doc = pdfium.PdfDocument(pdf_bytes)
            except Exception as e:
                pl_doc.close()
                return f"failed to render PDF: {e}"

        for page_num in to_build:
            page = pl_doc.pages[page_num - 1]
            render = fium_doc[page_num - 1].render(scale=_RENDER_SCALE).to_pil()
            tmp_dir = pages_dir / f".tmp-{page_num:02d}-{uuid.uuid4().hex}"
            tmp_dir.mkdir(parents=True)
            try:
                receipt = _materialize_page(page, render, tmp_dir)
            except Exception as e:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                pl_doc.close()
                return f"failed to materialise page {page_num}: {e}"

            final_dir = pages_dir / f"{page_num:02d}"
            os.rename(tmp_dir, final_dir)  # atomic: this dir exists iff complete
            manifest_pages[str(page_num)] = {
                "images": receipt["images"],
                "chars": receipt["chars"],
                "raw_images": receipt["raw_images"],
                "merged_images": receipt["merged_images"],
            }
            run_raw += receipt["raw_images"]
            run_merged += receipt["merged_images"]

    pl_doc.close()

    # The folder is the state: recompute the manifest/document.md from
    # whatever page directories actually exist on disk, not from what this
    # run intended to build.
    complete_pages = sorted(
        int(entry)
        for entry in os.listdir(pages_dir)
        if entry.isdigit() and (pages_dir / entry).is_dir()
    )

    total_chars = sum(
        manifest_pages.get(str(n), {}).get("chars", 0) for n in complete_pages
    )
    total_raw = sum(
        manifest_pages.get(str(n), {}).get("raw_images", 0) for n in complete_pages
    )
    total_merged = sum(
        manifest_pages.get(str(n), {}).get("merged_images", 0) for n in complete_pages
    )

    # Per-page token cost, MEASURED (chars/4 + this page's image tokens) rather
    # than looked up from a format average. Feeds both the shard packer below and
    # the whole-document estimate reported at the end.
    page_tokens: dict[int, int] = {}
    for n in complete_pages:
        page_dir = pages_dir / f"{n:02d}"
        tok = manifest_pages.get(str(n), {}).get("chars", 0) // 4
        for name in manifest_pages.get(str(n), {}).get("images", []):
            img_path = doc_dir / name if "/" in name else page_dir / name
            try:
                with Image.open(img_path) as im:
                    tok += (im.width * im.height) // _PIXELS_PER_IMAGE_TOKEN
            except OSError:
                continue
        page_tokens[n] = tok

    created_at = (manifest or {}).get("created_at") or datetime.now(
        timezone.utc
    ).isoformat()
    new_manifest = {
        "source": filename,
        "source_sha256": source_sha256,
        "source_format": source_format,
        "converted_by": converted_by,
        "slug": slug,
        "page_count": page_count,
        "scale": _RENDER_SCALE,
        "created_at": created_at,
        "pages": {
            str(n): manifest_pages[str(n)]
            for n in complete_pages
            if str(n) in manifest_pages
        },
        # SHARDING.md: how this document divides across reading agents. Computed
        # here so the planner reads a number instead of deriving one — the same
        # arithmetic done by a model is the same arithmetic done wrong sometimes.
        "shards": _build_shards(slug, source_format, list(complete_pages), page_tokens),
        "shard_basis": {
            "safe_budget": _SHARD_SAFE_BUDGETS[_SHARD_DEFAULT_MODEL],
            "agent_reserve": _SHARD_RESERVE_TOKENS,
            "usable": _SHARD_SAFE_BUDGETS[_SHARD_DEFAULT_MODEL] - _SHARD_RESERVE_TOKENS,
            "model": _SHARD_DEFAULT_MODEL,
            "page_cap": _SHARD_PAGE_CAP,
        },
        "totals": {
            "raw_images": total_raw,
            "after_merge": total_merged,
            # No dedupe is performed (research.md R-01), so every merged
            # picture is "unique" by construction.
            "unique": total_merged,
        },
    }
    _write_if_changed(manifest_path, json.dumps(new_manifest, indent=2))

    doc_parts = []
    for n in complete_pages:
        text_path = pages_dir / f"{n:02d}" / "text.md"
        text = text_path.read_text() if text_path.is_file() else ""
        # Contract (contracts/on-disk-format.md): a ref inside document.md is
        # relative to {slug}/, not to a page directory — there is no single page
        # directory to be relative to here. Left page-relative, every page's
        # "image-1.png" would name a different file and none would resolve.
        text = _DOC_REF_RE.sub(rf"@[[pages/{n:02d}/\1]]", text)
        doc_parts.append(
            f"\n\n<!-- ================= PAGE {n} ================= -->\n\n" + text
        )
    _write_if_changed(document_path, "".join(doc_parts))

    # Estimated cost of reading the whole document (text + every image) — the sum
    # of the per-page costs already measured above, so the two can never disagree.
    estimated_tokens = sum(page_tokens.values())

    lines = [
        f"Materialised {filename} -> {_doc_rel(source_format, slug)}/ "
        f"({page_count} page(s) total)\n"
    ]
    if to_build:
        lines.append(
            f"Processed: {len(to_build)} page(s) — {', '.join(map(str, to_build))}"
        )
        lines.append(f"  images this run: {run_raw} raw -> {run_merged} after merge")
    else:
        lines.append("Processed: 0 pages (nothing new to materialise)")
    lines.append(f"Skipped (already present): {len(skipped)} page(s)")
    lines.append("")
    lines.append(
        f"Document totals: {len(complete_pages)}/{page_count} page(s) complete, "
        f"{total_chars:,} characters, {total_raw} raw images -> {total_merged} after merge"
    )
    lines.append(
        f"Estimated tokens to read document.md + all images: ~{estimated_tokens:,}"
    )
    _shards = new_manifest["shards"]
    if _shards:
        lines.append(
            f"Shards: {len(_shards)} — "
            + ", ".join(
                f"{sh['id']} pages {sh['page_range']} (~{sh['est_tokens']:,} tok)"
                for sh in _shards
            )
        )
    lines.append("")
    lines.append(f"Read it with: read_file {_doc_rel(source_format, slug)}/document.md")
    if page_count > _LARGE_DOCUMENT_PAGES:
        # Advisory only — the document WAS materialised in full.
        lines.append(
            f"This document is {page_count} pages (~{estimated_tokens:,} tokens to read whole). "
            f'extract_text(path, pages="1-20") materialises a slice instead, and file_find '
            f"locates a term without reading anything."
        )
    if source_format == "xlsx":
        # A sheet has no pages until something paginates it, and LibreOffice does
        # that from print settings nobody set on purpose.
        lines.append(
            f"These {page_count} page(s) are LibreOffice's pagination of a spreadsheet, "
            f"driven by its print settings — not a structure the workbook itself has."
        )

    return "\n".join(lines) + _pagination_note(converted_by)


# ---------------------------------------------------------------------------
# HTML/HTM route (spec 021 T12) — screens, not pages. Kept OUTSIDE _PDFIUM_LOCK
# (see extract_text() above): this never touches pdfium, and a browser open is
# slow enough that serialising it behind the PDF lock would stall every
# concurrent PDF materialisation for no reason.
# ---------------------------------------------------------------------------


def _extract_html_sync(path: str, file_type: str = "") -> str:
    """Materialise an .html/.htm upload into .extract/html/{slug}/ (spec 021, FR-010..FR-013).

    Both extensions land under the SAME format directory ("html") — a `.htm`
    re-upload of the same document must not fork into a second folder. One page
    per screen (fields, actions, tables, hidden states, a screenshot), then the
    page's own scripts, built by `html_extract.materialise_html` — see that
    module for the browser/static route split. Never raises: any failure in
    either route comes back as readable text, matching every other route here.
    """
    if _SANDBOX is None:
        return "document tools not bound to a run sandbox (internal error)"

    filename = os.path.basename(path)
    supported = ", ".join("." + f for f in sorted(_SUPPORTED_FORMATS))

    if file_type:
        raw_format = file_type.strip().lower().lstrip(".")
    else:
        raw_format = _format_of(filename)
    if raw_format not in _HTML_FORMATS:
        return (
            f"cannot extract {filename} as html: .{raw_format or '(no extension)'} is not "
            f".html or .htm. Supported: {supported}."
        )

    source_bytes, err = _read_bytes(path)
    if err:
        return _missing_source_message(path, err)

    slug = _slug_from_filename(filename)
    doc_dir, err = _resolve_path(_doc_rel("html", slug))
    if err:
        return err
    source_path, err = _resolve_path(path)
    if err:
        return err

    # Lazy import, matching this module's PDF-library convention: the factory
    # imports file_extract_tools at composition time and must not pull
    # Playwright into every run that never touches an HTML upload.
    from app.agents.tools import html_extract

    try:
        result = html_extract.materialise_html(source_path, source_bytes, doc_dir, filename, slug)
    except Exception as e:  # noqa: BLE001 — never-raise discipline (module docstring)
        return f"failed to materialise {filename}: {e}"

    manifest = result["manifest"]
    page_count = manifest.get("page_count", 0)
    screens = manifest.get("screens", [])
    rendered_by = result["rendered_by"]

    lines = [
        f"Materialised {filename} -> {_doc_rel('html', slug)}/ "
        f"({page_count} page(s) total)\n"
    ]
    if result["rebuilt"]:
        lines.append(f"Processed: {page_count} page(s) (rebuilt)")
    else:
        lines.append("Processed: 0 pages (nothing new to materialise — source unchanged)")
    lines.append("")
    lines.append(f"Screens: {len(screens)} (rendered by {rendered_by})")
    if result.get("static_reason"):
        lines.append(f"  static fallback: {result['static_reason']}")
    totals = manifest.get("totals", {})
    lines.append(f"Document totals: {page_count} page(s), {totals.get('chars', 0):,} characters")
    shards = manifest.get("shards", [])
    if shards:
        lines.append(
            f"Shards: {len(shards)} — "
            + ", ".join(
                f"{sh['id']} pages {sh['page_range']} (~{sh['est_tokens']:,} tok)"
                for sh in shards
            )
        )
    lines.append("")
    lines.append(f"Read it with: read_file {_doc_rel('html', slug)}/document.md")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# T5 — file_find: search materialised text.md files (FR-010)
# ---------------------------------------------------------------------------

_FIND_DEFAULT_LIMIT = 50


def file_find(query: str, path: str = "", limit: int = _FIND_DEFAULT_LIMIT) -> str:
    """Search the materialised text.md files, not the PDFs.

    Default to every document; narrow when path is given. Return each hit as
    document, page number and surrounding context — output shaped to feed
    straight into a page argument. Cap the number of hits and SAY SO when
    capped, suggesting the query be narrowed; a search for a common word over
    hundreds of pages must not return thousands of hits.

    If the document has not been materialised yet, say that rather than
    returning "not found".

    Args:
        query: The search term (case-insensitive).
        path: Optional document path (.uploads/filename.pdf); empty = all documents.
        limit: Maximum hits to return (default 50).

    Returns:
        Readable text describing hits, or an error/info message.
    """
    if _SANDBOX is None:
        return "document tools not bound to a run sandbox (internal error)"

    if not query or not query.strip():
        return "search query is empty"

    query_lower = query.lower()
    pdf_dir, err = _resolve_path(_EXTRACT_PREFIX.rstrip("/"))
    if err:
        return err

    # Resolve the document slug if path was given
    target_slug = None
    target_format = None
    if path and path.strip():
        # Get the filename from the path directly—no PDF read needed (FR-010).
        # path_for validates the traversal, but we don't read the file.
        candidate, err = _resolve_path(path)
        if err:
            return err
        filename = candidate.name
        target_slug = _slug_from_filename(filename)
        target_format = _format_of(filename)

    hits: list[dict] = []

    # Every document under .extract/{format}/{slug}/ (FR-030's two-level tree).
    if not pdf_dir.is_dir():
        if target_slug:
            return f"document not materialised: {target_slug}"
        return "No materialised documents found."

    documents = _iter_document_dirs(pdf_dir)

    if target_slug is not None:
        documents = [
            d for d in documents if d[1] == target_slug and d[0] == target_format
        ]
        if not documents:
            return f"document not materialised: {target_format}/{target_slug}"
    elif not documents:
        return "No materialised documents found."

    # Search each document's pages
    for source_format, slug, doc_path in documents:
        pages_path = doc_path / "pages"

        if not pages_path.is_dir():
            continue

        try:
            page_dirs = sorted(
                [
                    d
                    for d in os.listdir(pages_path)
                    if (pages_path / d).is_dir() and d.isdigit()
                ],
                key=int,
            )
        except (OSError, IOError):
            continue

        for page_dir_name in page_dirs:
            page_path = pages_path / page_dir_name
            text_path = page_path / "text.md"

            if not text_path.is_file():
                continue

            try:
                text = text_path.read_text()
            except (OSError, IOError):
                continue

            # Search for the query (case-insensitive)
            text_lower = text.lower()
            if query_lower not in text_lower:
                continue

            # Find all occurrences and extract context
            start_idx = 0
            while True:
                idx = text_lower.find(query_lower, start_idx)
                if idx == -1:
                    break

                # Extract context: ~150 chars before and after
                context_start = max(0, idx - 150)
                context_end = min(len(text), idx + len(query) + 150)
                context = text[context_start:context_end].strip()

                # Replace newlines with spaces in context for readability
                context = " ".join(context.split())

                hits.append(
                    {
                        "document": f"{source_format}/{slug}",
                        "page": int(page_dir_name),
                        "context": context,
                        "query": query,
                    }
                )

                if len(hits) >= limit:
                    break

                start_idx = idx + 1

            if len(hits) >= limit:
                break

        if len(hits) >= limit:
            break

    # Format and return results
    if not hits:
        if target_slug:
            return f"No matches for '{query}' in document '{target_slug}'."
        return f"No matches for '{query}' in any materialised document."

    lines = [f"Found {len(hits)} match(es) for '{query}':\n"]
    for i, hit in enumerate(hits, 1):
        lines.append(
            f"{i}. Document: {hit['document']}, Page: {hit['page']}\n"
            f"   Context: ...{hit['context']}...\n"
        )

    if len(hits) >= limit:
        lines.append(
            f"\nResults capped at {limit} hits. To narrow the search, try a more specific query."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# T6 — file_page_image: render one page entire (FR-011, FR-012b)
# ---------------------------------------------------------------------------

# Per-image byte ceiling (from run_engine.py, matching Anthropic API limits)
_IMAGE_MAX_BYTES = int(3.75 * 1024 * 1024)

# Pixels-per-token conversion (same as in the reference implementation)
_PIXELS_PER_TOKEN = 750


async def file_page_image(path: str, page: int) -> str:
    """Render one page entire — for a full-page diagram or layout-heavy content.

    Args:
        path: Document path (.uploads/filename.pdf).
        page: Page number (1-indexed).

    Returns:
        "path.png (WxH, ~N tokens)" on success, or an error message. Never raises.
    """
    # Same event-loop-starvation + pdfium-serialisation guards as extract_text.
    return await asyncio.to_thread(_locked_call, _file_page_image_sync, path, page)


def _file_page_image_sync(path: str, page: int) -> str:
    """Render one page entire — for a full-page diagram or layout-heavy content.

    This is the escape hatch for when cropped pictures cannot answer: a layout
    that only reads as a whole, a full-page diagram, a page whose text extraction
    is untrustworthy. The rendered output is downscaled as needed to stay inside
    the per-image ceilings (FR-012b).

    Args:
        path: Document path (.uploads/filename.pdf).
        page: Page number (1-indexed).

    Returns:
        A readable string describing the result: either a path and size
        (formatted as "path.png (WxH, ~N tokens)") on success, or an error
        message on failure. Never raises.
    """
    if _SANDBOX is None:
        return "document tools not bound to a run sandbox (internal error)"

    if not isinstance(page, int) or page < 1:
        return f"page must be a positive integer (got {page!r})"

    pdf_bytes, err = _read_bytes(path)
    if err:
        return _missing_source_message(path, err)

    filename = os.path.basename(path)
    slug = _slug_from_filename(filename)
    source_format = _format_of(filename)

    # Resolve the page directory where this page's full render will be stored.
    doc_dir, err = _resolve_path(_doc_rel(source_format, slug))
    if err:
        return err
    page_dir = doc_dir / "pages" / f"{page:02d}"

    import io

    try:
        import pdfplumber
        import pypdfium2 as pdfium
    except ImportError as e:
        return f"PDF libraries unavailable: {e}"

    try:
        pl_doc = pdfplumber.open(io.BytesIO(pdf_bytes))
        page_count = len(pl_doc.pages)
    except Exception as e:
        return f"failed to read PDF: {e}"

    # Validate page number (1-indexed)
    if page < 1 or page > page_count:
        pl_doc.close()
        return f"page {page} out of range (1-{page_count})"

    # Open with pypdfium2 for rendering
    try:
        fium_doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as e:
        pl_doc.close()
        return f"failed to render PDF: {e}"

    result = None
    try:
        # Render the page at the standard scale; downscale if needed.
        render_scale = _RENDER_SCALE
        max_attempts = 5  # Prevent infinite loop

        for attempt in range(max_attempts):
            try:
                render = fium_doc[page - 1].render(scale=render_scale).to_pil()
            except Exception as e:
                result = f"failed to render page {page}: {e}"
                break

            # Convert to PNG and check file size
            png_buffer = io.BytesIO()
            render.save(png_buffer, format="PNG")
            png_bytes = png_buffer.getvalue()
            png_size = len(png_bytes)

            # If within byte limit, save and return
            if png_size <= _IMAGE_MAX_BYTES:
                # Ensure the page directory exists (materialization may not have run)
                page_dir.mkdir(parents=True, exist_ok=True)

                # Write the full-page image with a distinct name (not image-N.png)
                try:
                    out_path = page_dir / "page-full.png"
                    out_path.write_bytes(png_bytes)

                    # Calculate token estimate using the standard token cost
                    pixel_count = render.width * render.height
                    token_estimate = pixel_count // _PIXELS_PER_TOKEN

                    # Return summary of what was written: path relative to .pdf/slug/,
                    # dimensions, and token estimate
                    rel_path = str(out_path.relative_to(doc_dir))
                    result = (
                        f"{_doc_rel(source_format, slug)}/{rel_path} "
                        f"({render.width}x{render.height}, {png_size // 1024} KB, "
                        f"~{token_estimate} tokens)"
                    )
                except (OSError, IOError) as e:
                    result = f"failed to write page {page} image: {e}"
                break

            # Over-ceiling: reduce scale and retry
            render_scale *= 0.85  # Reduce by ~15% each time

        # If we got here without a result, we couldn't downscale enough
        if result is None:
            result = f"page {page} exceeds size limits even after downscaling (try file_find to locate relevant content)"

    finally:
        fium_doc.close()
        pl_doc.close()

    return result
