"""Static guards for the public share link GET /s/{token} (ISS-1037, ISS-1038; root ISS-948)."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[4]


def test_share_route_sends_csp_sandbox():
    """ISS-1038 - shared agent HTML must carry a Content-Security-Policy sandbox header."""
    src = (_ROOT / "backend/app/main.py").read_text()
    start = src.index("share_headers = {")
    block = src[start : src.index("}", start)]
    assert "Content-Security-Policy" in block and "sandbox" in block


def test_share_rewrite_survives_empty_api_url():
    """ISS-1037 - the /s/:token rewrite must treat an empty NEXT_PUBLIC_API_URL like unset."""
    src = (_ROOT / "frontend/next.config.ts").read_text()
    line = next(l for l in src.splitlines() if "/s/:token" in l and "destination" in l)
    assert "??" not in line
