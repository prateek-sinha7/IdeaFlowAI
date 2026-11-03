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

Both loaders seed the template's files, so the deck loader's signature is its
conditional design system: ``is_design_system_required`` is a bool for a deck and
``None`` for a page (a page template always requires one).
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
    return (od or {}).get("is_design_system_required") is not None


@pytest.mark.parametrize(
    "pipeline_type",
    ["prototype", "prototype_feature_revision", "custom", "prototype_v2"],
)
def test_web_pipelines_get_the_page_loader(pipeline_type):
    """Named web pipelines, a composed run, and a web FILE workflow all agree."""
    _, od = _resolve(pipeline_type)
    assert not _is_deck(od), f"{pipeline_type} was handed the deck loader"
    assert od["template_name"] == _WEB_TEMPLATE
    assert od["ds_name"]


@pytest.mark.parametrize("pipeline_type", ["ppt", "ppt_revision", "ppt_v2"])
def test_deck_pipelines_keep_the_deck_loader_and_its_blank_template_error(
    pipeline_type,
):
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


def test_a_page_run_seeds_the_files_its_template_names():
    """The template's SKILL.md tells the agent to open example.html,
    assets/template.html and references/checklist.md. Run 05b11d19 had only
    SKILL.md in .context/design/template/, so the agent found none of them."""
    _, od = _resolve("prototype_v2", template_id="underwriting-workbench")
    files = od["template_files"]
    assert {"example.html", "assets/template.html", "references/checklist.md"} <= set(
        files
    )
    assert "SKILL.md" not in files and not any(p.startswith("scripts/") for p in files)
    assert "<style" in files["example.html"]


def test_the_design_systems_css_tokens_travel_with_it():
    _, od = _resolve("prototype_v2")  # linear-app ships tokens.css + components.html
    assert set(od["ds_files"]) == {"tokens.css", "components.html"}


# ---------------------------------------------------------------------------
# CompilerError / ManifestValidationError handling
# ---------------------------------------------------------------------------
# resolve_launch_od_context calls compile_for_run to peek context_providers.
# If the workflow.yaml was partially deployed (e.g. has a new 'condition' step
# key the compiler doesn't yet recognise), compile_for_run raises CompilerError.
# Before the fix this propagated as an unhandled exception → HTTP 500.
# The broadened except clause now returns (base, None) for these errors.
# ---------------------------------------------------------------------------


def test_resolve_launch_od_context_returns_none_od_context_when_compiler_error():
    """CompilerError from compile_for_run must not escape — returns (base, None)."""
    from agents.workflows.compiler import CompilerError
    from unittest.mock import patch

    with patch(
        "agents.execution_engine.engine.compile_for_run",
        side_effect=CompilerError("unknown step key: condition"),
    ):
        base, od = resolve_launch_od_context(
            "prototype_v2", "web-prototype", _DS, fatal=True
        )

    assert base == "prototype_v2"
    assert od is None


def test_resolve_launch_od_context_returns_none_od_context_when_manifest_validation_error():
    """ManifestValidationError from compile_for_run must not escape — returns (base, None)."""
    from agents.workflows.manifest import ManifestValidationError
    from unittest.mock import patch

    with patch(
        "agents.execution_engine.engine.compile_for_run",
        side_effect=ManifestValidationError("unknown top-level key"),
    ):
        base, od = resolve_launch_od_context(
            "prototype_v2", "web-prototype", _DS, fatal=True
        )

    assert base == "prototype_v2"
    assert od is None


# ---------------------------------------------------------------------------
# prototype_v2 in _WEB_PIPELINES
# ---------------------------------------------------------------------------
# prototype_v2 was previously absent from _WEB_PIPELINES, causing it to fall
# into the else branch that called od_loader.get_template(template_id) to read
# the template's mode field. If the template had mode='deck' (e.g. a mis-picked
# template), prototype_v2 would have been handed the deck (ppt) loader instead
# of the page (prototype) loader. Adding it to _WEB_PIPELINES fixes this.
# ---------------------------------------------------------------------------


def test_prototype_v2_uses_page_loader_even_when_template_has_deck_mode():
    """prototype_v2 is now in _WEB_PIPELINES, so its loader is always 'prototype'.
    A deck-mode template must not cause it to be handed the ppt loader."""
    from unittest.mock import patch

    from app.services import od_loader

    deck_template = {
        "id": "fake-deck",
        "mode": "deck",
        "name": "Fake Deck Template",
        "body": "## Workflow\nDeck instructions.",
        "craft_required": [],
    }
    fake_ds = {"id": _DS, "name": "Linear", "body": ":root{}"}

    with (
        patch.object(od_loader, "get_template", return_value=deck_template),
        patch.object(od_loader, "get_design_system", return_value=fake_ds),
        patch.object(od_loader, "get_craft_rules", return_value={}),
        patch.object(od_loader, "get_template_files", return_value={}),
        patch.object(od_loader, "get_design_system_files", return_value={}),
    ):
        base, od = resolve_launch_od_context(
            "prototype_v2",
            "fake-deck",
            _DS,
            fatal=True,
            context_providers=["opendesign"],
        )

    assert base == "prototype_v2"
    # Page (prototype) loader sets is_design_system_required=None.
    # Deck (ppt) loader sets it to a boolean. A non-None value means the wrong
    # loader was used.
    assert od is not None
    assert (
        od["is_design_system_required"] is None
    ), "prototype_v2 was handed the deck loader — it should always use the page loader"
