"""tests/agents/test_validating_backend.py — ValidatingFilesystemBackend JSON validation.

Covers write/edit validation of .json files: valid JSON succeeds; invalid JSON is rejected
with precise error messages (path, error detail, line/column); edits that would corrupt JSON
are rolled back to the prior state; non-.json files bypass validation entirely.

Offline / pure (no DB / network).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.validating_backend import ValidatingFilesystemBackend


@pytest.fixture
def backend(tmp_path):
    """Create a ValidatingFilesystemBackend rooted in a temp directory."""
    return ValidatingFilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


def test_write_valid_json_succeeds(backend, tmp_path):
    """Write valid JSON creates the file and returns success."""
    content = json.dumps({"tasks": [{"id": "t1", "title": "Task 1"}]})
    result = backend.write("/data.json", content)

    assert result.error is None
    assert result.path == "/data.json"
    assert (tmp_path / "data.json").exists()
    assert json.loads((tmp_path / "data.json").read_text()) == {
        "tasks": [{"id": "t1", "title": "Task 1"}]
    }


def test_write_invalid_json_fails_and_file_not_created(backend, tmp_path):
    """Write invalid JSON returns error and does not create the file."""
    invalid_content = (
        '{"tasks": [{"id": "t1", "title": "Task 1"}'  # Missing closing brackets
    )

    result = backend.write("/build/tasks.json", invalid_content)

    assert result.error is not None
    assert "would not be valid JSON after this write" in result.error
    assert "line 1" in result.error
    assert "/build/tasks.json" in result.error
    assert result.path is None
    assert not (tmp_path / "build" / "tasks.json").exists()


def test_edit_that_keeps_json_valid_succeeds(backend, tmp_path):
    """Edit that maintains JSON validity succeeds."""
    # Create initial valid JSON
    initial = json.dumps({"count": 0, "items": []})
    (tmp_path / "config.json").write_text(initial)

    # Edit to change a value (still valid JSON)
    result = backend.edit("/config.json", '"count": 0', '"count": 42')

    assert result.error is None
    assert result.path == "/config.json"
    assert result.occurrences == 1
    final = json.loads((tmp_path / "config.json").read_text())
    assert final["count"] == 42


def test_edit_that_corrupts_json_is_rejected_and_rolled_back(backend, tmp_path):
    """Edit that would corrupt JSON is rejected, file is restored to prior content."""
    # Create initial valid JSON
    initial = json.dumps({"status": "ok", "data": {"value": 1}})
    (tmp_path / "state.json").write_text(initial)

    # Try to edit in a way that breaks JSON (remove a closing brace from the outer object)
    result = backend.edit("/state.json", "}}", "}")

    assert result.error is not None
    assert "would not be valid JSON after this edit" in result.error
    assert "line" in result.error
    assert result.path is None
    # File content must be byte-identical to before
    assert (tmp_path / "state.json").read_text() == initial
    assert json.loads((tmp_path / "state.json").read_text()) == json.loads(initial)


def test_markdown_file_with_invalid_json_content_writes_fine(backend, tmp_path):
    """Non-.json files bypass validation, even with invalid JSON content."""
    invalid_json_content = '{"broken": [1, 2, 3}'  # Invalid JSON

    result = backend.write("/docs/example.md", invalid_json_content)

    assert result.error is None
    assert result.path == "/docs/example.md"
    assert (tmp_path / "docs" / "example.md").exists()
    assert (tmp_path / "docs" / "example.md").read_text() == invalid_json_content


def test_uppercase_json_extension_is_validated(backend, tmp_path):
    """Uppercase .JSON extension is also validated."""
    invalid_content = '{"incomplete": '

    result = backend.write("/CONFIG.JSON", invalid_content)

    assert result.error is not None
    assert "would not be valid JSON after this write" in result.error
    assert result.path is None
    assert not (tmp_path / "CONFIG.JSON").exists()


def test_mixed_case_json_extension_is_validated(backend, tmp_path):
    """Mixed-case .Json extension is also validated."""
    invalid_content = "[1, 2, 3"

    result = backend.write("/data.Json", invalid_content)

    assert result.error is not None
    assert "would not be valid JSON after this write" in result.error
    assert result.path is None
    assert not (tmp_path / "data.Json").exists()


def test_error_message_contains_json_exception_details(backend, tmp_path):
    """Error message includes JSONDecodeError details for debugging."""
    # Unterminated string
    invalid = '{"key": "unterminated'

    result = backend.write("/invalid.json", invalid)

    assert result.error is not None
    # Should contain line and column info from JSONDecodeError
    assert "line" in result.error
    assert "column" in result.error
    assert "/invalid.json" in result.error


def test_write_refuses_overwrite_like_parent(backend, tmp_path):
    """Write still enforces the parent class rule: cannot overwrite existing files."""
    initial = json.dumps({"version": 1})
    (tmp_path / "existing.json").write_text(initial)

    # Attempt to write to existing file (valid JSON, but file exists)
    new_content = json.dumps({"version": 2})
    result = backend.write("/existing.json", new_content)

    assert result.error is not None
    assert "already exists" in result.error
    # File unchanged
    assert (tmp_path / "existing.json").read_text() == initial


def test_edit_nonexistent_file_fails(backend, tmp_path):
    """Edit of nonexistent file returns error (parent behavior)."""
    result = backend.edit("/missing.json", "old", "new")

    assert result.error is not None
    assert "not found" in result.error
    assert result.path is None


def test_nested_path_creation_for_write(backend, tmp_path):
    """Write creates parent directories as needed."""
    content = json.dumps([{"id": "nested"}])
    result = backend.write("/a/b/c/tasks.json", content)

    assert result.error is None
    assert result.path == "/a/b/c/tasks.json"
    assert (tmp_path / "a" / "b" / "c" / "tasks.json").exists()


def test_edit_without_replace_all_requires_single_occurrence(backend, tmp_path):
    """Edit with replace_all=False fails if old_string appears more than once."""
    initial = json.dumps({"key": "value", "key2": "value"})
    (tmp_path / "data.json").write_text(initial)

    # Try to replace "value" (appears twice) without replace_all=True
    result = backend.edit("/data.json", '"value"', '"replaced"', replace_all=False)

    # Parent class enforces single-occurrence rule; this should fail
    assert result.error is not None
    assert (tmp_path / "data.json").read_text() == initial


def test_edit_with_replace_all_succeeds(backend, tmp_path):
    """Edit with replace_all=True replaces all occurrences."""
    initial = json.dumps({"a": {"b": {"c": 0}}})
    (tmp_path / "nested.json").write_text(initial)

    # Increment depth (JSON still valid)
    result = backend.edit("/nested.json", "0", "1", replace_all=True)

    assert result.error is None
    assert result.path == "/nested.json"
    assert result.occurrences == 1  # Only one "0" in the JSON
    final = json.loads((tmp_path / "nested.json").read_text())
    assert final["a"]["b"]["c"] == 1


def test_edit_rolls_back_when_post_edit_reread_fails(backend, tmp_path, monkeypatch):
    """An I/O fault between the edit and its validation re-read must not leave the new
    content on disk while reporting failure — the file is restored and the error says so."""
    import app.agents.validating_backend as vb

    (tmp_path / "data.json").write_text('{"a": 1}')
    real_read = vb._read_text
    calls = {"n": 0}

    def flaky_read(path):
        calls["n"] += 1
        if calls["n"] == 2:  # 1st = pre-edit snapshot, 2nd = post-edit validation
            raise OSError("simulated read failure")
        return real_read(path)

    monkeypatch.setattr(vb, "_read_text", flaky_read)
    result = backend.edit("/data.json", '"a": 1', '"a": 2')

    assert result.error is not None
    assert "simulated read failure" in result.error
    assert "Nothing was written" in result.error
    assert (tmp_path / "data.json").read_text() == '{"a": 1}'


def test_edit_error_warns_when_rollback_itself_fails(backend, tmp_path, monkeypatch):
    """If the rollback cannot land, the caller is told the edit stuck instead of 'untouched'."""
    import app.agents.validating_backend as vb

    (tmp_path / "data.json").write_text('{"a": 1}')
    monkeypatch.setattr(vb, "_restore", lambda path, content: False)
    result = backend.edit("/data.json", "}", "}}")

    assert result.error is not None
    assert "would not be valid JSON after this edit" in result.error
    assert "could NOT be rolled back" in result.error


def test_trailing_whitespace_in_json_path_is_still_validated(backend):
    """'tasks.json ' must not dodge the check."""
    result = backend.write("/tasks.json ", '{"broken": ')
    assert result.error is not None
    assert "would not be valid JSON after this write" in result.error


def test_crlf_content_rolls_back_byte_identical(backend, tmp_path):
    """Rollback must preserve CRLF line endings exactly."""
    original = '{\r\n  "a": 1\r\n}'
    (tmp_path / "data.json").write_bytes(original.encode())
    result = backend.edit("/data.json", "}", "}}")
    assert result.error is not None
    assert (tmp_path / "data.json").read_bytes() == original.encode()
