"""tests/unit/test_qa_sg_014_output_format.py — QA-SG-014 output-format mismatch.

The custom-workflow composer's "Output format" control (CanvasView.tsx) lets a
user pick HTML for a `streamed_text` or `single_file` deliverable. Neither
resolver converts content to match the declared name's format — both silently
return the last agent's raw (markdown/plain) text. See ISS-770 (streamed_text,
root, confirmed live: run e49b91e6-f2fe-479c-a941-75da2b53c05d completed with
deliverable_filename="output.html" but deliverable_mimetype="text/markdown"
and raw markdown bytes) and ISS-776 (single_file sibling, inferred): selecting
"output.html" must never produce raw, untransformed markdown labeled as HTML.
"""

from __future__ import annotations

import types

import pytest

from agents.capabilities.deliverables.single_file import SingleFileResolver
from agents.capabilities.deliverables.streamed_text import StreamedTextResolver

RAW_MARKDOWN = "## Task 1: Do the thing\n\nSome plain markdown body text.\n"


@pytest.mark.issue("ISS-770")
def test_streamed_text_resolver_converts_content_to_declared_html_format():
    """ISS-770 — selecting 'output.html' must produce actual HTML markup, not
    the last agent's raw markdown verbatim (the live-reproduced defect: filename
    said .html, deliverable_mimetype and bytes stayed markdown)."""
    ctx = types.SimpleNamespace(
        last_streamed=RAW_MARKDOWN,
        deliverable=types.SimpleNamespace(name="output.html"),
    )
    out = StreamedTextResolver().resolve(ctx)
    assert "<html" in out.lower() or out.strip().startswith("<!DOCTYPE"), (
        f"declared output.html but resolved raw markdown verbatim: {out[:120]!r}"
    )


@pytest.mark.issue("ISS-776")
def test_single_file_resolver_never_labels_raw_fallback_text_as_html():
    """ISS-776 — when single_file falls back to raw last_streamed text (no step
    wrote the declared filename), the resolved bytes must not be mislabeled
    text/html while actually being unconverted markdown/plain text."""

    class _EmptySandbox:
        def list_files(self):
            return [], False

        def read(self, _filename):
            return None

    ctx = types.SimpleNamespace(
        runner=types.SimpleNamespace(sandbox=_EmptySandbox()),
        deliverable=types.SimpleNamespace(name="output.html", publish_from_glob=None),
        last_streamed=RAW_MARKDOWN,
        revision_original_html="",
    )
    resolved = SingleFileResolver().resolve(ctx)
    mimetype = SingleFileResolver.default_mimetype("output.html")

    if mimetype == "text/html":
        assert "<html" in resolved.lower() or resolved.strip().startswith("<!DOCTYPE"), (
            f"reported {mimetype} but resolved bytes are raw markdown: {resolved[:120]!r}"
        )
