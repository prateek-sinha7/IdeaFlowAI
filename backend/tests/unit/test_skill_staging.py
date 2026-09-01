"""tests/unit/test_skill_staging.py — behavioral coverage for skill_staging.stage_skills.

Verifies the synthesized SKILL.md frontmatter round-trips through
``frontmatter.loads``, idempotence (no rewrite on a second identical call),
description clamping at 1024 chars, id-traversal rejection, and the
``est_tokens`` formula (464 + 66 * len(staged)).
"""

from __future__ import annotations

import frontmatter
import pytest

from app.agents.sandbox import RunSandbox
from app.agents.skill_staging import SkillsDelivery, stage_skills


def _sandbox(tmp_path):
    sb = RunSandbox("user", "run", runs_root=str(tmp_path))
    sb.ensure()
    return sb


def test_empty_payload_is_inert(tmp_path):
    sb = _sandbox(tmp_path)
    result = stage_skills(sb, None)
    assert result == SkillsDelivery([], [], [], 0)
    assert not (sb.root / "skills").exists()

    result = stage_skills(sb, [])
    assert result == SkillsDelivery([], [], [], 0)
    assert not (sb.root / "skills").exists()


def test_one_skill_writes_valid_frontmatter(tmp_path):
    sb = _sandbox(tmp_path)
    result = stage_skills(sb, [{"id": "my-skill", "name": "My Skill", "content": "Do the thing."}])

    assert result.staged == ["my-skill"]
    assert result.sources == ["/skills"]
    assert result.errors == []

    skill_file = sb.root / "skills" / "my-skill" / "SKILL.md"
    assert skill_file.exists()

    post = frontmatter.loads(skill_file.read_text(encoding="utf-8"))
    assert post.metadata["name"] == "my-skill"
    assert post.content.strip() == "Do the thing."


def test_staging_twice_is_idempotent(tmp_path):
    sb = _sandbox(tmp_path)
    payload = [{"id": "my-skill", "name": "My Skill", "content": "Do the thing."}]

    first = stage_skills(sb, payload)
    skill_file = sb.root / "skills" / "my-skill" / "SKILL.md"
    mtime_before = skill_file.stat().st_mtime_ns

    second = stage_skills(sb, payload)
    mtime_after = skill_file.stat().st_mtime_ns

    assert first == second
    assert mtime_after == mtime_before


def test_empty_content_is_skipped(tmp_path):
    sb = _sandbox(tmp_path)
    result = stage_skills(sb, [{"id": "empty", "name": "Empty", "content": "   "}])

    assert result.staged == []
    assert result.sources == []
    assert len(result.errors) == 1


def test_long_description_is_clamped(tmp_path):
    sb = _sandbox(tmp_path)
    payload = [
        {
            "id": "long-desc",
            "name": "x" * 1500,
            "content": "Body.",
        }
    ]
    result = stage_skills(sb, payload)

    assert result.staged == ["long-desc"]
    assert any("clamp" in e for e in result.errors)

    skill_file = sb.root / "skills" / "long-desc" / "SKILL.md"
    post = frontmatter.loads(skill_file.read_text(encoding="utf-8"))
    assert len(post.metadata["description"]) == 1024


def test_traversal_id_is_rejected(tmp_path):
    sb = _sandbox(tmp_path)
    parent_before = sorted(p.name for p in sb.base.iterdir())

    result = stage_skills(sb, [{"id": "../escape", "name": "escape", "content": "Body."}])

    assert result.staged == []
    assert len(result.errors) == 1

    parent_after = sorted(p.name for p in sb.base.iterdir())
    assert parent_after == parent_before


def test_est_tokens_formula(tmp_path):
    sb = _sandbox(tmp_path)
    one = stage_skills(sb, [{"id": "a", "name": "a", "content": "x"}])
    assert one.est_tokens == 530

    sb2 = _sandbox(tmp_path.parent / (tmp_path.name + "-two"))
    three = stage_skills(
        sb2,
        [
            {"id": "a", "name": "a", "content": "x"},
            {"id": "b", "name": "b", "content": "y"},
            {"id": "c", "name": "c", "content": "z"},
        ],
    )
    assert three.est_tokens == 662


def test_yaml_metacharacter_id_is_rejected(tmp_path):
    """Test that an id with YAML metacharacters is safely rejected."""
    sb = _sandbox(tmp_path)
    result = stage_skills(sb, [{"id": "evil: name", "name": "Evil", "content": "Body."}])

    assert result.staged == []
    assert result.sources == []
    assert len(result.errors) == 1
    assert "unsafe skill id" in result.errors[0]

    # Verify no file was written for the unsafe id
    skills_dir = sb.root / "skills"
    if skills_dir.exists():
        assert not any("evil" in child.name for child in skills_dir.iterdir())


def test_step_skills_narrow_staging_to_that_agent(tmp_path, monkeypatch):
    """AC-04: agent A declaring skills:[x] gets exactly x staged; sibling agent
    B declaring no per-step skills falls back to the run-level attached list
    (spec 012 / R-01, D-03)."""
    from agents.factory import _resolve_step_skills
    from app.agents import skills_catalog

    catalog_entry = skills_catalog.GlobalSkillEntry(
        id="x",
        name="X Skill",
        display_name="X Skill",
        description="Does x.",
        content="Do the x thing.",
        isBeta=False,
    )
    monkeypatch.setattr(skills_catalog, "list_global_skills", lambda: [catalog_entry])

    run_level_skills = [{"id": "run-level", "name": "Run Level", "content": "Run-level body."}]

    # Agent A: step_skills = ["x"] → resolved via the catalog, narrowed to exactly x.
    sandbox_a = _sandbox(tmp_path / "a")
    a_skills = _resolve_step_skills(["x"])
    delivery_a = stage_skills(sandbox_a, a_skills, agent_id="agent-a")
    assert delivery_a.staged == ["x"]

    # Agent B: no per-step skills → falls back to the run-level attached list.
    sandbox_b = _sandbox(tmp_path / "b")
    b_skills = run_level_skills  # ctx.step_skills is empty, so factory uses ctx.attached_skills
    delivery_b = stage_skills(sandbox_b, b_skills, agent_id="agent-b")
    assert delivery_b.staged == ["run-level"]

    assert "run-level" not in delivery_a.staged
    assert "x" not in delivery_b.staged


@pytest.mark.issue("ISS-185")
def test_staged_skill_carries_its_referenced_sibling_files(tmp_path):
    """ISS-185 — a skill whose SKILL.md body tells the agent to read a sibling
    file ("`root-cause-tracing.md` in this directory") must have that file land
    next to the staged SKILL.md, or the agent's `ls`/`read_file` at the mount
    point it was told to use comes back empty. `stage_skills` today writes only
    the synthesized SKILL.md and never the catalog folder's other files."""
    from app.agents import skills_catalog

    skills_catalog.clear_cache()
    catalog_entry = next(
        e for e in skills_catalog.list_global_skills() if e.id == "systematic-debugging"
    )
    assert "root-cause-tracing.md" in catalog_entry.content  # sanity: body really references it

    sb = _sandbox(tmp_path)
    result = stage_skills(
        sb,
        [{"id": catalog_entry.id, "name": catalog_entry.name, "content": catalog_entry.content}],
    )

    assert result.staged == ["systematic-debugging"]
    referenced_sibling = sb.root / "skills" / "systematic-debugging" / "root-cause-tracing.md"
    assert referenced_sibling.exists(), (
        "SKILL.md tells the agent to read root-cause-tracing.md 'in this directory' "
        "but stage_skills never staged it there"
    )


def test_skill_name_in_frontmatter_is_properly_quoted(tmp_path):
    """Test that the skill_id is properly quoted in frontmatter and parses correctly."""
    sb = _sandbox(tmp_path)
    skill_id = "my-skill"
    result = stage_skills(sb, [{"id": skill_id, "name": "My Skill", "content": "Test body."}])

    assert result.staged == [skill_id]
    assert result.errors == []

    skill_file = sb.root / "skills" / skill_id / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    # Verify the file content has the name properly quoted
    assert 'name: "my-skill"' in content

    # Verify frontmatter.loads parses it correctly and the name equals the skill_id
    post = frontmatter.loads(content)
    assert post.metadata["name"] == skill_id
