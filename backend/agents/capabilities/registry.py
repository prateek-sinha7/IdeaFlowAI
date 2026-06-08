"""agents/capabilities/registry.py — central capability NAME registry (MAN-03).

Phase 4 / 1A seam: a minimal ``CapabilityRegistry`` keyed by ``(kind, name)``
holding the known capability names the 15 workflow manifests reference. The
compiler validates every declared capability reference against this registry
(INV-4) — an unknown name is a compile error naming the bad reference.

Scope guards (D-07):
  - NAMES only. No implementations (Phase 7); no self-registration decorator,
    no startup discovery machinery, and no per-owner trust flags (Phase 8).
    Registering names centrally now and converting to self-registration in
    Phase 8 is an evolution, not a dual implementation (INV-12 respected).
  - The ``od_prototype -> prototype`` id-alias is lifted from the single source
    of truth in ``agents.registry`` (``_OD_ALIAS_BASE``); it is NOT re-hardcoded
    here.

Mirrors the module-level-data + accessor idiom of ``agents/registry.py``.
"""

from __future__ import annotations

# Single source of truth for the od_* id alias (od_prototype -> prototype).
# Lifted, not redefined — do NOT inline the alias map here (MAN-05 / D-04).
from agents.registry import _OD_ALIAS_BASE

# ---------------------------------------------------------------------------
# Known capability names — the authoritative 15 (kind, name) pairs (D-07).
# strategy:        single_shot, task_loop
# validator:       html_static, html_render
# deliverable:     single_file, serialized_sandbox, streamed_text, ppt
# context_provider: opendesign, previous_run
# task_parser:     heading_tasks
# gate:            human, validation
# compaction:      html_skeleton
# model:           default  (the ModelCatalog data capability — name-only, D-03)
# ---------------------------------------------------------------------------
_KNOWN: set[tuple[str, str]] = {
    ("strategy", "single_shot"),
    ("strategy", "task_loop"),
    ("validator", "html_static"),
    ("validator", "html_render"),
    ("deliverable", "single_file"),
    ("deliverable", "serialized_sandbox"),
    ("deliverable", "streamed_text"),
    ("deliverable", "ppt"),
    ("context_provider", "opendesign"),
    ("context_provider", "previous_run"),
    ("task_parser", "heading_tasks"),
    ("gate", "human"),
    ("gate", "validation"),
    ("compaction", "html_skeleton"),
    ("model_catalog", "default"),
}


class CapabilityRegistry:
    """Validates declared capability references by ``(kind, name)`` membership.

    Phase 4 holds only the known names so the compiler can reject an unknown
    reference (INV-4). ``is_registered`` is a pure set-membership check — no
    ``eval``, no dynamic import, no ``getattr`` of the name (T-04-01).
    """

    def is_registered(self, kind: str, name: str) -> bool:
        """Return ``True`` iff ``(kind, name)`` is a known capability."""
        return (kind, name) in _KNOWN

    def resolve_alias(self, pipeline_type: str) -> str:
        """Resolve an id alias to its base manifest id (MAN-05).

        ``od_prototype`` -> ``prototype``; every real key resolves to itself.
        Sourced from ``agents.registry._OD_ALIAS_BASE`` (single source of truth).
        """
        return _OD_ALIAS_BASE.get(pipeline_type, pipeline_type)
