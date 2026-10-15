"""QA-KB-124 re-analysis 07: does a fix for ISS-1156 reach the LIVE path? (offline: no network, no DB, no model)

Why this exists
  The 5-fixer applied the ISS-1156 card's predicate (`"route_decision" in spec.produces` at factory.py:727)
  and found it inert (evidence/qa-kb-124/fix-01-card-predicate-inert.txt). This probe answers the question
  the fixer sent back to analysis: HOW does the step's declared `produces` reach `_compose_system_prompt`,
  and does that make the run complete?

What it does
  Drives the REAL ExecutionEngine + REAL factory through the offline scripted-model harness
  (backend/tests/agents/_scripted_model.py) over three plans of ex_A1_loop:

    builtin    the file plan (tool-free steps, greeting pasted)                       control, must not change
    override   admin's SAVED OVERRIDE bdf009f2 (read/write granted, edges dropped)    the reported failure
    composer   the built-in plan with every step's grants flipped to read+write ON,    ISS-1182: a Composer-drawn
               every edge and produces/consumes intact                                 decision step, no override

  `check` is a Haiku-LIKE model whose behaviour depends on the system prompt it is actually handed
  (the live runs in analysis-02 are the evidence for both branches):
    - prompt contains "## How to deliver"  -> read the greeting file, write_file the decision into the delivery
      file, narrate in the reply (runs c10a03ed, caa766dc, 1260b7ba, 9a931a7a: 4 of 4)
    - prompt does not                      -> reply with the bare JSON decision (run 83001c0b, Bedrock Haiku,
      built-in plan). INFERRED for a write-GRANTED step with no delivery block: no live run exists, because the
      block is what the fix removes. The probe therefore proves the WIRING (the prompt a run really gets),
      not the model.

How to run: from a backend root (the repo's backend/, or a scratch copy with a candidate patch applied)
    cd <backend root> && PYTHONPATH=. <backend/.venv/bin/python> <this file>
"""

import asyncio
import copy
import json
import pathlib
import warnings

warnings.filterwarnings("ignore")

HERE = pathlib.Path(__file__).resolve().parent
OVERRIDE_STEPS = json.loads((HERE / "analysis-01-override-row-bdf009f2.json").read_text())["manifest_json"]["steps"]

import agents.execution_engine.engine as engine_mod  # noqa: E402
import agents.factory as factory_mod  # noqa: E402
from agents.execution_engine.overrides import merge_override_steps  # noqa: E402

print("backend under test:", pathlib.Path(factory_mod.__file__).resolve().parents[1])

PLAN = {"which": "builtin"}
_base_compile = engine_mod.compile_for_run


def _compile(pipeline_type, _orig=_base_compile):
    base = _orig(pipeline_type)
    if pipeline_type != "ex_A1_loop":
        return base
    if PLAN["which"] == "override":
        return merge_override_steps(base, OVERRIDE_STEPS, engine_mod._CAPABILITY_REGISTRY)
    if PLAN["which"] == "composer":
        plan = copy.deepcopy(base)
        for s in plan.steps:
            s.tools.read_files = True
            s.tools.write_files = True
        return plan
    return base


engine_mod.compile_for_run = _compile

from tests.agents import _scripted_model as sm  # noqa: E402
from tests.agents._scripted_model import _drive, _ScriptedTurn  # noqa: E402

SLUG = "build-me-a-thing-for-managing-tasks"  # topic slug of the harness's default user message
_Orig = sm.ScriptedFakeChatModel


class _CheckScript(list):
    decision = "retry"


def _text_of(content):
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in (content or []))


class HaikuLikeCheck(_Orig):
    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        if self._call_index == 0:
            system_text = "\n".join(_text_of(m.content) for m in messages if getattr(m, "type", "") == "system")
            decision = self._decision
            read = _ScriptedTurn(
                texts=[""], tool_calls=[("read_file", json.dumps({"file_path": f"/greet-{SLUG}.md"}), "c1")], usage=(5, 3)
            )
            if "## How to deliver" in system_text:
                turns = [
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
                                json.dumps({"file_path": f"/check-{SLUG}.md", "content": json.dumps({"decision": decision})}),
                                "c2",
                            )
                        ],
                        usage=(5, 3),
                    ),
                    _ScriptedTurn(texts=[""], usage=(5, 3)),
                ]
            else:
                reply = _ScriptedTurn(texts=[json.dumps({"decision": decision})], usage=(5, 3))
                turns = [reply] if PLAN["which"] == "builtin" else [read, reply]
            object.__setattr__(self, "_turns", turns)
        return super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def _model(turns):
    if isinstance(turns, _CheckScript):
        m = HaikuLikeCheck(turns)
        object.__setattr__(m, "_decision", turns.decision)  # the base __init__ copies `turns` into a plain list
        return m
    return _Orig(turns)


sm.ScriptedFakeChatModel = _model


def _scripts_for_factory():
    state = {"check": 0}

    def _scripts_for(agent_id):
        if agent_id != "custom-agent:check":
            return [_ScriptedTurn(texts=["Hello team!"], usage=(5, 3))]
        state["check"] += 1
        script = _CheckScript([_ScriptedTurn(texts=[""], usage=(5, 3))])
        script.decision = "retry" if state["check"] == 1 else "ok"
        return script

    return _scripts_for


async def scenario(tag, which):
    PLAN["which"] = which
    sm._scripts_for = _scripts_for_factory()
    events = await _drive("ex_A1_loop")
    print(f"\n===== {tag}")
    started = [e["data"].get("agent_id", "").split(":")[-1] for e in events if e.get("type") == "agent_start"]
    print("dispatch order         :", started)
    seen_greet_block = None
    for e in events:
        t, d = e.get("type"), e.get("data", {})
        if t == "agent_input" and d.get("agent_id") == "custom-agent:greet" and seen_greet_block is None:
            seen_greet_block = "How to deliver" in (d.get("system_prompt") or "")
        if t == "agent_input" and d.get("agent_id") == "custom-agent:check":
            sp = d.get("system_prompt") or ""
            print("check 'How to deliver' :", "How to deliver" in sp, "| context_message:", repr(d.get("context_message"))[:60])
        elif t == "tool_call" and d.get("agent_id") == "custom-agent:check":
            print("   check tool_call     :", d.get("tool"), json.dumps(d.get("args"))[:90])
        elif t in ("gate_blocked", "pipeline_failed", "pipeline_complete"):
            keep = ("step", "gate", "reason", "error")  # published_status omitted: DB-less finalization always says degraded here
            print(t, json.dumps({k: v for k, v in d.items() if k in keep}))
    print("greet (non-decision) 'How to deliver':", seen_greet_block, "(must stay as it is: the block is right for a step whose answer is a file)")


async def main():
    await scenario("builtin plan (control: tool-free, must not change)", "builtin")
    await scenario("admin's saved override bdf009f2 (the reported failure)", "override")
    await scenario("ISS-1182: built-in edges with the Composer's default read+write grants (no override)", "composer")


asyncio.run(main())
