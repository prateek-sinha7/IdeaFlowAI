"""QA-KB-030 analyzer run-level check (scratch; OFFLINE scripted model; no repo writes).

Drives the REAL ExecutionEngine.execute() through the SC-001 task_loop fixture with the
exact launch shape the wizard produces when the user ticks the build agent in
"Review gates":   gate_agent_ids=[<agent>]   +   selections[<agent>].gates=["human"]
(ReviewGatesSection.toggle -> withHumanGate; IdeaInputPage/LaunchWizard launch payload).

Counts how many times a review gate is actually opened for the build agent:
  CURRENT   : TaskLoopStrategy undeclared runs_agent_inline  (as shipped)
  PROPOSED  : TaskLoopStrategy.runs_agent_inline = False     (set in-process only; no file edit)

Hermetic like tests/conftest.py: DATABASE_URL is pinned to a scratch SQLite file BEFORE any
app import, the model is a ScriptedFakeChatModel, the checkpointer is InMemory.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

SCRATCH = Path(os.environ["QA_SCRATCH"])
_DB = SCRATCH / "qa_kb_030_run.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"          # MUST precede any app import
os.environ["PARITY_RUNS_ROOT"] = str(SCRATCH / "runs")   # sandbox lands in scratch
(SCRATCH / "runs").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ENV", "development")
sys.path.insert(0, ".")

import app.models  # noqa: F401,E402  registers models on Base.metadata
from app.models.database import Base, engine as _db_engine  # noqa: E402

assert str(_db_engine.url).startswith("sqlite"), f"NOT hermetic: {_db_engine.url}"
Base.metadata.create_all(bind=_db_engine)
print("hermetic DB:", _db_engine.url)

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
        opened.append(agent_id)
        return
        yield  # async generator

    engine._run_review_gate = _recording_gate

    events: list[dict] = []
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Build me a tiny Python app.",
            pipeline_run_id=f"qa030-{uuid.uuid4().hex[:8]}",
            pipeline_type=_FIXTURE_ID,
            user_id="qa030-user",
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
    progress = [(e["data"]["task_number"], e["data"]["total_tasks"]) for e in events if e.get("type") == "task_loop_progress"]
    print(
        f"[{label}] review gates opened for {BUILD}: {opened.count(BUILD)}  "
        f"(all opened={opened})  tasks={progress}  pipeline_complete={'pipeline_complete' in types}  errors={len(errs)}"
    )


if __name__ == "__main__":
    asyncio.run(drive("CURRENT  - TaskLoopStrategy undeclared"))
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy

    TaskLoopStrategy.runs_agent_inline = False   # in-process simulation of the one-line fix
    asyncio.run(drive("PROPOSED - runs_agent_inline = False "))
