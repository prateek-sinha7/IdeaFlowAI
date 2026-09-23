"""FilesystemBackend subclass that validates JSON on write/edit.

A single stray bracket in a 90 KB tasks.json can kill an entire workflow run because
the filesystem tools have no validation at write time — the agent writes it, the
scheduler reads it silently corrupted on the next agent step, and the error surfaces
far downstream with no trace of the write that caused it.

This backend wraps write() and edit() to ensure that any .json file written to disk is
valid JSON before committing the write. On validation failure, the file is never touched
and the error message is precise enough for the agent to fix it immediately.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import EditResult, WriteResult

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _is_json_path(file_path: str) -> bool:
    # rstrip: a trailing space must not let "tasks.json " slip past the check.
    return file_path.rstrip().lower().endswith(".json")


def _read_text(path: Path) -> str:
    # newline="" keeps CRLF as CRLF so a rollback is byte-identical.
    fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _restore(path: Path, content: str) -> bool:
    """Put ``content`` back; True when it landed, False when the rollback itself failed."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_TRUNC | _O_NOFOLLOW)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    except (OSError, UnicodeEncodeError):
        return False
    return True


class ValidatingFilesystemBackend(FilesystemBackend):
    """FilesystemBackend that validates JSON files on write and edit."""

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Create a new file with content, validating JSON if the path ends with .json.

        Args:
            file_path: Path where the new file will be created.
            content: Text content to write to the file.

        Returns:
            `WriteResult` with path on success, or error message if validation fails
                or the file already exists or write fails.
        """
        if _is_json_path(file_path):
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                return WriteResult(
                    error=f"{file_path} would not be valid JSON after this write: {exc.msg} at line {exc.lineno} column {exc.colno}. Nothing was written — the file is exactly as it was. Fix your content string and make the SAME call again; do not read or rewrite the whole file."
                )

        return super().write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        """Edit a file by replacing string occurrences, validating JSON if applicable.

        For .json files, reads the current file content before the edit, performs the
        edit, validates the result, and restores the prior content if validation fails.
        The prior content is also restored when the post-edit re-read itself fails, so
        an error result always means the file is as it was — or says so when it is not.

        Args:
            file_path: Path to the file to edit.
            old_string: The text to search for and replace.
            new_string: The replacement text.
            replace_all: If `True`, replace all occurrences. If `False` (default),
                replace only if exactly one occurrence exists.

        Returns:
            `EditResult` with path and occurrence count on success, or error
                message if file not found, replacement fails, or JSON validation fails.
        """
        if not _is_json_path(file_path):
            return super().edit(file_path, old_string, new_string, replace_all)

        try:
            resolved_path = self._resolve_path(file_path)
        except (OSError, RuntimeError) as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")

        if not resolved_path.exists() or not resolved_path.is_file():
            return EditResult(error=f"Error: File '{file_path}' not found")

        try:
            prior_content = _read_text(resolved_path)
        except (OSError, UnicodeDecodeError) as e:
            return EditResult(error=f"Error reading file '{file_path}': {e}")

        result = super().edit(file_path, old_string, new_string, replace_all)
        if result.error is not None:
            return result

        try:
            json.loads(_read_text(resolved_path))
        except json.JSONDecodeError as exc:
            restored = _restore(resolved_path, prior_content)
            return EditResult(
                error=f"{file_path} would not be valid JSON after this edit: {exc.msg} at line {exc.lineno} column {exc.colno}. "
                + _rollback_note(restored)
            )
        except (OSError, UnicodeDecodeError) as e:
            restored = _restore(resolved_path, prior_content)
            return EditResult(
                error=f"Error re-reading file '{file_path}' after edit: {e}. " + _rollback_note(restored)
            )

        return result


def _rollback_note(restored: bool) -> str:
    if restored:
        return "Nothing was written — the file is exactly as it was; fix your new_string and make the SAME edit again, do not read or rewrite the whole file."
    return "WARNING: the edit was applied and could NOT be rolled back — read the file before editing it again."
