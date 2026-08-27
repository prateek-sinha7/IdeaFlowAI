"""agents/capabilities/tools/pptx.py — the ``pptx`` tool_provider capability (spec 017 / T4).

Emits the three tool KEYS `ppt_v2`'s code-generator step needs. Like every other
provider here it returns STRINGS, never tool objects, so this package stays
import-clean of ``app.*`` (import-linter: ``agents.capabilities`` ↛ ``app``) —
the concrete implementations live in ``app/agents/tools/pptx_tools.py`` and the
factory, which IS the composition root, resolves key → tool.

``user_allowed=False``: these tools write a binary into the run sandbox and shell
out to a node subprocess. A user- or db-authored manifest must not be able to
grant that by naming it (CAP-03) — only a file manifest can, which for now means
``ppt_v2`` alone.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

TOOL_RENDER_PPTX = "render_pptx"
TOOL_VERIFY_PPTX_LAYOUT = "verify_pptx_layout"
TOOL_EXTRACT_PPTX_SHAPES = "extract_pptx_shapes"
TOOL_SCREENSHOT_PPTX = "screenshot_pptx"


@register(
    "tool",
    "pptx",
    description="Build a real .pptx from PptxGenJS source and gate it on a "
    "deterministic geometry audit plus a render: render_pptx / "
    "verify_pptx_layout / extract_pptx_shapes / screenshot_pptx (spec 017).",
)
class PptxToolProvider:
    """The pptx tool set (``name='pptx'``).

    Returns ``exclude_builtin=False`` — the step still needs ``read_file`` to read
    the composed deck it is transcribing, so the native filesystem tools stay
    alongside these three.
    """

    name = "pptx"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return (
            [
                TOOL_RENDER_PPTX,
                TOOL_VERIFY_PPTX_LAYOUT,
                TOOL_EXTRACT_PPTX_SHAPES,
                TOOL_SCREENSHOT_PPTX,
            ],
            False,
        )
