"""SC-001 FAN-OUT PROOF — a brand-new fan-out workflow (``sample_fanout``) runs from
a manifest + AGENT.md ONLY, with ZERO engine edits authored FOR IT (11-05 / the phase
close).

This is the phase's owed core-value proof. ``CLAUDE.md`` Core Value / SC-001:

    "A brand-new custom workflow can replicate ``prototype`` by manifest + AGENT.md
     only — with zero engine edits."

The ``sample_fanout`` manifest lives at the REAL manifest home
(``agents/workflows/sample_fanout/``) so ``compile_for_run`` loads it with ZERO engine
edit (the 09-04 sample_brownfield / 07-11 sc001_task_loop precedent). It declares a
``fanout_batch`` step fanning 3 SELF copies (``fanout.agent: self, count: 3``,
``mode: parallel``), each worker writing a distinct file (``part_1.txt`` /
``part_2.txt`` / ``part_3.txt``), merged ``copy_disjoint`` — using ONLY already-
registered capabilities (``fanout_batch`` strategy + ``copy_disjoint`` merge +
``spawn_subagents`` tool + ``heading_tasks`` parser + ``serialized_sandbox``
deliverable). The declared deliverable is ``serialized_sandbox`` (13-04 / UAT Gap 6,
F6): it bundles the merged part_*.txt base the workers actually produce into the
``filename:``-block deliverable — so the run never hits the ``single_file``
"falling back to streamed output" warning. The worker AGENT.md specs are
test-scoped fixtures (the sc001_task_loop precedent — a real ``agents/prompts/``
AGENT.md with ``pipeline_type: sample_fanout`` would break the loader's
SUPPORTED_PIPELINE_TYPES schema gate, so the proven precedent keeps them test-scoped).

The test drives the workflow end-to-end OFFLINE (scripted model, no network) and
asserts, MIRRORING ``test_sc001_nonprototype_task_loop.py``:
  (1) 3 workers spawn (3 ``subagent_runs`` rows recorded);
  (2) 3 distinct files (``part_1.txt`` / ``part_2.txt`` / ``part_3.txt``) are produced
      in the merged base — deterministic, no conflict;
  (3) the structured summary names every worker's status + (offline) artifact slot;
  (3b) the declared deliverable resolves from the PRODUCED files — the
      ``serialized_sandbox`` bundle contains part_1/2/3.txt as ``filename:`` blocks
      (no single_file fallback to streamed output — UAT Gap 6 / F6, 13-04);
  (4) the CONCEPTUAL SC-001 acceptance, exactly as the task_loop proof does it:
      (a) the workflow runs PURELY off registered capabilities —
          ``registry.is_registered("strategy","fanout_batch")`` /
          ``("merge","copy_disjoint")`` / ``("tool","spawn_subagents")`` all True; and
      (b) ``grep -rc "sample_fanout" backend/agents/execution_engine/`` returns 0 —
          the kernel names NO workflow (INV-1); no engine file was created to
          accommodate ``sample_fanout`` specifically.

OFFLINE scaffolding mirrors ``test_sc001_nonprototype_task_loop.py``: per-agent
scripted models, ``compile_for_run`` / ``get_pipeline_agents`` pointed at the
fixture, the planner / store / review-gate neutralised. NO production code is changed
by the test.
"""

from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator

import frontmatter  # type: ignore[import-untyped]
import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from tests.agents._scripted_model import (  # noqa: E402
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
)

# The manifest lives at the REAL home; the AGENT.md worker specs are test-scoped.
_MANIFEST_HOME = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sc001_fanout"
_FIXTURE_ID = "sample_fanout"
_FANOUT_WIDTH = 3
_PART_RE = re.compile(r"part_(\d+)\.txt")

# The 3-task plan the scripted planner emits — one `## Task N:` heading per worker,
# each naming the distinct file that worker writes (the heading_tasks parser turns
# each heading into one fan-out worker request; the task body is the worker's input).
_TASK_PLAN = (
    "## Task 1: Write part 1\n"
    "Write the file part_1.txt with the content 'part one'.\n\n"
    "## Task 2: Write part 2\n"
    "Write the file part_2.txt with the content 'part two'.\n\n"
    "## Task 3: Write part 3\n"
    "Write the file part_3.txt with the content 'part three'.\n"
)


class _PartWritingModel(ScriptedFakeChatModel):
    """A scripted model whose worker turn writes the ``part_N.txt`` named in its input.

    Each fan-out worker is a SEPARATE ``create_runner`` invocation with a different
    task body injected (the ``=== CURRENT TASK ===`` block). This model inspects the
    incoming messages for the ``part_N.txt`` the task names and emits a ``write_file``
    tool-call for exactly that file — so the 3 workers write 3 DISTINCT files (the
    fan-out + copy_disjoint deterministic-merge proof). Only the WORKER agent writes
    (``_is_worker``); every other agent (the text-only planner) uses the parent
    scripted behaviour — a planner write_file would loop (it has no fs tools).
    """

    def __init__(self, turns, *, is_worker: bool = False, **kwargs: Any) -> None:
        super().__init__(turns, **kwargs)
        object.__setattr__(self, "_is_worker", is_worker)

    def _stream(
        self, messages: list, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        import json as _j

        if not self._is_worker:
            yield from super()._stream(messages, stop, run_manager, **kwargs)
            return
        # The injected CURRENT TASK block names THIS worker's part_N.txt. Scope the
        # search to that block — the full plan (carrying all 3 part markers) is ALSO in
        # context via context_from:[$previous], so a whole-blob search would always pick
        # the last part. The per-worker task lives between the CURRENT TASK markers.
        blob = "\n".join(str(getattr(m, "content", "")) for m in messages)
        task_blocks = re.findall(
            r"=== CURRENT TASK ===\n(.*?)\n=== END CURRENT TASK ===", blob, re.DOTALL
        )
        scope = task_blocks[-1] if task_blocks else blob
        matches = list(_PART_RE.finditer(scope))
        # After the FIRST turn writes the file, the second turn must terminate (a plain
        # text turn, no tool-call) so the deepagents graph does not loop forever.
        already_wrote = bool(self._call_index)
        object.__setattr__(self, "_call_index", self._call_index + 1)
        if not matches or already_wrote:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="Done.",
                    usage_metadata={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                    chunk_position="last",
                )
            )
            return
        m = matches[-1]
        fname = m.group(0)
        n = m.group(1)
        # One turn: write_file(part_N.txt) — the worker's single distinct deliverable.
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=f"Writing {fname}. ",
                tool_call_chunks=[
                    {
                        "name": "write_file",
                        "args": _j.dumps({"file_path": fname, "content": f"part {n}\n"}),
                        "id": f"c_w_{n}",
                        "index": 0,
                    }
                ],
                usage_metadata={"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
                chunk_position="last",
            )
        )


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
    """Per-agent scripted turns. The planner emits the 3-task plan; the worker turn is
    driven by _PartWritingModel off the injected task (so this default is only the
    no-op fallback)."""
    if agent_id == "sample-fanout-plan":
        return [_ScriptedTurn(texts=[_TASK_PLAN], usage=(20, 16))]
    return [_ScriptedTurn(texts=[f"{agent_id} default."], usage=(5, 3))]


async def _drive_fanout() -> tuple[list[dict], dict]:
    """Drive the sample_fanout workflow end-to-end offline. Returns (events, probe)."""
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    import agents.registry as registry_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.loader import _SPEC_CACHE
    from agents.workflows.manifest import load_manifest

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = _load_fixture_specs()
    spec_ids = [s.id for s in specs]

    probe: dict = {"recorded_workers": []}

    _orig_compile = engine_mod.compile_for_run
    _orig_resolve_alias = engine_mod.resolve_alias
    _CAPABILITY_REGISTRY = engine_mod._CAPABILITY_REGISTRY
    _WORKFLOW_COMPILER = engine_mod._WORKFLOW_COMPILER

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        if pipeline_type == _FIXTURE_ID:
            manifest = load_manifest(_FIXTURE_ID, _MANIFEST_HOME)
            compiled = _WORKFLOW_COMPILER.compile(manifest, _CAPABILITY_REGISTRY)
            compiled.clarify.mode = "off"
            return compiled
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    def _patched_resolve_alias(pipeline_type, _orig=_orig_resolve_alias):
        if pipeline_type == _FIXTURE_ID:
            return _FIXTURE_ID
        return _orig(pipeline_type)

    _orig_get_pipeline_agents = registry_mod.get_pipeline_agents

    def _patched_get_pipeline_agents(pipeline_type, _orig=_orig_get_pipeline_agents):
        if pipeline_type == _FIXTURE_ID:
            return list(specs)
        return _orig(pipeline_type)

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = _PartWritingModel(
            _scripts_for(agent_id), is_worker=(agent_id == "sample-fanout-worker")
        )
        return _orig_create_runner(agent_id, ctx, **kw)

    # Probe the single spawn-path audit: every recorded subagent_runs row (FANOUT-10).
    from agents.execution_engine.kernel_services import KernelServices
    _orig_record = KernelServices.record_subagent_run

    async def _probe_record(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None, worker_index=None, task_id=None):
        probe["recorded_workers"].append(
            dict(parent_step=parent_step, worker_agent=worker_agent, isolation=isolation, status=status, worker_index=worker_index, task_id=task_id)
        )
        return await _orig_record(
            self, parent_step=parent_step, worker_agent=worker_agent, depth=depth,
            isolation=isolation, status=status, tokens=tokens, cost=cost,
            worker_index=worker_index, task_id=task_id,
        )

    for s in specs:
        _SPEC_CACHE[s.id] = s

    engine_mod.compile_for_run = _patched_compile
    engine_mod.resolve_alias = _patched_resolve_alias
    registry_mod.get_pipeline_agents = _patched_get_pipeline_agents
    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    KernelServices.record_subagent_run = _probe_record

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
    run_id = f"sc001fan-{uuid.uuid4().hex[:8]}"
    sandbox_root: Path | None = None
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Fan out three file writers.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id="sc001fan-user",
            gate_agent_ids=[],
        ):
            events.append(ev)
        # Locate the run sandbox on disk to read the merged-base files back.
        from app.agents.sandbox import RunSandbox

        sandbox_root = RunSandbox("sc001fan-user", run_id).root
    finally:
        engine_mod.compile_for_run = _orig_compile
        engine_mod.resolve_alias = _orig_resolve_alias
        registry_mod.get_pipeline_agents = _orig_get_pipeline_agents
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        KernelServices.record_subagent_run = _orig_record
        for sid in spec_ids:
            _SPEC_CACHE.pop(sid, None)
    probe["sandbox_root"] = sandbox_root
    return events, probe


@pytest.mark.asyncio
async def test_sc001_fanout_spawns_three_workers_and_merges_distinct_files() -> None:
    """3 workers spawn (3 subagent_runs rows) + 3 distinct files merged — FANOUT-11/SC-001."""
    events, probe = await _drive_fanout()
    assert events, "sample_fanout produced no events (drove nothing / errored)"

    errors = [e for e in events if e.get("type") == "error"]
    assert not errors, f"sample_fanout errored: {errors}"

    # (1) 3 workers spawned — 3 subagent_runs rows recorded at the single spawn path.
    assert len(probe["recorded_workers"]) == _FANOUT_WIDTH, (
        f"expected {_FANOUT_WIDTH} subagent_runs rows, saw {probe['recorded_workers']}"
    )
    assert all(w["worker_agent"] == "sample-fanout-worker" for w in probe["recorded_workers"])

    # The lifecycle events: a subagent_spawned + subagent_result per worker.
    spawned = [e for e in events if e.get("type") == "subagent_spawned"]
    results = [e for e in events if e.get("type") == "subagent_result"]
    assert len(spawned) == _FANOUT_WIDTH, f"expected {_FANOUT_WIDTH} subagent_spawned, saw {len(spawned)}"
    assert len(results) == _FANOUT_WIDTH, f"expected {_FANOUT_WIDTH} subagent_result, saw {len(results)}"

    # (3) The structured summary names every worker's status (offline isolation degrades
    #     to shared_read so the 3 workers write into the shared merged base; each
    #     subagent_result carries the worker's terminal status).
    statuses = {(r.get("data") or {}).get("status") for r in results}
    assert statuses == {"complete"}, f"a worker did not complete: {statuses}"

    # (2) 3 DISTINCT files produced in the merged base (deterministic, no conflict).
    sandbox_root = probe["sandbox_root"]
    assert sandbox_root is not None and sandbox_root.is_dir(), "run sandbox missing on disk"
    produced = {
        p.name for p in sandbox_root.rglob("*.txt")
        if _PART_RE.fullmatch(p.name) and ".worktrees" not in p.parts
    }
    assert produced == {"part_1.txt", "part_2.txt", "part_3.txt"}, (
        f"the 3 fan-out workers did not produce 3 distinct merged files: {sorted(produced)}"
    )
    # No merge_conflict event — copy_disjoint merged the disjoint files cleanly.
    assert not any(e.get("type") == "merge_conflict" for e in events), (
        "copy_disjoint reported a conflict over disjoint files"
    )

    # (3b) Gap 6 (13-04 / F6): the DECLARED deliverable (serialized_sandbox) resolves
    # from the PRODUCED files — the final output is the filename:-block bundle of the
    # merged part_*.txt base, NOT the single_file fallback to one worker's streamed
    # text (the live-run degradation 8ffae37c fixed for sample_wave).
    complete = [e for e in events if e.get("type") == "pipeline_complete"]
    assert complete, "no pipeline_complete event emitted"
    final_output = complete[-1]["data"]["final_output"]
    assert final_output and final_output.strip(), "final deliverable is empty"
    assert "(no files written)" not in final_output, (
        "serialized_sandbox found no deliverable files — the merge did not land"
    )
    for part in ("part_1.txt", "part_2.txt", "part_3.txt"):
        assert f"filename: {part}" in final_output, (
            f"deliverable bundle missing produced file {part} — the declared "
            "deliverable did not resolve from the produced merged base"
        )


def test_sc001_fanout_runs_on_registered_capabilities_only() -> None:
    """SC-001 (a): the workflow runs PURELY off already-registered capabilities."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("strategy", "fanout_batch"), "fanout_batch strategy not registered"
    assert reg.is_registered("merge", "copy_disjoint"), "copy_disjoint merge not registered"
    assert reg.is_registered("tool", "spawn_subagents"), "spawn_subagents tool not registered"
    assert reg.is_registered("task_parser", "heading_tasks"), "heading_tasks parser not registered"
    assert reg.is_registered("deliverable", "serialized_sandbox"), (
        "serialized_sandbox deliverable not registered"
    )

    # The manifest declares ONLY those registered capabilities (no kernel edit to run).
    manifest_text = (_MANIFEST_HOME / _FIXTURE_ID / "workflow.yaml").read_text(encoding="utf-8")
    assert "strategy: fanout_batch" in manifest_text
    assert "spawn_subagents: true" in manifest_text
    assert "parser: heading_tasks" in manifest_text
    assert "strategy: serialized_sandbox" in manifest_text
    # Gap 6 (13-04 / F6): no dangling merged.txt — the deliverable resolves from the
    # files the workflow actually produces, not a never-written named file.
    assert "merged.txt" not in manifest_text


def test_sc001_fanout_kernel_names_no_workflow() -> None:
    """SC-001 (b): the kernel contains NO reference to sample_fanout by name (INV-1).

    The 11-01..11-04 engine infrastructure is workflow-agnostic — it does not name
    ``sample_fanout``. No engine file was created to accommodate THIS workflow
    specifically; it runs on the registered, declared capabilities. (Mirrors the
    07-11 SC-001 proof's grep — NOT a phase-start engine file-diff, which would
    false-fire on the legitimate agnostic-infrastructure edits 11-01..11-04 made.)
    """
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    engine_pkg = repo_root / "backend" / "agents" / "execution_engine"
    hits = subprocess.run(
        ["grep", "-rl", "sample_fanout", str(engine_pkg)],
        capture_output=True, text=True,
    ).stdout.strip()
    assert hits == "", (
        f"the kernel names the workflow sample_fanout (INV-1 violation) in:\n{hits}"
    )

    # The SC-001 proof artifacts all live OUTSIDE the engine package (zero engine edit
    # to RUN this workflow — the manifest + worker AGENT.md + this test only).
    proof_artifacts = [
        "backend/agents/workflows/sample_fanout/workflow.yaml",
        "backend/tests/agents/fixtures/sc001_fanout/sample-fanout-plan/AGENT.md",
        "backend/tests/agents/fixtures/sc001_fanout/sample-fanout-worker/AGENT.md",
        "backend/tests/agents/test_sc001_fanout.py",
    ]
    for rel in proof_artifacts:
        assert (repo_root / rel).is_file(), f"missing proof artifact: {rel}"
        assert not rel.startswith("backend/agents/execution_engine/"), (
            f"SC-001 proof artifact {rel} lives under the engine package — the proof "
            "must require ZERO engine edits to run the workflow"
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
