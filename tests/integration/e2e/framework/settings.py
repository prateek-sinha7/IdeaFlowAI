"""Every capture and timing knob for the suite, in one file.

These values decide what a screenshot looks like. When shots come out blurry,
half-painted, or full of skeletons, this is the ONLY file to change — nothing
below should hard-code a timeout, a viewport or a spinner selector.

Each is overridable from the environment so a slow machine or a CI box can be
tuned without editing code.
"""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# ── the browser ──────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:3000")

VIEWPORT = {
    "width": _int("E2E_VIEWPORT_WIDTH", 1440),
    "height": _int("E2E_VIEWPORT_HEIGHT", 900),
}

# Playwright defaults to 1, which produces a 1440x900 PNG for a 1440x900
# viewport — half the resolution a Retina display shows, and visibly soft the
# moment anyone opens it full size. 2 costs about 180 KB a shot instead of 70.
DEVICE_SCALE_FACTOR = _int("E2E_DPI", 2)


# ── settling before the shutter ──────────────────────────────────────────────

# Ceiling for the whole pre-shot settle. Long enough for a cold dev-server
# compile to finish painting, short enough that one stuck page does not add
# this to every shot in the run.
SETTLE_MS = _int("E2E_SETTLE_MS", 5000)

# Longest we wait for the app to stop showing a loading affordance. The `load`
# event fires when the DOCUMENT is done, which on a client-rendered app is well
# before the DATA is — that gap is what puts skeleton cards and a "Loading
# workspace…" toast into an otherwise correct screenshot.
BUSY_TIMEOUT_MS = _int("E2E_BUSY_TIMEOUT_MS", 8000)

# Anything visible here means the app is still working. Every shot waits for all
# of them to disappear.
#
# ADD TO THIS LIST when a new loading affordance appears — that is the fix for
# "the screenshot caught it mid-load", not a sleep in the test.
BUSY_SELECTORS = (
    # The post-sign-in background preload — store/GlobalPreloadIndicator.tsx.
    # It is deliberately non-blocking for the user, which is exactly why it is
    # still on screen when a naive screenshot fires.
    "text=Loading workspace…",
    # Tailwind's skeleton idiom, used for every placeholder card in the app.
    ".animate-pulse",
    # The spinner icon, wherever it is used.
    ".animate-spin",
    # Standard busy signals, in case a component sets them.
    '[aria-busy="true"]',
    '[data-loading="true"]',
)

# `networkidle` is deliberately NOT used anywhere. The Next.js dev server holds
# an open HMR websocket, so the network is never idle and that wait would burn
# its full timeout on every single shot.
