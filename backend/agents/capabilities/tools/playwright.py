"""agents/capabilities/tools/playwright.py — the ``playwright`` tool_provider capability (spec 018 / T4).

Emits the nine tool KEYS that headless-browser agents need: navigate, snapshot, click, type,
screenshot, console, wait, evaluate, and close. Like every other provider here it returns
STRINGS, never tool objects, so this package stays import-clean of ``app.*`` (import-linter:
``agents.capabilities`` ↛ ``app``) — the concrete implementations live in
``app/agents/tools/playwright.py`` and the factory, which IS the composition root, resolves
key → tool.

``user_allowed=False``: these tools launch a browser and drive it with user input. A user- or
db-authored manifest must not be able to grant that by naming it (CAP-03) — only a file
manifest can, which for now means ``ppt-deck-qa-v2`` and ``prototype-validate`` alone.

**Why exclude_builtin=False**: ``prototype-validate`` currently declares no tools, so it hits
the "if not spec.tools" short-circuit and returns ([], False) — meaning it keeps its native
filesystem tools (read_file, write_file, edit_file). The moment T9 grants it any tool set,
it routes through the AND-accumulator instead. Returning True (exclude_builtin=True) here
would SILENTLY STRIP read_file from a validator agent whose entire job is reading files.
This is a footgun: the feature would appear to work (no error), but the agent would lose its
primary capability. The False preserves the validator's read access while the browser tools
are present.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

TOOL_PLAYWRIGHT_NAVIGATE = "playwright_navigate"
TOOL_PLAYWRIGHT_SNAPSHOT = "playwright_snapshot"
TOOL_PLAYWRIGHT_CLICK = "playwright_click"
TOOL_PLAYWRIGHT_TYPE = "playwright_type"
TOOL_PLAYWRIGHT_TAKE_SCREENSHOT = "playwright_take_screenshot"
TOOL_PLAYWRIGHT_CONSOLE_MESSAGES = "playwright_console_messages"
TOOL_PLAYWRIGHT_WAIT_FOR = "playwright_wait_for"
TOOL_PLAYWRIGHT_EVALUATE = "playwright_evaluate"
TOOL_PLAYWRIGHT_CLOSE = "playwright_close"


@register(
    "tool",
    "playwright",
    description="Open HTML files in a headless browser, read the page structure, interact "
    "with elements by stable reference, capture screenshots, and inspect console output. "
    "All paths resolved inside the run sandbox, every screenshot written to the workspace. "
    "playwright_navigate / playwright_snapshot / playwright_click / playwright_type / "
    "playwright_take_screenshot / playwright_console_messages / playwright_wait_for / "
    "playwright_evaluate / playwright_close (spec 018).",
    user_allowed=False,
)
class PlaywrightToolProvider:
    """The playwright tool set (``name='playwright'``).

    Returns ``exclude_builtin=False`` — the agent still needs ``read_file`` and ``write_file``
    for workspace navigation and to read/write files alongside browser operations, so the
    native filesystem tools stay alongside these nine browser tools.

    For ``prototype-validate`` in particular: it declares no tools today (hitting the
    "if not spec.tools" short-circuit), so it keeps its native filesystem tools (read_file
    is its primary capability). If T9 grants it this tool set, it routes through the
    AND-accumulator. Returning True (exclude_builtin=True) here would SILENTLY STRIP
    read_file — the validator's core job — from the spec, creating a broken agent with no
    error message. The False is not a stylistic choice; it is load-bearing for correctness.
    """

    name = "playwright"

    def provide(self, spec: Any, ctx: Any) -> tuple[list[str], bool]:
        return (
            [
                TOOL_PLAYWRIGHT_NAVIGATE,
                TOOL_PLAYWRIGHT_SNAPSHOT,
                TOOL_PLAYWRIGHT_CLICK,
                TOOL_PLAYWRIGHT_TYPE,
                TOOL_PLAYWRIGHT_TAKE_SCREENSHOT,
                TOOL_PLAYWRIGHT_CONSOLE_MESSAGES,
                TOOL_PLAYWRIGHT_WAIT_FOR,
                TOOL_PLAYWRIGHT_EVALUATE,
                TOOL_PLAYWRIGHT_CLOSE,
            ],
            False,
        )
