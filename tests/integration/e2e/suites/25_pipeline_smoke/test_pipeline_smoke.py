"""Implements ../../../screens/25-pipeline-smoke.feature.md.

The only tests in this suite that ask whether the PIPELINE works rather than
whether a SCREEN does. Each one launches a first-party workflow from its
catalogue card, answers whatever gates it stops at, and asserts the run
finished and left the deliverable its manifest declares.

Every test here is `@live` and `@destructive`: it dispatches a real run
against a real model and leaves a real row in the history. The tier is
deselected by default (`pytest.ini` carries `-m "not live"`), so these only
execute under an explicit `-m live`.

**Launched from the catalogue card, never from the API.** `POST /api/runs`
skips the launch assembly the wizard performs — template, design system, the
agent roster the panel compiles — so an API launch does not exercise what a
user's launch does. `live.launch()` drives the real UI.

**Nothing here asserts on generated prose.** The brief is hello-world scale on
purpose; a smoke test that read the model's output would fail on model drift,
which is the opposite of what it is for.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import live
from framework.locators import run_detail as RD

# Manifest facts, mirrored from backend/agents/workflows/<id>/workflow.yaml.
# `name` is the catalogue card's `display_name`; `delivers` is the manifest's
# `deliverable.name`. None means the strategy is `serialized_sandbox`, which
# delivers a tree rather than one named file.
PPT = ("Pitch an idea", "presentation.pptx", r"PPT|PRESENTATION|Pitch")
PPT_V2 = ("Pitch an idea (v2)", "presentation.html", r"PPT|PRESENTATION|Pitch")
USER_STORIES = ("Generate product requirements", "user_stories.md", r"USER[ _]STORIES|REQUIREMENTS")
PROTOTYPE = ("Build an interactive prototype", "prototype.html", r"PROTOTYPE")
APP_BUILDER = ("Build an end-to-end application", None, r"APP[ _]BUILDER|APPLICATION")

# The smallest thing that is true of a real file of each type and false of a
# plausible-looking empty one. STRUCTURE ONLY — nothing here reads what the
# model wrote, so model drift can never fail these.
#
#   .pptx  an OOXML package is a ZIP: it opens with the local-file-header
#          magic and names ppt/presentation.xml among its entries. Entry names
#          are stored uncompressed, so a substring search finds one.
#   .html  a document element and a body. A deck that failed to render still
#          often leaves a stub, and a stub has neither.
#   .md    at least one ATX heading. Every one of these pipelines writes
#          structured markdown; a bare error string has no heading.
SHAPES = {
    ".pptx": lambda b: b.startswith("PK\x03\x04") and "ppt/presentation.xml" in b,
    ".html": lambda b: "<html" in b.lower() and "<body" in b.lower(),
    ".md": lambda b: re.search(r"^#{1,6}\s+\S", b, re.M) is not None,
}

SHAPE_SAYS = {
    ".pptx": "a ZIP whose entries include ppt/presentation.xml",
    ".html": "an <html> document with a <body>",
    ".md": "markdown with at least one heading",
}


def smoke(page, shot, card: str, delivers: str | None, names: str) -> None:
    """Launch `card`, drive it to a terminal state, and check what it left.

    Split out rather than parametrized: `capture/_scenarios.py` maps one
    scenario id to one test function, and five ids sharing a parametrized test
    would break that link in both directions.
    """
    with shot("launched", f'When I launch "{card}"'):
        run_id = live.launch(page, card)

    answered = live.run_to_completion(page)
    if answered:
        print(f"  answered {len(answered)} gate(s): {answered}")

    with shot("completed", "Then the run reaches a completed state"):
        expect(page.locator(RD.RUN_STATUS)).to_have_text(
            re.compile(r"done|completed", re.I)
        )

    # FIX-302's guard, generalised: a run must not render as some other
    # workflow. The bug only ever showed on a non-default type.
    assert re.search(names, page.content(), re.I), (
        f"the run surface does not name {card!r} anywhere"
    )

    # ---- every agent in the roster actually ran ----------------------------
    #
    # Checked BEFORE the file, because it is the failure a completed status
    # hides: a pipeline can skip a step and still write something at the
    # declared path, and then nothing downstream ever notices.
    roster, ran = live.agents(page, run_id)
    broken = [a for a in ran if a.get("error")]
    assert not broken, (
        f"{card!r} reports completed, but "
        + "; ".join(f"{a.get('name')}: {a['error']}" for a in broken)
    )
    assert len(ran) == roster, (
        f"{card!r} declares {roster} agents but only {len(ran)} reported: "
        f"{[a.get('name') for a in ran]}"
    )
    silent = [a.get("name") for a in ran if not a.get("total_tokens")]
    assert not silent, (
        f"{card!r} completed with agents that consumed no tokens at all, so "
        f"they never reached the model: {silent}"
    )

    # ---- the deliverable exists, is not empty, and is what it claims ------
    found = live.deliverables(page, run_id)
    assert found, f"{card!r} completed but flagged no file as a deliverable"

    empty = [f["path"] for f in found if not f.get("size")]
    assert not empty, (
        f"{card!r} delivered zero-byte file(s): {empty}. A named empty file is "
        f"the failure this suite exists to catch."
    )

    if not delivers:
        # serialized_sandbox — a tree, so there is no one name to check. The
        # roster and non-empty checks above are the whole assertion.
        return

    target = next((f for f in found if f["path"].split("/")[-1] == delivers), None)
    assert target, (
        f"{card!r} completed without its declared deliverable {delivers!r}; "
        f"the workspace delivered {[f['path'] for f in found]}"
    )

    ext = "." + delivers.rsplit(".", 1)[-1]
    looks_right = SHAPES.get(ext)
    if looks_right:
        body = live.file_bytes(page, run_id, target["path"])
        assert looks_right(body), (
            f"{delivers!r} is {target['size']} bytes but is not "
            f"{SHAPE_SAYS[ext]} — it starts {body[:40]!r}"
        )


@pytest.mark.scenario("S-25-01")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.timeout(900)
def test_ppt_runs_end_to_end_and_delivers_a_deck(page, shot):
    """Scenario: Pitch an idea runs end to end and delivers a deck"""
    smoke(page, shot, *PPT)


@pytest.mark.scenario("S-25-02")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.timeout(900)
def test_ppt_v2_runs_end_to_end_and_delivers_a_deck(page, shot):
    """Scenario: Pitch an idea v2 runs end to end and delivers a deck"""
    smoke(page, shot, *PPT_V2)


@pytest.mark.scenario("S-25-03")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.timeout(900)
def test_user_stories_runs_end_to_end_and_delivers_a_story_set(page, shot):
    """Scenario: Generate product requirements runs end to end and delivers a story set"""
    smoke(page, shot, *USER_STORIES)


@pytest.mark.scenario("S-25-04")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.timeout(900)
def test_prototype_runs_end_to_end_and_delivers_a_page(page, shot):
    """Scenario: Build an interactive prototype runs end to end and delivers a page"""
    smoke(page, shot, *PROTOTYPE)


@pytest.mark.scenario("S-25-05")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.timeout(900)
def test_app_builder_runs_end_to_end_and_delivers_a_sandbox(page, shot):
    """Scenario: Build an end-to-end application runs end to end and delivers a sandbox"""
    smoke(page, shot, *APP_BUILDER)
