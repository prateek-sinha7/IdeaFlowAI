"""T25 — `compatible_agents` returns to the skills loader and API.

Traces to R-31, R-33, R-34, F-08 (specs/012-per-agent-skills-custom-agents).

Mirrors the equivalent field already carried by ``hooks_catalog.py`` (see
``GlobalHookEntry.compatible_agents``). Covers:

* the field parses from SKILL.md frontmatter when present
* absent frontmatter yields an empty list — the safety default (R-33): a
  file the derivation pass misses degrades to "compatible with everything",
  never to an invisible filter
* the field is served on GET /api/skills/library (asdict serializes any
  dataclass field automatically, same as hooks)
* every real catalog entry still loads with the new field present

R-34: `compatible_agents` is never enforced server-side. No test here
exercises an attach/launch path being filtered or rejected by this field —
there is no such server-side check to test, by design.
"""

from __future__ import annotations

import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.agents.skills_catalog as skills_catalog
from app.agents.skills_catalog import GlobalSkillEntry, list_global_skills
from app.api.skills import router as skills_router
from app.core.dependencies import get_current_user


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture(autouse=True)
def _clear_cache():
    skills_catalog.clear_cache()
    yield
    skills_catalog.clear_cache()


def _write_skill(tmp_path, skill_id: str, frontmatter_extra: str = "") -> None:
    skill_dir = tmp_path / skill_id
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {skill_id}
            description: A test skill.
            {frontmatter_extra}
            ---
            Body content.
            """
        ),
        encoding="utf-8",
    )


def test_compatible_agents_parses_when_present(tmp_path, monkeypatch):
    _write_skill(
        tmp_path,
        "with-compat",
        frontmatter_extra="compatible_agents: [domain-analyst, epic-architect]",
    )
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    entries = list_global_skills()
    assert len(entries) == 1
    assert entries[0].compatible_agents == ["domain-analyst", "epic-architect"]


def test_compatible_agents_absent_yields_empty_list(tmp_path, monkeypatch):
    _write_skill(tmp_path, "no-compat")
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    entries = list_global_skills()
    assert len(entries) == 1
    assert entries[0].compatible_agents == []


def test_dataclass_default_is_empty_list():
    entry = GlobalSkillEntry(
        id="x",
        name="x",
        display_name="x",
        description="x",
        content="",
        isBeta=False,
    )
    assert entry.compatible_agents == []


def test_api_serializes_compatible_agents(tmp_path, monkeypatch):
    _write_skill(
        tmp_path,
        "with-compat",
        frontmatter_extra="compatible_agents: [prototype-build]",
    )
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(id="user-1")
    client = TestClient(app)

    response = client.get("/api/skills/library")
    assert response.status_code == 200
    body = response.json()
    assert body["skills"][0]["compatible_agents"] == ["prototype-build"]


def test_api_serializes_absent_compatible_agents_as_empty_list(tmp_path, monkeypatch):
    _write_skill(tmp_path, "no-compat")
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", tmp_path)

    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(id="user-1")
    client = TestClient(app)

    response = client.get("/api/skills/library")
    assert response.status_code == 200
    body = response.json()
    assert body["skills"][0]["compatible_agents"] == []


def test_every_catalog_entry_still_loads():
    """Real catalog (no monkeypatch) still parses fully with the new field.

    Deliberately NOT pinned to an exact count. This asserted ``== 182`` and had
    to be hand-edited every time a skill was added to ``backend/skills/global/``
    — which happens routinely, since attaching and removing skills is a normal
    authoring activity. The exact number was never the property under test: the
    loop below is, and a hard count only produced failures that said "someone
    added a skill", not "the catalog stopped parsing".

    The floor guards the case the count was really there for — a loader that
    silently returns [] would make the loop vacuously pass.
    """
    entries = list_global_skills()
    assert len(entries) > 100, f"catalog looks truncated: {len(entries)} entries"
    for entry in entries:
        assert isinstance(entry.compatible_agents, list)
