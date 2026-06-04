"""Shared offline parity driver for the Phase-3 verify gate (task #46).

Runs ``ExecutionEngine.execute()`` end-to-end OFFLINE (no network, no real
Bedrock) against a *scripted* ``BaseChatModel`` and prints the ordered list of
yielded engine event dicts as JSON Lines to stdout. The SAME file is dropped
into BOTH worktrees:

  * the working tree  → the NEW (post-cutover, ``create_runner``) engine;
  * a ``git worktree`` at HEAD → the OLD (pre-cutover, ``create_agent``) engine.

The parity test (`test_engine_ws_event_parity.py`) invokes this driver in a
subprocess per (engine, pipeline) so two incompatible copies of
``agents.execution_engine.engine`` never share one interpreter, then diffs the
two event streams.

WHY A FULL ``execute()`` RUN (not an internal method): the WS contract is
exactly what the engine *yields* — the websocket drainer
(``app/api/websocket.py`` ~1277) forwards ``event["type"]`` + ``event["data"]``
verbatim into the ``{type, chunk, section, data}`` envelope. Driving the public
``execute()`` therefore captures the real, end-to-end outbound event vocabulary.

OFFLINE SCAFFOLDING (test-only monkeypatches; NO production code changed):
  * Scripted model injected as ``model_id`` (NEW: used as-is by the runner;
    OLD: a ``create_agent`` wrapper sets ``agent.llm_with_tools = <fake>`` — the
    proven Phase-1 recipe, since legacy ``DeepAgent`` treats ``model`` as a str).
  * ``_run_planner`` → returns a default PROCEED context (the planner makes a
    real LLM call; prototype pipelines skip it anyway).
  * ``ALWAYS_CLARIFY`` forced False (the clarifier needs live WS round-trips).
  * ``ArtifactStore.store`` → async no-op (avoids DB coupling; deterministic).
  * ``_run_review_gate`` → no-op async-gen (the inter-agent gate is engine-level
    and byte-identical across both engines — proven separately by the P2 static
    event-type diff; suppressing it keeps the agent-streaming parity clean and
    non-blocking, since gated text agents would otherwise ``await event.wait()``).
  * ``RUNS_ROOT`` → a fresh temp dir (the real default ``/app/runs`` is absent
    locally); the per-run sandbox lands there so disk deliverables work.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

# ── Make the backend package root importable (tests/agents/_parity_driver.py →
#    backend/). Works whether run as a script or imported. ───────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ── RUNS_ROOT must be set BEFORE app.core.config / sandbox import it ──────────
_RUNS_ROOT = os.environ.get("PARITY_RUNS_ROOT") or tempfile.mkdtemp(prefix="parity-runs-")
os.environ["RUNS_ROOT"] = _RUNS_ROOT
# Force the InMemory checkpointer + sqlite (no Postgres / no creds needed).
os.environ.setdefault("ENV", "development")

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, AIMessageChunk  # noqa: E402
from langchain_core.messages.tool import tool_call_chunk  # noqa: E402
from langchain_core.outputs import (  # noqa: E402
    ChatGeneration,
    ChatGenerationChunk,
    ChatResult,
)


# ===========================================================================
# Scripted fake chat model — the proven Phase-1 recipe (see
# tests/agents/test_deep_agent_runner_parity.py module docstring).
# ===========================================================================


class _ScriptedTurn:
    def __init__(
        self,
        texts: list[str],
        tool_calls: list[tuple[str, str, str]] | None = None,
        usage: tuple[int, int] | None = None,
    ) -> None:
        self.texts = texts
        self.tool_calls = tool_calls or []
        self.usage = usage


class ScriptedFakeChatModel(BaseChatModel):
    """Minimal BaseChatModel that streams a different scripted turn per call."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, turns: list[_ScriptedTurn], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_turns", list(turns))
        object.__setattr__(self, "_call_index", 0)

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedFakeChatModel":
        return self

    def _next_turn(self) -> _ScriptedTurn:
        idx: int = self._call_index
        turns: list[_ScriptedTurn] = self._turns
        turn = turns[idx] if idx < len(turns) else turns[-1]
        object.__setattr__(self, "_call_index", idx + 1)
        return turn

    def _stream(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        turn = self._next_turn()
        pieces = turn.texts if turn.texts else [""]
        last_i = len(pieces) - 1
        for i, piece in enumerate(pieces):
            extra: dict[str, Any] = {}
            tcc: list = []
            usage = None
            if i == last_i:
                for tidx, (name, json_args, call_id) in enumerate(turn.tool_calls):
                    tcc.append(
                        tool_call_chunk(name=name, args=json_args, id=call_id, index=tidx)
                    )
                if turn.usage is not None:
                    t_in, t_out = turn.usage
                    usage = {
                        "input_tokens": t_in,
                        "output_tokens": t_out,
                        "total_tokens": t_in + t_out,
                    }
                extra["chunk_position"] = "last"
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=piece,
                    tool_call_chunks=tcc,
                    usage_metadata=usage,
                    **extra,
                )
            )

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        chunks = list(self._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        text = "".join(c.message.content for c in chunks if isinstance(c.message.content, str))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


# ===========================================================================
# Per-agent script registry — keyed by agent id, returns the scripted turns
# for THAT agent. The engine builds one agent per spec and runs it once (the
# build agent runs once per task), so each agent's model consumes its own turns.
#
# Tool-call args differ by engine "world" (the migration deliberately swapped
# emit_artifact→native write_file, workspace.write_file(path=)→native
# write_file(file_path=)); the event-TYPE sequence is what must match. The
# ``world`` arg ("old"|"new") selects the right tool name/args per agent.
# ===========================================================================


def _scripts_for(agent_id: str, world: str) -> list[_ScriptedTurn]:
    import json as _j

    # ── Text-only agents (tools=[]): one turn, text + usage, no tool calls. ──
    TEXT_ONLY = {
        "domain-analyst",
        "epic-architect",
        "story-estimator",
        "nfr-specialist",
        "backlog-reviewer",
        "backlog-compiler",
        "prototype-specify",
        "prototype-plan",
        # app_builder text agents
        "material-analyzer",
        "app-user-stories",
        "app-system-design",
        "app-security-architecture",
        "app-ux-design",
        "app-api-design",
        "app-database-design",
        "app-feature-implementation",
        "app-infra-generator",
        "app-code-compliance",
        "app-test-implementation",
        "app-test-compliance",
        "app-devops",
        "app-sdlc-governance",
    }
    if agent_id in TEXT_ONLY:
        # prototype-plan must emit a parseable task list so the build loop finds
        # exactly 2 tasks (## Task N:) — keeps the prototype run deterministic.
        if agent_id == "prototype-plan":
            return [
                _ScriptedTurn(
                    texts=[
                        "## Task 1: Build the HTML shell\n"
                        "Create the document skeleton.\n\n"
                        "## Task 2: Fill the dashboard page\n"
                        "Add the dashboard content.\n"
                    ],
                    usage=(40, 30),
                )
            ]
        return [_ScriptedTurn(texts=[f"{agent_id} output line one. ", "line two."], usage=(12, 7))]

    # ── prototype-build (tools=prototype_emit_only): runs once per task. ──────
    # OLD world: emit_artifact(html=…) + report_task_complete(...).
    # NEW world: write_file(file_path="prototype.html", content=…) +
    #            report_task_complete(...).
    # Both worlds call report_task_complete with task_number/task_title/summary
    # (the engine reads those args for task_progress in BOTH).
    if agent_id == "prototype-build":
        html = "<!doctype html><html><body><section data-page='dashboard'>hi</section></body></html>"
        if world == "old":
            return [
                _ScriptedTurn(
                    texts=["Building the page. "],
                    tool_calls=[
                        ("emit_artifact", _j.dumps({"html": html, "title": "Prototype"}), "c_emit"),
                        ("report_task_complete", _j.dumps({"task_number": 1, "task_title": "Build shell", "summary": "did it"}), "c_rtc"),
                    ],
                    usage=(50, 20),
                ),
                _ScriptedTurn(texts=["Done."], usage=(10, 5)),
            ]
        # new world
        return [
            _ScriptedTurn(
                texts=["Building the page. "],
                tool_calls=[
                    ("write_file", _j.dumps({"file_path": "prototype.html", "content": html}), "c_wf"),
                    ("report_task_complete", _j.dumps({"task_number": 1, "task_title": "Build shell", "summary": "did it"}), "c_rtc"),
                ],
                usage=(50, 20),
            ),
            _ScriptedTurn(texts=["Done."], usage=(10, 5)),
        ]

    # ── prototype-validate (tools=prototype_emit_only): text-only run is fine —
    # it may call no tools (validation pass). Keep it pure text so the prototype
    # pipeline terminates deterministically.
    if agent_id == "prototype-validate":
        return [_ScriptedTurn(texts=["Validation passed. No P0 issues."], usage=(20, 10))]

    # ── Code-gen agents (tools=workspace): write 2 files then a final text. ───
    # OLD world: workspace write_file(path=…, content=…).
    # NEW world: native write_file(file_path=…, content=…).
    if agent_id in ("app-code-generator", "prototype-revision-agent"):
        def mk(p, c):
            # OLD world uses path=; NEW world uses native write_file's file_path=.
            key = "path" if world == "old" else "file_path"
            return ("write_file", _j.dumps({key: p, "content": c}), f"c_{p}")
        if agent_id == "prototype-revision-agent":
            # Revision edits prototype.html in place.
            return [
                _ScriptedTurn(
                    texts=["Revising. "],
                    tool_calls=[mk("prototype.html", "<!doctype html><html><body>revised</body></html>")],
                    usage=(30, 15),
                ),
                _ScriptedTurn(texts=["Revision complete."], usage=(8, 4)),
            ]
        return [
            _ScriptedTurn(
                texts=["Generating files. "],
                tool_calls=[
                    mk("src/app.py", "print('hello')\n"),
                    mk("README.md", "# Generated App\n"),
                ],
                usage=(60, 25),
            ),
            _ScriptedTurn(texts=["All files written."], usage=(10, 5)),
        ]

    # Fallback — a generic text turn (unknown agent).
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


# ===========================================================================
# Engine driver
# ===========================================================================


async def _drive(pipeline_type: str, world: str) -> list[dict]:
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents

    # ── Force RUNS_ROOT to our temp dir at RUNTIME ────────────────────────────
    # The env var is set at import, but ``app.core.config.settings`` may have been
    # loaded earlier (e.g. by another test / conftest) with the default ``/app/runs``
    # (read-only here). RunSandbox reads ``settings.RUNS_ROOT`` in __init__, so we
    # override the live attribute so the per-run sandbox lands in the temp dir.
    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    # ── Disable ALWAYS_CLARIFY (the clarifier needs live WS round-trips). ─────
    engine_mod.ALWAYS_CLARIFY = False

    specs = get_pipeline_agents(pipeline_type)

    # ── Per-agent scripted model factory ──────────────────────────────────────
    # The engine creates one agent per spec via create_agent (OLD) / create_runner
    # (NEW). We inject a per-agent scripted model so each agent consumes its own
    # script. For NEW: the model instance flows in as ctx.model and is used as-is.
    # For OLD: legacy DeepAgent treats `model` as a str, so we wrap create_agent
    # to overwrite `.llm_with_tools` with the fake (the proven Phase-1 recipe).

    import agents.factory as factory_mod

    # Snapshot the originals so we can RESTORE them in finally (the engine is run
    # repeatedly in one pytest process across parametrized tests — leaking a
    # nested wrapper or a stale patch would corrupt later runs).
    _orig_create_runner = factory_mod.create_runner
    _orig_create_agent = factory_mod.create_agent
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)
    _orig_engine_create_agent = getattr(engine_mod, "create_agent", None)

    if world == "new":

        def _patched_create_runner(agent_id, ctx, **kw):
            ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id, world))
            return _orig_create_runner(agent_id, ctx, **kw)

        factory_mod.create_runner = _patched_create_runner
        # The engine imported create_runner by name at module load.
        engine_mod.create_runner = _patched_create_runner
    else:

        def _patched_create_agent(agent_id, ctx):
            agent = _orig_create_agent(agent_id, ctx)
            agent.llm_with_tools = ScriptedFakeChatModel(_scripts_for(agent_id, world))
            return agent

        factory_mod.create_agent = _patched_create_agent
        engine_mod.create_agent = _patched_create_agent

    engine = ExecutionEngine()

    # ── Neutralise the planner (real LLM call) → default PROCEED context. ─────
    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom"):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    # ── Artifact store writes → no-op (avoid DB coupling, stay deterministic). ─
    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    # ── Inter-agent review gate → no-op (engine-level, identical across engines;
    # proven by the P2 static type diff). Keeps the parity capture non-blocking. ─
    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover — make it an async generator

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    # ── Run execute() and capture every yielded event dict. ───────────────────
    # The state machine is a process-wide singleton keyed on run_id, so each call
    # needs a UNIQUE run_id (a reused id is "already completed" → StateMachineError).
    import uuid as _uuid

    events: list[dict] = []
    run_id = f"parity-{pipeline_type}-{world}-{_uuid.uuid4().hex[:8]}"

    # Prototype agents declare injects=['template', 'design_system', ...]; the
    # factory raises TemplateMissingError without a template body. Supply a
    # minimal od_context so injection succeeds and the build/task_progress path
    # actually runs. (Same od_context is fed to BOTH engines.)
    od_context = None
    if pipeline_type in ("prototype", "od_prototype"):
        od_context = {
            "template_body": "## Workflow\nUse .card and .grid classes. Build pages into <section data-page>.",
            "template_id": "web-prototype",
            "ds_id": "default",
            "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}",
            "craft_block": "Keep markup semantic; wire every nav link.",
            "is_design_system_required": True,
        }

    # NEW execute() accepts gate_agent_ids; OLD does not. Build kwargs accordingly.
    kwargs: dict[str, Any] = dict(
        agents=list(specs),
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=run_id,
        pipeline_type=pipeline_type,
        user_id="parity-user",
        od_context=od_context,
    )
    import inspect

    if "gate_agent_ids" in inspect.signature(engine.execute).parameters:
        kwargs["gate_agent_ids"] = []  # suppress all gates (NEW engine)

    try:
        async for ev in engine.execute(**kwargs):
            # Keep only what parity asserts on: the type and the data KEY SHAPE.
            events.append(ev)
    finally:
        # Restore the factory/engine globals so repeated _drive() calls in one
        # process (parametrized pytest) never accumulate patches.
        factory_mod.create_runner = _orig_create_runner
        factory_mod.create_agent = _orig_create_agent
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        if _orig_engine_create_agent is not None:
            engine_mod.create_agent = _orig_engine_create_agent
    return events


def _serialize(events: list[dict]) -> list[dict]:
    """Reduce each event to {type, data_keys, extra} — JSON-safe, value-agnostic.

    Parity is on the ordered event TYPE sequence and each event's DATA KEY SHAPE
    (not volatile values like timestamps/durations). We also surface a few
    load-bearing values the task calls out: tool names, task_progress counts/keys.
    """
    out: list[dict] = []
    for ev in events:
        t = ev.get("type")
        data = ev.get("data", {}) if isinstance(ev.get("data"), dict) else {}
        rec: dict[str, Any] = {"type": t, "data_keys": sorted(data.keys())}
        # Load-bearing detail per the task's P1 checklist:
        if t == "tool_call":
            rec["tool"] = data.get("tool")
        elif t == "tool_result":
            rec["tool"] = data.get("tool")
            rec["result_text"] = str(data.get("result", ""))
        elif t == "task_progress":
            rec["completed_count"] = data.get("completed_count")
            ct = data.get("completed_tasks") or []
            rec["completed_task_keys"] = sorted(ct[0].keys()) if ct else []
            rec["completed_tasks"] = ct
        elif t == "agent_complete":
            rec["token_keys"] = sorted(
                k for k in data.keys() if "token" in k
            )
        out.append(rec)
    return out


def main() -> None:
    pipeline_type = sys.argv[1]
    world = sys.argv[2]  # "old" | "new"
    events = asyncio.run(_drive(pipeline_type, world))
    serialized = _serialize(events)
    # Emit a single JSON object so the parent can json.loads it cleanly.
    print("PARITY_RESULT_JSON_START")
    print(json.dumps({"raw_types": [e.get("type") for e in events], "events": serialized}))
    print("PARITY_RESULT_JSON_END")


if __name__ == "__main__":
    main()
