"""agents/capabilities/hooks/secret_scan.py — the ``secret_scan`` executable hook (08-07 / HOOK-01..04 / §Security).

The fine-grained complement to the coarse ``security`` gate (08-02): a BLOCKING
``HookHandler`` bound to the ``before_write`` / ``pre_commit`` events that scans a
deliverable write payload for SECRETS and returns ``block`` on a match — halting
the offending write ADDITIVELY (it emits NO existing WS event; a clean
characterization run carries no secret, so the snapshots are unaffected — RESEARCH
Pitfall 6). Every firing writes a ``hook_runs`` row (HOOK-04): ``outcome=block``
on a match, ``outcome=continue`` on a clean payload.

Permissioned ``read_files`` (HOOK-02): the scanner reads write payloads, so it
binds only on a step whose effective permissions grant ``read_files`` (ON by
default). It is NOT bound on a step that lowered ``read_files`` off.

Registered ``user_allowed=True`` (D-02): a defensive scanner is safe to expose on
the user palette (it only blocks secrets; it grants no privilege).

Import purity (import-linter): imports ONLY the registry decorator + the hook
outcome/write helpers + stdlib ``re`` — NO kernel/app import. It reaches the
``hook_runs`` writer through ``ctx.runner`` (the KernelServices handle).
"""

from __future__ import annotations

import re
from typing import Any

from agents.capabilities.hooks.base import HOOK_BLOCK, HOOK_CONTINUE, HookOutcome
from agents.capabilities.hooks.write import write_hook_run
from agents.capabilities.registry import register

# Secret-bearing payload patterns (case-insensitive). Conservative, high-signal
# matchers — a private-key header, common provider key prefixes, and a
# ``key = "value"`` assignment over a secret-y identifier with a long opaque
# value. Tuned to catch obvious leaks WITHOUT flagging ordinary prose (RESEARCH
# Security Domain: secret_scan is the fine-grained complement, not a noisy
# heuristic that would block clean deliverables / break characterization parity).
#
# KNOWN FALSE NEGATIVES (IN-04) — this is NOT a complete DLP control, do not rely
# on it as one: it misses JWTs (``eyJ...`` base64 triples), generic 32/40-hex API
# keys with no ``key=``/prefix context, Azure connection strings, GCP service-
# account JSON private-key bodies not on a ``-----BEGIN-----`` line, base64-encoded
# credentials, and any secret assigned WITHOUT quotes or split across lines (the
# assignment pattern requires a quoted value). A JWT pattern + an entropy heuristic
# for unquoted long opaque tokens are deliberately deferred (they raise the false-
# POSITIVE rate, which would risk blocking clean deliverables). Treat a clean scan
# as "no OBVIOUS leak", never as "definitely no secret".
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PEM private-key blocks (RSA/EC/OPENSSH/generic).
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    # AWS access key id.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # GitHub personal-access / app tokens.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    # Slack tokens.
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    # Google API key.
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    # Stripe live/test secret keys.
    re.compile(r"\bsk_(?:live|test)_[0-9A-Za-z]{16,}\b"),
    # OpenAI / Anthropic style keys.
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    # A secret-y assignment: (api_key|secret|password|token|access_key) = "long opaque value".
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|passwd|access[_-]?key|"
        r"private[_-]?key|client[_-]?secret|auth[_-]?token|token)\b"
        r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    ),
)


def scan_for_secret(payload: str) -> str | None:
    """Return the matched-secret KIND (the pattern label) iff ``payload`` carries a secret.

    Returns ``None`` for a clean payload. Pure + stateless so it is unit-testable
    and reused by both the hook and any future pre_commit producer (P9). Matches the
    FIRST pattern that fires so the audit detail records a single deterministic kind.
    """
    if not payload:
        return None
    for pattern in _SECRET_PATTERNS:
        m = pattern.search(payload)
        if m:
            return m.group(0)[:16]  # truncated marker (never log the full secret)
    return None


@register("hook", "secret_scan", user_allowed=True)
class SecretScanHook:
    """The ``secret_scan`` blocking executable hook (``name='secret_scan'``).

    Satisfies the ``HookHandler`` port structurally (``name`` + ``events`` +
    ``required_permission`` + ``async handle``). Bound to ``before_write`` /
    ``pre_commit``; ``required_permission='read_files'`` (HOOK-02). Returns ``block``
    iff the write payload carries a secret, else ``continue`` — and writes a
    ``hook_runs`` row either way (HOOK-04).
    """

    name = "secret_scan"
    events = ["before_write", "pre_commit"]
    required_permission = "read_files"

    async def handle(self, event: Any, ctx: Any) -> HookOutcome:
        """Block iff the firing event's write payload carries a secret (HOOK-01/04)."""
        event_name = _event_name(event)
        payload = _event_payload(event)
        marker = scan_for_secret(payload)

        if marker is not None:
            detail = {
                "matched": True,
                # Never persist the secret itself — record only a truncated marker
                # so a hook_runs audit row carries provenance without the secret.
                "marker": marker,
                "reason": "secret detected in write payload (blocked, T-08-07-ID)",
            }
            await write_hook_run(ctx, self.name, event_name, HOOK_BLOCK, detail)
            return HookOutcome(outcome=HOOK_BLOCK, detail=detail)

        await write_hook_run(
            ctx, self.name, event_name, HOOK_CONTINUE, {"matched": False}
        )
        return HookOutcome(outcome=HOOK_CONTINUE)


def _event_name(event: Any) -> str:
    """Best-effort lifecycle-event name off the fired event (dict or attr)."""
    if isinstance(event, dict):
        return str(event.get("event") or event.get("name") or "before_write")
    return str(getattr(event, "event", None) or getattr(event, "name", "before_write"))


def _event_payload(event: Any) -> str:
    """Best-effort write-payload text off the fired event (dict or attr).

    The ``before_write`` firing carries the content about to be written under
    ``payload`` / ``content`` / ``text``; an absent payload scans to ``""`` (a clean
    continue). Kept defensive so an unexpected event shape degrades to a no-block
    pass rather than aborting the write.
    """
    if isinstance(event, dict):
        value = (
            event.get("payload")
            or event.get("content")
            or event.get("text")
            or ""
        )
    else:
        value = (
            getattr(event, "payload", None)
            or getattr(event, "content", None)
            or getattr(event, "text", None)
            or ""
        )
    return value if isinstance(value, str) else str(value)
