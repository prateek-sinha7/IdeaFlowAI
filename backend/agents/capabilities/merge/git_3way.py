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

Task 4.3 (sandbox-git-versioning-v2, Req 11 AC 9-10): ``merge()`` is now
``async`` so that the inter-fragment commit between sequential ``git merge`` calls
is routed through the ONE security-gated ``commit_in_sandbox`` primitive.  The
commit callable is pre-built in ``fanout.py`` (which CAN import ``engine.py``) and
threaded onto each ``_WorktreeFragmentView`` as ``fragment.commit_fn``.  When no
``commit_fn`` is present (offline harness / tests), the strategy falls back to a
plain ``commit_all`` call — preserving existing behavior for all non-git tests.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.merge.base import MergeResult
from agents.capabilities.registry import register

_SNIPPET_CAP = 256


@register(
    "merge",
    "git_3way",
    user_allowed=True,
    description="Merge overlapping fan-out worker outputs via a git three-way merge.",
)
class Git3WayMerge:
    """Merge per-worker worktree branches back to base via the runner merge handle.

    For each fragment, the engine threads ``runner`` (the ``ctx.runner`` handle, which
    owns the single version-control process owner), ``branch`` (the per-worker branch
    ``fanout/...``), and ``base_commit`` (the captured spawn-point merge-base). This
    strategy calls ``runner.git_3way_merge(branch, base_commit)`` — it shells NOTHING
    itself. A clean merge appends the branch to ``applied``; a conflicting merge appends
    the parsed conflict paths to ``conflicts`` (never overwriting the base, T-11-03-01).

    The strategy additionally performs a commit between each successfully merged fragment
    so that ``MERGE_HEAD`` is cleared before the next ``git merge`` is attempted
    (FR-034).  This commit is routed through the ``fragment.commit_fn`` async callable
    when available (task 4.3), otherwise through a plain ``commit_all`` fallback (offline
    harness / tests that do not supply a security-gated callable).
    """

    name = "git_3way"

    async def merge(self, base: Any, fragments: Any) -> MergeResult:  # type: ignore[override]
        """Merge fragments; async to allow awaiting the inter-fragment commit_fn."""
        result = MergeResult()
        # Iterate in declared (worker-index) order so the merge sequence is stable.
        for fi, frag in enumerate(list(fragments or [])):
            runner = getattr(frag, "runner", None)
            branch = getattr(frag, "branch", None)
            base_commit = getattr(frag, "base_commit", "")
            merge_fn = (
                getattr(runner, "git_3way_merge", None) if runner is not None else None
            )
            if merge_fn is None or not branch:
                # No reachable merge handle (offline / non-worktree fragment) — nothing
                # to merge for this fragment; skip without fabricating a conflict.
                continue
            info = merge_fn(branch, base_commit)
            conflict_paths = list((info or {}).get("conflicts", []) or [])
            if conflict_paths:
                for path in conflict_paths:
                    result.conflicts.append(
                        {
                            "path": path,
                            "sources": ["base", str(branch)],
                            "hunks": {
                                str(branch): str((info or {}).get("snippet", ""))[
                                    :_SNIPPET_CAP
                                ],
                            },
                        }
                    )
            else:
                result.applied.append(str(branch))
                # Commit between fragments so MERGE_HEAD is cleared before the next
                # fragment's ``git merge`` runs.  Without this commit the second merge
                # is refused (MERGE_HEAD still set), the conflict probe finds nothing,
                # and ``git merge --abort`` silently destroys the first fragment's work
                # (FR-034 / Requirements 7, 25).
                #
                # Task 4.3 (sandbox-git-versioning-v2, Req 11 AC 9-10): route through
                # the security-gated ``commit_fn`` when available; fall back to a plain
                # ``commit_all`` for offline harness / tests without a callable.
                # A failure in either path is tolerated — the calling layer surfaces the
                # inconsistency when the next merge is refused.
                commit_fn = getattr(frag, "commit_fn", None)
                commit_msg = f"merge: {branch}"
                if commit_fn is not None:
                    try:
                        await commit_fn(commit_msg)
                    except Exception:  # noqa: BLE001 — best-effort; never abort the loop
                        pass
                else:
                    # Fallback: plain commit_all via the base workspace duck-type
                    # (offline / test paths that supply no commit_fn).
                    plain_commit_fn = getattr(base, "commit_all", None)
                    if callable(plain_commit_fn):
                        try:
                            plain_commit_fn(commit_msg)
                        except Exception:  # noqa: BLE001 — best-effort; never abort the loop
                            pass
        return result
