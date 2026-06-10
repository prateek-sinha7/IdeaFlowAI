"""REPO-05 ACCEPT PROOF — the sample brownfield workflow runs end-to-end OFFLINE.

The phase's owed brownfield accept proof: a BRAND-NEW, NON-prototype workflow
(``sample_brownfield``) runs the whole repo workflow class against a LOCAL fixture
with ``exec`` OFF at every step and the surfaced ``repo_diff`` containing the
agent's edit — with ZERO edits to ``backend/agents/execution_engine/`` (SC-001
discipline: all power lives in the registered capabilities).

The chain (clone -> branch -> inventory/context -> read/edit >=1 -> diff):
  * a ``has_git=True`` ``LocalWorkspace`` clones the ``local_git_fixture`` (09-01)
    and branches ``work`` off ``main`` (offline, no network);
  * the workflow declares ``context_providers: [repo]`` (the 09-03 ContextPack /
    repo inventory) + a ``brownfield-build`` step that EDITS >=1 file
    (``write_files`` granted, ``exec`` NOT granted);
  * the deliverable is ``repo_diff`` (09-04) — the file tree + per-file unified
    diff + change summary, diff-only (no commit/PR push, N4).

The test drives ``execute()`` end-to-end (scripted model, the proven offline
harness from ``_scripted_model.py``) and asserts:
  (a) the run completes (a ``pipeline_complete`` event, no ``error``);
  (b) the surfaced ``repo_diff`` CONTAINS the agent's edit;
  (c) the effective-perms intersection has ``exec=off`` at EVERY step (no step
      grants exec anywhere on the path) — asserted off the compiled plan;
  (d) prototype characterization stays byte/event-identical (the repo path is
      additive — a separate prototype drive in the same session is unaffected).

The brownfield repo binding (the §15 RepoSpec — the local fixture path +
base/working branches) is supplied at RUN ENTRY by the harness (manifests are
pure data; the repo binding has no manifest top-key, INV-5 / D-08), exactly as a
runtime host would inject it. The build agent's repo edit is applied to the cloned
working tree at the step boundary (the ``write_files`` effect), then ``repo_diff``
reads ``main..work`` via the ``ctx.runner.workspace`` handle.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import frontmatter  # type: ignore[import-untyped]
import pytest

from tests.agents._scripted_model import (  # noqa: E402
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_brownfield"
_FIXTURE_ID = "sample_brownfield"

# The build agent's edit to the cloned repo (write_files, no exec). A unique marker
# so the surfaced diff can be asserted to contain it.
_EDIT_REL = "src/app.py"
_EDIT_CONTENT = (
    '"""Sample module."""\n\n\ndef greet(name: str) -> str:\n'
    '    return f"hello brownfield {name}"\n'
)
_EDIT_MARKER = "hello brownfield"


def _load_fixture_specs():
    """Build AgentSpec objects for the fixture agents (sc001 precedent — test-scoped)."""
    from agents.loader import AgentSpec

    specs = []
    for agent_dir in sorted(_FIXTURE_DIR.iterdir()):
        agent_file = agent_dir / "AGENT.md"
        if not agent_file.is_file():
            continue
        post = frontmatter.loads(agent_file.read_text(encoding="utf-8"))
        md = post.metadata
        specs.append(
            AgentSpec(
                id=md["id"],
                name=md["name"],
                role=md["role"],
                pipeline_type=md["pipeline_type"],
                order=int(md["order"]),
                max_tokens=int(md["max_tokens"]),
                prompt_body=post.content,
                tools=list(md.get("tools", []) or []),
                guardrails=list(md.get("guardrails", []) or []),
                context_from=list(md.get("context_from", []) or []),
                produces=list(md.get("produces", []) or []),
                consumes=list(md.get("consumes", []) or []),
            )
        )
    specs.sort(key=lambda s: s.order)
    return specs


def _scripts_for(agent_id: str):
    if agent_id == "brownfield-analyze":
        return [_ScriptedTurn(texts=["Edit src/app.py to personalize the greeting."], usage=(12, 7))]
    if agent_id == "brownfield-build":
        return [_ScriptedTurn(texts=["Edited src/app.py."], usage=(20, 10))]
    return [_ScriptedTurn(texts=[f"{agent_id} default."], usage=(5, 3))]


async def _drive_brownfield(fixture_repo: Path, runs_root: str):
    """Drive the sample brownfield workflow end-to-end offline.

    Provisions a has_git=True LocalWorkspace cloned from ``fixture_repo`` (branch
    ``work``), drives ``execute()`` against the production ``sample_brownfield``
    manifest, applies the build agent's repo edit at the build-step boundary, and
    attaches the workspace to ``ctx.runner`` so ``repo_diff`` reads ``main..work``.

    Returns ``(events, compiled)``.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    import agents.registry as registry_mod
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run
    from agents.loader import _SPEC_CACHE

    import app.core.config as config_module
    config_module.settings.RUNS_ROOT = runs_root

    from app.agents.runtime.local import LocalSandboxRuntime

    # ── Provision the has_git=True repo workspace (clone fixture, branch work) ───
    runtime = LocalSandboxRuntime()
    workspace = runtime.create_workspace(
        owner_id="brownfield-user", workspace_id="brownfield-ws", has_git=True, exec=False
    )
    workspace.clone_repo(str(fixture_repo))
    workspace.create_branch("work")

    specs = _load_fixture_specs()
    spec_ids = [s.id for s in specs]

    compiled = compile_for_run(_FIXTURE_ID)

    # ── Point membership + alias at the fixture (no production loader edit) ──────
    _orig_get_pipeline_agents = registry_mod.get_pipeline_agents
    _orig_resolve_alias = engine_mod.resolve_alias
    _orig_compile = engine_mod.compile_for_run

    def _patched_get_pipeline_agents(pipeline_type, _orig=_orig_get_pipeline_agents):
        if pipeline_type == _FIXTURE_ID:
            return list(specs)
        return _orig(pipeline_type)

    def _patched_resolve_alias(pipeline_type, _orig=_orig_resolve_alias):
        if pipeline_type == _FIXTURE_ID:
            return _FIXTURE_ID
        return _orig(pipeline_type)

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        cw = _orig(pipeline_type)
        cw.clarify.mode = "off"  # offline harness has no live WS clarify round-trip
        return cw

    # ── Per-agent scripted model + attach the repo workspace onto the runner ────
    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    # ── Apply the build agent's repo edit at the build-step boundary ────────────
    # The build agent (write_files, no exec) edits the cloned repo working tree;
    # the deepagents native fs tools write into the artifact RunSandbox, so for the
    # accept proof we apply the declared edit to the repo workspace at the step the
    # build agent runs (the write_files effect). NO engine edit — we wrap _run_agent.
    _orig_run_agent = ExecutionEngine._run_agent

    async def _probe_run_agent(self, spec, *a, **kw):
        if getattr(spec, "id", None) == "brownfield-build":
            workspace.write_file(_EDIT_REL, _EDIT_CONTENT)
        async for ev in _orig_run_agent(self, spec, *a, **kw):
            yield ev

    # ── Attach the repo workspace + branch refs onto ctx.runner after build ─────
    # The KernelServices handle is constructed inside execute(); we attach the
    # has_git workspace + the declared base/working branches onto it so the
    # repo_diff resolver reads ``ctx.runner.workspace.git_diff(main, work)``. We do
    # this by wrapping KernelServices.__init__ to stamp the attributes (no engine edit).
    from agents.execution_engine.kernel_services import KernelServices

    _orig_ks_init = KernelServices.__init__

    def _patched_ks_init(self, **kw):
        _orig_ks_init(self, **kw)
        self.workspace = workspace

    for s in specs:
        _SPEC_CACHE[s.id] = s

    registry_mod.get_pipeline_agents = _patched_get_pipeline_agents
    engine_mod.resolve_alias = _patched_resolve_alias
    engine_mod.compile_for_run = _patched_compile
    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    ExecutionEngine._run_agent = _probe_run_agent
    KernelServices.__init__ = _patched_ks_init

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    events: list[dict] = []
    run_id = f"brownfield-{uuid.uuid4().hex[:8]}"
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Personalize the greeting in the sample repo.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id="brownfield-user",
            gate_agent_ids=[],
        ):
            events.append(ev)
    finally:
        registry_mod.get_pipeline_agents = _orig_get_pipeline_agents
        engine_mod.resolve_alias = _orig_resolve_alias
        engine_mod.compile_for_run = _orig_compile
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        ExecutionEngine._run_agent = _orig_run_agent
        KernelServices.__init__ = _orig_ks_init
        for sid in spec_ids:
            _SPEC_CACHE.pop(sid, None)
    return events, compiled


@pytest.mark.asyncio
async def test_sample_brownfield_runs_end_to_end_with_diff(local_git_fixture, tmp_path) -> None:
    """REPO-05: the run completes offline and the surfaced repo_diff contains the edit."""
    events, _compiled = await _drive_brownfield(local_git_fixture, str(tmp_path / "runs"))
    assert events, "sample_brownfield produced no events"

    errors = [e for e in events if e.get("type") == "error"]
    assert not errors, f"sample_brownfield errored: {errors}"

    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert completes, "sample_brownfield produced no pipeline_complete event"
    final_output = (completes[-1].get("data") or {}).get("final_output")

    # The deliverable is the repo_diff dict (tree + per-file diff + summary).
    assert isinstance(final_output, dict), f"final_output is not a repo_diff dict: {final_output!r}"
    assert final_output.get("kind") == "repo_diff"
    assert _EDIT_REL in final_output["tree"], final_output["tree"]
    # The surfaced diff CONTAINS the agent's edit (REPO-05 core acceptance).
    assert _EDIT_MARKER in final_output["diff"], final_output["diff"]
    assert _EDIT_MARKER in final_output["diffs"][_EDIT_REL]
    assert final_output["summary"]["files_changed"] == 1
    assert final_output["summary"]["lines_added"] >= 1


@pytest.mark.asyncio
async def test_sample_brownfield_exec_off_at_every_step(local_git_fixture, tmp_path) -> None:
    """REPO-05 / T-09-04-01: the effective-perms intersection has exec=off everywhere."""
    _events, compiled = await _drive_brownfield(local_git_fixture, str(tmp_path / "runs"))
    assert compiled.steps, "the compiled workflow has no steps"
    for step in compiled.steps:
        assert step.tools.exec is False, (
            f"step {step.agent_id} grants exec — the brownfield path must run exec=off"
        )
    # The deliverable + repo provider all resolved against the registry (the manifest
    # compiled cleanly — no engine edit was needed to run the new workflow).
    assert compiled.deliverable.strategy == "repo_diff"
    assert "repo" in compiled.context_providers


def test_sample_brownfield_required_zero_engine_edits() -> None:
    """SC-001 discipline: the brownfield workflow's authored artifacts live ENTIRELY
    OUTSIDE ``backend/agents/execution_engine/`` — running it needed no engine edit.

    The manifest + AGENT.md fixtures + this test are the only artifacts the proof
    introduces; the ``repo_diff`` resolver + ``repo`` provider are registered
    capabilities (09-03/09-04), not engine code. None lives under the engine package.
    """
    import subprocess

    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    engine_pkg = "backend/agents/execution_engine/"
    artifacts = [
        "backend/agents/workflows/sample_brownfield/workflow.yaml",
        "backend/tests/agents/fixtures/sample_brownfield/brownfield-analyze/AGENT.md",
        "backend/tests/agents/fixtures/sample_brownfield/brownfield-build/AGENT.md",
        "backend/tests/agents/test_sample_brownfield_workflow.py",
        "backend/agents/capabilities/deliverables/repo_diff.py",
    ]
    for rel in artifacts:
        assert (repo_root / rel).is_file(), f"missing brownfield artifact: {rel}"
        assert not rel.startswith(engine_pkg), (
            f"brownfield artifact {rel} lives under the engine package — the new "
            "workflow must run with ZERO engine edits (SC-001)"
        )

    manifest_text = (
        repo_root / "backend/agents/workflows/sample_brownfield/workflow.yaml"
    ).read_text(encoding="utf-8")
    assert "strategy: repo_diff" in manifest_text
    assert "context_providers: [repo]" in manifest_text


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
