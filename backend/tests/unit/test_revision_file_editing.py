"""Unit tests for the direct-file-editing prototype revision flow.

Covers the two pieces that replaced the legacy REVISION_DIFF regex-merge:
  1. AgentWorkspace.edit_file — the surgical str_replace primitive the
     prototype-revision-agent uses to edit prototype.html in place.
  2. ExecutionEngine._extract_existing_prototype_html / _slim_revision_message —
     how the engine seeds the workspace and trims the prompt.
"""

from __future__ import annotations

from app.agents.tools.workspace import AgentWorkspace, make_workspace_tools


# ---------------------------------------------------------------------------
# edit_file — surgical, exact, unique, self-correcting
# ---------------------------------------------------------------------------


class TestEditFile:
    def test_workspace_toolset_exposes_edit_file(self):
        ws = AgentWorkspace()
        names = {t.name for t in make_workspace_tools(ws)}
        assert names == {"write_file", "read_file", "edit_file", "list_workspace_files"}

    def test_surgical_replace_changes_only_the_target(self):
        ws = AgentWorkspace()
        ws.write_file("p.html", "<a>one</a><b>keep</b><a>two</a>")
        result = ws.edit_file("p.html", "<a>one</a>", "<a>ONE</a>")
        assert "✓ Edited" in result
        assert ws.read_file("p.html") == "<a>ONE</a><b>keep</b><a>two</a>"

    def test_missing_file_returns_actionable_error(self):
        ws = AgentWorkspace()
        result = ws.edit_file("nope.html", "x", "y")
        assert "File not found" in result

    def test_no_match_returns_actionable_error_and_no_change(self):
        ws = AgentWorkspace()
        ws.write_file("p.html", "hello world")
        result = ws.edit_file("p.html", "ABSENT", "z")
        assert "not found" in result
        assert ws.read_file("p.html") == "hello world"  # unchanged

    def test_non_unique_match_refuses_and_no_change(self):
        ws = AgentWorkspace()
        ws.write_file("p.html", "<li>x</li><li>x</li>")
        result = ws.edit_file("p.html", "<li>x</li>", "<li>y</li>")
        assert "not unique" in result
        assert "2 occurrences" in result
        assert ws.read_file("p.html") == "<li>x</li><li>x</li>"  # unchanged

    def test_identical_strings_is_a_noop(self):
        ws = AgentWorkspace()
        ws.write_file("p.html", "same")
        result = ws.edit_file("p.html", "same", "same")
        assert "No change" in result

    def test_insert_near_anchor_via_context(self):
        """The agent inserts a route by including the anchor in both strings."""
        ws = AgentWorkspace()
        ws.write_file("p.html", "const routes = {'/a': 'a'};")
        ws.edit_file(
            "p.html",
            "const routes = {'/a': 'a'",
            "const routes = {'/a': 'a', '/b': 'b'",
        )
        assert ws.read_file("p.html") == "const routes = {'/a': 'a', '/b': 'b'};"


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
