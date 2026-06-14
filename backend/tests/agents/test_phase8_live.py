"""tests/agents/test_phase8_live.py — Phase-8 per-pipeline live suite + HITL (T3).

The verification suite that wires the **T1 harness** (``live_harness``) and the
**T2 validator** (``live_contract``) into ONE gated file that:

  1. runs EVERY drivable pipeline against the **real** Bedrock Haiku model when
     opted in (``RUN_LIVE_BEDROCK=1`` + resolvable default-profile AWS creds), and
  2. is **fully proven OFFLINE** (scripted model, zero Bedrock, no AWS) so it
     commits green — the live cases SKIP cleanly and the offline-proof cases PASS.

The whole design rests on a single idea: the SAME per-pipeline helper drives a
pipeline whether it is handed the real model (``model=None`` → live) or a scripted
model (offline). So the offline proof exercises the EXACT wiring the live sweep
uses — the harness drive call, the capture format, and the T2 contract validator —
just with a deterministic model and a ``require_tokens=False`` token gate (a
scripted pure-text run legitimately reports 0 tokens; the live gate is
``require_tokens=True``). See the harness/validator module docstrings for the full
contract.

────────────────────────────────────────────────────────────────────────────────
WHAT THIS FILE CONTAINS (and how it maps to the task)
────────────────────────────────────────────────────────────────────────────────
* **Per-pipeline helpers** (``_run_<pipeline>(model=...)``) — thin wrappers giving
  each pipeline a sensible brief + fixtures, parameterised on ``model`` so each can
  be driven live (``None``) or scripted. Covered: ``prototype`` (build),
  ``prototype_revision`` (chained off a prior prototype run via ``parent_run_id``),
  ``app_builder``, ``user_stories``, ``od_ppt`` (+ ``ppt`` note), free-``chat``,
  ``handoff`` (coding + test).
* **LIVE cases** (``TestLivePipelines`` / ``TestLiveHITL``) — ``skipif`` on
  :func:`live_skip_reason`; one test per pipeline driving the REAL model and
  asserting :func:`assert_capture` with ``require_tokens=True``, plus a session
  cost roll-up (:func:`summarize_cost` + :func:`assert_under_budget`). These SKIP
  cleanly offline.
* **HITL on/off** — gates-off (no ``review_gate_ready``), engine inter-agent
  gate-on (pause → resume → complete) via BOTH ``auto_resume_gates=True`` (one-shot)
  AND an explicit ``manual_resume_engine_gate`` pause/resume seam, and the
  runner tool-level gate via ``resume_paused_run``. Provided in BOTH a LIVE-gated
  flavour and a scripted-offline flavour.
* **OFFLINE PROOF (ungated, MUST pass with zero Bedrock)** — a representative
  subset (``user_stories`` [shared instance], ``prototype`` [per-agent factory],
  ``od_ppt``, ``app_builder``, ``prototype_revision`` [chained], ``chat``,
  ``handoff`` coding + test) driven through the SAME helpers + ``assert_capture``.
* **Collection/skip self-check** — proves the file imports cleanly, the live cases
  SKIP (not error) without creds, and the offline-proof cases PASS.

────────────────────────────────────────────────────────────────────────────────
DELIBERATELY-SKIPPED-OFFLINE PIPELINES (documented, not faked)
────────────────────────────────────────────────────────────────────────────────
The repo-input code-gen pipelines ``mulesoft_to_springboot`` / ``dotnet_to_azure``
(and their revisions) genuinely cannot be driven offline without a real source repo
to inventory/migrate — there is no synthetic brief that produces a faithful
``filename:`` deliverable the way ``app_builder`` does from a prose brief. They are
covered by a LIVE case (with a minimal fixture brief) but SKIPPED-with-reason in the
offline proof (:func:`_skip_codegen_offline`) rather than faked. ``ppt`` (the alias
whose agents are tagged ``od_ppt`` → ``get_pipeline_agents("ppt") == []``) is driven
via its real-agent twin ``od_ppt``; see :func:`_run_od_ppt`.

CONSTRAINTS honoured: no production code touched (read-only under app/ + agents/);
``live_harness`` / ``live_contract`` / ``_scripted_model`` consumed, never modified
(inline scripts live HERE); no ``RUN_LIVE_BEDROCK`` set; no git.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tests.agents._scripted_model import (
    ScriptedFakeChatModel,
    _ScriptedTurn,
    _scripts_for,
)
from tests.agents.live_contract import (
    assert_capture,
    assert_under_budget,
    summarize_cost,
    validate_capture,
)
from tests.agents.live_harness import (
    CaptureResult,
    capture_runner_stream,
    drive_chat,
    drive_engine_pipeline,
    drive_handoff,
    live_skip_reason,
    manual_resume_engine_gate,
    resume_paused_run,
)

# A type alias for the per-pipeline ``model`` switch. The helpers accept either a
# single ``BaseChatModel`` instance (homogeneous text pipelines / live shared
# client), a per-agent ``(agent_id) -> BaseChatModel`` factory (heterogeneous
# pipelines like prototype), or ``None`` (the LIVE path — let create_runner build
# real Bedrock). We do not import BaseChatModel at module top to keep collection
# import-light; the harness duck-types it.
ModelArg = object


# A soft cost ceiling for the WHOLE live sweep (Haiku 4.5: $0.25/M in, $1.25/M
# out) — a guardrail against a runaway live run, asserted in the session-cost
# roll-up. Recalibrated 2026-06-11 (13-04 / UAT test 8) from the measured CLEAN
# full sweep: $5.94 for 18.7M tokens (17.5M input) at Haiku 4.5 pricing, after
# MAX_OUTPUT_TOKENS was lifted to 32768. The original Phase-8 calibration (5.0)
# pre-dated that lift and sat below the measured clean-sweep spend; 8.0 keeps
# ~35% headroom over the measurement while still catching a runaway run.
LIVE_BUDGET_USD = 8.0


# ===========================================================================
# Skip gate — the SAME opt-in the harness defines (RUN_LIVE_BEDROCK=1 + creds).
# Evaluated at collection so the LIVE classes skip cleanly offline (never error).
# ===========================================================================

_LIVE_SKIP = live_skip_reason()
requires_live = pytest.mark.skipif(_LIVE_SKIP is not None, reason=_LIVE_SKIP or "")


def _skip_if_creds_lapsed_mid_sweep() -> None:
    """Runtime re-check: SKIP (not FAIL) when creds have lapsed mid-sweep (ISS-011).

    ``_LIVE_SKIP`` / the ``@requires_live`` mark are captured at COLLECTION time. On a
    multi-hour live sweep the default-profile SSO session can expire AFTER collection
    decided the suite was runnable — STS then stops resolving, the model call is
    swallowed to an ``error`` with 0 tokens, and the live assertions (``require_tokens``)
    FAIL spuriously, indistinguishable from a real regression.

    This re-evaluates the SINGLE runtime source of truth (:func:`live_skip_reason`,
    already runtime-callable) at each live-test start and turns a mid-sweep credential
    lapse into a clean ``pytest.skip`` with the exact re-run command — NOT a failure.
    It is resolved via the ``live_harness`` module (not the collection-time bound name)
    so the offline expired-creds simulation can monkeypatch it deterministically.
    """
    from tests.agents import live_harness

    reason = live_harness.live_skip_reason()
    if reason is not None:
        pytest.skip(
            "AWS SSO session expired mid-sweep — re-run after `aws sso login`: " + reason
        )


# ===========================================================================
# Shared offline fixtures — scripted models + briefs.
#
# Per the task constraint, anything ``_scripts_for`` does NOT cover is scripted
# INLINE here (we never modify the shared ``_scripted_model.py``). ``_scripts_for``
# DOES cover user_stories / prototype / app_builder; it does NOT cover the
# od_ppt text agents (they fall through to its generic text fallback, which is a
# valid non-empty text deliverable) nor the prototype_revision ``edit_file``
# protocol (its built-in script uses ``write_file``, which REFUSES to overwrite
# the engine-seeded prototype.html — so we script edit_file inline below).
# ===========================================================================


def _text_model(t_in: int = 12, t_out: int = 7) -> ScriptedFakeChatModel:
    """A pure-text scripted model (one turn, with usage) reused by every agent.

    ``ScriptedFakeChatModel`` falls back to its LAST turn once the call index
    exceeds the turn list, so this single text+usage turn serves every text-only
    agent in a homogeneous pipeline (e.g. user_stories) deterministically.
    """
    return ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["phase8 scripted output. ", "line two."], usage=(t_in, t_out))]
    )


def _per_agent_factory(agent_id: str) -> ScriptedFakeChatModel:
    """Per-agent scripted factory for a HETEROGENEOUS pipeline (reuses _scripts_for).

    Used to drive ``prototype`` / ``app_builder`` offline, where the build/code-gen
    agents need tool-calling scripts and the rest need plain text — exactly what
    ``_scripts_for`` already encodes per agent id.
    """
    return ScriptedFakeChatModel(_scripts_for(agent_id))


# od_context supplied to the od_ppt / prototype pipelines so the factory's
# ``injects`` (template / design_system) compose successfully. The prototype
# helpers rely on the harness's own built-in od_context (it injects an equivalent
# block when od_context is None for prototype/od_prototype); od_ppt has no such
# default in the harness, so we pass one explicitly.
_OD_PPT_CONTEXT: dict = {
    "template_body": "## Workflow\nUse .slide and .deck classes. One <section> per slide.",
    "template_id": "deck-template",
    "ds_id": "default",
    "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;}",
    "craft_block": "Keep each slide self-contained; consistent type scale.",
    "is_design_system_required": True,
}


# A VALID single-file SPA prototype the revision pipeline seeds + edits. nav↔
# sections resolve, the first page is is-active, the routes map is complete, and
# route() is defined — so it passes static_check (and render_check when a browser
# is available). The revision agent edits it IN PLACE via edit_file (write_file
# refuses to overwrite the engine-seeded file).
_REVISION_ORIGINAL_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>App</title>'
    "<style>[data-page]{display:none}[data-page].is-active{display:block}</style></head><body>"
    '<nav class="sidebar">'
    '<a class="nav-item" href="#/dashboard">Dashboard</a>'
    '<a class="nav-item" href="#/settings">Settings</a>'
    "</nav><main>"
    '<section data-page="dashboard" class="is-active"><h1>Dashboard</h1></section>'
    '<section data-page="settings"><h1>Settings</h1></section>'
    "</main><script>"
    'const routes={dashboard:"#/dashboard",settings:"#/settings"};'
    "function route(){var id=(location.hash||'#/dashboard').slice(2);"
    "document.querySelectorAll('[data-page]').forEach(function(e){"
    "e.classList.toggle('is-active',e.dataset.page===id);});}"
    "window.addEventListener('hashchange',route);"
    "window.addEventListener('DOMContentLoaded',route);"
    "</script></body></html>"
)

# The revision request, wrapped in the EXACT wire markers the engine extracts the
# existing HTML + the user instruction from (engine._extract_existing_prototype_html
# / _slim_revision_message). The HTML block is seeded into the revision sandbox as
# prototype.html; the REVISION REQUEST is the agent's instruction.
_REVISION_USER_INSTRUCTION = "Rename the dashboard heading to Home."
_REVISION_MESSAGE = (
    "=== EXISTING PROTOTYPE HTML ===\n"
    f"{_REVISION_ORIGINAL_HTML}\n"
    "=== END EXISTING HTML ===\n\n"
    "=== REVISION REQUEST ===\n"
    f"{_REVISION_USER_INSTRUCTION}\n"
    "=== END REQUEST ==="
)


def _revision_model_factory(agent_id: str) -> ScriptedFakeChatModel:
    """Per-agent factory for an OFFLINE prototype_revision run.

    The lone revision agent (``prototype-revision-agent``) edits prototype.html in
    place via ``edit_file`` — NOT ``write_file`` (the engine already wrote the
    seeded HTML to the sandbox, and deepagents' FilesystemBackend refuses to
    overwrite). The edit keeps the HTML valid (rename a heading), so the deliverable
    stays render-valid and the engine's post-revision smart-hybrid fix-loop is a
    no-op. (We script inline rather than touch _scripts_for, whose built-in revision
    script uses write_file.)
    """
    return ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=["Renaming the dashboard heading. "],
                tool_calls=[
                    (
                        "edit_file",
                        json.dumps(
                            {
                                "file_path": "prototype.html",
                                "old_string": "<h1>Dashboard</h1>",
                                "new_string": "<h1>Home</h1>",
                            }
                        ),
                        "rev_edit",
                    )
                ],
                usage=(12, 6),
            ),
            _ScriptedTurn(texts=["Revision complete."], usage=(4, 2)),
        ]
    )


# ===========================================================================
# PER-PIPELINE HELPERS — each takes a ``model`` so the SAME wrapper drives a
# pipeline live (model=None) or offline (a scripted model / per-agent factory).
# The HITL params (gate_agent_ids / auto_resume_gates / gate_approver / run_id)
# are threaded through so the gate scenarios reuse the same helpers.
# ===========================================================================


async def _run_user_stories(
    model: ModelArg = None,
    *,
    fake_planner: bool = False,
    **kw,
) -> CaptureResult:
    """``user_stories`` — a homogeneous text pipeline (6 text agents)."""
    return await drive_engine_pipeline(
        "user_stories",
        model=model,
        brief="Build a SaaS app for tracking team OKRs with weekly check-ins.",
        fake_planner=fake_planner,
        **kw,
    )


async def _run_prototype(
    model: ModelArg = None,
    *,
    fake_planner: bool = False,
    **kw,
) -> CaptureResult:
    """``prototype`` — heterogeneous (spec/plan text + build tool-calls + validate).

    od_context is left to the harness default (it injects an equivalent
    template/design-system block when od_context is None for the prototype family).
    """
    return await drive_engine_pipeline(
        "prototype",
        model=model,
        brief="Build a simple single-page task manager with a dashboard and a tasks list.",
        fake_planner=fake_planner,
        **kw,
    )


async def _run_prototype_revision(
    model: ModelArg = None,
    *,
    parent_run_id: str | None = None,
    fake_planner: bool = False,
    **kw,
) -> CaptureResult:
    """``prototype_revision`` — chains off a prior prototype run via ``parent_run_id``.

    The brief carries the EXISTING-HTML wire block (seeded as prototype.html) + the
    REVISION REQUEST; ``parent_run_id`` points at a completed prototype run so the
    engine seeds spec/design/tasks from that run's sandbox (graceful-degrade if
    absent). od_context mirrors the prototype family's inject requirements.
    """
    return await drive_engine_pipeline(
        "prototype_revision",
        model=model,
        brief=_REVISION_MESSAGE,
        parent_run_id=parent_run_id,
        od_context=_OD_PPT_CONTEXT,
        fake_planner=fake_planner,
        **kw,
    )


async def _run_app_builder(
    model: ModelArg = None,
    *,
    fake_planner: bool = False,
    **kw,
) -> CaptureResult:
    """``app_builder`` — a code-gen pipeline (15 agents; deliverable = filename: blocks)."""
    return await drive_engine_pipeline(
        "app_builder",
        model=model,
        brief="Build a small expense-tracker web app with a REST API and a SQLite store.",
        fake_planner=fake_planner,
        **kw,
    )


async def _run_od_ppt(
    model: ModelArg = None,
    *,
    fake_planner: bool = False,
    **kw,
) -> CaptureResult:
    """``od_ppt`` — the deck pipeline (text family; deliverable = non-empty).

    NOTE on ``ppt`` vs ``od_ppt``: the ``ppt`` pipeline is an ALIAS whose agents are
    tagged ``pipeline_type: od_ppt`` in their AGENT.md, so
    ``get_pipeline_agents("ppt") == []`` (a known, harmless static-frontend quirk —
    plan §9). Driving ``ppt`` would run zero agents and produce no deliverable, so
    the live + offline coverage for the PPT pipeline goes through its real-agent twin
    ``od_ppt`` (same three agents, own runner). od_context supplies the template/DS
    the od_ppt agents' ``injects`` require.
    """
    return await drive_engine_pipeline(
        "od_ppt",
        model=model,
        brief="Create a 6-slide investor pitch deck for a B2B analytics startup.",
        od_context=_OD_PPT_CONTEXT,
        fake_planner=fake_planner,
        **kw,
    )


async def _run_chat(model: ModelArg = None, **kw) -> CaptureResult:
    """free-``chat`` — the ChatRunner ``user_message`` path (its own world).

    The message mentions every deliverable keyword so all phases activate
    (deterministic, exercises the full phase envelope + the 10-key final output).
    """
    return await drive_chat(
        "Build a full product with user stories, a ppt deck, a prototype and a ui design.",
        mode="default",
        model=model,
        **kw,
    )


async def _run_handoff_coding(model: ModelArg = None, **kw) -> CaptureResult:
    """``/flowin-handoff`` coding mode — IDE→PR (handoff_github mocked, temp repo).

    The model switch signals offline (scripted → the 4 agents are mocked) vs live
    (None → the real build_model-backed agents run); handoff_github is ALWAYS mocked
    (never real GitHub), so even the live case never touches the network for git.
    """
    return await drive_handoff(mode="coding", model=model, **kw)


async def _run_handoff_test(model: ModelArg = None, **kw) -> CaptureResult:
    """``/flowin-handoff`` test mode — review only, no PR (pipeline_output omits PR)."""
    return await drive_handoff(mode="test", model=model, **kw)


def _skip_codegen_offline() -> None:
    """SKIP the repo-input code-gen pipelines offline (documented, not faked).

    ``mulesoft_to_springboot`` / ``dotnet_to_azure`` inventory + migrate a REAL
    source repository; there is no synthetic brief that yields a faithful
    ``filename:`` deliverable offline (unlike app_builder, which generates from a
    prose brief). They ARE exercised by the LIVE cases with a minimal fixture brief;
    offline we skip-with-reason rather than fabricate a deliverable.
    """
    pytest.skip(
        "repo-input code-gen pipelines (mulesoft_to_springboot / dotnet_to_azure) "
        "need a real source repo to inventory/migrate — covered by the LIVE cases "
        "with a fixture brief; not faked offline (per Phase-8 task constraint)."
    )


# Default-gated agents per pipeline (those whose AGENT.md declares gate: Human_Gate)
# — used by the gate-ON scenarios so the gate fires on the pipeline's REAL default
# gate agent. prototype-specify is the canonical first-stage gate.
_DEFAULT_GATE_AGENT: dict[str, str] = {
    "prototype": "prototype-specify",
    "user_stories": "domain-analyst",
}


# ===========================================================================
# LIVE — one case per pipeline against the REAL model. SKIP cleanly offline.
# Each asserts the T2 contract with require_tokens=True (a live run MUST report
# non-zero usage) and records its capture for the session cost roll-up.
# ===========================================================================


class _LiveCredsRecheckMixin:
    """Shared autouse mid-sweep credential re-check for the LIVE classes (ISS-011).

    The ``@requires_live`` mark / ``_LIVE_SKIP`` gate is captured ONCE at collection.
    On a multi-hour live sweep the default-profile SSO session can expire AFTER
    collection decided the suite was runnable — STS then stops resolving, the model
    call is swallowed to an ``error`` with 0 tokens, and the ``require_tokens=True``
    assertions FAIL spuriously. Both ``TestLivePipelines`` (which runs FIRST, ~2.8h)
    and ``TestLiveHITL`` carry that identical exposure, so the runtime re-check lives
    HERE, on a shared base BOTH inherit (no per-class duplication / dual-impl), rather
    than only on ``TestLiveHITL``.

    The fixture is autouse + ``function``-scoped, so it fires at EACH live-test start
    and turns a mid-sweep lapse into a clean ``pytest.skip`` (not a failure). It is a
    no-op when creds still resolve — and it never raises a SKIP for a genuine assertion
    failure, which is raised from the test body AFTER this fixture returns. It is bound
    only to the LIVE classes that inherit it, so ``TestOfflineHITL`` / ``TestOfflineProof``
    (which prove the gate seams with no creds) stay green offline.
    """

    @pytest.fixture(autouse=True)
    def _recheck_creds_at_runtime(self) -> None:
        _skip_if_creds_lapsed_mid_sweep()


@requires_live
class TestLivePipelines(_LiveCredsRecheckMixin):
    """LIVE Bedrock per-pipeline cases — gated on RUN_LIVE_BEDROCK=1 + creds.

    Collected into a class-level list so a session-cost summary + budget assertion
    runs after the sweep. Each test drives the REAL model (``model=None``), then
    ``assert_capture(result, require_tokens=True)``.
    """

    _captures: list[CaptureResult] = []

    def _record(self, result: CaptureResult) -> None:
        type(self)._captures.append(result)

    @pytest.mark.asyncio
    async def test_live_user_stories(self) -> None:
        result = await _run_user_stories(model=None)
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_prototype(self) -> None:
        result = await _run_prototype(model=None)
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_prototype_revision(self) -> None:
        # Chain off a real LIVE prototype build so parent seeding is exercised.
        parent = await _run_prototype(model=None)
        self._record(parent)
        assert_capture(parent, require_tokens=True)
        result = await _run_prototype_revision(model=None, parent_run_id=parent.run_id)
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_app_builder(self) -> None:
        result = await _run_app_builder(model=None)
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_od_ppt(self) -> None:
        result = await _run_od_ppt(model=None)
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_chat(self) -> None:
        result = await _run_chat(model=None)
        self._record(result)
        # Chat surfaces usage via the harness's astream_with_usage tap → live > 0.
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_handoff_coding(self) -> None:
        # handoff_github stays mocked even live; the MODEL is real (not mocked).
        result = await _run_handoff_coding(model=None)
        self._record(result)
        # Handoff agents are one-shot ainvoke calls whose usage the pipeline does
        # not surface as events → tokens are 0 by design; validity is the
        # pipeline_output shape, so require_tokens=False here (per the T1 contract).
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_live_handoff_test(self) -> None:
        result = await _run_handoff_test(model=None)
        self._record(result)
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_live_mulesoft_to_springboot(self) -> None:
        result = await drive_engine_pipeline(
            "mulesoft_to_springboot",
            model=None,
            brief=(
                "Migrate a MuleSoft integration that exposes an HTTP listener and "
                "transforms a JSON order payload to a Spring Boot REST service."
            ),
        )
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_dotnet_to_azure(self) -> None:
        result = await drive_engine_pipeline(
            "dotnet_to_azure",
            model=None,
            brief=(
                "Modernize a small .NET Framework web API with one orders controller "
                "to run on Azure App Service with Bicep infra."
            ),
        )
        self._record(result)
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_zz_live_cost_summary_under_budget(self) -> None:
        """Roll-up: print the per-capture cost table + assert the sweep budget.

        Ordered last in the class (``zz`` prefix) so the prior live cases have
        populated ``_captures``. Skips if no captures were recorded (e.g. the prior
        cases were deselected), so it never fails spuriously.
        """
        captures = type(self)._captures
        if not captures:
            pytest.skip("no live captures recorded (run the live pipeline cases first)")
        print("\n" + summarize_cost(captures))
        assert_under_budget(captures, LIVE_BUDGET_USD)


@requires_live
class TestLiveHITL(_LiveCredsRecheckMixin):
    """LIVE HITL on/off against the real model (gated on RUN_LIVE_BEDROCK=1).

    Inherits the autouse mid-sweep credential re-check from ``_LiveCredsRecheckMixin``
    (ISS-011), shared with ``TestLivePipelines`` so both live classes skip — not fail —
    on a mid-sweep SSO lapse.
    """

    @pytest.mark.asyncio
    async def test_live_gates_off_completes_without_gating(self) -> None:
        """gates-off: an empty gate_agent_ids ⇒ no review_gate_ready; run completes."""
        result = await _run_user_stories(model=None, gate_agent_ids=[])
        assert result.gated is False
        assert "review_gate_ready" not in result.event_types()
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_gate_on_pause_then_auto_resume(self) -> None:
        """gate-on (one-shot): gate the default agent → pause → auto-approve → complete."""
        result = await _run_user_stories(
            model=None, gate_agent_ids=[_DEFAULT_GATE_AGENT["user_stories"]]
        )
        types = result.event_types()
        assert result.gated is True
        assert types.count("review_gate_ready") == 1
        assert types.count("review_gate_approved") == 1
        assert_capture(result, require_tokens=True)

    @pytest.mark.asyncio
    async def test_live_runner_tool_gate_resume(self) -> None:
        """Runner tool-level gate: a real-model run pauses on a gated tool, then resumes.

        Uses the real Bedrock model with an armed report_task_complete gate. The model
        is non-deterministic — if it answers in plain text and never calls the tool,
        no gate can fire (the pause→resume path is unexercised), so we xfail rather
        than fail (mirrors test_deep_agent_runner_hitl_live.py).
        """
        from langchain_core.messages import ToolMessage
        from langchain_core.tools import tool
        from langgraph.checkpoint.memory import InMemorySaver

        from app.agents.deep_agent_runner import DeepAgentRunner
        from app.agents.model_factory import build_model

        @tool
        def report_task_complete(summary: str) -> str:
            """Record that the task is complete with a one-line summary."""
            return f"recorded: {summary}"

        runner = DeepAgentRunner(
            system_prompt=(
                "You are a worker. Call report_task_complete with a one-line summary "
                "when done."
            ),
            tools=[report_task_complete],
            model=build_model(),
            checkpointer=InMemorySaver(),
            thread_id="phase8-live-runner-gate",
            interrupt_on={"report_task_complete": True},
        )
        events, gate = await capture_runner_stream(
            runner,
            "Summarize 'the sky is blue' in one short line, then you MUST call the "
            "report_task_complete tool with that summary. Do not answer in plain text.",
        )
        types = [e.get("type") for e in events]
        if gate is None:
            assert "done" in types, "expected a clean 'done' if the gate never fired"
            pytest.xfail("model never called the gated tool — pause path unexercised this run")
        assert "done" not in types, "gate and done are mutually exclusive"

        final = await resume_paused_run(runner)
        tool_msgs = [
            m
            for m in final.get("messages", [])
            if isinstance(m, ToolMessage) and getattr(m, "name", "") == "report_task_complete"
        ]
        assert tool_msgs, "the approved gated tool must execute after resume"
        state = await runner._graph.aget_state(runner.config)
        assert state.next == (), "resumed graph must reach a terminal state"


# ===========================================================================
# OFFLINE PROOF (ungated, MUST PASS with zero Bedrock) — the SAME helpers driven
# with a scripted model, then validated by the SAME T2 validator. This is the
# load-bearing proof that the suite wiring + validator integration work end-to-end
# offline; the live cases above are the SAME calls with model=None.
#
# Scripted/offline captures use ``require_tokens=False`` (a scripted pure-text run
# legitimately reports the scripted usage, which the live gate would demand be > 0).
# ===========================================================================


class TestOfflineProof:
    @pytest.mark.asyncio
    async def test_user_stories_offline(self) -> None:
        """user_stories via a SHARED scripted instance (homogeneous text pipeline)."""
        result = await _run_user_stories(model=_text_model(), fake_planner=True)
        assert result.completed and result.error is None
        assert result.deliverable and result.deliverable.strip()
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_prototype_offline(self) -> None:
        """prototype via a PER-AGENT factory (_scripts_for) — exercises the rich path.

        tool_call + task_progress + a disk deliverable (prototype.html). The stock
        _scripts_for build writes a minimal stub whose HTML lacks an is-active page,
        so static_check legitimately FLAGS it — proving the deliverable-validity rule
        runs. We assert the RUN structure here (events/terminal/ordering) and that the
        only failures are the known static_check ones, not a wiring break.
        """
        result = await _run_prototype(model=_per_agent_factory, fake_planner=True)
        assert result.completed and result.error is None
        types = result.event_types()
        assert "tool_call" in types and "task_progress" in types
        assert types[-1] == "pipeline_complete"
        # The structural contract (everything EXCEPT deliverable validity) holds: a
        # run that completed structurally clean, with the deliverable check deferred.
        failures = validate_capture(result, require_tokens=False)
        # The stub HTML fails static_check; assert THAT is the only class of failure
        # (i.e. the harness + validator wiring is sound — no envelope/ordering/vocab
        # breakage). A render-valid build is proven separately below.
        assert all("static_check" in f for f in failures), (
            f"only the known stub static_check failure is expected offline, got: {failures}"
        )

    @pytest.mark.asyncio
    async def test_prototype_render_valid_offline(self) -> None:
        """prototype with an INLINE render-valid build → validates 100% clean.

        Complements the stub case: scripting a single-task plan + a build that writes
        a valid SPA makes the deliverable-validity rule (static_check [+ render_check])
        PASS, so validate_capture returns EMPTY — proving the full happy path offline.
        """
        result = await _run_prototype(model=_valid_prototype_factory, fake_planner=True)
        assert result.completed and result.error is None
        failures = validate_capture(result, require_tokens=False)
        assert failures == [], f"render-valid prototype should validate clean, got: {failures}"

    @pytest.mark.asyncio
    async def test_prototype_revision_offline_chained(self) -> None:
        """prototype_revision CHAINED off a real prior prototype run (parent_run_id).

        Drives a real offline prototype build, then a revision that seeds the parent's
        spec/design/tasks (via parent_run_id) and edits the seeded prototype.html in
        place. The edited HTML stays valid, so the capture validates clean.
        """
        parent = await _run_prototype(model=_per_agent_factory, fake_planner=True)
        assert parent.completed and parent.run_id
        result = await _run_prototype_revision(
            model=_revision_model_factory, parent_run_id=parent.run_id, fake_planner=True
        )
        assert result.completed and result.error is None
        # The edit was applied (Dashboard → Home) and the deliverable is the revised
        # HTML read back from the sandbox.
        assert "<h1>Home</h1>" in (result.deliverable or "")
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_app_builder_offline(self) -> None:
        """app_builder via the PER-AGENT factory — code-gen deliverable (filename: blocks)."""
        result = await _run_app_builder(model=_per_agent_factory, fake_planner=True)
        assert result.completed
        assert "```filename:" in (result.deliverable or "")
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_od_ppt_offline(self) -> None:
        """od_ppt via the PER-AGENT factory (text agents → non-empty deliverable)."""
        result = await _run_od_ppt(model=_per_agent_factory, fake_planner=True)
        assert result.completed and result.error is None
        assert result.deliverable and result.deliverable.strip()
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_chat_offline(self) -> None:
        """free-chat via a shared scripted instance — the 10-key final + phase envelope."""
        result = await _run_chat(model=_text_model())
        assert result.completed and result.error is None
        assert isinstance(result.final_output, dict)
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_handoff_coding_offline(self) -> None:
        """handoff coding via the scripted switch — full clone→…→PR stream + pipeline_output."""
        result = await _run_handoff_coding(model=_text_model())
        assert result.completed and result.label == "coding"
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_handoff_test_offline(self) -> None:
        """handoff test via the scripted switch — no PR; pipeline_output omits PR keys."""
        result = await _run_handoff_test(model=_text_model())
        assert result.completed and result.label == "test"
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_mulesoft_to_springboot_offline_skipped(self) -> None:
        """Documented SKIP: repo-input code-gen can't be driven offline without a repo."""
        _skip_codegen_offline()

    @pytest.mark.asyncio
    async def test_dotnet_to_azure_offline_skipped(self) -> None:
        """Documented SKIP: repo-input code-gen can't be driven offline without a repo."""
        _skip_codegen_offline()

    @pytest.mark.asyncio
    async def test_offline_cost_summary_renders(self) -> None:
        """The cost watcher renders a table over an offline sweep (smoke; no budget gate)."""
        captures = [
            await _run_user_stories(model=_text_model(), fake_planner=True),
            await _run_app_builder(model=_per_agent_factory, fake_planner=True),
            await _run_chat(model=_text_model()),
            await _run_handoff_coding(model=_text_model()),
        ]
        table = summarize_cost(captures)
        assert "Token / cost summary" in table and "GRAND TOTAL" in table
        # The whole offline sweep is trivially under a generous ceiling.
        assert_under_budget(captures, LIVE_BUDGET_USD)


# A render-valid inline prototype build (single-task plan + a build that writes a
# valid SPA), used by test_prototype_render_valid_offline. Defined after the class
# only for readability; referenced via the module-level name.
_VALID_PROTOTYPE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Tasks</title></head>
<body>
<nav>
  <a class="nav-item" href="#/dashboard">Dashboard</a>
  <a class="nav-item" href="#/tasks">Tasks</a>
</nav>
<section data-page="dashboard" class="is-active">
  <button onclick="addTask()">Add</button>
</section>
<section data-page="tasks">Tasks page</section>
<script>
var routes = { dashboard: "#/dashboard", tasks: "#/tasks" };
function addTask(){ console.log("add"); }
function go(id){
  var secs = document.querySelectorAll("[data-page]");
  for (var i = 0; i < secs.length; i++){ secs[i].classList.remove("is-active"); }
  var el = document.querySelector('[data-page="' + id + '"]');
  if (el){ el.classList.add("is-active"); }
}
var navs = document.querySelectorAll(".nav-item");
for (var j = 0; j < navs.length; j++){
  navs[j].addEventListener("click", function(e){
    e.preventDefault();
    go(this.getAttribute("href").slice(2));
  });
}
</script>
</body></html>"""


def _valid_prototype_factory(agent_id: str) -> ScriptedFakeChatModel:
    """Per-agent factory for a RENDER-VALID prototype build (overrides plan + build).

    A SINGLE Task 1 (the full shell, so the build loop runs once) + a build that
    writes ``_VALID_PROTOTYPE_HTML`` via native write_file then report_task_complete;
    every other agent reuses _scripts_for. The engine's per-task Both-validation
    passes (the HTML is valid), and the validator extracts + re-validates the HTML.
    """
    if agent_id == "prototype-plan":
        return ScriptedFakeChatModel(
            [
                _ScriptedTurn(
                    texts=["## Task 1: Build the full HTML shell\nEverything in one task.\n"],
                    usage=(40, 30),
                )
            ]
        )
    if agent_id == "prototype-build":
        return ScriptedFakeChatModel(
            [
                _ScriptedTurn(
                    texts=["Building the shell. "],
                    tool_calls=[
                        (
                            "write_file",
                            json.dumps(
                                {"file_path": "prototype.html", "content": _VALID_PROTOTYPE_HTML}
                            ),
                            "c_wf",
                        ),
                        (
                            "report_task_complete",
                            json.dumps(
                                {"task_number": 1, "task_title": "Shell", "summary": "built"}
                            ),
                            "c_rtc",
                        ),
                    ],
                    usage=(50, 20),
                ),
                _ScriptedTurn(texts=["Done."], usage=(10, 5)),
            ]
        )
    return ScriptedFakeChatModel(_scripts_for(agent_id))


# ===========================================================================
# HITL on/off — OFFLINE (scripted). These prove the gate seams T3's live HITL
# uses, deterministically + with zero Bedrock. Three mechanisms:
#   (a) gates-off                — no review_gate_ready, completes;
#   (b) engine inter-agent gate  — pause → resume → complete, via BOTH
#       auto_resume_gates=True (one-shot) AND an explicit manual_resume seam;
#   (c) runner tool-level gate   — capture_runner_stream + resume_paused_run.
# ===========================================================================


class TestOfflineHITL:
    @pytest.mark.asyncio
    async def test_gates_off_offline(self) -> None:
        """(a) gates-off: empty gate_agent_ids ⇒ no gate fires; run completes."""
        result = await _run_user_stories(
            model=_text_model(), fake_planner=True, gate_agent_ids=[]
        )
        assert result.gated is False
        assert "review_gate_ready" not in result.event_types()
        assert result.completed is True
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_gate_on_auto_resume_offline(self) -> None:
        """(b1) engine gate-on, one-shot: gate the first agent → pause → auto-approve."""
        result = await _run_user_stories(
            model=_text_model(),
            fake_planner=True,
            gate_agent_ids=[_DEFAULT_GATE_AGENT["user_stories"]],
        )
        types = result.event_types()
        assert result.gated is True
        assert types.count("review_gate_ready") == 1
        assert types.count("review_gate_approved") == 1
        assert result.completed is True
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_gate_on_custom_approver_offline(self) -> None:
        """(b2) the engine gate consults a caller-supplied approver (records the call)."""
        seen: list[str] = []

        def _approver(gate_key: str, data: dict):
            seen.append(gate_key)
            return True, None

        result = await _run_user_stories(
            model=_text_model(),
            fake_planner=True,
            gate_agent_ids=["domain-analyst"],
            gate_approver=_approver,
        )
        assert result.completed is True
        assert seen and seen[0].endswith(":domain-analyst")
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_gate_on_manual_resume_seam_offline(self) -> None:
        """(b3) explicit pause→resume seam: drive concurrently + manual_resume_engine_gate.

        With ``auto_resume_gates=False`` the engine BLOCKS at the gate inside its
        generator, so the drive is consumed as a concurrent task and the resume is
        issued from this coroutine via ``manual_resume_engine_gate`` — the engine's
        public review-response seam. The engine ``clear()``s the gate event when it
        reaches the gate, so we re-issue the resume in a small loop until the drive
        completes (each call sets the event; the post-clear set is the one that
        unblocks ``event.wait()``). Proves an EXPLICIT, non-auto pause/resume.
        """
        run_id = "phase8-manual-gate-001"
        gate_key = f"{run_id}:domain-analyst"
        drive_task = asyncio.create_task(
            _run_user_stories(
                model=_text_model(),
                fake_planner=True,
                gate_agent_ids=["domain-analyst"],
                auto_resume_gates=False,
                run_id=run_id,
            )
        )
        try:
            # Re-issue the approval until the drive completes; the engine clears the
            # gate event on entry, so the set that lands AFTER the clear is the one
            # that resumes it. Bounded so a wiring break fails fast (not hangs).
            for _ in range(2000):
                if drive_task.done():
                    break
                await manual_resume_engine_gate(gate_key, approved=True)
                await asyncio.sleep(0.01)
            result = await asyncio.wait_for(drive_task, timeout=30)
        finally:
            if not drive_task.done():
                drive_task.cancel()
        types = result.event_types()
        assert result.gated is True
        assert types.count("review_gate_ready") == 1
        # An explicitly-approved gate still emits review_gate_approved + completes.
        assert types.count("review_gate_approved") == 1
        assert result.completed is True
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_runner_tool_gate_offline(self) -> None:
        """(c) runner tool-level gate: armed runner PAUSES on the gated tool, then resumes.

        The Command(resume) seam (distinct from the engine inter-agent gate): a
        DeepAgentRunner with interrupt_on emits a ``gate`` event and never reaches
        ``done`` until ``resume_paused_run`` issues the approval, after which the
        gated tool executes and the graph reaches a terminal state.
        """
        from langchain_core.messages import ToolMessage
        from langchain_core.tools import tool
        from langgraph.checkpoint.memory import InMemorySaver

        from app.agents.deep_agent_runner import DeepAgentRunner

        @tool
        def report_task_complete(task_number: int, task_title: str, summary: str = "") -> str:
            """Report a task complete (gated for HITL in this test)."""
            return f"done {task_number} {task_title}"

        script = [
            _ScriptedTurn(
                texts=["working "],
                tool_calls=[
                    (
                        "report_task_complete",
                        json.dumps({"task_number": 1, "task_title": "Shell", "summary": "x"}),
                        "c1",
                    )
                ],
                usage=(11, 7),
            ),
            _ScriptedTurn(texts=["all done"], usage=(13, 5)),
        ]
        runner = DeepAgentRunner(
            system_prompt="worker",
            tools=[report_task_complete],
            model=ScriptedFakeChatModel(script),
            checkpointer=InMemorySaver(),
            thread_id="phase8-offline-runner-gate",
            interrupt_on={"report_task_complete": True},
        )

        events, gate = await capture_runner_stream(runner, "go")
        assert gate is not None, "armed runner must PAUSE at the gated tool"
        types = [e["type"] for e in events]
        assert "gate" in types and "done" not in types  # mutually exclusive

        final = await resume_paused_run(runner)
        tool_msgs = [
            m
            for m in final.get("messages", [])
            if isinstance(m, ToolMessage) and getattr(m, "name", "") == "report_task_complete"
        ]
        assert tool_msgs, "the approved gated tool must execute after resume"
        state = await runner._graph.aget_state(runner.config)
        assert state.next == (), "resumed graph must reach a terminal state"


# ===========================================================================
# Collection / skip self-check — offline: the file imports cleanly, the LIVE
# cases SKIP (not error), and the offline-proof machinery is wired.
# ===========================================================================


class TestCollectionSelfCheck:
    def test_live_gate_is_consistent_and_self_skipping(self) -> None:
        """The LIVE gate is correct: it SKIPS (with a reason) unless truly opted-in.

        The invariant under test is the GATE'S correctness, not the ambient env:
          * the harness must NEVER auto-flip ``RUN_LIVE_BEDROCK`` on import (opt-in
            is the caller's choice);
          * the live gate (``_LIVE_SKIP``) must agree with :func:`live_skip_reason`
            (the single source of truth the ``@requires_live`` mark uses);
          * when the gate is "skip", it carries a human-readable reason — so the
            LIVE cases skip cleanly rather than erroring deep in a model call. When
            the gate is "run" (opted in WITH creds), there is no reason and the live
            cases would execute against the real model.
        This passes whether or not ``RUN_LIVE_BEDROCK`` is set: with no creds the
        STS preflight still yields a skip reason; only a fully-opted-in-with-creds
        environment flips it to runnable.
        """
        from tests.agents.live_harness import live_enabled

        # ISS-011: do NOT assert strict ``_LIVE_SKIP == live_skip_reason()``. ``_LIVE_SKIP``
        # is captured ONCE at collection (line ~116); the runtime ``live_skip_reason()`` is
        # re-evaluated here. The old strict cross-time equality assumed the SSO session is
        # IMMORTAL across a multi-hour sweep — but the default-profile token can legitimately
        # expire mid-sweep (collection-valid → runtime-expired), which made this self-check
        # FAIL on a benign credential lapse. We now assert the GATE'S correctness, not
        # byte-equality across the run, and tolerate that drift. The runtime mid-sweep lapse
        # is handled by TestLiveHITL's per-test re-check (skip, not fail).

        # The @requires_live mark IS captured at collection — pairing it with the
        # collection-time _LIVE_SKIP is still valid (no cross-time drift there).
        assert requires_live.kwargs.get("reason") == (_LIVE_SKIP or "")

        # Gate correctness at the COLLECTION snapshot: a reason ⇒ not enabled (with a
        # human-readable message); no reason ⇒ enabled. (Stated against _LIVE_SKIP, the
        # value the @requires_live mark actually gates on, so this never depends on a
        # mid-run credential lapse.)
        if _LIVE_SKIP is None:
            # Fully opted in WITH resolvable creds at collection — the live cases WOULD run.
            assert requires_live.kwargs.get("reason") in ("", None)
        else:
            # Not opted in (or creds unavailable) at collection — the live cases SKIP.
            assert _LIVE_SKIP.strip(), "a skip must carry a human-readable reason"

        # Gate correctness at RUNTIME (the source of truth the per-test re-check uses):
        # a reason ⇒ not enabled (non-empty message); no reason ⇒ enabled. We assert
        # the gate's INTERNAL consistency at each point in time, NOT equality across time.
        runtime_reason = live_skip_reason()
        if runtime_reason is None:
            assert live_enabled() is True
        else:
            assert live_enabled() is False
            assert runtime_reason.strip(), "a runtime skip must carry a human-readable reason"

    def test_live_hitl_skips_on_mid_sweep_credential_expiry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ISS-011: a mid-sweep credential lapse SKIPS the live HITL re-check (never FAILS).

        Simulates the recurring fault offline (no Bedrock, no AWS): monkeypatch the
        ``live_skip_reason`` symbol the runtime re-check resolves (on the ``live_harness``
        MODULE) so it returns a non-None expiry reason — as if the default-profile SSO
        token expired AFTER collection decided the suite was runnable. The per-test guard
        must then raise ``pytest.skip.Exception`` (a SKIP outcome), NOT let the live
        assertions fail on 0 tokens. This pins the recurring-mode contract deterministically.
        """
        from tests.agents import live_harness

        expiry_reason = (
            "AWS credentials did not resolve: ExpiredTokenException: The security token "
            "included in the request is expired"
        )
        monkeypatch.setattr(live_harness, "live_skip_reason", lambda: expiry_reason)

        with pytest.raises(pytest.skip.Exception) as excinfo:
            _skip_if_creds_lapsed_mid_sweep()

        msg = str(excinfo.value)
        assert "aws sso login" in msg, "the skip must carry the re-run command"
        assert expiry_reason in msg, "the skip must surface the underlying expiry reason"

    def test_live_hitl_recheck_is_noop_when_creds_resolve(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ISS-011: when creds DO resolve at runtime, the re-check is a no-op (no skip).

        The complement of the expiry simulation — with ``live_skip_reason() is None`` the
        guard must NOT raise, so a genuinely-opted-in live run proceeds to the real model.
        """
        from tests.agents import live_harness

        monkeypatch.setattr(live_harness, "live_skip_reason", lambda: None)
        # Must not raise pytest.skip.Exception (nor anything else).
        _skip_if_creds_lapsed_mid_sweep()

    @pytest.mark.asyncio
    async def test_offline_proof_helpers_are_callable(self) -> None:
        """A tiny end-to-end check that the SAME helper + validator round-trips offline.

        The single most load-bearing assertion: one helper, driven scripted, produces
        a capture the T2 validator passes — i.e. the suite's offline path genuinely
        exercises the harness + validator (the live path is the SAME call with
        model=None).
        """
        result = await _run_user_stories(model=_text_model(), fake_planner=True)
        assert isinstance(result, CaptureResult)
        assert result.world == "engine" and result.label == "user_stories"
        assert validate_capture(result, require_tokens=False) == []
