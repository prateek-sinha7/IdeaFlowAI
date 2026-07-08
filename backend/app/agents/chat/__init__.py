"""app.agents.chat — the app-side ``chat`` capability package (33 / D-05).

Holds the registered ``chat:concierge`` impl (``concierge.py``), the per-run
conversational orchestrator. It lives APP-side because it imports the app-side
``DeepAgentRunner`` adapter (the sanctioned INV-13 model seam); it imports the kernel
PORT direction only (the ``@register`` decorator + the owner-scoped ``ScopedStore``
read surface), never the execution kernel.

``discover()`` (registry.py ``_forward_packages``) imports THIS package so the
``@register`` decorator fires — the registry IMPORTS the app package (the legal
``app -> capabilities`` direction), so the concierge self-registers without the kernel
ever importing ``app.*`` (import-linter 4 kept / 0 broken).
"""

# Importing the module here fires its @register at package import (discover()).
from app.agents.chat import concierge  # noqa: F401,E402
