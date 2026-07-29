"""The ONE narrow custom precheck hook for prototype-build — the checks the
generic, config-driven model_graded/precheck.py cannot express: the six
required ``:root`` CSS variables must all be present INSIDE the ``:root``
block specifically (not just anywhere in the document), and a hash-router
wiring signal must exist. This needs real parsing (locating the ``:root``
block's body, scanning for router-specific tokens), not a count/substring
check.

Unlike prototype-specify/-plan/-analyze, this agent's graded RESPONSE is a
raw HTML file read back from the sandbox (``driver.py``'s
``deliverable_file`` mechanism) — not a wrapped text document — so there is
no ``<spec>``/``<tasks>``/``<analysis>``-style envelope to check beyond the
document tags themselves (handled generically via ``precheck.wrapper``/
``close_wrapper``).
"""

from __future__ import annotations

import re

_REQUIRED_ROOT_VARS = ("--bg", "--fg", "--accent", "--surface", "--border", "--muted")


def check(response: str) -> tuple[bool, str]:
    """Verify the ``:root { }`` block defines all six required design
    tokens, and the document wires up a hash-based router."""
    root_match = re.search(r":root\s*\{([^}]*)\}", response, re.DOTALL)
    if not root_match:
        return False, "no ':root { }' block found"

    root_body = root_match.group(1)
    missing_vars = [v for v in _REQUIRED_ROOT_VARS if v not in root_body]
    if missing_vars:
        return False, f":root block missing token(s): {missing_vars}"

    if "data-page" not in response:
        return False, "no <section data-page=...> elements found"

    if "location.hash" not in response and "hashchange" not in response:
        return False, "no hash-router wiring found (location.hash / hashchange)"

    return True, "root tokens present, page sections found, hash router wired"
