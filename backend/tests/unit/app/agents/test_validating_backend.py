"""Unit tests for ``app/agents/validating_backend.py`` — the Windows ``:`` escape.

The engine names an agent's thread ``<run_id>:<agent_id>``, and deepagents' summarization
writes the evicted history to ``/conversation_history/<thread_id>.md``. Windows rejects
``:`` in a file name (``[Errno 22]``), so the offload failed and the evicted messages
were lost. The backend escapes ``:`` on the disk side only, so the virtual path the model
sees and re-opens keeps working.

The escape is a module flag decided at import, so the tests force it on and run the same
on every host.
"""

from __future__ import annotations

import os

import pytest

import app.agents.validating_backend as vb
from app.agents.validating_backend import ValidatingFilesystemBackend

_THREAD_PATH = "/conversation_history/725474ee-04f2:custom-agent:e2e-tester.md"


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setattr(vb, "_COLON_UNSAFE_PLATFORM", True)
    return ValidatingFilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


def test_write_succeeds_when_virtual_path_contains_colons(backend, tmp_path):
    result = backend.write(_THREAD_PATH, "evicted history")

    assert result.error is None
    on_disk = list((tmp_path / "conversation_history").iterdir())
    assert len(on_disk) == 1
    assert ":" not in on_disk[0].name
    assert on_disk[0].read_text(encoding="utf-8") == "evicted history"


def test_read_returns_content_when_opened_by_the_original_colon_path(backend):
    backend.write(_THREAD_PATH, "evicted history")

    result = backend.read(_THREAD_PATH)

    assert result.error is None
    assert "evicted history" in result.file_data["content"]


def test_read_returns_content_when_opened_by_the_listed_disk_name(backend):
    """A model that re-opens the name ``ls`` printed must reach the same file."""
    backend.write(_THREAD_PATH, "evicted history")

    listed = backend.ls("/conversation_history").entries
    result = backend.read(listed[0]["path"])

    assert result.error is None
    assert "evicted history" in result.file_data["content"]


def test_append_style_second_write_targets_the_same_file(backend, tmp_path):
    """Both paths resolve identically, so a later offload for the thread finds the first."""
    first = backend.write(_THREAD_PATH, "one")
    second = backend.write(_THREAD_PATH, "two")

    assert first.error is None
    assert (
        second.error is not None
    )  # deepagents refuses to overwrite: same file as the first
    assert len(list((tmp_path / "conversation_history").iterdir())) == 1


def test_path_traversal_is_still_refused_when_path_contains_colons(backend):
    with pytest.raises(ValueError, match="traversal"):
        backend._resolve_path("/a:b/../../etc/passwd")


@pytest.mark.skipif(os.name == "nt", reason="a ':' file name cannot exist on Windows")
def test_resolve_path_keeps_colons_when_platform_allows_them(tmp_path, monkeypatch):
    """POSIX hosts keep their existing file names byte for byte."""
    monkeypatch.setattr(vb, "_COLON_UNSAFE_PLATFORM", False)
    backend = ValidatingFilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)

    assert (
        backend._resolve_path(_THREAD_PATH).name
        == "725474ee-04f2:custom-agent:e2e-tester.md"
    )
