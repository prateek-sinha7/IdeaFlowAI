"""ISS-720: the ref-scoped listing's byte sizes come from the git tree itself.

``list_files_at_ref`` runs ``git ls-tree -r <ref> --name-only``, which drops the
object-size column — so ``GET /sandbox?ref=vN`` reported ``size: 0`` for every
row. ``file_sizes_at_ref`` reads the same tree with ``-l`` (long format) and
returns ``{path: size}``; the route looks each path up in it.

Two layers: the ``ls-tree -l`` parse against a real throwaway git repo in
``tmp_path``, and the two route branches that consume the map — the listing
(ISS-720) and the zip's 64MB cap, which the ref branch used to return past
(ISS-704). Offline, no server, no product run.

Do NOT run the full suite (it hangs offline) — this file only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _ws(root: Path):
    from app.agents.runtime.local import LocalWorkspace

    ws = LocalWorkspace.__new__(LocalWorkspace)
    ws._root = root
    return ws


def _repo_with_a_tag(tmp_path: Path) -> Path:
    root = tmp_path / "parent" / "sandbox"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    (root / "small.txt").write_text("x" * 11)
    (root / "presentation.html").write_text("y" * 4242)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "one")
    # A submodule entry (mode 160000): `ls-tree -l` prints "-" in the size column.
    sha = _git(root, "rev-parse", "HEAD").strip()
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{sha},vendor/sub")
    _git(root, "commit", "-qm", "two")
    _git(root, "tag", "v1")
    return root


def test_file_sizes_at_ref_reports_real_blob_sizes(tmp_path: Path) -> None:
    """The size a ref-scoped listing shows is the blob's own byte count, not 0."""
    ws = _ws(_repo_with_a_tag(tmp_path))

    sizes = ws.file_sizes_at_ref("v1")

    assert sizes["small.txt"] == 11
    assert sizes["presentation.html"] == 4242


def test_keys_line_up_with_list_files_at_ref_and_skip_the_submodule(
    tmp_path: Path,
) -> None:
    """Same key formatting as the path list, minus the entries with no size.

    The route looks each ``list_files_at_ref`` path up in this map, so any key
    that disagrees would silently fall back to 0 — the very bug. A submodule has
    no blob size (``-``), and must be omitted rather than crash the parse.
    """
    ws = _ws(_repo_with_a_tag(tmp_path))

    paths = ws.list_files_at_ref("v1")
    sizes = ws.file_sizes_at_ref("v1")

    assert "vendor/sub" in paths
    assert set(paths) - set(sizes) == {"vendor/sub"}
    assert all(sizes[p] > 0 for p in set(paths) - {"vendor/sub"})


def test_a_directory_without_git_reads_nothing(tmp_path: Path) -> None:
    """FIX-522: GIT_CEILING_DIRECTORIES keeps this call inside its own sandbox.

    Without the ceiling, git walks upward and answers from whatever repository
    encloses RUNS_ROOT.
    """
    root = _repo_with_a_tag(tmp_path)
    (root / "nested").mkdir()

    assert _ws(root / "nested").file_sizes_at_ref("v1") == {}
    assert _ws(root.parent).file_sizes_at_ref("v1") == {}


# ── the route wiring: both branches that consume the size map ───────────────


class _Sandbox:
    """The narrow slice of ``RunSandbox`` the two ref branches actually touch."""

    def __init__(self, sizes: dict[str, int]) -> None:
        self._sizes = sizes
        self.archived = False

    @property
    def root(self):
        return Path(__file__).parent  # both routes gate on root.is_dir()

    def list_tags(self) -> list[str]:
        return ["v1"]

    def list_files_at_ref(self, ref: str) -> list[str]:
        return sorted(self._sizes)

    def file_sizes_at_ref(self, ref: str) -> dict[str, int]:
        return dict(self._sizes)

    def archive_at_ref(self, ref: str) -> bytes:
        self.archived = True
        return b"PK\x05\x06" + b"\x00" * 18


def _user():
    return SimpleNamespace(id="user-1")


def _patch_route(monkeypatch, sandbox: _Sandbox):
    from app.api import run_files as rf

    async def _owned(run_id, current_user):
        return None

    monkeypatch.setattr(rf, "_resolve_owned_run", _owned)
    monkeypatch.setattr(rf, "_resolve_chain_root_or_404", lambda run_id, user_id: run_id)
    monkeypatch.setattr(rf, "RunSandbox", lambda *a, **k: sandbox)
    return rf


@pytest.mark.asyncio
async def test_the_ref_scoped_listing_carries_the_real_size(monkeypatch) -> None:
    """QA-PS-032: selecting a version showed 0 B for every file."""
    sandbox = _Sandbox({"presentation.html": 27549, "notes.md": 12})
    rf = _patch_route(monkeypatch, sandbox)

    payload = await rf.list_sandbox("run-1", ref="v1", current_user=_user())

    sizes = {f["path"]: f["size"] for f in payload["files"]}
    assert sizes == {"presentation.html": 27549, "notes.md": 12}


@pytest.mark.asyncio
async def test_the_ref_scoped_zip_refuses_an_over_cap_tree(monkeypatch) -> None:
    """ISS-704: the ref branch returned before the live path's 64MB cap check.

    The refusal must land BEFORE ``git archive`` runs — the cap exists to stop a
    runaway workspace being assembled in memory, not to discard it afterwards.
    """
    from fastapi import HTTPException

    from app.api.run_files import _SANDBOX_MAX_ZIP_BYTES

    sandbox = _Sandbox({"huge.bin": _SANDBOX_MAX_ZIP_BYTES + 1})
    rf = _patch_route(monkeypatch, sandbox)

    with pytest.raises(HTTPException) as excinfo:
        await rf.download_sandbox_zip("run-1", ref="v1", current_user=_user())

    assert excinfo.value.status_code == 413
    assert sandbox.archived is False, "the archive must never be built once over cap"


@pytest.mark.asyncio
async def test_the_ref_scoped_zip_still_serves_a_tree_under_the_cap(monkeypatch) -> None:
    """The cap is a ceiling, not a new refusal on the ordinary path."""
    sandbox = _Sandbox({"presentation.html": 27549})
    rf = _patch_route(monkeypatch, sandbox)

    response = await rf.download_sandbox_zip("run-1", ref="v1", current_user=_user())

    assert response.status_code == 200
    assert sandbox.archived is True
