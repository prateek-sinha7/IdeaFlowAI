"""The active Builder system prompt version and what it makes mandatory.

The prompt is a versioned file under ``prompts/``: a new version is a new file
and a change to :data:`PROMPT_VERSION_LABEL` (Req 19.1). The file is read once
at import. The mandatory skill files are parsed from the same text, so the
adherence record always tracks the list the active prompt names.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Final

__all__ = [
    "MANDATORY_FILES",
    "PROMPT_FILE",
    "PROMPT_VERSION",
    "PROMPT_VERSION_LABEL",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_SHA256",
    "mandatory_files",
]

PROMPT_VERSION_LABEL: Final = "v2"
PROMPT_FILE: Final = (
    Path(__file__).resolve().parent
    / "prompts"
    / f"system_prompt.{PROMPT_VERSION_LABEL}.md"
)
_PROMPT_HASH_CHARS: Final = 12
_SKILL_ID: Final = "velocity-workflow-creator"
_MANDATORY_INTRO: Final = re.compile(r"\bfiles are mandatory\b", re.IGNORECASE)
_MANDATORY_ITEM: Final = re.compile(rf"^- `/skills/{re.escape(_SKILL_ID)}/([^`]+)`\s*$")


def _load_system_prompt(path: Path) -> str:
    """Read the prompt file as UTF-8 with LF line endings."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def mandatory_files(prompt: str) -> tuple[str, ...]:
    """Return the skill files the prompt makes mandatory, relative to the skill folder.

    The list is the run of ``- `/skills/<skill>/<path>``` bullets that follows
    the sentence containing "files are mandatory", in prompt order.

    Raises:
        ValueError: The prompt names no mandatory file.
    """
    lines = prompt.splitlines()
    for index, line in enumerate(lines):
        if not _MANDATORY_INTRO.search(line):
            continue
        found: list[str] = []
        for item in lines[index + 1 :]:
            match = _MANDATORY_ITEM.match(item.strip())
            if match:
                found.append(match.group(1))
            elif found or item.strip():
                break
        if found:
            return tuple(found)
    raise ValueError("the system prompt names no mandatory skill file")


SYSTEM_PROMPT: Final = _load_system_prompt(PROMPT_FILE)
"""The system prompt text, read once at import (Req 19.1)."""

SYSTEM_PROMPT_SHA256: Final = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
"""SHA-256 of :data:`SYSTEM_PROMPT` (UTF-8, LF line endings), as lowercase hex."""

PROMPT_VERSION: Final = (
    f"{PROMPT_VERSION_LABEL}:{SYSTEM_PROMPT_SHA256[:_PROMPT_HASH_CHARS]}"
)
"""Stored on each assistant message: ``<label>:<first 12 hex of the hash>``."""

MANDATORY_FILES: Final[tuple[str, ...]] = mandatory_files(SYSTEM_PROMPT)
"""The mandatory skill files of the active prompt version, in prompt order."""
