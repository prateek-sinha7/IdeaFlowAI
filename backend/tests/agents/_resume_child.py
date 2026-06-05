"""tests/agents/_resume_child.py — subprocess entry point for the Phase-8
cross-process resume-after-kill proof (``test_phase8_resume.py``).

This is a standalone, ``python3.11``-runnable script (NOT a pytest module) that
the Phase-8 resume test spawns as TWO independent OS processes to prove the
Postgres checkpointer survives a real process boundary — the one durability
guarantee ``InMemorySaver`` cannot provide.

Why a separate process (not an in-process fixture): a true crash-recovery proof
must cross a real process boundary, so the second process CANNOT share any
in-memory object (graph, checkpointer pool, interrupt state) with the first. The
only thing carried across is the durable Postgres row, addressed by a stable
``thread_id``. (An in-memory ``InMemorySaver`` lives in the producer's heap, so a
fresh process starts with an empty saver — which is exactly the negative contrast
the test asserts.)

Which gate this exercises (the critical design fact, from the T1 survey):
  There are TWO HITL mechanisms in this system and only ONE is checkpoint-durable.
    * The engine's inter-agent "review gate" (``review_gate_ready``) is NOT a
      LangGraph interrupt — the engine pauses by awaiting an in-memory
      ``asyncio.Event`` (``ArtifactStore.get_review_event``). That is in-process
      only and CANNOT survive a kill, so it is deliberately NOT used here.
    * The **runner tool-level gate** (``DeepAgentRunner`` built with
      ``interrupt_on=[...]``) IS a real LangGraph interrupt whose state the
      checkpointer persists. THIS is what a Postgres checkpointer makes durable
      across processes, so this script drives exactly that mechanism.

Faithfulness to production:
  * Uses the PRODUCTION checkpointer factory ``app.agents.checkpointer.get_checkpointer``
    verbatim — when ``DATABASE_URL`` is Postgres it returns the real
    ``AsyncPostgresSaver`` over a ``psycopg_pool.AsyncConnectionPool`` and runs
    ``.setup()``; when it is sqlite/anything-else it returns ``InMemorySaver``.
    The child changes NO production code (verify-only).
  * Builds the runner via the supported factory entry point
    ``agents.factory.create_runner(agent_id, ctx, checkpointer=…, interrupt_on=…,
    thread_id=…)`` — the same call the engine makes — using a tiny throwaway
    agent spec written into a temp prompts dir, with a SCRIPTED model injected as
    ``ctx.model`` (zero Bedrock cost, fully deterministic). This proves the
    *production wiring* (factory → ``DeepAgentRunner`` → graph → checkpointer),
    not just a hand-built runner.

Phases (selected by ``--phase``):
  * ``run-until-interrupt`` — build the runner, drive it with the scripted model
    until the gated tool call fires the interrupt and the pause is persisted to
    the checkpointer, print ``INTERRUPTED <thread_id>`` and exit 0. (This is the
    point just before a kill; the parent may ALSO hard-kill the process here to
    simulate a crash — the persisted checkpoint must already be durable.)
  * ``resume`` — a FRESH process: reconstruct the runner with the SAME
    ``thread_id`` + the same (Postgres) checkpointer, issue
    ``Command(resume={"decisions":[{"type":"approve"}]})``, run to a terminal
    state, and assert the gated tool actually executed (its ``ToolMessage`` is in
    the final state). On success print ``RESUMED_COMPLETE <thread_id>`` and exit
    0; if the checkpoint was not durable (no pause is visible / resume is a no-op)
    print ``RESUME_FAILED <reason>`` and exit 3.

Machine-readable stdout markers (the test greps for these):
  * ``CHECKPOINTER <ClassName>``     — which saver the production factory chose.
  * ``INTERRUPTED <thread_id>``      — run-until-interrupt persisted the pause.
  * ``PRE_RESUME_STATE next=… interrupts=…`` — what the fresh process SEES.
  * ``RESUMED_COMPLETE <thread_id>`` — resume reached terminal + gated tool ran.
  * ``RESUME_FAILED <reason>``       — resume could not complete (negative path).
  * ``CHILD_ERROR <repr>``           — an unexpected exception (exit 2).

Usage (the test calls this; shown for reference)::

    DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:<port>/postgres \\
    ENV=development \\
        python3.11 tests/agents/_resume_child.py \\
            --phase run-until-interrupt --thread-id t-abc --run-id r-abc

``--kill-after-interrupt`` makes the run-until-interrupt phase HARD-KILL itself
(``SIGKILL``) the instant the gate fires — a self-inflicted crash with no chance
to flush/close the pool, the most adversarial durability test. (The test uses
the variant that lets the parent kill it; this flag exists so the child can also
prove self-kill durability and is covered by the test's primary path.)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

# ── Make the backend package root importable (tests/agents/_resume_child.py →
#    backend/). MUST happen before importing app.* / agents.*; this script is run
#    as a bare path from an arbitrary cwd, so the package root is not implicitly
#    on sys.path. ───────────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ── RUNS_ROOT must be a writable dir BEFORE app.core.config / sandbox import it
#    (the real default /app/runs is absent locally; create_runner builds a
#    RunSandbox under it). DATABASE_URL / ENV are supplied by the parent's env so
#    that the production ``settings`` singleton (and thus get_checkpointer's
#    provider choice) reads them on first import — we do NOT override them here. ──
os.environ.setdefault("RUNS_ROOT", tempfile.mkdtemp(prefix="resume-child-runs-"))
os.environ.setdefault("ENV", "development")

# The single gated tool's name — kept as one constant so the tool definition, the
# interrupt_on map, and the post-resume assertion all reference the same string (a
# typo would silently never gate). Matches the live HITL smoke's tool name.
GATED_TOOL = "report_task_complete"

# A throwaway agent id for the temp spec the child writes (so create_runner has a
# real spec to load). Deliberately not a real registered agent — we want a
# minimal, self-contained prototype-class agent (tools=[prototype_emit_only] →
# the factory binds report_task_complete + the native fs tools).
_AGENT_ID = "phase8-resume-probe"


def _scripted_turns() -> list:
    """Two scripted model turns driving the runner through one HITL gate.

    Turn 1 emits a little text and ONE call to the gated tool — that tool call is
    what arms ``HumanInTheLoopMiddleware`` and fires the interrupt (the run pauses
    BEFORE the tool node executes). Turn 2 is consumed only AFTER resume (it is the
    post-approval continuation), proving the resumed graph carried the conversation
    forward rather than restarting. Mirrors the Phase-3 cutover test's
    ``_hitl_script`` shape but lives here so the child is self-contained.
    """
    from tests.agents._scripted_model import _ScriptedTurn

    return [
        _ScriptedTurn(
            texts=["working "],
            tool_calls=[
                (
                    GATED_TOOL,
                    json.dumps(
                        {"task_number": 1, "task_title": "Shell", "summary": "x"}
                    ),
                    "call_1",
                )
            ],
            usage=(11, 7),
        ),
        _ScriptedTurn(texts=["all done"], usage=(13, 5)),
    ]


def _write_probe_spec(prompts_dir: Path) -> None:
    """Write a minimal AGENT.md for the throwaway probe agent into ``prompts_dir``.

    ``tools: [prototype_emit_only]`` makes ``_build_runner_tools`` bind the
    store-free ``report_task_complete`` custom tool (the gated tool) plus the
    native deepagents filesystem tools — exactly the production tool wiring for a
    prototype-class agent. ``pipeline_type: prototype`` is a valid supported type;
    ``order``/``max_tokens`` satisfy the loader's schema validation.
    """
    agent_dir = prompts_dir / _AGENT_ID
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        f"id: {_AGENT_ID}\n"
        "name: Phase8 Resume Probe\n"
        "role: Cross-process resume probe\n"
        "pipeline_type: prototype\n"
        "order: 99\n"
        "max_tokens: 4000\n"
        "tools:\n"
        "  - prototype_emit_only\n"
        "guardrails: []\n"
        "context_from: []\n"
        'icon: "🧪"\n'
        "estimated_duration: 1.0\n"
        "---\n\n"
        "You are a probe agent. Call report_task_complete when done.\n",
        encoding="utf-8",
    )


async def _build_runner(checkpointer, thread_id: str, run_id: str):
    """Build the production runner via ``create_runner`` with a scripted model.

    Points the loader at a temp prompts dir holding the throwaway probe spec, then
    calls the SAME ``agents.factory.create_runner`` the engine uses — passing the
    production ``checkpointer``, ``interrupt_on={GATED_TOOL: True}`` and the stable
    ``thread_id``. The scripted model is injected as ``ctx.model`` (used verbatim
    by the runner), so no Bedrock call is ever made.
    """
    import agents.loader as loader_mod
    from agents.factory import AgentContext, create_runner
    from tests.agents._scripted_model import ScriptedFakeChatModel

    # Redirect the loader to a temp prompts dir with our self-contained spec. The
    # loader caches specs; clear the cache so our temp spec is picked up. (This is
    # a fresh process, so there is no other test relying on the cache state.)
    prompts_dir = Path(tempfile.mkdtemp(prefix="resume-child-prompts-")) / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    _write_probe_spec(prompts_dir)
    loader_mod._PROMPTS_DIR = prompts_dir
    loader_mod._SPEC_CACHE.clear()

    ctx = AgentContext(
        user_request="probe",
        user_id="phase8",
        run_id=run_id,
        model=ScriptedFakeChatModel(_scripted_turns()),
    )
    return create_runner(
        _AGENT_ID,
        ctx,
        checkpointer=checkpointer,
        interrupt_on={GATED_TOOL: True},
        thread_id=thread_id,
    )


async def _phase_run_until_interrupt(thread_id: str, run_id: str, kill_after: bool) -> int:
    """Drive the runner until the HITL interrupt persists; print INTERRUPTED.

    Returns the process exit code (0 on a clean stop at the interrupt). When
    ``kill_after`` is set, the process ``SIGKILL``s itself the instant the gate
    fires (a crash with no pool flush) instead of returning — the most adversarial
    durability case; the persisted checkpoint must already be on disk in Postgres.
    """
    from app.agents.checkpointer import close_checkpointer, get_checkpointer

    checkpointer = await get_checkpointer()
    print(f"CHECKPOINTER {type(checkpointer).__name__}", flush=True)

    runner = await _build_runner(checkpointer, thread_id, run_id)

    saw_gate = False
    saw_done = False
    async for ev in runner.astream_events("go"):
        etype = ev.get("type")
        if etype == "gate":
            saw_gate = True
            # The pause is now persisted to the checkpointer. Announce it BEFORE
            # any optional self-kill so the parent always sees the marker.
            print(f"INTERRUPTED {thread_id}", flush=True)
            if kill_after:
                # Hard crash: no checkpointer.close(), no pool flush, no graceful
                # teardown. If the resume still works, the write was durable.
                os.kill(os.getpid(), signal.SIGKILL)
            break
        if etype == "done":
            saw_done = True

    if not saw_gate:
        # The model failed to trigger the gate (should be impossible with the
        # scripted tool call) — surface it so the test fails loudly rather than the
        # resume phase silently finding nothing to resume.
        print(
            f"RESUME_FAILED run-until-interrupt-did-not-gate saw_done={saw_done}",
            flush=True,
        )
        await close_checkpointer()
        return 3

    # Clean stop at the interrupt (the parent may hard-kill us after seeing the
    # marker; if not, we close the pool tidily and exit 0). Closing here is the
    # "graceful producer" path — the resume phase is a different process either way.
    await close_checkpointer()
    return 0


async def _phase_resume(thread_id: str, run_id: str) -> int:
    """Fresh process: resume the persisted pause and prove the gated tool ran.

    Reconstructs the runner with the SAME ``thread_id`` + production checkpointer,
    inspects the persisted state (must show a pending pause if the checkpoint was
    durable), issues ``Command(resume=…)``, then asserts the run reached a terminal
    state AND the gated tool executed (its ``ToolMessage`` is in the final state).
    Prints ``RESUMED_COMPLETE`` on success (exit 0) or ``RESUME_FAILED`` on the
    negative path (exit 3) — the latter is what an InMemory saver produces because
    the checkpoint never crossed the process boundary.
    """
    from langchain_core.messages import ToolMessage
    from langgraph.types import Command

    from app.agents.checkpointer import close_checkpointer, get_checkpointer

    checkpointer = await get_checkpointer()
    print(f"CHECKPOINTER {type(checkpointer).__name__}", flush=True)

    runner = await _build_runner(checkpointer, thread_id, run_id)

    # What does THIS fresh process see for the thread? With a durable (Postgres)
    # checkpoint, ``next`` is the paused HITL node and interrupts are present. With
    # a fresh InMemory saver, the thread is unknown → next == () and no interrupts.
    pre = await runner._graph.aget_state(runner.config)
    pre_next = tuple(getattr(pre, "next", ()) or ())
    pre_interrupts = bool(getattr(pre, "interrupts", None))
    print(
        f"PRE_RESUME_STATE next={list(pre_next)} interrupts={pre_interrupts}",
        flush=True,
    )

    if not pre_next:
        # No pending pause is visible → the checkpoint did NOT persist across the
        # process boundary. This is the expected InMemory (negative) outcome.
        print("RESUME_FAILED no-persisted-pause-in-fresh-process", flush=True)
        await close_checkpointer()
        return 3

    # Resume: exactly one approve per pending action_request (the middleware
    # validates the count). Our pause is a single gated tool call → one approve.
    try:
        await runner._graph.ainvoke(
            Command(resume={"decisions": [{"type": "approve"}]}), runner.config
        )
    except Exception as exc:  # noqa: BLE001 — surface a resume-time failure cleanly
        print(f"RESUME_FAILED resume-raised:{type(exc).__name__}:{exc}", flush=True)
        await close_checkpointer()
        return 3

    final = await runner._graph.aget_state(runner.config)
    final_next = tuple(getattr(final, "next", ()) or ())
    msgs = final.values.get("messages", []) if getattr(final, "values", None) else []
    gated_msgs = [
        m
        for m in msgs
        if isinstance(m, ToolMessage) and getattr(m, "name", None) == GATED_TOOL
    ]

    if final_next != ():
        print(f"RESUME_FAILED non-terminal-after-resume next={list(final_next)}", flush=True)
        await close_checkpointer()
        return 3
    if not gated_msgs:
        print("RESUME_FAILED gated-tool-did-not-execute", flush=True)
        await close_checkpointer()
        return 3

    # Success: terminal state reached and the approved gated tool actually ran in
    # the resumed (fresh-process) graph. Echo the tool's result content as proof
    # the real tool body executed (not a synthetic respond/reject message).
    print(
        f"GATED_TOOL_RESULT {json.dumps(str(gated_msgs[-1].content))}",
        flush=True,
    )
    print(f"RESUMED_COMPLETE {thread_id}", flush=True)
    await close_checkpointer()
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description="Phase-8 cross-process resume child.")
    parser.add_argument(
        "--phase",
        required=True,
        choices=["run-until-interrupt", "resume"],
        help="run-until-interrupt: drive to the HITL gate and persist it. "
        "resume: fresh process, resume the persisted pause to completion.",
    )
    parser.add_argument("--thread-id", required=True, help="Stable LangGraph thread id.")
    parser.add_argument(
        "--run-id",
        required=True,
        help="Per-run id (roots the RunSandbox; not the checkpoint key).",
    )
    parser.add_argument(
        "--kill-after-interrupt",
        action="store_true",
        help="run-until-interrupt only: SIGKILL self the instant the gate fires.",
    )
    args = parser.parse_args()

    try:
        if args.phase == "run-until-interrupt":
            return asyncio.run(
                _phase_run_until_interrupt(
                    args.thread_id, args.run_id, args.kill_after_interrupt
                )
            )
        return asyncio.run(_phase_resume(args.thread_id, args.run_id))
    except Exception as exc:  # noqa: BLE001 — any unexpected failure → marker + exit 2
        import traceback

        print(f"CHILD_ERROR {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
