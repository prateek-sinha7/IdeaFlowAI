"""Shared TLS trust configuration for outbound HTTP calls.

``httpx``'s ``verify=True`` default trusts *only* certifi's bundled CA
list, ignoring CAs installed in the OS / enterprise trust store. Behind a
TLS-intercepting corporate proxy that makes every outbound ``https://``
request fail with ``CERTIFICATE_VERIFY_FAILED`` even though ``curl`` — which
reads the OS store — reaches the same host fine (ISS-695).

Every outbound ``httpx`` client in the backend passes
``verify=default_ssl_context()`` so the trusted-CA set is resolved in one
place. This *widens* the accepted CAs only; certificate verification and
hostname checking stay on.
"""

from __future__ import annotations

import ssl
from functools import lru_cache

import certifi


@lru_cache(maxsize=1)
def default_ssl_context() -> ssl.SSLContext:
    """Return the TLS context every outbound HTTP call should verify against.

    Trusts the union of the OS/enterprise trust store (plus the standard
    ``SSL_CERT_FILE`` / ``SSL_CERT_DIR`` overrides) and certifi's bundle, so
    it is never narrower than httpx's own default.
    """
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
