"""tests/unit/test_deliverable_prose_leak.py — QA-PS-023 prose-before-HTML leak.

Preview tab shows the last agent's raw reasoning text prepended to the HTML
deliverable. Root cause: no deliverable resolver slices to the first
``<!DOCTYPE``/``<html`` occurrence when the model emits narrative prose ahead
of its HTML with no ``<artifact>`` wrapper. ``unwrap_artifact`` only strips a
literal wrapper; unwrapped prose+HTML passes straight through.

Covers all three affected resolvers (ISS-700 root, ISS-736 and ISS-737
siblings) — each xfails until the shared fix lands in ``_artifact.py``.
"""

from __future__ import annotations

import types

import pytest

from agents.capabilities.deliverables.ppt import PptResolver
from agents.capabilities.deliverables.single_file import SingleFileResolver
from agents.capabilities.deliverables.streamed_text import StreamedTextResolver

PROSE_THEN_HTML = (
    "The composer file contains no artifact. Let me check what files exist "
    "in the .agents/ directory: Let me check the brief analyst output: Now "
    "let me read the composer file completely to find the artifact: The "
    "composer output shows that no HTML deck was generated...\n"
    "<!DOCTYPE html>\n<html><head><title>Deck</title></head>"
    '<body><section class="slide">slide 1</section></body></html>'
)


@pytest.mark.issue("ISS-700")
def test_streamed_text_resolver_strips_prose_before_html():
    """ISS-700 — streamed_text must not leak reasoning prose ahead of the deck."""
    ctx = types.SimpleNamespace(last_streamed=PROSE_THEN_HTML)
    out = StreamedTextResolver().resolve(ctx)
    assert out.strip().startswith("<!DOCTYPE"), out[:120]


@pytest.mark.issue("ISS-736")
def test_ppt_resolver_strips_prose_before_html():
    """ISS-736 — base ppt strategy has the same unstripped-preamble leak."""
    ctx = types.SimpleNamespace(last_streamed=PROSE_THEN_HTML)
    out = PptResolver().resolve(ctx)
    assert out.strip().startswith("<!DOCTYPE"), out[:120]


@pytest.mark.issue("ISS-737")
def test_single_file_forward_build_fallback_strips_prose_before_html():
    """ISS-737 — single_file's no-file-written fallback returns raw last_streamed
    with no unwrap_artifact call at all, worse than the streamed_text/ppt cases."""

    class _EmptySandbox:
        def read(self, _filename):
            return None

    ctx = types.SimpleNamespace(
        runner=types.SimpleNamespace(sandbox=_EmptySandbox()),
        deliverable=types.SimpleNamespace(
            name="prototype.html", publish_from_glob=None
        ),
        last_streamed=PROSE_THEN_HTML,
        revision_original_html="",
    )
    out = SingleFileResolver().resolve(ctx)
    assert out.strip().startswith("<!DOCTYPE"), out[:120]
