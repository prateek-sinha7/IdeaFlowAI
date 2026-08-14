"""Unit tests for FIX-218 (KAN-170): chat file attachment content injection.

Tests cover:
1. _build_attached_files_block — the helper that renders file content entries
   into a formatted text block for the Concierge system prompt / steering note.
2. _ConciergeCtx.attached_files — the new ctx field is populated correctly.
3. concierge._compose_system_prompt — the ## Attached files block is injected.
4. MessageCommand.file_contents — the new field parses correctly.
5. Safety boundary — absent/empty file_contents is dormant (byte-identical).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. _build_attached_files_block helper
# ---------------------------------------------------------------------------
class TestBuildAttachedFilesBlock:
    """Unit tests for FIX-218: _build_attached_files_block helper."""

    def _fn(self, file_contents):
        from app.api.run_commands import _build_attached_files_block
        return _build_attached_files_block(file_contents)

    def test_fix218_none_returns_empty(self):
        """FIX-218 regression baseline: None file_contents → '' (dormant/INV-3)."""
        assert self._fn(None) == ""

    def test_fix218_empty_list_returns_empty(self):
        """FIX-218 regression baseline: empty list → '' (dormant/INV-3)."""
        assert self._fn([]) == ""

    def test_fix218_single_text_file(self):
        """FIX-218 happy path: a single text file's content is rendered correctly."""
        block = self._fn([{"name": "blockchain.txt", "text": "Blockchain is a ledger."}])
        assert "=== ATTACHED FILE: blockchain.txt ===" in block
        assert "Blockchain is a ledger." in block
        assert "=== END FILE ===" in block

    def test_fix218_truncated_marker_present(self):
        """FIX-218 edge case: text longer than _ATTACHED_FILE_TEXT_CAP gets truncation note."""
        from app.api.run_commands import _ATTACHED_FILE_TEXT_CAP
        long_text = "A" * (_ATTACHED_FILE_TEXT_CAP + 10)
        block = self._fn([{"name": "big.txt", "text": long_text}])
        assert "[Content truncated" in block
        # Block must NOT contain more than the cap + some overhead
        assert len(block) < _ATTACHED_FILE_TEXT_CAP + 300

    def test_fix218_extraction_error_included(self):
        """FIX-218 error surfacing: extraction error is included in the block."""
        block = self._fn([{"name": "encrypted.pdf", "text": "", "error": "Could not parse PDF"}])
        assert "encrypted.pdf" in block
        assert "Could not parse PDF" in block
        assert "[Extraction error:" in block

    def test_fix218_multiple_files(self):
        """FIX-218 edge case: multiple files are each rendered as separate blocks."""
        block = self._fn([
            {"name": "file1.txt", "text": "content one"},
            {"name": "file2.md", "text": "content two"},
        ])
        assert "file1.txt" in block
        assert "content one" in block
        assert "file2.md" in block
        assert "content two" in block

    def test_fix218_non_dict_entry_skipped(self):
        """FIX-218 safety boundary: non-dict entries in file_contents are skipped."""
        block = self._fn([None, "not-a-dict", {"name": "good.txt", "text": "ok"}])
        assert "good.txt" in block
        assert "ok" in block

    def test_fix218_filename_capped(self):
        """FIX-218 edge case: very long filename is truncated to 200 chars."""
        long_name = "x" * 250 + ".txt"
        block = self._fn([{"name": long_name, "text": "hi"}])
        assert "=== ATTACHED FILE:" in block
        # The name in the block should be at most 200 chars (plus .txt truncation)
        lines = block.split("\n")
        header = lines[0]
        # "=== ATTACHED FILE: " is 20 chars prefix, then name (capped), then " ==="
        name_in_header = header[len("=== ATTACHED FILE: "):-len(" ===")]
        assert len(name_in_header) <= 200


# ---------------------------------------------------------------------------
# 2. _ConciergeCtx.attached_files field
# ---------------------------------------------------------------------------
class TestConciergeCtxAttachedFilesField:
    """Unit tests for FIX-218: _ConciergeCtx.attached_files field."""

    def _make_ctx(self, **kwargs):
        from app.api.run_commands import _ConciergeCtx
        # Minimal required args; everything else defaults.
        return _ConciergeCtx(
            run_id="run-1",
            scoped_store=None,
            owner_id="owner-1",
            workspace_id=None,
            **kwargs,
        )

    def test_fix218_absent_defaults_to_empty_string(self):
        """FIX-218 regression baseline: attached_files absent → '' (dormant)."""
        ctx = self._make_ctx()
        assert ctx.attached_files == ""

    def test_fix218_none_defaults_to_empty_string(self):
        """FIX-218 edge case: attached_files=None → '' (degrade-safe)."""
        ctx = self._make_ctx(attached_files=None)
        assert ctx.attached_files == ""

    def test_fix218_attached_files_stored_correctly(self):
        """FIX-218 happy path: attached_files is stored and readable."""
        block = "=== ATTACHED FILE: test.txt ===\nhello\n=== END FILE ==="
        ctx = self._make_ctx(attached_files=block)
        assert ctx.attached_files == block

    def test_fix218_other_fields_unchanged(self):
        """FIX-218 safety boundary: pre-existing ctx fields are not affected."""
        ctx = self._make_ctx(run_summary="summary text", open_gate="review", attached_files="file block")
        assert ctx.run_summary == "summary text"
        assert ctx.open_gate == "review"
        assert ctx.attached_files == "file block"


# ---------------------------------------------------------------------------
# 3. Concierge _compose_system_prompt — ## Attached files block injection
# ---------------------------------------------------------------------------
class TestConciergeComposeSystemPromptAttachedFiles:
    """Unit tests for FIX-218: _compose_system_prompt injects attached_files block."""

    def _compose(self, attached_files: str = "", **ctx_kwargs):
        from app.api.run_commands import _ConciergeCtx
        from app.agents.chat.concierge import ConciergeCapability
        ctx = _ConciergeCtx(
            run_id="run-1",
            scoped_store=None,
            owner_id="owner-1",
            workspace_id=None,
            attached_files=attached_files,
            **ctx_kwargs,
        )
        return ConciergeCapability._compose_system_prompt(ctx)

    def test_fix218_no_files_no_block(self):
        """FIX-218 regression baseline: no attached_files → no ## Attached files block."""
        prompt = self._compose(attached_files="")
        assert "## Attached files" not in prompt

    def test_fix218_attached_files_injected(self):
        """FIX-218 happy path: attached_files block is injected into system prompt."""
        block = "=== ATTACHED FILE: blockchain.txt ===\nBlockchain content\n=== END FILE ==="
        prompt = self._compose(attached_files=block)
        assert "PRIORITY OVERRIDE — File attached this turn" in prompt
        assert "blockchain.txt" in prompt
        assert "Blockchain content" in prompt

    def test_fix218_extraction_error_in_prompt(self):
        """FIX-218 error surfacing: extraction error propagates to Concierge prompt."""
        block = "=== ATTACHED FILE: bad.pdf ===\n[Extraction error: encrypted PDF]\n=== END FILE ==="
        prompt = self._compose(attached_files=block)
        assert "PRIORITY OVERRIDE — File attached this turn" in prompt
        assert "Extraction error" in prompt

    def test_fix218_injection_guidance_present(self):
        """FIX-218 happy path: prompt includes injection guidance for propose_steering_note."""
        block = "=== ATTACHED FILE: spec.txt ===\ncontent\n=== END FILE ==="
        prompt = self._compose(attached_files=block)
        assert "propose_steering_note" in prompt

    def test_fix218_other_prompt_sections_unchanged(self):
        """FIX-218 safety boundary: pre-existing prompt sections are not affected."""
        prompt_with = self._compose(attached_files="=== ATTACHED FILE: f.txt ===\nhi\n=== END FILE ===")
        prompt_without = self._compose(attached_files="")
        # The role + RESPONSE RULES section must be in both
        assert "VelocityAI's run assistant" in prompt_with
        assert "VelocityAI's run assistant" in prompt_without
        # chain_hints block only appears when chain_hints are set — both absent → no block
        assert "## Available follow-up workflows" not in prompt_with
        assert "## Available follow-up workflows" not in prompt_without


# ---------------------------------------------------------------------------
# 4. MessageCommand.file_contents field
# ---------------------------------------------------------------------------
class TestMessageCommandFileContentsField:
    """Unit tests for FIX-218: MessageCommand.file_contents field parses correctly."""

    def _parse(self, body_dict: dict):
        from app.api.run_commands import MessageCommand
        return MessageCommand(**body_dict)

    def test_fix218_absent_defaults_to_none(self):
        """FIX-218 regression baseline: file_contents absent → None (dormant/INV-3)."""
        cmd = self._parse({"message_id": "m1", "text": "hello"})
        assert cmd.file_contents is None

    def test_fix218_parses_file_contents_list(self):
        """FIX-218 happy path: file_contents with valid entries parses correctly."""
        cmd = self._parse({
            "message_id": "m1",
            "text": "use this file",
            "file_contents": [{"name": "blockchain.txt", "text": "content", "truncated": False}],
        })
        assert cmd.file_contents is not None
        assert len(cmd.file_contents) == 1
        assert cmd.file_contents[0]["name"] == "blockchain.txt"
        assert cmd.file_contents[0]["text"] == "content"

    def test_fix218_file_contents_with_error(self):
        """FIX-218 edge case: file_contents entry with extraction error field."""
        cmd = self._parse({
            "message_id": "m1",
            "text": "file failed",
            "file_contents": [{"name": "bad.pdf", "text": "", "error": "Could not extract"}],
        })
        assert cmd.file_contents[0]["error"] == "Could not extract"

    def test_fix218_existing_fields_unaffected(self):
        """FIX-218 safety boundary: adding file_contents does not break existing fields."""
        cmd = self._parse({
            "message_id": "m1",
            "text": "hello",
            "concierge": True,
            "chain_hints": [{"id": "ppt", "label": "Presentation"}],
            "file_contents": [{"name": "f.txt", "text": "data"}],
        })
        assert cmd.text == "hello"
        assert cmd.concierge is True
        assert cmd.chain_hints == [{"id": "ppt", "label": "Presentation"}]
        assert cmd.file_contents[0]["name"] == "f.txt"


# ---------------------------------------------------------------------------
# 5. _build_attached_files_block used in CHANNEL_STEERING path (safety boundary)
# ---------------------------------------------------------------------------
class TestBuildAttachedFilesBlockSteering:
    """FIX-218 safety boundary: CHANNEL_STEERING path injection is dormant when no files."""

    def test_fix218_no_files_no_steering_note(self):
        """FIX-218 regression baseline: absent file_contents produces empty block (no-op steering)."""
        from app.api.run_commands import _build_attached_files_block
        block = _build_attached_files_block(None)
        # An empty block must not be passed to apply_steering (the caller guards on bool(block))
        assert not bool(block)

    def test_fix218_empty_list_no_steering_note(self):
        """FIX-218 regression baseline: empty file_contents list produces empty block."""
        from app.api.run_commands import _build_attached_files_block
        block = _build_attached_files_block([])
        assert not bool(block)

    def test_fix218_error_only_entry_still_produces_block(self):
        """FIX-218 edge case: an error-only entry still produces a non-empty block
        (so Concierge can inform user of the extraction failure)."""
        from app.api.run_commands import _build_attached_files_block
        block = _build_attached_files_block([{"name": "bad.pdf", "text": "", "error": "encrypted"}])
        # The error entry should produce content so the Concierge can tell the user
        assert bool(block)
        assert "encrypted" in block
