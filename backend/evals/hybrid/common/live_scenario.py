"""Generic live-scenario framework: shared by every workflow/<domain>/<variant>/
pipeline's live (real-model) eval tier. A phase folder supplies scenario YAML
files (via its own scenarios/ folder) and a checkers module; this file
supplies the loader, the dataclass, and the single-turn driver that invokes
whatever agent_id the scenario names.

This does NOT drive a full pipeline (multiple agents, gates, post-steps) —
it drives ONE agent's turn directly via create_runner, exactly like the
original prototype-revision-only driver always did. That is a deliberate
scope choice: it isolates "does the CURRENT PROMPT get the model to do the
right thing on this instruction," independent of whatever downstream
fix-loop may or may not exist. Wiring a full pipeline here would conflate
that question with whatever the pipeline-level defect evals are answering.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml


@dataclass(frozen=True)
class LiveScenario:
    id: str
    instruction: str
    checker: Callable[[str], tuple[bool, str]]
    html: str
    agent_id: str
    design_md: str | None = None
    output_filename: str = "prototype.html"
    logs_dir: "Path | None" = None  # set by load_scenario_yaml
    expensive: bool = False
    default_n: int = 10
    source_path: "Path | None" = None  # set by load_scenario_yaml


def _resolve_ctx_model(provider: str | None, model: str | None):
    """Resolve the value to pass as ``AgentContext.model`` for a live scenario run.

    ``provider is None`` (every existing caller) → pass ``model`` through
    unchanged (``None`` or a plain model-id string) — ``build_model()``'s
    default fallback chain applies, byte-identical to before this feature.

    ``provider="mistral"`` → build that provider's chat model instance
    eagerly via ``build_model(model, provider=provider)`` and return it.
    ``DeepAgentRunner`` duck-types ``AgentContext.model`` ("isinstance(model, str)
    or model is None" goes through ``build_model()``; anything else is used
    verbatim), so passing an already-built instance here forces the requested
    provider for this one call without any change to
    ``create_runner``/``DeepAgentRunner``/``AgentContext``.
    """
    if provider is not None:
        from app.agents.model_factory import build_model

        return build_model(model, provider=provider)
    return model


def _framed(instruction: str, html: str) -> str:
    return (
        "=== REVISION REQUEST ===\n"
        f"{instruction}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{html}\n"
        "=== END EXISTING HTML ==="
    )


def load_scenario_yaml(
    path: Path,
    *,
    checkers: dict[str, Callable[[str], tuple[bool, str]]],
    fixtures_root: Path,
    logs_root: Path,
) -> LiveScenario:
    """Load one scenario YAML file into a LiveScenario.

    `checkers` is the phase folder's own checker registry (its checkers.py's
    CHECKERS dict) — checker LOGIC has to be code, everything else about a
    scenario is data. `fixtures_root` is the phase folder itself (input.html
    / input.design_md paths in the YAML are relative to it). `logs_root` is
    evals/hybrid/ (NOT evals/hybrid/.runs/) — the YAML's `logs.dir` field
    (default ".runs") is resolved relative to it, matching every scenario's
    convention of naming the SAME shared .runs/ folder regardless of which
    phase folder the scenario came from.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    scenario_id = data.get("id")
    if not scenario_id:
        raise ValueError(f"{path}: 'id' is required")
    if scenario_id != path.stem:
        raise ValueError(
            f"{path}: id '{scenario_id}' must match the filename ('{path.stem}.yaml') "
            f"— a scenario can't answer to two names"
        )

    agent_id = data.get("agent_id")
    if not agent_id:
        raise ValueError(f"{path}: 'agent_id' is required")

    if "instruction_file" in data:
        instruction = (
            (fixtures_root / data["instruction_file"]).read_text(encoding="utf-8").strip()
        )
    elif "instruction" in data:
        instruction = str(data["instruction"]).strip()
    else:
        raise ValueError(f"{path}: needs 'instruction' or 'instruction_file'")

    input_spec = data.get("input") or {}
    html_rel = input_spec.get("html")
    if not html_rel:
        raise ValueError(f"{path}: 'input.html' is required")
    html = (fixtures_root / html_rel).read_text(encoding="utf-8").strip()

    design_md_rel = input_spec.get("design_md")
    design_md = (
        (fixtures_root / design_md_rel).read_text(encoding="utf-8")
        if design_md_rel
        else None
    )

    checker_name = data.get("checker")
    if checker_name not in checkers:
        raise ValueError(
            f"{path}: checker '{checker_name}' not in CHECKERS "
            f"(known: {sorted(checkers)})"
        )

    output_spec = data.get("output") or {}
    logs_spec = data.get("logs") or {}
    bench_spec = data.get("benchmark") or {}

    return LiveScenario(
        id=scenario_id,
        instruction=instruction,
        checker=checkers[checker_name],
        html=html,
        agent_id=agent_id,
        design_md=design_md,
        output_filename=output_spec.get("filename", "prototype.html"),
        logs_dir=logs_root / logs_spec.get("dir", ".runs"),
        expensive=bool(bench_spec.get("expensive", False)),
        default_n=int(bench_spec.get("default_n", 10)),
        source_path=path,
    )


class _NarrationBuffer:
    """Collapse a token-by-token text stream into readable, sentence-sized lines.

    The raw ``chunk`` stream arrives as arbitrary word/sub-word fragments —
    printing each one as its own line is unreadable (one word per terminal
    line). This accumulates fragments and flushes a single collapsed-
    whitespace line once the buffer looks like a complete thought (ends on
    sentence punctuation / newline) or has grown long enough that waiting
    further would delay visible progress too much.
    """

    _FLUSH_MIN_CHARS = 20
    _FORCE_FLUSH_CHARS = 300

    def __init__(self, emit: "Callable[[str], None]") -> None:
        self._buf = ""
        self._emit = emit

    def add(self, chunk: str) -> None:
        self._buf += chunk
        stripped = self._buf.strip()
        if not stripped:
            return
        boundary = bool(re.search(r"[.!?:;\n]\s*$", self._buf))
        if (boundary and len(stripped) >= self._FLUSH_MIN_CHARS) or len(stripped) >= self._FORCE_FLUSH_CHARS:
            self.flush()

    def flush(self) -> None:
        text = re.sub(r"\s+", " ", self._buf).strip()
        self._buf = ""
        if text:
            self._emit(text)


@dataclass
class LiveRunResult:
    scenario_id: str
    passed: bool
    reason: str
    errored: bool
    static_ok: bool
    static_issues: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: list[str] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    streamed_text: str = ""
    final_html: str = ""
    run_dir: str = ""


async def run_live_scenario_once(
    scenario: LiveScenario,
    *,
    on_event: "Callable[[str], None] | None" = None,
    provider: str | None = None,
    model: str | None = None,
) -> LiveRunResult:
    """Send the real composed prompt + dispatch message for ``scenario`` to the
    real model and check the delivered file. Consumes tokens.

    ``provider``/``model`` are optional, keyword-only overrides — both default to
    ``None``, so every existing caller (``live_benchmark.py``, ``test_live.py``)
    that omits them is unaffected and still runs against the default
    Haiku/Bedrock path (``ctx.model=None``). Pass ``provider="mistral"`` to
    force this run onto that provider instead — via
    ``app.agents.model_factory.build_model``'s explicit opt-in — even when
    ``ANTHROPIC_API_KEY`` is set in the calling shell; ``model`` optionally
    overrides that provider's default model id.

    ``on_event``, when given, is called with READABLE progress lines as the
    run proceeds (tool calls, and the model's narration COLLAPSED into
    sentence-sized lines via ``_NarrationBuffer`` — not one line per raw
    token) — without it, a caller sees nothing until the whole (possibly
    multi-minute, on a large fixture) run finishes.

    Independent of ``on_event``, EVERY run writes a self-contained folder to
    ``scenario.logs_dir/<run_id>/`` (``LiveRunResult.run_dir``) so a run can
    be investigated after the fact without re-running it:

        <logs_dir>/<run_id>/
          input/<output_filename>   the exact HTML fed to the agent
          input/design.md           (only when the scenario has one)
          input/instruction.md      the revision instruction sent
          output/<output_filename>  the exact file the agent delivered
          log.txt                   full raw transcript + tool calls + verdict
    """
    from agents.capabilities.context_providers.previous_run import (
        _slim_revision_message,
    )
    from agents.factory import AgentContext, create_runner
    from app.agents.sandbox import RunSandbox
    from app.agents.static_check import static_check

    # yymmddhhmmss prefix so log folders sort chronologically by name (which
    # ran first/before/after is visible from `ls` alone, no need to check
    # mtimes). The uuid suffix still guarantees uniqueness even when two runs
    # in a benchmark loop start within the same second.
    timestamp = time.strftime("%y%m%d%H%M%S")
    run_id = f"{timestamp}-live-{scenario.id}-{uuid.uuid4().hex[:8]}"
    user_id = "eval-live"
    sandbox = RunSandbox(user_id, run_id)
    sandbox.ensure()
    sandbox.write("prototype.html", scenario.html)
    if scenario.design_md is not None:
        sandbox.write("design.md", scenario.design_md)

    framed = _framed(scenario.instruction, scenario.html)
    dispatch = _slim_revision_message(framed, "prototype.html")

    run_model = _resolve_ctx_model(provider, model)

    ctx = AgentContext(
        user_request=dispatch,
        user_id=user_id,
        run_id=run_id,
        model=run_model,
    )
    runner = create_runner(scenario.agent_id, ctx, thread_id=f"{run_id}:live")

    run_dir = scenario.logs_dir / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    (input_dir / scenario.output_filename).write_text(scenario.html, encoding="utf-8")
    if scenario.design_md is not None:
        (input_dir / "design.md").write_text(scenario.design_md, encoding="utf-8")
    (input_dir / "instruction.md").write_text(scenario.instruction, encoding="utf-8")

    log_path = run_dir / "log.txt"
    log_f = log_path.open("w", encoding="utf-8")
    log_f.write(
        f"scenario: {scenario.id}\nrun_id: {run_id}\nstarted: "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}\ninstruction: {scenario.instruction}\n"
        f"{'=' * 80}\n\n"
    )

    def _emit(line: str) -> None:
        if on_event:
            on_event(f"[{scenario.id}] {line}")

    narration = _NarrationBuffer(_emit)

    streamed_text: list[str] = []
    tool_calls: list[str] = []
    tool_results: list[str] = []
    usage = {"input": 0, "output": 0}
    runner_error: str | None = None
    _emit("connecting to model...")
    try:
        async for event in runner.astream_events(dispatch):
            etype = event.get("type")
            if etype == "chunk":
                chunk = event["chunk"]
                streamed_text.append(chunk)
                log_f.write(chunk)
                narration.add(chunk)
            elif etype == "tool_call":
                narration.flush()
                args = str(event.get("args", ""))
                call = f"{event.get('tool')}({args})"
                tool_calls.append(call)
                log_f.write(f"\n\n>>> TOOL CALL #{len(tool_calls)}: {call}\n\n")
                _emit(f"tool_call #{len(tool_calls)}: {call[:160]}")
            elif etype == "tool_result":
                result = str(event.get("result", ""))
                tool_results.append(result)
                # Full, UNTRUNCATED result to the log file — errors like
                # deepagents' "Cannot write to X because it already exists"
                # would otherwise be invisible without reading library source.
                log_f.write(
                    f">>> TOOL RESULT #{len(tool_results)} "
                    f"({event.get('tool')}):\n{result}\n\n"
                )
                # Live/terminal view stays short — full detail is always in the log.
                one_line = re.sub(r"\s+", " ", result).strip()
                is_error = one_line.lower().startswith(("error", "cannot"))
                marker = "ERROR " if is_error else ""
                _emit(f"tool_result #{len(tool_results)} {marker}{one_line[:160]}")
            elif etype == "error":
                # DeepAgentRunner swallows its own exceptions and yields THIS
                # instead of raising — e.g. an AWS auth failure. Left
                # unhandled, the code below would check the checker against
                # the UNTOUCHED input and report a normal-looking MISS,
                # indistinguishable from a real model failure. Capture it
                # distinctly instead.
                runner_error = str(event.get("error", "")) or "(no error detail)"
                log_f.write(f"\n\n>>> RUNNER ERROR: {runner_error}\n\n")
                _emit(f"RUNNER ERROR: {runner_error[:300]}")
            elif etype == "usage":
                usage["input"] += event.get("input_tokens", 0)
                usage["output"] += event.get("output_tokens", 0)
        narration.flush()
        _emit("model turn done — checking result...")

        final_path = sandbox.path_for("prototype.html")
        final_html = final_path.read_text(encoding="utf-8")
        (output_dir / scenario.output_filename).write_text(final_html, encoding="utf-8")

        if runner_error is not None:
            # Do NOT run the content checker against an unedited (or
            # partially-edited-then-crashed) file and report it as a normal
            # miss — that conflates "the model tried and got it wrong" with
            # "the model never got a real turn." Surface the infra failure
            # as its own, clearly-labeled outcome instead.
            passed = False
            errored = True
            reason = f"INFRASTRUCTURE ERROR (model call failed, not evaluated): {runner_error}"
            sres = static_check(final_path)  # still recorded, for completeness
        else:
            errored = False
            passed, reason = scenario.checker(final_html)

            sres = static_check(final_path)
            if passed and not sres.ok:
                passed = False
                reason = f"static regression introduced: {sres.issues}"

        log_f.write(
            f"\n\n{'=' * 80}\n"
            f"result: {'ERROR' if errored else ('PASS' if passed else 'MISS')} "
            f"— {reason or 'satisfied'}\n"
            f"tokens: in={usage['input']} out={usage['output']}\n"
            f"tool_calls: {len(tool_calls)}\n"
            f"artifacts: {run_dir}\n"
        )
        # Emitted last so it's the final line a caller sees live — the run
        # folder path shouldn't require scrolling back up to find.
        _emit(f"artifacts folder: {run_dir}")
    finally:
        log_f.close()

    return LiveRunResult(
        scenario_id=scenario.id,
        passed=passed,
        reason=reason,
        errored=errored,
        static_ok=sres.ok,
        static_issues=list(sres.issues),
        tokens_in=usage["input"],
        tokens_out=usage["output"],
        tool_calls=tool_calls,
        tool_results=tool_results,
        streamed_text="".join(streamed_text),
        final_html=final_html,
        run_dir=str(run_dir),
    )
