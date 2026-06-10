"""agents/capabilities/registry.py — self-registering capability registry (MAN-03 / CAP-01..03).

Phase 8 / 08-01 seam: a self-registering ``CapabilityRegistry`` keyed by
``(kind, name)``. A module-level ``@register(kind, name, *, user_allowed=...)``
decorator binds ``(kind,name)->impl`` at module import; a startup ``discover()``
explicitly imports the known capability subpackages so each ``@register`` fires.
The compiler validates every declared capability reference against this registry
(INV-4) — an unknown name is a compile error naming the bad reference.

Evolution (D-01, INV-12): this REPLACES the Phase-7 explicit eager-binding
routine (the deleted ``install``/``_register_builtin`` spelling). ``discover()``
is its single successor — NOT a parallel path. The old eager binder is DELETED.

Scope guards:
  - ``_KNOWN`` is the compiler's pure-membership INV-4 surface (``is_registered``)
    and the declared allow-list ``@register`` validates against. It is a literal
    populated at registry-module import (impl-free) so the compiler path can
    validate manifest references WITHOUT any impl being bound
    (``test_registry_capabilities.py`` asserts no impls at compiler import).
    ``@register`` may ADD a ``(kind,name)`` pair (e.g. the new
    ``tool``/``skill``/``hook``/``runtime`` kinds whose names land in later
    plans) — there is no central if/elif over KIND strings; KINDs are free
    strings keyed in ``_KNOWN``.
  - ``discover()`` imports the impl modules — invoked LAZILY at engine import /
    first ``execute()`` / first ``resolve``, NEVER at compiler import (Pattern 3 /
    D-01). The compiler imports this module for ``is_registered`` only; the impl
    subpackages are dragged in only by ``discover()``.
  - ``resolve(kind, name)`` is a STATIC dict lookup over ``_KNOWN``-validated
    names — it performs no dynamic name resolution of any kind (no attribute
    fetch, no expression evaluation, no dynamic import) (T-04-01 / T-07-01-01).
  - Per-capability ``user_allowed`` trust flags live in ``_TRUST`` (D-02): the
    compiler trust check (CAP-03) keeps ``exec``/``secrets``/``spawn_subagents``
    off the user palette.
  - The ``od_prototype -> prototype`` id-alias is lifted from the single source of
    truth in ``agents.registry`` (``_OD_ALIAS_BASE``); it is NOT re-hardcoded here.

Mirrors the module-level-data + accessor idiom of ``agents/registry.py``.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

# Single source of truth for the od_* id alias (od_prototype -> prototype).
# Lifted, not redefined — do NOT inline the alias map here (MAN-05 / D-04).
from agents.registry import _OD_ALIAS_BASE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known capability names — the authoritative (kind, name) membership pairs.
#
# This literal is the compiler's INV-4 pure-membership surface (``is_registered``)
# AND the declared allow-list ``@register`` validates against. It is populated at
# registry-module IMPORT (impl-free) so the compiler can validate manifest
# references with zero impls bound. ``@register`` may ADD a pair (the new
# ``tool``/``skill``/``hook``/``runtime`` kinds land their names in 08-02..08-07).
#
# strategy:        single_shot, task_loop
# validator:       html_static, html_render, spec_plan_coverage, task_done_when, design_quality  (08-04)
# deliverable:     single_file, serialized_sandbox, streamed_text, ppt
# context_provider: opendesign, previous_run
# task_parser:     heading_tasks
# gate:            human, validation, approval, security  (08-02)
# tool:            workspace, prototype, prototype_emit_only, planning  (08-03 / F2)
# compaction:      html_skeleton
# post_step:       revision_validation
# model_catalog:   default  (the ModelCatalog data capability — name-only, D-03)
# runtime:         langchain_deepagents  (08-05 / F5 — AgentRuntimeAdapter, wraps DeepAgentRunner)
# prompt:          default  (08-05 / F1 — PromptAssemblyPolicy, fixed block order)
# skill:           ui, disk, template, repo  (08-05 / F3 / SKILL-01 — versioned skill providers)
# hook:            behavioral  (08-05 / F3 — non-executable hook sub-type)
#                  secret_scan, otel_tracing  (08-07 / HOOK-01..04 / OBS-02 — executable hooks)
# ---------------------------------------------------------------------------
_KNOWN: set[tuple[str, str]] = {
    ("strategy", "single_shot"),
    ("strategy", "task_loop"),
    ("validator", "html_static"),
    ("validator", "html_render"),
    ("validator", "spec_plan_coverage"),   # 08-04 / Tier#4
    ("validator", "task_done_when"),       # 08-04 / Tier#5
    ("validator", "design_quality"),       # 08-04 / Tier#6 (warnings-first)
    ("deliverable", "single_file"),
    ("deliverable", "serialized_sandbox"),
    ("deliverable", "streamed_text"),
    ("deliverable", "ppt"),
    ("context_provider", "opendesign"),
    ("context_provider", "previous_run"),
    ("task_parser", "heading_tasks"),
    ("gate", "human"),
    ("gate", "validation"),
    ("gate", "approval"),   # 08-02
    ("gate", "security"),   # 08-02
    ("tool", "workspace"),             # 08-03 / F2
    ("tool", "prototype"),             # 08-03 / F2
    ("tool", "prototype_emit_only"),   # 08-03 / F2
    ("tool", "planning"),              # 08-03 / F2
    ("compaction", "html_skeleton"),
    ("post_step", "revision_validation"),
    ("model_catalog", "default"),
    ("runtime", "langchain_deepagents"),   # 08-05 / F5
    ("prompt", "default"),                 # 08-05 / F1
    ("skill", "ui"),                       # 08-05 / F3 / SKILL-01
    ("skill", "disk"),                     # 08-05 / F3 / SKILL-01
    ("skill", "template"),                 # 08-05 / F3 / SKILL-01
    ("skill", "repo"),                     # 08-05 / F3 / SKILL-01
    ("hook", "behavioral"),                # 08-05 / F3 (non-executable sub-type)
    ("hook", "secret_scan"),               # 08-07 / HOOK-01..04 (executable, blocking)
    ("hook", "otel_tracing"),              # 08-07 / OBS-02 (executable, non-blocking)
    ("runtime_env", "local"),              # 09-01 / RUNTIME-01 — LocalSandboxRuntime (ECS-swap seam)
}


# ---------------------------------------------------------------------------
# (kind, name) -> impl instance map + per-capability trust flags (D-01/D-02).
#
# ``_IMPLS`` is SEPARATE from ``_KNOWN`` (the compiler membership set) on purpose:
# ``_KNOWN`` must validate manifest references at compiler import time WITHOUT any
# impl being bound. ``_IMPLS`` is populated by ``@register`` at IMPL-module import,
# which only happens inside ``discover()`` — at engine import / first ``execute()``
# / first ``resolve``, never at compiler import. ``resolve`` looks up THIS map (a
# fixed dict — no dynamic name resolution, T-07-01-01).
#
# ``_TRUST`` records the ``user_allowed`` flag per ``(kind, name)`` (D-02): the
# compiler trust check (CAP-03) keeps privileged capabilities off the user palette.
# ---------------------------------------------------------------------------
_IMPLS: dict[tuple[str, str], object] = {}
_TRUST: dict[tuple[str, str], bool] = {}
_DISCOVERED = False


_T = TypeVar("_T")


def register(
    kind: str, name: str, *, user_allowed: bool = False
) -> Callable[[type[_T]], type[_T]]:
    """Self-registration decorator: bind ``(kind,name)->impl`` at module import (D-01).

    Decorate a stateless capability impl CLASS. At import the decorator:
      * adds ``(kind, name)`` to ``_KNOWN`` (the declared membership/allow-list —
        no central if/elif over kinds; the new ``tool``/``skill``/``hook``/
        ``runtime`` kinds register here too);
      * instantiates the class once and binds the instance into ``_IMPLS``;
      * records ``user_allowed`` into ``_TRUST`` (D-02 — privileged capabilities
        default ``user_allowed=False`` and stay off the user palette).

    Built-ins decorate their existing Phase-7 impl classes so ``discover()``
    reproduces the exact ``_IMPLS`` set the deleted ``install()`` produced (INV-12).
    The decorator returns the class UNCHANGED (the binding is the side effect).
    """

    def _decorate(cls: type[_T]) -> type[_T]:
        _KNOWN.add((kind, name))
        _IMPLS[(kind, name)] = cls()
        _TRUST[(kind, name)] = user_allowed
        return cls

    return _decorate


def discover() -> None:
    """Import the known capability subpackages so every ``@register`` fires (D-01).

    The single successor to the deleted ``install()`` (INV-12). Explicitly imports
    the in-tree capability subpackages — NO namespace/package auto-walk, NO
    entry-point magic (D-01 rejects auto-discovery: non-deterministic ordering,
    pulls unintended modules, the import-linter cannot reason about it). Also
    imports the app-side ``app/agents/validators/`` package (the only app-side
    capability package) so the heavy-dep validators self-register without the
    kernel importing ``app.*`` directly (the registry IMPORTS the package to
    trigger its ``@register``; the validators import the kernel PORT, the legal
    direction — D-04).

    Idempotent (a flag guards re-invocation). Invoked LAZILY — at engine import /
    first ``execute()`` / first ``resolve`` — NEVER at compiler import, so the
    compiler's membership-only path (``is_registered`` over ``_KNOWN``) stays
    honest with zero impls bound (``test_registry_capabilities.py``).
    """
    global _DISCOVERED
    if _DISCOVERED:
        return
    # Mark discovered FIRST so a re-entrant import (a capability module importing
    # registry at import time) does not recurse into discover().
    _DISCOVERED = True

    import importlib

    # In-tree (kernel-side) capability packages whose modules carry @register.
    # The forward-surface packages (gates/tools/skills/hooks/runtimes/prompt/
    # validators) are created across 08-02..08-07; import them best-effort so a
    # not-yet-created package is a no-op rather than an ImportError.
    _builtin_modules = (
        "agents.capabilities.strategies.single_shot",
        "agents.capabilities.strategies.task_loop",
        "agents.capabilities.task_parsers.heading_tasks",
        "agents.capabilities.deliverables.single_file",
        "agents.capabilities.deliverables.serialized_sandbox",
        "agents.capabilities.deliverables.streamed_text",
        "agents.capabilities.deliverables.ppt",
        "agents.capabilities.context_providers.opendesign",
        "agents.capabilities.context_providers.previous_run",
        "agents.capabilities.compaction.html_skeleton",
        "agents.capabilities.post_steps.revision_validation",
        # Pure-stdlib kernel-side Tier validators (08-04 / D-05). Imported by module
        # (NOT via the validators package __init__) so importing
        # ``agents.capabilities.validators.severity`` stays @register/discover-clean
        # for the 08-02 gate (08-01 Issues-Encountered: keep severity import-light).
        "agents.capabilities.validators.spec_plan_coverage",
        "agents.capabilities.validators.task_done_when",
    )
    for mod in _builtin_modules:
        importlib.import_module(mod)

    # Forward-surface capability PACKAGES (created in later plans). A package whose
    # __init__ imports its registered modules fires their @register on import.
    _forward_packages = (
        "agents.capabilities.gates",
        "agents.capabilities.tools",
        "agents.capabilities.skills",
        "agents.capabilities.hooks",
        "agents.capabilities.runtimes",
        "agents.capabilities.prompt",
        "agents.capabilities.validators",
        # App-side capability packages (heavy-dep / app.*-reaching impls, D-04).
        # The registry IMPORTS these to trigger their @register; the impls import
        # the kernel PORT (the legal app->ports direction), never the reverse.
        "app.agents.validators",
        "app.agents.runtime",  # 09-01 / RUNTIME-01 — LocalSandboxRuntime self-registers
    )
    for pkg in _forward_packages:
        try:
            importlib.import_module(pkg)
        except ModuleNotFoundError:
            # Package not created yet (lands in a later plan) — best-effort no-op.
            continue
        except ImportError as exc:  # noqa: PERF203 — one broken pkg must not abort all
            # The package EXISTS but failed to import for some other reason (an
            # incompatible optional dependency, a circular import, a syntax error in
            # a sibling module). Degrade to "that package's capabilities are
            # unavailable" rather than aborting ALL registry discovery (IN-03). Logged
            # at warning so the gap is visible, not silent.
            logger.warning(
                "capability discovery: forward package %s failed to import (%s) — "
                "its capabilities are unavailable",
                pkg, exc,
            )
            continue


class CapabilityRegistry:
    """Validates declared capability references and resolves them to impls.

    Paths:
      * ``is_registered(kind, name)`` — the compiler's INV-4 membership check, a
        pure ``_KNOWN`` set lookup. No dynamic name resolution (T-04-01).
      * ``is_user_allowed(kind, name)`` — the CAP-03 trust check: ``True`` iff the
        capability was registered ``user_allowed=True`` (D-02). A capability with
        no recorded trust flag (e.g. the name-only ``model_catalog``) defaults to
        NOT user-allowed.
      * ``resolve(kind, name)`` — the execution seam: a STATIC dict lookup over the
        ``_IMPLS`` map (populated by ``discover()``) returning the bound impl
        instance. Raises on an unknown name BEFORE any lookup, and on a
        known-but-unbound name (a programmer error). Never returns ``None``.
    """

    def is_registered(self, kind: str, name: str) -> bool:
        """Return ``True`` iff ``(kind, name)`` is a known capability."""
        return (kind, name) in _KNOWN

    def is_user_allowed(self, kind: str, name: str) -> bool:
        """Return ``True`` iff the capability is user-grantable (CAP-03 / D-02).

        Ensures impls are discovered so the ``_TRUST`` flag is bound, then reads it.
        A capability with no recorded flag (name-only data capabilities, or an
        unknown reference) defaults to ``False`` — the safe default that keeps
        privileged capabilities off the user palette.
        """
        if not _DISCOVERED:
            discover()
        return _TRUST.get((kind, name), False)

    def resolve(self, kind: str, name: str) -> object:
        """Return the impl instance bound to ``(kind, name)`` (D-02).

        Raises ``KeyError`` for an unknown ``(kind, name)`` — checked against
        ``_KNOWN`` FIRST, before any impl lookup, so a name not in the validated
        set never reaches the map (T-07-01-01). Raises ``RuntimeError`` for a known
        name with no bound impl (the impl modules were not discovered, a programmer
        error). This is a pure static dict lookup — no dynamic name resolution.
        """
        if (kind, name) not in _KNOWN:
            raise KeyError(f"unknown capability reference: ({kind!r}, {name!r})")
        # Lazy discover on first resolve so callers need not order discover() themselves.
        if not _DISCOVERED:
            discover()
        try:
            return _IMPLS[(kind, name)]
        except KeyError:  # known name, no impl bound (e.g. an impl not yet landed)
            raise RuntimeError(
                f"capability ({kind!r}, {name!r}) is known but has no bound impl; "
                "call agents.capabilities.registry.discover()"
            ) from None

    def resolve_alias(self, pipeline_type: str) -> str:
        """Resolve an id alias to its base manifest id (MAN-05).

        ``od_prototype`` -> ``prototype``; every real key resolves to itself.
        Sourced from ``agents.registry._OD_ALIAS_BASE`` (single source of truth).
        """
        return _OD_ALIAS_BASE.get(pipeline_type, pipeline_type)
