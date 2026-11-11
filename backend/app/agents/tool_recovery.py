"""app/agents/tool_recovery.py — make a failed tool call recoverable.

Before this, a failed tool call went nowhere useful. The Playwright tools return error
TEXT and never raise (ADR-0036), so the framework saw a normal result: nothing retried
it, and nothing told the model it had failed. Run 725474ee shows the effect: after
``navigate('prototype.html?r=3')`` failed with ``ERR_FILE_NOT_FOUND`` the tester carried
on against the old page and never looked at why. A tool that RAISES was worse: LangGraph's
default handler re-raises it, which ended the whole step.

``ToolFailureRecoveryMiddleware`` wraps every tool call of one agent run and does three
things, each bounded:

1. **Recognises the failure.** A raised exception, a ``ToolMessage`` with ``status ==
   "error"`` (every deepagents filesystem tool), or a Playwright failure string
   (``tools.playwright.is_failure``).
2. **Retries what an identical repeat can fix.** Only a transient fault (a dropped browser
   connection, a closed target) on an idempotent tool, at most ``_MAX_AUTO_RETRIES`` times
   with a short backoff. A timeout, a missing file or a script error is deterministic, so
   repeating it unchanged is not tried.
3. **Tells the model what to do differently.** The failure text is kept, and a note names
   the cause class and the change that fixes it (a stale ref needs a fresh snapshot, a
   missing path needs ``ls``, a script syntax error needs the IIFE form). The note
   escalates when the same call fails again, so the model cannot loop on it.

Control flow is never swallowed: LangGraph interrupts (``GraphBubbleUp``), the kernel's
``BudgetExceeded`` and task cancellation (``CancelledError`` is a ``BaseException``) pass
through untouched.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp

from agents.execution_engine.budget import BudgetExceeded
from app.agents.tools.playwright import is_failure as _is_playwright_failure

if TYPE_CHECKING:
    from langgraph.prebuilt.tool_node import ToolCallRequest

logger = logging.getLogger(__name__)

#: Identical-repeat retries for a transient fault on an idempotent tool.
_MAX_AUTO_RETRIES = 2
#: Seconds before auto-retry ``n`` is ``_RETRY_BACKOFF_SECONDS * n``.
_RETRY_BACKOFF_SECONDS = 1.0
#: Same call, same arguments, failed this many times: say so.
_REPEAT_NOTE_AT = 2
#: ...and tell the model to stop and finish without it.
_STOP_AT = 3
#: This many failures of one tool in a row (any arguments): treat the tool as unavailable.
_STREAK_AT = 4
#: Longest exception text put into a ToolMessage.
_MAX_ERROR_CHARS = 1500

#: Tools whose identical repeat has no side effect, so an automatic retry is safe.
#: ``playwright_evaluate``, ``click`` and ``type`` are NOT here: a repeat could run a
#: script or an action twice.
_IDEMPOTENT_TOOLS = frozenset(
    {"playwright_navigate", "playwright_snapshot", "read_file", "ls", "glob", "grep"}
)

#: Never converted into a tool message: they are how the run is steered, not tool faults.
_PASSTHROUGH_EXCEPTIONS: tuple[type[BaseException], ...] = (
    GraphBubbleUp,
    BudgetExceeded,
)


@dataclass(frozen=True)
class ToolFailure:
    """What kind of failure this is and what the model should change."""

    kind: str
    advice: str
    transient: bool = False


# ── Classification ────────────────────────────────────────────────────────────
# Ordered: the first rule whose pattern is found in the (lower-cased) text wins.

_Rule = tuple["re.Pattern[str]", ToolFailure]


def _rules(*rows: tuple[str, str, str, bool]) -> tuple[_Rule, ...]:
    return tuple(
        (re.compile(pattern, re.DOTALL), ToolFailure(kind, advice, transient))
        for pattern, kind, advice, transient in rows
    )


_BROWSER_RULES = _rules(
    (
        r"^(browser unavailable|no run sandbox is bound|cannot extract run_id)",
        "environment",
        "The browser cannot run in this environment, and repeating the call will not "
        "change that. Do not call any playwright_* tool again. Verify by other means "
        "(read the file, grep for the ids and handlers) and state in your reply exactly "
        "what you could not check in a browser.",
        False,
    ),
    (
        r"^refused:",
        "policy",
        "The URL was refused by the browser policy named above. Open a workspace file "
        "by its relative path with no leading slash (playwright_navigate('prototype.html')) "
        "or use a localhost URL.",
        False,
    ),
    (
        r"^no page loaded",
        "state",
        "No page is open. Call playwright_navigate first, for example "
        "playwright_navigate('prototype.html'), then repeat this call.",
        False,
    ),
    (
        r"^reference \S+ is (stale|invalid)",
        "state",
        "That ref belongs to an earlier page. Call playwright_snapshot for fresh refs and "
        "use one of them, or act by id with playwright_evaluate "
        "(document.getElementById('<id>').click()), which needs no ref.",
        False,
    ),
    (
        r"err_file_not_found|enoent|no such file",
        "argument",
        "That path does not exist in the workspace. List the folder with ls or glob to "
        "find the real file name, then pass it relative to the workspace root with no "
        "leading slash. Do not add a query string to a file path.",
        False,
    ),
    (
        r"err_connection_(reset|closed)|err_network_changed|err_empty_response"
        r"|target (page, context or browser has been )?closed|browser has been closed"
        r"|execution context was destroyed|^failed to create page",
        "transient",
        "The browser connection dropped during the call. If it still fails after the "
        "automatic retries, call playwright_navigate again to reopen the page, then "
        "repeat this call.",
        True,
    ),
    (
        # Match the cause, not the prefix: "navigation timeout or failed:" is the prefix of
        # EVERY navigation failure, so only Playwright's own timeout wording counts.
        r"^navigation .*(timeout \d+ms exceeded|err_timed_out|timed out)",
        "timeout",
        "The page did not finish loading within 30 s, and an identical repeat will time "
        "out again. Usually the file waits on an external resource (an http:// script, "
        "font or image). grep the file for 'http://' and 'https://', remove or inline "
        "those, then navigate again.",
        False,
    ),
    (
        r"^evaluate (error|failed).*syntaxerror",
        "script",
        "The script has a JavaScript syntax error. playwright_evaluate takes ONE "
        "expression: wrap statements in an arrow function that is called at once, "
        "(() => { ...; return value })(). A bare return outside a function is illegal. "
        "Fix the script and send it again.",
        False,
    ),
    (
        r"^evaluate (error|failed)",
        "script",
        "The script threw inside the page. Read the message, check that the element or "
        "variable it uses exists (query the DOM first with a smaller script), and change "
        "the script before sending it again.",
        False,
    ),
    (
        r"^(click|type) (failed|error)",
        "state",
        "The element could not be acted on (hidden, covered, disabled or detached). Take "
        "a fresh playwright_snapshot, or act by id with playwright_evaluate and then "
        "measure the result.",
        False,
    ),
    (
        r"^text not found within",
        "state",
        "The text never appeared. Take a playwright_snapshot to see what is on screen and "
        "wait for text that is really there, or measure with playwright_evaluate instead "
        "of waiting.",
        False,
    ),
    (
        r"^(element screenshot|page screenshot|screenshot|failed to create screenshot|filename escapes)",
        "argument",
        "Save screenshots to a workspace-relative path such as .verify/final-1.png. A "
        "screenshot is optional evidence: if it keeps failing, continue without it and "
        "say so in your reply.",
        False,
    ),
    (
        r"^specify either text to wait for",
        "argument",
        "Pass either text to wait for or duration_ms greater than 0.",
        False,
    ),
    (
        r".*",
        "browser",
        "Read the message, work out which argument or page state caused it, and change "
        "it before calling again. playwright_snapshot shows the current page.",
        False,
    ),
)

_GENERIC_RULES = _rules(
    (
        r"error invoking tool|validation error|field required|input should be|extra inputs"
        r"|missing \d+ required|unexpected keyword",
        "argument",
        "The arguments did not match the tool's schema. Check the required argument names "
        "and types, then call again.",
        False,
    ),
    (
        r"permission denied|read-only|not permitted|not allowed|path traversal|reserved",
        "policy",
        "This path or action is not permitted for this step. Do not retry it. Use an "
        "allowed location, or finish without it and say what you could not do.",
        False,
    ),
    (
        r"already exists",
        "state",
        "The file already exists and write_file never overwrites. Change it with edit_file "
        "(exact old_string), or write to a new file name.",
        False,
    ),
    (
        r"string not found|appears \d+ times|old_string|not unique",
        "argument",
        "old_string must match the file exactly and be unique. Read the exact lines with "
        "read_file (offset and limit) or grep, copy the text verbatim, add surrounding "
        "lines until it is unique (or set replace_all), then edit again.",
        False,
    ),
    (
        r"not found|no such file|does not exist|enoent|is a directory|exceeds file length",
        "argument",
        "That path or line range does not exist. Use ls or glob to find the real path "
        "(paths are absolute from the workspace root, for example /build/plan.md), then "
        "repeat with the corrected value.",
        False,
    ),
    (
        r"timed out|timeout",
        "timeout",
        "The call took too long. Narrow the pattern or the path and try again.",
        False,
    ),
    (
        r".*",
        "error",
        "Read the error, work out the cause, and change the arguments or the approach "
        "before calling again.",
        False,
    ),
)


def _first_match(rules: tuple[_Rule, ...], text: str) -> ToolFailure:
    haystack = text.lstrip().lower()[:2000]
    for pattern, failure in rules:
        if pattern.search(haystack):
            return failure
    return rules[-1][1]


def classify_text(tool_name: str, text: str) -> ToolFailure:
    """Classify a failure that came back as text."""
    rules = _BROWSER_RULES if tool_name.startswith("playwright_") else _GENERIC_RULES
    return _first_match(rules, text)


def classify_exception(exc: Exception) -> ToolFailure:
    """Classify a failure that was raised."""
    name = type(exc).__name__
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ToolFailure(
            "transient",
            f"The tool raised {name}: {_clip(str(exc))}. It may succeed if repeated.",
            True,
        )
    return ToolFailure(
        "exception",
        f"The tool raised {name}: {_clip(str(exc))}. Check the arguments and the state it "
        "depends on, and change the approach before calling again.",
        False,
    )


def _clip(text: str) -> str:
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS] + "..."


# ── Message helpers ───────────────────────────────────────────────────────────


def _text_of(message: ToolMessage) -> str:
    """The text of a tool message (media blocks and non-text content are ignored)."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
            if isinstance(block, str)
            or (isinstance(block, dict) and block.get("type") == "text")
        )
    return ""


def _annotated(message: ToolMessage, note: str) -> ToolMessage:
    """``message`` with ``note`` appended, marked as an error."""
    content = message.content
    if isinstance(content, list):
        merged: str | list[Any] = [*content, {"type": "text", "text": note}]
    else:
        merged = f"{content}\n\n{note}"
    return message.model_copy(update={"content": merged, "status": "error"})


def _signature(name: str, args: Any) -> str:
    try:
        encoded = json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        encoded = repr(args)
    digest = hashlib.sha1(f"{name}\0{encoded}".encode(), usedforsecurity=False)
    return digest.hexdigest()[:16]


class _FailureLedger:
    """Consecutive-failure counts for one agent run (thread-safe: sync tools run in threads)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_call: dict[str, int] = {}
        self._by_tool: dict[str, int] = {}

    def failed(self, tool: str, signature: str) -> tuple[int, int]:
        """Record a failure; return (times this exact call failed, failures of this tool in a row)."""
        with self._lock:
            self._by_call[signature] = self._by_call.get(signature, 0) + 1
            self._by_tool[tool] = self._by_tool.get(tool, 0) + 1
            return self._by_call[signature], self._by_tool[tool]

    def succeeded(self, tool: str, signature: str) -> None:
        with self._lock:
            self._by_call.pop(signature, None)
            self._by_tool.pop(tool, None)


def _recovery_note(
    tool: str, failure: ToolFailure, *, same_call: int, streak: int, retried: int
) -> str:
    lines = [f"[tool recovery] {tool} failed ({failure.kind}). {failure.advice}"]
    if retried:
        lines.append(
            f"It was retried {retried} time(s) automatically and failed each time."
        )
    if same_call >= _REPEAT_NOTE_AT:
        lines.append(
            f"This exact call has now failed {same_call} times with the same arguments. "
            "Do not send it again unchanged."
        )
    if same_call >= _STOP_AT:
        lines.append(
            "Stop retrying it. Choose a different approach, or finish without it and state "
            "in your reply what you could not do or verify."
        )
    if streak >= _STREAK_AT:
        lines.append(
            f"{tool} has failed {streak} times in a row. Treat it as unavailable for the "
            "rest of this step unless you have clearly fixed the cause."
        )
    return "\n".join(lines)


class ToolFailureRecoveryMiddleware(AgentMiddleware[Any, Any, Any]):
    """Retry transient tool faults and tell the model how to recover from the rest.

    One instance serves one agent run, so its failure counts are per run. It must sit
    INSIDE the guard middleware (so a refusal that says "stop" is never rewritten into
    "try again") and OUTSIDE any observer that wants the raw exception.
    """

    def __init__(self, *, label: str = "?") -> None:
        super().__init__()
        self._label = label
        self._ledger = _FailureLedger()

    # ── shared logic ──────────────────────────────────────────────────────────

    def _assess(
        self, call: dict[str, Any], result: Any, raised: Exception | None
    ) -> tuple[ToolFailure | None, Any]:
        """Return (failure or None, the message to hand back if it is a failure)."""
        name = str(call.get("name", "?"))
        if raised is not None:
            message = ToolMessage(
                content=f"Error: {type(raised).__name__}: {_clip(str(raised))}",
                name=name,
                tool_call_id=call.get("id") or "",
                status="error",
            )
            return classify_exception(raised), message
        if not isinstance(result, ToolMessage):
            return None, result  # a Command (state update): not a tool result
        text = _text_of(result)
        if name.startswith("playwright_") and _is_playwright_failure(text):
            return classify_text(name, text), result
        if result.status == "error":
            return classify_text(name, text), result
        return None, result

    def _finish(
        self, call: dict[str, Any], message: Any, failure: ToolFailure, retried: int
    ) -> Any:
        name = str(call.get("name", "?"))
        signature = _signature(name, call.get("args"))
        same_call, streak = self._ledger.failed(name, signature)
        note = _recovery_note(
            name, failure, same_call=same_call, streak=streak, retried=retried
        )
        logger.warning(
            "tool failure: agent=%s tool=%s kind=%s same_call=%d streak=%d retried=%d",
            self._label,
            name,
            failure.kind,
            same_call,
            streak,
            retried,
        )
        return _annotated(message, note)

    def _may_retry(self, name: str, failure: ToolFailure, retried: int) -> bool:
        return (
            failure.transient
            and name in _IDEMPOTENT_TOOLS
            and retried < _MAX_AUTO_RETRIES
        )

    def _on_success(self, call: dict[str, Any]) -> None:
        name = str(call.get("name", "?"))
        self._ledger.succeeded(name, _signature(name, call.get("args")))

    # ── AgentMiddleware hooks ─────────────────────────────────────────────────

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        call = request.tool_call
        name = str(call.get("name", "?"))
        retried = 0
        while True:
            raised: Exception | None = None
            result: Any = None
            try:
                result = handler(request)
            except _PASSTHROUGH_EXCEPTIONS:
                raise
            except Exception as exc:  # noqa: BLE001 - converted to a message the model can act on
                raised = exc
            failure, message = self._assess(call, result, raised)
            if failure is None:
                self._on_success(call)
                return message
            if self._may_retry(name, failure, retried):
                retried += 1
                logger.info(
                    "tool retry: agent=%s tool=%s attempt=%d",
                    self._label,
                    name,
                    retried,
                )
                time.sleep(_RETRY_BACKOFF_SECONDS * retried)
                continue
            return self._finish(call, message, failure, retried)

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Callable):
        call = request.tool_call
        name = str(call.get("name", "?"))
        retried = 0
        while True:
            raised: Exception | None = None
            result: Any = None
            try:
                result = await handler(request)
            except _PASSTHROUGH_EXCEPTIONS:
                raise
            except Exception as exc:  # noqa: BLE001 - converted to a message the model can act on
                raised = exc
            failure, message = self._assess(call, result, raised)
            if failure is None:
                self._on_success(call)
                return message
            if self._may_retry(name, failure, retried):
                retried += 1
                logger.info(
                    "tool retry: agent=%s tool=%s attempt=%d",
                    self._label,
                    name,
                    retried,
                )
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * retried)
                continue
            return self._finish(call, message, failure, retried)
