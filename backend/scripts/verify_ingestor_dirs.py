"""
verify_ingestor_dirs.py — Quick sanity check for the Design Ingestor directory fix.

Simulates what od_context_sandbox.py does at run launch for a figma/html run
and verifies that .context/design/ subdirectories are pre-created correctly.

Run from backend/:
    uv run python scripts/verify_ingestor_dirs.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# ── Minimal duck-typed sandbox that writes to a real temp dir ────────────────


class TmpSandbox:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, relpath: str, content: str) -> None:
        full = self.root / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def read(self, relpath: str) -> str | None:
        full = self.root / relpath
        if not full.exists():
            return None
        return full.read_text(encoding="utf-8")

    def list_files(self):
        files = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                files.append({"path": str(p.relative_to(self.root))})
        return files, None


# ── Import the functions under test ─────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.services.od_context_sandbox import _write_od_context_to_sandbox  # noqa: E402
from agents.execution_engine.od_context import load_figma_ingest_context  # noqa: E402


# ── Test 1: Figma run pre-seeds .context/design/ directories ────────────────


def test_figma_directories_pre_created():
    print("\n── TEST 1: Figma run pre-seeds .context/design/ tree ──────────────")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = TmpSandbox(Path(tmp))
        ctx = load_figma_ingest_context(frame_count=5)
        _write_od_context_to_sandbox(sandbox, ctx)

        files = [f["path"].replace("\\", "/") for f in sandbox.list_files()[0]]
        print(f"  Files written: {files}")

        # Check selections.json
        assert (
            ".context/selections.json" in files
        ), "FAIL: .context/selections.json missing"
        sel = json.loads(sandbox.read(".context/selections.json"))
        assert (
            sel["source_type"] == "figma"
        ), f"FAIL: source_type={sel['source_type']!r}"
        assert (
            sel["figma_frame_count"] == 5
        ), f"FAIL: figma_frame_count={sel['figma_frame_count']}"
        print(
            f"  ✅ .context/selections.json: source_type={sel['source_type']}, figma_frame_count={sel['figma_frame_count']}"
        )

        # Check .context/design/ directories exist (via sentinel files)
        assert any(
            ".context/design/" in f for f in files
        ), "FAIL: .context/design/ directory not pre-created"
        print("  ✅ .context/design/ directory pre-created")

        assert any(
            ".context/design/template/" in f for f in files
        ), "FAIL: .context/design/template/ directory not pre-created"
        print("  ✅ .context/design/template/ directory pre-created")

        assert any(
            ".context/design/template/figma/" in f for f in files
        ), "FAIL: .context/design/template/figma/ directory not pre-created"
        print("  ✅ .context/design/template/figma/ directory pre-created")

        # Check NO design files written (ingestor agent owns those)
        design_files = [
            f for f in files if ".context/design/" in f and not f.endswith(".ingestor")
        ]
        assert (
            design_files == []
        ), f"FAIL: sandbox should not pre-populate design files: {design_files}"
        print("  ✅ No design files pre-written (ingestor agent owns those)")

        # Now simulate agent writing to .context/design/
        sandbox.write(
            ".context/design/design-system.md", "--bg: #13151f; --accent: #5b5fef;"
        )
        sandbox.write(
            ".context/design/template/SKILL.md", "# Figma Design Reference\n..."
        )
        sandbox.write(".context/design/template/example.html", "<html>...</html>")
        sandbox.write(
            ".context/design/template/figma/frames.json",
            '[{"index":0,"filename":"frame-1.png"}]',
        )
        sandbox.write(
            ".context/selections.json",
            json.dumps(
                {
                    "source_type": "figma",
                    "figma_frame_count": 5,
                    "template_id": "custom-figma",
                    "ds_id": "derived",
                    "template_name": "Figma Upload (5 screens)",
                    "ds_name": "Derived from Figma",
                    "no_template": False,
                    "is_design_system_required": None,
                }
            ),
        )
        print("  ✅ Agent can write to .context/design/ (simulated write succeeded)")

        files_after = [f["path"].replace("\\", "/") for f in sandbox.list_files()[0]]
        print(f"  Files after agent writes: {files_after}")

        assert (
            ".context/design/design-system.md" in files_after
        ), "FAIL: design-system.md not written"
        assert (
            ".context/design/template/SKILL.md" in files_after
        ), "FAIL: SKILL.md not written"
        assert (
            ".context/design/template/example.html" in files_after
        ), "FAIL: example.html not written"
        assert (
            ".context/design/template/figma/frames.json" in files_after
        ), "FAIL: frames.json not written"
        print("  ✅ All 4 design files written successfully")

    print("  PASS ✅")


# ── Test 2: HTML run pre-seeds .context/design/ directories ─────────────────


def test_html_directories_pre_created():
    print("\n── TEST 2: HTML run pre-seeds .context/design/ tree ───────────────")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = TmpSandbox(Path(tmp))
        html_ctx = {
            "source_type": "html",
            "template_id": "custom-html-123",
            "ds_id": "github",
            "template_body": None,
            "ds_body": "--bg: #fff;",
            "craft_block": "",
            "figma_frame_count": None,
            "no_template": False,
            "is_design_system_required": None,
            "template_name": "Custom HTML",
            "ds_name": "GitHub",
        }
        _write_od_context_to_sandbox(sandbox, html_ctx)
        files = [f["path"].replace("\\", "/") for f in sandbox.list_files()[0]]

        assert any(
            ".context/design/" in f for f in files
        ), "FAIL: .context/design/ not pre-created for html run"
        assert any(
            ".context/design/template/" in f for f in files
        ), "FAIL: .context/design/template/ not pre-created for html run"
        print("  ✅ .context/design/ and template/ pre-created for html run")

        # ds_body IS written for html (catalog DS selected)
        assert (
            ".context/design/design-system.md" in files
        ), "FAIL: design-system.md should be written when ds_body present"
        print("  ✅ design-system.md written (catalog DS present)")

        # No figma/ subdirectory for html runs
        assert not any(
            ".context/design/template/figma/" in f for f in files
        ), "FAIL: figma/ subdir should NOT be created for html runs"
        print("  ✅ No figma/ subdirectory for html run (correct)")

    print("  PASS ✅")


# ── Test 3: Catalog run is completely unchanged ──────────────────────────────


def test_catalog_run_unchanged():
    print("\n── TEST 3: Catalog run writes design files normally (unchanged) ────")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = TmpSandbox(Path(tmp))
        catalog_ctx = {
            "source_type": "catalog",
            "template_id": "web-prototype",
            "ds_id": "github",
            "template_body": "# Web Prototype\n## Workflow\n...",
            "ds_body": "--bg: #ffffff; --fg: #24292f;",
            "craft_block": "",
            "figma_frame_count": None,
            "no_template": False,
            "is_design_system_required": None,
            "template_name": "Web Prototype",
            "ds_name": "GitHub",
            "template_files": {"example.html": "<html>example</html>"},
            "ds_files": {},
        }
        _write_od_context_to_sandbox(sandbox, catalog_ctx)
        files = [f["path"].replace("\\", "/") for f in sandbox.list_files()[0]]
        print(f"  Files: {files}")

        assert (
            ".context/design/design-system.md" in files
        ), "FAIL: design-system.md missing"
        assert ".context/design/template/SKILL.md" in files, "FAIL: SKILL.md missing"
        assert (
            ".context/design/template/example.html" in files
        ), "FAIL: example.html missing"

        # No .ingestor sentinel files for catalog runs
        assert not any(
            ".ingestor" in f for f in files
        ), "FAIL: catalog run should have no .ingestor sentinel files"
        print("  ✅ Catalog run writes all design files directly (no sentinels)")

    print("  PASS ✅")


# ── Run all tests ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Design Ingestor Directory Pre-Seed Verification")
    print("=" * 60)

    try:
        test_figma_directories_pre_created()
        test_html_directories_pre_created()
        test_catalog_run_unchanged()
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
