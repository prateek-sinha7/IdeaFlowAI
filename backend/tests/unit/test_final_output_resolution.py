"""Deliverable resolution — ``_resolve_final_output`` by pipeline class.

WHAT THIS PROVES
----------------
The engine's final ``WorkflowRun.output`` is resolved by *pipeline class*, not by
blindly serializing every file on the run sandbox:

  * prototype / od_prototype / revision → the single ``prototype.html`` on disk,
  * code-gen (app_builder/mulesoft/dotnet) → ``serialize_sandbox_deliverable``,
  * text / PPT → the last streamed output (``<artifact>`` wrapper unwrapped).

REGRESSION GUARD (run bddadbfb)
-------------------------------
The prototype build loop writes ``spec.md`` / ``design.md`` / ``tasks.md`` into
the SAME sandbox as build-agent reference scaffolding. The OLD logic took the
code-gen path for prototype (``count_sandbox_deliverables > 0`` because of those
files), serialized ALL of them into one ~248 KB blob, then an ``<artifact>``
*example* printed inside ``design.md`` got extracted by an artifact-stripper —
yielding a ~125-char fragment instead of the real ~66 KB prototype. These tests
pin the corrected behavior: the prototype's deliverable is its ``prototype.html``,
the scaffolding never leaks, and ``<artifact>`` text inside any file is never
mis-extracted (for prototype OR code-gen).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.execution_engine.engine import _resolve_final_output, _unwrap_artifact
from app.agents.sandbox import RunSandbox, serialize_sandbox_deliverable

# A recognizable, sizable prototype — clearly distinct from the <artifact> example
# the reference files carry, so a mis-extraction would be obvious.
PROTOTYPE_HTML = (
    "<!doctype html>\n<html>\n<head><title>Real Prototype</title></head>\n<body>\n"
    + "".join(
        f"<section data-page='page{i}'>Full content for page {i}</section>\n"
        for i in range(40)
    )
    + "</body>\n</html>\n"
)

# design.md as the engine seeds it from the template SKILL.md: it carries an
# <artifact> EXAMPLE in an output-contract section — the exact bug trigger.
DESIGN_MD_WITH_ARTIFACT_EXAMPLE = (
    "# Template SKILL\n\n"
    "## Output contract\n\n"
    "Emit between `<artifact>` tags:\n\n"
    "```\n"
    '<artifact identifier="dashboard-slug" type="text/html" title="Dashboard">\n'
    "<!doctype html><html><body>EXAMPLE ONLY — NOT THE DELIVERABLE</body></html>\n"
    "</artifact>\n"
    "```\n\n"
    "Use the classes .section .container .grid-3.\n"
)

SPEC_MD = "# Spec\n\nBuild a dashboard. Emit between `<artifact>` tags as shown.\n"
TASKS_MD = "## Task 1: Shell\n## Task 2: Dashboard\n## Task 3: Validation\n"


def _sandbox(tmp_path: Path, files: dict[str, str]) -> RunSandbox:
    """Build a RunSandbox rooted under ``tmp_path`` and write ``files`` into it."""
    sb = RunSandbox("u", "r", runs_root=str(tmp_path))
    sb.ensure()
    for name, content in files.items():
        sb.write(name, content)
    return sb


# ---------------------------------------------------------------------------
# Prototype (forward build) — the core regression
# ---------------------------------------------------------------------------


def test_prototype_returns_prototype_html_not_serialized_bundle(tmp_path):
    """prototype with the full reference scaffolding present → prototype.html."""
    sb = _sandbox(
        tmp_path,
        {
            "prototype.html": PROTOTYPE_HTML,
            "spec.md": SPEC_MD,
            "design.md": DESIGN_MD_WITH_ARTIFACT_EXAMPLE,
            "tasks.md": TASKS_MD,
        },
    )

    out = _resolve_final_output("prototype", sb, [{"output": "✓ build complete"}])

    # The deliverable is exactly the prototype HTML — byte-for-byte.
    assert out == PROTOTYPE_HTML
    # NOT the serialized multi-file bundle, and no reference file leaked in.
    assert "```filename:" not in out
    assert "design.md" not in out and "spec.md" not in out
    # The exact run-bddadbfb failure: the design.md <artifact> example is NOT it.
    assert "EXAMPLE ONLY" not in out

    # And prove the OLD path WOULD have gone wrong: the serialized bundle both
    # contains the <artifact> trigger and is a different (longer) string.
    serialized = serialize_sandbox_deliverable(sb.root)
    assert "<artifact" in serialized
    assert out != serialized
    assert len(serialized) > len(out)


def test_od_prototype_resolves_like_prototype(tmp_path):
    """``od_prototype`` (NDJSON-adapter path) resolves to prototype.html too."""
    sb = _sandbox(
        tmp_path,
        {"prototype.html": PROTOTYPE_HTML, "spec.md": SPEC_MD, "design.md": DESIGN_MD_WITH_ARTIFACT_EXAMPLE},
    )
    assert _resolve_final_output("od_prototype", sb, [{"output": "c"}]) == PROTOTYPE_HTML


def test_prototype_html_with_literal_artifact_text_is_returned_verbatim(tmp_path):
    """Even if the prototype HTML itself contains ``<artifact>``, it is NOT stripped."""
    html = (
        "<!doctype html><html><body>"
        "<pre>docs mention &lt;artifact&gt;</pre>"
        "<artifact>do not strip me</artifact>"
        "</body></html>"
    )
    sb = _sandbox(tmp_path, {"prototype.html": html})
    assert _resolve_final_output("prototype", sb, []) == html


def test_prototype_missing_html_falls_back_to_streamed_not_serialize(tmp_path):
    """No prototype.html but scaffolding present (count>0) → streamed, never serialize."""
    sb = _sandbox(
        tmp_path,
        {"spec.md": SPEC_MD, "design.md": DESIGN_MD_WITH_ARTIFACT_EXAMPLE, "tasks.md": TASKS_MD},
    )
    out = _resolve_final_output("prototype", sb, [{"output": "build-agent confirmation text"}])
    assert out == "build-agent confirmation text"
    assert "```filename:" not in out
    assert "EXAMPLE ONLY" not in out


# ---------------------------------------------------------------------------
# Code-gen — serialize, and DON'T strip <artifact> text out of files
# ---------------------------------------------------------------------------


def test_codegen_serializes_all_deliverable_files(tmp_path):
    sb = _sandbox(tmp_path, {"src/app.py": "print('hi')\n", "README.md": "# App\n"})
    out = _resolve_final_output("app_builder", sb, [{"output": "ignored"}])
    assert out == serialize_sandbox_deliverable(sb.root)
    assert "```filename: README.md" in out
    assert "```filename: src/app.py" in out


def test_codegen_file_containing_artifact_text_is_not_stripped(tmp_path):
    """A code-gen deliverable containing literal ``<artifact>…</artifact>`` survives."""
    sb = _sandbox(
        tmp_path,
        {
            "docs/guide.md": "Wrap output: <artifact>SHOULD NOT BECOME THE DELIVERABLE</artifact>\n",
            "main.py": "x = 1\n",
        },
    )
    out = _resolve_final_output("app_builder", sb, [])
    assert out == serialize_sandbox_deliverable(sb.root)
    assert "main.py" in out  # the FULL bundle, not just the artifact fragment
    assert out != "SHOULD NOT BECOME THE DELIVERABLE"


# ---------------------------------------------------------------------------
# Text / PPT — streamed output, with <artifact> unwrap
# ---------------------------------------------------------------------------


def test_text_pipeline_returns_streamed_output(tmp_path):
    sb = _sandbox(tmp_path, {})
    out = _resolve_final_output("user_stories", sb, [{"output": "## Backlog\n- Story 1\n"}])
    assert out == "## Backlog\n- Story 1\n"


def test_text_pipeline_empty_results_returns_empty(tmp_path):
    sb = _sandbox(tmp_path, {})
    assert _resolve_final_output("user_stories", sb, []) == ""


def test_ppt_unwraps_artifact_wrapper(tmp_path):
    sb = _sandbox(tmp_path, {})
    deck = "<!doctype html><html><body>DECK</body></html>"
    streamed = f'Here is the deck:\n<artifact identifier="deck" type="text/html">{deck}</artifact>\nDone.'
    assert _resolve_final_output("od_ppt", sb, [{"output": streamed}]) == deck


# ---------------------------------------------------------------------------
# Prototype revision — prototype.html with original-HTML fallback
# ---------------------------------------------------------------------------


def test_revision_returns_prototype_html(tmp_path):
    sb = _sandbox(tmp_path, {"prototype.html": PROTOTYPE_HTML})
    assert (
        _resolve_final_output("prototype_revision", sb, [{"output": "c"}]) == PROTOTYPE_HTML
    )


def test_revision_missing_file_uses_streamed_html(tmp_path):
    sb = _sandbox(tmp_path, {})
    html = "<!doctype html><html><body>streamed revision</body></html>"
    out = _resolve_final_output(
        "prototype_revision", sb, [{"output": html}], revision_original_html="<html>ORIG</html>"
    )
    assert out == html


def test_revision_missing_file_non_html_uses_original(tmp_path):
    sb = _sandbox(tmp_path, {})
    out = _resolve_final_output(
        "prototype_revision",
        sb,
        [{"output": "I have edited the file."}],
        revision_original_html="<html>ORIG</html>",
    )
    assert out == "<html>ORIG</html>"


# ---------------------------------------------------------------------------
# _unwrap_artifact (the small reusable helper)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ('<artifact id="x">inner</artifact>', "inner"),
        ("pre <artifact>A</artifact> post", "A"),
        ("<artifact>multi\nline\ncontent</artifact>", "multi\nline\ncontent"),
        ("no wrapper here", "no wrapper here"),
        ("", ""),
        # A serialized bundle / raw HTML with no closing tag is left untouched.
        ("```filename: a.py\n<artifact incomplete\n```", "```filename: a.py\n<artifact incomplete\n```"),
    ],
)
def test_unwrap_artifact(text, expected):
    assert _unwrap_artifact(text) == expected
