"""agents/capabilities/deliverables/_mimetype.py — per-resolver default mimetype.

ISS-021 (18-01): the manifest already DECLARES the deliverable shape
(``DeliverableSpec.strategy`` + ``name``). When the author does NOT set an explicit
``DeliverableSpec.mimetype``, the resolver supplies a deterministic default derived
from the DECLARED strategy/name — so existing manifests need zero edits and the FE
renderer (18-03) can dispatch on a mimetype instead of a hardcoded workflow-name
branch (SC-001).

REJECTED hack (CONTEXT): do NOT content-sniff the resolved bytes
(``final_output.startswith("<!doctype")``). The default is a pure function of the
DECLARED strategy/name, never of the deliverable bytes.

Import purity (import-linter): this module is plain stdlib only — no ``app.*`` and
no kernel import — so it composes into the resolver capabilities without crossing a
boundary (Ports & Adapters; ``lint-imports`` stays 4 kept / 0 broken).
"""

from __future__ import annotations

# single_file infers from the declared output-name extension.
_EXTENSION_MIMETYPES: dict[str, str] = {
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
}

# Per-resolver-strategy defaults (used when the strategy is not name-inferred).
_STRATEGY_MIMETYPES: dict[str, str] = {
    "serialized_sandbox": "application/zip",
    "streamed_text": "text/markdown",
    "ppt": "text/html",
}

_FALLBACK = "application/octet-stream"


def _infer_from_name(name: str | None) -> str:
    """Map a declared output filename to a mimetype by its extension."""
    if not name:
        return _FALLBACK
    lowered = name.lower()
    dot = lowered.rfind(".")
    if dot == -1:
        return _FALLBACK
    return _EXTENSION_MIMETYPES.get(lowered[dot:], _FALLBACK)


def default_mimetype(strategy: str | None, name: str | None) -> str:
    """Return the deterministic default mimetype for a declared deliverable.

    Derived ONLY from the DECLARED ``strategy``/``name`` (never the bytes):

      * ``single_file``        → infer from ``name`` extension
                                 (``.html``/``.htm`` → ``text/html``,
                                  ``.md`` → ``text/markdown``,
                                  unknown/none → ``application/octet-stream``)
      * ``serialized_sandbox`` → ``application/zip``
      * ``streamed_text``      → ``text/markdown``
      * ``ppt``                → ``text/html``
      * anything else / None   → ``application/octet-stream``
    """
    if strategy == "single_file":
        return _infer_from_name(name)
    return _STRATEGY_MIMETYPES.get(strategy or "", _FALLBACK)
