"""File backend for the Workflow Builder agent.

The agent sees one virtual file tree built from two roots:

* ``/`` is the session sandbox. It is a ``ValidatingFilesystemBackend``, so a
  ``.json`` write that would not parse is refused at once with a precise
  message. The agent writes its manifests under ``/workflows/``.
* ``/skills/`` is the skill package (``workflow_builder/skills/``), served by
  ``ReadOnlySkillsBackend``. It is read-only and shows only the given skill
  folders, so any other entry beside them never appears in a listing. Nothing
  from the skill is copied into the sandbox.

The write-scope check on the agent's own tool calls (``/workflows/`` only)
lives in the builder middleware. This module covers the skills route and the
backend composition. See design section 3.6.4.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import (
    EditResult,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    WriteResult,
)

from app.agents.validating_backend import ValidatingFilesystemBackend

SKILLS_ROUTE = "/skills/"
SKILL_READ_ONLY_MESSAGE = (
    "The skill is read-only. Write your manifest under /workflows/."
)


def _first_segment(path: str) -> str:
    """Return the first path segment of ``path`` (``/a/b`` gives ``a``)."""
    return path.replace("\\", "/").lstrip("/").split("/", 1)[0]


class ReadOnlySkillsBackend(FilesystemBackend):
    """Read-only view of the skill package that shows only ``visible`` folders.

    ``visible`` holds skill folder names directly under the skills root. A
    listing, glob or grep result is kept only when the first segment of its
    path is one of them. Reads (``read``, ``download_files``) are not changed.
    Every mutation returns the read-only error result and touches nothing.
    """

    def __init__(
        self,
        root_dir: str | Path,
        virtual_mode: bool = True,  # noqa: FBT001, FBT002
        *,
        visible: frozenset[str],
        max_file_size_mb: int = 10,
    ) -> None:
        """Create the backend.

        Args:
            root_dir: The skills root (the folder that holds the skill folders).
            virtual_mode: Must be ``True``. The filters work on virtual paths.
            visible: Skill folder names to show.
            max_file_size_mb: Largest file the grep fallback reads.

        Raises:
            ValueError: ``virtual_mode`` is not ``True``.
        """
        if not virtual_mode:
            raise ValueError("ReadOnlySkillsBackend requires virtual_mode=True")
        super().__init__(
            root_dir=root_dir, virtual_mode=True, max_file_size_mb=max_file_size_mb
        )
        self._visible = frozenset(visible)

    @property
    def visible(self) -> frozenset[str]:
        """Skill folder names this backend shows."""
        return self._visible

    def _is_visible(self, path: str) -> bool:
        return _first_segment(path) in self._visible

    def _visible_entries(self, entries: Iterable[FileInfo]) -> list[FileInfo]:
        return [entry for entry in entries if self._is_visible(entry["path"])]

    def ls(self, path: str) -> LsResult:
        """List ``path`` and keep only entries inside a visible skill folder.

        The skills root itself lists the visible folders and nothing else.
        """
        result = super().ls(path)
        if result.error is not None:
            return result
        return LsResult(entries=self._visible_entries(result.entries or []))

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        """Glob ``pattern`` and keep only matches inside a visible skill folder."""
        result = super().glob(pattern, path)
        if result.error is not None:
            return result
        return GlobResult(matches=self._visible_entries(result.matches or []))

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        """Search and keep only matches inside a visible skill folder."""
        result = super().grep(pattern, path, glob)
        if result.error is not None:
            return result
        matches: list[GrepMatch] = [
            match for match in (result.matches or []) if self._is_visible(match["path"])
        ]
        return GrepResult(matches=matches)

    def write(self, file_path: str, content: str) -> WriteResult:  # noqa: ARG002
        """Refuse: the skill is read-only."""
        return WriteResult(error=SKILL_READ_ONLY_MESSAGE)

    async def awrite(self, file_path: str, content: str) -> WriteResult:  # noqa: ARG002
        """Refuse: the skill is read-only."""
        return WriteResult(error=SKILL_READ_ONLY_MESSAGE)

    def edit(
        self,
        file_path: str,  # noqa: ARG002
        old_string: str,  # noqa: ARG002
        new_string: str,  # noqa: ARG002
        replace_all: bool = False,  # noqa: ARG002, FBT001, FBT002
    ) -> EditResult:
        """Refuse: the skill is read-only."""
        return EditResult(error=SKILL_READ_ONLY_MESSAGE)

    async def aedit(
        self,
        file_path: str,  # noqa: ARG002
        old_string: str,  # noqa: ARG002
        new_string: str,  # noqa: ARG002
        replace_all: bool = False,  # noqa: ARG002, FBT001, FBT002
    ) -> EditResult:
        """Refuse: the skill is read-only."""
        return EditResult(error=SKILL_READ_ONLY_MESSAGE)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Refuse every file: the skill is read-only."""
        return [
            FileUploadResponse(path=path, error=SKILL_READ_ONLY_MESSAGE)
            for path, _ in files
        ]

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        """Refuse every file: the skill is read-only."""
        return self.upload_files(files)


def build_builder_backend(
    sandbox_root: str | Path,
    skills_root: str | Path,
    skill_ids: Iterable[str],
) -> CompositeBackend:
    """Build the Builder agent's file backend.

    Args:
        sandbox_root: The session sandbox folder. It serves ``/``.
        skills_root: The skill package root. It serves ``/skills/`` read-only.
        skill_ids: Skill folder names under ``skills_root`` to show.

    Returns:
        A ``CompositeBackend`` whose default is a ``ValidatingFilesystemBackend``
        on the sandbox and whose ``/skills/`` route is a ``ReadOnlySkillsBackend``.
        No skill file is copied into the sandbox.
    """
    return CompositeBackend(
        default=ValidatingFilesystemBackend(
            root_dir=str(sandbox_root), virtual_mode=True
        ),
        routes={
            SKILLS_ROUTE: ReadOnlySkillsBackend(
                root_dir=str(skills_root),
                virtual_mode=True,
                visible=frozenset(skill_ids),
            )
        },
    )
