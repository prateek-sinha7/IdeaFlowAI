"""Wave-0 acceptance for context_pack + context_selector + the repo provider (REPO-03).

Drives the targeted-context-subset capability OFFLINE:

  * the pack contains the TARGET file + selector-chosen neighbors (same-directory
    siblings + imported files), and EXCLUDES unrelated files,
  * an ``artifact_ref`` is written (lineage-tracked),
  * the ``repo`` ContextProvider surfaces the pack as an injected context block,
  * the provider's cross-owner ``assert_owns`` PermissionError PROPAGATES (L16).

Pure-stdlib, kernel-clean — reaches disk via a duck-typed workspace and the store
via a fake ctx.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agents.artifacts.graph import ArtifactGraph
from agents.capabilities.context_pack.pack import context_selector
from agents.capabilities.registry import CapabilityRegistry, discover


class _FakeWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read_file(self, relpath: str) -> str:
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
    def __init__(self, runner: _FakeRunner, *, target: str | None = None) -> None:
        self.runner = runner
        self.artifacts = ArtifactGraph()
        self.scoped_store = None
        self.run_id = "run-1"
        self.owner_id = "anon"
        self.workspace_id = "ws-1"
        self.context_pack_target = target


@pytest.fixture()
def repo_tree(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    # Target imports `helpers`; `sibling` is a same-dir neighbor; `unrelated` lives
    # elsewhere and must be EXCLUDED.
    (pkg / "main.py").write_text(
        "from pkg.helpers import do\n\n\ndef run():\n    return do()\n",
        encoding="utf-8",
    )
    (pkg / "helpers.py").write_text("def do():\n    return 1\n", encoding="utf-8")
    (pkg / "sibling.py").write_text("x = 1\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    (other / "unrelated.py").write_text("y = 2\n", encoding="utf-8")
    return tmp_path


def test_context_selector_picks_siblings_and_imports() -> None:
    candidates = ["pkg/main.py", "pkg/helpers.py", "pkg/sibling.py", "other/unrelated.py"]
    target_content = "from pkg.helpers import do\n"
    neighbors = context_selector("pkg/main.py", candidates, target_content)
    assert "pkg/helpers.py" in neighbors   # imported
    assert "pkg/sibling.py" in neighbors   # same-directory sibling
    assert "other/unrelated.py" not in neighbors  # unrelated, excluded
    assert "pkg/main.py" not in neighbors  # never the target itself


def _pack_cap():
    discover()
    return CapabilityRegistry().resolve("context_pack", "default")


def test_pack_contains_target_and_neighbors_excludes_unrelated(repo_tree: Path) -> None:
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)), target="pkg/main.py")
    pack = _pack_cap().build(ctx, target="pkg/main.py")

    assert pack["target"] == "pkg/main.py"
    files = pack["files"]
    assert "pkg/main.py" in files
    assert "pkg/helpers.py" in files
    assert "pkg/sibling.py" in files
    assert "other/unrelated.py" not in files


def test_pack_is_lineage_tracked(repo_tree: Path) -> None:
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)), target="pkg/main.py")
    _pack_cap().build(ctx, target="pkg/main.py")
    refs = ctx.artifacts.list_by_kind("context_pack")
    assert len(refs) == 1
    assert refs[0].kind == "context_pack"
    assert getattr(ctx, "context_pack_ref", None) is refs[0]


def test_repo_provider_surfaces_the_pack(repo_tree: Path) -> None:
    discover()
    provider = CapabilityRegistry().resolve("context_provider", "repo")
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)), target="pkg/main.py")

    blocks = asyncio.run(provider.load(ctx))
    assert "repo_context" in blocks
    body = blocks["repo_context"]
    assert "pkg/main.py" in body
    assert "pkg/helpers.py" in body
    assert "unrelated" not in body  # excluded file never surfaced


def test_repo_provider_propagates_cross_owner_permission_error(repo_tree: Path) -> None:
    """A cross-owner source run denies — PermissionError PROPAGATES (L16 / T-09-03-ID)."""

    class _DenyingStore:
        async def assert_owns(self, run_id: str) -> None:
            raise PermissionError("cross-owner")

    discover()
    provider = CapabilityRegistry().resolve("context_provider", "repo")
    ctx = _FakeCtx(_FakeRunner(_FakeWorkspace(repo_tree)), target="pkg/main.py")
    ctx.scoped_store = _DenyingStore()
    ctx.repo_source_run_id = "someone-elses-run"

    with pytest.raises(PermissionError):
        asyncio.run(provider.load(ctx))


def test_repo_capabilities_registered() -> None:
    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("context_pack", "default")
    assert reg.is_registered("context_provider", "repo")
