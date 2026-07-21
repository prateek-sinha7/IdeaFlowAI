"""[BLOCKING] OFFLINE COMPOSED-FAN-OUT CHARACTERIZATION — the Path-B crux proof (51-05).

The pivotal acceptance gate the FE waves depend on: a **user-COMPOSED** (selections-
driven, NOT file-manifest) fan-out actually spawns N worker sub-agents end-to-end,
offline, through the real kernel spawn path (``run_fanout``).

This mirrors ``test_sc001_fanout.py``'s harness EXACTLY, with ONE divergence (scope
§6b / D10 step 2): instead of a file manifest that DECLARES the fan-out step, the
fan-out is driven by a COMPOSED selection passed into ``engine.execute(...)``::

    selections = {
        "composed-fanout-worker": {
            "strategy": "fanout_batch",
            "task_source": {
                "kind": "parsed",
                "parser": "heading_tasks",
                "source_step": "composed-fanout-plan",
            },
            "fanout": {"mode": "parallel", "max_parallel": 3},
        }
    }

The worker is ABSENT from the base manifest — the mocked ``compile_for_run`` returns a
plan whose ``steps`` contain ONLY the producer, while the run specs / patched
``get_pipeline_agents`` also exclude the worker (so the membership assertion at
``engine.py:1714`` passes) BUT the run's ``agents=`` list INCLUDES it. So at the
synthesis site (``engine.py:2291``) ``_steps_by_agent.get(worker)`` is ``None`` and the
worker's fan-out step can ONLY come from ``_user_steps_by_agent`` (the trust-compiled
user-step map returned by ``_apply_selections``). This EXERCISES the absent-agent
synthesis-site consult (the COMMON ``custom`` case), NOT the in-plan overlay — the
crux carries ``strategy``/``fanout``/``task_source`` at the ABSENT site.

**C1 (pin the absent-worker mechanism):** the test records the base compiled plan the
engine actually consumed and asserts the worker is NOT among its step ids
(``_steps_by_agent.get(worker) is None``). An executor CANNOT silently downgrade this
to the in-plan overlay path by adding the worker to the base manifest without either
failing this assertion OR tripping the ``engine.py:1714`` membership assertion (which
compares the base compiled steps against the patched ``get_pipeline_agents``).

**C2 (D9 × composed):** a composed worker whose ``task_source.source_step`` names a
LATER run agent (a forward reference that EXISTS in the widened ``agent_ids``) — or an
UNKNOWN id — is REJECTED by the D9 upstream guard when ``_apply_selections`` runs its
internal ``trust="user"`` re-compile. Offline, the real disposition is the
``except CompilerError`` degrade in ``_apply_selections`` (``engine.py:6256``) that
returns ``(compiled, {})`` → the worker gets NO fan-out step → it falls back to a bare
``single_shot`` at runtime (0 workers spawned). (The alternative disposition — a 422 at
the LAUNCH re-validate ``run_commands.py:1535`` — is the WS-layer chokepoint, NOT
reachable by driving ``execute()`` directly; the offline path is the degrade.) The
happy path (``source_step`` = an EARLIER run agent) compiles clean and fans out — so the
widened ``agent_ids`` ORDERING is what the guard consumes.

**Benign hook delta (Risk #6 / D3):** the trust-compiled absent worker step carries the
compiler's default ``audit_logger``/``secret_scan`` hooks that a bare synthesized
``_Step`` lacked. This is INTENDED behavior (asserted below), NOT a regression.

**shared_read harness caveat (same as ``test_sc001_fanout``):** offline the fan-out
isolation degrades to ``shared_read`` so the 3 workers write into the shared merged
base (each worker's file is distinct, so ``copy_disjoint`` still merges cleanly with no
conflict). PER-WORKER ISOLATED writes + a real 3-way merge are a LIVE-BEDROCK concern —
proven by the orchestrator-owned live proof (scope §6d), not this offline harness.

SC-001: ``grep -rl "composed_fanout" backend/agents/execution_engine/`` returns "" — the
kernel names NO workflow; all power lives in the registered, declared capabilities and
the generic ``agent_id``-keyed overlay.
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

# Everything is test-scoped (no real manifest home) — this crux is driven by a COMPOSED
# selection, not a file manifest, so nothing needs to live at agents/workflows/.
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "composed_fanout"
_FIXTURE_ID = "composed_fanout"
_PRODUCER_ID = "composed-fanout-plan"
_WORKER_ID = "composed-fanout-worker"
_FANOUT_WIDTH = 3
_PART_RE = re.compile(r"part_(\d+)\.txt")

# The composed fan-out selection: the worker's SELECTION (not a file manifest) declares
# the fan-out. Keyed GENERICALLY on the worker agent id + generic lever keys (INV-1).
_COMPOSED_SELECTIONS: dict = {
    _WORKER_ID: {
        "strategy": "fanout_batch",
        "task_source": {
            "kind": "parsed",
            "parser": "heading_tasks",
            "source_step": _PRODUCER_ID,  # an EARLIER run agent — the happy path
        },
        "fanout": {"mode": "parallel", "max_parallel": 3},
    }
}

# The 3-task plan the scripted producer emits — one `## Task N:` heading per worker.
_TASK_PLAN = (
    "## Task 1: Write part 1\n"
    "Write the file part_1.txt with the content 'part one'.\n\n"
    "## Task 2: Write part 2\n"
    "Write the file part_2.txt with the content 'part two'.\n\n"
    "## Task 3: Write part 3\n"
    "Write the file part_3.txt with the content 'part three'.\n"
)


class _PartWritingModel(ScriptedFakeChatModel):
    """Worker turn writes the ``part_N.txt`` named in its injected ``=== CURRENT TASK ===``
    block (mirrors ``test_sc001_fanout._PartWritingModel`` exactly)."""

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
        blob = "\n".join(str(getattr(m, "content", "")) for m in messages)
        task_blocks = re.findall(
            r"=== CURRENT TASK ===\n(.*?)\n=== END CURRENT TASK ===", blob, re.DOTALL
        )
        scope = task_blocks[-1] if task_blocks else blob
        matches = list(_PART_RE.finditer(scope))
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
    """Per-agent scripted turns. The producer emits the 3-task plan; the worker turn is
    driven by _PartWritingModel off the injected task (so this default is only the
    no-op fallback for the worker)."""
    if agent_id == _PRODUCER_ID:
        return [_ScriptedTurn(texts=[_TASK_PLAN], usage=(20, 16))]
    return [_ScriptedTurn(texts=[f"{agent_id} default."], usage=(5, 3))]


def _build_base_compiled():
    """Compile the base manifest that EXCLUDES the worker (the C1 pin).

    The base plan declares ONLY the producer step — the worker's fan-out step can ONLY
    reach the run via the composed selection (the ``_user_steps_by_agent`` map), never
    the in-plan overlay. Compiled with the ENGINE's own compiler + registry so the plan
    the engine consumes is exactly this one (no drift).
    """
    import agents.execution_engine.engine as engine_mod
    from agents.workflows.manifest import WorkflowManifest

    manifest = WorkflowManifest(
        id=_FIXTURE_ID,
        steps=[
            {
                "agent": _PRODUCER_ID,
                "strategy": "single_shot",
                "gates": [],
                "tools": {"read_files": True, "write_files": True, "exec": False},
            }
        ],
        deliverable={"strategy": "serialized_sandbox"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        allowed_workers=[_WORKER_ID],
    )
    compiled = engine_mod._WORKFLOW_COMPILER.compile(
        manifest, engine_mod._CAPABILITY_REGISTRY
    )
    compiled.clarify.mode = "off"
    return compiled


async def _drive_composed_fanout(selections: dict) -> tuple[list[dict], dict]:
    """Drive a COMPOSED fan-out end-to-end offline. Returns (events, probe).

    ``selections`` is the composed per-step map passed into ``engine.execute(...)`` — the
    ONLY divergence from ``test_sc001_fanout`` (which declares the fan-out in a file
    manifest). The base compile EXCLUDES the worker (C1); the run ``agents`` INCLUDE it.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    import agents.registry as registry_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.loader import _SPEC_CACHE

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    specs = _load_fixture_specs()  # [producer, worker] (sorted by order)
    spec_ids = [s.id for s in specs]
    # get_pipeline_agents membership EXCLUDES the worker — it must equal the base
    # compiled steps (producer only) so the engine.py:1714 membership assertion passes.
    membership_specs = [s for s in specs if s.id != _WORKER_ID]

    probe: dict = {"recorded_workers": [], "base_compiled": None}

    _orig_compile = engine_mod.compile_for_run
    _orig_resolve_alias = engine_mod.resolve_alias

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        if pipeline_type == _FIXTURE_ID:
            compiled = _build_base_compiled()
            # Record the EXACT plan the engine consumes so C1 asserts on reality.
            probe["base_compiled"] = compiled
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
            return list(membership_specs)  # producer ONLY — worker is absent (C1)
        return _orig(pipeline_type)

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = _PartWritingModel(
            _scripts_for(agent_id), is_worker=(agent_id == _WORKER_ID)
        )
        return _orig_create_runner(agent_id, ctx, **kw)

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
    run_id = f"composedfan-{uuid.uuid4().hex[:8]}"
    sandbox_root: Path | None = None
    try:
        async for ev in engine.execute(
            agents=list(specs),  # INCLUDES the worker — the run drives it, the base plan does not
            user_message="Fan out three file writers from a composed selection.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id="composedfan-user",
            gate_agent_ids=[],
            selections=selections,  # ← THE DIVERGENCE: composed, not a file manifest
        ):
            events.append(ev)
        from app.agents.sandbox import RunSandbox

        sandbox_root = RunSandbox("composedfan-user", run_id).root
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
async def test_composed_fanout_spawns_three_workers_and_merges_distinct_files() -> None:
    """[BLOCKING] A COMPOSED (selections-driven) fan-out spawns 3 workers + merges — the crux."""
    events, probe = await _drive_composed_fanout(_COMPOSED_SELECTIONS)
    assert events, "composed fan-out produced no events (drove nothing / errored)"

    errors = [e for e in events if e.get("type") == "error"]
    assert not errors, f"composed fan-out errored: {errors}"

    # ── C1: PIN THE ABSENT-WORKER MECHANISM ──────────────────────────────────────
    # The base plan the engine ACTUALLY consumed excludes the worker, so at the
    # synthesis site ``_steps_by_agent.get(worker)`` was None — the worker's fan-out
    # step could ONLY come from ``_user_steps_by_agent`` (the composed overlay). An
    # executor cannot make the worker present in the base manifest without either
    # failing THIS assertion or tripping the engine.py:1714 membership assertion.
    base_compiled = probe["base_compiled"]
    assert base_compiled is not None, "base compile probe not captured"
    base_step_ids = [s.agent_id for s in base_compiled.steps]
    assert _WORKER_ID not in base_step_ids, (
        f"C1 VIOLATED: the worker is PRESENT in the base compiled plan {base_step_ids} — "
        "the test degraded to the in-plan overlay path, NOT the absent synthesis site. "
        "The [BLOCKING] crux proof requires _steps_by_agent.get(worker) is None."
    )
    assert base_step_ids == [_PRODUCER_ID], (
        f"base compile should declare ONLY the producer, saw {base_step_ids}"
    )

    # (1) 3 workers spawned — 3 subagent_runs rows recorded at the single spawn path.
    assert len(probe["recorded_workers"]) == _FANOUT_WIDTH, (
        f"expected {_FANOUT_WIDTH} subagent_runs rows, saw {probe['recorded_workers']}"
    )
    assert all(w["worker_agent"] == _WORKER_ID for w in probe["recorded_workers"])
    # The fan-out was parented on the WORKER step (the absent, composed agent).
    assert all(w["parent_step"] == _WORKER_ID for w in probe["recorded_workers"]), (
        f"fan-out not parented on the composed worker step: {probe['recorded_workers']}"
    )

    # The lifecycle events: a subagent_spawned + subagent_result per worker.
    spawned = [e for e in events if e.get("type") == "subagent_spawned"]
    results = [e for e in events if e.get("type") == "subagent_result"]
    assert len(spawned) == _FANOUT_WIDTH, f"expected {_FANOUT_WIDTH} subagent_spawned, saw {len(spawned)}"
    assert len(results) == _FANOUT_WIDTH, f"expected {_FANOUT_WIDTH} subagent_result, saw {len(results)}"

    statuses = {(r.get("data") or {}).get("status") for r in results}
    assert statuses == {"complete"}, f"a worker did not complete: {statuses}"

    # (2) 3 DISTINCT files produced in the merged base (deterministic, no conflict).
    #     shared_read harness caveat: offline the workers write into the SHARED base;
    #     per-worker isolated writes + a real merge are the LIVE-BEDROCK proof (§6d).
    sandbox_root = probe["sandbox_root"]
    assert sandbox_root is not None and sandbox_root.is_dir(), "run sandbox missing on disk"
    produced = {
        p.name for p in sandbox_root.rglob("*.txt")
        if _PART_RE.fullmatch(p.name) and ".worktrees" not in p.parts
    }
    assert produced == {"part_1.txt", "part_2.txt", "part_3.txt"}, (
        f"the 3 composed fan-out workers did not produce 3 distinct merged files: {sorted(produced)}"
    )
    assert not any(e.get("type") == "merge_conflict" for e in events), (
        "copy_disjoint reported a conflict over disjoint files"
    )

    # (3) The declared deliverable (serialized_sandbox) resolves from the PRODUCED files.
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


def test_composed_overlay_carries_fanout_at_absent_site_with_benign_hook_delta() -> None:
    """The composed worker's trust-compiled step carries strategy==fanout_batch at the
    ABSENT site, plus the INTENDED default-hooks delta (Risk #6 / D3) — asserted directly
    on ``_apply_selections`` (the single seam that feeds the synthesis site)."""
    from agents.capabilities.registry import discover
    from agents.execution_engine.engine import ExecutionEngine

    discover()
    base = _build_base_compiled()
    # Widen with the run's agent ids (producer + worker) exactly as engine.py:1467 does.
    plan, user_map = ExecutionEngine._apply_selections(
        base, _COMPOSED_SELECTIONS, [_PRODUCER_ID, _WORKER_ID]
    )
    # The overlay NEVER adds steps to the plan (membership assertion stays valid).
    assert [s.agent_id for s in plan.steps] == [_PRODUCER_ID], (
        "the overlay must not add/remove base plan steps"
    )
    # The worker's fan-out step lives in the user-step map (the absent-site consult).
    worker_step = user_map.get(_WORKER_ID)
    assert worker_step is not None, "composed worker step missing from _user_steps_by_agent"
    assert worker_step.strategy == "fanout_batch", (
        f"composed worker step did not carry fanout_batch: {worker_step.strategy!r}"
    )
    assert worker_step.task_source is not None
    assert worker_step.task_source.source_step == _PRODUCER_ID
    # Benign hook delta (Risk #6): the trust-compiled step carries the compiler's default
    # audit hooks a bare synthesized _Step lacked — INTENDED, not a regression.
    assert set(worker_step.hooks) >= {"audit_logger", "secret_scan"}, (
        f"expected the default audit hooks on the trust-compiled step, saw {worker_step.hooks}"
    )


def test_composed_fanout_d9_guard_rejects_non_upstream_source_step() -> None:
    """C2: the D9 upstream guard fires on the internal composed trust-compile.

    A composed worker whose ``source_step`` names a LATER run agent (a forward reference
    that EXISTS in the widened ``agent_ids`` — proving the guard consumes the ORDERING,
    not mere membership) OR an UNKNOWN id is rejected → ``_apply_selections`` degrades to
    ``(compiled, {})`` (no fan-out step). The EARLIER-source happy path yields the
    fan-out step. This is the offline disposition; the WS-layer 422
    (run_commands.py:1535) is not reachable by driving ``_apply_selections`` directly.
    """
    from agents.capabilities.registry import discover
    from agents.execution_engine.engine import ExecutionEngine

    discover()
    base = _build_base_compiled()
    _LATER_ID = "composed-fanout-tail"  # a LATER run agent (index 2 in the widened ids)

    def _sel(source_step: str) -> dict:
        return {
            _WORKER_ID: {
                "strategy": "fanout_batch",
                "task_source": {
                    "kind": "parsed",
                    "parser": "heading_tasks",
                    "source_step": source_step,
                },
            }
        }

    # LATER run agent: widened agent_ids = [producer, worker, tail]; the worker (index 1)
    # references tail (index 2) which is NOT yet upstream → D9 CompilerError → degrade.
    _, later_map = ExecutionEngine._apply_selections(
        base, _sel(_LATER_ID), [_PRODUCER_ID, _WORKER_ID, _LATER_ID]
    )
    assert later_map == {}, (
        "C2 VIOLATED: a fan-out source_step naming a LATER run agent was NOT rejected by "
        f"the D9 guard on the composed trust-compile (got {later_map})"
    )

    # UNKNOWN id: not in the widened agent_ids at all → D9 CompilerError → degrade.
    _, ghost_map = ExecutionEngine._apply_selections(
        base, _sel("composed-fanout-ghost"), [_PRODUCER_ID, _WORKER_ID]
    )
    assert ghost_map == {}, (
        f"an unknown fan-out source_step was NOT rejected by the D9 guard (got {ghost_map})"
    )

    # EARLIER (happy) source: producer precedes the worker → compiles clean → fans out.
    _, good_map = ExecutionEngine._apply_selections(
        base, _sel(_PRODUCER_ID), [_PRODUCER_ID, _WORKER_ID]
    )
    assert good_map.get(_WORKER_ID) is not None, (
        "the EARLIER-source happy path failed to yield a fan-out step"
    )
    assert good_map[_WORKER_ID].strategy == "fanout_batch"


def test_composed_fanout_producer_higher_base_order_still_carries_strategy() -> None:
    """Regression (live-found 2026-07-20): a composed fan-out over IN-BASE-MANIFEST agents
    whose producer has a HIGHER base-manifest ``order`` than its worker must STILL carry
    the fan-out strategy.

    Before the engine.py fix, ``_apply_selections`` built the synth manifest in BASE order,
    so ``task-list-planner`` (custom order 9) landed AFTER ``market-research-agent`` (custom
    order 1); the D9 upstream guard read ``source_step`` as a forward reference and the
    ENTIRE selection degraded to ``single_shot`` — the live fan-out silently ran once with
    no workers. The fix orders run agents FIRST (the user's composed producer->worker order,
    which presort preserves for unconstrained agents). This is the exact live scenario, run
    against the REAL ``custom`` manifest (not the synthetic fixtures the other tests use).
    """
    from agents.capabilities.registry import discover
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    discover()
    compiled = compile_for_run("custom")
    base_order = [s.agent_id for s in compiled.steps]
    # Precondition: both agents are IN the base manifest AND the producer's base order is
    # HIGHER than the worker's — the arrangement that broke the live run.
    assert "task-list-planner" in base_order and "market-research-agent" in base_order
    assert base_order.index("task-list-planner") > base_order.index(
        "market-research-agent"
    ), "this regression needs the producer to have a HIGHER base order than the worker"

    sels = {
        "market-research-agent": {
            "strategy": "fanout_batch",
            "task_source": {
                "kind": "parsed",
                "parser": "heading_tasks",
                "source_step": "task-list-planner",
            },
        }
    }
    # run_agent_ids in the USER's composed order: producer THEN worker.
    plan, user_map = ExecutionEngine._apply_selections(
        compiled, sels, ["task-list-planner", "market-research-agent"]
    )
    worker_step = next(s for s in plan.steps if s.agent_id == "market-research-agent")
    assert worker_step.strategy == "fanout_batch", (
        "REGRESSION: the composed fan-out degraded to single_shot because the D9 guard "
        f"read the producer as a forward reference (got {worker_step.strategy!r})"
    )
    assert worker_step.task_source is not None
    assert worker_step.task_source.source_step == "task-list-planner"
    assert user_map != {}, "the trust-compile must NOT have degraded"


@pytest.mark.asyncio
async def test_composed_fanout_non_upstream_source_degrades_to_no_fanout_at_runtime() -> None:
    """C2 (runtime): a composed worker whose ``source_step`` is not upstream degrades to
    NO fan-out end-to-end — the worker runs a bare single_shot, 0 workers spawned."""
    bad_selections = {
        _WORKER_ID: {
            "strategy": "fanout_batch",
            "task_source": {
                "kind": "parsed",
                "parser": "heading_tasks",
                "source_step": "composed-fanout-ghost",  # unknown → D9 rejects → degrade
            },
        }
    }
    events, probe = await _drive_composed_fanout(bad_selections)
    assert events, "negative composed run produced no events"
    errors = [e for e in events if e.get("type") == "error"]
    assert not errors, f"negative composed run errored (should degrade, not crash): {errors}"

    # The degrade is silent + safe: NO fan-out spawned (the worker ran single_shot).
    assert probe["recorded_workers"] == [], (
        f"a rejected composed fan-out still spawned workers: {probe['recorded_workers']}"
    )
    assert not any(e.get("type") == "subagent_spawned" for e in events), (
        "a rejected composed fan-out emitted subagent_spawned — the D9 degrade failed"
    )
    assert not any(e.get("type") == "subagent_result" for e in events)
    # The run still completes (degrade-to-single_shot, not a crash).
    assert any(e.get("type") == "pipeline_complete" for e in events), (
        "the degraded run did not complete"
    )


def test_composed_fanout_kernel_names_no_workflow() -> None:
    """SC-001 / INV-1: the kernel contains NO reference to the composed workflow by name.

    The overlay + synthesis-site consult are workflow-agnostic — keyed on generic
    ``agent_id`` + generic lever keys only. No engine file names ``composed_fanout``
    (nor its agent ids); the crux runs on registered, declared capabilities.
    """
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    engine_pkg = repo_root / "backend" / "agents" / "execution_engine"
    for needle in ("composed_fanout", _PRODUCER_ID, _WORKER_ID):
        hits = subprocess.run(
            ["grep", "-rl", needle, str(engine_pkg)],
            capture_output=True, text=True,
        ).stdout.strip()
        assert hits == "", (
            f"the kernel names the composed workflow/agent '{needle}' (INV-1 violation) in:\n{hits}"
        )

    # The proof artifacts all live OUTSIDE the engine package (zero engine edit to run
    # this COMPOSED fan-out — the overlay was authored generically in an earlier plan).
    proof_artifacts = [
        "backend/tests/agents/fixtures/composed_fanout/composed-fanout-plan/AGENT.md",
        "backend/tests/agents/fixtures/composed_fanout/composed-fanout-worker/AGENT.md",
        "backend/tests/agents/test_composed_fanout.py",
    ]
    for rel in proof_artifacts:
        assert (repo_root / rel).is_file(), f"missing proof artifact: {rel}"
        assert not rel.startswith("backend/agents/execution_engine/"), (
            f"proof artifact {rel} lives under the engine package"
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
