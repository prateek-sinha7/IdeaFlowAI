"""agents/capabilities/deliverables/repo_diff.py — the brownfield ``repo_diff`` resolver (REPO-04 / R-F / D-10).

The kernel-side ``DeliverableResolver`` for the brownfield repo workflow class.
It surfaces the agent's edits to a cloned repo as a **diff-only** deliverable:

  * a **file tree** of the changed files (added / modified / deleted),
  * a **per-file unified diff** (``git diff base..work``), and
  * a **change summary** (file count + total lines added / removed).

Reads the diff via the ``Workspace`` handle — ``ctx.runner.workspace.git_diff(base,
work)`` — and the resolver itself spawns no child process (D-10): the ``Workspace``
is the SINGLE owner of the version-control process surface (clone / branch /
diff, 09-01). The base / working branch refs come from the manifest-declared
deliverable binding, read off ``ctx`` at runtime (``base_branch`` /
``working_branch``, defaulting to ``main`` / ``work``) — never a workflow-name
branch (INV-1).

Strictly **diff-only — no write-back, no PR upload** (N4 / N5): the resolver
performs no record-write nor upstream upload of the working branch. It only READS
the ``base..work`` delta through the handle and composes a surface from it; the
``Workspace.git_diff`` it calls stages the working-tree edit onto the WORK branch
locally so the ref diff surfaces the edit — nothing leaves the local clone. The
repo deliverable's shape stays diff-only until N4 decides the hosting / PR scope.

Import purity (import-linter): reaches the diff exclusively through the
``ctx.runner`` handle — no ``app.*`` / kernel import. Mirrors
``serialized_sandbox.py`` (the resolver-via-handle analog).
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# Default refs when the manifest/ctx does not declare them (the local fixture
# clones ``main`` and branches ``work``; 09-01 ``local_git_fixture`` normalizes
# the default branch to ``main``).
_DEFAULT_BASE = "main"
_DEFAULT_WORK = "work"


@register("deliverable", "repo_diff")
class RepoDiffResolver:
    """Resolve the brownfield repo edit as a diff-only deliverable (``name='repo_diff'``).

    Satisfies the ``DeliverableResolver`` port (``name`` + ``resolve``). Reads the
    unified diff from the ``Workspace`` handle (no child process here), composes a
    file tree + per-file diff + change summary, and uploads NOTHING (diff-only, N4).
    """

    name = "repo_diff"

    def resolve(self, ctx: Any) -> Any:
        workspace = self._workspace(ctx)
        if workspace is None:
            logger.warning("repo_diff: no Workspace handle on ctx.runner — empty diff")
            return self._empty()

        base = getattr(ctx, "base_branch", None) or _DEFAULT_BASE
        work = getattr(ctx, "working_branch", None) or _DEFAULT_WORK

        # Read the unified diff via the handle — the Workspace is the SINGLE git
        # owner (clone/branch/diff). The resolver spawns no child process (D-10).
        try:
            unified = workspace.git_diff(base, work) or ""
        except Exception as exc:  # noqa: BLE001 — a diff failure degrades to empty, never aborts
            logger.warning("repo_diff: workspace.git_diff(%s, %s) failed (%s)", base, work, exc)
            return self._empty(base=base, work=work)

        per_file = self._split_per_file(unified)
        tree = self._file_tree(per_file)
        summary = self._summary(per_file, unified)

        return {
            "kind": "repo_diff",
            "base_branch": base,
            "working_branch": work,
            "tree": tree,                 # list of changed file paths (the file tree)
            "diffs": per_file,            # {relpath: per-file unified diff text}
            "diff": unified,              # the full unified diff (per-file blocks joined)
            "summary": summary,           # {files_changed, lines_added, lines_removed}
        }

    # ── handle resolution ────────────────────────────────────────────────────
    @staticmethod
    def _workspace(ctx: Any) -> Any:
        """Reach the ``Workspace`` via ``ctx.runner`` (handle, never an app import).

        Mirrors the repo capabilities' duck-typed reach: a runner exposing a
        ``.workspace`` is preferred; a bare ``Workspace`` passed AS the runner (the
        offline harness shape) is used directly iff it can produce a diff.
        """
        runner = getattr(ctx, "runner", None)
        if runner is None:
            return None
        ws = getattr(runner, "workspace", None)
        if ws is not None and callable(getattr(ws, "git_diff", None)):
            return ws
        if callable(getattr(runner, "git_diff", None)):
            return runner
        return None

    # ── unified-diff parsing (stdlib only) ───────────────────────────────────
    @staticmethod
    def _split_per_file(unified: str) -> dict[str, str]:
        """Split a unified diff into ``{relpath: per-file diff block}``.

        Splits on the ``diff --git a/<p> b/<p>`` headers git emits per file. The
        relpath is taken from the ``b/`` side (the working-tree path), falling back
        to the ``a/`` side for a deletion.
        """
        if not unified.strip():
            return {}
        per_file: dict[str, str] = {}
        current_path: str | None = None
        current_lines: list[str] = []

        def _flush() -> None:
            if current_path is not None and current_lines:
                per_file[current_path] = "\n".join(current_lines).rstrip() + "\n"

        for line in unified.splitlines():
            if line.startswith("diff --git "):
                _flush()
                current_lines = [line]
                current_path = RepoDiffResolver._path_from_header(line)
            else:
                current_lines.append(line)
        _flush()
        return per_file

    @staticmethod
    def _path_from_header(header: str) -> str | None:
        """Extract the changed file path from a ``diff --git a/<p> b/<p>`` header."""
        # header: "diff --git a/src/app.py b/src/app.py"
        parts = header.split(" ")
        # The last two tokens are a/<path> and b/<path>.
        b_token = parts[-1] if len(parts) >= 2 else ""
        a_token = parts[-2] if len(parts) >= 3 else ""
        if b_token.startswith("b/"):
            return b_token[2:]
        if a_token.startswith("a/"):
            return a_token[2:]
        return None

    @staticmethod
    def _file_tree(per_file: dict[str, str]) -> list[str]:
        """The file tree = the sorted list of changed file paths."""
        return sorted(per_file.keys())

    @staticmethod
    def _summary(per_file: dict[str, str], unified: str) -> dict[str, int]:
        """Compose the change summary: file count + lines added / removed.

        Counts ``+``/``-`` content lines, excluding the ``+++``/``---`` file headers
        (a unified-diff convention).
        """
        added = 0
        removed = 0
        for line in unified.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1
        return {
            "files_changed": len(per_file),
            "lines_added": added,
            "lines_removed": removed,
        }

    @staticmethod
    def _empty(*, base: str = _DEFAULT_BASE, work: str = _DEFAULT_WORK) -> dict[str, Any]:
        return {
            "kind": "repo_diff",
            "base_branch": base,
            "working_branch": work,
            "tree": [],
            "diffs": {},
            "diff": "",
            "summary": {"files_changed": 0, "lines_added": 0, "lines_removed": 0},
        }
