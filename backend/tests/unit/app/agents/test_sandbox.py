"""Unit tests for the upload-name helpers in ``app/agents/sandbox.py``.

``stored_upload_namer`` reproduces the name ``app.api.run_files`` stores an
upload under (``_safe_segment`` + ``_dedupe_segment``), so the kernel's
attachment listing can point at files that exist. Pure string handling — no I/O.
"""

from __future__ import annotations

import pytest

from app.agents.sandbox import _dedupe_segment, stored_upload_namer


@pytest.mark.parametrize(
    ("safe", "used", "expected"),
    [
        ("invoice_1.txt", set(), "invoice_1.txt"),
        ("invoice_1.txt", {"invoice_1.txt"}, "invoice_1-2.txt"),
        ("invoice_1.txt", {"invoice_1.txt", "invoice_1-2.txt"}, "invoice_1-3.txt"),
        ("README", {"README"}, "README-2"),
    ],
)
def test_dedupe_segment_returns_next_free_name_when_used(safe, used, expected):
    assert _dedupe_segment(safe, used) == expected


def test_stored_upload_namer_sanitizes_basename_when_name_has_spaces_or_path():
    namer = stored_upload_namer()

    assert namer("Business_Process_Requirements 1.pdf") == (
        "Business_Process_Requirements_1.pdf"
    )
    assert namer("../nested/Epics and Stories.pdf") == "Epics_and_Stories.pdf"


def test_stored_upload_namer_deduplicates_when_names_sanitize_alike():
    namer = stored_upload_namer()

    assert [namer("invoice#1.txt"), namer("invoice@1.txt"), namer("invoice 1.txt")] == [
        "invoice_1.txt",
        "invoice_1-2.txt",
        "invoice_1-3.txt",
    ]


def test_stored_upload_namer_starts_fresh_when_called_again():
    first, second = stored_upload_namer(), stored_upload_namer()

    assert first("a.pdf") == "a.pdf"
    assert second("a.pdf") == "a.pdf"
