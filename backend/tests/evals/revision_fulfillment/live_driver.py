"""Shared driver for LIVE (real-model) scenario runs — S1/S2/example1 (opt-in, tokens!).

Extracted from ``test_live_s1.py`` so the single-run pytest tests and the
repeated-sampling benchmark script (``live_benchmark.py``) share ONE
implementation of "seed the fixture, send the real prompt surface to the
real model, check the delivered file" — no duplicated drive logic to drift.

This does NOT drive the full ``prototype_revision`` PIPELINE (two agents,
gates, post-steps) — it drives ONLY the revision agent's turn directly via
``create_runner``, exactly like ``test_live_s1.py`` always has. That is a
deliberate scope choice (matching design.md D-07's "prompt vs. pipeline" —
see the investigation's README): it isolates "does the CURRENT PROMPT get
Haiku to do the right thing on this instruction," independent of whatever
downstream fix-loop may or may not exist. Wiring the full pipeline here would
conflate the two questions the live tier and the defect evals are each
answering separately.

Scenarios carry their OWN fixture (html + optional design.md) — S1/S2 use the
small synthetic ``mini_prototype.html``; ``example1`` uses a real, larger
user-provided artifact (``fixtures/example1/`` — a copy of a real revision
request + prototype, kept inside the eval package so the suite has no
dependency outside ``backend/``) with NO design.md, exercising the AGENT.md's
documented no-design.md fallback path.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tests.evals.conftest import FIXTURES_DIR

LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"

MINI_HTML = (FIXTURES_DIR / "mini_prototype.html").read_text(encoding="utf-8").strip()
DESIGN_MD = (FIXTURES_DIR / "design.md").read_text(encoding="utf-8")

_EXAMPLE1_DIR = FIXTURES_DIR / "example1"
EXAMPLE1_HTML = (_EXAMPLE1_DIR / "prototype.html").read_text(encoding="utf-8").strip()
EXAMPLE1_INSTRUCTION = (
    (_EXAMPLE1_DIR / "prompt.md").read_text(encoding="utf-8").strip()
)

_EXAMPLE1_PAGES = ("dashboard-overview", "roles", "mfa", "ldap", "audit")
# Real content is >2KB per page even in the SHORTER of the two duplicated
# copies in the source fixture (measured directly: 2.1-3.5KB); a genuinely
# blanked/placeholder page is nowhere close. Set well below that floor so the
# check flags a real regression without being sensitive to how the model
# chooses to phrase/trim content.
_EXAMPLE1_MIN_CONTENT_CHARS = 300


def _framed(instruction: str, html: str) -> str:
    return (
        "=== REVISION REQUEST ===\n"
        f"{instruction}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{html}\n"
        "=== END EXISTING HTML ==="
    )


def _s1_wired(final_html: str) -> tuple[bool, str]:
    """Is the Save button (#save-btn) actually wired — inline onclick or JS listener?"""
    btn_match = re.search(r'<button[^>]*id="save-btn"[^>]*>', final_html)
    if not btn_match:
        return False, "Save button disappeared from the delivered file"
    btn_tag = btn_match.group(0)

    inline = re.search(r'onclick="([A-Za-z_$][\w$]*)\s*\(', btn_tag)
    script_bound = re.search(
        r"(getElementById\(['\"]save-btn['\"]\)|querySelector\(['\"]#save-btn['\"]\))"
        r"[\s\S]{0,120}addEventListener",
        final_html,
    )
    wired = False
    if inline:
        fn = inline.group(1)
        wired = bool(
            re.search(rf"function\s+{re.escape(fn)}\s*\(", final_html)
            or re.search(rf"{re.escape(fn)}\s*=\s*(async\s*)?\(", final_html)
        )
    wired = wired or bool(script_bound)
    if not wired:
        return False, "Save button has no working handler (neither inline nor script-bound)"
    return True, ""


def _s2_reachable(final_html: str) -> tuple[bool, str]:
    """Is there a Reports page (section + route) reachable via a sidebar nav link?"""
    has_section = bool(re.search(r'<section[^>]*data-page="reports"', final_html))
    has_route = bool(re.search(r"reports\s*:\s*['\"]#/reports['\"]", final_html))
    has_nav_link = bool(
        re.search(r'<a[^>]*class="nav-item"[^>]*href="#/reports"', final_html)
    )
    if not has_section:
        return False, "no <section data-page=\"reports\"> in delivered file"
    if not has_route:
        return False, "no 'reports' entry in the routes map"
    if not has_nav_link:
        return False, "Reports page exists but has NO sidebar nav link (unreachable)"
    return True, ""


def _example1_pages_have_real_content(final_html: str) -> tuple[bool, str]:
    """Every known page exists EXACTLY ONCE and has substantive content.

    The source fixture's actual defect (confirmed by direct inspection, not
    guessed) is a fully DUPLICATED document — every ``<section data-page="...">``
    appears twice, each copy already containing real data (KPI cards, tables,
    forms — 2-30KB each), not empty shells. The user's "pages are blank"
    report is consistent with that: with a duplicate id/section per page and
    a single ``document.querySelector`` (not ``querySelectorAll``) toggling
    ``is-active``, which copy actually renders is undefined/fragile — a
    genuine rendering bug this static check cannot directly observe (would
    need ``render_check``/headless Chromium for that), but the STRUCTURAL
    half of the fix (dedup + real content surviving) is checkable here.
    """
    for page_id in _EXAMPLE1_PAGES:
        matches = re.findall(
            rf'<section[^>]*data-page="{page_id}"[^>]*>([\s\S]*?)</section>',
            final_html,
        )
        if not matches:
            return False, f"page '{page_id}' is missing entirely from the delivered file"
        if len(matches) > 1:
            return False, (
                f"page '{page_id}' still appears {len(matches)} times — the "
                f"duplicated-document defect was not cleaned up"
            )
        body = re.sub(r"<h2[^>]*>.*?</h2>", "", matches[0], flags=re.S).strip()
        if len(body) < _EXAMPLE1_MIN_CONTENT_CHARS:
            return False, (
                f"page '{page_id}' has only {len(body)} chars of content after "
                f"its heading — looks blank/placeholder, not real data"
            )
    return True, ""


@dataclass(frozen=True)
class LiveScenario:
    id: str
    instruction: str
    checker: Callable[[str], tuple[bool, str]]
    html: str
    design_md: str | None = None


LIVE_SCENARIOS: dict[str, LiveScenario] = {
    "s1": LiveScenario(
        id="s1",
        instruction="Make the Save button on Settings actually save",
        checker=_s1_wired,
        html=MINI_HTML,
        design_md=DESIGN_MD,
    ),
    "s2": LiveScenario(
        id="s2",
        instruction="Add a Reports page reachable from the sidebar",
        checker=_s2_reachable,
        html=MINI_HTML,
        design_md=DESIGN_MD,
    ),
    "example1": LiveScenario(
        id="example1",
        instruction=EXAMPLE1_INSTRUCTION,
        checker=_example1_pages_have_real_content,
        html=EXAMPLE1_HTML,
        design_md=None,  # no design.md provided — exercises the documented fallback
    ),
}


class _NarrationBuffer:
    """Collapse a token-by-token text stream into readable, sentence-sized lines.

    The raw ``chunk`` stream arrives as arbitrary word/sub-word fragments —
    printing each one as its own line (the previous behavior) is unreadable
    (one word per terminal line). This accumulates fragments and flushes a
    single collapsed-whitespace line once the buffer looks like a complete
    thought (ends on sentence punctuation / newline) or has grown long enough
    that waiting further would delay visible progress too much.
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
    scenario_id: str,
    *,
    on_event: "Callable[[str], None] | None" = None,
) -> LiveRunResult:
    """Send the real composed prompt + dispatch message for ``scenario_id`` to the
    real model (Haiku default) and check the delivered file. Consumes tokens.

    ``on_event``, when given, is called with READABLE progress lines as the
    run proceeds (tool calls, and the model's narration COLLAPSED into
    sentence-sized lines via ``_NarrationBuffer`` — not one line per raw
    token) — without it, a caller sees nothing until the whole (possibly
    multi-minute, on the larger ``example1`` fixture) run finishes.

    Independent of ``on_event``, EVERY run writes a self-contained folder to
    ``tests/evals/logs/<run_id>/`` (``LiveRunResult.run_dir``) so a run can be
    investigated after the fact without re-running it:

        logs/<run_id>/
          input/prototype.html    the exact HTML fed to the agent
          input/design.md         (only when the scenario has one)
          input/instruction.md    the revision instruction sent
          output/prototype.html   the exact file the agent delivered
          log.txt                 full raw transcript + tool calls + verdict

    """
    from agents.capabilities.context_providers.previous_run import (
        _slim_revision_message,
    )
    from agents.factory import AgentContext, create_runner
    from app.agents.sandbox import RunSandbox
    from app.agents.static_check import static_check

    scenario = LIVE_SCENARIOS[scenario_id]

    # yymmddhhmmss prefix so log folders sort chronologically by name (which
    # ran first/before/after is visible from `ls` alone, no need to check
    # mtimes). The uuid suffix still guarantees uniqueness even when two runs
    # in a benchmark loop start within the same second.
    timestamp = time.strftime("%y%m%d%H%M%S")
    run_id = f"{timestamp}-live-{scenario_id}-{uuid.uuid4().hex[:8]}"
    user_id = "eval-live"
    sandbox = RunSandbox(user_id, run_id)
    sandbox.ensure()
    sandbox.write("prototype.html", scenario.html)
    if scenario.design_md is not None:
        sandbox.write("design.md", scenario.design_md)

    framed = _framed(scenario.instruction, scenario.html)
    dispatch = _slim_revision_message(framed, "prototype.html")

    ctx = AgentContext(
        user_request=dispatch,
        user_id=user_id,
        run_id=run_id,
        model=None,  # None => build_model default (Haiku)
    )
    runner = create_runner(
        "prototype-revision-agent", ctx, thread_id=f"{run_id}:live"
    )

    run_dir = LOGS_DIR / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    (input_dir / "prototype.html").write_text(scenario.html, encoding="utf-8")
    if scenario.design_md is not None:
        (input_dir / "design.md").write_text(scenario.design_md, encoding="utf-8")
    (input_dir / "instruction.md").write_text(scenario.instruction, encoding="utf-8")

    log_path = run_dir / "log.txt"
    log_f = log_path.open("w", encoding="utf-8")
    log_f.write(
        f"scenario: {scenario_id}\nrun_id: {run_id}\nstarted: "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}\ninstruction: {scenario.instruction}\n"
        f"{'=' * 80}\n\n"
    )

    def _emit(line: str) -> None:
        if on_event:
            on_event(f"[{scenario_id}] {line}")

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
                # Full, UNTRUNCATED result to the log file (this is exactly the
                # detail that was missing when diagnosing live-example1-1bac45b3 —
                # e.g. the deepagents "Cannot write to X because it already
                # exists" error was invisible without it, forcing a read of the
                # library source instead of the run's own log).
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
                # instead of raising (deep_agent_runner.py:611) — e.g. an AWS
                # auth failure. Left unhandled, the loop just ends here with
                # 0 tokens and NO edits applied, and the code below would
                # check the checker against the UNTOUCHED input and report a
                # normal-looking "MISS — <content reason>" — indistinguishable
                # from a real model failure. That's actively misleading (seen
                # live: an AccessDeniedException got reported as "still
                # appears 2 times", hiding that the model was never even
                # called). Capture it distinctly instead.
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
        (output_dir / "prototype.html").write_text(final_html, encoding="utf-8")

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
        # folder path (input/output/log.txt, everything needed to
        # investigate) shouldn't require scrolling back up to find.
        _emit(f"artifacts folder: {run_dir}")
    finally:
        log_f.close()

    return LiveRunResult(
        scenario_id=scenario_id,
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
