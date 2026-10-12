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
outcome/write helpers + stdlib ``re`` / ``io`` / ``zipfile`` / ``os`` — NO
kernel/app import. It reaches the ``hook_runs`` writer through ``ctx.runner`` (the
KernelServices handle).

Binary scanning (Requirement 11 AC 14–17, V2-Q12):
  - Text payloads: matched against ``_SECRET_PATTERNS`` (unchanged from v1).
  - Binary payloads (bytes): dispatched through ``scan_staged_binary``, which applies
    a per-entry policy determined by file extension:
      * PPTX / DOCX / XLSX / ZIP → bounded safe extraction and text scan.
      * Oversized binary → block by size (``BINARY_MAX_BYTES``).
      * Unknown binary type → BLOCK (fail-closed; "binary files differ" is never OK).
    A security-approved exemption may be registered in ``BINARY_APPROVED_EXEMPTIONS``
    keyed by normalized basename + approval id.
  - Binary events carry both ``content_bytes`` (raw) and ``filename`` hint on the
    fired event.  The hook extracts them via ``_event_binary``.

Zip-slip protection: every member path extracted from a ZIP-family container is
normalized against an ephemeral in-memory prefix; any member whose normalized path
escapes the extraction root is rejected and blocks the commit.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Any

from agents.capabilities.hooks.base import HOOK_BLOCK, HOOK_CONTINUE, HookOutcome
from agents.capabilities.hooks.write import write_hook_run
from agents.capabilities.registry import register

# ---------------------------------------------------------------------------
# Text secret patterns (unchanged from v1 — D5 / Requirement 11 AC 4)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Binary scanning policy (Requirement 11 AC 14–17, V2-Q12)
# ---------------------------------------------------------------------------

# Maximum raw bytes to accept without blocking by size.  Files larger than this
# are blocked (policy: BLOCK_SIZE) rather than scanned, to avoid unbounded memory.
BINARY_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MiB

# Maximum cumulative uncompressed bytes extracted from a container scan.
EXTRACTION_MAX_BYTES: int = 200 * 1024 * 1024  # 200 MiB

# Maximum recursion depth for nested ZIP containers (flat containers → depth 1).
EXTRACTION_MAX_DEPTH: int = 2

# Extensions that identify Office Open XML / ZIP containers that can be safely
# extracted and text-scanned.
_EXTRACTABLE_EXTENSIONS: frozenset[str] = frozenset({".pptx", ".docx", ".xlsx", ".zip"})

# Extensions we treat as *text-content* binary (e.g. XML-heavy zips already
# covered above) — anything not in this set and not text is UNKNOWN → BLOCK.
_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".rst",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
        ".xml",
        ".html",
        ".htm",
        ".js",
        ".ts",
        ".py",
        ".rb",
        ".go",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".cs",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".sql",
        ".env",
        ".gitignore",
        ".gitattributes",
    }
)


@dataclass(frozen=True)
class BinaryApprovedExemption:
    """A security-approved exemption for a specific binary file pattern.

    ``approval_id`` is a mandatory, non-empty reference to the recorded security
    decision. An exemption with an empty ``approval_id`` is silently ignored at
    registration time so that a half-filled record cannot accidentally opt out of
    scanning.
    """

    basename_pattern: str  # fnmatch pattern against normalized file basename
    approval_id: str  # mandatory non-empty approval reference
    reason: str  # human-readable rationale for operator review


# Registry of security-approved binary exemptions. Keyed by ``approval_id`` so
# each exemption is uniquely attributable. Empty by default; operators add
# entries here under a recorded security review.
#
# IMPORTANT: an exemption ONLY bypasses the per-binary block; it does NOT
# bypass the secret-pattern scan of the extracted text.  The scan is still
# performed; only the "unknown-type → block" policy is relaxed.
BINARY_APPROVED_EXEMPTIONS: dict[str, BinaryApprovedExemption] = {}


def _matches_approved_exemption(filename: str) -> BinaryApprovedExemption | None:
    """Return the first matching approved exemption for *filename*, or ``None``."""
    import fnmatch  # stdlib, deferred to keep module-level imports minimal

    basename = os.path.basename(filename).lower()
    for exemption in BINARY_APPROVED_EXEMPTIONS.values():
        if not exemption.approval_id:
            continue  # misconfigured exemption — skip rather than allow
        if fnmatch.fnmatch(basename, exemption.basename_pattern.lower()):
            return exemption
    return None


# ---------------------------------------------------------------------------
# Zip-slip guard
# ---------------------------------------------------------------------------


def _safe_extract_text(
    zf: zipfile.ZipFile,
    *,
    depth: int = 0,
    budget_bytes: list[int],
) -> str:
    """Extract printable text from all members of *zf*, recursively for nested ZIPs.

    Returns the concatenated text content of all safe, in-bounds members.
    Raises ``ValueError`` on:
      - a member whose normalized path escapes the extraction root (zip-slip)
      - exceeded ``EXTRACTION_MAX_BYTES`` budget
      - ``EXTRACTION_MAX_DEPTH`` exceeded

    All extraction failures are treated as block-worthy: the caller must catch
    ``ValueError`` and ``zipfile.BadZipFile`` and block rather than pass.

    Parameters
    ----------
    zf:
        Open ``ZipFile`` to extract from.
    depth:
        Current recursion depth. Starts at 0 for the outermost container.
    budget_bytes:
        Single-element list used as a mutable shared counter across recursive
        calls so the total extracted size is bounded globally.
    """
    if depth > EXTRACTION_MAX_DEPTH:
        raise ValueError(
            f"extraction depth {depth} exceeds EXTRACTION_MAX_DEPTH={EXTRACTION_MAX_DEPTH}"
        )

    texts: list[str] = []
    # Synthetic root prefix — every member path must start here after join+normpath.
    sentinel = os.path.abspath("/extraction_root")

    for info in zf.infolist():
        # Zip-slip check: normalize the member path against an absolute sentinel.
        member_path = os.path.normpath(os.path.join(sentinel, info.filename))
        if not member_path.startswith(sentinel + os.sep) and member_path != sentinel:
            raise ValueError(
                f"zip-slip detected: member '{info.filename}' escapes extraction root"
            )

        if info.is_dir():
            continue

        # Budget check before reading.
        if budget_bytes[0] + info.file_size > EXTRACTION_MAX_BYTES:
            raise ValueError(
                f"extraction size budget exceeded: {budget_bytes[0] + info.file_size} "
                f"> {EXTRACTION_MAX_BYTES} bytes"
            )

        raw = zf.read(info.filename)
        budget_bytes[0] += len(raw)

        lower_name = info.filename.lower()

        # Recurse into nested ZIP members (bounded by depth).
        if lower_name.endswith(".zip") and depth < EXTRACTION_MAX_DEPTH:
            try:
                nested_zf = zipfile.ZipFile(io.BytesIO(raw))
            except zipfile.BadZipFile as exc:
                raise ValueError(
                    f"malformed nested ZIP member '{info.filename}': {exc}"
                ) from exc
            texts.append(
                _safe_extract_text(
                    nested_zf, depth=depth + 1, budget_bytes=budget_bytes
                )
            )
            continue

        # Extract printable text from XML-based parts (Office Open XML stores
        # content in XML files inside the ZIP container).
        if lower_name.endswith((".xml", ".rels", ".vml", ".html", ".htm")):
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                text = raw.decode("latin-1", errors="replace")
            texts.append(text)
            continue

        # For other text-adjacent members, attempt decode.
        if any(
            lower_name.endswith(ext)
            for ext in (".txt", ".csv", ".json", ".yaml", ".yml")
        ):
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                text = raw.decode("latin-1", errors="replace")
            texts.append(text)
            continue

        # Binary members that are not containers or text — skip (don't scan raw binary
        # bytes as text, which would produce noise; the container scan is the gate here).

    return "\n".join(texts)


# ---------------------------------------------------------------------------
# Per-entry binary policy (Requirement 11 AC 14–17)
# ---------------------------------------------------------------------------


def scan_staged_binary(filename: str, content_bytes: bytes) -> str | None:
    """Scan staged binary *content_bytes* according to the per-entry binary policy.

    Returns a brief block-reason string iff the content should be blocked, or
    ``None`` if the content is clean (or an approved exemption applies).

    Per-entry policy (Requirement 11 AC 15):
    1. **BLOCK_SIZE**: files larger than ``BINARY_MAX_BYTES`` are blocked.
    2. **EXTRACT_SCAN**: PPTX / DOCX / XLSX / ZIP files are extracted (with
       zip-slip protection, recursion depth bound, and size budget) and the
       extracted text is passed through ``scan_for_secret``.  A malformed
       container, exceeded bounds, or zip-slip is a block (fail-closed).
    3. **SCAN_RAW** (text-adjacent extensions): attempt UTF-8 decode and scan.
    4. **APPROVED_EXEMPTION**: if the filename matches a registered exemption, the
       type-based block is bypassed (secret-pattern scan still runs on whatever
       text can be extracted).
    5. **BLOCK (unknown type)**: any binary not matched by the above policies is
       blocked unconditionally.  "Binary files differ" is never an accepted result
       (Requirement 11 AC 17).

    Parameters
    ----------
    filename:
        Path or basename hint for the staged file (used for extension dispatch
        and exemption matching). May be an empty string — falls through to the
        unknown-type block in that case.
    content_bytes:
        Raw file bytes as staged by Git.  Must not be empty; an empty bytes value
        is a clean pass (nothing to scan).
    """
    if not content_bytes:
        return None  # empty → nothing to block

    # 1. Block by size (before any extraction attempt).
    if len(content_bytes) > BINARY_MAX_BYTES:
        return (
            f"binary file exceeds maximum scan size "
            f"({len(content_bytes)} > {BINARY_MAX_BYTES} bytes): {filename!r}"
        )

    lower_name = (os.path.basename(filename) or "").lower()
    ext = os.path.splitext(lower_name)[1] if lower_name else ""

    # 2. Extractable container types (PPTX / DOCX / XLSX / ZIP).
    if ext in _EXTRACTABLE_EXTENSIONS:
        try:
            zf = zipfile.ZipFile(io.BytesIO(content_bytes))
        except zipfile.BadZipFile as exc:
            return f"malformed container '{filename}': {exc} — blocked (fail-closed)"
        try:
            budget: list[int] = [0]
            extracted_text = _safe_extract_text(zf, depth=0, budget_bytes=budget)
        except ValueError as exc:
            return str(exc)

        marker = scan_for_secret(extracted_text)
        if marker is not None:
            return f"secret detected in extracted container content: {marker}"
        return None  # clean container

    # 3. Text-adjacent extensions: decode and run the text scanner.
    if ext in _TEXT_EXTENSIONS:
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = content_bytes.decode("latin-1", errors="replace")
        return scan_for_secret(text)  # None or a marker

    # 4. Approved exemption — allows unknown-type binaries through IF explicitly
    #    registered. Secret-pattern scan is still attempted via raw-byte decode.
    exemption = _matches_approved_exemption(filename)
    if exemption is not None:
        # Best-effort text decode of raw bytes for pattern scan.
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = content_bytes.decode("latin-1", errors="replace")
        marker = scan_for_secret(text)
        if marker is not None:
            return (
                f"secret detected in approved-exemption binary (approval={exemption.approval_id!r}): "
                f"{marker}"
            )
        return None  # approved and clean

    # 5. Unknown binary type → BLOCK (fail-closed; Requirement 11 AC 15 default).
    return (
        f"unknown binary type blocked (fail-closed): "
        f"extension={ext!r}, filename={filename!r} — "
        "register an approved exemption to allow this file type"
    )


# ---------------------------------------------------------------------------
# Text scanner (unchanged public API)
# ---------------------------------------------------------------------------


def scan_for_secret(payload: str) -> str | None:
    """Return the matched-secret KIND (the pattern label) iff ``payload`` carries a secret.

    Returns ``None`` for a clean payload. Pure + stateless so it is unit-testable
    and reused by both the hook and any future pre_commit producer (P9). Matches the
    FIRST pattern that fires so the audit detail records a single deterministic kind.
    """
    if not payload:
        return None
    for pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(payload):
            if not _is_aws_doc_example(m.group(0)):
                return m.group(0)[:16]  # truncated marker (never log the full secret)
    return None


# AWS's published documentation credentials. An API spec derived from AWS docs
# carries them as "example" values (run 3976f8ce); they grant nothing. Only these
# exact values are exempt — any other key still blocks.
_AWS_DOC_EXAMPLES = frozenset({"AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"})
_QUOTED_VALUE = re.compile(r"['\"]([^'\"\s]+)['\"]$")


def _is_aws_doc_example(matched: str) -> bool:
    """True when a match is exactly one of the AWS doc examples (bare, or as the quoted value of an assignment)."""
    if matched in _AWS_DOC_EXAMPLES:
        return True
    quoted = _QUOTED_VALUE.search(matched)
    return quoted is not None and quoted.group(1) in _AWS_DOC_EXAMPLES


# ---------------------------------------------------------------------------
# Hook implementation
# ---------------------------------------------------------------------------


@register(
    "hook",
    "secret_scan",
    user_allowed=True,
    description="Blocking executable hook: scan agent output for secrets and halt on a hit.",
)
class SecretScanHook:
    """The ``secret_scan`` blocking executable hook (``name='secret_scan'``).

    Satisfies the ``HookHandler`` port structurally (``name`` + ``events`` +
    ``required_permission`` + ``async handle``). Bound to ``before_write`` /
    ``pre_commit``; ``required_permission='read_files'`` (HOOK-02). Returns ``block``
    iff the write payload carries a secret (text or binary), else ``continue`` — and
    writes a ``hook_runs`` row either way (HOOK-04).

    Binary payloads (Requirement 11 AC 14–17): when the fired event carries
    ``content_bytes`` (raw bytes) alongside the ``filename`` hint, the binary policy
    is applied via ``scan_staged_binary``.  When only a text payload is available,
    ``scan_for_secret`` runs as before.  "Binary files differ" is never an accepted
    result (Requirement 11 AC 17).
    """

    name = "secret_scan"
    events = ["before_write", "pre_commit"]
    required_permission = "read_files"

    async def handle(self, event: Any, ctx: Any) -> HookOutcome:
        """Block iff the firing event's write payload carries a secret (HOOK-01/04)."""
        event_name = _event_name(event)

        # Check for binary content first (Requirement 11 AC 14 — binary takes
        # priority over the text diff path).
        filename, content_bytes = _event_binary(event)
        if content_bytes is not None:
            reason = scan_staged_binary(filename, content_bytes)
            if reason is not None:
                detail = {
                    "matched": True,
                    # Never persist the full reason if it could contain file content
                    # — truncate to a safe diagnostic length.
                    "marker": reason[:120],
                    "binary": True,
                    "reason": "binary secret scan blocked staged content (Req 11 AC 14-17)",
                }
                await write_hook_run(ctx, self.name, event_name, HOOK_BLOCK, detail)
                return HookOutcome(outcome=HOOK_BLOCK, detail=detail)

            await write_hook_run(
                ctx,
                self.name,
                event_name,
                HOOK_CONTINUE,
                {"matched": False, "binary": True},
            )
            return HookOutcome(outcome=HOOK_CONTINUE)

        # Text payload path (D5 fix: real staged diff, not "").
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


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


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
        value = event.get("payload") or event.get("content") or event.get("text") or ""
    else:
        value = (
            getattr(event, "payload", None)
            or getattr(event, "content", None)
            or getattr(event, "text", None)
            or ""
        )
    return value if isinstance(value, str) else str(value)


def _event_binary(event: Any) -> tuple[str, bytes | None]:
    """Extract binary content and filename hint from the fired event.

    Returns ``(filename, content_bytes)`` when the event carries binary data, or
    ``(filename, None)`` when only text content is available. The filename hint is
    used by ``scan_staged_binary`` for extension-based policy dispatch; it may be
    an empty string when the event does not supply one.

    Binary data is expected under ``content_bytes`` / ``raw_bytes`` / ``file_bytes``
    on the event dict or object.  A value present but not a ``bytes`` instance is
    treated as absent (text-only event).
    """
    if isinstance(event, dict):
        raw = (
            event.get("content_bytes")
            or event.get("raw_bytes")
            or event.get("file_bytes")
        )
        filename = str(
            event.get("filename") or event.get("path") or event.get("name") or ""
        )
    else:
        raw = (
            getattr(event, "content_bytes", None)
            or getattr(event, "raw_bytes", None)
            or getattr(event, "file_bytes", None)
        )
        filename = str(
            getattr(event, "filename", None)
            or getattr(event, "path", None)
            or getattr(event, "name", None)
            or ""
        )

    if not isinstance(raw, bytes):
        return filename, None
    return filename, raw
