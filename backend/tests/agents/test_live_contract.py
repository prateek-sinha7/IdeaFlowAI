"""tests/agents/test_live_contract.py — OFFLINE self-test for the T2 validator.

Proves the ``tests/agents/live_contract`` validator + cost watcher are correct by
driving the T1 harness with a ``ScriptedFakeChatModel`` (NOT live) — so it runs
with **zero Bedrock cost and no AWS credentials** and commits green. If the
validator is wrong here (passes a broken capture, or fails a faithful one), every
T3 live assertion that calls it inherits the bug.

It covers, all OFFLINE (``require_tokens=False`` — a scripted run's tokens are the
scripted usage, which is non-zero here but is NOT asserted as the live gate):

  * **happy path** — ``validate_capture`` returns EMPTY (pass) for a faithful
    capture of every world:
      - engine ``prototype`` (exercises the deliverable-validity registry's
        ``static_check`` + ``render_check`` path; the scripted build writes a
        VALID single-file SPA so the prototype HTML actually passes),
      - engine ``app_builder`` (a code-gen pipeline → ``filename:`` block rule),
      - engine ``user_stories`` (a text pipeline → non-empty rule),
      - ``chat`` (the 10-key FinalOutputModel + phase envelope),
      - ``handoff`` coding (PR path) AND test (no-PR path);
  * **broken captures the validator MUST catch** — drop a ``phase_end`` (chat
    envelope), inject an UNKNOWN event type (engine vocabulary), corrupt the
    prototype HTML (deliverable validity), strip a key from the chat
    FinalOutputModel, give test-mode handoff a PR (mode-shape), drop required
    envelope keys, and the ``require_tokens`` live gate on a zero-token capture;
  * **assert_capture** raises ``CaptureContractError`` carrying all failures;
  * **summarize_cost / assert_under_budget** — a one-and-many smoke + the soft
    ceiling.

No live model is ever run (``RUN_LIVE_BEDROCK`` is never set here).
"""

from __future__ import annotations

import copy
import json

import pytest

from tests.agents._scripted_model import (
    ScriptedFakeChatModel,
    _ScriptedTurn,
    _scripts_for,
)
from tests.agents.live_contract import (
    BudgetExceededError,
    CaptureContractError,
    assert_capture,
    assert_under_budget,
    summarize_cost,
    total_cost_usd,
    validate_capture,
)
from tests.agents.live_harness import (
    CaptureResult,
    TokenTotals,
    drive_chat,
    drive_engine_pipeline,
    drive_handoff,
)


# ---------------------------------------------------------------------------
# Scripted models.
# ---------------------------------------------------------------------------


def _text_model(t_in: int = 12, t_out: int = 7) -> ScriptedFakeChatModel:
    """A pure-text scripted model (one turn, with usage) reused by every agent."""
    return ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["scripted output. ", "line two."], usage=(t_in, t_out))]
    )


# A VALID single-file SPA prototype: nav links → sections, a routes map, an
# ``is-active`` page, and a defined inline handler — so it passes BOTH static_check
# AND render_check (verified by the prototype happy-path test). This is what a
# faithful LIVE prototype build produces; we script it so the offline validator
# exercises the real deliverable-validity path (NOT a stub that would fail).
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


def _valid_prototype_model_factory(agent_id: str) -> ScriptedFakeChatModel:
    """Per-agent factory for a prototype run whose HTML is render-valid.

    Overrides only ``prototype-plan`` (a SINGLE Task 1 = the full shell, so the
    build loop runs once) and ``prototype-build`` (writes ``_VALID_PROTOTYPE_HTML``
    via the native ``write_file`` then ``report_task_complete``); every other
    agent reuses the shared ``_scripts_for`` script. The engine's per-task
    Both-validation passes (the HTML is valid), and the deliverable read back is a
    ``filename:`` bundle whose ``prototype.html`` block the validator extracts.
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


# ---------------------------------------------------------------------------
# Shared fixtures — built once, reused across the happy-path + broken tests.
# (Module-scoped via simple async factories called per-test; each drive is cheap.)
# ---------------------------------------------------------------------------


async def _capture_user_stories() -> CaptureResult:
    return await drive_engine_pipeline(
        "user_stories", model=_text_model(), fake_planner=True
    )


async def _capture_app_builder() -> CaptureResult:
    return await drive_engine_pipeline(
        "app_builder",
        model=lambda aid: ScriptedFakeChatModel(_scripts_for(aid)),
        fake_planner=True,
    )


async def _capture_prototype_valid() -> CaptureResult:
    return await drive_engine_pipeline(
        "prototype", model=_valid_prototype_model_factory, fake_planner=True
    )


async def _capture_prototype_stub() -> CaptureResult:
    """A prototype run using the SHARED scripts — its HTML stub FAILS static_check.

    The stock ``_scripts_for('prototype-build')`` writes a minimal
    ``<section data-page='dashboard'>`` with NO ``is-active`` — a structurally
    invalid prototype. This is the natural 'corrupt prototype HTML' broken case.
    """
    return await drive_engine_pipeline(
        "prototype",
        model=lambda aid: ScriptedFakeChatModel(_scripts_for(aid)),
        fake_planner=True,
    )


async def _capture_chat() -> CaptureResult:
    # Mention every deliverable keyword so all phases activate (full envelope).
    msg = "Build a product with user stories, ppt, prototype and ui design."
    return await drive_chat(msg, mode="default", model=_text_model())


async def _capture_handoff_coding() -> CaptureResult:
    return await drive_handoff(mode="coding", model=_text_model())


async def _capture_handoff_test() -> CaptureResult:
    return await drive_handoff(mode="test", model=_text_model())


# ===========================================================================
# Happy path — validate_capture returns EMPTY for a faithful capture.
# ===========================================================================


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_engine_user_stories_passes(self) -> None:
        result = await _capture_user_stories()
        assert result.completed and result.error is None
        assert validate_capture(result, require_tokens=False) == []
        # Strict form is a no-op on a clean capture.
        assert_capture(result, require_tokens=False)

    @pytest.mark.asyncio
    async def test_engine_app_builder_codegen_passes(self) -> None:
        """Code-gen deliverable validity: the ``filename:`` block rule passes."""
        result = await _capture_app_builder()
        assert result.completed
        # The deliverable IS a filename: bundle (sandbox serialization).
        assert "```filename:" in (result.deliverable or "")
        assert validate_capture(result, require_tokens=False) == []

    @pytest.mark.asyncio
    async def test_engine_prototype_passes_static_and_render(self) -> None:
        """The prototype deliverable-validity path (static_check + render_check).

        The scripted build writes a render-valid SPA, so the validator's prototype
        rule extracts the HTML and BOTH checks pass — proving the registry's
        richest rule end-to-end (render_check runs for real locally; it skips
        gracefully if Chromium is unavailable, never a false failure).
        """
        result = await _capture_prototype_valid()
        assert result.completed and result.error is None
        types = result.event_types()
        assert "tool_call" in types and "task_progress" in types
        failures = validate_capture(result, require_tokens=False)
        assert failures == [], f"prototype should validate clean, got: {failures}"

    @pytest.mark.asyncio
    async def test_chat_passes(self) -> None:
        result = await _capture_chat()
        assert result.completed
        assert isinstance(result.final_output, dict)
        assert validate_capture(result, require_tokens=False) == []

    @pytest.mark.asyncio
    async def test_handoff_coding_passes(self) -> None:
        result = await _capture_handoff_coding()
        assert result.completed and result.label == "coding"
        assert validate_capture(result, require_tokens=False) == []

    @pytest.mark.asyncio
    async def test_handoff_test_passes(self) -> None:
        result = await _capture_handoff_test()
        assert result.completed and result.label == "test"
        assert validate_capture(result, require_tokens=False) == []

    @pytest.mark.asyncio
    async def test_token_consistency_holds_offline(self) -> None:
        """tokens.total == input+output is asserted even with require_tokens=False."""
        result = await _capture_user_stories()
        assert result.tokens.total == result.tokens.input + result.tokens.output
        assert validate_capture(result, require_tokens=False) == []


# ===========================================================================
# Broken captures — the validator MUST catch each defect.
# ===========================================================================


class TestBrokenCapturesCaught:
    @pytest.mark.asyncio
    async def test_dropped_phase_end_is_caught(self) -> None:
        """Drop a chat ``phase_end`` → unclosed/unbalanced phase envelope flagged."""
        result = await _capture_chat()
        assert validate_capture(result) == []  # clean first

        broken = copy.deepcopy(result)
        end_idxs = [i for i, e in enumerate(broken.events) if e.get("type") == "phase_end"]
        assert end_idxs, "expected the chat capture to have phase_end events"
        del broken.events[end_idxs[-1]]

        failures = validate_capture(broken)
        assert failures, "dropping a phase_end must be caught"
        assert any("phase" in f.lower() for f in failures), failures

    @pytest.mark.asyncio
    async def test_unknown_event_type_is_caught(self) -> None:
        """Inject an UNKNOWN event type into the engine stream → flagged as regression."""
        result = await _capture_user_stories()
        assert validate_capture(result) == []

        broken = copy.deepcopy(result)
        broken.events.insert(2, {"type": "frobnicate_widget", "data": {}})

        failures = validate_capture(broken)
        assert any("UNKNOWN event type" in f and "frobnicate_widget" in f for f in failures), (
            failures
        )

    @pytest.mark.asyncio
    async def test_corrupt_prototype_html_is_caught(self) -> None:
        """A prototype whose HTML fails static_check → deliverable-validity flagged.

        Uses the SHARED ``_scripts_for`` build, whose stub HTML has no ``is-active``
        section. The validator extracts that HTML and ``static_check`` rejects it.
        """
        result = await _capture_prototype_stub()
        assert result.completed  # the RUN completes; the DELIVERABLE is invalid
        failures = validate_capture(result, require_tokens=False)
        assert any("static_check" in f for f in failures), (
            f"a structurally-invalid prototype must be caught, got: {failures}"
        )

    @pytest.mark.asyncio
    async def test_corrupt_prototype_html_inline_is_caught(self) -> None:
        """Corrupt a VALID prototype capture's deliverable in place → caught.

        Belt-and-braces: mutate a known-good capture's deliverable to broken HTML
        and confirm the validator flips from pass → fail (isolating the deliverable
        rule from the rest of the capture).
        """
        result = await _capture_prototype_valid()
        assert validate_capture(result) == []

        broken = copy.deepcopy(result)
        # Replace the deliverable with HTML that has a dead nav link + no is-active.
        broken.deliverable = (
            '<!doctype html><html><body>'
            '<a class="nav-item" href="#/missing">Missing</a>'
            '<section data-page="home">home</section>'
            '</body></html>'
        )
        broken.final_output = broken.deliverable
        failures = validate_capture(broken)
        assert any("static_check" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_chat_final_output_missing_key_is_caught(self) -> None:
        """Strip a key from the chat FinalOutputModel → the 10-key check fails."""
        result = await _capture_chat()
        assert validate_capture(result) == []

        broken = copy.deepcopy(result)
        # Drop a key from BOTH the complete event data and the mirrored final_output.
        for ev in broken.events:
            if ev.get("type") == "complete" and isinstance(ev.get("data"), dict):
                ev["data"].pop("prototype", None)
        if isinstance(broken.final_output, dict):
            broken.final_output.pop("prototype", None)

        failures = validate_capture(broken)
        assert any("10" in f and "FinalOutputModel" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_chat_final_output_extra_key_is_caught(self) -> None:
        """An EXTRA key on the chat final output is also a contract violation."""
        result = await _capture_chat()
        broken = copy.deepcopy(result)
        for ev in broken.events:
            if ev.get("type") == "complete" and isinstance(ev.get("data"), dict):
                ev["data"]["surprise"] = {"unexpected": True}
        if isinstance(broken.final_output, dict):
            broken.final_output["surprise"] = {"unexpected": True}

        failures = validate_capture(broken)
        assert any("extra" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_test_mode_handoff_with_pr_is_caught(self) -> None:
        """Give a test-mode handoff a ``pr_created`` event + PR keys → mode-shape fails."""
        result = await _capture_handoff_test()
        assert validate_capture(result) == []

        broken = copy.deepcopy(result)
        # Inject a pr_created event (test mode must NOT have one).
        broken.events.insert(
            -1, {"type": "pr_created", "chunk": None, "section": None, "data": {"url": "x", "number": 9}}
        )
        # And smuggle PR keys into the pipeline_output.
        for ev in broken.events:
            if ev.get("type") == "pipeline_complete" and isinstance(ev.get("data"), dict):
                ev["data"]["pr_url"] = "x"
                ev["data"]["pr_number"] = 9
        if isinstance(broken.final_output, dict):
            broken.final_output["pr_url"] = "x"
            broken.final_output["pr_number"] = 9

        failures = validate_capture(broken)
        assert any("test-mode" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_coding_mode_handoff_without_pr_is_caught(self) -> None:
        """Remove the PR event/keys from a coding handoff → coding-shape fails."""
        result = await _capture_handoff_coding()
        broken = copy.deepcopy(result)
        broken.events = [e for e in broken.events if e.get("type") != "pr_created"]
        for ev in broken.events:
            if ev.get("type") == "pipeline_complete" and isinstance(ev.get("data"), dict):
                ev["data"].pop("pr_url", None)
                ev["data"].pop("pr_number", None)
                ev["data"].pop("coding_summary", None)
        if isinstance(broken.final_output, dict):
            broken.final_output.pop("pr_url", None)
            broken.final_output.pop("pr_number", None)
            broken.final_output.pop("coding_summary", None)

        failures = validate_capture(broken)
        assert any("coding-mode" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_missing_envelope_key_is_caught(self) -> None:
        """An event missing a required envelope key is flagged (chat WS envelope)."""
        result = await _capture_chat()
        broken = copy.deepcopy(result)
        # Drop the 'section' key from one stream event.
        for ev in broken.events:
            if ev.get("type") == "stream":
                ev.pop("section", None)
                break
        failures = validate_capture(broken)
        assert any("missing required key" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_empty_events_is_caught(self) -> None:
        """An empty event stream fails the common 'events non-empty' check."""
        empty = CaptureResult(world="engine", label="user_stories")
        failures = validate_capture(empty)
        assert any("no events captured" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_unknown_world_is_caught(self) -> None:
        """An unrecognized world fails fast with a clear message."""
        bogus = CaptureResult(world="martian", label="x", events=[{"type": "a", "data": {}}])
        failures = validate_capture(bogus)
        assert any("unknown capture world" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_missing_terminal_without_error_is_caught(self) -> None:
        """A non-errored engine run that never reached pipeline_complete is flagged."""
        result = await _capture_user_stories()
        broken = copy.deepcopy(result)
        broken.events = [e for e in broken.events if e.get("type") != "pipeline_complete"]
        broken.completed = False
        failures = validate_capture(broken, require_completed=False)
        assert any("missing terminal event" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_require_tokens_flags_zero_token_capture(self) -> None:
        """The LIVE token gate: require_tokens=True on a 0-token capture fails.

        Built by zeroing a clean capture's tokens (a scripted PURE-TEXT live-style
        run can report 0 — the T1 NOTE — so the gate is opt-in). With
        require_tokens=False the same capture passes; with True it fails on tokens.
        """
        result = await _capture_user_stories()
        zeroed = copy.deepcopy(result)
        zeroed.tokens = TokenTotals(input=0, output=0, total=0)
        zeroed.per_agent_tokens = {}

        # Offline (require_tokens=False) — still valid (tokens not gated).
        assert validate_capture(zeroed, require_tokens=False) == []
        # Live gate (require_tokens=True) — fails specifically on tokens.
        failures = validate_capture(zeroed, require_tokens=True)
        assert any("non-zero usage" in f for f in failures), failures

    @pytest.mark.asyncio
    async def test_require_completed_flags_incomplete(self) -> None:
        """require_completed=True flags a capture whose completed flag is False."""
        result = await _capture_user_stories()
        broken = copy.deepcopy(result)
        broken.completed = False
        failures = validate_capture(broken, require_completed=True)
        assert any("result.completed is False" in f for f in failures), failures


# ===========================================================================
# assert_capture — strict raising form.
# ===========================================================================


class TestAssertCapture:
    @pytest.mark.asyncio
    async def test_assert_capture_raises_with_all_failures(self) -> None:
        result = await _capture_user_stories()
        broken = copy.deepcopy(result)
        broken.events.insert(1, {"type": "bogus_one", "data": {}})
        broken.events.insert(2, {"type": "bogus_two", "data": {}})

        with pytest.raises(CaptureContractError) as ei:
            assert_capture(broken)
        err = ei.value
        # Both unknown types surface (assert collects ALL failures).
        assert len(err.failures) >= 2
        assert err.world == "engine"
        assert "bogus_one" in str(err) and "bogus_two" in str(err)

    @pytest.mark.asyncio
    async def test_assert_capture_noop_on_clean(self) -> None:
        result = await _capture_handoff_coding()
        assert_capture(result, require_tokens=False)  # must not raise


# ===========================================================================
# Cost watcher — summarize_cost / total_cost_usd / assert_under_budget.
# ===========================================================================


class TestCostWatcher:
    @pytest.mark.asyncio
    async def test_summarize_cost_single_capture(self) -> None:
        result = await _capture_user_stories()
        table = summarize_cost(result)
        assert "Token / cost summary" in table
        assert "GRAND TOTAL" in table
        assert "user_stories" in table
        # The grand-total token count reconciles with the capture's own total.
        assert f"{result.tokens.total:,}" in table

    @pytest.mark.asyncio
    async def test_summarize_cost_many_captures(self) -> None:
        rs = [
            await _capture_user_stories(),
            await _capture_app_builder(),
            await _capture_chat(),
            await _capture_handoff_coding(),
        ]
        table = summarize_cost(rs)
        assert table.count("[engine:") >= 2  # user_stories + app_builder
        assert "[chat:default]" in table
        assert "[handoff:coding]" in table
        # GRAND TOTAL reconciles with total_cost_usd().
        assert f"${total_cost_usd(rs):.4f}" in table

    @pytest.mark.asyncio
    async def test_total_cost_matches_capture_cost(self) -> None:
        result = await _capture_user_stories()
        assert total_cost_usd(result) == pytest.approx(result.cost_usd())
        assert total_cost_usd([result, result]) == pytest.approx(2 * result.cost_usd())

    @pytest.mark.asyncio
    async def test_assert_under_budget_passes_under_ceiling(self) -> None:
        result = await _capture_user_stories()
        # Scripted tokens are tiny → well under a 1-cent ceiling.
        total = assert_under_budget([result], max_usd=0.01)
        assert total == pytest.approx(result.cost_usd())
        assert total <= 0.01

    @pytest.mark.asyncio
    async def test_assert_under_budget_raises_over_ceiling(self) -> None:
        """A capture with large tokens trips the soft ceiling."""
        big = CaptureResult(
            world="engine",
            label="user_stories",
            tokens=TokenTotals(input=5_000_000, output=5_000_000, total=10_000_000),
        )
        # 5M in * $0.25/M + 5M out * $1.25/M = $1.25 + $6.25 = $7.50.
        with pytest.raises(BudgetExceededError) as ei:
            assert_under_budget([big], max_usd=1.00)
        assert ei.value.total_usd == pytest.approx(7.50)
        assert ei.value.max_usd == 1.00
        # The table is attached to the error for triage.
        assert "GRAND TOTAL" in str(ei.value)

    @pytest.mark.asyncio
    async def test_summarize_cost_handles_zero_tokens(self) -> None:
        """A zero-token capture renders without error (e.g. a handoff capture)."""
        result = await _capture_handoff_coding()  # handoff tokens are TokenTotals()
        assert result.tokens == TokenTotals()
        table = summarize_cost(result)
        assert "$   0.0000" in table or "$0.0000" in table


class TestClarifyVocabularyOffline:
    """Regression: a live planner may return CLARIFY_REQUIRED → the engine emits
    questionnaire_ready/questionnaire_complete. Those are legitimate engine events;
    the validator must NOT flag them as UNKNOWN. (The first live smoke surfaced this
    gap — offline never emitted clarify events because the planner was faked.)"""

    @pytest.mark.asyncio
    async def test_clarify_events_validate_clean(self) -> None:
        from agents.execution_engine.engine import ExecutionEngine

        ctx = ExecutionEngine()._default_planning_context(
            "Build user stories for a web app."
        )
        ctx["pipeline_type"] = "user_stories"
        ctx["execution_gate"] = "CLARIFY_REQUIRED"
        ctx["missing_information"] = ["topic", "target_audience"]

        result = await drive_engine_pipeline(
            "user_stories",
            model=lambda aid: ScriptedFakeChatModel(_scripts_for(aid)),
            planner_result=(ctx, "CLARIFY_REQUIRED"),
        )
        # Clarify actually happened in this capture ...
        assert "questionnaire_ready" in result.event_types()
        assert "questionnaire_complete" in result.event_types()
        # ... and the validator accepts the clarify events (no UNKNOWN-type failures).
        failures = validate_capture(result, require_tokens=False)
        assert failures == [], f"validator flagged clarify events: {failures}"
