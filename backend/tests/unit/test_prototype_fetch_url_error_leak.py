"""tests/unit/test_prototype_fetch_url_error_leak.py — ISS-343 / ISS-584.

`GET /api/prototype/fetch-url` proxies a user-supplied URL. On an unreachable
domain, `fetch_url_for_template`'s catch-all `except Exception` clause
(`backend/app/api/prototype_templates.py:387-389`) interpolates `str(exc)`
straight into the HTTP `detail`, leaking the raw OS/socket exception text
(e.g. "[Errno 8] nodename nor servname provided, or not known") to the
frontend, which renders it verbatim (`CustomTemplateModal.tsx:110`).

ISS-343 is the root (`/create/prototype`, CONFIRMED live). ISS-584 is the
INFERRED sibling: `PPTTemplateGallery.tsx` (`/create/ppt`) imports and
renders the *same* `CustomTemplateModal`, so the same backend endpoint is the
single chokepoint for both routes — one backend-level test guards both,
matching the cards' own "one fix closes both routes" analysis.

Calls the endpoint function directly (no live network, no TestClient) —
`_is_private_url`'s DNS lookup and the outbound `httpx` fetch are both
mocked to raise the exact `socket.gaierror` the cards document.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.prototype_templates import fetch_url_for_template

DNS_FAILURE = socket.gaierror(8, "nodename nor servname provided, or not known")


async def _call_fetch_url(url: str) -> HTTPException:
    """Invoke the endpoint with DNS resolution and the outbound fetch both
    failing exactly as the cards' repro describes, and return the raised
    HTTPException."""
    with (
        patch("app.api.prototype_templates.socket.gethostbyname", side_effect=DNS_FAILURE),
        patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=DNS_FAILURE)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await fetch_url_for_template(url=url, current_user=None)
    return exc_info.value


@pytest.mark.asyncio
@pytest.mark.issue("ISS-343")
async def test_fetch_url_unreachable_domain_does_not_leak_raw_errno() -> None:
    """A DNS resolution failure must return a friendly message, never the
    raw Python/OS exception text (the root, /create/prototype route)."""
    exc = await _call_fetch_url("http://example.invalid.nonexistent-domain-xyz123/")

    assert exc.status_code == 502
    detail = exc.detail
    assert "Errno" not in detail, f"raw errno text leaked into detail: {detail!r}"
    assert "nodename" not in detail, f"raw socket text leaked into detail: {detail!r}"


@pytest.mark.asyncio
@pytest.mark.issue("ISS-584")
async def test_fetch_url_unreachable_domain_does_not_leak_raw_errno_second_domain() -> None:
    """Same guard, second unreachable domain — pins the deterministic,
    domain-independent nature of the leak the /create/ppt sibling (ISS-584)
    reaches through the identical shared endpoint."""
    exc = await _call_fetch_url("https://another-totally-fake-domain-abc987.invalid/")

    assert exc.status_code == 502
    detail = exc.detail
    assert "Errno" not in detail, f"raw errno text leaked into detail: {detail!r}"
    assert "nodename" not in detail, f"raw socket text leaked into detail: {detail!r}"
