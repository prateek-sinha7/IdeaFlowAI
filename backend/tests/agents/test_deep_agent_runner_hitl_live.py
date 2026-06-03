"""tests/agents/test_deep_agent_runner_hitl_live.py — opt-in LIVE HITL smoke.

Proves the ``DeepAgentRunner`` (``app/agents/deep_agent_runner.py``) pause→resume
loop **end-to-end against real AWS Bedrock Haiku** — the same interrupt contract
the offline parity test (#28) verifies with a scripted fake model, now exercised
with a real model emitting a real tool call.

What it asserts (the Phase-1 HITL invariant, plan §"Phase 1"):
  1. A run armed with ``interrupt_on={tool_name: True}`` + a checkpointer PAUSES
     before the gated tool: ``astream_events`` emits a ``{"type":"gate", ...}``
     event whose payload's ``action_requests`` references the gated tool, and the
     run does **not** reach ``done`` (gate and done are mutually exclusive).
  2. ``Command(resume={"decisions":[{"type":"approve"}]})`` resumes the paused
     graph to a terminal state (``StateSnapshot.next == ()``) and the gated tool
     actually executes (a ``ToolMessage`` from the tool lands in final messages).

Opt-in / self-skipping — the default offline suite and credential-less CI stay
green. This test runs ONLY when BOTH hold:
  * env ``RUN_LIVE_BEDROCK=1`` is set (explicit opt-in), AND
  * AWS credentials actually resolve (SSO not expired) — probed via STS.
Otherwise it ``pytest.skip(...)``\\s with the exact command to run it live.

Run it live (creds via SSO):
    aws sso login --profile personal-sso
    RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso \\
        python3.11 -m pytest tests/agents/test_deep_agent_runner_hitl_live.py -v -s

Note on the model-tolerance loop: a chat model is non-deterministic — Haiku might
answer in plain text without calling the gated tool, in which case the run ends at
``done`` with no gate (correct behaviour, just nothing to prove). We therefore
retry the drive a few times with an increasingly forceful prompt; if no attempt
ever triggers the gate we ``pytest.xfail`` (model never called the tool) rather
than fail — the assertion under test is "the gate fires WHEN the model calls the
gated tool", which a no-call run cannot exercise.
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.deep_agent_runner import DeepAgentRunner

# Name of the single gated tool exercised by this smoke. Kept as a module
# constant so the tool definition, the interrupt_on map, and the assertions all
# reference the exact same string (a typo here would silently never gate).
GATED_TOOL = "report_task_complete"


# ---------------------------------------------------------------------------
# Skip gate — opt-in (RUN_LIVE_BEDROCK=1) AND credentials must actually resolve.
# ---------------------------------------------------------------------------

_RUN_LIVE_HINT = (
    "LIVE Bedrock HITL smoke is opt-in. To run it:\n"
    "    aws sso login --profile personal-sso\n"
    "    RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso "
    "python3.11 -m pytest tests/agents/test_deep_agent_runner_hitl_live.py -v -s"
)


def _aws_creds_resolve() -> tuple[bool, str]:
    """Return ``(ok, detail)`` — whether usable AWS credentials resolve right now.

    Probes ``sts.get_caller_identity()`` (cheap, no Bedrock charge). Catches the
    botocore credential/token errors raised when the SSO session is missing or
    expired so the test SKIPS cleanly with a helpful message rather than erroring
    deep inside a live model call. ``build_model()`` selects Bedrock only when no
    ``ANTHROPIC_API_KEY`` is set, so a usable STS identity is the right precondition
    for the Bedrock path; the rare local Anthropic-key dev box is handled below.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        from app.core.config import settings

        region = settings.AWS_REGION or os.getenv("AWS_REGION") or None
        ident = boto3.client("sts", region_name=region).get_caller_identity()
        return True, f"sts caller={ident.get('Arn', '<unknown>')}"
    except (BotoCoreError, ClientError) as exc:  # SSO expired / no creds / no token
        return False, f"AWS credentials did not resolve: {type(exc).__name__}: {exc}"
    except Exception as exc:  # pragma: no cover — defensive (e.g. boto3 missing)
        return False, f"AWS credential probe failed: {type(exc).__name__}: {exc}"


def _skip_reason() -> str | None:
    """Return a skip reason if the live smoke must not run, else ``None``."""
    if os.getenv("RUN_LIVE_BEDROCK") != "1":
        return f"RUN_LIVE_BEDROCK!=1 — live Bedrock HITL smoke is opt-in.\n{_RUN_LIVE_HINT}"

    # Opted in. If a local Anthropic key is configured, build_model() uses that
    # provider and no AWS creds are needed; otherwise require resolvable AWS creds.
    from app.core.config import settings

    if settings.ANTHROPIC_API_KEY:
        return None

    ok, detail = _aws_creds_resolve()
    if not ok:
        return f"{detail}\n{_RUN_LIVE_HINT}"
    return None


# Module-level gate: evaluated at collection so the whole module skips cleanly
# (rather than erroring) in a credential-less / CI environment. Keeping the
# default suite green is the point of the opt-in design.
pytestmark = pytest.mark.skipif(_skip_reason() is not None, reason=_skip_reason() or "")


# ---------------------------------------------------------------------------
# The gated tool + a helper to find the gate event in a drive.
# ---------------------------------------------------------------------------


@tool
def report_task_complete(summary: str) -> str:
    """Record that the task is complete with a one-line summary."""
    return f"recorded: {summary}"


def _gate_event(events: list[dict]) -> dict | None:
    """Return the first ``gate`` event in a drive's events, or ``None``."""
    return next((e for e in events if e.get("type") == "gate"), None)


# ---------------------------------------------------------------------------
# The test.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_bedrock_hitl_pause_then_resume() -> None:
    """Real Bedrock Haiku: gated tool call PAUSES the run; approve RESUMES it.

    Drives the exact same pause→resume loop tasks #24–#28 verified with a fake
    model, but with ``build_model()`` (Bedrock Haiku). Because the model is
    non-deterministic, the drive is retried with escalating prompts until the gate
    fires; if it never does (model answered in plain text every time) the test
    ``xfail``\\s — there is no gated tool call to prove a gate on.
    """
    from app.agents.model_factory import build_model

    # Escalating prompts — each retry leans harder on "call the tool" so a
    # reluctant model is nudged toward the tool-call turn that arms the gate.
    prompts = [
        "Summarize: the sky is blue. Then report task complete.",
        "Summarize 'the sky is blue' in one short line, then you MUST call the "
        "report_task_complete tool with that summary. Do not answer in plain text.",
        "Call the report_task_complete tool now with summary='the sky is blue'. "
        "Your only job is to invoke that tool — do not reply with prose.",
    ]

    gate_evt: dict | None = None
    saw_done_without_gate = False
    runner: DeepAgentRunner | None = None

    for attempt, prompt in enumerate(prompts, start=1):
        # Fresh runner + checkpointer + thread per attempt so a prior attempt's
        # persisted state can never leak into this one's gate detection.
        runner = DeepAgentRunner(
            system_prompt=(
                "You are a worker. Call report_task_complete with a one-line "
                "summary when done."
            ),
            tools=[report_task_complete],
            model=build_model(),
            checkpointer=InMemorySaver(),
            thread_id=f"hitl-smoke-{attempt}",
            interrupt_on={GATED_TOOL: True},
        )

        events: list[dict] = []
        async for event in runner.astream_events(prompt):
            events.append(event)

        gate_evt = _gate_event(events)
        types = [e.get("type") for e in events]
        print(f"\n[attempt {attempt}] event types: {types}")

        if gate_evt is not None:
            # Gate fired → the run paused. Assert it did NOT also reach done
            # (mutually exclusive per the adapter contract), then break to resume.
            assert "done" not in types, (
                "gate and done are mutually exclusive — a paused run must not also "
                f"emit done. Got event types: {types}"
            )
            print(f"[attempt {attempt}] GATE payload: {gate_evt['interrupt']}")
            break

        # No gate this attempt. If it cleanly finished, the model just didn't call
        # the gated tool — record that and try a more forceful prompt.
        if "done" in types:
            saw_done_without_gate = True
        elif "error" in types:
            err = next((e["error"] for e in events if e.get("type") == "error"), "")
            pytest.fail(f"live drive errored on attempt {attempt}: {err}")

    if gate_evt is None:
        # Every attempt finished without the model calling the gated tool. The
        # gate-fires-on-tool-call assertion can't be exercised — xfail, don't fail.
        assert saw_done_without_gate, (
            "expected at least one clean 'done' if the gate never fired; "
            "got no gate and no done either"
        )
        pytest.xfail(
            "Bedrock Haiku answered in plain text on every attempt and never "
            "called the gated tool, so no gate could fire (run reached 'done'). "
            "The pause→resume path is unexercised this run; re-run to retry."
        )

    assert runner is not None  # for type-checkers; set inside the loop on a gate

    # ── Validate the gate payload shape ───────────────────────────────────
    interrupt = gate_evt["interrupt"]
    assert gate_evt.get("thread_id") == runner.thread_id, (
        "gate event must carry the runner's thread_id for Phase-3 resume routing"
    )
    action_names = [req.get("name") for req in interrupt.get("action_requests", [])]
    assert GATED_TOOL in action_names, (
        f"gate payload must reference the gated tool {GATED_TOOL!r}; "
        f"action_requests names were {action_names}"
    )
    # interrupt_ids are the resume handles; at least one must be present so Phase 3
    # could target the pending interrupt. (We resume with a single value below.)
    assert interrupt.get("interrupt_ids"), (
        f"gate payload must carry interrupt_ids (resume handles); got {interrupt}"
    )
    # The graph must genuinely be paused (a node queued in `next`).
    assert interrupt.get("next"), f"a paused gate must report a non-empty next; got {interrupt}"

    # ── RESUME: approve the single pending action_request ──────────────────
    # Exactly ONE Decision per pending action_request (the middleware validates
    # the count). Our gate paused on a single report_task_complete call, so one
    # approve. ``Command(resume=<value>)`` resumes the one pending interrupt.
    n_actions = len(interrupt["action_requests"])
    resume_value = {"decisions": [{"type": "approve"}] * n_actions}
    await runner._graph.ainvoke(Command(resume=resume_value), runner.config)

    # ── Assert terminal + the gated tool actually executed ─────────────────
    final_state = await runner._graph.aget_state(runner.config)
    assert final_state.next == (), (
        f"resumed run must reach a terminal state (next == ()); got next={final_state.next!r}"
    )

    final_messages = final_state.values.get("messages", [])
    tool_messages = [
        m
        for m in final_messages
        if isinstance(m, ToolMessage) and getattr(m, "name", None) == GATED_TOOL
    ]
    assert tool_messages, (
        f"the approved gated tool {GATED_TOOL!r} must have executed after resume — "
        f"expected a ToolMessage from it in the final messages. "
        f"Final message types: {[type(m).__name__ for m in final_messages]}"
    )
    # Our tool returns "recorded: <summary>"; confirm the real tool body ran
    # (not a synthetic respond/reject message).
    tm = tool_messages[-1]
    print(f"[resume] terminal next={final_state.next!r}; "
          f"ToolMessage(name={tm.name!r}, content={tm.content!r})")
    assert str(tm.content).startswith("recorded:"), (
        f"the gated tool's real body must have run on approve (returns 'recorded: …'); "
        f"got ToolMessage content {tm.content!r}"
    )
