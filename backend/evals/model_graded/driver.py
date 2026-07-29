"""model_graded/driver.py — the generic model-graded driver.

Dispatches a scenario's ``prompt`` to its named, already-registered agent via
``agents/factory.py::create_runner`` — reused as-is, never a raw
``build_model().invoke(...)`` chat-completion call (see
specs/005-prompt-eval-scoring/clarifications.md Q9/Q11: only ``create_runner``
composes the actual production system prompt — injected template/design-
system content, guardrails, skills, hooks, constitution, then the ``AGENT.md``
body — and only ``create_runner`` gives a future tool-using agent real tool
execution to verify it produced a correct result).

For a pure text-only agent (``prototype-specify``, ``prototype-plan``,
``prototype-analyze``) the deliverable IS the captured response text — no
sandbox seeding, no file read-back. For a tool-using / file-editing agent
(``prototype-build``, ``prototype-validate``), ``GradedScenario.seed_files``/
``deliverable_file`` opt into seeding input files onto the same per-run
``RunSandbox`` ``create_runner`` already builds and reading the resulting
file back as the graded response — see their docstrings on ``GradedScenario``
below. This keeps the driver's default (both ``None``) behavior byte-
identical to before, while covering the same ground
``evals/hybrid/common/live_scenario.py::run_live_scenario_once`` (the
deterministic track's file-editing driver) does, for this branch's
model-graded scenarios.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_MODEL_GRADED_ROOT = Path(__file__).resolve().parent
DEFAULT_LOGS_DIR = _MODEL_GRADED_ROOT / "logs"


@dataclass(frozen=True)
class GradedScenario:
    """The unit of "what to run" for the model-graded branch.

    ``precheck_config`` drives the GENERIC, agent-agnostic
    ``model_graded/precheck.py::run_precheck`` — no per-agent Python required
    for the common case. ``precheck_module``, when set, is an ADDITIONAL
    narrow custom check (e.g. prototype-specify's nav-target cross-reference)
    run alongside, not instead of, the generic check. ``rubric`` is plain
    text/markdown fed as-is into judge.py's one shared prompt-builder — not a
    per-agent rubric module (clarifications.md Q10).
    """

    id: str
    agent_id: str
    prompt: str
    precheck_config: dict
    rubric: str
    min_pages: int = 4
    design_md: str | None = None
    precheck_module: "Callable[[str], tuple[bool, str]] | None" = None
    logs_dir: Path = DEFAULT_LOGS_DIR
    source_path: "Path | None" = None
    # Carried through from a dataset.json entry's "industry" field (None for
    # a standalone scenario YAML) — purely descriptive metadata, unused by
    # any grading logic, but threaded through so a `dataset` run can carry
    # it forward into the NEXT pipeline stage's auto-generated dataset.json
    # (clarifications.md-style chaining: this stage's output becomes the
    # next stage's dataset "prompt", same id/industry).
    industry: str | None = None
    # For TOOL-USING / file-editing agents (prototype-build, prototype-
    # validate) whose real deliverable is a FILE on the per-run sandbox, not
    # the streamed text — e.g. prototype-build writes prototype.html via
    # write_file/edit_file, and only speaks a short confirmation. When set,
    # ``seed_files`` (relpath -> content) is written into the sandbox BEFORE
    # dispatch (so read_file("spec.md") etc. work exactly like the real
    # pipeline), and ``deliverable_file`` is read back AFTER dispatch to use
    # as the graded response instead of the streamed text. Both None (the
    # default) reproduces a pure text-only agent exactly as before — no
    # sandbox seeding, no file read-back (driver.py's original contract).
    seed_files: dict[str, str] | None = None
    deliverable_file: str | None = None


@dataclass
class GradedRunResult:
    """What one dispatch of a GradedScenario to its agent produced.

    Deliberately carries no precheck/judge fields — dispatch-and-capture is
    this module's whole job (Component Boundaries: driver.py never imports
    judge.py/report.py/precheck.py). The caller (cli.py) runs the precheck
    and, optionally, the judge as separate steps against this result.
    """

    scenario_id: str
    agent_id: str
    response: str
    errored: bool
    error_reason: str | None
    tokens_in: int
    tokens_out: int
    run_dir: str
    resolved_model_id: str
    run_id: str


def _new_run_id(scenario_id: str) -> str:
    timestamp = time.strftime("%y%m%d%H%M%S")
    return f"{timestamp}-graded-{scenario_id}-{uuid.uuid4().hex[:8]}"


async def run_graded_scenario_once(
    scenario: GradedScenario,
    *,
    provider: str | None = None,
    model: str | None = None,
    run_dir: Path | None = None,
    log_filename: str | None = None,
) -> GradedRunResult:
    """Dispatch ``scenario.prompt`` to ``scenario.agent_id`` and capture its
    raw response.

    ``provider``/``model`` are optional, keyword-only overrides for the model
    the AGENT UNDER TEST runs with (rare — grading normally targets whatever
    the agent's own default is); ``None`` (the default) leaves
    ``AgentContext.model`` unset so ``create_runner``'s own default resolves,
    exactly like every other caller.

    ``run_dir``/``log_filename`` let a caller running MULTIPLE scenarios in
    one CLI invocation (e.g. the ``dataset`` command) share ONE folder across
    every dispatch instead of getting a fresh ``scenario.logs_dir/<run_id>/``
    folder each time — pass the same ``run_dir`` and a per-scenario
    ``log_filename`` (e.g. ``f"log-{scenario.id}.txt"``) so transcripts don't
    collide. Both default to ``None``, which reproduces the original
    behavior exactly: a fresh ``scenario.logs_dir/<run_id>/log.txt``.

    Every run writes a self-contained log file regardless of outcome, so a
    run can be investigated after the fact without re-running it.
    """
    from agents.factory import AgentContext, create_runner

    run_id = _new_run_id(scenario.id)
    user_id = "eval-graded"

    # Tool-using / file-editing agents (prototype-build, prototype-validate):
    # seed the per-run sandbox BEFORE dispatch so read_file("spec.md") etc.
    # inside the agent's own tool calls find real content — create_runner
    # (below) builds its OWN RunSandbox(user_id, run_id), which resolves to
    # this SAME on-disk root (same user_id/run_id → same _safe_segment path),
    # so seeding here is visible to it without any run_sandbox= override.
    sandbox = None
    if scenario.seed_files:
        from app.agents.sandbox import RunSandbox

        sandbox = RunSandbox(user_id, run_id)
        sandbox.ensure()
        for relpath, content in scenario.seed_files.items():
            sandbox.write(relpath, content)

    run_model = model
    if provider is not None:
        from app.agents.model_factory import build_model

        run_model = build_model(model, provider=provider)

    ctx = AgentContext(
        user_request=scenario.prompt,
        user_id=user_id,
        run_id=run_id,
        model=run_model,
    )
    runner = create_runner(scenario.agent_id, ctx, thread_id=f"{run_id}:graded")
    # DeepAgentRunner exposes the ACTUAL resolved model id (via
    # app.agents.model_factory.model_identifier off the built chat-model
    # instance), not just whatever `model`/`provider` the caller passed in —
    # the latter is often None (the common default-fallback-chain case), which
    # would otherwise make it impossible to tell which model actually ran.
    resolved_model_id = getattr(runner, "model_id", None) or "unknown"

    if run_dir is None:
        run_dir = scenario.logs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / (log_filename or "log.txt")

    streamed_text: list[str] = []
    usage = {"input": 0, "output": 0}
    runner_error: str | None = None

    with log_path.open("w", encoding="utf-8") as log_f:
        log_f.write(
            f"scenario: {scenario.id}\nagent_id: {scenario.agent_id}\nrun_id: {run_id}\n"
            f"started: {time.strftime('%Y-%m-%d %H:%M:%S')}\nprompt: {scenario.prompt}\n"
            f"{'=' * 80}\n\n"
        )
        async for event in runner.astream_events(scenario.prompt):
            etype = event.get("type")
            if etype == "chunk":
                chunk = event["chunk"]
                streamed_text.append(chunk)
                log_f.write(chunk)
            elif etype == "tool_call":
                log_f.write(f"\n\n>>> TOOL CALL: {event.get('tool')}({event.get('args')})\n\n")
            elif etype == "tool_result":
                log_f.write(f">>> TOOL RESULT ({event.get('tool')}): {event.get('result')}\n\n")
            elif etype == "error":
                # DeepAgentRunner swallows its own exceptions and yields THIS
                # instead of raising — capture distinctly, don't treat a
                # partial/no response as a normal (ungraded-worthy) miss.
                runner_error = str(event.get("error", "")) or "(no error detail)"
                log_f.write(f"\n\n>>> RUNNER ERROR: {runner_error}\n\n")
            elif etype == "usage":
                usage["input"] += event.get("input_tokens", 0)
                usage["output"] += event.get("output_tokens", 0)

        response = "".join(streamed_text)
        errored = runner_error is not None

        # Tool-using / file-editing agents: the graded DELIVERABLE is a file
        # on the sandbox, not the streamed text (which is often just a short
        # confirmation, or nothing at all). Read it back and use its content
        # as the response — but never on an errored dispatch (nothing was
        # necessarily written, and the streamed error text is what matters).
        if scenario.deliverable_file and not errored:
            if sandbox is None:
                from app.agents.sandbox import RunSandbox

                sandbox = RunSandbox(user_id, run_id)
            deliverable_content = sandbox.read(scenario.deliverable_file)
            if deliverable_content is not None:
                response = deliverable_content
                log_f.write(
                    f"\n\n{'=' * 80}\n"
                    f"deliverable read back from sandbox: {scenario.deliverable_file} "
                    f"({len(deliverable_content)} chars)\n"
                )

        log_f.write(
            f"\n\n{'=' * 80}\n"
            f"result: {'ERROR' if errored else 'CAPTURED'}\n"
            f"tokens: in={usage['input']} out={usage['output']}\n"
        )

    return GradedRunResult(
        scenario_id=scenario.id,
        agent_id=scenario.agent_id,
        response=response,
        errored=errored,
        error_reason=runner_error,
        tokens_in=usage["input"],
        tokens_out=usage["output"],
        run_dir=str(run_dir),
        resolved_model_id=resolved_model_id,
        run_id=run_id,
    )
