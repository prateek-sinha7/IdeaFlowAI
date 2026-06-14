"""agents/capabilities/merge/json_merge.py — key-level JSON document merge.

A fan-out merge for fragments that are JSON documents (FANOUT-07): shallow key-level
merge into a base JSON dict. A key present in two fragments (or in a fragment vs the
base) with DIFFERING values is reported as a conflict — never silently overwritten
(Pitfall 6 / T-11-03-01). Determinism: fragments + keys are iterated in sorted order.

Pure stdlib — no kernel import, no ``app.*`` import, no subprocess. ``base`` /
``fragments`` are plain ``dict``s (the engine adapts a JSON deliverable to this shape);
the merge is a pure value transform returning the typed ``MergeResult``.
"""

from __future__ import annotations

import json
from typing import Any

from agents.capabilities.merge.base import MergeResult
from agents.capabilities.registry import register

_SNIPPET_CAP = 256


def _as_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if isinstance(obj, str):
        try:
            loaded = json.loads(obj)
            return dict(loaded) if isinstance(loaded, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _name_of(obj: Any, fallback: str) -> str:
    return str(getattr(obj, "name", None) or fallback)


@register(
    "merge",
    "json",
    user_allowed=True,
    description="Merge fan-out worker outputs by deep-merging their JSON documents.",
)
class JsonMerge:
    """Shallow key-level JSON merge; same-key differing-value → reported conflict.

    The merged document accumulates each fragment's NON-conflicting keys; a key whose
    value differs from an earlier claimant (or the base) is appended to ``conflicts``
    with a truncated value snippet (no raw secret leak, Phase-10 D-04). ``applied``
    lists the merged keys in sorted order (deterministic).
    """

    name = "json"

    def merge(self, base: Any, fragments: Any) -> MergeResult:
        result = MergeResult()
        base_doc = _as_dict(base)
        # WR-08: the merged document must EXIST — mirror copy_disjoint and invoke a
        # structural writer on the base when it exposes one (the live path); a plain
        # dict/str base (offline tests) has no writer and the typed MergeResult is
        # asserted directly.
        writer = getattr(base, "write", None)
        # key -> (source_name, value) of the first claimant.
        claimed: dict[str, tuple[str, Any]] = {}
        conflicted: set[str] = set()  # evicted keys are NEVER applied (no silent overwrite)

        ordered = sorted(list(fragments or []), key=lambda f: _name_of(f, ""))
        for fi, frag in enumerate(ordered):
            frag_name = _name_of(frag, f"fragment-{fi}")
            frag_doc = _as_dict(getattr(frag, "doc", frag))
            for key in sorted(frag_doc.keys()):
                value = frag_doc[key]
                if key in conflicted:
                    continue
                if key in base_doc and base_doc[key] != value:
                    result.conflicts.append(self._conflict(
                        key, [("base", base_doc[key]), (frag_name, value)]
                    ))
                    conflicted.add(key)
                    claimed.pop(key, None)
                    continue
                if key in claimed:
                    prev_name, prev_value = claimed[key]
                    if prev_value != value:
                        result.conflicts.append(self._conflict(
                            key, [(prev_name, prev_value), (frag_name, value)]
                        ))
                        conflicted.add(key)
                        claimed.pop(key, None)
                    continue
                claimed[key] = (frag_name, value)

        # Apply the non-conflicting claims in deterministic key order — writing each
        # merged key onto the base so the merged document accumulates (WR-08).
        for key in sorted(claimed.keys()):
            _src, value = claimed[key]
            if callable(writer):
                writer(key, value)
            result.applied.append(key)
        return result

    @staticmethod
    def _conflict(key: str, sources: list[tuple[str, Any]]) -> dict:
        return {
            "path": key,
            "sources": [name for name, _ in sources],
            "hunks": {name: str(value)[:_SNIPPET_CAP] for name, value in sources},
        }
