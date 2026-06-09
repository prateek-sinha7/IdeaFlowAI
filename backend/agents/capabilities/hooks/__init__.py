"""agents/capabilities/hooks/ — the HookProvider / HookHandler capability package (08-05 / F3 / §30).

Importing this package imports its registered hook modules, firing each
``@register("hook", <name>)`` decorator so ``discover()`` (which best-effort imports
this package) binds them into the registry.

08-05 (F3) lands the ``behavioral`` non-executable hook sub-type — the legacy
prompt-only ``## Active Behavioral Hooks`` render lifted out of the factory's inline
hook injection (``behavioral.py``). The package is left importable and the behavioral
sub-type intact because 08-07 (Wave 5) EXTENDS this package with EXECUTABLE
``HookHandler`` hooks (``secret_scan`` / ``otel_tracing``); do not collapse the package
or remove the behavioral provider.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing — NO
``app.*`` import, NO kernel import.
"""

from __future__ import annotations

from agents.capabilities.hooks import behavioral  # noqa: F401 — import side effect: @register
from agents.capabilities.hooks import secret_scan  # noqa: F401 — import side effect: @register (08-07)
from agents.capabilities.hooks.base import (  # noqa: F401 — re-export the executable-hook contract
    HOOK_BLOCK,
    HOOK_CONTINUE,
    HOOK_WARN,
    HOOK_WILDCARD,
    HookOutcome,
    bound_hooks,
)
from agents.capabilities.hooks.behavioral import HookBlock

__all__ = [
    "behavioral",
    "secret_scan",
    "HookBlock",
    "HOOK_BLOCK",
    "HOOK_CONTINUE",
    "HOOK_WARN",
    "HOOK_WILDCARD",
    "HookOutcome",
    "bound_hooks",
]
