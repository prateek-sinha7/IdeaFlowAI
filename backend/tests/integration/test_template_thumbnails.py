"""Tests for the OpenDesign gallery thumbnail serving path (FIX-039/040/042).

Covers the ``GET /api/{prototype,ppt}/templates/{id}/thumbnail`` route handlers
and the loader plumbing behind them:

* ``has_thumbnail`` on the loaded template dict reflects the on-disk file.
* A present ``thumbnail.jpg`` serves as ``image/jpeg`` (the <img> fast-path).
* An unknown template id yields a 404 (never a path-traversal / 500).
* A thumbnail deleted AFTER load (stale ``has_thumbnail`` flag, computed once by
  the ``lru_cache``d ``_all_templates()``) yields a clean 404 rather than a 500
  mid-``FileResponse`` — the FIX-042 on-disk re-check — so the gallery card can
  fall back to the live iframe.

The thumbnail routes are intentionally unauthenticated (static, same rationale
as ``/preview``), so the handlers are exercised directly without the DB/lifespan
machinery a full ``TestClient`` would require.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api.ppt_templates import get_ppt_template_thumbnail
from app.api.prototype_templates import get_template_thumbnail
from app.services import od_loader

_JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


def _write_template(root, template_id: str, *, mode: str, thumbnail: bool) -> None:
    """Create a minimal on-disk OpenDesign template folder."""
    folder = root / template_id
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {template_id}\ndescription: test\nod:\n  mode: {mode}\n---\n# body\n",
        encoding="utf-8",
    )
    (folder / "example.html").write_text("<html><body>hi</body></html>", encoding="utf-8")
    if thumbnail:
        (folder / "thumbnail.jpg").write_bytes(_JPEG_MAGIC)


@pytest.fixture()
def od_templates(monkeypatch, tmp_path):
    """Point the loader at a temp templates dir with a known fixture set.

    Two prototype templates (one with a thumbnail, one without) and one deck
    template with a thumbnail. Clears the ``_all_templates`` cache on the way in
    and out so neither the real tree nor this fixture leaks across tests.
    """
    templates_dir = tmp_path / "design-templates"
    templates_dir.mkdir()
    _write_template(templates_dir, "with-thumb", mode="prototype", thumbnail=True)
    _write_template(templates_dir, "no-thumb", mode="prototype", thumbnail=False)
    _write_template(templates_dir, "deck-thumb", mode="deck", thumbnail=True)

    monkeypatch.setattr(od_loader, "_TEMPLATES_DIR", templates_dir)
    od_loader._all_templates.cache_clear()
    yield templates_dir
    od_loader._all_templates.cache_clear()


# --- loader flag --------------------------------------------------------


def test_has_thumbnail_flag_reflects_disk(od_templates):
    by_id = {t["id"]: t for t in od_loader.list_prototype_templates()}
    assert by_id["with-thumb"]["has_thumbnail"] is True
    assert by_id["no-thumb"]["has_thumbnail"] is False


def test_thumbnail_path_present_and_absent(od_templates):
    assert od_loader.get_template_thumbnail_path("with-thumb") is not None
    assert od_loader.get_template_thumbnail_path("no-thumb") is None
    assert od_loader.get_template_thumbnail_path("does-not-exist") is None


# --- prototype endpoint -------------------------------------------------


def test_prototype_thumbnail_served_as_jpeg(od_templates):
    resp = get_template_thumbnail("with-thumb")
    assert isinstance(resp, FileResponse)
    assert resp.media_type == "image/jpeg"
    assert str(resp.path).endswith("thumbnail.jpg")


def test_prototype_thumbnail_missing_file_is_404(od_templates):
    with pytest.raises(HTTPException) as exc:
        get_template_thumbnail("no-thumb")
    assert exc.value.status_code == 404


def test_prototype_thumbnail_unknown_id_is_404(od_templates):
    with pytest.raises(HTTPException) as exc:
        get_template_thumbnail("../../etc/passwd")
    assert exc.value.status_code == 404


def test_prototype_thumbnail_stale_flag_is_404_not_500(od_templates):
    """FIX-042: a thumbnail deleted after load leaves ``has_thumbnail`` True in
    the cache, but the endpoint re-checks disk and returns a clean 404."""
    # Warm the cache so has_thumbnail is computed as True.
    assert od_loader.get_template("with-thumb")["has_thumbnail"] is True
    # Delete the file out from under the cached flag.
    (od_templates / "with-thumb" / "thumbnail.jpg").unlink()

    with pytest.raises(HTTPException) as exc:
        get_template_thumbnail("with-thumb")
    assert exc.value.status_code == 404


# --- ppt endpoint -------------------------------------------------------


def test_ppt_thumbnail_served_as_jpeg(od_templates):
    resp = get_ppt_template_thumbnail("deck-thumb")
    assert isinstance(resp, FileResponse)
    assert resp.media_type == "image/jpeg"
    assert str(resp.path).endswith("thumbnail.jpg")


def test_ppt_thumbnail_unknown_id_is_404(od_templates):
    with pytest.raises(HTTPException) as exc:
        get_ppt_template_thumbnail("nope")
    assert exc.value.status_code == 404
