"""agents/capabilities/compaction/html_skeleton.py — the ``html_skeleton`` compaction.

VERBATIM lift of the engine's ``_extract_html_skeleton`` pure function (engine.py
:3514-3577) behind the compaction capability (PARITY-04 / COMPACT-01 / COMPACT-03).
Extracts a compact ~1-3k char state-map from the full prototype HTML — ``:root``
token values, the routes map, the filled-vs-empty ``<section data-page>`` scan, the
chrome summary, and the total-size line — so build task-2+ receives the skeleton
instead of re-injecting the full (growing) HTML on every call.

The algorithm is COPIED UNCHANGED from the engine: the Phase 0C ``>=50%`` reduction
gate is calibrated to this EXACT output, so the lift must be byte-identical. The
``html_skeleton`` impl here is the strangler "wrap" — the engine's inline copy stays
live until 07-04 routes the build through ``task_loop``/this capability and 07-05
deletes the engine's copy.

The module is PURE: stdlib (``re``) only — no kernel/engine state, no ``app.*`` or
``agents.execution_engine`` import (Pitfall 4 / import-linter). It satisfies the
compaction contract structurally — a ``name`` attribute plus ``compact(html) -> str``
— the shape ``task_loop`` calls via ``resolve("compaction", step.compaction).compact``.
"""

from __future__ import annotations

import re as _re


class HtmlSkeletonCompaction:
    """Compact a full prototype HTML into its skeleton state-map (``name='html_skeleton'``).

    Satisfies the compaction contract: a ``name`` attribute plus
    ``compact(self, html: str) -> str``. The body is a verbatim lift of
    ``ExecutionEngine._extract_html_skeleton`` — do NOT alter the algorithm
    (the 0C ``>=50%`` reduction gate is calibrated to this exact output).
    """

    name = "html_skeleton"

    def compact(self, html: str) -> str:
        """Extract a compact skeleton from the full HTML for build agent context.

        Option 1+5: instead of passing the full HTML (which grows with every task
        and causes O(n²) slowdown), extract only what the build agent needs:
          - :root token values (so DS tokens are preserved across calls)
          - List of <section data-page> IDs with filled/empty status
          - Routes map
          - Chrome structure summary

        Returns a compact ~1-3k char summary instead of the full 50k+ HTML.
        """
        lines: list[str] = []

        # 1. Extract :root tokens
        root_match = _re.search(r":root\s*\{([^}]+)\}", html, _re.DOTALL)
        if root_match:
            root_content = root_match.group(1).strip()
            # Keep only the 6 key token lines
            token_lines = []
            for line in root_content.split("\n"):
                line = line.strip()
                if any(tok in line for tok in ["--bg:", "--fg:", "--accent:", "--surface:", "--border:", "--muted:", "--font-"]):
                    token_lines.append(f"  {line}")
            if token_lines:
                lines.append(":root tokens (current):\n" + "\n".join(token_lines[:12]))

        # 2. Extract routes map
        routes_match = _re.search(r"const routes\s*=\s*\{([^}]+)\}", html, _re.DOTALL)
        if routes_match:
            routes_content = routes_match.group(1).strip()
            lines.append(f"Routes map:\n  {{{ routes_content.strip() }}}")

        # 3. Scan all <section data-page> elements — filled vs empty
        sections = _re.findall(
            r'<section[^>]+data-page=["\']([^"\']+)["\'][^>]*>([\s\S]*?)(?=<section|</body>)',
            html, _re.IGNORECASE
        )
        filled = []
        empty = []
        for page_id, content in sections:
            # A section is "filled" if it has more than just whitespace/comments
            stripped = _re.sub(r'<!--.*?-->', '', content, flags=_re.DOTALL).strip()
            if len(stripped) > 100:
                filled.append(page_id)
            else:
                empty.append(page_id)

        if filled:
            lines.append(f"Pages already built ({len(filled)}): {', '.join(filled)}")
        if empty:
            lines.append(f"Pages still empty ({len(empty)}): {', '.join(empty)}")

        # 4. Chrome summary (topnav/sidebar presence)
        has_sidebar = bool(_re.search(r'<aside|data-od-id=["\']sidebar', html, _re.IGNORECASE))
        has_topnav = bool(_re.search(r'class=["\'][^"\']*topnav|data-od-id=["\']topnav', html, _re.IGNORECASE))
        chrome_type = "sidebar" if has_sidebar else ("topnav" if has_topnav else "none")
        lines.append(f"Chrome: {chrome_type} (copy chrome from any filled page — do NOT rewrite it)")

        # 5. Total HTML size for reference
        lines.append(f"Total HTML so far: {len(html):,} chars across {len(filled) + len(empty)} sections")

        return "\n".join(lines)
