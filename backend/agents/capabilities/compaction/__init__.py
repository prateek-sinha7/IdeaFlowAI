"""agents.capabilities.compaction — the ``CompactionStrategy`` capabilities.

A compaction shrinks a large prior deliverable into a compact state-map the
per-task sub-agent receives instead of the full content, so build task-2+ does
not re-inject the whole (growing) HTML on every call (the Phase 0C token-trim
change, COMPACT-01/COMPACT-03 / PARITY-04).

  * ``html_skeleton`` — the verbatim lift of the engine's ``_extract_html_skeleton``
    pure function: ``:root`` tokens + routes map + filled/empty section scan +
    chrome summary + total-size line, returning a ~1-3k char summary instead of
    the full 50k+ HTML.

Each impl satisfies the compaction contract structurally — a ``name`` attribute
plus ``compact(html: str) -> str`` — the shape ``task_loop`` calls against via
``registry.resolve("compaction", step.compaction).compact(prior_html)``. The
module is PURE (stdlib only): no kernel/engine state, no ``app.*`` or
``agents.execution_engine`` import (Pitfall 4 / import-linter).
"""
