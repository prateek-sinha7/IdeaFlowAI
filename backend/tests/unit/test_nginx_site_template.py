"""A1 — pin the nginx site template's SSE-stream exemption (repo-side, offline).

Pure stdlib, cross-platform. Extracts the site heredoc out of
``infra/scripts/reconcile-host-config.sh`` and asserts the SSE location exists, is NOT
rate limited, and that the general ``/api/`` limiter survives. Non-vacuous: every
assertion fails on the pre-fix tree.

The heredocs live in ``reconcile-host-config.sh``, NOT ``bootstrap-ec2.sh``: FIX-159
extracted the declarative nginx config so it can be re-applied to a running host.
If a future change moves them again, ``_render_site`` / ``_render_limits`` raise
``StopIteration`` rather than silently passing on an empty string — the tests fail
loudly instead of going vacuous.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RECONCILE = REPO_ROOT / "infra" / "scripts" / "reconcile-host-config.sh"

_SSE_LOCATION_RE = re.compile(
    r"location\s+~\s+\^/api/runs/\[\^/\]\+/events/stream/\?\$\s*\{(.*?)\n    \}",
    re.S,
)


def _reconcile_text() -> str:
    return RECONCILE.read_text(encoding="utf-8")


def _render_site() -> str:
    """Extract the `sites-available/velocityai` heredoc from reconcile-host-config.sh.

    This is a pure-Python extraction; no subprocess/bash required.
    """
    text = _reconcile_text()
    lines = text.splitlines()
    start = next(
        i for i, l in enumerate(lines)
        if l.startswith("cat > /etc/nginx/sites-available/velocityai <<EOF")
    )
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "EOF")
    # Extract and perform shell-like variable substitution for $DOMAIN
    body = "\n".join(lines[start + 1 : end])
    # Simple substitution: replace ${DOMAIN} and $DOMAIN with example.test
    body = body.replace("${DOMAIN}", "example.test")
    body = body.replace("$DOMAIN", "example.test")
    return body


def _render_limits() -> str:
    """Extract the `velocityai-limits.conf` heredoc from reconcile-host-config.sh."""
    text = _reconcile_text()
    lines = text.splitlines()
    start = next(
        i for i, l in enumerate(lines)
        if l.startswith("cat > /etc/nginx/conf.d/velocityai-limits.conf <<'EOF'")
    )
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "EOF")
    return "\n".join(lines[start + 1 : end])


def test_limit_conn_zone_declared_for_the_stream():
    """The velocityai_stream zone must be declared in the limits config."""
    limits = _render_limits()
    assert "limit_conn_zone $binary_remote_addr zone=velocityai_stream:10m;" in limits


def test_sse_location_exists_and_is_the_only_regex_location():
    """Exactly one regex location should exist, matching the SSE endpoint."""
    site = _render_site()
    blocks = _SSE_LOCATION_RE.findall(site)
    assert len(blocks) == 1, "expected exactly one SSE regex location"
    # Scan only `location` DIRECTIVE lines — never the whole file. Comment prose
    # legitimately names these tokens, and a prose match is a false ratchet trip
    # (the Phase-8 "keep prose off the bare tokens" lesson).
    directives = re.findall(r"^\s*location\s+(\S+)", site, re.M)
    assert directives.count("~") == 1, (
        "a second regex location would compete for the SSE URI by definition order"
    )
    assert "^~" not in directives, (
        "a caret-tilde prefix location would suppress regex matching entirely"
    )


def test_sse_location_is_not_rate_limited_but_is_connection_capped():
    """The SSE location must use limit_conn, not limit_req."""
    site = _render_site()
    match = _SSE_LOCATION_RE.search(site)
    assert match, "SSE regex location not found"
    body = match.group(1)
    assert "limit_req" not in body, "the SSE stream must not sit on the request-rate bucket"
    assert "limit_conn         velocityai_stream 64;" in body
    assert "limit_conn_status" not in body, "leave the default 503 so 429 stays unambiguous"


def _directives(block_body: str) -> list[str]:
    """Directive lines only — comments stripped.

    The block deliberately NAMES `add_header` in a warning comment; asserting over
    raw text would be a false ratchet trip on our own prose (the Phase-8
    "keep prose off the bare tokens" lesson).
    """
    return [
        l.strip() for l in block_body.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]


def test_sse_location_keeps_the_streaming_proxy_contract():
    """Verify proxy headers and timeouts match the /ws/chat contract."""
    site = _render_site()
    match = _SSE_LOCATION_RE.search(site)
    assert match, "SSE regex location not found"
    body = match.group(1)
    directives = _directives(body)
    assert "include            /etc/nginx/snippets/velocityai-proxy-headers.conf;" in directives
    assert "proxy_buffering    off;" in directives
    assert "proxy_request_buffering off;" in directives
    assert "proxy_read_timeout 5400s;" in directives


def test_sse_location_declares_no_add_header():
    """D3: add_header is replace-not-merge — ONE here drops all five inherited
    security headers. sse_starlette already force-sets X-Accel-Buffering (sse.py:140),
    so the tempting one is also unnecessary."""
    site = _render_site()
    match = _SSE_LOCATION_RE.search(site)
    assert match, "SSE regex location not found"
    directives = _directives(match.group(1))
    offenders = [d for d in directives if d.startswith("add_header")]
    assert offenders == [], (
        f"add_header in the SSE location discards the 5 server-level "
        f"security headers (D3): {offenders}"
    )


def test_general_api_rate_limit_survives():
    """The generic /api/ location must still have its rate limit."""
    site = _render_site()
    api_block = re.search(r"location /api/ \{(.*?)\n    \}", site, re.S).group(1)
    assert "limit_req zone=velocityai_api burst=20 nodelay;" in api_block
    assert "limit_req_status 429;" in api_block
