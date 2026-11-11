"""Example budgets for the property suite.

Most properties here are cheap, but a few drive a whole builder turn (a scripted
model, a fake process factory, a temp folder) or build a ``CompiledWorkflow`` per
example, and cost 0.2 to 0.6 s per example. At ``max_examples=100`` or ``200`` a
single test then takes 20 to 60 s on a CI runner with coverage tracing, and the
handful of them added up to about 6 minutes of the backend-offline job.

``examples`` keeps the original, stronger count available for a thorough run
(``PROPERTY_FULL_EXAMPLES=1``, for example a nightly job) and uses a smaller
``quick`` count otherwise. Hypothesis still shrinks and replays failures from its
example database, so a failing case found by the thorough run reproduces quickly.
"""

from __future__ import annotations

import os
from typing import Final

_FULL_ENV: Final = "PROPERTY_FULL_EXAMPLES"


def examples(full: int, *, quick: int) -> int:
    """Return ``full`` when ``PROPERTY_FULL_EXAMPLES=1``, else ``min(full, quick)``."""
    if os.environ.get(_FULL_ENV) == "1":
        return full
    return min(full, quick)
