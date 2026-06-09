"""app.agents.validators — the app-side heavy-dep Validator capability package (D-04).

The ONLY app-side capability package. Its modules hold the registered ``Validator``
impls that wrap a heavy/app-side dependency:

  * ``html_static``    — wraps ``app.agents.static_check.static_check`` (stdlib HTML
    structural validation);
  * ``html_render``    — wraps ``app.agents.render_check.render_check`` (headless
    Chromium; degrades to ``available=False`` offline);
  * ``design_quality`` — Tier#6 tokens/placeholder/a11y warnings (warnings-first,
    non-blocking — emits only P2/P3).

These live APP-side because they import a heavy ``app.*`` dependency. They import the
kernel PORT (``agents.capabilities.base.Validator``) + the ``@register`` decorator —
the import-linter-LEGAL direction (app → capabilities; it forbids only the reverse
``agents.capabilities -> app``). The kernel / ``task_loop`` NEVER import this package;
they reach the impls via ``CapabilityRegistry().resolve("validator", name)`` and call
``.validate(target)`` where ``target.runner`` is the KernelServices handle.

``discover()`` (08-01, registry.py) imports THIS package so the ``@register``
decorators fire (the registry imports the app package — the legal direction — so the
heavy-dep validators self-register without the kernel importing ``app.*`` directly).

The pure-stdlib Tier validators (``task_done_when`` / ``spec_plan_coverage``) live
KERNEL-side in ``agents/capabilities/validators/`` — they need no heavy dep.
"""

# Importing the modules here fires their @register at package import (discover()).
from app.agents.validators import html_render, html_static  # noqa: F401,E402

# design_quality lands in Task 2 (best-effort import keeps the package importable
# between Task-1 and Task-2 commits without an ImportError).
try:  # pragma: no cover - transitional between Task 1 and Task 2
    from app.agents.validators import design_quality  # noqa: F401,E402
except ImportError:
    pass
