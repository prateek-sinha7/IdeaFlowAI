"""Unit tests for the prototype-revision prompt helpers.

Covers the existing-artifact extraction + message-slimming used by the in-place
revision seed: how the prior artifact is extracted from a revision request and the
prompt is trimmed down to a file-pointer (the artifact is seeded into the run
sandbox under ``deliverable.name`` and the agent edits it there).

SOURCE-OF-TRUTH NOTE (07-10 / CR-06 relocation)
-----------------------------------------------
These helpers previously lived on ``ExecutionEngine`` as
``_extract_existing_prototype_html`` / ``_slim_revision_message`` (kernel-resident,
the self-described "DELIBERATE EXCEPTION"). 07-10 moved the in-place-revision seed
OUT of the kernel into the ``previous_run`` context provider — the SINGLE home for
this behavior (no dual implementation). The helpers are now module-level functions
in ``agents.capabilities.context_providers.previous_run``, parameterized by the
declared ``deliverable.name`` (NOT a hardcoded ``REVISION_FILE_NAME`` const). The
LIVE behavior tests below are retained, re-pointed at the new home.

A prior Phase-7a rewrite also dropped a dead ``TestEditFile`` block exercising the
removed in-memory ``AgentWorkspace.edit_file`` — revisions now edit the artifact on
the per-run disk sandbox via the native ``deepagents`` ``edit_file`` tool.
"""

from __future__ import annotations

from agents.capabilities.context_providers.previous_run import (
    _extract_existing_artifact,
    _extract_revision_instruction,
    _slim_revision_message,
)

_MSG = (
    "=== EXISTING PROTOTYPE HTML ===\n"
    "<!doctype html><html><body>hi</body></html>\n"
    "=== END EXISTING HTML ===\n\n"
    "=== REVISION REQUEST ===\n"
    "make the New Claim button work\n"
    "=== END REQUEST ==="
)


class TestRevisionSeedHelpers:
    def test_extract_existing_artifact(self):
        html = _extract_existing_artifact(_MSG)
        assert html == "<!doctype html><html><body>hi</body></html>"

    def test_extract_returns_empty_when_markers_absent(self):
        assert _extract_existing_artifact("just an instruction") == ""

    def test_extract_revision_instruction(self):
        assert _extract_revision_instruction(_MSG) == "make the New Claim button work"

    def test_extract_instruction_returns_none_when_absent(self):
        assert _extract_revision_instruction("no markers here") is None

    def test_slim_drops_html_keeps_request_adds_pointer(self):
        # Parameterized by deliverable.name (no hardcoded const).
        artifact_name = "prototype.html"
        slim = _slim_revision_message(_MSG, artifact_name)
        assert "<!doctype" not in slim                 # large HTML payload removed
        assert artifact_name in slim                   # pointer to the workspace file
        assert "make the New Claim button work" in slim  # instruction preserved
        assert "REVISION REQUEST" in slim              # title-extraction marker preserved

    def test_slim_pointer_uses_the_declared_filename(self):
        slim = _slim_revision_message(_MSG, "deck.html")
        assert "deck.html" in slim
        assert "prototype.html" not in slim
