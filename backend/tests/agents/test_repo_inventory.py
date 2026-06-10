"""Wave-0 acceptance for the kernel-side repo inventory (Phase 09 / REPO-01).

Drives ``repo_inventory`` OFFLINE over a real on-disk tree seeded with a binary
file + a ``.flowinignore`` entry + a dependency manifest:

  * lists source files,
  * EXCLUDES ``.flowinignore``-matched + binary files,
  * applies the documented size caps,
  * reports language stats + a parsed dependency list,
  * lineage-tracks the inventory as a typed ``repo_inventory`` artifact.

Pure-stdlib, kernel-clean (no app.* import) — reaches disk via a duck-typed
workspace handle and the store via a fake ctx.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agents.artifacts.graph import ArtifactGraph
from agents.capabilities.registry import CapabilityRegistry, discover


class _FakeWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read_file(self, relpath: str) -> str:
        # Mirror the LocalWorkspace contract: UTF-8 decode (raises on binary).
        return (self.root / relpath).read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        return [
            p.relative_to(self.root).as_posix()
            for p in sorted(self.root.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        ]


class _FakeRunner:
    def __init__(self, workspace: _FakeWorkspace) -> None:
        self.workspace = workspace


class _FakeCtx:
    def __init__(self, runner: _FakeRunner) -> None:
        self.runner = runner
        self.artifacts = ArtifactGraph()
        self.scoped_store = None  # no DB in the offline unit path
        self.run_id = "run-1"
        self.owner_id = "anon"
        self.workspace_id = "ws-1"


@pytest.fixture()
def repo_tree(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    (src / "util.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    # A JS file for language-stat coverage.
    (tmp_path / "index.js").write_text("console.log('x');\n", encoding="utf-8")
    # A binary file (null byte) — must be excluded by the binary-skip sniff.
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\x00\x00binary\x00data")
    # A .flowinignore entry — secret.txt must be excluded.
    (tmp_path / ".flowinignore").write_text("secret.txt\n*.tmp\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("password=123\n", encoding="utf-8")
    (tmp_path / "scratch.tmp").write_text("temp\n", encoding="utf-8")
    # A dependency manifest.
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n# comment\nrequests\n", encoding="utf-8")
    return tmp_path


def _inventory():
    discover()
    return CapabilityRegistry().resolve("repo_inventory", "default")


def test_inventory_lists_sources_excludes_ignored_and_binary(repo_tree: Path) -> None:
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)))
    result = _inventory().build(ctx)

    files = result["files"]
    assert "src/app.py" in files
    assert "src/util.py" in files
    assert "index.js" in files

    # Binary excluded (null-byte sniff).
    assert "logo.png" not in files
    # .flowinignore excluded.
    assert "secret.txt" not in files
    assert "scratch.tmp" not in files


def test_inventory_reports_language_stats(repo_tree: Path) -> None:
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)))
    langs = _inventory().build(ctx)["languages"]
    assert langs.get(".py") == 2
    assert langs.get(".js") == 1
    assert ".png" not in langs  # binary never counted


def test_inventory_parses_dependencies(repo_tree: Path) -> None:
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)))
    deps = _inventory().build(ctx)["dependencies"]
    assert "flask==3.0.0" in deps
    assert "requests" in deps
    assert "# comment" not in deps


def test_inventory_applies_per_file_size_cap(tmp_path: Path) -> None:
    from agents.capabilities.repo_inventory.inventory import MAX_FILE_BYTES

    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "huge.py").write_text("x" * (MAX_FILE_BYTES + 10), encoding="utf-8")
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(tmp_path)))
    files = _inventory().build(ctx)["files"]
    assert "small.py" in files
    assert "huge.py" not in files  # over the per-file cap


def test_inventory_is_lineage_tracked(repo_tree: Path) -> None:
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)))
    _inventory().build(ctx)
    # A repo_inventory ArtifactRef was written into the per-run graph.
    refs = ctx.artifacts.list_by_kind("repo_inventory")
    assert len(refs) == 1
    assert refs[0].kind == "repo_inventory"
    assert refs[0].owner_id == "anon"
    assert getattr(ctx, "repo_inventory_ref", None) is refs[0]


def test_inventory_registered() -> None:
    discover()
    assert CapabilityRegistry().is_registered("repo_inventory", "default")
