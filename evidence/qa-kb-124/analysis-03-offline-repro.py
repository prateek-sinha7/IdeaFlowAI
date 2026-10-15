"""QA-KB-124 analysis 03: offline reproduction of the ex_A1_loop failure (no network, no DB, no model).

What it does
  Drives the REAL engine + REAL factory through the offline scripted-model harness
  (backend/tests/agents/_scripted_model.py) twice:

    scenario 1  the BUILT-IN ex_A1_loop plan (agents/workflows/ex_A1_loop/workflow.yaml)
    scenario 2  the admin's SAVED OVERRIDE of ex_A1_loop (analysis-01-override-row-bdf009f2.json,
                a SELECT snapshot of workflows.id = bdf009f2-...), merged exactly as the launch does
                (agents.execution_engine.overrides.merge_override_steps)

  `check` is scripted to behave like the live Bedrock Haiku runs recorded in run_events
  (see analysis-02): when it has a delivery file it reads the greeting, WRITES its decision to the
  delivery file with write_file, and replies with narration only; when it has no write tool it
  replies with the JSON decision as plain text (that is what run 83001c0b did on the built-in plan).

How to run (from the repo root of this worktree)
  cd backend && PYTHONPATH=. <venv python> ../evidence/qa-kb-124/analysis-03-offline-repro.py

Expected today
  scenario 1: pipeline_complete, `check` system prompt has no "How to deliver", greeting pasted.
  scenario 2: gate_blocked + pipeline_failed "Check's conditional gate had nowhere to route: ...",
              `check` system prompt ends with "## How to deliver ... Call `write_file` ...", empty
              context_message, tool_calls read_file + write_file.
"""

import asyncio
import json
import pathlib
import warnings

warnings.filterwarnings("ignore")

HERE = pathlib.Path(__file__).resolve().parent
OVERRIDE_STEPS = json.loads((HERE / "analysis-01-override-row-bdf009f2.json").read_text())["manifest_json"]["steps"]

import agents.execution_engine.engine as engine_mod  # noqa: E402
from agents.execution_engine.overrides import merge_override_steps  # noqa: E402

_base_compile = engine_mod.compile_for_run
_USE_OVERRIDE = {"on": False}


def _compile(pipeline_type, _orig=_base_compile):
    base = _orig(pipeline_type)
    if pipeline_type == "ex_A1_loop" and _USE_OVERRIDE["on"]:
        return merge_override_steps(base, OVERRIDE_STEPS, engine_mod._CAPABILITY_REGISTRY)
    return base


engine_mod.compile_for_run = _compile

from tests.agents import _scripted_model as _sm  # noqa: E402
from tests.agents._scripted_model import _drive, _ScriptedTurn  # noqa: E402

SLUG = "build-me-a-thing-for-managing-tasks"  # topic slug of the harness's default user message


def _scripts_for_factory():
    state = {"check": 0}

    def _scripts_for(agent_id):
        if agent_id != "custom-agent:check":
            return [_ScriptedTurn(texts=["Hello team!"], usage=(5, 3))]
        state["check"] += 1
        if not _USE_OVERRIDE["on"]:
            # built-in plan: no write tool, greeting pasted -> Haiku replies with the JSON as text
            decision = "retry" if state["check"] == 1 else "ok"
            return [_ScriptedTurn(texts=[f'{{"decision": "{decision}"}}'], usage=(5, 3))]
        # override plan: write grant + "How to deliver" -> read the greeting file, write the decision
        # to the delivery file, narrate in the reply (runs c10a03ed / caa766dc / 1260b7ba / 9a931a7a)
        return [
            _ScriptedTurn(
                texts=["I need to read the greeting file first."],
                tool_calls=[("read_file", json.dumps({"file_path": f"/greet-{SLUG}.md"}), "c1")],
                usage=(5, 3),
            ),
            _ScriptedTurn(
                texts=["Now I'll write my answer to the output file:"],
                tool_calls=[
                    (
                        "write_file",
                        json.dumps({"file_path": f"/check-{SLUG}.md", "content": '{"decision": "retry"}'}),
                        "c2",
                    )
                ],
                usage=(5, 3),
            ),
            _ScriptedTurn(texts=[""], usage=(5, 3)),
        ]

    return _scripts_for


async def scenario(tag, use_override):
    _USE_OVERRIDE["on"] = use_override
    _sm._scripts_for = _scripts_for_factory()
    events = await _drive("ex_A1_loop")
    print(f"\n===== {tag}")
    for e in events:
        t, d = e.get("type"), e.get("data", {})
        if t == "agent_input" and d.get("agent_id") == "custom-agent:check":
            sp = d.get("system_prompt") or ""
            print("check.context_message  :", repr(d.get("context_message")))
            print("check 'How to deliver' :", "How to deliver" in sp)
            print("check system_prompt end:", repr(sp[-200:]))
        elif t in ("tool_call", "tool_result") and d.get("agent_id") == "custom-agent:check":
            print(" ", t, d.get("tool"), json.dumps(d.get("args") or d.get("result"))[:110])
        elif t in ("gate_blocked", "pipeline_failed", "pipeline_complete"):
            keep = ("step", "gate", "reason", "error")  # published_status omitted: DB-less finalization always reports "degraded" in this harness
            print(t, json.dumps({k: v for k, v in d.items() if k in keep}))


async def main():
    await scenario("scenario 1: BUILT-IN plan (tool-free steps, greeting pasted)", False)
    await scenario("scenario 2: admin's SAVED OVERRIDE (read/write granted, consumes/produces dropped)", True)


asyncio.run(main())
