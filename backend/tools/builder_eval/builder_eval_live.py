"""Live eval harness: drive real Builder turns in-process and record what they did.

This is the smallest harness that runs the production Builder turn loop outside
the HTTP server. It calls :func:`app.api.workflow_builder.turns.run_turn` with:

* the real ``TurnRunner``, ``DeepAgentRunner`` loop, observer middleware, skill
  file backend, script runner and ``propose_draft`` tool;
* the real ``ServerGate`` (``TurnDeps.gate=None``);
* the REAL chat model, built from ``--model`` like a production turn (Bedrock;
  AWS credentials come from the environment, never from this file);
* ``tests.fakes.builder_store.InMemoryBuilderStore`` instead of PostgreSQL, and a
  throw-away sandbox folder.

It is the same wiring as ``tests/security/builder_turn_harness.py`` with the
scripted model swapped for the real one. It calls a paid model, so an operator
runs it; CI never does.

One invocation runs one session: the first message, then each ``--followup``
message as a further turn in the same session (history is replayed from the
in-memory store exactly as production replays it from the database).

For every turn it writes, under ``<out>/<request id>/``:

* ``turn<N>.json``: status, outcome, stop reason, duration, tool-call counts,
  check verdicts, token usage, the counted questions, whether a draft was
  accepted, and the skill validator's result on the accepted manifest;
* ``turn<N>.reply.md``: the assistant reply exactly as stored;
* ``turn<N>.workflow.json``: the accepted manifest, when there is one.

Thinking text and tool results are not written.

Usage (from ``backend/``)::

    uv run python -m tools.builder_eval.builder_eval_live --id vague-a \\
        --text "create workflow for converting pdf to md content" \\
        --out ../path/to/baseline
    uv run python -m tools.builder_eval.builder_eval_live --id vague-a --text "..." \\
        --followup defaults --out ../path/to/phase1
    uv run python -m tools.builder_eval.builder_eval_live --summarize ../path/to/baseline

Exit status: 0 when every turn finished (whatever its outcome), 1 when a turn
failed, 2 on bad arguments.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

__all__ = ["TurnRecord", "count_questions", "main"]

# Evals run on Haiku 5.5 (a builder chat model, cost class cheap) unless --model says otherwise.
_DEFAULT_MODEL: Final = "eu.anthropic.claude-haiku-5-5"
_DEFAULT_TIER: Final = "basic"
_USER: Final = "eval-harness-user"
_SKILL_REL: Final = Path("app/agents/workflow_builder/skills/velocity-workflow-creator")
_VALIDATOR: Final = _SKILL_REL / "scripts" / "validate_manifest.py"
_BACKEND_DIR: Final = Path(__file__).resolve().parents[2]
_FOOTER: Final = (
    'Reply e.g. "1a 2c 3b", or "defaults" to accept all recommended options.'
)

# A numbered item ("1.", "1)", "**1.**", "### 1.") whose text holds a question mark.
_NUMBERED_RE: Final = re.compile(r"^\s*(?:#+\s*)?(?:\*\*)?\s*(\d{1,2})[.)]")
# A lettered option line ("a)", "a.", "- a)", "(a)", "**a)**", "A.").
_OPTION_RE: Final = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?\(?([a-fA-F])[.)]\s")


@dataclass(slots=True)
class TurnRecord:
    """What one Builder turn did, as recorded by the harness."""

    request_id: str
    turn: int
    message: str
    model_id: str
    effort: str | None
    tier: str
    status: str | None = None
    outcome: str | None = None
    stop_reason: str | None = None
    error_code: str | None = None
    error_text: str | None = None
    duration_seconds: float = 0.0
    tool_calls: int = 0
    tools_by_name: dict[str, int] = field(default_factory=dict)
    scripts_by_name: dict[str, int] = field(default_factory=dict)
    files_read: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    gate_rejections: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    questions_counted: int = 0
    question_lines: list[str] = field(default_factory=list)
    option_lines: int = 0
    draft_accepted: bool = False
    accepted_revision: int | None = None
    manifest_steps: int | None = None
    validator_verdict: str | None = None
    validator_head: list[str] = field(default_factory=list)
    reply_chars: int = 0
    intake_enabled: bool = False
    prompt_version: str | None = None
    intake_phase: str | None = None
    intake_rounds: int | None = None
    intake_ready_reason: str | None = None
    intake_sources: dict[str, str] = field(default_factory=dict)
    intake_assumptions: list[str] = field(default_factory=list)
    reply_footer_last: bool = False
    human_gate_steps: list[str] = field(default_factory=list)
    intake_source_counts: dict[str, int] = field(default_factory=dict)
    intake_blocking_source_counts: dict[str, int] = field(default_factory=dict)
    intake_repairs_total: int = 0
    intake_retries_total: int = 0
    intake_questions: list[dict[str, Any]] = field(default_factory=list)
    assumptions_echoed: int | None = None
    manifest_shape: dict[str, Any] = field(default_factory=dict)
    answer_choices: list[str] = field(default_factory=list)
    open_question_bullets: int | None = None
    gate_rejection_rules: list[list[str]] = field(default_factory=list)
    irreversible_gate_rejections: int = 0
    redo_accepted_after_irreversible_rejection: bool | None = None
    reply_has_assumptions_block: bool = False
    intake_feasibility_notes: list[str] = field(default_factory=list)
    intake_effort: str | None = None
    irreversible_action_after_intake: bool | None = None
    approval_question_form: str | None = None
    transient_retries: list[str] = field(default_factory=list)
    infra_failure: str | None = None
    intake_failure: str | None = None
    critic_model: str | None = None
    critic_status: str | None = None
    critic_scores: dict[str, int | None] = field(default_factory=dict)
    critic_usage: list[dict[str, Any]] = field(default_factory=list)
    shape_diff_vs_defaults: str | None = None


def count_questions(reply: str) -> tuple[int, list[str], int]:
    """Count the numbered questions and lettered options in a reply.

    A numbered item counts as a question when its line, or one of the next two
    non-empty lines, contains ``?``. The count is a heuristic for the report;
    the reply file is the evidence.

    Returns:
        ``(question count, the question lines, lettered option lines)``.
    """
    lines = reply.splitlines()
    questions: list[str] = []
    for index, line in enumerate(lines):
        if not _NUMBERED_RE.match(line):
            continue
        window = [line, *[x for x in lines[index + 1 : index + 4] if x.strip()][:2]]
        if any("?" in part for part in window):
            questions.append(line.strip()[:200])
    options = sum(1 for line in lines if _OPTION_RE.match(line))
    return len(questions), questions, options


@contextmanager
def _scope(store: Any) -> Iterator[Any]:
    yield store


def _validate(manifest_path: Path) -> tuple[str, list[str]]:
    """Run the skill validator at ``user`` trust; return the verdict and its head."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        # The file name only, run from its folder: the report then holds no local path.
        [
            sys.executable,
            str(_BACKEND_DIR / _VALIDATOR),
            manifest_path.name,
            "--trust",
            "user",
            "--summary",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=manifest_path.parent,
        timeout=120,
        check=False,
    )
    lines = [x for x in completed.stdout.splitlines() if x.strip()]
    verdict = (
        "VALID"
        if completed.returncode == 0
        else f"INVALID (exit {completed.returncode})"
    )
    return verdict, lines[:40]


def _human_gate_steps(manifest: dict[str, Any]) -> list[str]:
    """``instance_id`` of every step (nested too) with a human-family gate."""
    found: list[str] = []

    def walk(steps: Any) -> None:
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            gates = step.get("gates") or []
            if any(g in ("human", "before-human", "approval") for g in gates):
                found.append(str(step.get("instance_id") or step.get("agent")))
            walk((step.get("subagents") or {}).get("steps"))

    walk(manifest.get("steps"))
    return found


_BLOCKING: Final = frozenset(
    {
        "goal",
        "deliverable",
        "done_when",
        "input_source",
        "input_variability",
        "output_structure",
        "external_systems",
        "write_destinations",
        "irreversible_actions",
        "human_approval_points",
    }
)


def _record_intake(record: TurnRecord, sandbox: Any) -> dict[str, Any]:
    """Copy the intake state into the record: phase, rounds, sources, counts, questions.

    Returns the whole state (the critic needs the slot values); ``{}`` when none.
    """
    path = sandbox.path_for("intake/state.json")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(state, dict):
        return {}
    _copy_intake(record, state)
    return state


def _copy_intake(record: TurnRecord, state: dict[str, Any]) -> None:
    record.intake_phase = state.get("phase")
    record.intake_rounds = state.get("rounds_asked")
    record.intake_ready_reason = state.get("ready_reason")
    record.intake_sources = {
        name: str(slot.get("source"))
        for name, slot in (state.get("slots") or {}).items()
    }
    record.intake_source_counts = dict(Counter(record.intake_sources.values()))
    record.intake_blocking_source_counts = dict(
        Counter(s for n, s in record.intake_sources.items() if n in _BLOCKING)
    )
    record.intake_assumptions = list(state.get("assumptions") or [])
    record.intake_repairs_total = int(state.get("repairs") or 0)
    record.intake_retries_total = int(state.get("retries") or 0)
    if state.get("phase") == "asking":
        record.intake_questions = [
            {
                "slot": q.get("slot"),
                "criticality": "blocking"
                if q.get("slot") in _BLOCKING
                else "important",
                "text": q.get("text"),
                "options": [o.get("label") for o in q.get("options") or []],
                "recommended_flags": [
                    bool(o.get("recommended")) for o in q.get("options") or []
                ],
                "followups": {
                    str(i): {
                        "text": o.get("followup_text"),
                        "slot": o.get("followup_slot"),
                    }
                    for i, o in enumerate(q.get("options") or [])
                    if o.get("followup_slot")
                },
            }
            for q in state.get("questions") or []
        ]
    record.intake_feasibility_notes = list(state.get("feasibility_notes") or [])
    rule = _rule()
    slots = state.get("slots") or {}
    record.irreversible_action_after_intake = (
        bool(rule.has_irreversible_action(slots)) if slots else None
    )
    for q in record.intake_questions:
        if q["slot"] == "human_approval_points":
            real = [o for o in q["options"] if not str(o).startswith("Not sure")]
            record.approval_question_form = (
                "whether"
                if any(rule.removes_person(str(o)) for o in real)
                else "where_what"
            )


def _rule() -> Any:
    """The skill's readiness rule (scripts/intake_readiness.py), as the builder loads it."""
    from app.agents.workflow_builder import intake
    from app.agents.workflow_builder.skill_package import SKILL_DIR

    return intake._readiness(SKILL_DIR)  # noqa: SLF001 - eval tool reuses the one rule


def open_question_bullets(reply: str) -> int:
    """Bullet lines in the reply's "Open questions" part, up to the next bold heading."""
    lines = reply.splitlines()
    start = next(
        (i for i, x in enumerate(lines) if "open questions" in x.lower()), None
    )
    if start is None:
        return 0
    count = 0
    for line in lines[start + 1 :]:
        if line.startswith("**"):
            break
        if line.lstrip().startswith(("- ", "* ")) or re.match(r"^\s*\d+[.)] ", line):
            count += 1
    return count


def _echoed(line: str, reply_lower: str) -> bool:
    """Whether an assumption line's slot or value shows up in the builder's reply."""
    name, _, value = line.removeprefix("Assumption: ").partition(" = ")
    value = value.removesuffix(" - correct me if wrong").strip().lower()
    names = (name.lower(), name.replace("_", " ").lower())
    return any(n in reply_lower for n in names) or (
        bool(value) and value[:40] in reply_lower
    )


def answer_codes(questions: list[dict[str, Any]], plan: dict[str, str]) -> str:
    """Answer the round-one questions by option LETTER, as codes "1b 2c".

    ``plan`` maps a slot to the letter to pick on the question about that slot, as
    the question JSON lists its options (a = first). A slot not in the plan, or a
    letter the question does not have, takes the recommended option. No keyword
    matching: what was chosen is exactly the letter, recorded with its label.
    """
    codes = []
    for number, question in enumerate(questions, start=1):
        options = list(question.get("options") or [])
        letter, _, text = (
            str(plan.get(str(question.get("slot")), plan.get("*", "")))
            .strip()
            .partition(" ")
        )
        index = ord(letter.lower()) - ord("a") if letter else -1
        if not 0 <= index < len(options):
            index = next(
                (
                    i
                    for i, flag in enumerate(question.get("recommended_flags") or [])
                    if flag
                ),
                0,
            )
        followups = question.get("followups") or {}
        if plan.get("_prefer_followup") and followups and not letter:
            index = int(min(followups, key=int))
        if not text and str(index) in followups:
            text = str(plan.get("_followup_default", ""))
        code = f"{number}{chr(ord('a') + index)}"
        codes.append(f"{code} {text.strip()}" if text.strip() else code)
    return " ".join(codes)


def _flatten(steps: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps or []:
        if isinstance(step, dict):
            out.append(step)
            out += _flatten((step.get("subagents") or {}).get("steps"))
    return out


def manifest_shape(manifest: dict[str, Any]) -> dict[str, Any]:
    """The manifest's shape: steps, intake step, branch, fan-out, loop, gates before posts.

    Irreversible steps and their gates use the platform's own check
    (``irreversible_gate``), so the harness and the Server_Gate agree.
    """
    from app.agents.workflow_builder import irreversible_gate

    roots = [s for s in manifest.get("steps") or [] if isinstance(s, dict)]
    steps = _flatten(roots)
    text = json.dumps(manifest).lower()
    first = roots[0] if roots else {}
    first_name = f"{first.get('instance_id', '')} {first.get('name', '')}".lower()
    ungated = {
        issue.message.split("'")[1] for issue in irreversible_gate.check(manifest)
    }
    irreversible = [
        {
            "step": s.get("instance_id"),
            "gated": str(s.get("instance_id")) not in ungated,
        }
        for s in steps
        if irreversible_gate.irreversible_tools(s)
    ]
    return {
        "root_steps": len(roots),
        "all_steps": len(steps),
        "deliverable": (manifest.get("deliverable") or {}).get("strategy"),
        # By name: a drafter whose human gate is the approval before a post is not one.
        "intake_step": "human" in (first.get("gates") or []) and "intake" in first_name,
        "human_gates": len(_human_gate_steps(manifest)),
        "branch": any(
            "conditional" in (s.get("gates") or [])
            and not (s.get("route") or {}).get("loop_max_iterations")
            for s in steps
        ),
        "loop": any((s.get("route") or {}).get("loop_max_iterations") for s in steps),
        "fan_out": any(
            s.get("strategy") in ("fanout_batch", "wave_scheduler", "task_loop")
            or (s.get("subagents") or {}).get("mode") in ("fanout", "parallel")
            for s in steps
        ),
        "ocr": "ocr" in text or "pdf_pages" in text,
        "validators": sorted({v for s in steps for v in s.get("validators") or []}),
        "irreversible_steps": irreversible,
    }


def shape_diff(base: dict[str, Any], other: dict[str, Any]) -> str:
    """One line: how ``other`` differs from ``base`` (``+``/``-`` per feature)."""
    parts = []
    for key in ("intake_step", "branch", "loop", "fan_out", "ocr"):
        if bool(base.get(key)) != bool(other.get(key)):
            parts.append(f"{'+' if other.get(key) else '-'} {key.replace('_', ' ')}")
    for key in ("root_steps", "human_gates"):
        if base.get(key) != other.get(key):
            parts.append(f"{key.replace('_', ' ')} {base.get(key)} -> {other.get(key)}")
    if base.get("deliverable") != other.get("deliverable"):
        parts.append(
            f"deliverable {base.get('deliverable')} -> {other.get('deliverable')}"
        )
    added = sorted(
        set(other.get("validators") or []) - set(base.get("validators") or [])
    )
    if added:
        parts.append(f"+ validators {', '.join(added)}")
    return ", ".join(parts) or "no shape change"


def _built_shape(folder: Path) -> dict[str, Any] | None:
    """The manifest shape of the last turn that built a draft in ``folder``."""
    for path in sorted(folder.glob("turn*.json"), reverse=True):
        if path.name.endswith((".workflow.json", ".critic.json")):
            continue
        try:
            shape = json.loads(path.read_text(encoding="utf-8")).get("manifest_shape")
        except (OSError, ValueError):
            continue
        if shape:
            return shape
    return None


async def _run_critic(  # noqa: PLR0913 - one call site, all named
    record: TurnRecord,
    manifest_path: Path,
    state: dict[str, Any],
    reply: str,
    *,
    defaults_run: dict[str, Any] | None,
    critic_model: str,
) -> None:
    """Score the turn's manifest with the offline critic; facts go to ``turn<N>.critic.json``."""
    from tools.builder_eval import critic

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        result = await _retrying(critic.score, record.transient_retries)(
            manifest,
            slots=state.get("slots") or {},
            reply=reply,
            assumptions=record.intake_assumptions,
            model_id=critic_model,
            defaults_run=defaults_run,
        )
    except Exception as exc:  # noqa: BLE001 - a critic failure must not lose the turn record
        record.critic_status = f"error: {type(exc).__name__}"
        return
    record.critic_model = critic_model
    record.critic_status = result.status
    record.critic_scores = {k: v.get("score") for k, v in result.scores.items()}
    record.critic_usage = result.usage
    manifest_path.with_name(
        manifest_path.name.replace(".workflow.json", ".critic.json")
    ).write_text(
        json.dumps({"scores": result.scores, "facts": result.facts}, indent=2),
        encoding="utf-8",
    )


# Transient Bedrock / network failures (DNS, connection resets, throttling, timeouts).
_TRANSIENT_MARKERS: Final = (
    "getaddrinfo failed",
    "NameResolutionError",
    "ConnectionResetError",
    "Connection broken",
    "EndpointConnectionError",
    "ConnectionClosedError",
    "ThrottlingException",
    "TooManyRequests",
    "ServiceUnavailable",
    "ReadTimeoutError",
    "ConnectTimeoutError",
    "ModelStreamErrorException",
    "Could not connect",
    "ProtocolError",
)
_BACKOFF_SECONDS: Final = (15.0, 45.0, 90.0)


def is_transient(exc: BaseException) -> bool:
    """True when ``exc`` or anything in its cause chain is a transient network/throttling error."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = f"{type(current).__name__} {current}"
        if any(marker in text for marker in _TRANSIENT_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


_ERROR_TEXT_CHARS: Final = 400
# Local paths in an error text, so a stored turn record names no machine folder.
_LOCAL_PATH: Final = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp|var)/)[^\s'\"]*")


class _TransientLog(logging.Handler):
    """Collects log lines that show a transient failure, and every error line, during one turn."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.hits: list[str] = []
        self.errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage() + (
            f" {record.exc_info[1]!r}" if record.exc_info else ""
        )
        if any(marker in text for marker in _TRANSIENT_MARKERS):
            self.hits.append(next(m for m in _TRANSIENT_MARKERS if m in text))
        if record.levelno >= logging.ERROR:
            self.errors.append(_LOCAL_PATH.sub("<path>", text)[:_ERROR_TEXT_CHARS])


def _retrying(func: Any, attempts: list[str]) -> Any:
    """Wrap an async call so transient errors retry 3 times with backoff."""

    async def call(*a: Any, **kw: Any) -> Any:
        for attempt in range(len(_BACKOFF_SECONDS) + 1):
            try:
                return await func(*a, **kw)
            except Exception as exc:  # noqa: BLE001 - re-raised unless transient
                if attempt == len(_BACKOFF_SECONDS) or not is_transient(exc):
                    raise
                attempts.append(type(exc).__name__)
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
        raise RuntimeError("unreachable")

    return call


async def _run_session(args: argparse.Namespace) -> int:  # noqa: PLR0915 - one linear script
    # Imported here so --summarize and --help work without the backend settings.
    from app.core.config import settings

    if args.intake is None:
        args.intake = settings.BUILDER_INTAKE_V2_ENABLED
    settings.BUILDER_INTAKE_V2_ENABLED = bool(args.intake)
    settings.BUILDER_INTAKE_EFFORT = args.intake_effort
    from app.api.workflow_builder import turns
    from app.api.workflow_builder.bus import SessionEventBus
    from app.api.workflow_builder.turns import (
        LiveTurn,
        TurnDeps,
        TurnRequest,
        attach_task,
        register_live_turn,
        run_turn,
        set_event_bus,
    )
    from app.agents.workflow_builder.sandbox import BuilderSandbox
    from tests.factories.builder_session_factory import BuilderSessionFactory
    from tests.fakes.builder_store import InMemoryBuilderStore

    out_dir = Path(args.out) / args.id
    out_dir.mkdir(parents=True, exist_ok=True)
    store = InMemoryBuilderStore()
    session = store.create_session(_USER, **BuilderSessionFactory.create_kwargs())
    session_id = str(session.id)
    sandbox_root = Path(tempfile.mkdtemp(prefix="builder-eval-"))
    # The sandbox holds session files only; the record and manifests go to --out.
    atexit.register(shutil.rmtree, sandbox_root, True)
    messages = [args.text, *(args.followup or [])]
    plan_choices: list[str] = []
    failed = False
    for number, message in enumerate(messages, start=1):
        started = time.monotonic()
        transient_retries: list[str] = []
        infra_failure: str | None = None
        for attempt in range(len(_BACKOFF_SECONDS) + 1):
            turns._LIVE_TURNS.clear()  # noqa: SLF001 - same reset as the security harness
            turns._TURN_TASKS.clear()  # noqa: SLF001
            begun = store.begin_turn(
                _USER,
                session_id,
                content=message,
                canvas_state=None,
                client_message_id=f"eval-{args.id}-{number}-{attempt}",
                model_id=args.model,
                effort=args.effort,
                skill_hash=None,
            )
            bus = SessionEventBus()
            set_event_bus(bus)
            deps = TurnDeps(
                bus=bus,
                store_scope=lambda: _scope(store),
                sandbox_factory=lambda user, sid: BuilderSandbox(
                    user, sid, root=sandbox_root
                ),
            )
            live = LiveTurn(
                session_id=session_id,
                turn_id=str(begun.assistant_message.id),
                user_message_id=str(begun.user_message.id),
                user_id=_USER,
                model_id=args.model,
                effort=args.effort,
                tier=args.tier,
            )
            register_live_turn(live)
            watcher = _TransientLog()
            logging.getLogger().addHandler(watcher)
            try:
                task = asyncio.ensure_future(
                    run_turn(
                        live, TurnRequest(content=message, canvas_state=None), deps
                    )
                )
                attach_task(live, task)
                await task
            finally:
                logging.getLogger().removeHandler(watcher)
                set_event_bus(None)
            row_now = store.get_message(_USER, live.turn_id)
            failed_now = getattr(row_now, "status", None) == "failed"
            intake_fell_back = bool(args.intake and live.intake_failure)
            if not watcher.hits or not (failed_now or intake_fell_back):
                break
            if intake_fell_back and live.accepted_revision is not None:
                infra_failure = (
                    f"intake fell back on a transient error ({watcher.hits[0]})"
                )
                break
            if attempt == len(_BACKOFF_SECONDS):
                infra_failure = (
                    f"still failing after {attempt} retries ({watcher.hits[0]})"
                )
                break
            transient_retries.append(watcher.hits[0])
            print(
                f"{args.id} turn {number}: transient {watcher.hits[0]}; retry {attempt + 1}",
                flush=True,
            )
            await asyncio.sleep(_BACKOFF_SECONDS[attempt])
        record = TurnRecord(
            request_id=args.id,
            turn=number,
            message=message,
            model_id=args.model,
            effort=args.effort,
            tier=args.tier,
            duration_seconds=round(time.monotonic() - started, 1),
        )
        row = store.get_message(_USER, live.turn_id)
        reply = str(getattr(row, "content", "") or "")
        record.status = getattr(row, "status", None)
        record.outcome = getattr(row, "outcome", None)
        record.stop_reason = getattr(row, "stop_reason", None)
        record.error_code = getattr(row, "error_code", None)
        record.error_text = watcher.errors[0] if watcher.errors else None
        record.tool_calls = live.tool_calls
        record.transient_retries = transient_retries
        record.infra_failure = infra_failure
        record.intake_failure = live.intake_failure
        record.tools_by_name = dict(Counter(a.tool for a in live.activity))
        record.scripts_by_name = dict(
            Counter(c.script for c in live.finished_calls if c.script)
        )
        record.files_read = [
            str(c.path) for c in live.finished_calls if c.name == "read_file" and c.path
        ]
        record.checks = [c.model_dump(mode="json") for c in live.checks]
        record.gate_rejections = live.gate_rejections
        record.usage = live.usage.model_dump(mode="json")
        record.reply_chars = len(reply)
        (
            record.questions_counted,
            record.question_lines,
            record.option_lines,
        ) = count_questions(reply)
        (out_dir / f"turn{number}.reply.md").write_text(reply, encoding="utf-8")
        record.gate_rejection_rules = [
            [str(issue.rule) for issue in issues]
            for issues in live.gate_rejection_issues
        ]
        record.irreversible_gate_rejections = sum(
            "irreversible_gate" in rules for rules in record.gate_rejection_rules
        )
        if record.irreversible_gate_rejections:
            record.redo_accepted_after_irreversible_rejection = (
                live.accepted_revision is not None
            )
        record.reply_has_assumptions_block = "**Assumptions**" in reply
        record.intake_enabled = bool(args.intake)
        record.intake_effort = getattr(live, "intake_effort", None)
        record.prompt_version = getattr(row, "prompt_version", None)
        record.reply_footer_last = bool(reply.strip()) and (
            reply.strip().splitlines()[-1] == _FOOTER
        )
        state = _record_intake(
            record, BuilderSandbox(_USER, session_id, root=sandbox_root)
        )
        record.accepted_revision = live.accepted_revision
        record.draft_accepted = live.accepted_revision is not None
        if record.draft_accepted:
            draft = store.get_latest_revision(_USER, session_id, "accepted")
            manifest = getattr(draft, "manifest", None)
            if isinstance(manifest, dict):
                path = out_dir / f"turn{number}.workflow.json"
                path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                record.manifest_steps = len(manifest.get("steps") or [])
                record.human_gate_steps = _human_gate_steps(manifest)
                record.manifest_shape = manifest_shape(manifest)
                record.validator_verdict, record.validator_head = _validate(path)
        if record.intake_assumptions and record.draft_accepted:
            lowered = reply.lower()
            record.assumptions_echoed = sum(
                1 for line in record.intake_assumptions if _echoed(line, lowered)
            )
            record.open_question_bullets = open_question_bullets(reply)
        if number >= 2 and plan_choices:
            record.answer_choices = plan_choices
        base_shape = _built_shape(args.compare_with) if args.compare_with else None
        if base_shape and record.manifest_shape:
            record.shape_diff_vs_defaults = shape_diff(
                base_shape, record.manifest_shape
            )
        if args.critic and record.draft_accepted and record.manifest_shape:
            await _run_critic(
                record,
                out_dir / f"turn{number}.workflow.json",
                state,
                reply,
                defaults_run=(
                    {
                        "shape": base_shape,
                        "answers_chosen": plan_choices,
                        "shape_diff": record.shape_diff_vs_defaults,
                    }
                    if base_shape and plan_choices
                    else None
                ),
                critic_model=args.critic_model,
            )
        if number == 1 and args.answer_plan and record.intake_questions:
            plan = json.loads(args.answer_plan.read_text(encoding="utf-8"))
            codes = answer_codes(record.intake_questions, plan)
            plan_choices = [
                f"{q['slot']}: {q['options'][ord(code[1]) - ord('a')]}"
                for q, code in zip(
                    record.intake_questions, re.findall(r"\d[a-e]", codes), strict=True
                )
            ]
            # The scripted answer is turn 2; any --followup ("defaults") comes after it.
            messages.insert(number, codes)
        if record.status not in ("completed",):
            failed = failed or record.status == "failed"
        stop_now = (
            bool(args.stop_when_built and record.draft_accepted)
            or record.infra_failure is not None
        )
        (out_dir / f"turn{number}.json").write_text(
            json.dumps(asdict(record), indent=2), encoding="utf-8"
        )
        print(
            f"{args.id} turn {number}: status={record.status} outcome={record.outcome} "
            f"questions={record.questions_counted} draft={record.draft_accepted} "
            f"validator={record.validator_verdict} {record.duration_seconds}s"
        )
        if stop_now:
            break
    return 1 if failed else 0


def _summarize(folder: Path) -> int:
    """Print a Markdown table of every ``turn<N>.json`` under ``folder``."""
    rows = []
    for path in sorted(folder.glob("*/turn*.json")):
        if path.name.endswith((".workflow.json", ".critic.json")):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(data)
    print(
        "| Request | Turn | Status | Outcome | Questions | Options | Draft | Steps "
        "| Validator | Human gates | Intake | Tool calls | Time (s) |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        intake = "-"
        if r.get("intake_enabled"):
            intake = f"{r.get('intake_phase') or 'none'}/{r.get('intake_ready_reason') or '-'}"
        gates = ", ".join(r.get("human_gate_steps") or []) or (
            "-" if not r["draft_accepted"] else "none"
        )
        print(
            f"| {r['request_id']} | {r['turn']} | {r['status']} | {r['outcome']} "
            f"| {r['questions_counted']} | {r['option_lines']} | "
            f"{'yes' if r['draft_accepted'] else 'no'} | {r['manifest_steps'] or '-'} "
            f"| {r['validator_verdict'] or '-'} | {gates} | {intake} | {r['tool_calls']} "
            f"| {r['duration_seconds']} |"
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--id", help="request id, names the output folder")
    parser.add_argument("--text", help="the first user message")
    parser.add_argument(
        "--followup", action="append", help="a later user message (repeatable)"
    )
    parser.add_argument("--out", help="output folder")
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    parser.add_argument("--effort", default=None)
    parser.add_argument("--tier", default=_DEFAULT_TIER)
    parser.add_argument(
        "--intake",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="BUILDER_INTAKE_V2_ENABLED for this run (default: the config default, on)",
    )
    parser.add_argument(
        "--intake-effort",
        choices=("default", "highest"),
        default="default",
        help="BUILDER_INTAKE_EFFORT for this run",
    )
    parser.add_argument(
        "--answer-plan",
        metavar="JSON_FILE",
        type=Path,
        help="after turn 1, answer its intake questions by option letter: a JSON object "
        "{slot: letter}; the chosen codes are sent as turn 2",
    )
    parser.add_argument(
        "--critic",
        action="store_true",
        help="score each accepted manifest with the offline critic (a paid model call)",
    )
    parser.add_argument("--critic-model", default=_DEFAULT_MODEL)
    parser.add_argument(
        "--stop-when-built",
        action="store_true",
        help="skip the remaining --followup messages once a draft is accepted",
    )
    parser.add_argument(
        "--compare-with",
        metavar="FOLDER",
        type=Path,
        help="with --answer-plan: a run of the same request answered 'defaults'; "
        "turn 2 then records a one-line manifest shape diff against it",
    )
    parser.add_argument("--summarize", metavar="FOLDER", help="print a table and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; see the module docstring."""
    args = _parser().parse_args(argv)
    if args.summarize:
        return _summarize(Path(args.summarize))
    if not (args.id and args.text and args.out):
        print("--id, --text and --out are required", file=sys.stderr)
        return 2
    return asyncio.run(_run_session(args))


if __name__ == "__main__":
    raise SystemExit(main())
