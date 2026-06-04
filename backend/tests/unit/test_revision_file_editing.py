"""Unit tests for the engine-side prototype revision prompt helpers.

Covers ``ExecutionEngine._extract_existing_prototype_html`` /
``_slim_revision_message`` — how the engine extracts the inlined original HTML
from a revision request and trims the prompt down to a file-pointer (the HTML is
seeded into the run sandbox as ``prototype.html`` and the agent edits it there).

SOURCE-OF-TRUTH NOTE (Phase 7a rewrite)
---------------------------------------
This file previously also had a ``TestEditFile`` block exercising
``AgentWorkspace.edit_file`` (the surgical str_replace primitive). The in-memory
``AgentWorkspace`` (``app/agents/tools/workspace.py``) is dead pipeline-legacy
removed in Phase 7a — revisions now edit ``prototype.html`` on the per-run disk
sandbox via the native ``deepagents`` ``edit_file`` tool. That dead block (and
its ``AgentWorkspace`` / ``make_workspace_tools`` import) was dropped. The LIVE
engine helper tests below are retained unchanged.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Engine revision helpers
# ---------------------------------------------------------------------------

_MSG = (
    "=== EXISTING PROTOTYPE HTML ===\n"
    "<!doctype html><html><body>hi</body></html>\n"
    "=== END EXISTING HTML ===\n\n"
    "=== REVISION REQUEST ===\n"
    "make the New Claim button work\n"
    "=== END REQUEST ==="
)


class TestEngineRevisionHelpers:
    def _engine_cls(self):
        from agents.execution_engine.engine import ExecutionEngine
        return ExecutionEngine

    def test_extract_existing_html(self):
        Eng = self._engine_cls()
        html = Eng._extract_existing_prototype_html(_MSG)
        assert html == "<!doctype html><html><body>hi</body></html>"

    def test_extract_returns_empty_when_markers_absent(self):
        Eng = self._engine_cls()
        assert Eng._extract_existing_prototype_html("just an instruction") == ""

    def test_slim_drops_html_keeps_request_adds_pointer(self):
        from agents.execution_engine.engine import REVISION_FILE_NAME
        Eng = self._engine_cls()
        slim = Eng._slim_revision_message(_MSG)
        assert "<!doctype" not in slim                 # large HTML payload removed
        assert REVISION_FILE_NAME in slim              # pointer to the workspace file
        assert "make the New Claim button work" in slim  # instruction preserved
        assert "REVISION REQUEST" in slim              # title-extraction marker preserved
