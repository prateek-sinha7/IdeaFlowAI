"""QA-KB-070 / ISS-897 analyzer measurement (scratch; OFFLINE scripted model; NO repo writes).

Adapted from evidence/qa-kb-030/04-analyze-run-drive.py. Drives the REAL
ExecutionEngine.execute() through the SC-001 task_loop fixture (2 tasks) with the exact
launch shape the wizard produces when the user ticks the build agent under "Review gates":

    gate_agent_ids=[<agent>]   +   selections[<agent>].gates=["human"]

and counts how many times a review gate is entered for the build agent:

  AS SHIPPED : task_loop.py:164 runs_agent_inline=False AND task_loop.py:364 invocation_gated=False
  MUTATED    : the SAME code with the `invocation_gated=False,` line deleted IN MEMORY
               (mutate_task_loop.apply_mutation) -- i.e. the revert ISS-897 says nothing detects.

Hermetic like tests/conftest.py: DATABASE_URL is pinned to a scratch SQLite file BEFORE any app
import, the model is a ScriptedFakeChatModel (zero LLM cost), the checkpointer is InMemory.

Run from backend/ (QA_SCRATCH = any writable scratch dir):

    QA_SCRATCH=/tmp/qa070 .venv/bin/python -I ../evidence/qa-kb-070/02-analyze-gate-count-drive.py
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

SCRATCH = Path(os.environ["QA_SCRATCH"])
SCRATCH.mkdir(parents=True, exist_ok=True)
_DB = SCRATCH / "qa_kb_070_run.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"          # MUST precede any app import
os.environ["PARITY_RUNS_ROOT"] = str(SCRATCH / "runs")   # sandbox lands in scratch
(SCRATCH / "runs").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ENV", "development")
sys.path.insert(0, ".")                                   # cwd is backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for mutate_task_loop

import app.models  # noqa: F401,E402  registers models on Base.metadata
from app.models.database import Base, engine as _db_engine  # noqa: E402

assert str(_db_engine.url).startswith("sqlite"), f"NOT hermetic: {_db_engine.url}"
Base.metadata.create_all(bind=_db_engine)
print("hermetic DB:", _db_engine.url)

from mutate_task_loop import apply_mutation  # noqa: E402
from tests.agents._scripted_model import _RUNS_ROOT, ScriptedFakeChatModel  # noqa: E402
from tests.integration.agents.test_sc001_nonprototype_task_loop import (  # noqa: E402
    _FIXTURE_DIR,
    _FIXTURE_ID,
    _load_fixture_specs,
    _sc001_scripts_for,
)

BUILD = "sc001-build"


async def drive(label: str) -> None:
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

    _orig_compile = engine_mod.compile_for_run
    _orig_resolve_alias = engine_mod.resolve_alias
    _CAP = engine_mod._CAPABILITY_REGISTRY
    _COMPILER = engine_mod._WORKFLOW_COMPILER

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        if pipeline_type == _FIXTURE_ID:
            manifest = load_manifest(_FIXTURE_ID, _FIXTURE_DIR.parent)
            compiled = _COMPILER.compile(manifest, _CAP)
            compiled.clarify.mode = "off"
            return compiled
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    def _patched_resolve_alias(pipeline_type, _orig=_orig_resolve_alias):
        return _FIXTURE_ID if pipeline_type == _FIXTURE_ID else _orig(pipeline_type)

    _orig_gpa = registry_mod.get_pipeline_agents

    def _patched_gpa(pipeline_type, _orig=_orig_gpa):
        return list(specs) if pipeline_type == _FIXTURE_ID else _orig(pipeline_type)

    _orig_cr = factory_mod.create_runner
    _orig_ecr = getattr(engine_mod, "create_runner", None)

    def _patched_cr(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_sc001_scripts_for(agent_id))
        return _orig_cr(agent_id, ctx, **kw)

    for s in specs:
        _SPEC_CACHE[s.id] = s
    engine_mod.compile_for_run = _patched_compile
    engine_mod.resolve_alias = _patched_resolve_alias
    registry_mod.get_pipeline_agents = _patched_gpa
    factory_mod.create_runner = _patched_cr
    engine_mod.create_runner = _patched_cr

    engine = ExecutionEngine()

    async def _fake_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kw):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_planner

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store

    opened: list[str] = []

    async def _recording_gate(*, agent_id, **kw):
        # RECORDING, not blocking: counts every entry into the review gate (the three inline
        # sites inside _run_agent AND the declared gates:[human] path both delegate here).
        opened.append(agent_id)
        return
        yield  # async generator

    engine._run_review_gate = _recording_gate

    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Build me a tiny Python app.",
            pipeline_run_id=f"qa070-{uuid.uuid4().hex[:8]}",
            pipeline_type=_FIXTURE_ID,
            user_id="qa070-user",
            gate_agent_ids=[BUILD],                                # the wizard tick
            selections={BUILD: {"gates": ["human"]}},              # ISS-247 withHumanGate
        ):
            events.append(ev)
    finally:
        engine_mod.compile_for_run = _orig_compile
        engine_mod.resolve_alias = _orig_resolve_alias
        registry_mod.get_pipeline_agents = _orig_gpa
        factory_mod.create_runner = _orig_cr
        if _orig_ecr is not None:
            engine_mod.create_runner = _orig_ecr
        for sid in spec_ids:
            _SPEC_CACHE.pop(sid, None)

    types = [e.get("type") for e in events]
    errs = [e for e in events if e.get("type") == "error"]
    progress = [
        (e["data"]["task_number"], e["data"]["total_tasks"])
        for e in events
        if e.get("type") == "task_loop_progress"
    ]
    print(
        f"[{label}] review gates entered for {BUILD}: {opened.count(BUILD)}  "
        f"(all entries={opened})  tasks={progress}  "
        f"pipeline_complete={'pipeline_complete' in types}  errors={len(errs)}"
    )


if __name__ == "__main__":
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy

    print(f"TaskLoopStrategy.runs_agent_inline = {TaskLoopStrategy.runs_agent_inline}")
    asyncio.run(drive("AS SHIPPED - kwarg present  "))
    apply_mutation()  # delete `invocation_gated=False,` from TaskLoopStrategy.run (in memory)
    asyncio.run(drive("MUTATED    - kwarg deleted  "))
