"""tests/agents/live_contract.py — Phase 8 contract validator + cost watcher (T2).

A reusable, **content-agnostic** validator + cost reporter over the T1 harness's
:class:`~tests.agents.live_harness.CaptureResult`. Live LLM text is
nondeterministic, so this module asserts the *structure* of a captured run — the
event vocabulary, ordering, required keys, terminal/error invariants, non-zero
token usage (opt-in), and **deliverable validity** (the prototype HTML renders;
code-gen has ``filename:`` blocks; chat has the 10-key ``FinalOutputModel``;
handoff has the ``pipeline_output`` shape) — **never** the exact words a model
produced.

────────────────────────────────────────────────────────────────────────────────
WHO CALLS THIS (and how)
────────────────────────────────────────────────────────────────────────────────
T3 (the live suite, ``test_phase8_live.py``) drives a real Bedrock run through a
T1 ``drive_*`` entry point, gets a ``CaptureResult`` back, and asserts it is
contract-faithful with::

    from tests.agents.live_contract import assert_capture, summarize_cost
    result = await drive_engine_pipeline("prototype", model=None)   # LIVE
    assert_capture(result, require_tokens=True)                     # raises on any failure
    print(summarize_cost(result))                                   # cost table

The same calls work OFFLINE against a scripted capture with
``require_tokens=False`` (a scripted pure-text run may report 0 tokens — see the
T1 NOTE), which is exactly what this module's own self-test
(``test_live_contract.py``) does — so the machinery is proven green with no creds.

────────────────────────────────────────────────────────────────────────────────
THE TWO ENTRY POINTS
────────────────────────────────────────────────────────────────────────────────
  * :func:`validate_capture` → ``list[str]`` of human-readable failures (empty =
    pass). Non-raising; good for collecting/printing every problem at once.
  * :func:`assert_capture` → raises :class:`CaptureContractError` carrying ALL
    failures if any. Strict gate for a test.

Plus the cost watcher:
  * :func:`summarize_cost` → a printable per-agent + cumulative token/cost table
    (Haiku pricing via ``live_harness.cost_usd``), for ONE or MANY captures.
  * :func:`assert_under_budget` → a soft ceiling (logs the table, raises
    :class:`BudgetExceededError` if the cumulative USD exceeds ``max_usd``).

────────────────────────────────────────────────────────────────────────────────
THE DELIVERABLE-VALIDITY REGISTRY (extensible, keyed off world+label)
────────────────────────────────────────────────────────────────────────────────
The "is this run's artifact valid?" rule differs per pipeline, so it is a small
registry (:data:`_ENGINE_DELIVERABLE_RULES`) mapping an engine ``label``
(``pipeline_type``) → a validity callable. Three rule kinds ship:

  * **prototype family** (``prototype`` / ``od_prototype`` / ``prototype_revision``):
    the deliverable's prototype HTML must pass :func:`app.agents.static_check`
    AND — when a browser is available — :func:`app.agents.render_check`. The HTML
    is extracted from the deliverable whether it is raw HTML or a ``filename:``
    bundle (the engine may serialize the whole sandbox when other files are
    present); see :func:`_extract_prototype_html`.
  * **code-gen family** (``app_builder`` / ``mulesoft_to_springboot`` /
    ``dotnet_to_azure`` + revisions): the deliverable must be non-empty and carry
    at least one ``filename:`` block marker (the format the UI FilesTab parses).
  * **text family** (``user_stories`` / ``ppt`` / … + the catch-all default): the
    deliverable must simply be non-empty.

Unknown engine labels fall back to the **text** rule (non-empty) rather than
failing — so a newly-registered pipeline is still validated for the common
contract (events + terminal + non-empty deliverable) without a code change here,
and a richer rule can be added to the registry when warranted.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Callable

from tests.agents.live_harness import CaptureResult, TokenTotals, cost_usd

logger = logging.getLogger("tests.agents.live_contract")


# ===========================================================================
# Errors raised by the strict helpers.
# ===========================================================================


class CaptureContractError(AssertionError):
    """Raised by :func:`assert_capture` when a capture violates the contract.

    Subclasses :class:`AssertionError` so it reads naturally in a test failure.
    The full list of failures is on :attr:`failures` and rendered in the message.
    """

    def __init__(self, failures: list[str], *, world: str = "", label: str = "") -> None:
        self.failures = list(failures)
        self.world = world
        self.label = label
        header = f"capture contract FAILED (world={world!r} label={label!r}) — {len(failures)} issue(s):"
        body = "\n".join(f"  - {f}" for f in failures)
        super().__init__(f"{header}\n{body}")


class BudgetExceededError(AssertionError):
    """Raised by :func:`assert_under_budget` when cumulative cost exceeds the ceiling."""

    def __init__(self, total_usd: float, max_usd: float, table: str) -> None:
        self.total_usd = total_usd
        self.max_usd = max_usd
        super().__init__(
            f"cost ${total_usd:.4f} exceeds soft ceiling ${max_usd:.4f}\n{table}"
        )


# ===========================================================================
# Per-world event vocabulary + required keys.
# ===========================================================================
#
# These are the SUPERSET of event types each world can legitimately emit. An
# event whose ``type`` is not in its world's set is flagged as UNKNOWN — a
# regression signal (a renamed/new event the validator + FE haven't accounted
# for). The sets are intentionally generous (every event the engine/chat/handoff
# generators yield today) so a faithful run never false-flags; only genuine drift
# trips it. Grounded against:
#   * engine — ``agents/execution_engine/engine.py`` (every ``yield {...}``),
#   * chat   — ``app/agents/chat_runner.py``,
#   * handoff— ``app/services/handoff_pipeline.py`` (frozen in
#              ``tests/integration/test_handoff_contract.py``).

# Engine outbound WS event vocabulary. Internal control sentinels
# (``_gate_rejected`` / ``_gate_edited``) are filtered by the websocket layer and
# never reach the browser, but the engine MAY yield them; we accept (not flag)
# them so a gate-reject scenario doesn't read as "unknown type".
_ENGINE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "workflow_validated",
        "planner_start",
        "planner_timeout",
        "planner_complete",
        "gate_status",
        "pipeline_start",
        "agent_start",
        "agent_input",
        "agent_chunk",
        "tool_call",
        "tool_result",
        "task_progress",
        "task_loop_progress",
        "agent_complete",
        # Progressive-disclosure skills (spec 011): emitted once per step that
        # stages skills into the sandbox. This is a SECOND vocabulary list — the
        # other is `_DOCUMENTED_EVENT_TYPES` in test_phase3_cutover_verify.py.
        # 011 declared the event there but not here, so every engine-world
        # capture failed with "UNKNOWN event type 'agent_skills'" (40 tests).
        "agent_skills",
        "review_gate_ready",
        "review_gate_approved",
        # Clarify (Human_Gate) — emitted by ClarifyEngine when the planner returns
        # CLARIFY_REQUIRED (a live run; the harness auto-answers questionnaire_ready).
        "questionnaire_ready",
        "questionnaire_complete",
        "clarification_limit_reached",
        "pipeline_complete",
        "pipeline_cancelled",
        "agent_error",
        "error",
        # internal control sentinels (stripped by the WS layer; accepted here)
        "_gate_rejected",
        "_gate_edited",
    }
)

_CHAT_EVENT_TYPES: frozenset[str] = frozenset(
    {"phase_start", "stream", "phase_end", "error", "complete"}
)

_HANDOFF_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "phase_start",
        "phase_end",
        "agent_thinking",
        "agent_complete",
        "agent_error",
        "pr_created",
        "pipeline_complete",
        # the pipeline may also surface a top-level handoff_error envelope
        "handoff_error",
    }
)

# Required keys on EVERY event of a world (the envelope contract). Engine events
# are ``{"type","data"}`` (the websocket drainer forwards exactly these); chat +
# handoff share the WS envelope ``{"type","chunk","section","data"}``.
_ENGINE_REQUIRED_KEYS: frozenset[str] = frozenset({"type", "data"})
_WS_ENVELOPE_KEYS: frozenset[str] = frozenset({"type", "chunk", "section", "data"})

# The terminal event type per world (must appear unless the run errored).
_TERMINAL_TYPE: dict[str, str] = {
    "engine": "pipeline_complete",
    "chat": "complete",
    "handoff": "pipeline_complete",
}

# Error event types per world (their presence relaxes the "terminal required" rule).
_ERROR_TYPES: dict[str, frozenset[str]] = {
    "engine": frozenset({"error", "agent_error"}),
    "chat": frozenset({"error"}),
    "handoff": frozenset({"agent_error", "handoff_error"}),
}

# The exact 10 keys of the chat FinalOutputModel (app/models/schemas.py).
_CHAT_FINAL_OUTPUT_KEYS: frozenset[str] = frozenset(
    {
        "auth",
        "realtime",
        "dashboard",
        "discovery",
        "requirements",
        "user_stories",
        "ppt",
        "prototype",
        "ui_design",
        "ui_preview",
    }
)

# Keys ALWAYS present on a handoff ``pipeline_output`` (both coding + test modes),
# grounded in test_handoff_contract.py's GOLDEN_PIPELINE_OUTPUT_*.
_HANDOFF_OUTPUT_COMMON_KEYS: frozenset[str] = frozenset(
    {
        "handoff_id",
        "started_at",
        "branch_name",
        "edit_results",
        "base_branch",
        "default_branch",
        "resolved_mode",
        "test_report",
        "compliance_report",
        "completed_at",
    }
)
# Extra keys present ONLY when coding mode reached the PR branch.
_HANDOFF_OUTPUT_CODING_KEYS: frozenset[str] = frozenset(
    {"coding_summary", "pr_url", "pr_number"}
)


# ===========================================================================
# Deliverable extraction helpers (content-agnostic).
# ===========================================================================

# A ``filename:`` block header as emitted by serialize_sandbox_deliverable():
#   ```filename: {relpath}
#   {content}
#   ```
_FILENAME_BLOCK_RE = re.compile(
    r"```filename:\s*(?P<path>[^\n]+)\n(?P<body>.*?)\n```",
    re.DOTALL,
)
# The sentinel serialize_sandbox_deliverable() returns for an empty sandbox.
_EMPTY_DELIVERABLE_SENTINEL = "(no files written)"


def _parse_filename_blocks(deliverable: str) -> dict[str, str]:
    """Return ``{relpath: content}`` for every ``filename:`` block in *deliverable*.

    Empty dict when the string is not a ``filename:`` bundle (e.g. it's raw HTML).
    """
    blocks: dict[str, str] = {}
    for m in _FILENAME_BLOCK_RE.finditer(deliverable or ""):
        blocks[m.group("path").strip()] = m.group("body")
    return blocks


def _looks_like_html(text: str) -> bool:
    """Heuristic: the string is (starts as) an HTML document, not a bundle/JSON."""
    head = (text or "").lstrip()[:256].lower()
    return head.startswith("<!doctype") or head.startswith("<html") or "<body" in head


def _extract_prototype_html(deliverable: str) -> str | None:
    """Pull the prototype HTML out of an engine deliverable string.

    The engine yields the prototype deliverable in one of two shapes:
      * **raw HTML** — the common case (prototype / od_prototype / revision: the
        engine reads ``prototype.html`` back directly), OR
      * a **``filename:`` bundle** — when the sandbox also holds other files
        (e.g. the offline scripted build leaves ``spec.md`` / ``design.md`` /
        ``tasks.md`` so ``serialize_sandbox_deliverable`` wraps everything). In
        that case the prototype is the ``prototype.html`` block.

    Returns the HTML string, or ``None`` if no prototype HTML can be found.
    """
    if not deliverable:
        return None
    blocks = _parse_filename_blocks(deliverable)
    if blocks:
        # Prefer an explicit prototype.html / index.html block.
        for key in ("prototype.html", "index.html"):
            if key in blocks:
                return blocks[key]
        # Otherwise the first HTML-looking block.
        for content in blocks.values():
            if _looks_like_html(content):
                return content
        return None
    # Not a bundle — treat as raw HTML if it looks like a document.
    if _looks_like_html(deliverable) or "<section" in deliverable.lower():
        return deliverable
    return None


# ===========================================================================
# Deliverable-validity registry — keyed off the engine label (pipeline_type).
# ===========================================================================
#
# Each rule is ``(deliverable: str | None, *, allow_render: bool) -> list[str]``
# returning failures (empty = valid). The registry maps a pipeline_type to its
# rule; unknown types fall back to the non-empty "text" rule (see
# ``_deliverable_rule_for``). This keeps validity extensible without touching the
# core validator.

DeliverableRule = Callable[..., list[str]]


def _rule_text_nonempty(deliverable: str | None, *, allow_render: bool = True) -> list[str]:
    """Validity for text/markup pipelines: the deliverable is simply non-empty."""
    if deliverable is None:
        return ["deliverable is None (run did not complete or produced no output)"]
    if not str(deliverable).strip():
        return ["deliverable is empty"]
    if str(deliverable).strip() == _EMPTY_DELIVERABLE_SENTINEL:
        return [f"deliverable is the empty-sandbox sentinel {_EMPTY_DELIVERABLE_SENTINEL!r}"]
    return []


def _rule_codegen_filename_blocks(
    deliverable: str | None, *, allow_render: bool = True
) -> list[str]:
    """Validity for code-gen pipelines: non-empty + ≥1 ``filename:`` block marker.

    The UI FilesTab / AppBuilderPreview parse the deliverable as a sequence of
    ```` ```filename: <path> ```` blocks, so a code-gen run that wrote files must
    serialize to at least one such block. (A run that wrote NOTHING degrades to
    the sentinel / last-agent text — flagged here as no blocks.)
    """
    failures = _rule_text_nonempty(deliverable)
    if failures:
        return failures
    blocks = _parse_filename_blocks(deliverable or "")
    if not blocks:
        return [
            "code-gen deliverable has no ```filename: ...``` block "
            "(expected serialized sandbox files)"
        ]
    # Every block should have a path and (typically) some content; flag obviously
    # broken (path-less) blocks defensively — the regex already requires a path,
    # so this is a belt-and-braces non-empty-path check.
    bad = [p for p in blocks if not p.strip()]
    if bad:
        return [f"code-gen deliverable has {len(bad)} filename block(s) with an empty path"]
    return []


def _rule_prototype_html(
    deliverable: str | None, *, allow_render: bool = True
) -> list[str]:
    """Validity for the prototype family: the HTML passes static_check (+ render).

    Extracts the prototype HTML (raw or from a ``filename:`` bundle), runs the
    stdlib :func:`static_check`, and — when ``allow_render`` and a browser is
    available — the headless :func:`render_check`. A render where the browser is
    unavailable is treated as SKIPPED (``available=False``), never a failure
    (mirrors render_check's own graceful-skip contract).
    """
    from app.agents.static_check import static_check

    failures = _rule_text_nonempty(deliverable)
    if failures:
        return failures

    html = _extract_prototype_html(deliverable or "")
    if html is None:
        return [
            "could not extract prototype HTML from the deliverable "
            "(neither raw HTML nor a prototype.html filename-block)"
        ]

    # --- static structural check (no browser) -------------------------------
    sc = static_check(html)
    if not sc.ok:
        return [f"static_check FAILED: {sc.summary()} :: {'; '.join(sc.issues)}"]

    # --- headless render check (graceful skip if no browser) ----------------
    if allow_render:
        rc = _run_render_check(html)
        if rc is not None and rc.available and not rc.ok:
            return [f"render_check FAILED: {rc.summary()}"]
        if rc is not None and not rc.available:
            logger.info("render_check skipped (browser unavailable): %s", rc.note)

    return []


def _run_render_check(html: str):
    """Run the async :func:`render_check` on *html* synchronously; ``None`` on error.

    Writes the HTML to a temp file (render_check takes a path), then drives the
    coroutine. Handles being called both with and without a running event loop:
    if a loop is already running (e.g. inside an async test that called the sync
    validator) the render is run in a fresh loop on a worker thread so we never
    ``await`` from sync code on the live loop. Any harness/browser error degrades
    to ``None`` (treated as skip), never a hard failure.
    """
    import os
    import tempfile

    from app.agents.render_check import RenderResult, render_check

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="live-contract-render-", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(html)

        async def _go() -> RenderResult:
            return await render_check(tmp_path)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to drive directly.
            return asyncio.run(_go())
        # A loop is already running on THIS thread: run the coroutine to
        # completion on a separate thread with its own loop.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_go())).result()
    except Exception as exc:  # noqa: BLE001 — render is best-effort; skip on any error
        logger.warning("live_contract: render_check harness error (%s) — skipping", exc)
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# pipeline_type → deliverable-validity rule. Unknown → text/non-empty (see
# _deliverable_rule_for). Revisions reuse their base pipeline's rule.
_ENGINE_DELIVERABLE_RULES: dict[str, DeliverableRule] = {
    # prototype family — HTML must render
    "prototype": _rule_prototype_html,
    "od_prototype": _rule_prototype_html,
    "prototype_revision": _rule_prototype_html,
    # code-gen family — filename: blocks
    "app_builder": _rule_codegen_filename_blocks,
    "app_builder_revision": _rule_codegen_filename_blocks,
    "mulesoft_to_springboot": _rule_codegen_filename_blocks,
    "mulesoft_to_springboot_revision": _rule_codegen_filename_blocks,
    "dotnet_to_azure": _rule_codegen_filename_blocks,
    "dotnet_to_azure_revision": _rule_codegen_filename_blocks,
    # text/markup family — non-empty (explicit entries for clarity; the default
    # is the same rule, so adding/removing these never changes behavior)
    "user_stories": _rule_text_nonempty,
    "user_stories_revision": _rule_text_nonempty,
    "ppt": _rule_text_nonempty,
    "od_ppt": _rule_text_nonempty,
    "ppt_revision": _rule_text_nonempty,
    "od_ppt_revision": _rule_text_nonempty,
    "custom": _rule_text_nonempty,
}


def _deliverable_rule_for(label: str) -> DeliverableRule:
    """Resolve the deliverable-validity rule for an engine ``label`` (pipeline_type).

    Falls back to the non-empty text rule for an unregistered pipeline so a new
    pipeline is still validated for the common contract (and a richer rule can be
    registered later) instead of erroring or silently skipping.
    """
    return _ENGINE_DELIVERABLE_RULES.get(label, _rule_text_nonempty)


# ===========================================================================
# Common (world-agnostic) checks.
# ===========================================================================


def _check_events_nonempty(result: CaptureResult) -> list[str]:
    if not result.events:
        return ["no events captured (event stream is empty)"]
    return []


def _check_required_keys(result: CaptureResult, required: frozenset[str]) -> list[str]:
    """Every event must carry the world's required envelope keys."""
    failures: list[str] = []
    for i, ev in enumerate(result.events):
        if not isinstance(ev, dict):
            failures.append(f"event[{i}] is not a dict: {type(ev).__name__}")
            continue
        missing = required - set(ev.keys())
        if missing:
            failures.append(
                f"event[{i}] (type={ev.get('type')!r}) missing required key(s): "
                f"{sorted(missing)}"
            )
    return failures


def _check_known_vocabulary(
    result: CaptureResult, known: frozenset[str]
) -> list[str]:
    """Flag any event ``type`` not in the world's known vocabulary (regression)."""
    failures: list[str] = []
    seen_unknown: set[str] = set()
    for ev in result.events:
        etype = ev.get("type") if isinstance(ev, dict) else None
        if etype is None:
            failures.append("an event has no 'type'")
            continue
        if etype not in known and etype not in seen_unknown:
            seen_unknown.add(etype)
            failures.append(
                f"UNKNOWN event type {etype!r} — not in the {result.world} vocabulary "
                f"(possible contract regression)"
            )
    return failures


def _has_error(result: CaptureResult) -> bool:
    """True iff the capture reached an error terminal (error event or raised exc)."""
    err_types = _ERROR_TYPES.get(result.world, frozenset())
    if any(ev.get("type") in err_types for ev in result.events):
        return True
    return result.error is not None or result.raised is not None


def _check_terminal(result: CaptureResult) -> list[str]:
    """A terminal event must be present (and last) unless the run errored."""
    terminal = _TERMINAL_TYPE.get(result.world)
    if terminal is None:
        return [f"unknown world {result.world!r} (no terminal-event rule)"]

    types = result.event_types()
    errored = _has_error(result)

    if terminal not in types:
        if errored:
            return []  # an errored run legitimately has no terminal event
        return [f"missing terminal event {terminal!r} (and no error was captured)"]

    # Terminal present → must be unique and last (a healthy run ends on it).
    failures: list[str] = []
    if types.count(terminal) != 1:
        failures.append(
            f"terminal event {terminal!r} appears {types.count(terminal)} times (expected exactly 1)"
        )
    if types[-1] != terminal:
        failures.append(
            f"terminal event {terminal!r} is not last (last is {types[-1]!r})"
        )
    return failures


def _check_completed_flag(result: CaptureResult, *, require_completed: bool) -> list[str]:
    if require_completed and not result.completed:
        return [
            f"result.completed is False (error={result.error!r}, "
            f"last event={result.event_types()[-1] if result.events else None!r})"
        ]
    return []


def _check_tokens(result: CaptureResult, *, require_tokens: bool) -> list[str]:
    failures: list[str] = []
    t = result.tokens
    # Internal consistency: total == input + output (always assertable).
    if t.total != t.input + t.output:
        failures.append(
            f"token totals inconsistent: total={t.total} != input+output="
            f"{t.input + t.output}"
        )
    if require_tokens and t.total <= 0:
        failures.append(
            "tokens.total is 0 — a LIVE run must report non-zero usage "
            "(set require_tokens=False for scripted captures)"
        )
    return failures


# ===========================================================================
# Per-world structural / ordering checks.
# ===========================================================================


def _check_engine(result: CaptureResult, *, require_completed: bool) -> list[str]:
    """Engine-world ordering + deliverable validity."""
    failures: list[str] = []
    types = result.event_types()

    # ── Ordering: per-agent agent_start precedes that agent's agent_complete, and
    #    every agent_start is balanced by an agent_complete (no orphans). ───────
    open_agents: dict[str, int] = {}
    completed_agents: set[str] = set()
    for ev in result.events:
        etype = ev.get("type")
        data = ev.get("data") or {}
        aid = data.get("agent_id")
        if etype == "agent_start" and aid is not None:
            open_agents[aid] = open_agents.get(aid, 0) + 1
        elif etype == "agent_complete" and aid is not None:
            if aid not in open_agents or open_agents[aid] <= 0:
                failures.append(
                    f"agent_complete for {aid!r} with no preceding open agent_start"
                )
            else:
                open_agents[aid] -= 1
                completed_agents.add(aid)

    # Any agent that opened but never balanced (unless the run errored mid-agent).
    leftover = {a: n for a, n in open_agents.items() if n > 0}
    if leftover and not _has_error(result):
        failures.append(
            f"agent_start without a matching agent_complete: {sorted(leftover)}"
        )

    # Counts balance on a clean run.
    n_start = types.count("agent_start")
    n_complete = types.count("agent_complete")
    if not _has_error(result) and n_start != n_complete:
        failures.append(
            f"agent_start ({n_start}) != agent_complete ({n_complete}) on a non-errored run"
        )

    # ── task_progress, when present, must follow a report_task_complete tool ──
    #    flow (prototype build). Light check: a task_progress implies at least one
    #    tool_call for report_task_complete earlier. ───────────────────────────
    if "task_progress" in types:
        saw_rtc = any(
            ev.get("type") == "tool_call"
            and (ev.get("data") or {}).get("tool") == "report_task_complete"
            for ev in result.events
        )
        if not saw_rtc:
            failures.append(
                "task_progress emitted but no report_task_complete tool_call preceded it"
            )

    # ── Deliverable validity (registry keyed off the pipeline_type label). ────
    #    Only enforce on a run that was supposed to complete (and did, or we are
    #    requiring completion) — an errored/aborted run has no valid deliverable.
    if require_completed or result.completed:
        rule = _deliverable_rule_for(result.label)
        failures.extend(rule(result.deliverable))

    return failures


def _check_chat(result: CaptureResult, *, require_completed: bool) -> list[str]:
    """Chat-world ordering + the 10-key FinalOutputModel on the complete event."""
    failures: list[str] = []

    # ── Ordering: each phase_start is closed by a phase_end for the SAME section,
    #    and starts/ends balance (no nesting, no orphans). ─────────────────────
    open_section: str | None = None
    starts = 0
    ends = 0
    for ev in result.events:
        etype = ev.get("type")
        section = ev.get("section")
        if etype == "phase_start":
            starts += 1
            if open_section is not None:
                failures.append(
                    f"nested phase_start (section={section!r}) inside open "
                    f"phase {open_section!r}"
                )
            open_section = section
        elif etype == "phase_end":
            ends += 1
            if open_section is None:
                failures.append(f"phase_end (section={section!r}) with no open phase")
            elif open_section != section:
                failures.append(
                    f"phase_end section {section!r} != open phase {open_section!r}"
                )
                open_section = None
            else:
                open_section = None
    if open_section is not None:
        failures.append(f"unclosed chat phase (section={open_section!r})")
    if starts != ends:
        failures.append(f"phase_start ({starts}) != phase_end ({ends})")

    # ── stream events must carry chunk text; non-stream must not. ─────────────
    for i, ev in enumerate(result.events):
        if ev.get("type") == "stream":
            if not ev.get("chunk"):
                failures.append(f"chat stream event[{i}] has empty/None chunk")
        else:
            if ev.get("chunk") is not None:
                failures.append(
                    f"chat non-stream event[{i}] (type={ev.get('type')!r}) has a "
                    f"non-None chunk {ev.get('chunk')!r}"
                )

    # ── final_output: the exact 10-key FinalOutputModel, carried by `complete`. ─
    completes = result.events_of("complete")
    if completes:
        data = completes[-1].get("data")
        failures.extend(_validate_chat_final_output(data, where="complete event data"))
    # Also validate the mirrored CaptureResult.final_output when present.
    if result.final_output is not None:
        failures.extend(
            _validate_chat_final_output(result.final_output, where="result.final_output")
        )
    elif require_completed:
        failures.append("chat result.final_output is None (expected the 10-key dict)")

    return failures


def _validate_chat_final_output(data, *, where: str) -> list[str]:
    if not isinstance(data, dict):
        return [f"chat {where} is not a dict (got {type(data).__name__})"]
    keys = set(data.keys())
    if keys != set(_CHAT_FINAL_OUTPUT_KEYS):
        missing = _CHAT_FINAL_OUTPUT_KEYS - keys
        extra = keys - _CHAT_FINAL_OUTPUT_KEYS
        bits = []
        if missing:
            bits.append(f"missing={sorted(missing)}")
        if extra:
            bits.append(f"extra={sorted(extra)}")
        return [f"chat {where} key set != the 10 FinalOutputModel keys ({'; '.join(bits)})"]
    return []


def _check_handoff(result: CaptureResult, *, require_completed: bool) -> list[str]:
    """Handoff-world: pipeline_output shape + coding-emits-PR / test-omits-PR."""
    failures: list[str] = []

    # ── On a non-errored run the terminal pipeline_complete carries the
    #    pipeline_output dict. ─────────────────────────────────────────────────
    terminals = result.events_of("pipeline_complete")
    output = None
    if terminals:
        output = terminals[-1].get("data")
    elif result.final_output is not None:
        output = result.final_output

    if output is None:
        if not _has_error(result):
            failures.append("handoff produced no pipeline_output (and no error captured)")
        return failures

    if not isinstance(output, dict):
        return [f"handoff pipeline_output is not a dict (got {type(output).__name__})"]

    out_keys = set(output.keys())
    missing_common = _HANDOFF_OUTPUT_COMMON_KEYS - out_keys
    if missing_common:
        failures.append(
            f"handoff pipeline_output missing common key(s): {sorted(missing_common)}"
        )

    resolved_mode = output.get("resolved_mode")
    types = result.event_types()
    has_pr_event = "pr_created" in types

    if resolved_mode == "coding":
        # Coding mode → a PR was created: the event fired AND the output carries
        # the coding/PR keys.
        if not has_pr_event:
            failures.append("coding-mode handoff did not emit a pr_created event")
        missing_coding = _HANDOFF_OUTPUT_CODING_KEYS - out_keys
        if missing_coding:
            failures.append(
                f"coding-mode pipeline_output missing PR key(s): {sorted(missing_coding)}"
            )
        if not output.get("pr_url") or not output.get("pr_number"):
            failures.append("coding-mode pipeline_output has empty pr_url/pr_number")
    elif resolved_mode == "test":
        # Test mode → NO PR: no pr_created event, and the coding/PR keys are absent.
        if has_pr_event:
            failures.append("test-mode handoff emitted a pr_created event (should not)")
        present_coding = _HANDOFF_OUTPUT_CODING_KEYS & out_keys
        if present_coding:
            failures.append(
                f"test-mode pipeline_output carries coding/PR key(s) it should omit: "
                f"{sorted(present_coding)}"
            )
        if output.get("edit_results") != []:
            failures.append(
                f"test-mode pipeline_output edit_results should be [] "
                f"(got {output.get('edit_results')!r})"
            )
    else:
        failures.append(
            f"handoff resolved_mode is {resolved_mode!r} (expected 'coding' or 'test')"
        )

    # Every handoff event is the WS envelope with chunk=None (never token-streams).
    for i, ev in enumerate(result.events):
        if ev.get("chunk") is not None:
            failures.append(
                f"handoff event[{i}] (type={ev.get('type')!r}) has a non-None chunk "
                "(handoff never token-streams)"
            )

    return failures


# ===========================================================================
# Public validator API.
# ===========================================================================

_WORLD_VOCAB: dict[str, frozenset[str]] = {
    "engine": _ENGINE_EVENT_TYPES,
    "chat": _CHAT_EVENT_TYPES,
    "handoff": _HANDOFF_EVENT_TYPES,
}
_WORLD_REQUIRED_KEYS: dict[str, frozenset[str]] = {
    "engine": _ENGINE_REQUIRED_KEYS,
    "chat": _WS_ENVELOPE_KEYS,
    "handoff": _WS_ENVELOPE_KEYS,
}
_WORLD_CHECKER: dict[str, Callable[..., list[str]]] = {
    "engine": _check_engine,
    "chat": _check_chat,
    "handoff": _check_handoff,
}


def validate_capture(
    result: CaptureResult,
    *,
    require_tokens: bool = False,
    require_completed: bool = True,
) -> list[str]:
    """Validate a :class:`CaptureResult` content-agnostically; return failures.

    Returns a list of human-readable failure strings (EMPTY = the capture is
    contract-faithful). Never raises on a contract violation — use
    :func:`assert_capture` for the strict (raising) form.

    Applies, per world:

    **Common (all worlds)**
      * the event stream is non-empty;
      * every event carries the world's required envelope keys (engine:
        ``{type,data}``; chat/handoff: ``{type,chunk,section,data}``);
      * every event ``type`` is in the world's known vocabulary (an UNKNOWN type
        is flagged as a regression signal);
      * a terminal event is present + unique + last (engine/handoff
        ``pipeline_complete``; chat ``complete``) **unless** the run errored;
      * ``tokens.total == input + output`` always; and, if ``require_tokens``,
        ``tokens.total > 0`` (a LIVE-only assertion — scripted text runs may be 0);
      * if ``require_completed`` (default), ``result.completed`` is ``True``.

    **engine**
      * per-agent ``agent_start`` precedes that agent's ``agent_complete``, and
        starts/completes balance (no orphans) on a non-errored run;
      * ``task_progress`` (when present) is preceded by a ``report_task_complete``
        ``tool_call`` (the prototype build-loop signal);
      * **deliverable validity** via the ``(label →)`` rule registry — prototype
        family: HTML passes ``static_check`` (+ ``render_check`` when a browser is
        available); code-gen family: ≥1 ``filename:`` block; text family /
        unknown: non-empty.

    **chat**
      * each ``phase_start`` is closed by a ``phase_end`` for the same section,
        non-nested, balanced;
      * ``stream`` events carry chunk text, non-``stream`` events do not;
      * ``final_output`` (and the ``complete`` event's data) is the EXACT 10-key
        ``FinalOutputModel`` dict.

    **handoff**
      * the terminal ``pipeline_complete`` carries the ``pipeline_output`` dict
        with its documented common keys;
      * coding mode emits ``pr_created`` + carries ``coding_summary``/``pr_url``/
        ``pr_number``; test mode does NOT (and ``edit_results == []``);
      * every event's ``chunk`` is ``None`` (handoff never token-streams).

    Args:
        result: the capture to validate.
        require_tokens: assert ``tokens.total > 0`` (use on LIVE captures only).
        require_completed: assert ``result.completed`` and enforce deliverable
            validity (default True). Set False to validate a deliberately-aborted
            or error-path capture's structure without demanding completion.
    """
    failures: list[str] = []

    # World must be recognized before anything else.
    if result.world not in _WORLD_VOCAB:
        return [
            f"unknown capture world {result.world!r} "
            f"(expected one of {sorted(_WORLD_VOCAB)})"
        ]

    # ── Common checks ────────────────────────────────────────────────────────
    failures.extend(_check_events_nonempty(result))
    if not result.events:
        # Nothing else is meaningful without events.
        return failures

    failures.extend(_check_required_keys(result, _WORLD_REQUIRED_KEYS[result.world]))
    failures.extend(_check_known_vocabulary(result, _WORLD_VOCAB[result.world]))
    failures.extend(_check_terminal(result))
    failures.extend(_check_completed_flag(result, require_completed=require_completed))
    failures.extend(_check_tokens(result, require_tokens=require_tokens))

    # ── Per-world checks ─────────────────────────────────────────────────────
    checker = _WORLD_CHECKER[result.world]
    failures.extend(checker(result, require_completed=require_completed))

    return failures


def assert_capture(
    result: CaptureResult,
    *,
    require_tokens: bool = False,
    require_completed: bool = True,
) -> None:
    """Strict form of :func:`validate_capture` — raise on ANY failure.

    Runs :func:`validate_capture` with the same args; if it returns a non-empty
    failure list, raises :class:`CaptureContractError` carrying every failure (so
    a test surfaces all problems at once, not just the first). No-op on a clean
    capture.
    """
    failures = validate_capture(
        result, require_tokens=require_tokens, require_completed=require_completed
    )
    if failures:
        raise CaptureContractError(failures, world=result.world, label=result.label)


# ===========================================================================
# Cost watcher — per-agent + cumulative token/cost table.
# ===========================================================================


@dataclass
class _CostRow:
    """One row of the cost table (a single agent, or a capture's TOTAL)."""

    label: str
    input: int
    output: int

    @property
    def total(self) -> int:
        return self.input + self.output

    @property
    def usd(self) -> float:
        return cost_usd(TokenTotals(input=self.input, output=self.output, total=self.total))


def _as_results(result_or_results) -> list[CaptureResult]:
    """Normalize a single CaptureResult or an iterable of them to a list."""
    if isinstance(result_or_results, CaptureResult):
        return [result_or_results]
    return list(result_or_results)


def summarize_cost(result_or_results) -> str:
    """Return a printable per-agent + cumulative token/cost table (Haiku pricing).

    Accepts ONE :class:`CaptureResult` or an iterable of them (the live suite
    summarizes a whole sweep). For each capture it prints a section header
    (``world:label``) with one row per agent (from ``per_agent_tokens``) and a
    capture TOTAL (from ``tokens``); then a GRAND TOTAL across all captures. Costs
    use the shared :func:`tests.agents.live_harness.cost_usd` (Haiku 4.5:
    $0.25/M input, $1.25/M output), so the table reconciles with
    ``CaptureResult.cost_usd()``.

    Pure formatting — no assertions, safe to call on any capture (including a
    zero-token scripted run, which shows ``$0.0000``).
    """
    results = _as_results(result_or_results)

    # Column widths.
    name_w = max(
        [len("agent / capture")]
        + [len(f"{r.world}:{r.label}") for r in results]
        + [
            len(aid)
            for r in results
            for aid in r.per_agent_tokens
        ]
        + [len("TOTAL")],
        default=20,
    )
    name_w = max(name_w, 20)

    def _fmt_row(name: str, inp: int, out: int, total: int, usd: float, *, indent: str = "  ") -> str:
        return (
            f"{indent}{name:<{name_w}}  "
            f"{inp:>10,}  {out:>10,}  {total:>11,}  ${usd:>9.4f}"
        )

    def _hdr() -> str:
        return (
            f"  {'agent / capture':<{name_w}}  "
            f"{'input':>10}  {'output':>10}  {'total':>11}  {'cost USD':>10}"
        )

    lines: list[str] = []
    lines.append("=" * (name_w + 50))
    lines.append("Token / cost summary (Bedrock Haiku 4.5: $0.25/M in, $1.25/M out)")
    lines.append("=" * (name_w + 50))

    grand_in = grand_out = 0
    for r in results:
        lines.append("")
        lines.append(f"[{r.world}:{r.label}]"
                     + (f"  run_id={r.run_id}" if r.run_id else "")
                     + (f"  ({r.duration_s:.1f}s)" if r.duration_s else ""))
        lines.append(_hdr())
        lines.append("  " + "-" * (name_w + 48))
        # Per-agent rows (sorted for stable output).
        for aid in sorted(r.per_agent_tokens):
            t = r.per_agent_tokens[aid]
            row = _CostRow(aid, t.input, t.output)
            lines.append(_fmt_row(row.label, row.input, row.output, row.total, row.usd))
        # Capture TOTAL (authoritative — straight off CaptureResult.tokens).
        tot = _CostRow("TOTAL", r.tokens.input, r.tokens.output)
        lines.append("  " + "-" * (name_w + 48))
        lines.append(_fmt_row(tot.label, tot.input, tot.output, tot.total, tot.usd))
        grand_in += r.tokens.input
        grand_out += r.tokens.output

    grand = _CostRow("GRAND TOTAL", grand_in, grand_out)
    lines.append("")
    lines.append("=" * (name_w + 50))
    lines.append(_fmt_row(grand.label, grand.input, grand.output, grand.total, grand.usd, indent=""))
    lines.append(f"captures={len(results)}  grand cost=${grand.usd:.4f}")
    lines.append("=" * (name_w + 50))
    return "\n".join(lines)


def total_cost_usd(result_or_results) -> float:
    """Cumulative USD cost across one or many captures (Haiku pricing)."""
    return sum(r.cost_usd() for r in _as_results(result_or_results))


def assert_under_budget(
    results,
    max_usd: float,
    *,
    log: bool = True,
) -> float:
    """Soft cost ceiling: log the cost table, raise if cumulative USD > ``max_usd``.

    Returns the cumulative USD cost (so a caller can record it). Logs the full
    :func:`summarize_cost` table at INFO when ``log`` (the default) so a live run
    always leaves a cost trail, then raises :class:`BudgetExceededError` (with the
    table attached) iff the total exceeds ``max_usd``. A "soft" ceiling: it is a
    test-time guardrail against a runaway live sweep, not a hard runtime cap.

    Args:
        results: one :class:`CaptureResult` or an iterable of them.
        max_usd: the cumulative-cost ceiling in USD.
        log: emit the cost table at INFO (default True).
    """
    captures = _as_results(results)
    table = summarize_cost(captures)
    total = total_cost_usd(captures)
    if log:
        logger.info("cost watch (ceiling $%.4f):\n%s", max_usd, table)
    if total > max_usd:
        raise BudgetExceededError(total, max_usd, table)
    return total


__all__ = [
    "CaptureContractError",
    "BudgetExceededError",
    "validate_capture",
    "assert_capture",
    "summarize_cost",
    "total_cost_usd",
    "assert_under_budget",
]
