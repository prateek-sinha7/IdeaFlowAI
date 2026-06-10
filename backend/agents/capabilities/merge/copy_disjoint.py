"""agents/capabilities/merge/copy_disjoint.py — deterministic disjoint-file merge.

The default fan-out merge for ``sub_sandbox`` fragments (FANOUT-07): copy each
worker fragment's files into the base. A DISJOINT set (no two fragments write the same
relative path) produces a byte-stable deterministic result; an OVERLAP (two fragments —
or a fragment vs the base-since-spawn — touching the SAME relative path with DIFFERING
content) is reported as a conflict and NEVER overwritten (Pitfall 6 / T-11-03-01).

Pure stdlib — no kernel import, no ``app.*`` import, no subprocess. Operates over a
structural fragment shape: each fragment exposes ``files() -> dict[str, str]`` (relative
path → content) and ``name`` (worker provenance); the base exposes the same so a
base-since-spawn overlap is detectable. The engine adapts an isolated ``Workspace`` to
this shape via a thin fragment view — the strategy stays handle-free and offline-testable.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.merge.base import MergeResult
from agents.capabilities.registry import register

# Truncate any snippet that rides the conflict payload so a raw secret can never leak
# into the merge_conflict artifact / the human_gate adjudication view (Phase-10 D-04).
_SNIPPET_CAP = 256


def _files_of(obj: Any) -> dict[str, str]:
    """Return the relative-path → content map for a fragment/base (structural).

    A fragment exposes ``files()``; a missing/None object is the empty map (a base with
    no files-since-spawn). Sorted iteration is the caller's concern (determinism).
    """
    if obj is None:
        return {}
    files = getattr(obj, "files", None)
    if callable(files):
        return dict(files() or {})
    return {}


def _name_of(obj: Any, fallback: str) -> str:
    return str(getattr(obj, "name", None) or fallback)


@register("merge", "copy_disjoint", user_allowed=True)
class CopyDisjointMerge:
    """Copy disjoint fragment files into base; report same-path overlaps as conflicts.

    Determinism: fragments are iterated in SORTED order (by fragment name) and each
    fragment's files in SORTED path order, so a disjoint set produces a byte-stable
    ``applied`` list across runs (T-11-03-01 determinism). The merge is recorded as
    ``applied`` (the merged relative paths); ``base.write(path, content)`` is invoked
    when the base exposes a writer (the live path) — offline tests assert the typed
    ``MergeResult`` directly.
    """

    name = "copy_disjoint"

    def merge(self, base: Any, fragments: Any) -> MergeResult:
        result = MergeResult()
        base_files = _files_of(base)
        writer = getattr(base, "write", None)

        # path -> (source_name, content) of the FIRST fragment that claimed it, so a
        # second differing writer is detected as an overlap (never silently applied).
        claimed: dict[str, tuple[str, str]] = {}
        # Paths that hit a conflict are EVICTED from claimed so a conflicting path is
        # NEVER applied to the base (no silent overwrite — T-11-03-01).
        conflicted: set[str] = set()

        ordered = sorted(
            list(fragments or []),
            key=lambda f: _name_of(f, ""),
        )
        for fi, frag in enumerate(ordered):
            frag_name = _name_of(frag, f"fragment-{fi}")
            for path in sorted(_files_of(frag).keys()):
                content = _files_of(frag)[path]
                if path in conflicted:
                    continue  # already reported — never apply a conflicting path
                # Overlap vs the base-since-spawn (same path, DIFFERING content).
                if path in base_files and base_files[path] != content:
                    result.conflicts.append(self._conflict(
                        path, [("base", base_files[path]), (frag_name, content)]
                    ))
                    conflicted.add(path)
                    claimed.pop(path, None)
                    continue
                # Overlap vs an earlier fragment (same path, DIFFERING content).
                if path in claimed:
                    prev_name, prev_content = claimed[path]
                    if prev_content != content:
                        result.conflicts.append(self._conflict(
                            path, [(prev_name, prev_content), (frag_name, content)]
                        ))
                        conflicted.add(path)
                        claimed.pop(path, None)
                    # Same content as an earlier claimant ⇒ idempotent, already applied.
                    continue
                claimed[path] = (frag_name, content)

        # Apply the non-conflicting claims in deterministic path order.
        for path in sorted(claimed.keys()):
            _src, content = claimed[path]
            if callable(writer):
                writer(path, content)
            result.applied.append(path)
        return result

    @staticmethod
    def _conflict(path: str, sources: list[tuple[str, str]]) -> dict:
        """Build a secret-safe conflict record (truncated hunks; per-source provenance)."""
        return {
            "path": path,
            "sources": [name for name, _ in sources],
            "hunks": {name: (content or "")[:_SNIPPET_CAP] for name, content in sources},
        }
