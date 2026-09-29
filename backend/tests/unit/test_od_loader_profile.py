"""Which od_context LOADER a pipeline gets — page templates or deck templates.

The two named families are listed explicitly and everything else derives its
family from the picked template's own ``mode``. Both halves have already been
got wrong once:

* An exclusion tuple ``("prototype", "ppt", "ppt_revision")`` let ``ppt_v2`` —
  which also declares ``context_providers: [opendesign]`` — fall into the
  derivation. With a design system and no template there is no mode to read, so
  a DECK pipeline was handed a web od_context instead of raising LookupError →
  a clean 400 template_not_found.
* Narrowing the derivation to ``custom`` fixed that and broke the other side:
  ``pdf_to_prototype`` (a web workflow) fell through to
  ``base_profile = "pdf_to_prototype"``, which is not ``"prototype"``, and landed
  on the DECK loader.

A `template_files` key in the result is the deck loader's signature — the web
loader passes its template through as prompt text and seeds nothing to disk.
"""

import pytest

from app.api.launch_context import resolve_launch_od_context

_DS = "linear-app"
_WEB_TEMPLATE = "live-dashboard"


def _resolve(pipeline_type, template_id=_WEB_TEMPLATE):
    return resolve_launch_od_context(
        pipeline_type, template_id, _DS, fatal=True, context_providers=["opendesign"]
    )


def _is_deck(od):
    return "template_files" in (od or {})


@pytest.mark.parametrize(
    "pipeline_type", ["prototype", "prototype_feature_revision", "custom", "prototype_v2"]
)
def test_web_pipelines_get_the_page_loader(pipeline_type):
    """Named web pipelines, a composed run, and a web FILE workflow all agree."""
    _, od = _resolve(pipeline_type)
    assert not _is_deck(od), f"{pipeline_type} was handed the deck loader"
    assert od["template_name"] == _WEB_TEMPLATE
    assert od["ds_name"]


@pytest.mark.parametrize("pipeline_type", ["ppt", "ppt_revision", "ppt_v2"])
def test_deck_pipelines_keep_the_deck_loader_and_its_blank_template_error(pipeline_type):
    """A deck pipeline with no template must FAIL, not silently build a web one.

    The blank-canvas branch upstream sets template_id = "", so there is no mode
    to read. The deck loader has no no-template path and raises — which the API
    turns into a clean 400 template_not_found. Falling through to the web loader
    (which does have one) would have produced page context for a deck run.
    """
    with pytest.raises(LookupError):
        _resolve(pipeline_type, template_id="")


def test_an_unknown_pipeline_follows_its_template(monkeypatch):
    """The derivation itself: the template says whether it is a page or a deck."""
    # `od_loader` is imported INSIDE the function, so patch it at its source.
    from app.services import od_loader

    monkeypatch.setattr(od_loader, "get_template", lambda _tid: {"mode": "deck"})
    # A name in neither family + a deck-mode template ⇒ the deck loader, which
    # then rejects the (fake) id rather than quietly building web context.
    with pytest.raises(LookupError):
        _resolve("some_future_deck_workflow", template_id="whatever")


def test_no_opendesign_declaration_resolves_nothing():
    """Unchanged: a workflow that does not declare the provider gets no context."""
    base, od = resolve_launch_od_context(
        "prototype_v2", _WEB_TEMPLATE, _DS, fatal=True, context_providers=[]
    )
    assert od is None
    assert base == "prototype_v2"
