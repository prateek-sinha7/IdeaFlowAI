"""QA-KB-124 re-analysis 09: what the delivery contract does on a loop's SECOND pass (offline: no network, no DB, no model)

Question
  The decision step is fixed by keeping `## How to deliver` away from a `route_decision` producer (analysis-07).
  `greet`, the step the loop re-runs, is NOT a decision step, so it keeps the block and is told on EVERY pass to
  `write_file` the same path (`artifact_name(instance_id, topic)` has no pass component). What does pass 2 get?

What it does
  Drives the REAL engine, factory and deepagents filesystem backend over the ex_A1_loop edges with the Composer's
  default read+write grants (the ISS-1182 shape), on a backend that already has the decision-step fix (run it from
  the scratch copy with `AgentContext.step_produces`, see analysis-07). `greet` is scripted to do exactly what the
  block says on each pass: `write_file` its delivery file, reply "Done!". `check` is a Haiku-like judge: it reads
  the greeting file and answers ok only if the text it READ contains a joke.

  Facts this prints (independent of any model): the tool_result of pass 2's write_file, the file on disk after the
  run, and whether the artifact fallback replaced it. What a real model does after the refusal (edit_file, a new
  path, give up) is NOT scripted here: INFERRED, would need a live run.

How to run (from a backend root that has the fix, e.g. the optA scratch copy):
    cd <backend root> && PYTHONPATH=. <backend/.venv/bin/python> <this file>
"""

import asyncio
import copy
import json
import pathlib
import warnings

warnings.filterwarnings("ignore")

import agents.execution_engine.engine as engine_mod  # noqa: E402
import agents.factory as factory_mod  # noqa: E402

print("backend under test:", pathlib.Path(factory_mod.__file__).resolve().parents[1])

_base_compile = engine_mod.compile_for_run


def _compile(pipeline_type, _orig=_base_compile):
    plan = copy.deepcopy(_orig(pipeline_type))
    if pipeline_type == "ex_A1_loop":
        for s in plan.steps:
            s.tools.read_files = True
            s.tools.write_files = True
    return plan


engine_mod.compile_for_run = _compile

from tests.agents import _scripted_model as sm  # noqa: E402
from tests.agents._scripted_model import _drive, _ScriptedTurn  # noqa: E402

SLUG = "build-me-a-thing-for-managing-tasks"
GREET = f"/greet-{SLUG}.md"
_Orig = sm.ScriptedFakeChatModel


def _text_of(content):
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in (content or []))


class _Judge(_Orig):
    """check: read the greeting file, then answer from the text it actually read."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        if self._call_index == 0:
            object.__setattr__(
                self,
                "_turns",
                [_ScriptedTurn(texts=[""], tool_calls=[("read_file", json.dumps({"file_path": GREET}), "c1")], usage=(5, 3)), None],
            )
        elif self._call_index == 1:
            tool_text = " ".join(_text_of(m.content) for m in messages if getattr(m, "type", "") == "tool")
            decision = "ok" if "joke" in tool_text.lower() or "cross the road" in tool_text.lower() else "retry"
            print(f"   check read: {tool_text.strip()[:70]!r} -> {decision}")
            self._turns[1] = _ScriptedTurn(texts=[json.dumps({"decision": decision})], usage=(5, 3))
        return super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


class _Marker(list):
    pass


def _model(turns):
    return _Judge(turns) if isinstance(turns, _Marker) else _Orig(turns)


sm.ScriptedFakeChatModel = _model


def _scripts_for_factory():
    n = {"greet": 0}

    def _scripts_for(agent_id):
        if agent_id == "custom-agent:check":
            return _Marker([_ScriptedTurn(texts=[""], usage=(5, 3))])
        if agent_id == "custom-agent:greet":
            n["greet"] += 1
            body = "Hello team!" if n["greet"] == 1 else "Hello team! Why did the chicken cross the road? A joke."
            return [
                _ScriptedTurn(texts=[""], tool_calls=[("write_file", json.dumps({"file_path": GREET, "content": body}), f"w{n['greet']}")], usage=(5, 3)),
                _ScriptedTurn(texts=["Done!"], usage=(5, 3)),
            ]
        return [_ScriptedTurn(texts=["Done!"], usage=(5, 3))]

    return _scripts_for


async def main():
    sm._scripts_for = _scripts_for_factory()
    events = await _drive("ex_A1_loop")
    print("\n===== ex_A1_loop edges, Composer-default read+write grants, decision-step fix present")
    print("dispatch order:", [e["data"].get("agent_id", "").split(":")[-1] for e in events if e.get("type") == "agent_start"])
    n = 0
    for e in events:
        t, d = e.get("type"), e.get("data", {})
        if t == "tool_result" and d.get("agent_id") == "custom-agent:greet":
            n += 1
            print(f"   greet pass {n} write_file -> {str(d.get('result'))[:150]!r}")
        elif t == "artifact_fallback":
            print("   artifact_fallback:", d)
        elif t in ("pipeline_complete", "pipeline_failed", "budget_aborted", "gate_blocked"):
            print(t, json.dumps({k: v for k, v in d.items() if k in ("error", "reason", "step", "passes", "max_passes")}))
    root = pathlib.Path(sm._RUNS_ROOT)
    for p in sorted(root.rglob(f"greet-{SLUG}.md")):
        print("file on disk after the run:", p.name, "->", repr(p.read_text()))


asyncio.run(main())
