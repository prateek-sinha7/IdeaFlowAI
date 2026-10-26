"""tests/integration/api/test_figma_ingestor_sandbox_v2.py

Phase 6 integration tests: after the Design Ingestor AGENT.md update,
new output files must appear in context/design/ and must have improved quality.

Uses tmp_path for real file I/O via a duck-typed sandbox. No LLM required —
these tests verify the CONTRACT of what the updated agent should write,
not that the agent actually runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_INGESTOR_MD = _BACKEND / "agents" / "prompts" / "design-ingestor" / "AGENT.md"


def _make_disk_sandbox(tmp_path: Path) -> Any:
    """Duck-typed sandbox backed by real files."""

    class _DiskSandbox:
        root = tmp_path

        def write(self, relpath: str, content: str) -> None:
            full = tmp_path / relpath
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        def read(self, relpath: str) -> str | None:
            full = tmp_path / relpath
            return full.read_text(encoding="utf-8") if full.is_file() else None

        def list_files(self):
            entries = []
            for p in tmp_path.rglob("*"):
                if p.is_file():
                    rel = str(p.relative_to(tmp_path)).replace("\\", "/")
                    entries.append({"path": f"./{rel}"})
            return entries, {}

    return _DiskSandbox()


# ── AGENT.md contract tests (Phase 6 readiness checks) ───────────────────────


@pytest.mark.integration
def test_agent_md_mentions_observations_json() -> None:
    """After Phase 6, AGENT.md must write observations.json (new structured format)."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert (
        "observations.json" in content
    ), "AGENT.md must reference observations.json — Phase 6 adds this structured output"


@pytest.mark.integration
def test_agent_md_mentions_exec_figma_extract() -> None:
    """After Phase 6, AGENT.md must instruct agent to exec figma_extract.py."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert (
        "figma_extract.py" in content
    ), "AGENT.md must reference figma_extract.py script — added in Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_exec_make_ds() -> None:
    """After Phase 6, AGENT.md must instruct agent to exec make_ds.py."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert (
        "make_ds.py" in content
    ), "AGENT.md must reference make_ds.py script — added in Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_exec_figma_to_html() -> None:
    """After Phase 6, AGENT.md must instruct agent to exec figma_to_html.py."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert (
        "figma_to_html.py" in content
    ), "AGENT.md must reference figma_to_html.py script — added in Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_tokens_css_output() -> None:
    """After Phase 6, AGENT.md must reference tokens.css as an output file."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert (
        "tokens.css" in content
    ), "AGENT.md must reference tokens.css — new output file after Phase 6"


@pytest.mark.integration
def test_agent_md_mentions_components_html_output() -> None:
    """After Phase 6, AGENT.md must reference components.html as an output file."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    assert (
        "components.html" in content
    ), "AGENT.md must reference components.html — new output file after Phase 6"


@pytest.mark.integration
def test_agent_md_design_system_md_has_9_section_structure() -> None:
    """After Phase 6, AGENT.md must instruct the agent to write 9-section DESIGN.md."""
    content = _INGESTOR_MD.read_text(encoding="utf-8")
    # The 3 required section headings from reference/design-md.md
    required_sections = ["Visual Theme", "Color Palette", "Typography"]
    for section in required_sections:
        assert (
            section in content
        ), f"AGENT.md must instruct agent to write '{section}' section in DESIGN.md format"


# ── Sandbox output contract tests ─────────────────────────────────────────────
# These simulate what an updated ingestor should write and verify the contract.


@pytest.mark.integration
def test_tokens_css_written_to_context_design(tmp_path) -> None:
    """After Phase 6, tokens.css must be findable via rebuild_od_context_from_sandbox."""
    from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    sandbox.write(
        ".context/selections.json",
        json.dumps(
            {
                "template_id": "custom-figma",
                "ds_id": "derived",
                "source_type": "figma",
                "figma_frame_count": 2,
                "no_template": False,
                "is_design_system_required": None,
            }
        ),
    )
    sandbox.write(
        "context/design/tokens.css",
        ":root {\n  --bg: #13151f;\n  --accent: #5b5fef;\n}",
    )
    sandbox.write(
        "context/design/design-system.md",
        "# Design System Inspired by SaaS App\n\n## 1. Visual Theme\n",
    )

    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    ds_files = rebuilt.get("ds_files", {})
    assert (
        "tokens.css" in ds_files
    ), "rebuild must pick up tokens.css from context/design/"
    assert "--bg" in ds_files["tokens.css"], "tokens.css content must be read correctly"


@pytest.mark.integration
def test_components_html_written_to_context_design(tmp_path) -> None:
    """After Phase 6, components.html must be findable via rebuild_od_context_from_sandbox."""
    from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    sandbox.write(
        ".context/selections.json",
        json.dumps(
            {
                "template_id": "custom-figma",
                "ds_id": "derived",
                "source_type": "figma",
                "figma_frame_count": 2,
                "no_template": False,
                "is_design_system_required": None,
            }
        ),
    )
    sandbox.write(
        "context/design/components.html",
        "<html><body><div style='background:var(--bg)'>Component</div></body></html>",
    )
    sandbox.write("context/design/design-system.md", "# Design System\n")

    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    ds_files = rebuilt.get("ds_files", {})
    assert (
        "components.html" in ds_files
    ), "rebuild must pick up components.html from context/design/"


@pytest.mark.integration
def test_nine_section_design_md_readable_by_opendesign_provider(tmp_path) -> None:
    """A 9-section design-system.md must be readable by the opendesign provider."""
    nine_section_md = """# Design System Inspired by SaaS Dashboard

> Category: Product
> Dark SaaS dashboard with indigo accent and compact density.

## 1. Visual Theme & Atmosphere

Dark, compact SaaS dashboard. Primary brand colour is indigo (#5b5fef).

**Key characteristics:**
- Canvas: #13151f (near-black navy)
- Cards: #1e2130
- Accent: #5b5fef (indigo)

**Provenance:** Colours extracted via visual analysis of 2 Figma PNG frames.

## 2. Color Palette & Roles

### Primary
- **Indigo** (`#5b5fef`): buttons, active states

### Surfaces & Neutrals
- **Canvas** (`#13151f`): `--bg`
- **Card** (`#1e2130`): `--surface`

## 3. Typography Rules

### Font Family
- Body: Inter, system-ui, sans-serif

## 4. Component Stylings

### Buttons
Primary: #5b5fef fill, white text, 6px radius.

## 5. Layout Principles
- Spacing: 4 8 12 16 24 32 48

## 6. Depth & Elevation
Flat design with subtle border separators.

## 7. Do's and Don'ts
- Do: use --accent for interactive elements
- Don't: use raw hex values

## 8. Responsive Behaviour
Desktop-first, 1440px.

## 9. Agent Prompt Guide
Use dark navy backgrounds with indigo accents.
"""
    design_md_path = tmp_path / "context" / "design" / "design-system.md"
    design_md_path.parent.mkdir(parents=True)
    design_md_path.write_text(nine_section_md, encoding="utf-8")

    # Verify it has all 9 sections
    content = design_md_path.read_text()
    for section_num in range(1, 10):
        assert (
            f"## {section_num}." in content
        ), f"9-section design-system.md must contain '## {section_num}.'"
