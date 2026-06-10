"""agents/capabilities/merge/base.py — the ``MergeStrategy`` port + ``MergeResult``.

The hexagonal port for the merge layer (FANOUT-07). A ``MergeStrategy`` integrates a
set of per-worker fragments into a base workspace/document and reports any conflict as
FIRST-CLASS data (never a silent overwrite — Pitfall 6 / T-11-03-01). Mirrors the
``capabilities.base.ExecutionStrategy`` one-method ``@runtime_checkable`` Protocol
idiom: a ``name: str`` attribute + ONE declared method, runtime objects typed ``Any``.

Import purity: this module imports ONLY stdlib ``typing`` + ``dataclasses`` — no
kernel engine, no ``app.*`` (the import-linter keeps the kernel→ports direction
one-way). The concrete impls satisfy the port structurally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class MergeResult:
    """The typed outcome of a merge (FANOUT-07).

    ``applied`` — the relative paths (or document keys) successfully merged into the
    base. ``conflicts`` — one dict per UNRESOLVED conflict; each carries enough to be
    the ``human_gate`` adjudication payload WITHOUT leaking a raw secret (Phase-10 D-04
    discipline): the relative ``path``/``key``, the per-source worker provenance
    (``sources``), and TRUNCATED hunks/snippets (``hunks``). A non-empty ``conflicts``
    list means the merge reported a conflict — the engine writes a ``merge_conflict``
    artifact + emits a ``merge_conflict`` event and resolves per ``on_conflict``.
    """

    applied: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """``True`` iff no conflicts were reported (the merge applied cleanly)."""
        return not self.conflicts


@runtime_checkable
class MergeStrategy(Protocol):
    """How a set of fan-out fragments integrates into a base — the merge port (§13).

    Variants: ``copy_disjoint`` | ``git_3way`` | ``json`` | ``html_fragment``. The
    ENGINE selects the impl by name (INV-7); the user never names a merge strategy.
    """

    name: str

    def merge(self, base: Any, fragments: Any) -> "MergeResult":
        """Integrate ``fragments`` into ``base``; return the typed ``MergeResult``.

        ``base`` is the merge target (the run's primary workspace handle, a base JSON
        document, or a base HTML document — strategy-specific). ``fragments`` is the
        ordered set of per-worker fragments (workspace handles, JSON docs, or HTML
        snippets). A same-target differing-content overlap is reported as a conflict —
        NEVER silently overwritten (Pitfall 6).
        """
        ...
