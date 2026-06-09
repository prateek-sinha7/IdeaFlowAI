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
# Order matters (WR-02): import the SECURITY hook (``secret_scan``) BEFORE the
# OPTIONAL-dependency observability hook (``otel_tracing``) so the security control
# registers independently — even though otel_tracing now guards its imports, keeping
# the security hook first means a future hard-import failure in an observability hook
# can never de-register the secret scanner.
from agents.capabilities.hooks import secret_scan  # noqa: F401 — import side effect: @register (08-07)
from agents.capabilities.hooks import otel_tracing  # noqa: F401 — import side effect: @register (08-07 / OBS-02)
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
    "otel_tracing",
    "secret_scan",
    "HookBlock",
    "HOOK_BLOCK",
    "HOOK_CONTINUE",
    "HOOK_WARN",
    "HOOK_WILDCARD",
    "HookOutcome",
    "bound_hooks",
]
