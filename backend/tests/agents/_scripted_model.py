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
  * ``compile_for_run`` wrapped to set the compiled ``clarify.mode`` to "off" — the
    auto-clarify override needs live WS round-trips (replaces the old ALWAYS_CLARIFY=False
    monkeypatch; the flag was deleted in 07-05 and the behavior is manifest-sourced now).
  * ``ArtifactStore.store`` → async no-op (avoids DB coupling; deterministic).
  * ``_run_review_gate`` → no-op async-gen (the inter-agent gate is engine-level;
    suppressing it keeps the agent-streaming capture non-blocking).
  * ``RUNS_ROOT`` → a fresh temp dir (the real default ``/app/runs`` is absent
    locally); the per-run sandbox lands there so disk deliverables work.
"""

from __future__ import annotations

import contextlib
import copy
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
_RUNS_ROOT = os.environ.get("PARITY_RUNS_ROOT") or tempfile.mkdtemp(
    prefix="harness-runs-"
)
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


class ScriptedThrottleError(Exception):
    """Synthetic transient throttle raised by ``ScriptedFakeChatModel`` (06-05).

    Shaped so ``agents.model_policy._is_transient_throttle`` classifies it ``True``
    via the botocore-``ClientError`` layer: it carries a ``response`` dict whose
    ``Error.Code`` is ``ThrottlingException`` and whose HTTP status is 429 — exactly
    the prod Bedrock throttle the engine's APPROACH-B retry loop reacts to. No live
    Bedrock / no botocore import: the predicate matches on the duck-typed shape.
    """

    def __init__(self, message: str = "Rate exceeded (synthetic throttle)") -> None:
        super().__init__(message)
        self.response = {
            "Error": {"Code": "ThrottlingException", "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": 429},
        }


class ScriptedNonTransientError(Exception):
    """Synthetic NON-transient error (a ``ValidationException`` analogue, 06-05).

    Shaped so ``_is_transient_throttle`` classifies it ``False`` (bad-params / auth
    class): the engine must NOT switch models — it propagates immediately. The
    ``response`` code is ``ValidationException`` and the status 400; neither is in
    the transient sets, and the type name / message carry no transient substring.
    """

    def __init__(
        self, message: str = "Invalid request (synthetic non-transient)"
    ) -> None:
        super().__init__(message)
        self.response = {
            "Error": {"Code": "ValidationException", "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        }


class ScriptedFakeChatModel(BaseChatModel):
    """Minimal BaseChatModel that streams a different scripted turn per call.

    06-05 fallback extension: when ``raise_exc`` is set the model RAISES that
    exception from ``_stream``/``_generate`` instead of streaming — simulating a
    model that throttles (or hard-fails) on every invocation. The engine's
    APPROACH-B retry loop builds a fresh ``ScriptedFakeChatModel`` per chain id
    (via the patched ``create_runner``), so a per-instance ``raise_exc`` lets a
    test flag throttle-on-id-A while id-B streams normally — no live Bedrock.
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        turns: list[_ScriptedTurn],
        *,
        raise_exc: BaseException | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_turns", list(turns))
        object.__setattr__(self, "_call_index", 0)
        # When set, every model turn raises this exception instead of streaming
        # (the synthetic throttle / non-transient error for the fallback tests).
        object.__setattr__(self, "_raise_exc", raise_exc)

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
        # 06-05: a flagged instance raises pre-first-token (the common Bedrock
        # throttle case) so the engine's retry loop restarts cleanly on the next
        # chain id. Raised here AND in _generate so both stream / invoke paths fail.
        if self._raise_exc is not None:
            raise self._raise_exc
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
                        tool_call_chunk(
                            name=name, args=json_args, id=call_id, index=tidx
                        )
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
        if self._raise_exc is not None:
            raise self._raise_exc
        chunks = list(
            self._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        )
        text = "".join(
            c.message.content for c in chunks if isinstance(c.message.content, str)
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


# ===========================================================================
# Fan-out worker scripted-model helper (Phase 11 / FANOUT-04).
# ===========================================================================


def worker_model(
    text: str = "worker output", usage: tuple[int, int] = (10, 5)
) -> "ScriptedFakeChatModel":
    """A minimal single-turn scripted model for a fan-out WORKER (no tool calls).

    Each fan-out child runs ONE agent invocation that streams text + usage and calls
    no tools (workers carry no gates / no per-worker fix-loop — D-01). The kernel
    ``run_fanout`` spawn path runs each worker against its own ``thread_id``; this
    helper supplies a deterministic per-worker model so a parallel/sequential fan-out
    test can assert N children + the concurrency cap offline (no Bedrock).
    """
    return ScriptedFakeChatModel([_ScriptedTurn(texts=[text], usage=usage)])


# ===========================================================================
# Per-agent script registry — keyed by agent id, returns the scripted turns
# for THAT agent in the LIVE (create_runner) world. The engine builds one agent
# per spec and runs it once (the build agent runs once per task), so each
# agent's model consumes its own turns.
# ===========================================================================


PART_ONE = '<section class="screen" id="screen-one"><h1>Screen One</h1></section>\n'
PART_TWO = '<section class="screen" id="screen-two"><h1>Screen Two</h1></section>\n'


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
        return [
            _ScriptedTurn(
                texts=[f"{agent_id} output line one. ", "line two."], usage=(12, 7)
            )
        ]

    # ── od_ppt / ppt agents (tools=[], text-only). ───────────────────────────
    # The three deck agents (ppt-brief-analyst / ppt-composer /
    # ppt-validator) are text-only (no filesystem tools), so the deck is a
    # streamed-text deliverable — NOT a file on disk. _resolve_final_output's
    # text/PPT branch takes the LAST agent's streamed output as the deliverable
    # (the validator here), unwrapping a single <artifact>…</artifact> wrapper.
    # So the deck the characterization test snapshots is whatever the VALIDATOR
    # streams. Keep each turn's text + usage FIXED for determinism.
    #
    # ppt-brief-analyst declares injects=['template'] and ppt-composer
    # declares injects=['template','design_system']; _drive seeds an od_context
    # for od_ppt/ppt (below) so _compose_injection does not raise
    # TemplateMissingError. (D-02 / PATTERNS S2.)
    if agent_id == "ppt-brief-analyst":
        return [
            _ScriptedTurn(
                texts=[
                    "## Slide Plan\n",
                    "1. Title slide. 2. Problem. 3. Solution. 4. Closing.\n",
                ],
                usage=(18, 12),
            )
        ]
    if agent_id == "ppt-composer":
        # The composer narrates building the deck; its text is consumed by the
        # validator (last agent), whose output is the actual deliverable.
        return [
            _ScriptedTurn(
                texts=["Composing the 4-slide deck per the strategist plan."],
                usage=(40, 30),
            )
        ]
    if agent_id == "ppt-validator":
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
                texts=[
                    f"Validation passed. No P0 issues.\n<artifact>{deck}</artifact>"
                ],
                usage=(22, 14),
            )
        ]

    # ── Phase-14 revision agent: deterministic turns for the run_revision
    # dispatch tests (ppt_revision is the manifest the FE run_revision frame
    # dispatches through execute()).
    # ISS-727/ISS-723: this agent used to stream the deck wrapped in a single
    # <artifact> tag, which is why the sandbox-root presentation.html every
    # `ref=vN` git tag captures was never rewritten after v1. Its manifest now
    # declares `strategy: single_file, name: presentation.html` plus a step-level
    # `tools: {read_files: true, write_files: true}` grant, and its prompt tells
    # it to edit that file in place — so the script writes the file, the same
    # shape as prototype-build below. `write_file` (not `edit_file`): this
    # harness runs on a FRESH sandbox with no deck on disk, whereas a real
    # revision edits the family sandbox's existing presentation.html.
    # The REVISED deck stays byte-distinct from the ppt-validator parent deck so
    # readback + lineage assertions can tell them apart.
    if agent_id == "ppt-revision-agent":
        revised = (
            "<!doctype html><html><head><title>Revised Deck</title></head>"
            "<body>"
            "<section class='deck-slide'>Revised Title</section>"
            "<section class='deck-slide'>Problem</section>"
            "<section class='deck-slide'>Solution</section>"
            "<section class='deck-slide'>Call To Action</section>"
            "</body></html>"
        )
        return [
            _ScriptedTurn(
                texts=["Revised per instruction."],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps(
                            {"file_path": "presentation.html", "content": revised}
                        ),
                        "c_rev_wf",
                    ),
                ],
                usage=(24, 16),
            ),
            _ScriptedTurn(texts=["Revised per instruction."], usage=(10, 5)),
        ]
    # (The legacy 2-agent ppt_revision pipeline — ppt-revision-agent +
    # ppt-revision-assembler, pre-collapse — is archived; agents/prompts/
    # .archive/ppt-revision-{agent,assembler}/. Those ids are no longer
    # scanned/dispatchable, so their scripted branches were removed.)

    # ── prototype-build (tools=prototype_emit_only): runs once per task. ──────
    # NEW world: write_file(file_path="prototype.html", content=…) +
    #            report_task_complete(task_number/task_title/summary).
    if agent_id == "prototype-build":
        html = "<!doctype html><html><body><section data-page='dashboard'>hi</section></body></html>"
        return [
            _ScriptedTurn(
                texts=["Building the page. "],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps({"file_path": "prototype.html", "content": html}),
                        "c_wf",
                    ),
                    (
                        "report_task_complete",
                        _j.dumps(
                            {
                                "task_number": 1,
                                "task_title": "Build shell",
                                "summary": "did it",
                            }
                        ),
                        "c_rtc",
                    ),
                ],
                usage=(50, 20),
            ),
            _ScriptedTurn(texts=["Done."], usage=(10, 5)),
        ]

    # ── prototype-analyze (tools=[], text-only): the Spec Kit Analyzer runs at
    # order 3 (specify → plan → ANALYZE → build → validate). It is READ-ONLY and
    # TERMINAL — nothing consumes prototype-analyze and the prototype deliverable
    # is read from the on-disk prototype.html, so this turn's text never touches
    # the built artifact. Mirror the prototype-plan special-case (a faithful
    # <analysis> report rather than the generic "output line one" stub) so the
    # golden captures a realistic analyze stream. The text obeys the AGENT.md
    # ABSOLUTE OUTPUT CONTRACT: first chars are <analysis>, ends with </analysis>,
    # includes the report heading + a couple of finding lines + a
    # "### Readiness verdict\nREADY TO BUILD" line. Fixed usage keeps token
    # normalization deterministic; the exact bytes become the pinned output_length.
    if agent_id == "prototype-analyze":
        return [
            _ScriptedTurn(
                texts=[
                    "<analysis>\n"
                    "## Spec Kit Analysis Report\n\n"
                    "### Summary\n"
                    "The spec and task list are consistent and buildable; "
                    "coverage is complete with no blocking gaps.\n\n"
                    "### Findings\n"
                    "| # | Category | Status | Detail |\n"
                    "|---|----------|--------|--------|\n"
                    "| 1 | Consistency | ✅ Clear | Tasks implement every spec page. |\n"
                    "| 2 | Coverage gaps | ✅ Clear | All requirements mapped to a task. |\n\n"
                    "### Issues requiring attention\n"
                    "No blocking issues found.\n\n"
                    "### Readiness verdict\n"
                    "READY TO BUILD\n"
                    "The artifacts are aligned; proceed to implementation.\n"
                    "</analysis>"
                ],
                usage=(28, 16),
            )
        ]

    # ── prototype-validate (tools=prototype_emit_only): text-only run is fine —
    # it may call no tools (validation pass). Keep it pure text so the prototype
    # pipeline terminates deterministically.
    if agent_id == "prototype-validate":
        return [
            _ScriptedTurn(texts=["Validation passed. No P0 issues."], usage=(20, 10))
        ]

    # ── prototype-revision-analyzer (tools=[], text-only): outputs a ## Solution Plan
    # section so the engine's produces_solution_plan hook can extract it and store it
    # on ectx.analyzer_solution. This is step 0 of prototype_revision,
    # prototype_large_revision, and prototype_feature_revision. The text must contain
    # a ## Solution Plan heading so parse_analyzer_output returns a non-empty string
    # (the downstream _compose_context_message then injects === REVISION ANALYSIS ===
    # into step 1's context). Fixed usage keeps token normalisation deterministic.
    if agent_id == "prototype-revision-analyzer":
        return [
            _ScriptedTurn(
                texts=[
                    "## Solution Plan\n"
                    "Update the `<header id='page-header'>` element to display the revised title. "
                    "No route, function, or style changes are required."
                ],
                usage=(20, 12),
            )
        ]

    # ── prototype-revision-planner (tools=workspace): reads prototype.html then
    # writes tasks.md and streams a <tasks> block. The task_loop step reads the
    # streamed text via latest_typed_content("prototype-revision-planner"). The
    # heading_tasks parser extracts ## Task N: headers from the streamed text.
    if agent_id == "prototype-revision-planner":
        tasks_content = (
            "<tasks>\n"
            "## Task 1: Update the page header\n"
            "Update `<header id='page-header'>` to display the revised title text "
            "as instructed in the solution plan.\n\n"
            "## Task 2: Verify navigation links\n"
            "Check that all nav links in `<nav id='main-nav'>` resolve correctly "
            "after the header update.\n"
            "</tasks>"
        )
        return [
            _ScriptedTurn(
                texts=[tasks_content],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps({"file_path": "tasks.md", "content": tasks_content}),
                        "c_tasks",
                    ),
                ],
                usage=(50, 25),
            ),
            _ScriptedTurn(texts=["Task plan written."], usage=(8, 4)),
        ]

    # ── prototype-revision-validate (tools=workspace): reads prototype.html then
    # emits a validation summary. Text-only — no file edits in the scripted harness
    # (the golden just needs to see the agent fire; real edits happen on live Bedrock).
    if agent_id == "prototype-revision-validate":
        return [
            _ScriptedTurn(
                texts=["Validated — 1 page checked, no issues found."], usage=(20, 10)
            )
        ]

    # ── prototype-revision-feature-specify (tools=workspace, strategy=single_shot):
    # writes a feature spec file. Uses write_file so the spec is available to the
    # task_loop build step via runner.latest_typed_content("prototype-revision-feature-specify").
    if agent_id == "prototype-revision-feature-specify":
        spec_content = (
            "## Feature Specification: Task Detail Panel\n\n"
            "### Overview\n"
            "Extend the dashboard with an inline task-detail panel.\n\n"
            "### Requirements\n"
            "1. Each task row in `#task-list` must be expandable on click.\n"
            "2. The expanded panel must show description and due-date.\n"
            "3. Toggle state must be managed via `data-task-id` attributes.\n"
        )
        return [
            _ScriptedTurn(
                texts=["Writing feature specification. "],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps(
                            {"file_path": "feature-spec.md", "content": spec_content}
                        ),
                        "c_fs",
                    ),
                ],
                usage=(28, 14),
            ),
            _ScriptedTurn(texts=["Feature specification complete."], usage=(8, 4)),
        ]

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
                    tool_calls=[
                        mk(
                            "prototype.html",
                            "<!doctype html><html><body>revised</body></html>",
                        )
                    ],
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

    # ── plan-lead (pdf_to_prototype Planner: tools=workspace): writes build/tasks.json
    # and returns the same JSON in a fenced block. The wave_scheduler's
    # parse_preferring_target needs both the file (for normal flow) and the fence
    # (for resume replays). Fixed usage keeps token normalization deterministic.
    if agent_id == "custom-agent:plan-lead":
        tasks_obj = {
            "tasks": [
                {
                    "id": "1",
                    "title": "Screen 1: Dashboard",
                    "targets": ["screens/1.html"],
                    "depends_on": [],
                    "body": 'Build the screen "Screen 1: Dashboard" (page id 1).',
                },
                {
                    "id": "2",
                    "title": "Screen 2: Details",
                    "targets": ["screens/2.html"],
                    "depends_on": [],
                    "body": 'Build the screen "Screen 2: Details" (page id 2).',
                },
            ]
        }
        tasks_json = _j.dumps(tasks_obj, indent=2)
        return [
            _ScriptedTurn(
                texts=["Task list created.\n\n```json\n" + tasks_json + "\n```"],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps(
                            {"file_path": "build/tasks.json", "content": tasks_json}
                        ),
                        "c_tasks",
                    ),
                ],
                usage=(80, 50),
            ),
            _ScriptedTurn(texts=["Tasks written."], usage=(10, 5)),
        ]

    # ── fi-planner (prototype_v2 Reading Planner): writes build/tasks.json, one
    # reader task per attached document plus the rollup. Same dual output as
    # plan-lead above — the file for normal flow, the fence for resume replays.
    if agent_id == "custom-agent:fi-planner":
        tasks_obj = {
            "tasks": [
                {
                    "id": "doc-a-s01",
                    "title": "Read doc-a pages 1-2",
                    "targets": ["file-synthesis/doc-a/shards/doc-a-s01/notes.md"],
                    "depends_on": [],
                    "body": "Read .uploads/doc-a.pdf pages 1-2 and write the shard.",
                },
                {
                    "id": "doc-a-rollup",
                    "title": "Roll up doc-a",
                    "targets": ["file-synthesis/doc-a/synthesis.md"],
                    "depends_on": ["doc-a-s01"],
                    "body": "Combine the doc-a shards into one document synthesis.",
                },
            ]
        }
        tasks_json = _j.dumps(tasks_obj, indent=2)
        return [
            _ScriptedTurn(
                texts=["Reading plan created.\n\n```json\n" + tasks_json + "\n```"],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps(
                            {"file_path": "build/tasks.json", "content": tasks_json}
                        ),
                        "c_fi_tasks",
                    ),
                ],
                usage=(80, 50),
            ),
            _ScriptedTurn(texts=["Reading plan written."], usage=(10, 5)),
        ]

    # ── pb-design (prototype_v2 Architect): writes build/screens.json, the
    # inventory the `screen_plan` parser expands into one builder task per screen.
    # `spec.md` is an enrichment the parser tolerates missing, so it is not faked.
    if agent_id == "custom-agent:pb-design":
        screens_obj = {
            "title": "Scripted Prototype",
            "entry": "screen-one",
            "screens": [
                {
                    "id": "screen-one",
                    "title": "Screen One",
                    "kind": "page",
                    "nav": "Flow A",
                    "reqs": ["REQ-001"],
                    "summary": "The first screen.",
                    "transitions": [{"label": "Go to two", "to": "screen-two"}],
                },
                {
                    "id": "screen-two",
                    "title": "Screen Two",
                    "kind": "page",
                    "nav": "Flow A",
                    "reqs": ["REQ-002"],
                    "summary": "The second screen.",
                    "transitions": [],
                },
            ],
            "unresolved": [],
        }
        screens_json = _j.dumps(screens_obj, indent=2)
        return [
            _ScriptedTurn(
                texts=[
                    "Screen inventory created.\n\n```json\n" + screens_json + "\n```"
                ],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps(
                            {"file_path": "build/screens.json", "content": screens_json}
                        ),
                        "c_screens",
                    ),
                ],
                usage=(80, 50),
            ),
            _ScriptedTurn(texts=["Inventory written."], usage=(10, 5)),
        ]

    # ── pb-build (prototype_v2 Builders): the wave runs one worker per screen,
    # but `_scripts_for` is keyed on agent_id ALONE and never sees the task body,
    # so a worker cannot know which screen it owns. Each writes BOTH parts with
    # identical bytes — enough for `pb-assemble` to have real parts to assemble,
    # which is what lets pb-validate and pb-present run at all.
    if agent_id == "custom-agent:pb-build":
        parts = {
            "parts/screen-one.html": PART_ONE,
            "parts/screen-two.html": PART_TWO,
        }
        return [
            _ScriptedTurn(
                texts=["Parts written."],
                tool_calls=[
                    (
                        "write_file",
                        _j.dumps({"file_path": path, "content": body}),
                        f"c_part_{i}",
                    )
                    for i, (path, body) in enumerate(parts.items())
                ],
                usage=(60, 30),
            ),
            _ScriptedTurn(texts=["Done."], usage=(10, 5)),
        ]

    # Fallback — a generic text turn (unknown agent).
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


# ===========================================================================
# Engine driver (LIVE create_runner path only).
# ===========================================================================


def offline_session_local(*_a, **_k):
    """``SessionLocal`` stand-in that fails with the DB error the engine contracts on.

    THE single definition of this harness's typed-substrate DB seam. The engine
    persists per-run workspace / run_capabilities / artifact_refs / run_events rows
    through ``ScopedStore``, which opens ``app.models.database.SessionLocal()`` when
    no session is injected. An offline harness has no ``workflow_runs`` row — and
    under ``tests/unit`` no database at all — so those writes must DEGRADE.

    ``engine.py`` degrades them ONLY for ``SQLAlchemyError``; anything else is
    re-raised as a real bug (WR-02). That is deliberate, and it is why simply letting
    the ``tests/unit`` isolation guard fire is not enough: it raises
    ``UnitIsolationError`` (not a ``SQLAlchemyError``), which the engine correctly
    refuses to swallow, so the whole run dies instead of degrading. Raising
    ``OperationalError`` here hits the contracted degrade path WITHOUT touching a
    socket, keeping the run hermetic and the event stream byte-identical.
    """
    from sqlalchemy.exc import OperationalError

    raise OperationalError(
        "offline scripted harness: no database", None, Exception("offline harness")
    )


@contextlib.contextmanager
def offline_db_seam() -> Iterator[None]:
    """Scope :func:`offline_session_local` over a block, restoring on exit.

    For harnesses that drive ``ExecutionEngine.execute()`` WITHOUT going through
    :func:`_prepare_engine_run` (which installs the same seam itself) — notably unit tests that
    hand-roll the engine wiring to capture one seam. Without this, the engine's
    best-effort persistence reaches the ``tests/unit`` DB guard and the run aborts
    instead of degrading.
    """
    import app.models.database as _db_mod

    _orig_session_local = _db_mod.SessionLocal
    _db_mod.SessionLocal = offline_session_local
    try:
        yield
    finally:
        _db_mod.SessionLocal = _orig_session_local


def _prepare_engine_run(
    pipeline_type: str,
    world: str = "new",
    *,
    offline_db: bool = True,
    **execute_kwargs,
):
    """Build a scripted, offline ``ExecutionEngine`` run and return the RAW
    (unconsumed) ``execute()`` async generator plus a ``restore`` callback.

    Extracted out of ``_drive`` (below) — ``_drive`` is now a thin wrapper
    that drains this generator to completion. A caller that needs to
    suspend a run mid-flight (break out of one ``async for`` pull on this
    generator, do other work, then resume pulling from the SAME generator)
    gets a genuine coroutine suspension at ``execute()``'s internal ``yield``
    — no thread/event trickery needed. The caller owns calling ``restore()``
    exactly once, after the generator is fully drained or abandoned; it
    undoes the module-level monkeypatches (``factory_mod.create_runner`` /
    ``engine_mod.create_runner`` / ``engine_mod.compile_for_run``) installed
    below.

    ``offline_db`` (default ``True``) forces the typed-substrate DB seam to the
    deterministic "no database" failure described at its patch site below, which is
    what every characterization/offline caller wants: zero persistence, zero
    sockets, byte-identical event streams.

    Pass ``offline_db=False`` when the CALLER has already wired a real, working
    ``app.models.database.SessionLocal`` (e.g. an in-memory SQLite fixture) and the
    assertion under test depends on the run path persisting ORGANICALLY — an FR-014
    revision chain, for instance, can only resolve artifacts the parent run actually
    wrote. Forcing the seam off in that case would silently drop every write and the
    later cross-run read would resolve ∅.
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
    # We replicate exactly that. ``ppt``'s deck agents now declare
    # ``pipeline_type: ppt`` directly (the former od_ppt/ppt alias is closed —
    # see agents/registry.py), so no lookup remap is needed for it anymore.
    # The od_prototype alias is closed too now (registry._OD_ALIAS_BASE is empty),
    # so no lookup remap is needed for any label — the run type IS the manifest id.
    _lookup_type = pipeline_type

    # ── Force RUNS_ROOT to our temp dir at RUNTIME ────────────────────────────
    # The env var is set at import, but ``app.core.config.settings`` may have been
    # loaded earlier (e.g. by another test / conftest) with the default ``/app/runs``
    # (read-only here). RunSandbox reads ``settings.RUNS_ROOT`` in __init__, so we
    # override the live attribute so the per-run sandbox lands in the temp dir.
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    # ── Disable the auto-clarify gate (the clarifier needs live WS round-trips). ─
    # The former module-level ALWAYS_CLARIFY flag was deleted in 07-05; the "force
    # CLARIFY_REQUIRED on every run" behavior is now declared per-workflow by the
    # manifest ``clarify.mode`` ("auto"), read off the CompiledWorkflow at run entry.
    # The offline harness has no live WS round-trip, so we wrap ``compile_for_run`` to
    # flip the compiled clarify.mode to "off" — disabling the auto-clarify override
    # exactly as setting ALWAYS_CLARIFY=False used to (the planner still runs; only the
    # PROCEED→CLARIFY_REQUIRED forcing is suppressed). Restored in finally.
    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
        # DEEP-COPY before mutating: engine.compile_for_run is @lru_cache'd, so it
        # returns a SHARED CompiledWorkflow — mutating it in place would corrupt the
        # cache for every later caller in the same pytest process (e.g. the compiler
        # assertion in test_nav_coverage). Copy first, mutate the copy, leave the cached
        # original pristine. (This also fixes the latent same-cache leak the pre-existing
        # ``clarify.mode = 'off'`` write already had.)
        compiled = copy.deepcopy(_orig(pipeline_type))
        compiled.clarify.mode = "off"
        # quick-260701-erg: pin every compiled step's require_render=False for golden
        # runs. The goldens are byte/event snapshots RECORDED at require_render=False
        # semantics; the production manifests now flip require_render:true (prototype
        # build + prototype_revision), so a browserless golden run would otherwise flip a
        # step to skipped_blocked and diverge. Pinning False makes the 5 goldens knob-
        # AND Chromium-independent (INV-3 defense-in-depth) — NOT a coverage hole: the
        # require_render=true production behavior is covered by test_nav_coverage
        # scenarios 4a/4b, and (with Chromium present) true/false are both status "ok",
        # so the pin masks nothing real. Restored via compile_for_run in finally.
        for s in getattr(compiled, "steps", []) or []:
            if hasattr(s, "require_render"):
                s.require_render = False
        return compiled

    engine_mod.compile_for_run = _patched_compile_for_run

    # ── Typed-substrate DB seam → deterministic "no database" (offline harness) ────
    # See :func:`offline_session_local` for WHY this seam must raise a SQLAlchemyError.
    # Restored in finally.
    import app.models.database as _db_mod

    _orig_session_local = _db_mod.SessionLocal

    # Opt-out (``offline_db=False``): the caller supplied a working SessionLocal and
    # NEEDS the run path to persist — see the parameter's docstring.
    if offline_db:
        _db_mod.SessionLocal = offline_session_local

    # ── Agent list: let the engine build from compiled manifest steps ──────────
    # Pass agents=[] so the engine's ``if compiled.steps and not agents`` branch
    # fires and calls ``_specs_from_plan(compiled.steps)``. This ensures revision
    # pipelines include ``prototype-revision-analyzer`` as step 0 (declared in the
    # manifest but not registered in PIPELINE_AGENTS because its AGENT.md carries
    # pipeline_type: prototype_revision_analyzer). The registry-based list via
    # ``get_pipeline_agents`` is still available for callers that need it, but the
    # harness defers to the manifest — the single source of truth for agent ordering.
    # NOTE: ``get_pipeline_agents`` is still imported above for call-site compat
    # (other tests may import it directly from this module).
    _ = get_pipeline_agents  # keep the import referenced (linter guard)

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
    async def _fake_run_planner(
        user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs
    ):
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

    # ── Build the run kwargs. ──────────────────────────────────────────────────
    # The state machine is a process-wide singleton keyed on run_id, so each call
    # needs a UNIQUE run_id (a reused id is "already completed" → StateMachineError).
    import uuid as _uuid

    run_id = f"harness-{pipeline_type}-{_uuid.uuid4().hex[:8]}"

    # Prototype agents declare injects=['template', 'design_system', ...]; the
    # factory raises TemplateMissingError without a template body. Supply a
    # minimal od_context so injection succeeds and the build/task_progress path
    # actually runs.
    od_context = None
    if pipeline_type in ("prototype", "ppt"):
        od_context = {
            "template_body": "## Workflow\nUse .card and .grid classes. Build pages into <section data-page>.",
            "template_id": "web-prototype",
            "ds_id": "default",
            "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}",
            "craft_block": "Keep markup semantic; wire every nav link.",
            "is_design_system_required": True,
        }

    kwargs: dict[str, Any] = dict(
        agents=[],  # engine builds from compiled manifest steps via _specs_from_plan
        user_message="Build me a thing for managing tasks.",
        pipeline_run_id=run_id,
        pipeline_type=pipeline_type,
        user_id="harness-user",
        od_context=od_context,
        gate_agent_ids=[],  # suppress all gates
    )
    # Optional passthrough (43-05): a caller may inject extra execute() kwargs — e.g. the
    # live-ectx register/unregister callback pair — to exercise engine seams end-to-end.
    kwargs.update(execute_kwargs)

    def _restore() -> None:
        # Restore the factory/engine globals so repeated runs in one process
        # (parametrized pytest) never accumulate patches.
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.compile_for_run = _orig_compile_for_run
        # Restore ONLY what we patched: under ``offline_db=False`` the caller owns
        # SessionLocal, so writing to it here could clobber their fixture.
        if offline_db:
            _db_mod.SessionLocal = _orig_session_local

    return engine.execute(**kwargs), _restore


async def _drive(
    pipeline_type: str,
    world: str = "new",
    *,
    offline_db: bool = True,
    **execute_kwargs,
) -> list[dict]:
    """Run ``ExecutionEngine.execute()`` end-to-end offline and return the
    ordered list of yielded engine event dicts.

    Only the LIVE (``create_runner``) world is supported — the pre-cutover
    ``create_agent`` path was deleted in Phase 7a. ``world`` is retained for
    call-site compatibility; any value other than ``"new"`` is rejected.
    """
    agen, restore = _prepare_engine_run(
        pipeline_type, world=world, offline_db=offline_db, **execute_kwargs
    )
    events: list[dict] = []
    try:
        async for ev in agen:
            events.append(ev)
    finally:
        restore()
    return events
