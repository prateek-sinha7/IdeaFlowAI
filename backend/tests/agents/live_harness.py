"""tests/agents/live_harness.py — Phase 8 live-verification harness (foundation).

A GENERIC, reusable driver that runs the REAL migrated deepagents stack against a
REAL model (default-profile AWS Bedrock Haiku 4.5) **and** against an offline
``ScriptedFakeChatModel`` (zero Bedrock cost) through the SAME entry points — so
the whole Phase-8 verify suite commits green with no credentials and is flipped
live by passing ``model=live_model()`` (or ``model=None`` to let the production
factory build Bedrock itself).

This module is the **integration contract** the rest of Phase 8 builds on: the
contract validator (T2 ``live_contract.py``), the per-pipeline live suite
(T3 ``test_phase8_live.py``), and the cross-process resume test (T4) all consume
:class:`CaptureResult` and call the three ``drive_*`` entry points + the opt-in
gate (:func:`live_enabled` / :func:`live_skip_reason`).

────────────────────────────────────────────────────────────────────────────────
THREE DRIVE WORLDS (one entry point each)
────────────────────────────────────────────────────────────────────────────────
Not every pipeline runs through the ``ExecutionEngine``; there are three runtimes,
each with its own entry point and event vocabulary:

  * :func:`drive_engine_pipeline` — the engine-sequenced pipelines (prototype
    build/revision, app_builder, user_stories, ppt, mulesoft/dotnet, custom, …)
    via the public ``ExecutionEngine.execute()``. Generalizes
    ``tests/agents/_scripted_model._drive`` to accept a real-or-scripted model and
    to run the REAL planner. Captures the outbound WS event vocabulary verbatim
    (the websocket drainer forwards ``event["type"]`` + ``event["data"]``).
  * :func:`drive_chat` — the free-chat ``user_message`` path via
    ``ChatRunner.astream_execute()`` (its own ``phase_start`` / ``stream`` /
    ``phase_end`` / ``complete`` vocabulary + the trailing 10-key
    ``FinalOutputModel``).
  * :func:`drive_handoff` — the ``/flowin-handoff`` IDE→PR pipeline via
    ``run_handoff_pipeline()``, with ``handoff_github`` MOCKED and a temp local git
    workspace (NEVER real GitHub). Modeled on
    ``tests/integration/test_handoff_contract.py``.

────────────────────────────────────────────────────────────────────────────────
OFFLINE vs LIVE (the ``model`` parameter is the switch)
────────────────────────────────────────────────────────────────────────────────
Every ``drive_*`` takes a ``model`` argument:

  * ``model`` is a ``BaseChatModel`` INSTANCE (scripted OR real) → it is injected
    verbatim (engine/chat: as ``ctx.model``, consumed as-is by ``create_runner`` →
    ``DeepAgentRunner``; handoff: patched onto the four agents' ``build_model``).
    Pass a :class:`ScriptedFakeChatModel` for a zero-cost offline run.
  * ``model is None`` → NOTHING is patched: ``create_runner`` →
    ``build_model()`` builds the real provider (default-profile Bedrock Haiku when
    ``ANTHROPIC_API_KEY`` is empty). This is the LIVE path.
  * :func:`live_model` returns ``build_model(None, max_tokens=…)`` for callers that
    want an explicit instance (e.g. to share one client across worlds).

The LIVE path is gated by :func:`live_enabled` (``RUN_LIVE_BEDROCK=1`` + an STS
preflight on the DEFAULT AWS profile — NOT ``personal-sso``). The harness itself
never sets ``RUN_LIVE_BEDROCK``; callers opt in.

────────────────────────────────────────────────────────────────────────────────
TWO GATE MECHANISMS (engine-level vs tool-level — they are DIFFERENT)
────────────────────────────────────────────────────────────────────────────────
HITL appears in two distinct places; the harness handles both:

  1. **Engine inter-agent gate** (the user-facing "Review gates"): the engine
     PAUSES between agents by awaiting ``ArtifactStore.get_review_event(gate_key)``
     and emits ``review_gate_ready`` (``gate_key = f"{run_id}:{agent_id}"``). It is
     NOT a LangGraph interrupt. :func:`drive_engine_pipeline` drives the generator
     concurrently and, by default (``auto_resume_gates=True``), auto-approves each
     gate via ``ArtifactStore.set_review_response(gate_key, approved=True)`` so a
     gated pipeline runs to completion; ``CaptureResult.gated`` records that a gate
     fired. T3 can pass ``auto_resume_gates=False`` + a manual approver to test the
     pause→resume seam explicitly.
  2. **Runner tool-level gate** (dormant in the engine path, used by the
     standalone-runner HITL smoke): a ``DeepAgentRunner`` armed with
     ``interrupt_on`` emits a ``gate`` event with ``interrupt_ids`` and resumes via
     ``Command(resume={"decisions":[{"type":"approve"}]})``. :func:`resume_paused_run`
     issues exactly that command for a paused runner (the contract the task asked
     for; mirrors ``test_deep_agent_runner_hitl_live.py`` /
     ``test_phase3_cutover_verify.py``).

────────────────────────────────────────────────────────────────────────────────
§12 GOTCHAS HONOURED
────────────────────────────────────────────────────────────────────────────────
  * ``RUNS_ROOT`` is set to a temp dir at import (before ``app.core.config`` reads
    it) AND re-forced on ``settings`` at runtime (it may have been imported earlier
    with the read-only ``/app/runs`` default).
  * ``ENV=development`` → the checkpointer falls back to ``InMemorySaver`` (no
    Postgres / no creds).
  * The engine's ``ArtifactStore.store`` is no-op'd (no ``workflow_runs`` row in
    tests → an FK INSERT would abort the run).
  * ``ALWAYS_CLARIFY`` is forced ``False`` (the clarifier needs live WS round-trips).
  * Each run gets a UNIQUE ``pipeline_run_id`` (the state machine is a process-wide
    singleton keyed on run id; a reused id is "already completed").
  * EVERY patched global (``create_runner`` on both ``factory`` and ``engine``
    modules, ``engine._run_planner``, ``ArtifactStore.store``, ``settings``) is
    restored in a ``finally`` — the harness is called repeatedly in one process.

NOTHING under ``app/`` or ``agents/`` is modified — this is verify-only test code.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

# ── Make the backend package root importable (tests/agents/live_harness.py →
#    backend/). Works whether run as a script or imported. ─────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ── RUNS_ROOT must be set BEFORE app.core.config / sandbox import it ───────────
# Reuse the same env var the scripted driver honours so a parent test that already
# set it wins; otherwise a fresh temp dir.
_RUNS_ROOT = os.environ.get("PARITY_RUNS_ROOT") or tempfile.mkdtemp(prefix="live-harness-runs-")
os.environ["RUNS_ROOT"] = _RUNS_ROOT
# Force the InMemory checkpointer for the offline / non-Postgres path (no creds).
os.environ.setdefault("ENV", "development")

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


# ===========================================================================
# Haiku 4.5 pricing — used by cost_usd() and the T2 cost watcher.
# (Matches the rate encoded at websocket.py:1207 — $0.25/M in, $1.25/M out.)
# ===========================================================================

HAIKU_INPUT_USD_PER_MTOK: float = 0.25
HAIKU_OUTPUT_USD_PER_MTOK: float = 1.25


def cost_usd(tokens: "TokenTotals | dict[str, int]") -> float:
    """Return the USD cost of a token total at Bedrock Haiku 4.5 pricing.

    Accepts either a :class:`TokenTotals` or a plain ``{"input","output",...}``
    dict (so it composes with ``CaptureResult.tokens``). Only input/output are
    billed; ``total`` is ignored for the calculation.
    """
    if isinstance(tokens, TokenTotals):
        t_in, t_out = tokens.input, tokens.output
    else:
        t_in = int(tokens.get("input", 0) or 0)
        t_out = int(tokens.get("output", 0) or 0)
    return (
        t_in / 1_000_000 * HAIKU_INPUT_USD_PER_MTOK
        + t_out / 1_000_000 * HAIKU_OUTPUT_USD_PER_MTOK
    )


# ===========================================================================
# The canonical capture format — the contract T2/T3/T4 consume.
# ===========================================================================


@dataclass
class TokenTotals:
    """Summed token usage for a run (from the runner's ``usage`` events).

    Fields:
      * ``input``  (int) — total input/prompt tokens summed across all model turns.
      * ``output`` (int) — total output/completion tokens summed across all turns.
      * ``total``  (int) — ``input + output`` (kept explicit so consumers don't
        have to recompute and so a future provider that reports a distinct
        ``total_tokens`` could override it).
    """

    input: int = 0
    output: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output, "total": self.total}


@dataclass
class CaptureResult:
    """The canonical, world-agnostic capture of ONE drive — the Phase-8 contract.

    Produced by every ``drive_*`` entry point and consumed by the T2 validator,
    the T3 live suite, and the T4 resume test. Every field is documented here
    because this dataclass IS the integration contract.

    Fields
    ------
    world : str
        Which runtime produced this capture — one of ``"engine"`` / ``"chat"`` /
        ``"handoff"``. Selects the validator's per-world assertions in T2.
    label : str
        The sub-identifier within the world: the ``pipeline_type`` for the engine
        world (e.g. ``"user_stories"`` / ``"prototype"``), the chat ``mode`` for
        the chat world (e.g. ``"default"``), and the resolved handoff ``mode`` for
        the handoff world (e.g. ``"coding"`` / ``"test"``).
    events : list[dict]
        EVERY yielded event dict, in emission order, captured verbatim. The shape
        is world-specific:
          - engine: the outbound WS events ``{"type", "data", ...}`` the engine
            yields (the same dicts the websocket drainer forwards). Includes
            ``agent_start`` / ``agent_chunk`` / ``tool_call`` / ``tool_result`` /
            ``task_progress`` / ``agent_complete`` / ``review_gate_*`` /
            ``pipeline_complete`` / ``error`` etc.
          - chat: ``StreamMessageModel`` dicts ``{"type","chunk","section","data"}``
            (``phase_start`` / ``stream`` / ``phase_end`` / ``error`` / ``complete``).
          - handoff: the WS envelope ``{"type","chunk","section","data"}``
            (``phase_start`` / ``phase_end`` / ``agent_thinking`` / ``agent_complete``
            / ``agent_error`` / ``pr_created`` / ``pipeline_complete``).
    tokens : TokenTotals
        Input/output/total tokens summed from the world's ``usage`` signal:
          - engine: summed from the engine's ``agent_complete`` events
            (``input_tokens`` / ``output_tokens`` / ``total_tokens`` per agent,
            which the engine itself sums from the runner's ``usage`` events).
          - chat: summed from each ``DeepAgentRunner``'s ``usage`` events captured
            via an ``astream_with_usage`` tap (see :func:`drive_chat`); a scripted
            chat run that streams pure text may legitimately report zero.
          - handoff: ``TokenTotals()`` (zero) — the handoff agents are one-shot
            ``ainvoke`` calls whose usage the pipeline does not surface as events;
            handoff cost is asserted by deliverable validity, not tokens.
        For a LIVE engine/chat run these are expected to be NON-ZERO (a core T2
        assertion); offline scripted runs report exactly the scripted usage.
    per_agent_tokens : dict[str, TokenTotals]
        Per-agent breakdown keyed by ``agent_id`` (engine: from ``agent_complete``;
        chat: per chat-phase agent id; handoff: empty). Lets T2/cost reporting
        attribute spend to a specific agent.
    deliverable : str | None
        The engine/handoff world's primary artifact:
          - engine: the ``final_output`` string off ``pipeline_complete.data``
            (``prototype.html`` for prototype/revision; the ``filename:``-block
            string for code-gen; the agent text otherwise). ``None`` if the run did
            not complete.
          - handoff: ``None`` (the handoff artifact is the structured
            ``pipeline_output`` dict — see :attr:`final_output`).
          - chat: ``None`` (chat's artifact is the 10-key dict — see
            :attr:`final_output`).
    final_output : Any | None
        The world's STRUCTURED terminal payload (complementary to
        :attr:`deliverable`):
          - chat: the 10-key ``FinalOutputModel.model_dump()`` dict off the trailing
            ``complete`` event.
          - handoff: the ``pipeline_output`` dict off the terminal
            ``pipeline_complete`` event (carries ``resolved_mode`` / ``branch_name``
            / ``pr_url`` / ``pr_number`` / ``test_report`` / ``compliance_report``).
          - engine: the same string as :attr:`deliverable` (mirrored for a uniform
            "the terminal payload" accessor).
    gated : bool
        ``True`` iff a HITL gate fired during the run — an engine
        ``review_gate_ready`` event, or a runner-level ``gate`` event in a captured
        runner stream. Lets T3 assert gate-on vs gates-off behavior.
    completed : bool
        ``True`` iff the run reached its terminal event for its world
        (``pipeline_complete`` for engine/handoff; ``complete`` for chat) AND no
        terminal ``error``/``agent_error``/``handoff_error`` aborted it. A quick
        success predicate for T2/T3.
    error : str | None
        The first error message captured (engine ``error`` / ``agent_error``; chat
        ``error``; handoff ``agent_error`` / ``handoff_error``), else ``None``.
    run_id : str | None
        The unique ``pipeline_run_id`` used for the engine world (so T4 can resume
        the SAME run id against Postgres). ``None`` for chat/handoff.
    duration_s : float
        Wall-clock seconds the drive took (cheap latency signal for the cost watcher).
    raised : BaseException | None
        For worlds whose generator RE-RAISES on the error path (handoff): the
        propagated exception, captured rather than bubbled, so a caller can assert
        the error contract without a try/except. ``None`` otherwise.
    """

    world: str
    label: str
    events: list[dict] = field(default_factory=list)
    tokens: TokenTotals = field(default_factory=TokenTotals)
    per_agent_tokens: dict[str, TokenTotals] = field(default_factory=dict)
    deliverable: str | None = None
    final_output: Any | None = None
    gated: bool = False
    completed: bool = False
    error: str | None = None
    run_id: str | None = None
    duration_s: float = 0.0
    raised: BaseException | None = None

    # -- Convenience accessors (used by the validator + cost watcher) ----------

    def event_types(self) -> list[str]:
        """Ordered list of every event ``type`` (the vocabulary, in order)."""
        return [e.get("type") for e in self.events]

    def events_of(self, event_type: str) -> list[dict]:
        """All captured events of a given ``type`` (in order)."""
        return [e for e in self.events if e.get("type") == event_type]

    def cost_usd(self) -> float:
        """USD cost of this capture's token total at Haiku 4.5 pricing."""
        return cost_usd(self.tokens)


# ===========================================================================
# Real model helper + opt-in gate (default AWS profile).
# ===========================================================================


def live_model(max_tokens: int | None = None) -> "BaseChatModel":
    """Return the REAL provider model — default-profile Bedrock Haiku 4.5.

    Thin pass-through to ``app.agents.model_factory.build_model(None, …)``: with
    ``settings.ANTHROPIC_API_KEY`` empty (the prod/default-profile case) this
    builds ``ChatBedrockConverse`` for ``settings.BEDROCK_INFERENCE_PROFILE_ID``
    (``eu.anthropic.claude-haiku-4-5-…``) in ``settings.AWS_REGION`` with the
    embedded botocore timeouts + adaptive retries. Use this (or ``model=None`` on a
    ``drive_*`` call) for the LIVE path; the resolved AWS credentials come from the
    DEFAULT profile.
    """
    from app.agents.model_factory import build_model

    return build_model(None, max_tokens=max_tokens)


_RUN_LIVE_HINT = (
    "LIVE Bedrock verification is opt-in. To run it (DEFAULT aws profile):\n"
    "    aws sso login            # refresh the default-profile SSO session\n"
    "    RUN_LIVE_BEDROCK=1 python3.11 -m pytest tests/agents/test_phase8_live.py -v -s\n"
    "(build_model() selects Bedrock Haiku 4.5 in eu-central-1 when ANTHROPIC_API_KEY "
    "is empty; the default profile must resolve via STS.)"
)


def _aws_creds_resolve() -> tuple[bool, str]:
    """Return ``(ok, detail)`` — whether usable AWS credentials resolve right now.

    Probes ``sts.get_caller_identity()`` (cheap, no Bedrock charge) on the DEFAULT
    profile (we deliberately do NOT set ``AWS_PROFILE`` — the default chain wins,
    per the Phase-8 decision to use the default profile, not ``personal-sso``).
    Catches the botocore credential/token errors raised when the SSO session is
    missing/expired so the live suite SKIPS cleanly rather than erroring deep inside
    a model call. Ported from ``test_deep_agent_runner_hitl_live.py``.
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


def live_skip_reason() -> str | None:
    """Return a skip reason if the LIVE Bedrock path must not run, else ``None``.

    Live runs ONLY when BOTH hold:
      * ``RUN_LIVE_BEDROCK=1`` (explicit opt-in), AND
      * a usable provider resolves — a configured ``ANTHROPIC_API_KEY`` (local dev,
        no AWS needed) OR resolvable DEFAULT-profile AWS creds (the Bedrock case).
    Otherwise returns a human-readable reason (with the exact run command) suitable
    for ``pytest.skip(...)`` / ``pytest.mark.skipif``.
    """
    if os.getenv("RUN_LIVE_BEDROCK") != "1":
        return f"RUN_LIVE_BEDROCK!=1 — live Bedrock verification is opt-in.\n{_RUN_LIVE_HINT}"

    from app.core.config import settings

    # A local Anthropic key means build_model() uses that provider — no AWS needed.
    if settings.ANTHROPIC_API_KEY:
        return None

    ok, detail = _aws_creds_resolve()
    if not ok:
        return f"{detail}\n{_RUN_LIVE_HINT}"
    return None


def live_enabled() -> bool:
    """``True`` iff the LIVE Bedrock path may run (see :func:`live_skip_reason`)."""
    return live_skip_reason() is None


# ===========================================================================
# Shared token-summing helpers.
# ===========================================================================


def _accumulate_usage(totals: TokenTotals, t_in: int, t_out: int) -> None:
    """Add (t_in, t_out) into ``totals`` (keeping ``total`` in sync)."""
    totals.input += int(t_in or 0)
    totals.output += int(t_out or 0)
    totals.total = totals.input + totals.output


def _is_base_chat_model(obj: Any) -> bool:
    """Duck-typed ``BaseChatModel`` check (avoid the heavy import at module top)."""
    if obj is None:
        return False
    from langchain_core.language_models import BaseChatModel

    return isinstance(obj, BaseChatModel)


# ===========================================================================
# World 1 — engine-sequenced pipelines (ExecutionEngine.execute()).
# ===========================================================================

# A gate approver: given (gate_key, gate_ready_event_data) decides approve/reject
# + optional edited content. Returns (approved, edited_content_or_None). May be a
# plain function OR a coroutine function (an async approver can delay/decide).
GateApprover = Callable[[str, dict], Any]


def _default_approver(gate_key: str, data: dict) -> "tuple[bool, str | None]":
    """Default gate policy: approve, no edit (lets a gated pipeline complete)."""
    return True, None


async def _apply_gate(store: Any, approver: GateApprover, gate_key: str, data: dict) -> None:
    """Resolve an approver (sync OR async) and write the review response.

    Runs as a concurrent task while the engine is blocked on the gate's
    ``asyncio.Event``. Supports both a plain ``(approved, edited)`` return and a
    coroutine returning the same — so callers can implement delays/decisions.
    """
    decision = approver(gate_key, data)
    if asyncio.iscoroutine(decision):
        decision = await decision
    approved, edited = decision
    await store.set_review_response(gate_key, approved=approved, edited_content=edited)


async def _answer_clarify(store: Any, run_id: str, data: dict) -> None:
    """Headless auto-answer for a ClarifyEngine questionnaire.

    A LIVE run's REAL planner may return ``CLARIFY_REQUIRED`` → the engine emits
    ``questionnaire_ready`` and ``ClarifyEngine.run`` BLOCKS on
    ``get_resume_event(run_id).wait()`` waiting for a human. Headless, nobody
    answers, so the run hangs forever. We pick each question's
    ``recommended_answer`` (the engine's own default) and submit it via
    ``set_questionnaire_responses`` (which also sets the resume event), so the
    pipeline proceeds — the "auto-proceed on clarify" the Phase-8 plan calls for,
    while still exercising the real planner + clarify question generation. Runs as
    a concurrent task (like :func:`_apply_gate`) so the next ``await`` in the
    drive's ``async for`` lets the blocked engine resume.
    """
    questions = data.get("questions") or []
    responses = [
        {
            "question_id": q.get("question_id"),
            "answer": q.get("recommended_answer")
            or (q.get("options") or ["No preference"])[-1],
        }
        for q in questions
    ]
    await store.set_questionnaire_responses(run_id, responses)


async def manual_resume_engine_gate(
    gate_key: str, *, approved: bool = True, edited_content: str | None = None
) -> None:
    """Resume a paused engine inter-agent gate by writing the review response.

    The explicit seam for T3's pause→resume scenario WITHOUT auto-resume: run
    :func:`drive_engine_pipeline` with ``auto_resume_gates=False`` as a concurrent
    task, wait for its ``review_gate_ready`` (the ``gate_key`` is on the event's
    ``data["gate_key"]``), then call this to unblock the engine (it sets the
    ArtifactStore review response + signals the gate's ``asyncio.Event``). This is
    the engine-level analogue of :func:`resume_paused_run` (which is the runner-level
    ``Command(resume)`` gate).

    ⚠️ With ``auto_resume_gates=False`` and a SINGLE consumer, a gated run will
    BLOCK at the first gate (the engine awaits the event inside its generator), so
    the drive MUST be consumed concurrently with the resume — never inline.
    """
    from agents.artifact_store.store import get_artifact_store

    store = get_artifact_store()
    await store.set_review_response(gate_key, approved=approved, edited_content=edited_content)


async def drive_engine_pipeline(
    pipeline_type: str,
    *,
    model: "BaseChatModel | Callable[[str], BaseChatModel] | None" = None,
    gate_agent_ids: "tuple[str, ...] | list[str]" = (),
    brief: str | None = None,
    od_context: dict | None = None,
    parent_run_id: str | None = None,
    fake_planner: bool = False,
    planner_result: "tuple[dict, str] | None" = None,
    auto_answer_clarify: bool = True,
    auto_resume_gates: bool = True,
    gate_approver: GateApprover | None = None,
    user_id: str = "harness-user",
    run_id: str | None = None,
    cancel_event: "asyncio.Event | None" = None,
) -> CaptureResult:
    """Drive ``ExecutionEngine.execute()`` end-to-end and capture the result.

    Generalizes ``tests/agents/_scripted_model._drive`` to a real-or-scripted model
    and the REAL planner. The ``model`` switch selects offline vs live:

      * ``model`` is a ``BaseChatModel`` (scripted OR real) → injected as ``ctx.model``
        for EVERY agent (the runner uses it verbatim) by monkeypatching
        ``create_runner`` on BOTH the ``factory`` and ``engine`` modules (the engine
        imported it by name). Good for a homogeneous offline pipeline (all text, e.g.
        ``user_stories``) or to share one real client across agents.
      * ``model`` is a CALLABLE ``(agent_id) -> BaseChatModel`` → a PER-AGENT factory.
        Use this to drive a HETEROGENEOUS pipeline offline — e.g. ``prototype``, where
        ``prototype-build`` needs a tool-calling script and the others need plain text:
        pass ``lambda aid: ScriptedFakeChatModel(_scripts_for(aid))`` (reusing
        ``tests/agents/_scripted_model._scripts_for``).
      * ``model is None`` → NO patch: ``create_runner`` → ``build_model()`` builds the
        real provider (default-profile Bedrock Haiku). This is the LIVE path.

    Planner: by default the REAL planner runs (``ALWAYS_CLARIFY`` forced off; a brief
    that is unlikely to clarify is used). ``fake_planner=True`` replaces ``_run_planner``
    with a default-PROCEED stub (used by the offline self-test to skip a planner LLM
    call). Note: prototype pipelines skip the planner anyway.

    Gates: ``gate_agent_ids`` is threaded into ``execute()`` (empty ⇒ no inter-agent
    gates; a list ⇒ gate exactly those agent ids). The engine's inter-agent gate
    PAUSES on an ``asyncio.Event`` (``ArtifactStore.get_review_event``), so a gated run
    is driven CONCURRENTLY: events are consumed in one task while, on each
    ``review_gate_ready``, a second task calls ``ArtifactStore.set_review_response``
    using ``gate_approver`` (default = approve) when ``auto_resume_gates`` is True. Pass
    ``auto_resume_gates=False`` to leave the gate open (T3 drives the resume itself).

    §12 gotchas honoured: ``RUNS_ROOT`` forced to a temp dir; ``engine._store.store``
    no-op'd; a UNIQUE ``pipeline_run_id``; ``ALWAYS_CLARIFY=False``; ALL patched
    globals restored in ``finally``.

    Returns a :class:`CaptureResult` (``world="engine"``, ``label=pipeline_type``).
    """
    import time

    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.registry import get_pipeline_agents
    from app.core.config import settings as _settings

    # ── Force RUNS_ROOT at RUNTIME (settings may have been loaded with /app/runs) ─
    _orig_runs_root = _settings.RUNS_ROOT
    _settings.RUNS_ROOT = _RUNS_ROOT

    # ── Don't FORCE clarify; if the real planner still returns CLARIFY_REQUIRED,
    #    the event loop auto-answers questionnaire_ready (auto_answer_clarify). ──
    # The former module-level ALWAYS_CLARIFY=False knob was deleted in 07-05; the
    # auto-clarify forcing is now declared by the manifest clarify.mode == "auto",
    # read off the CompiledWorkflow at run entry. Wrap compile_for_run to flip the
    # compiled clarify.mode to "off" (restored in finally) — same effect as the old knob.
    _orig_compile_for_run = engine_mod.compile_for_run

    def _harness_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    engine_mod.compile_for_run = _harness_compile_for_run

    specs = get_pipeline_agents(pipeline_type)

    # ── Snapshot every global we patch so finally can restore EXACTLY. ───────
    _orig_factory_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    # The model switch resolves to one of three regimes:
    #   * a BaseChatModel INSTANCE → injected as ctx.model for EVERY agent (shared);
    #   * a CALLABLE (agent_id) -> BaseChatModel → a PER-AGENT factory (offline
    #     heterogeneous pipelines like prototype, where the build agent needs a
    #     tool-calling script and the text agents need plain text — reuse
    #     ``_scripted_model._scripts_for``);
    #   * None → no patch → create_runner → build_model() builds real Bedrock (LIVE).
    _model_factory: "Callable[[str], BaseChatModel] | None" = None
    if _is_base_chat_model(model):
        _shared = model

        def _model_factory(_agent_id: str):  # type: ignore[misc]
            return _shared
    elif callable(model):
        _model_factory = model  # type: ignore[assignment]

    if _model_factory is not None:
        # Inject the (scripted or real) instance as ctx.model — used as-is by the
        # runner. We patch BOTH module bindings: the engine imported create_runner
        # by name at module load, so patching only factory_mod would miss it.
        def _patched_create_runner(agent_id, ctx, **kw):
            ctx.model = _model_factory(agent_id)
            return _orig_factory_create_runner(agent_id, ctx, **kw)

        factory_mod.create_runner = _patched_create_runner
        engine_mod.create_runner = _patched_create_runner
    # else: model is None → leave create_runner untouched → build_model() builds
    # real Bedrock (the LIVE path).

    engine = ExecutionEngine()

    # ── Artifact persistence: NO no-op needed post-Phase-5/12. The old
    #    ``ArtifactStore.store`` method (whose FK INSERT aborted harness runs at
    #    Phase 8) was deleted in the decoupling; the engine now persists through
    #    the owner-scoped ScopedStore, which degrades gracefully without a
    #    workflow_runs row. ``engine._store`` survives as the gate/questionnaire
    #    event hub (get_review_event / set_questionnaire_responses) used below. ──

    # ── Planner: real by default; default-PROCEED stub only if requested. ────
    _orig_run_planner = engine._run_planner
    if planner_result is not None:
        # Force a specific (planning_context, gate_verdict) — used offline to
        # exercise the CLARIFY_REQUIRED → auto-answer path deterministically.
        _forced_ctx, _forced_verdict = planner_result

        async def _forced_run_planner(
            user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs
        ):
            return dict(_forced_ctx), _forced_verdict

        engine._run_planner = _forced_run_planner  # type: ignore[assignment]
    elif fake_planner:

        async def _fake_run_planner(
            user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs
        ):
            return engine._default_planning_context(user_message), "PROCEED"

        engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    # ── Unique run id (state machine is a process-wide singleton per run id). ─
    run_id = run_id or f"harness-{pipeline_type}-{uuid.uuid4().hex[:8]}"

    # ── Prototype agents declare injects (template/design_system); supply a
    #    minimal od_context so injection succeeds (matches _scripted_model). ──
    if od_context is None and pipeline_type in ("prototype", "od_prototype"):
        od_context = {
            "template_body": (
                "## Workflow\nUse .card and .grid classes. Build pages into "
                "<section data-page>."
            ),
            "template_id": "web-prototype",
            "ds_id": "default",
            "ds_body": (
                ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;"
                "--border:#ddd;--muted:#888;}"
            ),
            "craft_block": "Keep markup semantic; wire every nav link.",
            "is_design_system_required": True,
        }

    brief = brief or "Build me a simple app for managing a personal task list."

    result = CaptureResult(world="engine", label=pipeline_type, run_id=run_id)
    approver = gate_approver or _default_approver
    store = engine._store
    _pending_resume_tasks: list[asyncio.Task] = []

    # ── Manifest-declared human gates (``gates: [human]`` on compiled steps, e.g.
    #    prototype specify/plan) consume ``_run_review_gate`` INSIDE gate
    #    evaluation (HumanGate → runner.run_human_gate → the engine method), so
    #    ``review_gate_ready`` never reaches this consumer — and the gate CLEARS
    #    its event on arming, so pre-approving the response can't unblock it
    #    either. Wrap the engine's ``_run_review_gate`` to fire the approver
    #    CONCURRENTLY the moment the gate yields ready — uniform for the legacy
    #    inline path and the declared-gate delegate (which resolves
    #    ``self._engine._run_review_gate`` at call time). Pass-through when
    #    auto-resume is off (the TestLiveHITL manual pause→resume seam). The
    #    engine instance is per-drive, so no restore is needed. ────────────────
    _orig_review_gate = engine._run_review_gate

    #    ``**kwargs`` must be BOTH accepted and FORWARDED: the engine grew redoable /
    #    update_specs_eligible / artifact_kind / revision_cycle / revision_in_flight /
    #    cancel_event and passes them by keyword. Accepting without forwarding is green on
    #    every arity check while dropping Stop (cancel_event) and the name-free SC-001
    #    discriminators. The four named parameters stay named — the body reads two of them.
    async def _auto_resume_review_gate(pipeline_run_id, agent_id, agent_name, output, **kwargs):
        async for _gev in _orig_review_gate(
            pipeline_run_id, agent_id, agent_name, output, **kwargs,
        ):
            if auto_resume_gates and _gev.get("type") == "review_gate_ready":
                result.gated = True
                _gdata = dict(_gev.get("data") or {})
                _gkey = _gdata.get("gate_key") or f"{pipeline_run_id}:{agent_id}"
                _pending_resume_tasks.append(
                    asyncio.create_task(_apply_gate(store, approver, _gkey, _gdata))
                )
            yield _gev

    engine._run_review_gate = _auto_resume_review_gate  # type: ignore[assignment]

    kwargs: dict[str, Any] = dict(
        agents=list(specs),
        user_message=brief,
        pipeline_run_id=run_id,
        pipeline_type=pipeline_type,
        user_id=user_id,
        od_context=od_context,
        gate_agent_ids=list(gate_agent_ids),
        parent_run_id=parent_run_id,
        cancel_event=cancel_event,
    )

    t0 = time.time()
    try:
        async for ev in engine.execute(**kwargs):
            result.events.append(ev)
            etype = ev.get("type")
            data = ev.get("data") or {}

            if etype == "agent_complete":
                # The engine sums the runner's usage into per-agent totals here.
                aid = data.get("agent_id", "<unknown>")
                per = result.per_agent_tokens.setdefault(aid, TokenTotals())
                _accumulate_usage(
                    per, data.get("input_tokens", 0), data.get("output_tokens", 0)
                )
                _accumulate_usage(
                    result.tokens, data.get("input_tokens", 0), data.get("output_tokens", 0)
                )

            elif etype == "review_gate_ready":
                # Approval (when auto_resume_gates) is scheduled by the
                # ``_auto_resume_review_gate`` wrapper at the YIELD site — it
                # covers BOTH the legacy inline path (whose events surface here)
                # and the declared-gate delegate (whose events do not). Here we
                # only record that a gate fired.
                result.gated = True

            elif etype == "questionnaire_ready":
                # The REAL planner asked to clarify; auto-answer headlessly so the
                # run proceeds. The engine is BLOCKED on the resume event inside
                # this same generator, so answer from a CONCURRENT task (like the
                # review gate above) — the next `await` lets the engine resume.
                if auto_answer_clarify:
                    _pending_resume_tasks.append(
                        asyncio.create_task(_answer_clarify(store, run_id, dict(data)))
                    )

            elif etype == "pipeline_complete":
                result.completed = True
                fo = data.get("final_output")
                result.deliverable = fo
                result.final_output = fo

            elif etype in ("error", "agent_error"):
                if result.error is None:
                    result.error = data.get("error") or data.get("message") or str(data)
    finally:
        result.duration_s = time.time() - t0
        # Drain any in-flight resume tasks so they don't leak past the drive.
        for task in _pending_resume_tasks:
            with contextlib.suppress(Exception):
                await task
        # Restore EVERY patched global (the harness runs repeatedly per process).
        factory_mod.create_runner = _orig_factory_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine._run_planner = _orig_run_planner  # type: ignore[assignment]
        engine_mod.compile_for_run = _orig_compile_for_run
        _settings.RUNS_ROOT = _orig_runs_root

    return result


# ===========================================================================
# World 2 — free-chat (ChatRunner.astream_execute()).
# ===========================================================================


async def drive_chat(
    message: str,
    *,
    mode: str | None = None,
    mode_prompt: str = "",
    model: "BaseChatModel | None" = None,
    user_id: str = "harness-user",
    run_id: str | None = None,
) -> CaptureResult:
    """Drive ``ChatRunner.astream_execute()`` and capture the result.

    The chat world is its own sequencer (not the engine): it runs the 7 text-only
    ``chat-*`` agents in phase order and emits ``phase_start`` / ``stream`` /
    ``phase_end`` / ``error`` / a trailing ``complete`` (10-key ``FinalOutputModel``).

    Model switch (same semantics as the engine world):
      * ``model`` is a ``BaseChatModel`` → injected as ``ctx.model`` so each chat
        agent's ``create_runner`` builds a ``DeepAgentRunner`` over THAT model.
      * ``model is None`` → real ``build_model()`` (LIVE path).

    Tokens: ``ChatRunner`` consumes each agent via ``DeepAgentRunner.astream`` (text
    chunks only — no usage surfaced). To still capture token totals we install a
    lightweight TAP: each runner's ``.astream`` is wrapped so it ALSO drains the
    runner's ``astream_with_usage`` accounting. Concretely, we monkeypatch
    ``DeepAgentRunner.astream`` on the constructed runners to delegate to
    ``astream_with_usage`` and record the final ``TokenUsage``. A scripted chat run
    that reports no usage yields ``TokenTotals()`` (zero) — that is expected offline.

    Returns a :class:`CaptureResult` (``world="chat"``, ``label=mode``). The 10-key
    final dict is in ``final_output``; ``deliverable`` is ``None`` (chat's artifact is
    the structured dict).
    """
    import time

    from agents.factory import AgentContext
    from app.agents.chat_runner import ChatRunner
    from app.core.config import settings as _settings

    mode = mode or "default"
    run_id = run_id or f"harness-chat-{uuid.uuid4().hex[:8]}"

    # ── Force RUNS_ROOT at RUNTIME: ChatRunner.__init__ → create_runner builds a
    #    per-agent RunSandbox off settings.RUNS_ROOT, which may have been imported
    #    with the read-only /app/runs default. (The chat agents are text-only, so
    #    the sandbox is unused — but it is still ensured() at construction.) ──────
    _orig_runs_root = _settings.RUNS_ROOT
    _settings.RUNS_ROOT = _RUNS_ROOT

    ctx = AgentContext(user_request=message, user_id=user_id, run_id=run_id)
    if _is_base_chat_model(model):
        ctx.model = model
    # else: ctx.model stays default → create_runner → build_model() (LIVE).

    result = CaptureResult(world="chat", label=mode, run_id=None)

    # ── Token tap: wrap each runner's .astream to record usage via the runner's
    #    own astream_with_usage path (which yields text chunks then a TokenUsage).
    #    A pure factory (no `runner` dependency) so it can be defined before the
    #    try block; the result accumulator is closed over. ─────────────────────
    def _wrap_astream(dar, phase_aid: str):
        orig_astream_with_usage = dar.astream_with_usage

        async def _astream(message: str):
            last_usage = None
            async for item in orig_astream_with_usage(message):
                # astream_with_usage yields str chunks, then a final TokenUsage.
                if isinstance(item, str):
                    yield item
                else:
                    last_usage = item
            if last_usage is not None:
                t_in = int(getattr(last_usage, "input_tokens", 0) or 0)
                t_out = int(getattr(last_usage, "output_tokens", 0) or 0)
                _accumulate_usage(result.tokens, t_in, t_out)
                per = result.per_agent_tokens.setdefault(phase_aid, TokenTotals())
                _accumulate_usage(per, t_in, t_out)

        return _astream

    t0 = time.time()
    try:
        # Construct INSIDE the try so the finally always restores RUNS_ROOT, even
        # if create_runner / graph construction raises.
        runner = ChatRunner(ctx)
        # ChatRunner stores its 7 agents in ._runners (phase → DeepAgentRunner).
        # Key the per-agent token breakdown by the chat agent id (from
        # _PHASE_AGENTS), not the model_id (identical across all chat agents).
        _phase_agents = getattr(ChatRunner, "_PHASE_AGENTS", {})
        for _phase, dar in getattr(runner, "_runners", {}).items():
            # Only wrap real DeepAgentRunners (a test may have swapped in a stub).
            if hasattr(dar, "astream_with_usage"):
                aid = _phase_agents.get(_phase, (f"chat-phase-{_phase}",))[0]
                dar.astream = _wrap_astream(dar, aid)  # type: ignore[attr-defined]

        async for ev in runner.astream_execute(
            message, chat_session_id=run_id, mode=mode, mode_prompt=mode_prompt
        ):
            result.events.append(ev)
            etype = ev.get("type")
            if etype == "complete":
                result.completed = True
                result.final_output = ev.get("data")
            elif etype == "error":
                if result.error is None:
                    d = ev.get("data") or {}
                    result.error = d.get("error") or str(d)
    finally:
        result.duration_s = time.time() - t0
        _settings.RUNS_ROOT = _orig_runs_root

    return result


# ===========================================================================
# World 3 — /flowin-handoff (run_handoff_pipeline()) with mocked GitHub.
# ===========================================================================

# Minimal deterministic repo the fake clone materialises (modeled on
# test_handoff_contract.py's FILES_ON_CLONE — small enough that the preview trim
# is a no-op).
_HANDOFF_FILES_ON_CLONE: dict[str, str] = {
    "README.md": "# Demo\nA demo repo for the live harness.\n",
    "app/main.py": "def add(a, b):\n    return a + b\n",
    "app/test_main.py": "def test_add():\n    assert True\n",
}

# Deterministic fake-PR identifiers + branch metadata.
_HANDOFF_PR_URL = "https://github.com/acme/widgets/pull/1"
_HANDOFF_PR_NUMBER = 1
_HANDOFF_DEFAULT_BRANCH = "main"


class _FakeGitResult:
    """Stand-in for ``handoff_github.GitResult`` (returncode/stdout/stderr)."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_handoff_github_patches(stack: contextlib.ExitStack) -> None:
    """Patch ``handoff_github`` so the pipeline never touches the network / real git.

    Mirrors ``test_handoff_contract.py``: ``clone`` writes a deterministic workspace
    that the pipeline then walks/edits (so ``edit_results`` are REAL), the git
    mutators return success, ``create_pull_request`` returns a fake ``{url,number}``,
    and ``cleanup_workspace`` really ``rmtree``s the temp root (so nothing leaks).
    ``parse_github_url`` is left REAL (deterministic, no I/O).
    """
    import os as _os
    import shutil
    from unittest.mock import patch

    from app.services import handoff_github as gh

    def _fake_clone(target, pat, dest_dir, branch=None):
        workspace = _os.path.join(dest_dir, "workspace")
        for rel, content in _HANDOFF_FILES_ON_CLONE.items():
            full = _os.path.join(workspace, rel)
            _os.makedirs(_os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)
        return _FakeGitResult(0)

    async def _fake_get_repo_metadata(target, pat):
        return {"default_branch": _HANDOFF_DEFAULT_BRANCH}

    async def _fake_create_pull_request(**kwargs):
        return {"url": _HANDOFF_PR_URL, "number": _HANDOFF_PR_NUMBER}

    def _fake_cleanup_workspace(workspace_root: str) -> None:
        shutil.rmtree(workspace_root, ignore_errors=True)

    stack.enter_context(patch.object(gh, "clone", _fake_clone))
    stack.enter_context(patch.object(gh, "get_repo_metadata", _fake_get_repo_metadata))
    stack.enter_context(patch.object(gh, "create_pull_request", _fake_create_pull_request))
    stack.enter_context(patch.object(gh, "checkout_new_branch", lambda ws, b: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "stage_all", lambda ws: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "commit", lambda ws, m: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "push", lambda t, p, ws, b: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "wipe_credentialed_remote", lambda ws: None))
    stack.enter_context(patch.object(gh, "cleanup_workspace", _fake_cleanup_workspace))


# Offline-scripted agent plans (used when model is a scripted BaseChatModel). These
# are the JSON-plan shapes the real agents' ``setdefault`` contracts guarantee, with
# an edit whose old_string matches the cloned app/main.py EXACTLY ONCE (so
# _apply_edits → "applied" → the commit/push/PR branch runs end-to-end).
_HANDOFF_CODING_PLAN: dict[str, Any] = {
    "summary": "Add subtract function",
    "rationale": "Implements subtraction as requested.",
    "edits": [
        {
            "path": "app/main.py",
            "operation": "modify",
            "old_string": "def add(a, b):\n    return a + b\n",
            "new_string": (
                "def add(a, b):\n    return a + b\n\n\n"
                "def subtract(a, b):\n    return a - b\n"
            ),
        }
    ],
    "tests_added": ["app/test_main.py"],
    "follow_ups": [],
}
_HANDOFF_TEST_REPORT: dict[str, Any] = {
    "summary": "Tests cover happy path.",
    "verdict": "concerns",
    "tests_present": [{"path": "app/test_main.py", "covers": "add"}],
    "missing_coverage": [{"area": "subtract", "suggested_test": "test_subtract"}],
    "quality_issues": [],
    "recommended_additions": ["add a subtract test"],
}
_HANDOFF_COMPLIANCE_REPORT: dict[str, Any] = {
    "summary": "No security issues.",
    "verdict": "approve_with_changes",
    "findings": [],
    "positives": ["clean diff"],
}


def _deepish_copy(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deepish_copy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deepish_copy(v) for v in obj]
    return obj


def _make_scripted_agent_patches(stack: contextlib.ExitStack) -> None:
    """Patch the four handoff agents AS BOUND IN THE PIPELINE with scripted fakes.

    Used for the OFFLINE path (when a scripted model is supplied / no live run): the
    pipeline binds ``CodingAgent``/``TestAgent``/``ComplianceAgent``/``classify_task``
    at import, so we patch ``handoff_pipeline.{...}``. This is migration-agnostic and
    needs NO Bedrock — the LIVE path skips it and lets the real ``build_model``-backed
    agents run.
    """
    from unittest.mock import patch

    from app.services import handoff_pipeline as hp

    class _FakeCodingAgent:
        def __init__(self, *a, **k) -> None:
            pass

        async def propose_edits(self, **kwargs):
            return _deepish_copy(_HANDOFF_CODING_PLAN)

    class _FakeTestAgent:
        def __init__(self, *a, **k) -> None:
            pass

        async def analyse(self, **kwargs):
            return _deepish_copy(_HANDOFF_TEST_REPORT)

    class _FakeComplianceAgent:
        def __init__(self, *a, **k) -> None:
            pass

        async def review(self, **kwargs):
            return _deepish_copy(_HANDOFF_COMPLIANCE_REPORT)

    async def _fake_classify(task_description, transcript_excerpt=None):
        return "coding"

    stack.enter_context(patch.object(hp, "CodingAgent", _FakeCodingAgent))
    stack.enter_context(patch.object(hp, "TestAgent", _FakeTestAgent))
    stack.enter_context(patch.object(hp, "ComplianceAgent", _FakeComplianceAgent))
    stack.enter_context(patch.object(hp, "classify_task", _fake_classify))


async def drive_handoff(
    *,
    mode: str = "coding",
    model: "BaseChatModel | None" = None,
    task_description: str = "Add a subtract function",
    repo_url: str = "https://github.com/acme/widgets",
    handoff_id: str | None = None,
) -> CaptureResult:
    """Drive ``run_handoff_pipeline()`` with ``handoff_github`` mocked + a temp repo.

    Models ``tests/integration/test_handoff_contract.py``: the pipeline runs for real
    (it calls ``tempfile.mkdtemp`` + ``_walk_repo`` + ``_apply_edits`` on the cloned
    workspace) but every ``handoff_github`` call is faked, so NO network / NO real
    GitHub is touched and the only filesystem written is a self-contained temp dir the
    faked cleanup deletes.

    Model switch:
      * ``model`` is a ``BaseChatModel`` (scripted) → the four handoff agents are
        REPLACED by scripted fakes returning fixed JSON plans (zero Bedrock). The
        ``model`` instance itself is not consumed (the handoff agents are mocked
        wholesale offline); passing a scripted model is the signal "run offline".
      * ``model is None`` → the REAL ``build_model``-backed handoff agents run (LIVE
        path) — only ``handoff_github`` is mocked, never the model.

    Tokens are ``TokenTotals()`` (the handoff agents are one-shot ``ainvoke`` calls
    whose usage the pipeline does not surface as events). The handoff artifact is the
    terminal ``pipeline_output`` dict (``final_output``); ``deliverable`` is ``None``.

    Returns a :class:`CaptureResult` (``world="handoff"``, ``label=<resolved mode>``).
    The handoff pipeline RE-RAISES on the error path; that exception is captured into
    ``CaptureResult.raised`` (and ``error``) rather than propagated.
    """
    import time

    handoff_id = handoff_id or f"{uuid.uuid4()}"
    offline = _is_base_chat_model(model)

    result = CaptureResult(world="handoff", label=mode)

    stack = contextlib.ExitStack()
    _make_handoff_github_patches(stack)
    if offline:
        # No live model → script the agents so the pipeline is fully deterministic.
        _make_scripted_agent_patches(stack)

    t0 = time.time()
    try:
        # Import lazily INSIDE the patched scope so the pipeline picks up the
        # patched module-bound symbols.
        from app.services import handoff_pipeline as hp

        gen = hp.run_handoff_pipeline(
            handoff_id=handoff_id,
            handoff_token="harness-tok",
            task_description=task_description,
            transcript_excerpt=None,
            repo_url=repo_url,
            requested_mode=mode,
            source_branch=None,
            pat="github_pat_harness_fake",
            issuer_email="harness@example.com",
            handoff_public_url="https://flowin.example/handoff/harness",
        )
        try:
            async for ev in gen:
                result.events.append(ev)
                etype = ev.get("type")
                data = ev.get("data") or {}
                if etype == "pipeline_complete":
                    result.completed = True
                    result.final_output = data  # the pipeline_output dict
                    result.label = data.get("resolved_mode", mode)
                elif etype in ("agent_error", "handoff_error"):
                    if result.error is None:
                        result.error = data.get("error") or data.get("message") or str(data)
        except BaseException as exc:  # noqa: BLE001 — capture the re-raise contract
            result.raised = exc
            if result.error is None:
                result.error = str(exc)
            with contextlib.suppress(Exception):
                await gen.aclose()
    finally:
        result.duration_s = time.time() - t0
        stack.close()

    return result


# ===========================================================================
# Runner-level (tool) gate resume — Command(resume=…). The contract the task
# asked for; mirrors test_deep_agent_runner_hitl_live.py / test_phase3_cutover.
# ===========================================================================


async def resume_paused_run(
    runner: Any,
    *,
    n_decisions: int | None = None,
    decision: str = "approve",
) -> Any:
    """Resume a ``DeepAgentRunner`` paused at a tool-level HITL gate.

    Issues ``Command(resume={"decisions":[{"type":decision}] * n})`` on the runner's
    own graph + config — exactly the resume the live HITL smoke + the Phase-3 cutover
    test use. ``n_decisions`` must equal the number of pending ``action_requests``
    (the middleware validates the count); if ``None`` it is read from the persisted
    state's pending interrupts (defaulting to 1).

    This is the RUNNER (LangGraph-interrupt) gate — distinct from the engine's
    inter-agent ``review_gate`` (which :func:`drive_engine_pipeline` resumes via the
    ArtifactStore). Returns the graph's terminal state dict (``ainvoke`` result) so a
    caller can assert the gated tool executed.
    """
    from langgraph.types import Command

    if n_decisions is None:
        n_decisions = await _count_pending_interrupts(runner)
    n_decisions = max(1, int(n_decisions))
    resume_value = {"decisions": [{"type": decision}] * n_decisions}
    return await runner._graph.ainvoke(Command(resume=resume_value), runner.config)


async def _count_pending_interrupts(runner: Any) -> int:
    """Count pending action_requests on a paused runner's persisted state (≥? )."""
    state = await runner._graph.aget_state(runner.config)
    total = 0
    for intr in getattr(state, "interrupts", ()) or ():
        val = getattr(intr, "value", None)
        if isinstance(val, dict):
            total += len(val.get("action_requests", []) or [])
    if total == 0:
        for task in getattr(state, "tasks", ()) or ():
            for intr in getattr(task, "interrupts", ()) or ():
                val = getattr(intr, "value", None)
                if isinstance(val, dict):
                    total += len(val.get("action_requests", []) or [])
    return total


# ===========================================================================
# Convenience: drive a standalone DeepAgentRunner and capture its events.
# (Used by T3's runner-level gate-on/off scenarios; complements the 3 worlds.)
# ===========================================================================


async def capture_runner_stream(
    runner: Any, message: str
) -> "tuple[list[dict], dict | None]":
    """Drive ``runner.astream_events(message)``; return (events, gate_event|None).

    A thin helper for T3's tool-level HITL scenarios: returns the ordered event list
    plus the first ``gate`` event (or ``None`` if the run reached ``done``). Keeps the
    runner-level gate handling in one place alongside :func:`resume_paused_run`.
    """
    events: list[dict] = []
    gate_event: dict | None = None
    async for ev in runner.astream_events(message):
        events.append(ev)
        if ev.get("type") == "gate" and gate_event is None:
            gate_event = ev
    return events, gate_event


# Awaitable type alias re-exported for callers building custom approvers/runners.
DriveCoroutine = Callable[..., Awaitable[CaptureResult]]
