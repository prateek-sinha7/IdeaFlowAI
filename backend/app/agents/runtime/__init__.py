"""app/agents/runtime — app-side runtime implementations (Phase 09 / RUNTIME-01).

The concrete ``RuntimeEnvironment`` impls (local now; ECS-backed later) live here,
NOT in the kernel — they reach ``app.*`` (``app.agents.sandbox`` disk-safety,
``app.core.config.settings.RUNS_ROOT``), which is why they are app-side. Importing
this package fires each module's ``@register`` (the discovery seam in
``agents.capabilities.registry.discover()`` imports ``app.agents.runtime``).
"""

from __future__ import annotations

# Import the impl module so its @register("runtime_env", "local") fires on
# package import (mirrors the app.agents.validators discovery precedent).
from app.agents.runtime import local as local  # noqa: F401
