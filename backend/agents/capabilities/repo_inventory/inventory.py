"""agents/capabilities/repo_inventory/inventory.py — file tree + langs + deps (REPO-01 / R-F).

Kernel-side, pure-stdlib. Produces a structural map of a cloned brownfield repo:

  * a file tree (the source files that survive the ignore + binary + size filters),
  * language stats (file count by extension),
  * a dependency list (parsed from ``requirements.txt`` / ``pyproject.toml`` /
    ``package.json`` when present).

Ignore handling (REPO-01 acceptance): prefer ``git ls-files --cached --others
--exclude-standard`` via the ``Workspace`` handle — git already implements
``.gitignore`` semantics natively (R-F: "git already implements ignore
semantics"). Then ADDITIONALLY apply ``.flowinignore`` globs with stdlib
``fnmatch`` (no ``pathspec`` dep). When the handle exposes no git ls-files, fall
back to a stdlib walk that still honors ``.flowinignore`` + binary-skip + size-cap.

Binary-skip: a null-byte sniff over the first ~8 KB (mirrors the
``serialize_sandbox_deliverable`` UTF-8-decode-or-skip defensive idiom).

Size-cap: documented per-file + total-inventory byte caps as module constants.

Lineage (REPO-03/lineage parity): the inventory is written as a typed artifact
(``kind="repo_inventory"``) via the per-run ``ctx.artifacts`` graph + the
``ctx.scoped_store`` writer — owner/workspace-scoped, best-effort DB persist (a
missing offline-harness FK degrades, never breaks the run). Reaches the store via
``getattr(ctx, ...)`` so this module imports no kernel/app type (import-linter).
"""

from __future__ import annotations

import json
import logging
from fnmatch import fnmatch
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# WR-02: asyncio holds only a WEAK reference to tasks — a bare
# ``loop.create_task(...)`` can be garbage-collected before it runs, silently
# dropping the lineage DB write. Retain a strong reference here until each
# persist task completes (discarded via done-callback).
_PENDING_LINEAGE_TASKS: set = set()

# ── documented caps (module constants, REPO-01 acceptance) ───────────────────
MAX_FILE_BYTES = 1_000_000          # skip any single file larger than ~1 MB
MAX_TOTAL_INVENTORY_BYTES = 50_000_000  # stop accumulating past ~50 MB total
_BINARY_SNIFF_BYTES = 8192          # read this many bytes to sniff for a null byte

_FLOWINIGNORE = ".flowinignore"
_DEP_FILES = ("requirements.txt", "pyproject.toml", "package.json")


@register("repo_inventory", "default")
class RepoInventory:
    """Build the structural map of a cloned repo (``name='default'``).

    Stateless; ``build(ctx)`` returns the inventory dict and lineage-tracks it.
    Pure-stdlib — reaches git/disk only via ``ctx.runner`` and the store via
    ``ctx.scoped_store`` (never an ``app.*`` import).
    """

    name = "default"

    def build(self, ctx: Any) -> dict[str, Any]:
        """Walk the repo and return ``{files, languages, dependencies}``.

        Honors ``.gitignore`` (via git ls-files when available) + ``.flowinignore``
        + binary-skip + size-caps. Writes the result as a ``repo_inventory``
        artifact (best-effort).
        """
        runner = getattr(ctx, "runner", None)
        workspace = getattr(runner, "workspace", None) or runner
        if workspace is None:
            return {"files": [], "languages": {}, "dependencies": []}

        ignore_globs = self._load_flowinignore(workspace)
        candidates = self._candidate_files(workspace)

        files: list[str] = []
        languages: dict[str, int] = {}
        total_bytes = 0
        for rel in candidates:
            if self._is_flowinignored(rel, ignore_globs):
                continue
            content = self._read(workspace, rel)
            if content is None:  # unreadable / binary / over the per-file cap
                continue
            size = len(content.encode("utf-8"))
            if total_bytes + size > MAX_TOTAL_INVENTORY_BYTES:
                logger.warning(
                    "repo_inventory: total cap (%d bytes) reached — truncating",
                    MAX_TOTAL_INVENTORY_BYTES,
                )
                break
            total_bytes += size
            files.append(rel)
            ext = rel[rel.rfind(".") :] if "." in rel else "(none)"
            languages[ext] = languages.get(ext, 0) + 1

        dependencies = self._parse_dependencies(workspace, files)

        inventory = {
            "files": sorted(files),
            "languages": languages,
            "dependencies": dependencies,
        }
        self._lineage_track(ctx, inventory)
        return inventory

    # ── ignore / candidate listing ──────────────────────────────────────────
    @staticmethod
    def _candidate_files(workspace: Any) -> list[str]:
        """Prefer ``git ls-files --cached --others --exclude-standard`` (honors
        ``.gitignore`` natively, R-F); else fall back to a stdlib walk."""
        git_ls = getattr(workspace, "git_ls_files", None)
        if callable(git_ls):
            try:
                return list(git_ls())
            except Exception:  # noqa: BLE001 — fall back to a plain walk
                pass
        list_files = getattr(workspace, "list_files", None)
        if callable(list_files):
            return list(list_files())
        root = getattr(workspace, "root", None) or getattr(workspace, "_root", None)
        if root is None:
            return []
        from pathlib import Path

        root_path = Path(root)
        return [
            p.relative_to(root_path).as_posix()
            for p in sorted(root_path.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        ]

    @staticmethod
    def _load_flowinignore(workspace: Any) -> list[str]:
        """Read ``.flowinignore`` globs (one per line, ``#`` comments skipped)."""
        try:
            text = workspace.read_file(_FLOWINIGNORE)
        except Exception:  # noqa: BLE001 — absent is the common case
            return []
        globs: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                globs.append(stripped)
        return globs

    @staticmethod
    def _is_flowinignored(rel: str, globs: list[str]) -> bool:
        for pattern in globs:
            # Match the full relpath, the basename, and a dir-prefix form so a
            # ``build/`` entry excludes ``build/x.o`` too.
            base = rel.rsplit("/", 1)[-1]
            if (
                fnmatch(rel, pattern)
                or fnmatch(base, pattern)
                or fnmatch(rel, pattern.rstrip("/") + "/*")
            ):
                return True
        return False

    # ── read + binary-skip + size-cap ───────────────────────────────────────
    @staticmethod
    def _read(workspace: Any, rel: str) -> str | None:
        """Return decoded text, or ``None`` for binary / unreadable / over-cap."""
        try:
            content = workspace.read_file(rel)
        except UnicodeDecodeError:
            return None  # binary (handle decoded as UTF-8 and failed)
        except Exception:  # noqa: BLE001 — unreadable / missing
            return None
        # Null-byte sniff over the head (defensive even if read_file decoded).
        head = content[:_BINARY_SNIFF_BYTES]
        if "\x00" in head:
            return None
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            return None  # over the per-file cap
        return content

    # ── dependency parsing ──────────────────────────────────────────────────
    def _parse_dependencies(self, workspace: Any, files: list[str]) -> list[str]:
        deps: list[str] = []
        present = set(files)
        for dep_file in _DEP_FILES:
            if dep_file not in present:
                continue
            try:
                text = workspace.read_file(dep_file)
            except Exception:  # noqa: BLE001
                continue
            deps.extend(self._extract_deps(dep_file, text))
        return sorted(set(deps))

    @staticmethod
    def _extract_deps(dep_file: str, text: str) -> list[str]:
        if dep_file == "requirements.txt":
            return [
                ln.strip()
                for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
        if dep_file == "package.json":
            try:
                data = json.loads(text)
            except (ValueError, TypeError):
                return []
            out: list[str] = []
            for key in ("dependencies", "devDependencies"):
                out.extend((data.get(key) or {}).keys())
            return out
        if dep_file == "pyproject.toml":
            # Minimal stdlib extraction: names under [project] dependencies / the
            # poetry table. tomllib is stdlib on 3.11+.
            try:
                import tomllib

                data = tomllib.loads(text)
            except Exception:  # noqa: BLE001 — malformed toml → no deps
                return []
            out = list(data.get("project", {}).get("dependencies", []) or [])
            poetry = (
                data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
            )
            out.extend(poetry.keys())
            return out
        return []

    # ── lineage ─────────────────────────────────────────────────────────────
    def _lineage_track(self, ctx: Any, inventory: dict[str, Any]) -> None:
        """Write the inventory as a typed ``repo_inventory`` artifact (best-effort)."""
        graph = getattr(ctx, "artifacts", None)
        store = getattr(ctx, "scoped_store", None)
        if graph is None:
            return
        try:
            content = json.dumps(inventory, sort_keys=True)
            ref = graph.write_ref(
                run_id=getattr(ctx, "run_id", "") or "",
                owner_id=getattr(ctx, "owner_id", "") or "",
                workspace_id=getattr(ctx, "workspace_id", "") or "",
                kind="repo_inventory",
                producer_step=getattr(ctx, "current_step", None) or "repo_inventory",
                producer_agent=getattr(ctx, "current_agent", None) or "repo_inventory",
                task_id=None,
                content=content,
                location="repo_inventory.json",
                visibility="workspace",
            )
        except Exception as exc:  # noqa: BLE001 — never break the run on lineage write
            logger.warning("repo_inventory: lineage write_ref failed (%s)", exc)
            return
        ctx.repo_inventory_ref = ref
        if store is not None:
            import asyncio

            async def _persist() -> None:
                try:
                    await store.write_ref(ref)
                except Exception as exc:  # noqa: BLE001 — best-effort DB persist
                    logger.warning("repo_inventory: store.write_ref failed (%s)", exc)

            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(_persist())
                # Strong ref until done — asyncio only weak-refs tasks (WR-02).
                _PENDING_LINEAGE_TASKS.add(task)
                task.add_done_callback(_PENDING_LINEAGE_TASKS.discard)
            except RuntimeError:
                # No running loop (sync test/build path) — persist synchronously.
                asyncio.run(_persist())
