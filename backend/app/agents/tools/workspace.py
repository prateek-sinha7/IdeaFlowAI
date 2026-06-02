"""Workspace tools for code-generating deep agents.

These tools give code-writing agents (app-code-generator, feature-implementation,
mulesoft-feature-coding, dotnet-feature-coding, etc.) a real file system to write
into rather than dumping everything into one giant text blob.

Each pipeline run gets its own AgentWorkspace instance. The workspace travels
through the orchestrator as part of the agent context. At pipeline_complete,
workspace.to_final_output() produces the text block the existing PreviewPanel
and FilesTab already know how to parse.

Tools defined here are bound to a workspace instance at construction time
(via factory functions) so each run has isolated state.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Workspace state — one per pipeline run
# ---------------------------------------------------------------------------


class AgentWorkspace:
    """In-memory file store for a single pipeline run.

    Agents write files here via write_file(); the orchestrator serialises the
    workspace to the WorkflowRun.output column as ``filename:`` code blocks so
    the existing FilesTab / AppBuilderPreview continue to work unchanged.
    """

    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    # ── Tool implementations ──────────────────────────────────────────────

    def write_file(self, path: str, content: str) -> str:
        path = _sanitize_path(path)
        self._files[path] = content
        return f"✓ Written: {path} ({len(content):,} bytes)"

    def read_file(self, path: str) -> str:
        path = _sanitize_path(path)
        content = self._files.get(path)
        if content is None:
            return f"File not found: {path}. Available files:\n{self._list()}"
        return content

    def list_files(self) -> str:
        return self._list()

    def _list(self) -> str:
        if not self._files:
            return "(workspace is empty)"
        return "\n".join(
            f"- {p}  ({len(c):,} bytes)" for p, c in sorted(self._files.items())
        )

    # ── Output serialisation ─────────────────────────────────────────────

    # Files written by the engine itself (planning artifacts) — excluded from
    # the deliverable output so they don't pollute the FilesTab / AppBuilderPreview.
    _INTERNAL_FILES = frozenset({"PLANNER.md"})

    def to_final_output(self) -> str:
        """Serialise deliverable files in the ``filename:`` block format that
        the existing AppBuilderPreview and FilesTab parsers understand.

        Internal planning files (PLANNER.md) are excluded — they are engine
        artifacts, not agent deliverables.
        """
        deliverable = {p: c for p, c in self._files.items() if p not in self._INTERNAL_FILES}
        if not deliverable:
            return "(no files written)"
        parts: list[str] = []
        for path, content in sorted(deliverable.items()):
            parts.append(f"```filename: {path}\n{content}\n```")
        return "\n\n".join(parts)

    def file_count(self) -> int:
        """Return count of deliverable files (excludes internal planning files)."""
        return sum(1 for p in self._files if p not in self._INTERNAL_FILES)


# ---------------------------------------------------------------------------
# Path sanitisation — prevent path traversal in tool inputs
# ---------------------------------------------------------------------------


def _sanitize_path(path: str) -> str:
    """Strip leading slashes and resolve any ``..`` components.

    Agent-generated paths can be absolute or contain traversal sequences.
    We normalise to a relative path so everything stays within the workspace.
    """
    # Remove leading slashes, drive letters, UNC prefixes
    path = re.sub(r"^[/\\]+", "", path)
    path = re.sub(r"^[A-Za-z]:[/\\]", "", path)
    # Resolve .. components
    try:
        resolved = str(PurePosixPath(path))
        # If resolution produces an absolute path somehow, strip it
        return resolved.lstrip("/")
    except Exception:
        return path.replace("..", "").lstrip("/")


# ---------------------------------------------------------------------------
# Tool factory — bind tools to a specific workspace instance
# ---------------------------------------------------------------------------


def make_workspace_tools(ws: AgentWorkspace) -> list:
    """Return a list of LangChain tools bound to the given workspace.

    Calling code:
        ws = AgentWorkspace()
        tools = make_workspace_tools(ws)
        agent = DeepAgent(system_prompt=..., tools=tools)
        ...
        output = ws.to_final_output()  # after agent finishes
    """

    @tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file in the project workspace.

        Use this for EVERY file you produce: source code, config files,
        tests, infrastructure, documentation. The path should be relative
        to the project root (e.g. 'src/components/Dashboard.tsx').
        Call write_file once per file — do not dump multiple files in one call.
        """
        return ws.write_file(path, content)

    @tool
    def read_file(path: str) -> str:
        """Read a file that was previously written to the workspace.

        Use this to inspect what a previous agent wrote before extending it,
        or to read a file you wrote earlier in this session.
        """
        return ws.read_file(path)

    @tool
    def list_workspace_files() -> str:
        """List all files currently in the workspace with their sizes.

        Call this at the start of your session to see what previous agents
        have already written so you don't duplicate work.
        """
        return ws.list_files()

    return [write_file, read_file, list_workspace_files]
