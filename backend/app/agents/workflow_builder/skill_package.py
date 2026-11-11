"""Where the builder skill lives, and the facts the Builder reads from its files.

The skill is ``skills/velocity-workflow-creator/`` next to this file
(``backend/app/agents/workflow_builder/skills/``). That folder is the source of
truth: it is edited in place and committed, and the image ships it with the rest
of ``app/``. The path is fixed and worked out from this file's location, so local
dev, the tests and the image need no setting.

The skill hash and the line counts are computed from the files on disk each time
they are asked for. Nothing is stored beside the skill.

Hash definition. For every file under the skill folder, except ``__pycache__``
folders and bytecode, sorted by relative POSIX path::

    data = file bytes with CRLF replaced by LF
    blob = sha1(b"blob " + str(len(data)).encode() + b"\\0" + data)
    line = f"{path}\\0{blob}\\n"
    skill_hash = "sha256:" + sha256("".join(lines).encode())

For LF text the blob value equals ``git hash-object`` of the file, and the
result does not depend on the OS, the checkout's line endings or the order in
which files are enumerated.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final

from app.agents.workflow_builder.adherence import MANDATORY_FILES
from app.agents.workflow_builder.script_policy import (
    BUILDER_SKILL_ID,
    allowed_script_names,
)

__all__ = [
    "HASH_PREFIX",
    "SKILLS_ROOT",
    "SKILL_DIR",
    "SkillFacts",
    "blob_hash",
    "compute_skill_hash",
    "count_lines",
    "list_skill_files",
    "missing_files",
    "read_skill_facts",
    "required_files",
]

HASH_PREFIX: Final = "sha256:"

SKILLS_ROOT: Final[Path] = Path(__file__).resolve().parent / "skills"
"""The folder that holds the skill folder. ``/skills/`` serves it read-only."""

SKILL_DIR: Final[Path] = SKILLS_ROOT / BUILDER_SKILL_ID
"""The builder skill folder, the source of truth for the Builder's method."""

# Names never part of a skill: bytecode written by a stray run.
_EXCLUDED_DIR_NAMES: Final = frozenset({"__pycache__"})
_EXCLUDED_SUFFIXES: Final = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True)
class SkillFacts:
    """What the Builder records about the skill for one session or turn.

    Attributes:
        skill_hash: The hash of every skill file (module docstring).
        line_counts: ``{relative POSIX path: line count}`` for every skill file.
    """

    skill_hash: str
    line_counts: Mapping[str, int]


def normalise_content(data: bytes) -> bytes:
    """Return ``data`` with CRLF replaced by LF."""
    return data.replace(b"\r\n", b"\n")


def blob_hash(data: bytes) -> str:
    """Return the git blob hash (sha1 hex) of ``data`` after LF normalisation."""
    content = normalise_content(data)
    header = b"blob " + str(len(content)).encode() + b"\0"
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def count_lines(data: bytes) -> int:
    """Count lines of ``data`` after LF normalisation.

    A final line without a trailing newline counts as a line.
    """
    content = normalise_content(data)
    if not content:
        return 0
    return content.count(b"\n") + (0 if content.endswith(b"\n") else 1)


def compute_skill_hash(entries: Iterable[tuple[str, str]]) -> str:
    """Return the skill hash for ``(relative_path, blob)`` pairs.

    The pairs are sorted by path, so enumeration order does not matter.
    """
    lines = "".join(f"{path}\0{blob}\n" for path, blob in sorted(entries))
    return HASH_PREFIX + hashlib.sha256(lines.encode()).hexdigest()


def _is_excluded(relative: PurePosixPath) -> bool:
    """True for bytecode folders and files, which are not part of a skill."""
    return bool(_EXCLUDED_DIR_NAMES.intersection(relative.parts)) or (
        relative.suffix in _EXCLUDED_SUFFIXES
    )


def list_skill_files(skill_dir: Path) -> list[str]:
    """Return the sorted relative POSIX paths of the files under ``skill_dir``.

    ``__pycache__`` folders and bytecode files are left out. A missing folder
    gives an empty list.
    """
    paths: list[str] = []
    for entry in skill_dir.rglob("*"):
        if not entry.is_file():
            continue
        relative = PurePosixPath(entry.relative_to(skill_dir).as_posix())
        if not _is_excluded(relative):
            paths.append(relative.as_posix())
    return sorted(paths)


def read_skill_facts(skill_dir: Path = SKILL_DIR) -> SkillFacts:
    """Compute the skill hash and line counts from the files on disk. Blocking.

    Args:
        skill_dir: The skill folder. Defaults to :data:`SKILL_DIR`.

    Raises:
        FileNotFoundError: The folder holds no skill files.
        OSError: A file cannot be read.
    """
    paths = list_skill_files(skill_dir)
    if not paths:
        raise FileNotFoundError(f"no skill files under {skill_dir}")
    blobs: list[tuple[str, str]] = []
    counts: dict[str, int] = {}
    for path in paths:
        data = (skill_dir / path).read_bytes()
        blobs.append((path, blob_hash(data)))
        counts[path] = count_lines(data)
    return SkillFacts(
        skill_hash=compute_skill_hash(blobs), line_counts=MappingProxyType(counts)
    )


def required_files() -> tuple[str, ...]:
    """Return the files the Builder cannot work without, relative to the skill folder.

    These are the files the system prompt makes mandatory reading and the
    scripts the script runner allows.
    """
    scripts = tuple(
        f"scripts/{name}" for name in allowed_script_names(BUILDER_SKILL_ID)
    )
    return (*MANDATORY_FILES, *scripts)


def missing_files(skill_dir: Path = SKILL_DIR) -> list[str]:
    """Return the :func:`required_files` that are not files under ``skill_dir``."""
    return [path for path in required_files() if not (skill_dir / path).is_file()]
