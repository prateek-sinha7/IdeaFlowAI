"""agents/capabilities/tools/documents.py — the ``file_extract`` tool_provider capability (spec 019).

Emits the four tool KEYS document extraction and retrieval need. Like every other
provider here it returns STRINGS, never tool objects, so this package stays
import-clean of ``app.*`` (import-linter: ``agents.capabilities`` ↛ ``app``) —
the concrete implementations live in ``app/agents/tools/file_extract_tools.py`` and the
factory, which IS the composition root, resolves key → tool.

The key is ``file_extract``, not ``pdf`` (FR-039a): the tool set materialises .docx,
.xlsx and .pptx as readily as .pdf, and ``_KNOWN`` is the compiler's INV-4
membership surface — a name that misdescribes what it grants is a defect in the
one place the system is supposed to be literally true.

``user_allowed=True``: reading a document the user uploaded to their own run is
not a privileged operation (CAP-03), unlike the pptx tools which write a binary
and shell out to a subprocess.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

TOOL_EXTRACT_TEXT = "extract_text"
TOOL_FILE_INFO = "file_info"
TOOL_FILE_FIND = "file_find"
TOOL_FILE_PAGE_IMAGE = "file_page_image"


@register(
    "tool",
    "file_extract",
    user_allowed=True,
    description="Extract text from an uploaded file: extract_text / file_info / file_find / file_page_image (spec 019). ONE entry point for every type — a plain-text file (.txt, .md, .csv, .json) comes back as text in the tool result; a .pdf, .docx, .xlsx or .pptx is materialised into .extract/{format}/{name}/ (Office files converted by LibreOffice first) and the receipt names document.md to read; a .html or .htm is opened in a headless browser and materialised screen by screen into .extract/html/{name}/, falling back to a static read when no browser can launch (spec 021); anything else is refused in readable text. Page images are crops of the RENDERED page, so annotation arrows drawn over a screenshot survive where embedded-image extraction loses them."
    "or PowerPoint document: extract_text / file_info / file_find / "
    "file_page_image (spec 019). One entry point for every format — an Office "
    "file is converted to PDF underneath and the caller never sees it. Materialises "
    "the document into layout-aware text with @[[image-N.png]] placeholders in "
    "reading order, where each image is a crop of the rendered page (preserving "
    "annotation arrows), not the embedded image.",
)
class FileExtractToolProvider:
    """The documents tool set (``name='documents'``).

    Returns ``exclude_builtin=False`` — the step still needs ``read_file`` to read
    the extracted text and search results, so the native filesystem tools stay
    alongside these four.
    """

    name = "file_extract"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return (
            [
                TOOL_EXTRACT_TEXT,
                TOOL_FILE_INFO,
                TOOL_FILE_FIND,
                TOOL_FILE_PAGE_IMAGE,
            ],
            False,
        )
