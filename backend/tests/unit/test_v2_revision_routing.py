"""Spec 022 §8 items 1-4, 6 and decision D1: prototype_v2 revision manifests, the
transcript-path contract between their steps, and the routing that picks them."""

from __future__ import annotations

import re
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from agents.execution_engine.engine import compile_for_run
from agents.registry import REVISION_BASE_MAP, get_pipeline_agents
from app.agents.chat.concierge import ProposalIntent
from app.agents.sandbox import agent_output_relpath
from app.api import run_commands as rc

FAST = "prototype_v2_revision"
DEPTH = "prototype_v2_feature_revision"
FAST_IDS = [
    "prototype-revision-analyzer",
    "custom-agent:v2-fix",
    "custom-agent:v2-validate",
]
DEPTH_IDS = [
    "prototype-revision-analyzer",
    "custom-agent:v2-specify",
    "custom-agent:v2-plan",
    "custom-agent:v2-build",
    "custom-agent:v2-validate",
]
_PATH_RE = re.compile(r"\.agents/\d\d-[A-Za-z0-9._-]+\.md")


def _relpaths(pipeline: str) -> dict[str, str]:
    steps = compile_for_run(pipeline).steps
    return {
        s.agent_id: agent_output_relpath(index=i, agent_id=s.agent_id)
        for i, s in enumerate(steps)
    }


# ── 1. manifests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pipeline,ids", [(FAST, FAST_IDS), (DEPTH, DEPTH_IDS)])
def test_manifest_step_order_and_deliverable(pipeline, ids):
    compiled = compile_for_run(pipeline)
    assert [s.agent_id for s in compiled.steps] == ids
    d = compiled.deliverable
    assert (d.strategy, d.name, d.revises_existing) == (
        "single_file",
        "prototype.html",
        True,
    )


@pytest.mark.parametrize("pipeline", [FAST, DEPTH])
def test_fix_and_build_have_no_gates_or_validators_and_playwright_only_where_expected(
    pipeline,
):
    steps = {s.agent_id: s for s in compile_for_run(pipeline).steps}
    for aid in ("custom-agent:v2-fix", "custom-agent:v2-build"):
        if aid in steps:
            assert not steps[aid].gates, aid
            assert not steps[aid].validators, aid
    if pipeline == DEPTH:
        assert steps["custom-agent:v2-build"].strategy == "single_shot"
    with_pw = {
        aid for aid, s in steps.items() if "playwright" in (s.tools.tool_sets or [])
    }
    expected = {"custom-agent:v2-validate"}
    if pipeline == FAST:
        expected.add("custom-agent:v2-fix")
    assert with_pw == expected


# ── 2. transcript contract ──────────────────────────────────────────────────


@pytest.mark.parametrize("pipeline", [FAST, DEPTH])
def test_every_transcript_path_in_a_prompt_is_an_earlier_step(pipeline):
    steps = compile_for_run(pipeline).steps
    found = 0
    for i, step in enumerate(steps):
        earlier = {
            agent_output_relpath(index=j, agent_id=steps[j].agent_id) for j in range(i)
        }
        for path in _PATH_RE.findall(step.prompt or ""):
            found += 1
            assert path in earlier, (step.agent_id, path)
    assert found >= 2


def test_fast_named_transcripts():
    rel = _relpaths(FAST)
    prompts = {s.agent_id: s.prompt for s in compile_for_run(FAST).steps}
    analyzer = rel["prototype-revision-analyzer"]
    assert analyzer == ".agents/01-prototype-revision-analyzer.md"
    assert analyzer in prompts["custom-agent:v2-fix"]
    assert rel["custom-agent:v2-fix"] in prompts["custom-agent:v2-validate"]


def test_depth_named_transcripts():
    rel = _relpaths(DEPTH)
    prompts = {s.agent_id: s.prompt for s in compile_for_run(DEPTH).steps}
    analyzer = rel["prototype-revision-analyzer"]
    assert analyzer == ".agents/01-prototype-revision-analyzer.md"
    assert analyzer in prompts["custom-agent:v2-specify"]
    assert rel["custom-agent:v2-specify"] in prompts["custom-agent:v2-plan"]
    plan = rel["custom-agent:v2-plan"]
    assert plan in prompts["custom-agent:v2-build"]
    assert plan in prompts["custom-agent:v2-validate"]


# ── fakes shared by 3-6 ─────────────────────────────────────────────────────


class _User:
    id = "u-1"
    preferred_model = None


class _Db:
    """Session double: every query resolves to a row-less result."""

    def __init__(self):
        self.added = []

    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return object()  # the parent exists

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def wired(monkeypatch):
    """Stub everything create_revision / the Concierge disposal touch; expose the
    tier the classifier returns and the mint kwargs captured."""
    state = {"tier": "small", "mint": None}

    async def _classify(instruction, parent_run_id, model_id=None):
        return state["tier"]

    def _mint(db, **kwargs):
        state["mint"] = kwargs
        return kwargs["pipeline_run_id"], "x_revision"

    async def _drive(**_kwargs):
        return None

    monkeypatch.setattr(rc, "_get_db", lambda: _Db())
    monkeypatch.setattr(rc, "_classify_revision_tier", _classify)
    monkeypatch.setattr(rc, "_mint_revision_row", _mint)
    monkeypatch.setattr(rc, "_drive_revision_to_queue", _drive)
    monkeypatch.setattr(rc, "_require_host_capacity", lambda _u: None)
    monkeypatch.setattr(rc, "effective_tier", lambda _u, _p: "enterprise")
    return state


async def _create(state, tier, target):
    state["tier"] = tier
    await rc.create_revision(
        "parent-1",
        rc.RevisionCommand(target_artifact_type=target, instruction="change it"),
        auth=(_User(), object()),
    )
    return state["mint"]["target_artifact_type"]


async def _dispose(state, tier, wr_type, target=None):
    state["tier"] = tier
    params = {"instruction": "change it"}
    if target is not None:
        params["target"] = target
    res = await rc._dispose_concierge_proposal(
        ProposalIntent(channel="revision", params=params),
        confirmed=True,
        store=None,
        art_store=None,
        run_id="parent-1",
        message_id="m-1",
        current_user=_User(),
        caller_tier="enterprise",
        wr_status="completed",
        wr_type=wr_type,
        gate_key=None,
        ectx=None,
    )
    assert res["disposed"] == "revision"
    return state["mint"]["target_artifact_type"]


V2_EXPECT = [
    ("small", "prototype_v2_output"),
    ("large", "prototype_v2_feature_output"),
    ("feature", "prototype_v2_feature_output"),
]
V1_EXPECT = [
    ("small", "prototype_output"),
    ("large", "prototype_large_output"),
    ("feature", "prototype_feature_output"),
]


# ── 3. create_revision ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,expected", V2_EXPECT)
async def test_create_revision_v2_parent_routes_by_tier(wired, tier, expected):
    assert await _create(wired, tier, "prototype_v2_output") == expected


# ── 4. Concierge disposal, v2 parent ────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [None, "prototype_output", "prototype_v2_output"])
@pytest.mark.parametrize("tier,expected", V2_EXPECT)
async def test_concierge_v2_parent_always_lands_on_v2_target(
    wired, tier, expected, target
):
    assert await _dispose(wired, tier, "prototype_v2", target) == expected


# ── 5. nested base ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("wr_type", [DEPTH, FAST])
@pytest.mark.parametrize("tier,expected", V2_EXPECT)
async def test_concierge_nested_v2_revision_parent_keeps_v2_base(
    wired, wr_type, tier, expected
):
    assert await _dispose(wired, tier, wr_type) == expected


def test_revision_base_map_v2():
    assert REVISION_BASE_MAP[DEPTH] == REVISION_BASE_MAP[FAST] == "prototype_v2"


# ── 6. v1 unchanged ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,expected", V1_EXPECT)
async def test_v1_create_revision_unchanged(wired, tier, expected):
    assert await _create(wired, tier, "prototype_output") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,expected", V1_EXPECT)
async def test_v1_concierge_unchanged(wired, tier, expected):
    assert await _dispose(wired, tier, "prototype", "prototype_output") == expected


# ── 7. D1: roster-or-manifest step count ────────────────────────────────────


@pytest.mark.parametrize(
    "pipeline",
    [
        "app_builder_revision",
        "custom_revision",
        "ppt_revision",
        "prototype_feature_revision",
        "prototype_large_revision",
        "prototype_revision",
        "user_stories_revision",
    ],
)
def test_existing_revisions_roster_equals_plan(pipeline):
    n = len(get_pipeline_agents(pipeline))
    assert (
        n == len(compile_for_run(pipeline).steps) == rc._compiled_step_count(pipeline)
    )


@pytest.mark.parametrize(
    "pipeline,count",
    [(FAST, 3), (DEPTH, 5), ("backlog_revision", 5), ("no_such_pipeline_revision", 0)],
)
def test_compiled_step_count(pipeline, count):
    assert rc._compiled_step_count(pipeline) == count


@pytest.fixture
def mint_env(monkeypatch):
    @contextmanager
    def _lock(*_a, **_k):
        yield

    monkeypatch.setattr(rc, "family_lock", _lock)
    monkeypatch.setattr(rc, "_revision_chain_root_id", lambda *_a, **_k: "root-1")
    monkeypatch.setattr(rc, "_has_active_chain_revision", lambda *_a, **_k: False)
    monkeypatch.setattr(rc, "can_run_pipeline", lambda *_a, **_k: (True, ""))
    return _Db()


@pytest.mark.parametrize(
    "target,pipeline,agents",
    [
        ("prototype_v2_output", FAST, 3),
        ("prototype_v2_feature_output", DEPTH, 5),
    ],
)
def test_mint_uses_compiled_step_count_when_roster_is_empty(
    mint_env, target, pipeline, agents
):
    run_id, ptype = rc._mint_revision_row(
        mint_env,
        user=_User(),
        caller_tier="enterprise",
        parent_run_id="parent-1",
        target_artifact_type=target,
        instruction="x",
    )
    assert ptype == pipeline
    (wr,) = mint_env.added
    assert wr.type == pipeline and wr.agent_count == agents and wr.id == run_id


def test_mint_refuses_pipeline_with_no_roster_and_no_manifest(mint_env):
    with pytest.raises(HTTPException) as exc:
        rc._mint_revision_row(
            mint_env,
            user=_User(),
            caller_tier="enterprise",
            parent_run_id="parent-1",
            target_artifact_type="no_such_pipeline_output",
            instruction="x",
        )
    assert exc.value.detail["code"] == "revision_unsupported"
    assert mint_env.added == []
