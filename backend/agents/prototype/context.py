"""agents/prototype/context.py — RELOCATED (move-don't-copy, INV-12).

The three live prototype OD loaders that used to live here —
``load_prototype_context``, ``get_template_injection_parts``, ``get_example_html``
— were PHYSICALLY MOVED to ``agents/execution_engine/od_context.py`` (their single
new home) in Phase 07-02. The capability layer composes its injection blocks via
the ``opendesign`` ContextProvider (``agents/capabilities/context_providers/
opendesign.py``); the boundary still calls the relocated loaders to build the
``od_context`` dict.

This module is now empty of those definitions. The ``agents/prototype/`` package
itself (this file + the dead ``pipeline.py``) is removed in 07-05 once
``pipeline.py`` is gone — it is intentionally NOT deleted here to keep this plan's
diff scoped to the relocation + importer rewires.
"""

from __future__ import annotations
