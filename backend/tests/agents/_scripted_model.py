"""Shared offline test harness — the scripted ``BaseChatModel`` recipe + the
end-to-end ``ExecutionEngine.execute()`` driver used by the durable Phase-3/4/5
verify-gate tests.

This module is the SURVIVING, post-cutover subset of what used to live in
``tests/agents/_parity_driver.py`` (deleted in the Phase-7a legacy excision).
The old-vs-new *worktree parity* harness (a ``git worktree`` at HEAD running the
pre-cutover ``create_agent`` engine, plus its ``main()`` / ``_serialize`` JSON
emitter) was migration-only scaffolding and is gone. What remains here is the
reusable machinery the live tests still depend on:

  * ``ScriptedFakeChatModel`` + ``_ScriptedTurn`` — the proven scripted-model
    recipe (a minimal ``BaseChatModel`` whose ``_stream`` yields real
    ``AIMessageChunk``s with ``tool_call_chunks`` + ``usage_metadata`` and a
    no-op ``bind_tools``). The stock LangChain fakes do NOT drive the deepagents
    loop, so this hand-rolled model is the canonical way to script the runtime
    offline (plan §12 "Scripted-model test recipe").
  * ``_scripts_for(agent_id)`` — a per-agent script registry for the LIVE
    (``create_runner``) engine, so a whole pipeline can be driven deterministically.
  * ``_drive(pipeline_type)`` — runs the public ``ExecutionEngine.execute()``
    end-to-end OFFLINE (no network / no Bedrock) against per-agent scripted
    models and returns the ordered list of yielded engine event dicts. Driving
    the public ``execute()`` captures the real outbound WS event vocabulary
    (the websocket drainer forwards ``event["type"]`` + ``event["data"]``
    verbatim).

OFFLINE SCAFFOLDING (test-only monkeypatches; NO production code changed):
  * Scripted model injected as ``ctx.model`` (used as-is by the runner).
  * ``_run_planner`` → default PROCEED context (the planner makes a real LLM
    call; prototype pipelines skip it anyway).
  * ``ALWAYS_CLARIFY`` forced False (the clarifier needs live WS round-trips).
  * ``ArtifactStore.store`` → async no-op (avoids DB coupling; deterministic).
  * ``_run_review_gate`` → no-op async-gen (the inter-agent gate is engine-level;
    suppressing it keeps the agent-streaming capture non-blocking).
  * ``RUNS_ROOT`` → a fresh temp dir (the real default ``/app/runs`` is absent
    locally); the per-run sandbox lands there so disk deliverables work.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

# ── Make the backend package root importable (tests/agents/_scripted_model.py →
#    backend/). Works whether run as a script or imported. ───────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ── RUNS_ROOT must be set BEFORE app.core.config / sandbox import it ──────────
_RUNS_ROOT = os.environ.get("PARITY_RUNS_ROOT") or tempfile.mkdtemp(prefix="harness-runs-")
os.environ["RUNS_ROOT"] = _RUNS_ROOT
# Force the InMemory checkpointer (no Postgres / no creds needed).
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
# Scripted fake chat model — the proven recipe (plan §12).
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
# for THAT agent in the LIVE (create_runner) world. The engine builds one agent
# per spec and runs it once (the build agent runs once per task), so each
# agent's model consumes its own turns.
# ===========================================================================


def _scripts_for(agent_id: str) -> list[_ScriptedTurn]:
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

    # ── od_ppt / ppt agents (tools=[], text-only). ───────────────────────────
    # The three deck agents (od-ppt-brief-analyst / od-ppt-composer /
    # od-ppt-validator) are text-only (no filesystem tools), so the deck is a
    # streamed-text deliverable — NOT a file on disk. _resolve_final_output's
    # text/PPT branch takes the LAST agent's streamed output as the deliverable
    # (the validator here), unwrapping a single <artifact>…</artifact> wrapper.
    # So the deck the characterization test snapshots is whatever the VALIDATOR
    # streams. Keep each turn's text + usage FIXED for determinism.
    #
    # od-ppt-brief-analyst declares injects=['template'] and od-ppt-composer
    # declares injects=['template','design_system']; _drive seeds an od_context
    # for od_ppt/ppt (below) so _compose_injection does not raise
    # TemplateMissingError. (D-02 / PATTERNS S2.)
    if agent_id == "od-ppt-brief-analyst":
        return [
            _ScriptedTurn(
                texts=[
                    "## Slide Plan\n",
                    "1. Title slide. 2. Problem. 3. Solution. 4. Closing.\n",
                ],
                usage=(18, 12),
            )
        ]
    if agent_id == "od-ppt-composer":
        # The composer narrates building the deck; its text is consumed by the
        # validator (last agent), whose output is the actual deliverable.
        return [
            _ScriptedTurn(
                texts=["Composing the 4-slide deck per the strategist plan."],
                usage=(40, 30),
            )
        ]
    if agent_id == "od-ppt-validator":
        # LAST agent → its streamed output IS the deliverable (text/PPT class).
        # Emit the final deck wrapped in a single <artifact> tag so
        # _resolve_final_output unwraps it to the raw deck HTML (deterministic,
        # non-empty). Plain markup (no translateX/vw + .stage/.slide) so the
        # engine's carousel sanitizer passes it through unchanged.
        deck = (
            "<!doctype html><html><head><title>Deck</title></head>"
            "<body>"
            "<section class='deck-slide'>Title</section>"
            "<section class='deck-slide'>Problem</section>"
            "<section class='deck-slide'>Solution</section>"
            "<section class='deck-slide'>Closing</section>"
            "</body></html>"
        )
        return [
            _ScriptedTurn(
                texts=[f"Validation passed. No P0 issues.\n<artifact>{deck}</artifact>"],
                usage=(22, 14),
            )
        ]

    # ── prototype-build (tools=prototype_emit_only): runs once per task. ──────
    # NEW world: write_file(file_path="prototype.html", content=…) +
    #            report_task_complete(task_number/task_title/summary).
    if agent_id == "prototype-build":
        html = "<!doctype html><html><body><section data-page='dashboard'>hi</section></body></html>"
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
    # NEW world: native write_file(file_path=…, content=…).
    if agent_id in ("app-code-generator", "prototype-revision-agent"):
        def mk(p, c):
            return ("write_file", _j.dumps({"file_path": p, "content": c}), f"c_{p}")
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
# Engine driver (LIVE create_runner path only).
# ===========================================================================


async def _drive(pipeline_type: str, world: str = "new") -> list[dict]:
    """Run ``ExecutionEngine.execute()`` end-to-end offline and return the
    ordered list of yielded engine event dicts.

    Only the LIVE (``create_runner``) world is supported — the pre-cutover
    ``create_agent`` path was deleted in Phase 7a. ``world`` is retained for
    call-site compatibility; any value other than ``"new"`` is rejected.
    """
    if world != "new":
        raise ValueError(
            f"_drive only supports the live 'new' engine world; got {world!r}. "
            "The pre-cutover 'old' (create_agent) path was removed in Phase 7a."
        )

    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents

    # ── Resolve od_ aliases for AGENT LOOKUP ONLY (mirrors the WS handler). ────
    # ``od_prototype`` is an OpenDesign-context alias of ``prototype``: it has NO
    # AGENT.md of its own (the prototype agents declare ``pipeline_type:
    # prototype``), so ``get_pipeline_agents("od_prototype")`` returns ∅ and the
    # resolver rejects the run ("must contain at least 1 agent"). The production
    # WS ``run_pipeline`` handler resolves the alias for the agent lookup but
    # forwards the UNALIASED label to ``execute()`` (engine.py keeps both
    # spellings on the prototype deliverable path — see _PROTOTYPE_PIPELINE_TYPES).
    # We replicate exactly that: look up specs under the base, drive under the
    # original label. ``ppt`` is likewise an alias of ``od_ppt`` (the deck agents
    # declare ``pipeline_type: od_ppt``); ``od_ppt`` itself IS a real registry key.
    _OD_ALIAS_FOR_LOOKUP = {"od_prototype": "prototype", "ppt": "od_ppt"}
    _lookup_type = _OD_ALIAS_FOR_LOOKUP.get(pipeline_type, pipeline_type)

    # ── Force RUNS_ROOT to our temp dir at RUNTIME ────────────────────────────
    # The env var is set at import, but ``app.core.config.settings`` may have been
    # loaded earlier (e.g. by another test / conftest) with the default ``/app/runs``
    # (read-only here). RunSandbox reads ``settings.RUNS_ROOT`` in __init__, so we
    # override the live attribute so the per-run sandbox lands in the temp dir.
    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    # ── Disable ALWAYS_CLARIFY (the clarifier needs live WS round-trips). ─────
    engine_mod.ALWAYS_CLARIFY = False

    specs = get_pipeline_agents(_lookup_type)

    # ── Per-agent scripted model factory ──────────────────────────────────────
    # The engine creates one agent per spec via create_runner. We inject a
    # per-agent scripted model so each agent consumes its own script; the model
    # instance flows in as ctx.model and is used as-is by the runner.
    import agents.factory as factory_mod

    # Snapshot the originals so we can RESTORE them in finally (the engine is run
    # repeatedly in one pytest process across parametrized tests — leaking a
    # nested wrapper or a stale patch would corrupt later runs).
    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    # The engine imported create_runner by name at module load.
    engine_mod.create_runner = _patched_create_runner

    engine = ExecutionEngine()

    # ── Neutralise the planner (real LLM call) → default PROCEED context. ─────
    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom"):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    # ── Artifact store writes → no-op (avoid DB coupling, stay deterministic). ─
    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    # ── Inter-agent review gate → no-op (engine-level; keeps capture non-blocking). ─
    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover — make it an async generator

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    # ── Run execute() and capture every yielded event dict. ───────────────────
    # The state machine is a process-wide singleton keyed on run_id, so each call
    # needs a UNIQUE run_id (a reused id is "already completed" → StateMachineError).
    import uuid as _uuid

    events: list[dict] = []
    run_id = f"harness-{pipeline_type}-{_uuid.uuid4().hex[:8]}"

    # Prototype agents declare injects=['template', 'design_system', ...]; the
    # factory raises TemplateMissingError without a template body. Supply a
    # minimal od_context so injection succeeds and the build/task_progress path
    # actually runs.
    od_context = None
    if pipeline_type in ("prototype", "od_prototype", "od_ppt", "ppt"):
        od_context = {
            "template_body": "## Workflow\nUse .card and .grid classes. Build pages into <section data-page>.",
            "template_id": "web-prototype",
            "ds_id": "default",
            "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}",
            "craft_block": "Keep markup semantic; wire every nav link.",
            "is_design_system_required": True,
        }

    kwargs: dict[str, Any] = dict(
        agents=list(specs),
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=run_id,
        pipeline_type=pipeline_type,
        user_id="harness-user",
        od_context=od_context,
        gate_agent_ids=[],  # suppress all gates
    )

    try:
        async for ev in engine.execute(**kwargs):
            events.append(ev)
    finally:
        # Restore the factory/engine globals so repeated _drive() calls in one
        # process (parametrized pytest) never accumulate patches.
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
    return events
