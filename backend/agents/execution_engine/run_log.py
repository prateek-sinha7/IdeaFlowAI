"""Engine-owned JSONL trace writer (R-23).

``RunLog`` writes ``<sandbox_root>/.logs/run-logs.jsonl`` — one JSON object per
line, append-only. It is instantiated and called by the engine only; no agent
tool exposes it. A logging failure (unwritable dir, serialization error, full
disk) must never fail a run — every method here swallows its own exceptions
and logs a warning instead of raising.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class RunLog:
    """Append-only JSONL trace writer scoped to one run's sandbox."""

    def __init__(self, sandbox_root: Path | None) -> None:
        # A run can legitimately have no sandbox (see `_run_agent`, which is
        # driven sandbox-less by several suites). Tracing is best-effort, so a
        # missing root disables the log rather than failing the run — the same
        # contract as the try/except in `write`.
        self._path = Path(sandbox_root) / ".logs" / "run-logs.jsonl" if sandbox_root else None

    def write(self, event: str, **fields: object) -> None:
        """Append one JSON object line. Never raises."""
        if self._path is None:
            return
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **fields,
            }
            line = json.dumps(entry, default=repr)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:  # noqa: BLE001 — logging must never fail a run
            logger.warning("RunLog.write failed for event %r: %s", event, exc)


# Two policies, because the trace carries two kinds of string.
#
# The model's OWN words — its output and its reasoning — ARE the trace. They are
# kept whole, bounded only so one pathological value cannot produce an unreadable
# line. Truncation there is announced, never silent.
_MAX_FIELD_CHARS = 200_000

# Everything a TOOL carried is described, not quoted. Reading a 10 MB file is one
# fact — which file, and did it work — and inlining the file itself buries every
# other line in the run. The head is kept because that is where a failure states
# itself ("Error: File '/presentation.html' not found"); the body is dropped and
# its size reported, so nothing is silently missing.
_MAX_PAYLOAD_CHARS = 2_000
_PAYLOAD_HEAD_CHARS = 200


def _walk(value: object, fn, _depth: int = 0) -> object:
    """Apply ``fn`` to every string inside ``value``, recursing into containers.

    Recursion is the point: the string worth bounding is never a top-level field,
    it is ``tool_call.args.content``. Depth-bounded so a self-referential or
    absurdly nested structure cannot spin — tool arguments are shallow, and
    anything past the bound is rendered rather than walked.
    """
    if isinstance(value, str):
        return fn(value)
    if _depth >= 6:
        return fn(repr(value))
    if isinstance(value, dict):
        return {k: _walk(v, fn, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_walk(v, fn, _depth + 1) for v in value]
    return value


def _cap(value: object) -> object:
    """Bound the model's own text, marking the cut so a reader is never misled."""

    def _one(text: str) -> str:
        if len(text) <= _MAX_FIELD_CHARS:
            return text
        return f"{text[:_MAX_FIELD_CHARS]}\u2026 [truncated, {len(text)} chars total]"

    return _walk(value, _one)


def _elide(value: object) -> object:
    """Describe a tool payload rather than quoting it.

    A short value (a path, a pattern, an `ok`, a one-line error) passes through
    untouched — that is the identifying detail worth having. A long one keeps its
    head and reports its size: enough to see WHAT happened and whether it worked,
    without the file body.
    """

    def _one(text: str) -> str:
        if len(text) <= _MAX_PAYLOAD_CHARS:
            return text
        return f"{text[:_PAYLOAD_HEAD_CHARS]}\u2026 <{len(text)} chars, elided>"

    return _walk(value, _one)


class RunTrace:
    """Full-fidelity tracer for one run, fed from the engine's OWN event stream.

    ``RunLog`` alone recorded step boundaries and errors — enough to see THAT a
    step ran and nothing about what it did. Diagnosing a run meant reading the
    server console or the database; the file on disk could not answer "did the
    agent call write_file, and with what?".

    The engine already emits every one of those facts as a typed event, and
    ``execute()`` stamps every event at ONE boundary before yielding it. This is
    driven from exactly that point, so coverage is by CONSTRUCTION — a new event
    type reaches the trace without anyone editing the engine — and the engine
    itself needs no per-event logging calls.

    Streaming deltas are never written per-event: they arrive token-by-token, and
    a line each would be tens of thousands of lines carrying a few characters
    apiece — a transcript of nothing. They are buffered and written whole, but the
    two kinds flush on DIFFERENT boundaries, because they are read differently.

    ``agent_chunk`` (the model's output) flushes as soon as anything else happens.
    What an agent said immediately BEFORE a tool call is part of reading that tool
    call, so the interleaving is the information.

    ``agent_thinking`` accumulates for the WHOLE step and is written once, when
    that agent finishes. Reasoning read in fragments split around tool calls is
    harder to follow than the same reasoning read straight through, and it is the
    conclusion that matters rather than where it happened to pause.
    """

    def __init__(self, sandbox_root: Path | None) -> None:
        self._log = RunLog(sandbox_root)
        self._out_agent: str | None = None
        self._out: list[str] = []
        # agent_id -> its reasoning so far, held until the agent's step ends.
        self._thinking: dict[str, list[str]] = {}

    # ── Ingest ────────────────────────────────────────────────────────────────

    def observe(self, event: dict) -> None:
        """Trace one engine event. Never raises (``RunLog.write`` swallows)."""
        try:
            etype = event.get("type") or "unknown"
            data = event.get("data")
            data = data if isinstance(data, dict) else {}
            agent_id = str(data.get("agent_id") or "")

            if etype == "agent_thinking":
                self._thinking.setdefault(agent_id, []).append(str(data.get("thinking") or ""))
                return
            if etype == "agent_chunk":
                if agent_id != self._out_agent:
                    self._flush_output()
                    self._out_agent = agent_id
                self._out.append(str(data.get("chunk") or ""))
                return

            self._flush_output()
            # A step's reasoning belongs with the step, so it is written just
            # BEFORE the line that ends it rather than after.
            if etype in ("agent_complete", "agent_error"):
                self._flush_thinking(agent_id)
            # Tool payloads are described, not quoted — see `_elide`.
            policy = _elide if etype in ("tool_call", "tool_result") else _cap
            self._log.write(etype, **{k: policy(v) for k, v in data.items()})
        except Exception:  # noqa: BLE001 — tracing must never break a run
            logger.warning("RunTrace.observe failed for %r", event.get("type"))

    # ── Flush ─────────────────────────────────────────────────────────────────

    def _flush_output(self) -> None:
        agent_id, text = self._out_agent, "".join(self._out)
        self._out_agent, self._out = None, []
        if text:
            self._log.write("agent_output", agent_id=agent_id, text=_cap(text), chars=len(text))

    def _flush_thinking(self, agent_id: str) -> None:
        text = "".join(self._thinking.pop(agent_id, []))
        if text:
            self._log.write(
                "agent_thinking", agent_id=agent_id, thinking=_cap(text), chars=len(text)
            )

    def flush(self) -> None:
        """Write everything still buffered — called when the run ends, however it
        ends, so a cancelled or failed run still leaves its last output and the
        reasoning of the step it died in."""
        self._flush_output()
        for agent_id in list(self._thinking):
            self._flush_thinking(agent_id)
