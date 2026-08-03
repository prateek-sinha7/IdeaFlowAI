"""Run one dataset row through one agent and capture what came back.

The ONLY module here that touches the real agent runtime. Copied from
model_graded/driver.py and must preserve its invariants verbatim — the sandbox
identity coupling especially, where a mistake fails silently rather than loudly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import agents.factory
import agents.loader
import app.agents.model_factory
import app.agents.sandbox

USER_ID = "eval-graded"
MAX_SANDBOX_RUN_ID = 128


@dataclass
class DispatchResult:
    """One row's dispatch: the response and everything needed to grade it."""

    row_id: str
    agent_id: str
    response: str
    system_prompt: str
    errored: bool
    error_reason: str | None
    tokens_in: int
    tokens_out: int
    resolved_model_id: str
    log_path: str
    sandbox_run_id: str
    seed_files: dict[str, str] = field(default_factory=dict)


def _compose_prompt_for(agent_id: str, ctx) -> str:
    """Compose the system prompt exactly as create_runner does for this agent."""
    spec = agents.loader.load_agent_spec(agent_id)
    custom_tools, exclude_builtin = agents.factory._resolve_runner_tools(spec, ctx)
    no_tools = exclude_builtin and not custom_tools
    return agents.factory._compose_system_prompt(spec, ctx, no_tools=no_tools)


def sweep_expired_sandboxes() -> int:
    """Remove expired row sandboxes via the runtime's own TTL sweep.

    Grading has no server to run the periodic sweep the app relies on, so the
    orchestrator calls this at end of run: the finishing run's sandboxes stay
    inspectable, anything past RUN_DIR_TTL_HOURS goes.
    """
    return app.agents.sandbox.sweep_expired()


def _seeded_sandbox(sandbox_run_id: str, seed_files: dict[str, str]):
    """Build the row's RunSandbox and write every seed file into it."""
    sandbox = app.agents.sandbox.RunSandbox(USER_ID, sandbox_run_id)
    sandbox.ensure()
    for relpath, content in seed_files.items():
        sandbox.write(relpath, content)
    return sandbox


def _resolve_model(provider: str | None, model: str | None):
    """provider set -> a built model INSTANCE; otherwise the raw model id/None."""
    if provider is None:
        return model
    return app.agents.model_factory.build_model(model, provider=provider)


async def run_row(
    stage_input,
    *,
    agent_id: str,
    sandbox_run_id: str,
    log_path: Path,
    deliverable_file: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> DispatchResult:
    """Dispatch one row via create_runner and capture the response.

    Invariants that must survive verbatim from the copied driver:

    - ONE SANDBOX PER ROW for the whole workflow: `sandbox_run_id` is
      `{dataset_run_id}-{row_id}`, so build -> validate chains exactly as
      production does. Assert it is <= 128 chars — RunSandbox._safe_segment
      truncates, and a truncation collides two rows into one sandbox.
    - Build the RunSandbox here, seed `stage_input.seed_files` into it BEFORE
      dispatch, and pass it to create_runner as `run_sandbox=` EXPLICITLY rather
      than relying on the identity coincidence.
    - `thread_id = f"{sandbox_run_id}:{agent_id}"` — what the engine does.
    - provider is not None -> ctx.model = build_model(model, provider=provider)
      (an INSTANCE); else ctx.model = model. DeepAgentRunner does not forward
      provider.
    - `resolved_model_id = getattr(runner, "model_id", None) or "unknown"`.
    - astream_events YIELDS errors, never raises. `usage` fires once per model
      turn and must be SUMMED. Events: chunk, usage, tool_call, tool_result,
      error, gate, done.
    - Deliverable read-back is skipped on error and only replaces `response`
      when `sandbox.read()` returns non-None.
    - EMPTY RESPONSE IS AN ERROR: classify `not response.strip()` as errored
      here, before precheck ever sees it, or it fails the wrapper check with a
      misleading reason and counts against precheck_pass_rate.

    Returns the COMPOSED system prompt actually used, so the judge grades the
    prompt the agent really saw rather than re-composing it with no_tools=True.
    """
    if len(sandbox_run_id) > MAX_SANDBOX_RUN_ID:
        raise ValueError(
            f"sandbox_run_id is {len(sandbox_run_id)} chars, over the "
            f"{MAX_SANDBOX_RUN_ID}-char limit RunSandbox._safe_segment truncates at "
            f"— a truncated id would collide two rows into one sandbox: {sandbox_run_id!r}"
        )

    seed_files = dict(stage_input.seed_files or {})
    deliverable = deliverable_file if deliverable_file is not None else stage_input.deliverable_file
    sandbox = _seeded_sandbox(sandbox_run_id, seed_files)

    ctx = agents.factory.AgentContext(
        user_request=stage_input.prompt,
        user_id=USER_ID,
        run_id=sandbox_run_id,
        model=_resolve_model(provider, model),
    )
    system_prompt = _compose_prompt_for(agent_id, ctx)
    runner = agents.factory.create_runner(
        agent_id,
        ctx,
        thread_id=f"{sandbox_run_id}:{agent_id}",
        run_sandbox=sandbox,
    )
    resolved_model_id = getattr(runner, "model_id", None) or "unknown"

    streamed: list[str] = []
    usage = {"input": 0, "output": 0}
    error_reason: str | None = None

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_f:
        log_f.write(
            f"row_id: {stage_input.row_id}\nagent_id: {agent_id}\n"
            f"sandbox_run_id: {sandbox_run_id}\nmodel: {resolved_model_id}\n"
            f"started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"seed_files: {sorted(seed_files)}\nprompt: {stage_input.prompt}\n"
            f"{'=' * 80}\n\n"
        )
        async for event in runner.astream_events(stage_input.prompt):
            etype = event.get("type")
            if etype == "chunk":
                chunk = event["chunk"]
                streamed.append(chunk)
                log_f.write(chunk)
            elif etype == "usage":
                usage["input"] += event.get("input_tokens", 0)
                usage["output"] += event.get("output_tokens", 0)
            elif etype == "tool_call":
                log_f.write(f"\n\n>>> TOOL CALL: {event.get('tool')}({event.get('args')})\n\n")
            elif etype == "tool_result":
                log_f.write(f">>> TOOL RESULT ({event.get('tool')}): {event.get('result')}\n\n")
            elif etype == "error":
                error_reason = str(event.get("error", "")) or "(no error detail)"
                log_f.write(f"\n\n>>> RUNNER ERROR: {error_reason}\n\n")

        response = "".join(streamed)
        errored = error_reason is not None

        if deliverable and not errored:
            content = sandbox.read(deliverable)
            if content is not None:
                response = content
                log_f.write(
                    f"\n\n{'=' * 80}\n"
                    f"deliverable read back from sandbox: {deliverable} "
                    f"({len(content)} chars)\n"
                )

        if not errored and not response.strip():
            errored = True
            detail = f" and nothing readable at {deliverable}" if deliverable else ""
            error_reason = f"empty response: the agent produced no text{detail}"
            log_f.write(f"\n\n>>> EMPTY RESPONSE: {error_reason}\n\n")

        log_f.write(
            f"\n\n{'=' * 80}\n"
            f"result: {'ERROR' if errored else 'CAPTURED'}\n"
            f"tokens: in={usage['input']} out={usage['output']}\n"
        )

    return DispatchResult(
        row_id=stage_input.row_id,
        agent_id=agent_id,
        response=response,
        system_prompt=system_prompt,
        errored=errored,
        error_reason=error_reason,
        tokens_in=usage["input"],
        tokens_out=usage["output"],
        resolved_model_id=resolved_model_id,
        log_path=str(log_path),
        sandbox_run_id=sandbox_run_id,
        seed_files=seed_files,
    )
