"""tests/agents/test_binary_scan.py — unit tests for scan_staged_binary (binary policy).

Tests for task 4.6 (sandbox-git-versioning-v2, Requirement 11 AC 14–17).

The binary policy matrix verified here:

1. PPTX with embedded secret is blocked (EXTRACT_SCAN → secret found).
2. Zip-slip member escaping the root is blocked (fail-closed).
3. File exceeding BINARY_MAX_BYTES is blocked (BLOCK_SIZE).
4. Unknown binary type (e.g. ``.exe``) is blocked unconditionally (BLOCK unknown).
5. Text-adjacent extension (``.env``) with a secret is caught (SCAN_RAW).
6. Clean PPTX (no secret) passes (EXTRACT_SCAN → clean).
7. Approved exemption bypasses the type block but the content scan still runs;
   a clean approved-exemption file passes while one with a secret is blocked.

All tests are pure Python (no filesystem, no git) — scan_staged_binary takes
raw bytes so the whole suite runs without a sandbox.

Requirements: 11
"""

from __future__ import annotations

import io
import zipfile

import pytest


# ---------------------------------------------------------------------------
# Helpers — build minimal in-memory binary payloads
# ---------------------------------------------------------------------------


def _make_pptx_bytes(xml_content: str) -> bytes:
    """Return a minimal valid PPTX (ZIP) with one slide XML part.

    PPTX is an Office Open XML container — a ZIP whose text-bearing members
    end in ``.xml``.  ``scan_staged_binary`` opens it as a ZIP and scans the
    extracted XML text, so we can embed a secret inside the XML body.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("ppt/slides/slide1.xml", xml_content)
        zf.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


def _make_zip_bytes(members: dict[str, bytes]) -> bytes:
    """Return a ZIP with the provided ``{member_name: content}`` mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_zipslip_bytes() -> bytes:
    """Return a ZIP containing a path-traversal member (zip-slip).

    The member path ``../../escape.txt`` escapes the extraction root and must
    trigger the zip-slip guard inside ``_safe_extract_text``.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        # zipfile allows writing arbitrary member names; the guard must catch it.
        info = zipfile.ZipInfo("../../escape.txt")
        zf.writestr(info, "innocent text")
    return buf.getvalue()


# A recognisable secret pattern: AWS access key id (AKIA + 16 uppercase alnum).
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"

# A recognisable OpenAI/Anthropic style key: sk- + 24+ alnum chars.
_SK_KEY = "sk-" + "B" * 24

# A clean XML fragment that contains no secret patterns.
_CLEAN_XML = "<p>Hello world, no secrets here.</p>"


# ---------------------------------------------------------------------------
# 1. PPTX with embedded secret → blocked
# ---------------------------------------------------------------------------


def test_pptx_with_embedded_secret_is_blocked() -> None:
    """A PPTX file whose XML body contains a secret must be blocked.

    scan_staged_binary extracts the ZIP members for PPTX files and runs the
    text scanner on the extracted XML.  The AWS access-key pattern embedded
    in the slide XML must trigger a block (EXTRACT_SCAN policy).

    Requirement 11 AC 14–15 (V2-Q12): binary container payloads are scanned
    by content; a container carrying a secret is blocked.
    """
    from agents.capabilities.hooks.secret_scan import scan_staged_binary

    pptx_bytes = _make_pptx_bytes(
        f"<Presentation><slide><p>key={_AWS_KEY}</p></slide></Presentation>"
    )
    reason = scan_staged_binary("report.pptx", pptx_bytes)

    assert (
        reason is not None
    ), "PPTX containing an AWS key in its XML must be blocked; got reason=None"
    assert (
        "secret" in reason.lower() or "detected" in reason.lower()
    ), f"Block reason must indicate a secret was detected; got: {reason!r}"


# ---------------------------------------------------------------------------
# 2. Zip-slip member → blocked (fail-closed)
# ---------------------------------------------------------------------------


def test_zipslip_member_is_blocked() -> None:
    """A ZIP with a path-traversal member must be blocked (fail-closed).

    The zip-slip guard in ``_safe_extract_text`` raises ValueError for any
    member whose normalised path escapes the extraction root.  scan_staged_binary
    must catch that and return a non-None reason string.

    Requirement 11 AC 16: malformed or path-escaping containers are blocked.
    """
    from agents.capabilities.hooks.secret_scan import scan_staged_binary

    slippy_bytes = _make_zipslip_bytes()
    # Use .zip extension to trigger the EXTRACT_SCAN path.
    reason = scan_staged_binary("archive.zip", slippy_bytes)

    assert (
        reason is not None
    ), "A ZIP with a zip-slip member must be blocked; got reason=None"
    assert (
        "zip-slip" in reason.lower() or "escape" in reason.lower()
    ), f"Block reason must mention zip-slip; got: {reason!r}"


# ---------------------------------------------------------------------------
# 3. File exceeding BINARY_MAX_BYTES → blocked by size
# ---------------------------------------------------------------------------


def test_oversized_binary_is_blocked() -> None:
    """A binary file larger than BINARY_MAX_BYTES must be blocked by size.

    The size check (BLOCK_SIZE policy) runs before any extraction attempt so
    even a well-formed container is refused when it is too large.

    Requirement 11 AC 15 (BLOCK_SIZE): oversized binaries are blocked to
    avoid unbounded memory.
    """
    from agents.capabilities.hooks.secret_scan import (
        BINARY_MAX_BYTES,
        scan_staged_binary,
    )

    # Construct a byte string one byte beyond the limit.
    oversized = b"\x00" * (BINARY_MAX_BYTES + 1)
    reason = scan_staged_binary("large.bin", oversized)

    assert reason is not None, (
        f"A file of {len(oversized)} bytes (>{BINARY_MAX_BYTES}) must be blocked; "
        "got reason=None"
    )
    assert (
        "exceeds" in reason.lower() or "maximum" in reason.lower()
    ), f"Block reason must mention size limit; got: {reason!r}"


# ---------------------------------------------------------------------------
# 4. Unknown binary type (.exe) → blocked unconditionally
# ---------------------------------------------------------------------------


def test_unknown_binary_type_is_blocked() -> None:
    """An unknown binary extension must be blocked unconditionally (fail-closed).

    'Binary files differ' is never an accepted outcome (Requirement 11 AC 17).
    Any file whose extension is not in the extractable or text-adjacent sets,
    and for which no approved exemption is registered, must be blocked.

    Requirement 11 AC 15 (BLOCK unknown): fail-closed default for unknown types.
    """
    from agents.capabilities.hooks.secret_scan import (
        BINARY_APPROVED_EXEMPTIONS,
        scan_staged_binary,
    )

    # Ensure the exemptions registry is empty for this file type.
    assert "exe-test" not in BINARY_APPROVED_EXEMPTIONS

    exe_bytes = b"\x4d\x5a" + b"\x00" * 100  # minimal MZ (PE) header bytes
    reason = scan_staged_binary("tool.exe", exe_bytes)

    assert (
        reason is not None
    ), "An .exe file must be blocked unconditionally; got reason=None"
    assert (
        "unknown" in reason.lower() or "blocked" in reason.lower()
    ), f"Block reason must indicate unknown type block; got: {reason!r}"


# ---------------------------------------------------------------------------
# 5. Text-adjacent .env with a secret → caught
# ---------------------------------------------------------------------------


def test_env_file_with_secret_is_caught() -> None:
    """A .env file (text-adjacent extension) containing a secret must be blocked.

    .env is in ``_TEXT_EXTENSIONS`` so scan_staged_binary decodes the bytes as
    UTF-8 and runs scan_for_secret on the result (SCAN_RAW policy).

    Requirement 11 AC 14 (binary policy matrix): text-adjacent extensions are
    decoded and scanned.
    """
    from agents.capabilities.hooks.secret_scan import scan_staged_binary

    env_content = (
        "DATABASE_URL=postgres://user:password@localhost/db\n"
        f"OPENAI_API_KEY={_SK_KEY}\n"
        "DEBUG=false\n"
    ).encode("utf-8")

    reason = scan_staged_binary(".env", env_content)

    assert (
        reason is not None
    ), ".env file containing an API key must be blocked; got reason=None"


# ---------------------------------------------------------------------------
# 6. Clean PPTX (no secret) → passes
# ---------------------------------------------------------------------------


def test_clean_pptx_passes() -> None:
    """A PPTX file with no secrets must pass the binary scan (reason is None).

    EXTRACT_SCAN runs on the container; a clean XML body must not trigger any
    secret pattern match.

    Requirement 11 AC 14–15: a clean binary container is allowed through.
    """
    from agents.capabilities.hooks.secret_scan import scan_staged_binary

    clean_pptx_bytes = _make_pptx_bytes(_CLEAN_XML)
    reason = scan_staged_binary("slides.pptx", clean_pptx_bytes)

    assert (
        reason is None
    ), f"A clean PPTX must pass the binary scan; got reason={reason!r}"


# ---------------------------------------------------------------------------
# 7. Approved exemption: type block is bypassed but content scan still runs
# ---------------------------------------------------------------------------


class TestApprovedExemption:
    """An approved exemption bypasses the unknown-type block but not the content scan.

    Requirement 11 AC 15 (APPROVED_EXEMPTION): a registered exemption allows an
    unknown-type binary through — but scan_for_secret still runs on the decoded
    bytes.  A clean approved-exemption file passes; one with a secret is blocked.
    """

    @pytest.fixture(autouse=True)
    def _register_and_cleanup(self):
        """Register a test exemption and remove it after the test."""
        from agents.capabilities.hooks.secret_scan import (
            BINARY_APPROVED_EXEMPTIONS,
            BinaryApprovedExemption,
        )

        exemption = BinaryApprovedExemption(
            basename_pattern="*.custom",
            approval_id="TEST-APPROVAL-001",
            reason="Test exemption for .custom files",
        )
        BINARY_APPROVED_EXEMPTIONS["TEST-APPROVAL-001"] = exemption
        yield
        BINARY_APPROVED_EXEMPTIONS.pop("TEST-APPROVAL-001", None)

    def test_approved_exemption_clean_file_passes(self) -> None:
        """A clean file matching the approved exemption must pass (reason=None).

        The type block is bypassed, and scan_for_secret on the decoded bytes
        finds no secret pattern.
        """
        from agents.capabilities.hooks.secret_scan import scan_staged_binary

        clean_bytes = b"just some proprietary binary data without secrets"
        reason = scan_staged_binary("model.custom", clean_bytes)

        assert (
            reason is None
        ), f"An approved-exemption file with no secrets must pass; got reason={reason!r}"

    def test_approved_exemption_file_with_secret_is_still_blocked(self) -> None:
        """A file matching the exemption but containing a secret must still be blocked.

        The exemption bypasses the 'unknown type → block' rule but does NOT bypass
        the secret-pattern scan.  A secret in the decoded bytes must trigger a block.

        Requirement 11 AC 15 (APPROVED_EXEMPTION): secret scan still runs on exempted
        files.
        """
        from agents.capabilities.hooks.secret_scan import scan_staged_binary

        secret_bytes = f"HEADER binary\napi_key = '{_SK_KEY}'\nEOF\n".encode("utf-8")
        reason = scan_staged_binary("model.custom", secret_bytes)

        assert reason is not None, (
            "An approved-exemption file containing a secret must still be blocked; "
            "got reason=None"
        )
        assert (
            "approval" in reason.lower() or "secret" in reason.lower()
        ), f"Block reason must mention secret detection in exempted file; got: {reason!r}"
