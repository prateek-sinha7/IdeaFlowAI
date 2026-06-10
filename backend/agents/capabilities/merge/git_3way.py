"""agents/capabilities/merge/git_3way.py — 3-way version-control merge of worktree fragments.

The fan-out merge for ``worktree`` fragments (FANOUT-07): each worker committed on a
per-worker branch off the captured spawn-point commit (11-02); this strategy merges
those branches back into the base working branch. The 3-way merge runs ONLY through
the ``ctx.runner`` handle (``KernelServices.git_3way_merge`` → ``LocalWorkspace
.merge_worktree``) — NEVER a capability-side process spawn (Pitfall 2 / Phase-9 D-10).
A merge conflict is parsed into ``MergeResult.conflicts`` (the conflicting paths
+ per-branch provenance), never silently resolved.

Pure stdlib — no kernel import, no ``app.*`` import, and NO process spawning of the
version-control toolchain here. The strategy reaches the merge dynamically off the
runner handle the engine threads onto each fragment (``fragment.runner`` + branch).
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.merge.base import MergeResult
from agents.capabilities.registry import register

_SNIPPET_CAP = 256


@register("merge", "git_3way", user_allowed=True)
class Git3WayMerge:
    """Merge per-worker worktree branches back to base via the runner merge handle.

    For each fragment, the engine threads ``runner`` (the ``ctx.runner`` handle, which
    owns the single version-control process owner), ``branch`` (the per-worker branch
    ``fanout/...``), and ``base_commit`` (the captured spawn-point merge-base). This
    strategy calls ``runner.git_3way_merge(branch, base_commit)`` — it shells NOTHING
    itself. A clean merge appends the branch to ``applied``; a conflicting merge appends
    the parsed conflict paths to ``conflicts`` (never overwriting the base, T-11-03-01).
    """

    name = "git_3way"

    def merge(self, base: Any, fragments: Any) -> MergeResult:
        result = MergeResult()
        # Iterate in declared (worker-index) order so the merge sequence is stable.
        for fi, frag in enumerate(list(fragments or [])):
            runner = getattr(frag, "runner", None)
            branch = getattr(frag, "branch", None)
            base_commit = getattr(frag, "base_commit", "")
            merge_fn = getattr(runner, "git_3way_merge", None) if runner is not None else None
            if merge_fn is None or not branch:
                # No reachable merge handle (offline / non-worktree fragment) — nothing
                # to merge for this fragment; skip without fabricating a conflict.
                continue
            info = merge_fn(branch, base_commit)
            conflict_paths = list((info or {}).get("conflicts", []) or [])
            if conflict_paths:
                for path in conflict_paths:
                    result.conflicts.append({
                        "path": path,
                        "sources": ["base", str(branch)],
                        "hunks": {
                            str(branch): str((info or {}).get("snippet", ""))[:_SNIPPET_CAP],
                        },
                    })
            else:
                result.applied.append(str(branch))
        return result
