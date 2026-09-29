"""tests/agents/test_seam2_gate_v3.py — Step 0 engine gate (GAPS §0.3 step 0, §1 P0 #8).

**Updated for Phase Z (GAPS §0.3 step N+1, "delete seam 2").** Every workflow
finished the Q4 migration (Phase M), so ``ExecutionEngine._compose_context_message``
no longer branches on ``prompt_policy`` at all — the ``if not _is_migrated:`` world-
block gates this file originally proved are GONE from engine.py, not merely closed.
What remains to prove: (a) a migrated agent (any non-default policy — every real
agent, always) still receives no WORLD block, and agent 1 still gets the brief; (c)
every built-in workflow the Phase-8 offline harness can run stays free of every
WORLD marker for its non-first agents; (d) the ``MIGRATED_WORKFLOWS`` roster (every
production workflow) is fully off ``default`` with a Sandbox Reading Guide on each
agent. The former test (b) — "both agents on `default`, the old blocks are
unchanged" — exercised ONLY the now-deleted default path and is removed rather than
converted: there is no code path left for it to drive (§0's evidence standard: a
test that can no longer reach the behaviour it names is dead, not green).

(a) uses the ``test_retry_recipients_v2.py`` full-composer pattern (direct
``_run_agent`` drives via ``_EngineHarness`` / ``_drive_agent`` / ``_make_ectx``).
(c) drives every built-in workflow the Phase-8 offline harness can run and checks
the real ``agent_input`` events. (d) is the ``MIGRATED_WORKFLOWS`` list Phase M
appended workflow ids to as it migrated them (batches composed entirely of the
shared ``custom-agent`` template go in ``TEMPLATE_COMPOSED_WORKFLOWS`` instead,
since ``get_pipeline_agents`` cannot see template-cloned steps — see M1 below).

Offline-safe: scripted model only (no Bedrock / Postgres / Chromium).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from types import SimpleNamespace

import re
import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads — keep this import first (test_retry_recipients_v2.py
# precedent).
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedFakeChatModel,
    _ScriptedTurn,
)
from tests.unit.agents.test_redo_gate_safety import (  # noqa: E402
    _EngineHarness,
    _drive_agent,
    _make_ectx,
)


# ---------------------------------------------------------------------------
# Marker list (GIT_VERSIONING_TASK.md §0 Rev 3 / GAPS §0.3 step 0) — none of
# these substrings may reach a migrated, non-first agent's context_message.
#
# Rev 3 correction: the uploaded-files marker is "## Uploaded Files" — the
# RENDERED HEADING the UploadedFilesProvider writes into the message value
# (uploaded_files.py:_compose returns
#   {"uploaded_files_context": "## Uploaded Files\n\n…"}
# ).  The dict key "uploaded_files_context" is a Python implementation detail
# that NEVER appears in any context_message, so asserting its absence is
# permanently vacuous.  The correct string to assert absent is the heading the
# agent would actually see if the provider pasted its output.
# ---------------------------------------------------------------------------
_WORLD_MARKERS = (
    "=== ORIGINAL USER REQUEST",
    "## Uploaded Files",       # rendered heading (Rev 3: was "uploaded_files_context")
    "ACTIVE DESIGN SYSTEM",
    "ACTIVE TEMPLATE",
    "TEMPLATE EXAMPLE",
    "--- Output from",
    "## Planning Context",
    # NOTE: "REVISION MODE" is deliberately NOT a world marker. That string lives in
    # the KAN-101 "SPEC KIT ANALYSIS REPORT (REVISION CONTEXT)" block, whose payload
    # is produced fresh at an update_specs gate click and handed to exactly the agent
    # that pass re-dispatches — a one-shot steering directive, i.e. CONTROL under
    # GAPS §0.2, like === ADDITIONAL INSTRUCTIONS (REVISE) === and === USER GUIDANCE ===.
    # GAPS FR-030 row 15 originally conflated it with the genuinely-world
    # "PRIOR ARTIFACT UNDER REVISION" block; the ledger is corrected there.
    # "PRIOR ARTIFACT UNDER REVISION" IS world state (the agent's own previous output,
    # also on disk) and retired for the FIX-217 spec-revision publisher in Phase M10,
    # at the same moment prototype-specify was granted read_files and told where to
    # read it (its own `.agents/01-prototype-specify.md`). It is STILL delivered on
    # the ISS-086 generic "Request changes" redo publisher, on purpose — see the
    # engine.py comment at the block itself (`_compose_context_message`, "D1: the
    # artifact UNDER revision") for why: `test_redo_prompt_contract.py` parametrizes
    # that publisher over already-migrated agents (domain-analyst, epic-architect) and
    # would regress if this marker were asserted absent unconditionally. `_seed_world_
    # signals` below seeds ONLY the FIX-217 shape (prior artifact, no redo_directive),
    # so the loop below correctly proves the retired half without asserting the
    # ISS-086 half away.
    "PRIOR ARTIFACT UNDER REVISION",
    "CURRENT PROTOTYPE HTML",
    "TEMPLATE COMPLIANCE",
)


def _turn(text: str) -> list[_ScriptedTurn]:
    return [_ScriptedTurn(texts=[text], usage=(5, 3))]


def _collect_context_messages(events: list[dict]) -> list[str]:
    return [
        ev["data"].get("context_message", "")
        for ev in events
        if ev.get("type") == "agent_input"
        and "context_message" in ev.get("data", {})
    ]


class _FakeUploadSandbox:
    """Minimal ``.uploads/`` disk stub (``sandbox.read(path)``) the real
    ``UploadedFilesProvider`` reads through ``ctx.runner.sandbox`` (V5's
    ``_FakeSandbox`` precedent, reimplemented locally so this file owns it).

    When ``_compose`` runs it would return
    ``{"uploaded_files_context": "## Uploaded Files\\n\\n<text>"}``; the value
    starts with the ``## Uploaded Files`` marker this file asserts absent from
    context_messages.  Seating this stub in ``ectx.runner.sandbox`` means the
    provider *could* produce that output — which is the correct shape for the
    (a)/(b) assertions to have any bite."""

    def __init__(self, name: str, text: str) -> None:
        self._manifest = json.dumps([{"name": name, "mime": "text/plain", "has_text": True}])
        self._sidecar_path = f".uploads/{name}.txt"
        self._text = text

    def read(self, path: str) -> str:
        if path == ".uploads/manifest.json":
            return self._manifest
        if path == self._sidecar_path:
            return self._text
        raise FileNotFoundError(path)


def _seed_world_signals(ectx) -> None:
    """Populate every world-input signal the row names: uploads, od_context,
    planning context (via ``_drive_agent``'s own default), upstream output (via
    the real domain-analyst→epic-architect produces/consumes edge) and revision
    mode. Shared by the (a) migrated and (b) default-policy tests so they differ
    ONLY in agent 2's ``prompt_policy``."""
    ectx.gate_agent_ids = []
    ectx.compiled_context_providers = ["opendesign", "uploaded_files"]
    ectx.od_context = {
        "ds_id": "acme",
        "ds_body": "Design tokens body.",
        "template_id": "web-basic",
        "template_body": "Template body text.",
    }
    ectx.runner = SimpleNamespace(
        sandbox=_FakeUploadSandbox("brief.txt", "Uploaded document body text.")
    )
    ectx.spec_revision_context = "Fix the login page duplication."
    # FIX-217 shape (M10): a prior artifact with no redo_directive — the spec-revision
    # (update_specs) publisher, the one Phase M10 retires for a migrated agent. Leaving
    # ectx.redo_directive unset (empty) is what selects this shape over ISS-086's redo
    # shape — see the engine.py comment at the PRIOR ARTIFACT UNDER REVISION block.
    ectx.spec_revision_prior_artifact = "Previous spec draft under revision."


# ---------------------------------------------------------------------------
# (a) A migrated agent 2 (body_only) receives NO world block; agent 1 (index 0,
#     the existing brief-to-agent-1 gate) still gets the brief regardless.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_migrated_agent_gets_no_world_blocks_agent1_keeps_brief() -> None:
    from agents.loader import load_agent_spec

    spec_a = load_agent_spec("domain-analyst")  # agent 1 — brief always reaches it
    spec_b = dataclasses.replace(
        load_agent_spec("epic-architect"),  # agent 2 — flip the switch for this test
        prompt_policy="body_only",
        injects=["design_system", "template", "uploaded_files"],
    )

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output text"))
    ) as h:
        ectx = _make_ectx("s0-migrated-run")
        _seed_world_signals(ectx)

        results: list[dict] = []
        ordered = [spec_a, spec_b]
        events_a = await _drive_agent(h.engine, spec_a, ectx, results, ordered, index=0)
        events_b = await _drive_agent(h.engine, spec_b, ectx, results, ordered, index=1)

    msgs_a = _collect_context_messages(events_a)
    msgs_b = _collect_context_messages(events_b)

    assert msgs_a and "=== ORIGINAL USER REQUEST ===" in msgs_a[0], (
        "agent 1 must still get the brief (existing gate, unaffected by Step 0)"
    )

    assert msgs_b, "agent 2 produced no agent_input event"
    for marker in _WORLD_MARKERS:
        assert marker not in msgs_b[0], (
            f"migrated (body_only) agent 2's message leaked world-block marker {marker!r}"
        )


# ---------------------------------------------------------------------------
# (b) [Phase Z] Converted, not deleted — the original (b) put both agents on
#     `default` and asserted the OLD blocks were still pasted (proving Step 0's
#     gate left the pre-migration path byte-identical). That path no longer
#     exists in engine.py at all, so there is nothing left for that assertion
#     to drive. What (b) proves now is the Phase Z claim itself (policy.py's
#     "seam 2 no longer varies by policy" doc note): an agent explicitly on
#     `prompt_policy=None` (the `default` name, still valid for seam 1 / the
#     system prompt) gets EXACTLY the same seam-2 treatment as a migrated
#     agent — no world block, no branch on policy at all.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_default_policy_agent2_also_gets_no_world_blocks() -> None:
    from agents.loader import load_agent_spec

    spec_a = dataclasses.replace(load_agent_spec("domain-analyst"), prompt_policy=None)
    spec_b = dataclasses.replace(
        load_agent_spec("epic-architect"),
        prompt_policy=None,
        injects=["design_system", "template", "uploaded_files"],
    )

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_turn("output text"))
    ) as h:
        ectx = _make_ectx("s0-default-run")
        _seed_world_signals(ectx)

        results: list[dict] = []
        ordered = [spec_a, spec_b]
        events_a = await _drive_agent(h.engine, spec_a, ectx, results, ordered, index=0)
        events_b = await _drive_agent(h.engine, spec_b, ectx, results, ordered, index=1)

    msgs_a = _collect_context_messages(events_a)
    msgs_b = _collect_context_messages(events_b)

    assert msgs_a and "=== ORIGINAL USER REQUEST ===" in msgs_a[0], (
        "agent 1 must still get the brief regardless of policy (existing gate)"
    )

    assert msgs_b, "agent 2 produced no agent_input event"
    for marker in _WORLD_MARKERS:
        assert marker not in msgs_b[0], (
            f"default-policy agent 2's message leaked world-block marker {marker!r} "
            "— seam 2 must not vary by prompt_policy after Phase Z"
        )


# ---------------------------------------------------------------------------
# (c) Every built-in workflow the Phase-8 offline harness can drive: for every
#     agent_input event, a migrated non-first agent leaks no marker; the first
#     agent always carries the brief. Undrivable workflows are skipped with a
#     reason (see the journal for the full list + why).
# ---------------------------------------------------------------------------

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ALL_WORKFLOW_IDS = sorted(
    p.parent.name for p in (_BACKEND_ROOT / "agents" / "workflows").glob("*/workflow.yaml")
)

# The only pipeline_types the Phase-8 offline harness (test_phase8_live.py) drives
# through the ENGINE world (drive_engine_pipeline) with a ScriptedFakeChatModel.
_REPO_INPUT_CODEGEN = {"mulesoft_to_springboot", "dotnet_to_azure"}


def _skip_reason(workflow: str) -> str | None:
    if workflow in {"user_stories", "prototype", "prototype_revision", "app_builder", "ppt"}:
        return None
    if workflow in _REPO_INPUT_CODEGEN:
        return (
            f"{workflow}: repo-input code-gen — test_phase8_live.py documents this as "
            "undrivable offline (no synthetic brief produces a faithful deliverable)"
        )
    if workflow == "chat":
        return (
            "chat: test_phase8_live.py's _run_chat drives the free-chat ChatRunner via "
            "drive_chat (a different world/event vocabulary), not drive_engine_pipeline"
        )
    return f"{workflow}: no Phase-8 offline engine-world helper defined in test_phase8_live.py"


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", _ALL_WORKFLOW_IDS)
async def test_workflow_agents_free_of_world_blocks(workflow: str) -> None:
    reason = _skip_reason(workflow)
    if reason:
        pytest.skip(reason)

    from agents.loader import load_agent_spec
    from tests.e2e.agents.test_phase8_live import (
        _per_agent_factory,
        _revision_model_factory,
        _run_app_builder,
        _run_prototype,
        _run_prototype_revision,
        _run_ppt,
        _run_user_stories,
        _text_model,
    )

    if workflow == "prototype_revision":
        parent = await _run_prototype(model=_per_agent_factory, fake_planner=True)
        assert parent.completed, f"prototype_revision needs a completed parent run: {parent.error}"
        result = await _run_prototype_revision(
            model=_revision_model_factory, parent_run_id=parent.run_id, fake_planner=True,
        )
    elif workflow == "user_stories":
        result = await _run_user_stories(model=_text_model(), fake_planner=True)
    elif workflow == "prototype":
        result = await _run_prototype(model=_per_agent_factory, fake_planner=True)
    elif workflow == "app_builder":
        result = await _run_app_builder(model=_per_agent_factory, fake_planner=True)
    else:  # ppt
        result = await _run_ppt(model=_per_agent_factory, fake_planner=True)

    assert result.completed, f"{workflow} offline drive did not complete: {result.error}"
    agent_inputs = result.events_of("agent_input")
    assert agent_inputs, f"{workflow} emitted no agent_input events"
    first_agent_id = agent_inputs[0]["data"]["agent_id"]

    for ev in agent_inputs:
        agent_id = ev["data"]["agent_id"]
        msg = ev["data"].get("context_message", "")
        spec = load_agent_spec(agent_id)
        policy = getattr(spec, "prompt_policy", None) or "default"
        if policy != "default" and agent_id != first_agent_id:
            for marker in _WORLD_MARKERS:
                assert marker not in msg, (
                    f"{workflow}/{agent_id} (prompt_policy={policy}) leaked {marker!r}"
                )
        if agent_id == first_agent_id:
            assert "=== ORIGINAL USER REQUEST ===" in msg, (
                f"{workflow}: first agent {agent_id} is missing the brief"
            )


# ---------------------------------------------------------------------------
# (d) Fully-migrated workflows — Phase M appends workflow ids here as it lands
#     each batch. Empty today ⇒ this collects zero test instances (by design).
#
# TEMPLATE_COMPOSED_WORKFLOWS (M1): every step of these workflows is a
# `custom-agent:<instance_id>` clone of the one shared, blank template at
# `agents/prompts/custom-agent/AGENT.md` (`template: true`). `list_agent_ids`
# / `get_pipeline_agents` deliberately EXCLUDE `template: true` specs from
# every roster (registry.py:204-211, "a composed manifest's steps ARE those
# instances, so completing the roster from the manifest must honour the same
# rule or every composed workflow grows a phantom custom-agent member") — so
# `get_pipeline_agents(workflow)` is `[]` for these by design, not because
# they are unmigrated. `gaps-hello-chain` is DB-backed (no on-disk manifest
# at all, see harness fact E2), so there is no per-workflow file to inspect
# regardless of mechanism. For this batch "migrated" can only mean "the
# shared template is migrated" — verified directly against
# `load_agent_spec("custom-agent")`, confirmed by reading every workflow.yaml
# in the batch (all steps are `agent: custom-agent`, no other agent mixed
# in). Every other workflow keeps the original `get_pipeline_agents` roster
# check and its `assert agents` guard unchanged, so a typo'd/unmigrated
# per-workflow id still fails loudly.
# ---------------------------------------------------------------------------

TEMPLATE_COMPOSED_WORKFLOWS: frozenset[str] = frozenset(
    {
        "ex_A1_loop",
        "ex_A2_branch",
        "ex_A3_b_spanish",
        "ex_A3_c_dutch",
        "ex_A3_divert",
        "ex_A4_human_divert",
        "ex_A4_human_gate",
        "sample_subagents_parallel",
        "gaps-hello-chain",
    }
)

# AGENTLESS_WORKFLOWS (M3): `sample_fanout` and `sample_wave` declare steps for
# `sample-fanout-plan`/`sample-fanout-worker` and `sample-wave-plan`/`sample-wave-worker`,
# none of which have an AGENT.md on disk — each workflow.yaml says so itself
# ("NOT launchable ... have no AGENT.md on disk, so a launch raises
# FileNotFoundError building the roster. Declared as DATA rather than hidden by
# a name list (SC-001 / ADR-0005)."). `get_pipeline_agents` skips any manifest
# step whose AGENT.md fails to load (registry.py `except (FileNotFoundError,
# AgentSpecError): continue`), so it returns `[]` for both — "this pipeline
# exists and has no agents" (registry.py's own docstring), not a hidden bug.
# There is therefore no AGENT.md in this batch to set `prompt_policy` on or add
# a guide to; "fully migrated" is vacuously true. Asserting the roster stays
# empty (instead of just listing them with no assertion) means a future
# AGENT.md added for either agent id fails this test loudly rather than
# silently reintroducing an unmigrated default-policy agent.
#
# `reverse_engineer` (M11): a different shape of the same "no AGENT.md" fact —
# its manifest declares `steps: []` outright (no step names at all), and
# `agents/registry.py::_discover_pipeline_agents`'s own docstring names it as
# the reason PIPELINE_AGENTS keeps an empty list here instead of a KeyError
# ("`reverse_engineer` (a manifest with no agents) ... have no AGENT.md
# declaring them, so they vanished from the dict entirely"). No AGENT.md
# declares `pipeline_type: reverse_engineer`, so `get_pipeline_agents` returns
# `[]` — same vacuous-migration shape as `sample_fanout`/`sample_wave` above.
AGENTLESS_WORKFLOWS: frozenset[str] = frozenset(
    {"sample_fanout", "sample_wave", "reverse_engineer"}
)

MIGRATED_WORKFLOWS: list[str] = sorted(
    TEMPLATE_COMPOSED_WORKFLOWS
    | AGENTLESS_WORKFLOWS
    | {
        "user_stories",
        "user_stories_revision",
        "sc001-test-fixture",
        "ex_playwright_smoke_test",
        "custom",
        "custom_revision",
        "chat",
        "dotnet_to_azure",
        "mulesoft_to_springboot",
        "ppt",
        "ppt_v2",
        "ppt_revision",
        "app_builder",
        "app_builder_revision",
        # M10 (GAPS §0.3/§1 P1 Q4 rollout, cheapest-first ... prototype last):
        # prototype + its three revision variants, all migrated together (shared
        # prompts move once, recipe rule 5).
        "prototype",
        "prototype_revision",
        "prototype_feature_revision",
        "prototype_large_revision",
        # M11: every remaining on-disk AGENT.md with no `prompt_policy` lives
        # under `pipeline_type: spec_kit` (the 7 orphans — constitution-agent,
        # specify-agent, clarify-agent, research-agent, plan-agent, tasks-agent,
        # analyze-agent — none referenced by any `workflow.yaml` step; plus
        # `deep-planner`, already migrated). `spec_kit` has no
        # `agents/workflows/spec_kit/workflow.yaml`, so it is a valid
        # `SUPPORTED_PIPELINE_TYPES` key with a non-empty on-disk roster and no
        # manifest to dispatch it — unlike `reverse_engineer` above, this is the
        # ordinary (non-agentless) branch below.
        "spec_kit",
    }
)


@pytest.mark.parametrize("workflow", MIGRATED_WORKFLOWS)
def test_workflow_fully_migrated(workflow: str) -> None:
    from agents.loader import load_agent_spec
    from agents.registry import get_pipeline_agents

    if workflow in TEMPLATE_COMPOSED_WORKFLOWS:
        agents = [load_agent_spec("custom-agent")]
    elif workflow in AGENTLESS_WORKFLOWS:
        agents = get_pipeline_agents(workflow)
        assert agents == [], (
            f"{workflow}: expected no on-disk agents (AGENTLESS_WORKFLOWS) but "
            f"found {[a.id for a in agents]} — update the comment/assertion above"
        )
        return
    else:
        agents = get_pipeline_agents(workflow)
        assert agents, f"{workflow}: no agents found in the registry"
    for spec in agents:
        policy = getattr(spec, "prompt_policy", None) or "default"
        assert policy != "default", (
            f"{workflow}/{spec.id}: still on the default prompt_policy"
        )
        assert "## Sandbox Reading Guide" in (spec.prompt_body or ""), (
            f"{workflow}/{spec.id}: AGENT.md is missing the Sandbox Reading Guide"
        )


# ---------------------------------------------------------------------------
# LB3-fix (journal/LB3-fix.md): a migrated agent's Sandbox Reading Guide is
# the ONLY thing that reaches it for a prior step's output — the "Include the
# brief when: default policy, OR agent 1, OR Req 14 retry" branch above means
# every OTHER dispatch gets ``parts = []`` (see the "later agents read context
# from .agents/ files" comment on that branch). So the guide's table has to
# name a path the agent's own read tool can ACTUALLY open.
#
# It cannot, for any ``.agents/NN-*.md`` path: ``AGENT_READABLE_RESERVED``
# (app/agents/sandbox.py) contains only ``.context/`` — ``.agents/`` was never
# added — so ``_ReservedPathGuardMiddleware`` refuses that read unconditionally,
# regardless of how the prompt is worded. This is why ppt-composer made ZERO
# tool calls on the LB3 run (it never got the spec) and is orthogonal to model
# quality. ppt-composer/ppt-brief-analyst were re-pointed at ``brief-spec.md``,
# a plain sandbox-root file (not under any RESERVED_PATHS prefix, so both
# read_file and write_file reach it unconditionally) that ppt-brief-analyst
# now ALSO write_file's alongside its unchanged ``<spec>`` stream.
#
# The other 54 migrated agents whose guide still names an unreadable
# ``.agents/`` path are OUT OF SCOPE for this fix (the real fix is one line —
# adding ``.agents/`` to ``AGENT_READABLE_RESERVED`` — but that file was not
# in this task's authorized scope). ``test_known_broken_guide_targets_do_not_grow``
# below is a ratchet, not a fix: it fails if the defect SPREADS to a new
# agent, and never fails when an agent is fixed off the list.
# ---------------------------------------------------------------------------

import re  # noqa: E402

from app.agents.sandbox import AGENT_READABLE_RESERVED, RESERVED_PATHS  # noqa: E402

_GUIDE_TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def _sandbox_reading_guide_section(body: str) -> str:
    m = re.search(r"## Sandbox Reading Guide\b(.*?)(?=\n## |\Z)", body, re.DOTALL)
    return m.group(1) if m else ""


def _declared_agents_dir_targets(body: str) -> list[str]:
    """``.agents/NN-*.md`` paths the agent's OWN guide table names as required reads."""
    guide = _sandbox_reading_guide_section(body)
    return [p for p in _GUIDE_TABLE_ROW.findall(guide) if p.startswith(".agents/")]


def _tool_can_read(path: str) -> bool:
    """Reproduces ``_ReservedPathGuardMiddleware._is_reserved`` /
    ``_is_agent_readable`` (app/agents/deep_agent_runner.py) against the real,
    imported registries — so this drifts with the middleware, never a copy."""

    def _under_any(norm: str, entries: frozenset[str]) -> bool:
        return any(
            norm == e.rstrip("/") or norm.startswith(e.rstrip("/") + "/") or norm.startswith(e)
            for e in entries
        )

    norm = path.lstrip("/")
    if norm.startswith("./"):
        norm = norm[2:]
    if not _under_any(norm, RESERVED_PATHS):
        return True
    return _under_any(norm, AGENT_READABLE_RESERVED)




def _iter_migrated_agent_files():
    """Every `AGENT.md` carrying a non-default `prompt_policy`."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "agents" / "prompts"
    for md in sorted(root.glob("*/AGENT.md")):
        head = md.read_text(encoding="utf-8")[:2000]
        if re.search(r"^prompt_policy:\s*(body_only|governance)\s*$", head, re.M):
            yield md


class TestGuideTargetsAreToolReadable:
    """A migrated prompt's reading guide must name paths its tools can actually open.

    History: the Q4 migration moved upstream agent output out of the message and
    into `.agents/NN-<agent-id>.md`, and 81 migrated guides name that path — but
    the reserved-path guard only allowed `.context/`, so every one of those reads
    was refused and the migration was inert. A live `ppt_v2` run on a real model
    exposed it: the composer made no tool call at all and the run produced no
    deliverable. The fix is one entry in `AGENT_READABLE_RESERVED`
    (`app/agents/sandbox.py`); the canonical read-allowed / write-refused
    contract lives in `test_reserved_path_registry.py`. These tests guard the
    property that matters here: **no migrated guide may point at a path the
    agent cannot read.**
    """

    def test_agents_dir_is_agent_readable(self) -> None:
        """`.agents/` is readable — without this the whole migration is inert."""
        from app.agents.sandbox import AGENT_READABLE_RESERVED

        assert ".agents/" in AGENT_READABLE_RESERVED
        assert _tool_can_read(".agents/01-anything.md")

    def test_agents_dir_is_not_agent_writable(self) -> None:
        """Read access must not have granted write access."""
        from app.agents.sandbox import RESERVED_PATHS

        assert ".agents/" in RESERVED_PATHS

    def test_no_migrated_guide_names_an_unreadable_path(self) -> None:
        """Every path a migrated guide names must be tool-readable.

        This is the general form of the defect the live run found. It covers all
        94 prompts, not the one pair that happened to fail first.
        """
        offenders: dict[str, set[str]] = {}
        for md in _iter_migrated_agent_files():
            body = md.read_text(encoding="utf-8")
            bad = {
                path
                for path in re.findall(r"`([.][A-Za-z][\w./*-]*)`", body)
                if not _tool_can_read(path.rstrip("*/"))
            }
            if bad:
                offenders[md.parent.name] = bad
        assert not offenders, (
            "these migrated prompts tell an agent to read a path its tools refuse: "
            + "; ".join(f"{k}: {sorted(v)}" for k, v in sorted(offenders.items()))
        )
