"""P27 E4 — ``skills_inline`` / ``skills_select`` step keys: compile + prompt composition."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.factory import (
    AgentContext,
    _compose_system_prompt,
    _build_inline_skill_blocks,
)
from agents.workflows import compiler as compiler_mod
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest

_SELECT = {
    "file": "goal/spec.json",
    "field": "kind",
    "map": {"web": ["sk-b"], "cli": ["sk-c"]},
}


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(
        compiler_mod, "_global_skill_ids", lambda: {"sk-a", "sk-b", "sk-c"}
    )


def _compile(**step_keys):
    step = {"agent": "step-x", **step_keys}
    m = WorkflowManifest(
        id="t",
        steps=[step],
        deliverable={"strategy": "single_file", "name": "o.html"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )
    return WorkflowCompiler().compile(m, CapabilityRegistry()).steps[0]


def test_compile_accepts_and_carries():
    step = _compile(skills=["x"], skills_inline=["sk-a"], skills_select=_SELECT)
    assert step.skills == ["x"]
    assert step.skills_inline == ["sk-a"]
    assert step.skills_select == _SELECT


def test_compile_absent_defaults():
    step = _compile()
    assert step.skills_inline == [] and step.skills_select is None


@pytest.mark.parametrize(
    "keys, needle",
    [
        ({"skills_inline": ["nope"]}, "nope"),
        ({"skills_inline": "sk-a"}, "skills_inline"),
        ({"skills_inline": [1]}, "skills_inline"),
        ({"skills_select": {"file": "a", "field": "b"}}, "exactly"),
        ({"skills_select": {"file": "a", "field": "b", "map": {}, "x": 1}}, "exactly"),
        (
            {"skills_select": {"file": "a", "field": "b", "map": {"v": "sk-a"}}},
            "list of skill ids",
        ),
        (
            {"skills_select": {"file": "a", "field": "b", "map": {"v": ["ghost"]}}},
            "ghost",
        ),
        ({"skills_select": {"file": "a", "field": "b", "map": []}}, "map"),
    ],
)
def test_compile_rejects(keys, needle):
    with pytest.raises(CompilerError) as exc:
        _compile(**keys)
    assert needle in str(exc.value)
    assert "step-x" in str(exc.value)


@dataclass
class _Spec:
    id: str = "agent"
    prompt_body: str = "BODY"
    guardrails: list = field(default_factory=list)
    injects: list = field(default_factory=list)


class _Sandbox:
    def __init__(self, root: Path):
        self.root = root

    def path_for(self, rel: str) -> Path:
        return self.root / rel


@dataclass
class _Entry:
    id: str
    content: str
    name: str = ""


@pytest.fixture
def skills(monkeypatch):
    import app.agents.skills_catalog as cat

    entries = [
        _Entry("sk-a", "A body"),
        _Entry("sk-b", "B body"),
        _Entry("sk-c", "C body"),
        _Entry("sk-inj", "pre {{INJECT_FROM:ctx/t.md}} post"),
    ]
    monkeypatch.setattr(cat, "list_global_skills", lambda: entries)


def _compose(ctx, sandbox):
    return _compose_system_prompt(
        _Spec(), ctx, inline_skill_blocks=_build_inline_skill_blocks(ctx, sandbox)
    )


def test_inline_bodies_in_order_before_body(skills, tmp_path):
    ctx = AgentContext(user_request="x", step_skills_inline=["sk-b", "sk-a"])
    out = _compose(ctx, _Sandbox(tmp_path))
    assert out == "## SKILL: sk-b\n\nB body\n\n## SKILL: sk-a\n\nA body\n\nBODY"


def test_inject_from_resolved(skills, tmp_path):
    (tmp_path / "ctx").mkdir()
    (tmp_path / "ctx/t.md").write_text("TEMPLATE\n")
    ctx = AgentContext(user_request="x", step_skills_inline=["sk-inj"])
    out = _compose(ctx, _Sandbox(tmp_path))
    assert "## SKILL: sk-inj\n\npre TEMPLATE post" in out
    assert "INJECT_FROM" not in out


def test_select_valid_appends_deduped(skills, tmp_path):
    (tmp_path / "goal").mkdir()
    (tmp_path / "goal/spec.json").write_text(json.dumps({"kind": "web"}))
    ctx = AgentContext(
        user_request="x",
        step_skills_inline=["sk-b", "sk-a"],
        step_skills_select=_SELECT,
    )
    out = _compose(ctx, _Sandbox(tmp_path))
    assert out == "## SKILL: sk-b\n\nB body\n\n## SKILL: sk-a\n\nA body\n\nBODY"
    ctx = AgentContext(user_request="x", step_skills_select=_SELECT)
    assert _compose(ctx, _Sandbox(tmp_path)) == "## SKILL: sk-b\n\nB body\n\nBODY"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "{not json",
        json.dumps({"other": 1}),
        json.dumps({"kind": "zzz"}),
        json.dumps([1]),
    ],
)
def test_select_falls_back_to_inline_only(skills, tmp_path, content):
    if content is not None:
        (tmp_path / "goal").mkdir()
        (tmp_path / "goal/spec.json").write_text(content)
    ctx = AgentContext(
        user_request="x", step_skills_inline=["sk-a"], step_skills_select=_SELECT
    )
    assert _compose(ctx, _Sandbox(tmp_path)) == "## SKILL: sk-a\n\nA body\n\nBODY"


def test_absent_keys_prompt_unchanged(tmp_path):
    ctx = AgentContext(user_request="x")
    assert _build_inline_skill_blocks(ctx, _Sandbox(tmp_path)) == []
    assert (
        _compose(ctx, _Sandbox(tmp_path))
        == _compose_system_prompt(_Spec(), ctx)
        == "BODY"
    )


@dataclass
class _BodyOnlySpec(_Spec):
    prompt_policy: str = "body_only"


@pytest.mark.parametrize("policy", ["body_only", "governance", "default"])
def test_inline_skills_reach_every_prompt_policy(skills, tmp_path, policy):
    """Regression (P27 run 3): custom-agent uses prompt_policy body_only, whose order had no
    skills slot, so goal-workflow agents never received their forced skills."""
    ctx = AgentContext(user_request="x", step_skills_inline=["sk-a"])
    spec = _BodyOnlySpec(prompt_policy=policy)
    out = _compose_system_prompt(
        spec,
        ctx,
        inline_skill_blocks=_build_inline_skill_blocks(ctx, _Sandbox(tmp_path)),
    )
    assert "## SKILL: sk-a\n\nA body" in out
    assert out.index("## SKILL: sk-a") < out.index("BODY")


def test_body_only_without_inline_skills_unchanged(tmp_path):
    ctx = AgentContext(user_request="x")
    assert _compose_system_prompt(_BodyOnlySpec(), ctx) == "BODY"
