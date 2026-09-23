"""agents/capabilities/gates/conditional.py — the ``conditional`` gate (spec 014 / R-05b / §9).

Makes a declared ``gates: [conditional]`` step a branch point (spec 014's in-workflow
branching + cross-workflow triggering). At such a step it:

  1. resolves the DECISION SOURCE — ``route.condition_agent`` (default: this step's own
     id) — and reads its ``route_decision`` typed artifact via the SAME typed-graph read
     every inter-agent context routing uses (``ctx.runner.latest_typed_content``, the
     public handle over the engine's ``_latest_typed_content``, R-05b);
  2. ``json.loads``es the content and extracts ``parsed["decision"]``; malformed JSON, a
     non-object payload, or a missing ``"decision"`` key is treated as "no match" — NEVER
     a crash (the manifest-route-schema.md runtime contract, step 7);
  3. matches the decision value against ``route.outcomes`` keys:
       * a match returns the ``GATE_ROUTE`` outcome, carrying the matched
         ``{"trigger": ..., "target": ...}`` verbatim in ``detail`` — the dispatch-loop
         cursor jump this gate exists to drive (Phase 3, not this file's concern);
       * no match, ``route.default_next`` set → ``GATE_PASS`` (the engine advances
         normally, no special routing — the SAME outcome every non-branching step emits);
       * no match, ``route.default_next`` unset → the run has NOWHERE TO GO. This reuses
         the EXISTING ``GATE_BLOCK`` outcome + ``gate_blocked`` event shape
         (validation.py/security.py's block path) rather than inventing a new outcome —
         R-13's stop-and-hand-off is the same "nowhere to go" shape a blocking gate
         already produces.

Pure data-in dispatch: this gate makes no dispatch-loop decisions itself (INV-5) — it only
resolves and reports WHICH outcome applies. The engine's dispatch-loop cursor jump on a
``GATE_ROUTE`` outcome is Phase 3 work, wired elsewhere.

Import purity (import-linter): registry decorator + the gate-outcome contract + the shared
``write_gate_event`` helper only; the typed-artifact read is reached through ``ctx.runner``
— NO kernel/app import.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.capabilities.gates.base import GATE_BLOCK, GATE_PASS, GATE_ROUTE, GateOutcome
from agents.capabilities.gates.write import write_gate_event
from agents.capabilities.registry import register

logger = logging.getLogger(__name__)



def _trailing_json_object(content: str) -> dict | None:
    """Return the JSON object a reply ENDS with, or ``None``.

    A decision agent's artifact is its whole streamed reply, so a tool-using step
    reasons in prose and only then commits to its answer. The strict
    ``json.loads`` of the whole string fails for every such reply and the gate
    reads "no decision" — the route is skipped and the run silently takes
    ``default_next`` as though the agent never spoke. Observed live: a Coverage
    Check returned ``{"decision": "incomplete"}`` after ~4KB of analysis and was
    ignored, so the run continued on a synthesis its own checker had rejected.

    STRICTLY the trailing object. Content after the closing brace (other than
    whitespace or a closing code fence) means the model kept talking past its
    answer, and recovering a decision from THAT shape was considered and
    deliberately rejected — see
    ``test_unparseable_decision_ends_the_run_instead_of_falling_through``, whose
    ``{"decision": "english"}Hello! How can I help you today?`` must keep failing
    closed. Prose-then-JSON is a model that finished deciding; JSON-then-prose is
    a model that did not, and only the first is recovered here.
    """
    if not isinstance(content, str):
        return None
    tail = content.rstrip()
    # Allow a fenced answer (```json ... ```) — strip only the closing fence.
    if tail.endswith("```"):
        tail = tail[: -len("```")].rstrip()
    if not tail.endswith("}"):
        return None

    close = len(tail) - 1
    depth = 0
    in_string = False
    for i in range(close, -1, -1):
        ch = tail[i]
        if in_string:
            # Walking backwards, a quote closes the string only when it is not
            # itself escaped (an ODD run of preceding backslashes escapes it).
            if ch == '"':
                back = i - 1
                slashes = 0
                while back >= 0 and tail[back] == "\\":
                    slashes += 1
                    back -= 1
                if slashes % 2 == 0:
                    in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(tail[i : close + 1])
                except (TypeError, ValueError):
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


@register(
    "gate",
    "conditional",
    user_allowed=True,
    description="Branch the run to a declared step or trigger another workflow based on a step's typed decision.",
)
class ConditionalGate:
    """Resolves a step's routing decision and reports pass/route/block (``name='conditional'``).

    Satisfies the ``GateHandler`` port structurally (``name`` + ``async evaluate``).
    """

    name = "conditional"

    async def evaluate(self, step: Any, ctx: Any) -> GateOutcome:
        """Resolve the declared ``route`` against the decision source's typed artifact."""
        step_id = getattr(step, "agent_id", None) or "?"
        route = getattr(step, "route", None)

        condition_agent = getattr(route, "condition_agent", None) if route else None
        decision_source = condition_agent or step_id

        decision = self._read_decision(ctx, step_id, decision_source)

        outcomes = (getattr(route, "outcomes", None) or {}) if route else {}
        matched = None
        if decision is not None:
            try:
                matched = outcomes.get(decision)
            except TypeError:
                # An unhashable (but validly-JSON) decision value, e.g. a list — fail
                # closed to "no match" rather than crashing the gate (never raise).
                logger.warning(
                    "conditional gate: step %s got an unhashable decision value from %r",
                    step_id, decision_source,
                )
                matched = None

        # ── Match found → GATE_ROUTE (the dispatch-loop cursor jump, Phase 3) ──────
        if matched is not None:
            # Every OTHER trigger="step" outcome on this route is, by definition,
            # not being walked this pass — computed here (we already have
            # `outcomes` in scope) so the dispatch loop only has to resolve each
            # raw target string to a real ordered_agents id and yield, not also
            # re-scan `route.outcomes` itself (that scan belongs in exactly one
            # place).
            _skipped_targets = [
                v.target for v in outcomes.values()
                if v.trigger == "step" and v.target != matched.target
            ]
            detail = {
                "trigger": matched.trigger,
                "target": matched.target,
                "decision": decision,
                "skipped_targets": _skipped_targets,
                # R-28: authored retry guidance, carried so the dispatch loop can inject
                # it into the target's context AND so it is observable on the gate_events
                # row (a routed outcome emits no SSE event — that row is the only record).
                "feedback": matched.feedback,
            }
            _all_options = ", ".join(f"{k!r}->{v.target}" for k, v in outcomes.items())
            logger.info(
                "condition: step %s picked %r -> target=%s | declared options: %s",
                step_id, decision, matched.target, _all_options or "-",
            )
            await write_gate_event(ctx, step_id, "conditional", GATE_ROUTE, detail)
            return GateOutcome(outcome=GATE_ROUTE, detail=detail)

        default_next = getattr(route, "default_next", None) if route else None

        # ── No match, a fallback is declared → GATE_PASS (plain forward advance) ──
        if default_next:
            detail = {"decision": decision, "reason": "no matching route outcome"}
            await write_gate_event(ctx, step_id, "conditional", GATE_PASS, detail)
            return GateOutcome(outcome=GATE_PASS, detail=detail)

        # ── No match, no fallback → NOWHERE TO GO (R-13's stop-and-hand-off shape) ─
        # Reuses the SAME GATE_BLOCK outcome + gate_blocked event validation.py/
        # security.py already emit when a step cannot proceed — no new outcome shape.
        detail = {
            "decision": decision,
            "reason": "no matching route outcome and no default_next",
        }
        await write_gate_event(ctx, step_id, "conditional", GATE_BLOCK, detail)
        return GateOutcome(
            outcome=GATE_BLOCK,
            events=[
                {
                    "type": "gate_blocked",
                    "data": {
                        "step": step_id,
                        "gate": "conditional",
                        "reason": detail["reason"],
                    },
                }
            ],
            detail=detail,
        )

    def _read_decision(self, ctx: Any, step_id: str, decision_source: str) -> Any:
        """Read + parse the decision source's ``route_decision`` artifact (R-05b).

        Fail-closed per the runtime contract (manifest-route-schema.md step 7): a missing
        reader/artifact, malformed JSON, a non-object payload, or a missing ``"decision"``
        key all return ``None`` (treated as "no match" by the caller) — NEVER a crash. Each
        failure logs an observable line (the contract's "an observable event/log line
        should record this").
        """
        runner = getattr(ctx, "runner", None)
        reader = getattr(runner, "latest_typed_content", None)
        if reader is None:
            logger.warning(
                "conditional gate: step %s has no latest_typed_content reader available",
                step_id,
            )
            return None

        content = reader(decision_source)
        if not content:
            logger.info(
                "conditional gate: step %s found no route_decision artifact from %r",
                step_id, decision_source,
            )
            return None

        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            # The artifact is the decision agent's WHOLE streamed reply, not a bare
            # JSON document. A tool-using agent reasons in prose before it answers
            # ("Let me check coverage… ", tool call, more prose), so the strict
            # whole-string parse above fails for every such step and the gate then
            # reads "no decision" — the route is skipped and the run takes
            # default_next as though the agent never spoke. That is silent
            # mis-routing, not a safe failure: observed live on a Coverage Check
            # that correctly returned {"decision": "incomplete"} after ~4KB of
            # analysis and was ignored, so the run continued on a synthesis its own
            # checker had just rejected.
            #
            # Recover the trailing JSON object instead. LAST object, not the first:
            # a reply may quote the schema, or an earlier draft, before settling on
            # its answer, and the final one is the decision. Still fail-closed —
            # anything unparseable returns None exactly as before.
            parsed = _trailing_json_object(content)
            if parsed is None:
                logger.warning(
                    "conditional gate: step %s got malformed route_decision JSON from %r",
                    step_id, decision_source,
                )
                return None

        if not isinstance(parsed, dict) or "decision" not in parsed:
            logger.warning(
                "conditional gate: step %s route_decision from %r has no 'decision' key",
                step_id, decision_source,
            )
            return None

        return parsed["decision"]
