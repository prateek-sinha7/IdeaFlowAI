"""ISS-974 (QA-KB-053) - figma-export renders the requested version's own
prototype.html.

Every member of a revision family shares ONE sandbox, so its working tree is
the NEWEST member's file. With ``ref`` the route must render the bytes at that
tag (from a temp file in the sandbox's git-ignored .browser/ scratch, removed
afterwards); without it, the working tree as before.
"""

import sys
import types
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from fastapi import HTTPException

from app.api import run_figma_export as mod

USER = types.SimpleNamespace(id="user-1")


class _Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "prototype.html").write_text("<html>live: the newest member</html>")

    def list_tags(self) -> list[str]:
        return ["v1", "v2"]

    def read_file_at_ref(self, ref: str, relpath: str) -> bytes:
        return f"<html>{relpath} at {ref}</html>".encode()

    def path_for(self, relpath: str) -> Path:
        return self.root / relpath


@pytest.fixture
def rendered(monkeypatch, tmp_path):
    seen: dict = {}

    async def _owned(run_id, current_user):
        return None

    async def _extract(html_uri: str) -> dict:
        path = Path(unquote(urlparse(html_uri).path))
        seen["path"] = path
        seen["html"] = path.read_text()
        return {"screens": [{"tag": "body"}]}

    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=None),
    )
    monkeypatch.setattr(mod, "_resolve_owned_run", _owned)
    monkeypatch.setattr(
        mod, "_resolve_chain_root_or_404", lambda run_id, user_id: "root"
    )
    monkeypatch.setattr(mod, "RunSandbox", lambda *a, **k: _Sandbox(tmp_path))
    monkeypatch.setattr(mod, "_run_playwright_extraction", _extract)
    return seen


async def test_ref_renders_that_versions_own_prototype_and_cleans_up(
    rendered, tmp_path
):
    await mod.figma_export("member-v1", ref="v1", current_user=USER)

    assert rendered["html"] == "<html>prototype.html at v1</html>"
    assert rendered["path"].parent == tmp_path / ".browser"
    assert not rendered["path"].exists()


async def test_no_ref_renders_the_working_tree(rendered, tmp_path):
    await mod.figma_export("member-v2", current_user=USER)

    assert rendered["html"] == "<html>live: the newest member</html>"
    assert rendered["path"] == tmp_path / "prototype.html"


async def test_a_ref_that_is_not_a_version_tag_is_rejected(rendered):
    with pytest.raises(HTTPException) as exc:
        await mod.figma_export("member-v1", ref="HEAD~1", current_user=USER)

    assert exc.value.status_code == 400
    assert "html" not in rendered
