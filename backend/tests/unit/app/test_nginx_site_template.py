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

REPO_ROOT = Path(__file__).resolve().parents[4]
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
        i
        for i, l in enumerate(lines)
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
        i
        for i, l in enumerate(lines)
        if l.startswith("cat > /etc/nginx/conf.d/velocityai-limits.conf <<'EOF'")
    )
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "EOF")
    return "\n".join(lines[start + 1 : end])


def test_limit_conn_zone_declared_for_the_stream():
    """The velocityai_stream zone must be declared in the limits config."""
    limits = _render_limits()
    assert "limit_conn_zone $binary_remote_addr zone=velocityai_stream:10m;" in limits


_SSE_PATTERN = r"^/api/runs/[^/]+/events/stream/?$"
_LIVE_RUN_FILES_PATTERN = r"^/api/runs/[^/]+/files/?$"


def test_sse_location_exists_and_is_the_only_regex_location():
    """Exactly one regex location matches the SSE endpoint, and no other regex
    location can compete for it.

    The live-run upload route (``POST /api/runs/{id}/files``) is the one other
    regex location. nginx tries regex locations in definition order, so the set
    of regex patterns is pinned and the two are proven disjoint on sample URIs:
    neither can capture the other's requests.
    """
    site = _render_site()
    blocks = _SSE_LOCATION_RE.findall(site)
    assert len(blocks) == 1, "expected exactly one SSE regex location"
    # Scan only `location` DIRECTIVE lines — never the whole file. Comment prose
    # legitimately names these tokens, and a prose match is a false ratchet trip
    # (the Phase-8 "keep prose off the bare tokens" lesson).
    directives = re.findall(r"^\s*location\s+(\S+)", site, re.M)
    regex_patterns = set(re.findall(r"^\s*location\s+~\s+(\S+)\s*\{", site, re.M))
    assert regex_patterns == {_SSE_PATTERN, _LIVE_RUN_FILES_PATTERN}, (
        "an unexpected regex location would compete for the SSE URI by "
        f"definition order: {sorted(regex_patterns)}"
    )
    sse_uri = "/api/runs/abc/events/stream"
    files_uri = "/api/runs/abc/files"
    assert re.match(_SSE_PATTERN, sse_uri)
    assert not re.match(_LIVE_RUN_FILES_PATTERN, sse_uri)
    assert re.match(_LIVE_RUN_FILES_PATTERN, files_uri)
    assert not re.match(_SSE_PATTERN, files_uri)
    assert (
        "^~" not in directives
    ), "a caret-tilde prefix location would suppress regex matching entirely"


def test_sse_location_is_not_rate_limited_but_is_connection_capped():
    """The SSE location must use limit_conn, not limit_req."""
    site = _render_site()
    match = _SSE_LOCATION_RE.search(site)
    assert match, "SSE regex location not found"
    body = match.group(1)
    assert (
        "limit_req" not in body
    ), "the SSE stream must not sit on the request-rate bucket"
    assert "limit_conn         velocityai_stream 64;" in body
    assert (
        "limit_conn_status" not in body
    ), "leave the default 503 so 429 stays unambiguous"


def _directives(block_body: str) -> list[str]:
    """Directive lines only — comments stripped.

    The block deliberately NAMES `add_header` in a warning comment; asserting over
    raw text would be a false ratchet trip on our own prose (the Phase-8
    "keep prose off the bare tokens" lesson).
    """
    return [
        l.strip()
        for l in block_body.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]


def test_sse_location_keeps_the_streaming_proxy_contract():
    """Verify proxy headers and timeouts match the /ws/chat contract."""
    site = _render_site()
    match = _SSE_LOCATION_RE.search(site)
    assert match, "SSE regex location not found"
    body = match.group(1)
    directives = _directives(body)
    assert (
        "include            /etc/nginx/snippets/velocityai-proxy-headers.conf;"
        in directives
    )
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


# ── Upload routes: per-location body caps (dev 413 on document uploads) ─────
# The server-wide `client_max_body_size 1m;` 413'd every document over 1 MiB on
# the two wizard upload routes before the request reached FastAPI. These tests
# pin per-route caps against the backend's own limits so the default can never
# silently shadow an upload route again.

_STAGE_HEADER = r"location\s+=\s+/api/runs/uploads/stage"
_EXTRACT_HEADER = r"location\s+=\s+/api/files/extract-text"
_LIVE_RUN_FILES_HEADER = r"location\s+~\s+\^/api/runs/\[\^/\]\+/files/\?\$"
_UPLOAD_HEADERS = (_STAGE_HEADER, _EXTRACT_HEADER, _LIVE_RUN_FILES_HEADER)

_SIZE_UNITS = {"": 1, "k": 1024, "m": 1024 * 1024, "g": 1024 * 1024 * 1024}


def _location_block(site: str, header_regex: str) -> str:
    """Return the body of the single location block whose header matches.

    Same `\\{(.*?)\\n    \\}` idiom as the SSE extraction above: a location block
    closes at the first 4-space-indented brace.
    """
    blocks = re.findall(header_regex + r"\s*\{(.*?)\n    \}", site, re.S)
    assert len(blocks) == 1, f"expected exactly one location matching {header_regex!r}"
    return blocks[0]


def _body_cap_bytes(block_body: str) -> int:
    """Parse the block's `client_max_body_size <N>[k|m|g];` into bytes."""
    caps = [d for d in _directives(block_body) if d.startswith("client_max_body_size")]
    assert len(caps) == 1, f"expected exactly one client_max_body_size, got {caps}"
    match = re.fullmatch(r"client_max_body_size\s+(\d+)([kKmMgG]?);", caps[0])
    assert match, f"unparseable body cap: {caps[0]!r}"
    return int(match.group(1)) * _SIZE_UNITS[match.group(2).lower()]


def _seconds(directive: str, block_body: str) -> int:
    """Parse `<directive> <N>s;` from the block into seconds."""
    values = [d for d in _directives(block_body) if d.split()[0] == directive]
    assert len(values) == 1, f"expected exactly one {directive}, got {values}"
    match = re.fullmatch(rf"{directive}\s+(\d+)s;", values[0])
    assert match, f"unparseable {directive}: {values[0]!r}"
    return int(match.group(1))


def test_site_template_stage_cap_covers_backend_aggregate_when_rendered():
    from app.api.run_files import _MAX_AGGREGATE_BYTES

    block = _location_block(_render_site(), _STAGE_HEADER)
    assert _body_cap_bytes(block) >= _MAX_AGGREGATE_BYTES


def test_site_template_extract_cap_covers_backend_file_limit_when_rendered():
    from app.api.file_extract import _MAX_FILE_BYTES

    block = _location_block(_render_site(), _EXTRACT_HEADER)
    assert _body_cap_bytes(block) >= _MAX_FILE_BYTES


def test_site_template_live_run_files_cap_covers_backend_aggregate_when_rendered():
    from app.api.run_files import _MAX_AGGREGATE_BYTES

    block = _location_block(_render_site(), _LIVE_RUN_FILES_HEADER)
    assert _body_cap_bytes(block) >= _MAX_AGGREGATE_BYTES


def test_site_template_upload_locations_keep_api_contract_when_rendered():
    """Each upload block keeps everything the generic /api/ block gives a
    request: the shared rate limit, the backend upstream, the proxy headers and
    unbuffered streaming. No add_header: it is replace-not-merge, so one here
    would drop the five server-level security headers."""
    site = _render_site()
    for header in _UPLOAD_HEADERS:
        directives = _directives(_location_block(site, header))
        assert "limit_req zone=velocityai_api burst=20 nodelay;" in directives, header
        assert "limit_req_status 429;" in directives, header
        assert "proxy_pass         http://velocityai_backend;" in directives, header
        assert (
            "include            /etc/nginx/snippets/velocityai-proxy-headers.conf;"
            in directives
        ), header
        assert "proxy_request_buffering off;" in directives, header
        assert _seconds("client_body_timeout", "\n".join(directives)) >= 120, header
        assert _seconds("proxy_read_timeout", "\n".join(directives)) >= 300, header
        offenders = [d for d in directives if d.startswith("add_header")]
        assert (
            offenders == []
        ), f"{header}: add_header drops security headers {offenders}"


def test_site_template_upload_routes_use_exact_match_when_rendered():
    """The two wizard routes are exact-match locations. nginx stops at an exact
    match before it looks at any prefix or regex location, so neither the 1m
    server default nor the `/api/` prefix block can shadow them."""
    site = _render_site()
    exact = set(re.findall(r"^\s*location\s+=\s+(\S+)\s*\{", site, re.M))
    assert "/api/runs/uploads/stage" in exact
    assert "/api/files/extract-text" in exact


def test_site_template_server_default_stays_one_mebibyte_when_rendered():
    """Only the upload routes are widened: the server-scope default stays 1m and
    the generic /api/ block does not override it."""
    site = _render_site()
    server_scope = re.findall(r"^    client_max_body_size\s+(\S+);", site, re.M)
    assert server_scope == ["1m"], server_scope
    api_block = _location_block(site, r"location /api/")
    assert not any(d.startswith("client_max_body_size") for d in _directives(api_block))
