"""Unit tests for ``agents/execution_engine/user_prompt.py`` attachment helpers.

Covers the dev-upload fail-fast change: the inlined ``=== Attached: … ===`` text
is stripped only when ``.uploads/manifest.json`` lists uploads, and the listing
names the sanitized stored names. Pure string handling — no I/O.
"""

from __future__ import annotations

import json
import logging
import os

import pytest

from agents.execution_engine.user_prompt import (
    UPLOADS_MANIFEST_PATH,
    USER_PROMPT_PATH,
    manifest_upload_names,
    parse_inline_attachments,
    prepare_brief_for_uploads,
    strip_attachments_if_uploaded,
    strip_inline_attachments,
)
from app.agents.sandbox import _safe_segment, stored_upload_namer

_BRIEF = (
    "create prototype from given docs\n\n"
    "=== Attached: Business_Process_Requirements 1.pdf ===\n"
    "SECRET-PAGE-TEXT-ONE\n"
    "=== End: Business_Process_Requirements 1.pdf ===\n\n"
    "=== Attached: Epics_and_user_Stories 1.pdf ===\n"
    "SECRET-PAGE-TEXT-TWO\n"
    "=== End: Epics_and_user_Stories 1.pdf ==="
)


def _manifest(*names: str) -> str:
    """A ``.uploads/manifest.json`` text in the shape run_files writes."""
    return json.dumps(
        [{"name": n, "mime": "application/pdf", "has_text": True} for n in names]
    )


_MANIFEST = _manifest(
    "Business_Process_Requirements_1.pdf", "Epics_and_user_Stories_1.pdf"
)


def _stored_name(name: str) -> str:
    """The same name mapping run_files applies when it writes an upload."""
    return _safe_segment(os.path.basename(name), fallback="upload")


def test_parse_inline_attachments_returns_names_when_blocks_present():
    assert parse_inline_attachments(_BRIEF) == [
        "Business_Process_Requirements 1.pdf",
        "Epics_and_user_Stories 1.pdf",
    ]


@pytest.mark.parametrize("message", [None, "", "just a brief, no attachments"])
def test_parse_inline_attachments_returns_empty_when_no_blocks(message):
    assert parse_inline_attachments(message) == []


def test_strip_inline_attachments_lists_sanitized_names_when_name_for_given():
    result = strip_inline_attachments(_BRIEF, name_for=_stored_name)

    assert "- .uploads/Business_Process_Requirements_1.pdf" in result
    assert "- .uploads/Epics_and_user_Stories_1.pdf" in result
    assert "Business_Process_Requirements 1.pdf" not in result
    assert "SECRET-PAGE-TEXT" not in result


def test_strip_inline_attachments_keeps_header_names_when_name_for_omitted():
    result = strip_inline_attachments(_BRIEF)

    assert "- .uploads/Business_Process_Requirements 1.pdf" in result


@pytest.mark.parametrize(
    "manifest_text",
    [None, "", "[]", "{}", "not json", '[{"x": 1}]', '[{"name": 3}]', '["a.pdf"]'],
)
def test_manifest_upload_names_empty_when_missing_empty_or_malformed(manifest_text):
    assert manifest_upload_names(manifest_text) == frozenset()


def test_manifest_upload_names_returns_stored_names_when_entries_have_names():
    assert manifest_upload_names(_MANIFEST) == {
        "Business_Process_Requirements_1.pdf",
        "Epics_and_user_Stories_1.pdf",
    }


def test_prepare_brief_for_uploads_strips_when_manifest_lists_uploads():
    message, stripped = prepare_brief_for_uploads(
        _BRIEF, _MANIFEST, name_for=_stored_name
    )

    assert stripped is True
    assert "SECRET-PAGE-TEXT" not in message
    assert "- .uploads/Business_Process_Requirements_1.pdf" in message
    assert "- .uploads/Epics_and_user_Stories_1.pdf" in message
    # Byte-identical to the unconditional strip when every document is uploaded.
    assert message == strip_inline_attachments(_BRIEF, name_for=_stored_name)


def test_prepare_brief_for_uploads_keeps_unlisted_document_inline_when_manifest_is_partial(
    caplog,
):
    caplog.set_level(logging.WARNING, logger="agents.execution_engine.user_prompt")

    message, stripped = prepare_brief_for_uploads(
        _BRIEF,
        _manifest("Business_Process_Requirements_1.pdf"),
        name_for=_stored_name,
    )

    assert stripped is True
    assert "SECRET-PAGE-TEXT-ONE" not in message
    assert "- .uploads/Business_Process_Requirements_1.pdf" in message
    # The document that never reached .uploads/ keeps its only copy: the inline block.
    assert (
        "=== Attached: Epics_and_user_Stories 1.pdf ===\n"
        "SECRET-PAGE-TEXT-TWO\n"
        "=== End: Epics_and_user_Stories 1.pdf ==="
    ) in message
    assert ".uploads/Epics_and_user_Stories_1.pdf" not in message
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        "inline attachments kept: not listed in .uploads/manifest.json "
        "(kept=1, stripped=1)"
    ]


def test_prepare_brief_for_uploads_strips_text_only_attachment_when_staged():
    brief = (
        "build from the notes\n\n"
        "=== Attached: requirements.md ===\n# SECRET-NOTES\n=== End: requirements.md ==="
    )

    message, stripped = prepare_brief_for_uploads(
        brief, _manifest("requirements.md"), name_for=stored_upload_namer()
    )

    assert stripped is True
    assert "SECRET-NOTES" not in message
    assert message.endswith("- .uploads/requirements.md")


def test_prepare_brief_for_uploads_lists_deduplicated_names_when_names_sanitize_alike():
    # run_files stores `invoice#1.txt` and `invoice@1.txt` as invoice_1.txt and
    # invoice_1-2.txt (_dedupe_segment); the listing must name both real files.
    brief = (
        "brief\n\n"
        "=== Attached: invoice#1.txt ===\nA\n=== End: invoice#1.txt ===\n\n"
        "=== Attached: invoice@1.txt ===\nB\n=== End: invoice@1.txt ==="
    )

    message, stripped = prepare_brief_for_uploads(
        brief,
        _manifest("invoice_1.txt", "invoice_1-2.txt"),
        name_for=stored_upload_namer(),
    )

    assert stripped is True
    assert message.endswith("- .uploads/invoice_1.txt\n- .uploads/invoice_1-2.txt")


def test_prepare_brief_for_uploads_strips_both_blocks_when_reattached_header_repeats(
    caplog,
):
    # "Edit brief & run again" seeds the failed run's block; re-attaching the file
    # appends a second block with the same header while one file is staged. The
    # namer maps the repeat to BPR_1-2.pdf, which the manifest does not list.
    caplog.set_level(logging.WARNING, logger="agents.execution_engine.user_prompt")
    brief = (
        "create prototype from given docs\n\n"
        "=== Attached: BPR 1.pdf ===\n"
        "[could not be extracted in-browser]\n"
        "=== End: BPR 1.pdf ===\n\n"
        "=== Attached: BPR 1.pdf ===\n"
        "SECRET-REATTACHED-TEXT\n"
        "=== End: BPR 1.pdf ==="
    )

    message, stripped = prepare_brief_for_uploads(
        brief, _manifest("BPR_1.pdf"), name_for=stored_upload_namer()
    )

    assert stripped is True
    assert "SECRET-REATTACHED-TEXT" not in message
    assert "could not be extracted" not in message
    assert "=== Attached:" not in message
    assert message.endswith("their text is not included here):\n- .uploads/BPR_1.pdf")
    assert message.count(".uploads/BPR_1.pdf") == 1
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_prepare_brief_for_uploads_keeps_alike_sanitized_distinct_name_when_only_one_listed():
    # Distinct headers that sanitize alike are different documents: with only the
    # first one staged, the second keeps its inline text (no repeat fallback).
    brief = (
        "brief\n\n"
        "=== Attached: invoice#1.txt ===\nA\n=== End: invoice#1.txt ===\n\n"
        "=== Attached: invoice@1.txt ===\nSECRET-B\n=== End: invoice@1.txt ==="
    )

    message, stripped = prepare_brief_for_uploads(
        brief, _manifest("invoice_1.txt"), name_for=stored_upload_namer()
    )

    assert stripped is True
    assert "=== Attached: invoice@1.txt ===\nSECRET-B\n" in message
    assert message.endswith("- .uploads/invoice_1.txt")


@pytest.mark.parametrize("manifest_text", [None, "", "[]"])
def test_prepare_brief_for_uploads_keeps_inline_text_and_warns_when_manifest_absent(
    manifest_text, caplog
):
    caplog.set_level(logging.WARNING, logger="agents.execution_engine.user_prompt")

    message, stripped = prepare_brief_for_uploads(
        _BRIEF, manifest_text, name_for=_stored_name
    )

    assert stripped is False
    assert message == _BRIEF
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    text = warnings[0].getMessage()
    assert "attachments=2" in text
    assert "SECRET-PAGE-TEXT" not in text
    assert "Business_Process_Requirements" not in text
    assert "Epics_and_user_Stories" not in text


def test_prepare_brief_for_uploads_noop_when_no_attachment_blocks(caplog):
    caplog.set_level(logging.WARNING, logger="agents.execution_engine.user_prompt")

    message, stripped = prepare_brief_for_uploads(
        "plain brief", None, name_for=_stored_name
    )

    assert (message, stripped) == ("plain brief", False)
    assert not caplog.records


class FakeSandbox:
    """In-memory stand-in for RunSandbox's read/write (relpath -> text)."""

    def __init__(self, files: dict[str, str] | None = None, *, read_error=None):
        self.files = dict(files or {})
        self.reads: list[str] = []
        self._read_error = read_error

    def read(self, relpath: str) -> str | None:
        self.reads.append(relpath)
        if self._read_error is not None:
            raise self._read_error
        return self.files.get(relpath)

    def write(self, relpath: str, content: str) -> None:
        self.files[relpath] = content


def test_strip_attachments_if_uploaded_strips_and_rewrites_prompt_when_manifest_lists_uploads():
    sandbox = FakeSandbox({UPLOADS_MANIFEST_PATH: _MANIFEST})

    result = strip_attachments_if_uploaded(sandbox, _BRIEF, name_for=_stored_name)

    assert "SECRET-PAGE-TEXT" not in result
    assert "- .uploads/Epics_and_user_Stories_1.pdf" in result
    assert sandbox.files[USER_PROMPT_PATH] == result.strip() + "\n"


@pytest.mark.parametrize(
    "sandbox",
    [
        FakeSandbox(),
        FakeSandbox({UPLOADS_MANIFEST_PATH: "[]"}),
        FakeSandbox(read_error=OSError("unreadable")),
    ],
    ids=["absent", "empty", "unreadable"],
)
def test_strip_attachments_if_uploaded_keeps_inline_text_when_manifest_missing(sandbox):
    result = strip_attachments_if_uploaded(sandbox, _BRIEF, name_for=_stored_name)

    assert result == _BRIEF
    assert USER_PROMPT_PATH not in sandbox.files


def test_strip_attachments_if_uploaded_skips_sandbox_when_no_attachment_blocks():
    sandbox = FakeSandbox({UPLOADS_MANIFEST_PATH: _MANIFEST})

    assert strip_attachments_if_uploaded(sandbox, "plain brief") == "plain brief"
    assert sandbox.reads == []
