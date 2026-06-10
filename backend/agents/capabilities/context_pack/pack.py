"""agents/capabilities/context_pack/pack.py — targeted per-task context subset (REPO-03 / R-F).

Kernel-side, pure-stdlib. The brownfield analog of ``html_skeleton`` compaction:
given a TARGET file for a task, build a small subset = the target + its
selector-chosen neighbors (same-directory siblings + files the target imports),
EXCLUDING unrelated files. The pack is lineage-tracked as a typed ``context_pack``
artifact so the agent's context provenance is recorded.

``context_selector`` is the pure neighbor-selection function (testable in
isolation): given the target relpath, the candidate file list, and the target's
content, it returns the ordered neighbor relpaths to include. The selector is
deliberately simple + deterministic (no embeddings, D-04): same-directory
siblings first, then files referenced by an import/require/include of the target.

Reaches disk only via ``ctx.runner`` (``Workspace.read_file`` / file listing) and
the store via ``ctx.scoped_store`` — no ``app.*`` / engine import (Pitfall 5).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# Documented cap: never pack more than this many neighbor files (keeps the subset
# targeted — the whole point of the compaction analog).
MAX_NEIGHBORS = 8

# Lightweight import/reference extraction across the supported languages. We only
# need file-name-ish tokens; the selector matches them against the candidate list.
_IMPORT_TOKEN_RE = re.compile(
    r"""(?:from\s+([\w./-]+)\s+import)      # python: from X import
        |(?:import\s+([\w./-]+))            # python/js: import X
        |(?:require\(['"]([\w./-]+)['"]\))  # js: require('X')
        |(?:from\s+['"]([\w./-]+)['"])      # js/ts: from 'X'
    """,
    re.VERBOSE,
)


def context_selector(
    target: str, candidates: list[str], target_content: str
) -> list[str]:
    """Pick the neighbor files for ``target`` (deterministic, no embeddings, D-04).

    Order: same-directory siblings first, then files referenced by the target's
    imports. Excludes the target itself and anything not in ``candidates``. Capped
    at :data:`MAX_NEIGHBORS`.
    """
    candidate_set = {c for c in candidates if c != target}
    ordered: list[str] = []
    seen: set[str] = set()

    # 1) same-directory siblings.
    target_dir = target.rsplit("/", 1)[0] if "/" in target else ""
    for cand in sorted(candidate_set):
        cand_dir = cand.rsplit("/", 1)[0] if "/" in cand else ""
        if cand_dir == target_dir:
            if cand not in seen:
                ordered.append(cand)
                seen.add(cand)

    # 2) import/reference targets (match the imported token against basenames).
    referenced_tokens: set[str] = set()
    for match in _IMPORT_TOKEN_RE.finditer(target_content):
        token = next((g for g in match.groups() if g), None)
        if token:
            # Reduce a dotted/pathy token to its last segment for basename matching.
            referenced_tokens.add(token.replace("/", ".").split(".")[-1])
    if referenced_tokens:
        for cand in sorted(candidate_set):
            if cand in seen:
                continue
            base = cand.rsplit("/", 1)[-1]
            stem = base[: base.rfind(".")] if "." in base else base
            if stem in referenced_tokens:
                ordered.append(cand)
                seen.add(cand)

    return ordered[:MAX_NEIGHBORS]


@register("context_pack", "default")
class ContextPack:
    """Build a targeted file/snippet subset for a task (``name='default'``).

    ``build(ctx, target=...)`` returns ``{target, neighbors, files}`` where
    ``files`` maps each included relpath to its content. Excludes unrelated files;
    lineage-tracked as a ``context_pack`` artifact.
    """

    name = "default"

    def build(self, ctx: Any, *, target: str | None = None) -> dict[str, Any]:
        runner = getattr(ctx, "runner", None)
        workspace = getattr(runner, "workspace", None) or runner
        if workspace is None:
            return {"target": target, "neighbors": [], "files": {}}

        # Resolve the target: explicit arg, else ctx.context_pack_target.
        target = target or getattr(ctx, "context_pack_target", None)
        if not target:
            return {"target": None, "neighbors": [], "files": {}}

        candidates = self._list(workspace)
        target_content = self._read(workspace, target) or ""
        neighbors = context_selector(target, candidates, target_content)

        files: dict[str, str] = {target: target_content}
        for rel in neighbors:
            content = self._read(workspace, rel)
            if content is not None:
                files[rel] = content

        pack = {"target": target, "neighbors": neighbors, "files": files}
        self._lineage_track(ctx, pack)
        return pack

    # ── helpers ─────────────────────────────────────────────────────────────
    @staticmethod
    def _list(workspace: Any) -> list[str]:
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
    def _read(workspace: Any, rel: str) -> str | None:
        try:
            return workspace.read_file(rel)
        except Exception:  # noqa: BLE001 — unreadable / missing
            return None

    def _lineage_track(self, ctx: Any, pack: dict[str, Any]) -> None:
        graph = getattr(ctx, "artifacts", None)
        store = getattr(ctx, "scoped_store", None)
        if graph is None:
            return
        try:
            content = json.dumps(
                {"target": pack["target"], "neighbors": pack["neighbors"]},
                sort_keys=True,
            )
            ref = graph.write_ref(
                run_id=getattr(ctx, "run_id", "") or "",
                owner_id=getattr(ctx, "owner_id", "") or "",
                workspace_id=getattr(ctx, "workspace_id", "") or "",
                kind="context_pack",
                producer_step=getattr(ctx, "current_step", None) or "context_pack",
                producer_agent=getattr(ctx, "current_agent", None) or "context_pack",
                task_id=getattr(ctx, "current_task_id", None),
                content=content,
                location="context_pack.json",
                visibility="workspace",
            )
        except Exception as exc:  # noqa: BLE001 — never break the run on lineage write
            logger.warning("context_pack: lineage write_ref failed (%s)", exc)
            return
        ctx.context_pack_ref = ref
        if store is not None:
            import asyncio

            async def _persist() -> None:
                try:
                    await store.write_ref(ref)
                except Exception as exc:  # noqa: BLE001 — best-effort DB persist
                    logger.warning("context_pack: store.write_ref failed (%s)", exc)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_persist())
            except RuntimeError:
                asyncio.run(_persist())
