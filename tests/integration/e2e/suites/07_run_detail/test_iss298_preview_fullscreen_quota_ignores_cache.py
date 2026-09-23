"""ISS-298 — `/preview-fullscreen?error=quota` must not discard a still-valid
cached preview sitting in `sessionStorage["__app_preview__"]`.

The `error === "quota"` branch in `preview-fullscreen/page.tsx`'s `useEffect`
returns unconditionally before ever reading that key, even though the plain
(no-param) route a few lines later reads that exact key and renders the
working preview when it holds valid data. `AppBuilderPreview.handleFullscreen`
opens the quota tab without `"noopener"` specifically so it shares
sessionStorage with the opener — so a prior successful Full Screen write is
still there when a later, too-large write throws and opens `?error=quota`.

Reproduction per ISS-298: seed `__app_preview__` with a valid payload, load
the plain route once to prove it renders, then load `?error=quota` in the
same browsing context and confirm the dead-end message no longer wins over
the cached, renderable payload.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

VALID_PAYLOAD = json.dumps(
    {
        "files": [{"path": "index.html", "content": "<h1>hello</h1>"}],
        "projectName": "Iss298Project",
    }
)


@pytest.mark.issue("ISS-298")
def test_quota_error_still_renders_valid_cached_preview(page):
    """`?error=quota` with a valid `__app_preview__` payload already cached
    must render that preview (or at least not show the generic dead-end
    message), matching what the plain route does with the same data."""
    page.goto("/preview-fullscreen")
    page.evaluate(
        "(payload) => sessionStorage.setItem('__app_preview__', payload)",
        VALID_PAYLOAD,
    )

    # Sanity: the plain route renders the cached payload as a working preview.
    page.goto("/preview-fullscreen")
    page.wait_for_load_state("networkidle")
    expect(page).to_have_title("Iss298Project — IDE Preview")

    # Same shared sessionStorage, now hit the quota-flagged URL.
    page.goto("/preview-fullscreen?error=quota")
    page.wait_for_load_state("networkidle")

    dead_end = page.get_by_text("Project too large for full screen")
    expect(dead_end).not_to_be_visible()
