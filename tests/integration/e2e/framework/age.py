"""Does this text carry a relative age?

The product has THREE independent relative-age formatters and they do not
agree on units:

  SavedWorkflowsPage  just now | Nm | Nh | Nd | Nw | then a LOCALE DATE
  NotificationPanel   just now | Nm | Nh | Nd
  LaneRunHeader       just now | Nm | Nh | Nd | Nw | Nmo | Ny

Two things a naive `"ago" in text` gets wrong, and both have already bitten:

  **"just now."** Anything under a minute has no "ago" in it at all. The suite
  CREATES rows as it runs — S-04-17 saves a workflow that S-05-03 then reads —
  so the newest row is reliably seconds old and reliably fails. This is not
  flake; it fails every full run in which those two are ordered that way.

  **The date fallback.** A saved workflow older than 30 days renders
  "Jul 3, 2026", which is a perfectly good age and contains no "ago" either.
  Today every seeded row is recent, so nothing has caught this yet.

`—` is the formatters' own output for an unparseable timestamp, and is
deliberately NOT accepted: that is the absence of an age, not an age.
"""

from __future__ import annotations

import re

# "just now" | "5m ago" / "2w ago" / "3mo ago" | "Jul 3, 2026"
AGE = re.compile(
    r"just now"
    r"|\d+\s*(?:s|m|h|d|w|mo|y)\s+ago"
    r"|[A-Z][a-z]{2}\s+\d{1,2},\s*\d{4}",
)


def has_age(text: str) -> bool:
    """True when `text` states how old something is, in any of the forms above."""
    return AGE.search(text) is not None
