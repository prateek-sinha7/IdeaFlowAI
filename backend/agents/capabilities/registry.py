"""agents/capabilities/registry.py — central capability NAME registry (MAN-03).

Phase 4 / 1A seam: a minimal ``CapabilityRegistry`` keyed by ``(kind, name)``
holding the known capability names the 15 workflow manifests reference. The
compiler validates every declared capability reference against this registry
(INV-4) — an unknown name is a compile error naming the bad reference.

Scope guards (D-07):
  - The ``_KNOWN`` membership set stays NAMES only — it is the compiler's INV-4
    validation surface (``is_registered``) and MUST NOT depend on any impl being
    bound. Phase 7 adds a SEPARATE ``(kind,name)->impl`` map (populated by an
    explicit ``install()``), NOT a self-registration decorator and NOT startup
    discovery machinery (those, plus per-owner trust flags, are Phase 8).
    Centralising the bindings in an explicit ``install()`` now and converting to
    ``@register``/``discover()`` in Phase 8 is an evolution, not a dual
    implementation (INV-12 respected).
  - ``resolve(kind, name)`` is a STATIC dict lookup over ``_KNOWN``-validated
    names — it performs no dynamic name resolution of any kind (no attribute
    fetch, no expression evaluation, no dynamic module import) (T-04-01 /
    T-07-01-01). A compiled manifest name maps to executable behavior only
    through this fixed map, so it can never become a code-exec vector.
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


# ---------------------------------------------------------------------------
# (kind, name) -> impl instance map (Phase 7 / D-02).
#
# SEPARATE from ``_KNOWN`` (the compiler membership set) on purpose: ``_KNOWN``
# must validate manifest references at Phase-4 compiler import time WITHOUT any
# impl being bound (``test_registry_capabilities.py`` asserts no impls at that
# import). The impl map is populated LAZILY by :func:`install` — at engine import
# / first ``execute()``, never at compiler import. ``resolve`` looks up THIS map
# (a fixed dict — no dynamic name resolution, T-07-01-01).
# ---------------------------------------------------------------------------
_IMPLS: dict[tuple[str, str], object] = {}
_INSTALLED = False


def install() -> None:
    """Bind one capability impl instance per known ``(kind, name)`` (D-02).

    Imports the builtin capability modules and binds a single stateless instance
    per pair into ``_IMPLS``. Idempotent (re-invocation is a no-op). Invoked
    LAZILY — at engine import / first ``execute()``, NOT at compiler import — so
    the compiler's membership-only path (``is_registered`` over ``_KNOWN``) stays
    honest with zero impls bound (``test_registry_capabilities.py``).

    This is the explicit-binding form sanctioned for Phase 7; the evolution to a
    ``@register``/``discover()`` self-registration machine is Phase 8 (INV-12 —
    not a dual implementation).
    """
    global _INSTALLED
    if _INSTALLED:
        return

    # Local imports (NOT module-level) so importing ``registry`` for the
    # membership path never drags in the impl modules — keeps the compiler import
    # impl-free and avoids any import cycle.
    from agents.capabilities.strategies.single_shot import SingleShotStrategy
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy
    from agents.capabilities.task_parsers.heading_tasks import HeadingTasksParser
    from agents.capabilities.deliverables.single_file import SingleFileResolver
    from agents.capabilities.deliverables.serialized_sandbox import (
        SerializedSandboxResolver,
    )
    from agents.capabilities.deliverables.streamed_text import StreamedTextResolver
    from agents.capabilities.deliverables.ppt import PptResolver

    _IMPLS[("task_parser", "heading_tasks")] = HeadingTasksParser()
    _IMPLS[("strategy", "single_shot")] = SingleShotStrategy()
    _IMPLS[("strategy", "task_loop")] = TaskLoopStrategy()
    # Deliverable resolvers (07-02 / PARITY-02 + PARITY-07).
    _IMPLS[("deliverable", "single_file")] = SingleFileResolver()
    _IMPLS[("deliverable", "serialized_sandbox")] = SerializedSandboxResolver()
    _IMPLS[("deliverable", "streamed_text")] = StreamedTextResolver()
    _IMPLS[("deliverable", "ppt")] = PptResolver()
    # NOTE: context providers (07-02 task 2) + further bindings (validators,
    # compaction, gates) land in later plans
    # as those impl modules are created — add them here alongside their module
    # import. ``resolve`` raises a clear RuntimeError for any known-but-unbound
    # ``(kind, name)`` until then.

    _INSTALLED = True


# Backwards-compatible alias for the D-02 ``install()``/``_register_builtins()``
# spelling — both names point at the same explicit-binding routine.
_register_builtins = install


class CapabilityRegistry:
    """Validates declared capability references and resolves them to impls.

    Two distinct paths:
      * ``is_registered(kind, name)`` — the compiler's INV-4 membership check, a
        pure ``_KNOWN`` set lookup. No dynamic name resolution of any kind
        (T-04-01). Unchanged from Phase 4.
      * ``resolve(kind, name)`` — the D-02 execution seam: a STATIC dict lookup
        over the ``_IMPLS`` map (populated by :func:`install`) returning the bound
        impl instance. Raises on an unknown name BEFORE any lookup, and on a
        known-but-unbound name (a programmer error). Never returns ``None``.
    """

    def is_registered(self, kind: str, name: str) -> bool:
        """Return ``True`` iff ``(kind, name)`` is a known capability."""
        return (kind, name) in _KNOWN

    def resolve(self, kind: str, name: str) -> object:
        """Return the impl instance bound to ``(kind, name)`` (D-02).

        Raises ``KeyError`` for an unknown ``(kind, name)`` — checked against
        ``_KNOWN`` FIRST, before any impl lookup, so a name not in the validated
        set never reaches the map (T-07-01-01). Raises ``RuntimeError`` for a
        known name with no bound impl (the impl modules were not ``install()``-ed,
        a programmer error). This is a pure static dict lookup — it performs no
        dynamic name resolution of any kind.
        """
        if (kind, name) not in _KNOWN:
            raise KeyError(f"unknown capability reference: ({kind!r}, {name!r})")
        # Lazy bind on first resolve so callers need not order install() themselves.
        if not _INSTALLED:
            install()
        try:
            return _IMPLS[(kind, name)]
        except KeyError:  # known name, no impl bound (e.g. an impl not yet landed)
            raise RuntimeError(
                f"capability ({kind!r}, {name!r}) is known but has no bound impl; "
                "call agents.capabilities.registry.install()"
            ) from None

    def resolve_alias(self, pipeline_type: str) -> str:
        """Resolve an id alias to its base manifest id (MAN-05).

        ``od_prototype`` -> ``prototype``; every real key resolves to itself.
        Sourced from ``agents.registry._OD_ALIAS_BASE`` (single source of truth).
        """
        return _OD_ALIAS_BASE.get(pipeline_type, pipeline_type)
