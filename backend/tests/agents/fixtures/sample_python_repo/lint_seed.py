"""A file carrying a SEEDED ruff violation for the code_lint validator (EXEC-02).

It compiles cleanly (so code_compile / code_test stay green) but carries an unused
import (``os``) — a Pyflakes F401 finding ruff flags under its default rule set. The
code_lint test asserts code_lint surfaces >=1 issue here with a ``map_severity``
label (NOT a locally-derived string).
"""

import os  # noqa-free ON PURPOSE: this unused import is the seeded F401 violation


def greeting() -> str:
    return "hello"
