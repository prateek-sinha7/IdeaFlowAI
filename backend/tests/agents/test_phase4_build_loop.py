"""Phase-4 verify gate (task #53) — the durable regression net for the per-task
isolated sub-agent build loop with engine-side Both-validation + a bounded,
INTERNAL fix-loop.

Phase 4 rewired ``ExecutionEngine._run_build_task_loop`` so the prototype build
runs **one isolated sub-agent per task** (each gets the current ``## Task N:``
block injected via ``=== CURRENT TASK ===`` and may ``read_file`` the
sandbox-written ``spec.md`` / ``design.md`` / ``tasks.md``), and after EVERY task
the engine runs Both-validation (``static_check`` + ``render_check``) with a
bounded ``N=2`` same-sub-agent INTERNAL fix-loop. The migration's invariant is
**UI-identical** — the user sees exactly ONE build per task; the validation +
fix is "richer build underneath". This module is the COMMITTED guard for that
contract (it survives the Phase-7 deletion of the legacy runtime + the transient
old-vs-new worktree parity harness).

It drives the REAL ``_run_build_task_loop`` (engine-level, offline) with a
controllable ``create_runner`` that hands each per-task / per-fix sub-agent a
*scripted* ``BaseChatModel`` (the proven ``ScriptedFakeChatModel`` recipe from
``tests/agents/_scripted_model.py``) over a REAL ``DeepAgentRunner`` + a temp
``RunSandbox`` — so the native ``deepagents`` filesystem tools, the real
validators, and the real fix-loop all execute. No network, no Bedrock.

THE REAL build protocol this test models (discovered + on record for #53):
  The native ``deepagents`` ``FilesystemBackend.write_file`` **refuses to
  overwrite an existing file** ("Cannot write to … because it already exists.
  Read and then make an edit, or write to a new path."). The Phase-4 design
  relies on exactly this: **Task 1 = the HTML shell via ``write_file``**; **Tasks
  2..N + every fix = ``edit_file``** on the existing ``prototype.html`` (the
  ``prototype-build`` prompt and the fix-loop message both instruct ``edit_file``).
  The scripted models here therefore use ``write_file`` for task 1 and
  ``edit_file`` for every later task / fix — modelling the production protocol,
  not papering over it.

Assertion groups (mapping to the task #53 checklist):
  1. ``TestReferenceFiles`` — after the loop the sandbox holds ``spec.md`` (=
     specify output), ``design.md`` (ACTIVE TEMPLATE + ACTIVE DESIGN SYSTEM
     headers from ``od_context``) and ``tasks.md`` (= plan output).
  2. ``TestPerTaskInjection`` — each task's ``prototype-build`` context carries
     ``=== CURRENT TASK ===`` with ONLY that task's ``## Task N:`` block (task 2
     does not leak task 1's or task 3's block).
  3. ``TestAccumulationAndEvents`` — ``prototype.html`` grows across a shell+2-page
     build; ``task_loop_progress`` (per task) + ``task_progress`` (cumulative
     ``completed_count`` 1,2,3) emit with unchanged payload shapes; the streamed
     event-type vocabulary equals the documented pre-Phase-4 prototype set.
  4. ``TestInternalFixLoop`` — a defect ``static_check`` catches re-invokes the
     SAME sub-agent on a ``…:fix{n}`` thread (≤2) AND no extra
     ``agent_start``/``agent_complete``/``agent_chunk``/``tool_*`` for the fix
     reach the caller (build ``agent_complete`` count == #tasks, not #tasks+fixes);
     an unrepairable defect → exactly 2 attempts → a logged warning → the build
     still completes (never blocks).
  5. ``TestFinalValidity`` — the final ``prototype.html`` passes BOTH
     ``static_check`` and ``render_check`` (Chromium is available locally; the
     test skips the render assertion cleanly if it is not).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter

import pytest

from app.agents.deep_agent_runner import DeepAgentRunner
from app.agents.sandbox import RunSandbox
from app.agents.static_check import static_check
from app.agents.tools.runner_tools import report_task_complete
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn, _drive
from tests.agents.test_phase3_cutover_verify import (
    _DOCUMENTED_EVENT_TYPES,
    _REQUIRED_DATA_KEYS,
)


# ===========================================================================
# Shared HTML fixtures + scripted-turn builders (model the real build protocol)
# ===========================================================================

# A valid SPA shell with a slot per page that later tasks edit into. nav↔sections
# resolve, routes map complete, first page is-active, route() handler defined —
# i.e. it passes static_check AND render_check on its own (the control shell).
_SHELL = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>App</title>"
    "<style>:root{--bg:#fff;--fg:#111}[data-page]{display:none}"
    "[data-page].is-active{display:block}</style></head><body>"
    "<nav class=\"sidebar\">"
    "<a class=\"nav-item\" href=\"#/dashboard\">Dashboard</a>"
    "<a class=\"nav-item\" href=\"#/reports\">Reports</a>"
    "</nav><main>"
    "<section data-page=\"dashboard\" class=\"is-active\"><h1>Dashboard</h1><!--DASHBOARD_SLOT--></section>"
    "<section data-page=\"reports\"><!--REPORTS_SLOT--></section>"
    "</main><script>"
    "const routes={dashboard:'#/dashboard',reports:'#/reports'};"
    "function route(){var id=(location.hash||'#/dashboard').slice(2);"
    "document.querySelectorAll('[data-page]').forEach(function(e){"
    "e.classList.toggle('is-active',e.dataset.page===id);});}"
    "window.addEventListener('hashchange',route);"
    "window.addEventListener('DOMContentLoaded',route);"
    "</script></body></html>"
)


def _rtc(task_number: int, title: str) -> tuple[str, str, str]:
    """A ``report_task_complete`` tool-call tuple carrying the progress args the
    engine reads for ``task_progress``."""
    return (
        "report_task_complete",
        json.dumps({"task_number": task_number, "task_title": title, "summary": f"did {task_number}"}),
        f"rtc_{task_number}",
    )


def _write_shell_turn(task_number: int = 1, title: str = "Shell") -> _ScriptedTurn:
    """Task-1 turn: ``write_file`` the shell (the only task allowed to write —
    later tasks must ``edit_file`` the now-existing file) + ``report_task_complete``."""
    return _ScriptedTurn(
        texts=["building shell "],
        tool_calls=[
            ("write_file", json.dumps({"file_path": "prototype.html", "content": _SHELL}), "wf_shell"),
            _rtc(task_number, title),
        ],
        usage=(20, 8),
    )


def _edit_slot_turn(
    task_number: int, title: str, slot: str, new_html: str
) -> _ScriptedTurn:
    """A later-task turn: ``edit_file`` a slot comment into page content (grows the
    document) + ``report_task_complete``."""
    return _ScriptedTurn(
        texts=[f"filling {title} "],
        tool_calls=[
            (
                "edit_file",
                json.dumps({"file_path": "prototype.html", "old_string": slot, "new_string": new_html}),
                f"ed_{task_number}",
            ),
            _rtc(task_number, title),
        ],
        usage=(15, 6),
    )


def _final_text_turn() -> _ScriptedTurn:
    """The sub-agent's wrap-up turn (no tool calls)."""
    return _ScriptedTurn(texts=["done."], usage=(3, 2))


_OD_CONTEXT = {
    "template_body": "## Workflow\nUse .card / .grid. Build into <section data-page>.",
    "template_id": "web-prototype",
    "ds_id": "acme-ds",
    "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;}",
    "craft_block": "Wire every nav link.",
    "is_design_system_required": True,
}


# ===========================================================================
# Engine harness — drive the REAL _run_build_task_loop offline.
# ===========================================================================


def _fresh_engine(monkeypatch, tmp_path):
    """An ``ExecutionEngine`` + per-run ``ExecutionContext`` wired for an offline
    ``_run_build_task_loop`` run.

    Mirrors the neutralizers ``_scripted_model`` / ``TestCumulativeTaskProgress``
    apply: a temp ``RUNS_ROOT`` (the real ``/app/runs`` is absent locally), a
    no-op artifact store (the fake run_id has no ``workflow_runs`` row), and the
    per-run state ``execute()`` constructs — now on the threaded ``ExecutionContext``
    (CTX-01/CTX-02), not the engine singleton. Returns ``(engine_mod, engine, ectx)``;
    callers thread ``ectx`` into ``_run_build_task_loop`` and read ``ectx.*`` state.
    """
    import agents.execution_engine.engine as engine_mod
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "RUNS_ROOT", str(tmp_path))

    engine = engine_mod.ExecutionEngine()
    ectx = engine_mod.ExecutionContext(
        run_id="phase4-build",
        owner_id="anon",
        gate_agent_ids=[],        # suppress the inter-agent review gate
        od_context=dict(_OD_CONTEXT),
    )

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]
    return engine_mod, engine, ectx


def _install_scripted_runner_factory(monkeypatch, engine_mod, *, turns_for):
    """Replace ``engine.create_runner`` with one that returns a REAL
    ``DeepAgentRunner`` over a scripted model, and RECORD every call.

    ``turns_for(agent_id, thread_id, is_fix, task_num)`` returns the scripted
    ``_ScriptedTurn`` list for that sub-agent invocation. Records
    ``(agent_id, thread_id)`` so tests can assert which threads ran (per-task
    ``…:N`` vs internal fix ``…:N:fix{n}``).
    """
    calls: list[tuple[str, str]] = []
    # The build loop calls _run_agent (which calls create_runner) once per task,
    # in order; fix sub-agents are created with a ":fix" thread by the loop. A
    # per-task counter lets the script vary by task number (the runner gets the
    # FILTERED ctx that strips _build_task_number, so we track it here).
    task_counter = {"n": 0}

    def _factory(agent_id, ctx, **kw):
        thread_id = kw.get("thread_id") or ""
        calls.append((agent_id, thread_id))
        is_fix = ":fix" in thread_id
        if is_fix:
            task_num = task_counter["n"]
        else:
            task_counter["n"] += 1
            task_num = task_counter["n"]
        rs = RunSandbox(ctx.user_id or "anon", ctx.run_id)
        rs.ensure()
        return DeepAgentRunner(
            system_prompt="build agent",
            tools=[report_task_complete],
            model=ScriptedFakeChatModel(turns_for(agent_id, thread_id, is_fix, task_num)),
            run_sandbox=rs,
            checkpointer=kw.get("checkpointer"),
            thread_id=thread_id,
        )

    monkeypatch.setattr(engine_mod, "create_runner", _factory)
    return calls


def _build_spec():
    from agents.registry import get_pipeline_agents

    return next(
        s for s in get_pipeline_agents("prototype") if s.id == "prototype-build"
    )


def _seed_typed(ectx, seeds: dict[str, str]) -> None:
    """Seed upstream agent content into the typed ArtifactGraph (the SOLE source
    since the prior-agent output mirror was deleted in 05-07). Tests pass the same
    ``{producer_agent: content}`` map they used to hand the loop as a dict."""
    for producer_agent, content in seeds.items():
        ectx.artifacts.write_ref(
            run_id=ectx.run_id,
            owner_id=ectx.owner_id,
            workspace_id=ectx.workspace_id,
            kind="html_file" if producer_agent == "prototype-build" else "text",
            producer_step=producer_agent,
            producer_agent=producer_agent,
            task_id=None,
            content=content,
            location=f"artifact_refs/{producer_agent}",
        )


async def _run_loop(engine, build_spec, run_id, upstream_outputs, sandbox, ectx):
    """Drive the REAL ``_run_build_task_loop`` and collect the yielded events."""
    _seed_typed(ectx, upstream_outputs)
    events: list[dict] = []
    async for ev in engine._run_build_task_loop(
        build_spec, 2, [build_spec], "Build me a task manager.",
        sandbox, run_id, "prototype", {},
        None, None, None, [], None,
        ectx,
    ):
        events.append(ev)
    return events


def _plan(n_tasks: int) -> str:
    """A planner output with ``n_tasks`` distinctively-bodied ``## Task N:`` headers."""
    blocks = ["## Task 1: Build the HTML shell\nCreate the skeleton. MARKER_1 only.\n"]
    for i in range(2, n_tasks + 1):
        blocks.append(f"## Task {i}: Fill page {i}\nAdd page {i} content. MARKER_{i} only.\n")
    return "\n".join(blocks)


# ===========================================================================
# Group 1 — reference files (spec.md / design.md / tasks.md)
# ===========================================================================


class TestReferenceFiles:
    """The loop writes spec.md / design.md / tasks.md to the run sandbox ONCE so
    every per-task (and fix) sub-agent can ``read_file`` them."""

    @pytest.mark.asyncio
    async def test_reference_files_written_with_expected_content(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)

        def turns_for(agent_id, thread_id, is_fix, task_num):
            # Single clean task — reference-file writing happens before any task.
            return [_write_shell_turn(1, "Shell"), _final_text_turn()]

        _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "ref-files-run"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()

        spec_text = "# Specification\nThe app manages tasks.\n## Architecture\nSPA, hash routing."
        accumulated = {"prototype-specify": spec_text, "prototype-plan": _plan(1)}

        await _run_loop(engine, _build_spec(), run_id, accumulated, sandbox, ectx)

        # spec.md == the specify agent's output.
        assert sandbox.read("spec.md") == spec_text
        # tasks.md == the planner's output.
        assert sandbox.read("tasks.md") == _plan(1)
        # design.md carries BOTH headers (template + design system) from od_context,
        # each tagged with its id, followed by its body.
        design = sandbox.read("design.md") or ""
        assert "# ACTIVE TEMPLATE (web-prototype)" in design
        assert _OD_CONTEXT["template_body"] in design
        assert "# ACTIVE DESIGN SYSTEM (acme-ds)" in design
        assert _OD_CONTEXT["ds_body"] in design

    @pytest.mark.asyncio
    async def test_design_md_degrades_gracefully_with_no_design_system(
        self, tmp_path, monkeypatch
    ) -> None:
        """A run with a template but NO design system still gets a template-only
        design.md (per the engine's "include a header only if its body is present")."""
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)
        ectx.od_context = {
            "template_body": "## Workflow\nTemplate only.",
            "template_id": "tpl-x",
            # no ds_body / ds_id
        }

        def turns_for(agent_id, thread_id, is_fix, task_num):
            return [_write_shell_turn(1, "Shell"), _final_text_turn()]

        _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "ref-files-nods"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()
        await _run_loop(
            engine, _build_spec(), run_id,
            {"prototype-specify": "spec", "prototype-plan": _plan(1)}, sandbox, ectx,
        )

        design = sandbox.read("design.md") or ""
        assert "# ACTIVE TEMPLATE (tpl-x)" in design
        assert "Template only." in design
        # No design-system header leaked in when there is no DS body.
        assert "ACTIVE DESIGN SYSTEM" not in design


# ===========================================================================
# Group 2 — per-task CURRENT TASK injection isolation
# ===========================================================================


class TestPerTaskInjection:
    """Each task's prototype-build context carries ``=== CURRENT TASK ===`` with
    ONLY that task's ``## Task N:`` block — no leakage across tasks."""

    @pytest.mark.asyncio
    async def test_current_task_block_is_isolated_per_task(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)

        # Spy on the REAL _build_context_message to capture the CURRENT TASK block
        # the build sub-agent is actually handed per task. The method now takes the
        # threaded ExecutionContext (ectx) — the spy mirrors the new signature.
        captured: list[str | None] = []
        orig_bcm = engine_mod.ExecutionEngine._build_context_message

        def spy(self, spec, ordered_agents, user_message, planning_context, ectx):
            msg = orig_bcm(self, spec, ordered_agents, user_message, planning_context, ectx)
            if getattr(spec, "id", None) == "prototype-build":
                m = re.search(
                    r"=== CURRENT TASK ===\n(.*?)\n=== END CURRENT TASK ===", msg, re.DOTALL
                )
                captured.append(m.group(1) if m else None)
            return msg

        monkeypatch.setattr(engine_mod.ExecutionEngine, "_build_context_message", spy)

        # Three tasks: shell (write) + two edits into the two slots.
        def turns_for(agent_id, thread_id, is_fix, task_num):
            if task_num == 1:
                return [_write_shell_turn(1, "Shell"), _final_text_turn()]
            slot = "<!--DASHBOARD_SLOT-->" if task_num == 2 else "<!--REPORTS_SLOT-->"
            return [
                _edit_slot_turn(task_num, f"Page {task_num}", slot, f"<p>page {task_num}</p>"),
                _final_text_turn(),
            ]

        _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "inject-run"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()
        await _run_loop(
            engine, _build_spec(), run_id,
            {"prototype-specify": "spec", "prototype-plan": _plan(3)}, sandbox, ectx,
        )

        assert len(captured) == 3, f"expected one CURRENT TASK block per task; got {captured}"
        for i, block in enumerate(captured, start=1):
            assert block is not None, f"task {i}: no === CURRENT TASK === marker injected"
            # The block names THIS task and carries its full `## Task i:` header+body.
            assert f"## Task {i}:" in block, f"task {i} block missing its own header: {block!r}"
            assert f"MARKER_{i}" in block, f"task {i} block missing its own marker: {block!r}"
            # No OTHER task's distinctive marker leaks into this task's block.
            for j in range(1, 4):
                if j != i:
                    assert f"MARKER_{j}" not in block, (
                        f"task {i} block LEAKED task {j}'s content: {block!r}"
                    )
                    assert f"## Task {j}:" not in block, (
                        f"task {i} block LEAKED task {j}'s header: {block!r}"
                    )


# ===========================================================================
# Group 3 — accumulation, progress events, and event-vocabulary parity
# ===========================================================================


class TestAccumulationAndEvents:
    """prototype.html grows across a multi-task build; the progress events keep
    their payload shapes; the streamed event-type set matches the documented
    pre-Phase-4 prototype vocabulary."""

    @pytest.mark.asyncio
    async def test_html_accumulates_and_progress_events_unchanged(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)

        # Shell + 2 page edits, each adding a sizeable chunk so the doc grows.
        page2 = "<p>" + ("dashboard widgets " * 8) + "</p>"
        page3 = "<p>" + ("reports tables " * 8) + "</p>"

        def turns_for(agent_id, thread_id, is_fix, task_num):
            if task_num == 1:
                return [_write_shell_turn(1, "Shell"), _final_text_turn()]
            if task_num == 2:
                return [
                    _edit_slot_turn(2, "Dashboard", "<!--DASHBOARD_SLOT-->", page2),
                    _final_text_turn(),
                ]
            return [
                _edit_slot_turn(3, "Reports", "<!--REPORTS_SLOT-->", page3),
                _final_text_turn(),
            ]

        _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "accum-run"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()

        # Seed upstream content into the typed graph (sole source since 05-07).
        _seed_typed(ectx, {"prototype-specify": "spec", "prototype-plan": _plan(3)})

        # Capture HTML length at each task_loop_progress boundary to prove growth.
        events: list[dict] = []
        lengths_at_task_start: list[int] = []
        async for ev in engine._run_build_task_loop(
            _build_spec(), 2, [_build_spec()], "brief",
            sandbox, run_id, "prototype", {}, None, None, None, [], None,
            ectx,
        ):
            events.append(ev)
            if ev["type"] == "task_loop_progress":
                lengths_at_task_start.append(len(sandbox.read("prototype.html") or ""))

        # ── prototype.html grew across the build (shell → +page2 → +page3). ──
        # At task 1 start the file is absent (0); each later task starts with a
        # strictly longer document than the previous task started with.
        assert lengths_at_task_start[0] == 0, "task 1 should start with no prototype.html yet"
        assert lengths_at_task_start[1] > 0, "after task 1 the shell must exist"
        assert lengths_at_task_start[2] > lengths_at_task_start[1], (
            f"prototype.html must grow task-over-task; got {lengths_at_task_start}"
        )
        final_html = sandbox.read("prototype.html") or ""
        assert len(final_html) > lengths_at_task_start[2], "the last edit must grow the doc further"
        assert "dashboard widgets" in final_html and "reports tables" in final_html

        # ── task_loop_progress: one per task, payload shape unchanged. ──
        tlp = [e for e in events if e["type"] == "task_loop_progress"]
        assert [e["data"]["task_number"] for e in tlp] == [1, 2, 3]
        for e in tlp:
            assert e["data"]["total_tasks"] == 3
            assert _REQUIRED_DATA_KEYS["task_loop_progress"] <= set(e["data"].keys())

        # ── task_progress: cumulative completed_count 1,2,3, payload shape unchanged. ──
        tp = [e for e in events if e["type"] == "task_progress"]
        assert [e["data"]["completed_count"] for e in tp] == [1, 2, 3], (
            "completed_count must accumulate cumulatively across the build loop"
        )
        for e in tp:
            assert _REQUIRED_DATA_KEYS["task_progress"] <= set(e["data"].keys())
            item = (e["data"]["completed_tasks"] or [])[0]
            assert set(item.keys()) == {"number", "title", "summary"}

    @pytest.mark.asyncio
    async def test_event_vocabulary_matches_pre_phase4_prototype_set(self) -> None:
        """The full streamed event-type set for a Phase-4 prototype build equals the
        documented pre-Phase-4 prototype vocabulary (no type added/dropped/reshaped).

        Reuses ``_scripted_model._drive`` (the same end-to-end ``engine.execute()``
        offline driver the Phase-3 gate uses) so this asserts the REAL outbound WS
        vocabulary, then checks it against the documented contract (the set the
        ``websocket.py`` drainer forwards verbatim) imported from the Phase-3 guard.
        """
        events = await _drive("prototype", "new")
        assert events, "prototype build produced no events"

        seen_types = {e.get("type") for e in events}
        # Every emitted type is in the documented vocabulary — nothing new slipped in.
        unknown = seen_types - _DOCUMENTED_EVENT_TYPES
        assert not unknown, f"Phase-4 build emitted UNDOCUMENTED event type(s): {sorted(unknown)}"

        # The build-specific events are present (the loop + progress contract).
        assert "task_loop_progress" in seen_types
        assert "task_progress" in seen_types
        assert {"agent_start", "agent_chunk", "tool_call", "tool_result", "agent_complete"} <= seen_types

        # Each load-bearing event still carries (at least) its documented data keys.
        for ev in events:
            required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
            if required is None:
                continue
            missing = required - set(ev.get("data", {}).keys())
            assert not missing, f"event '{ev['type']}' dropped required keys {sorted(missing)}"


# ===========================================================================
# Group 4 — Both-validation + bounded INTERNAL fix-loop
# ===========================================================================


class TestInternalFixLoop:
    """A defect static_check catches re-invokes the SAME sub-agent internally
    (≤2), the fix stream never reaches the caller, and an unrepairable defect
    stops after exactly 2 attempts with a warning while the build completes."""

    @pytest.mark.asyncio
    async def test_repairable_defect_is_fixed_internally_without_leaking_events(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)

        # Task 2 edits in a page that introduces a DEAD nav link (#/ghost) — a
        # defect static_check (and render_check) catch. The fix sub-agent edits
        # the ghost link out. (Shell is clean; task 1 never fails.)
        broken_page = "<h1>Reports</h1><a class=\"nav-item\" href=\"#/ghost\">Ghost</a>"
        ghost_anchor = "<a class=\"nav-item\" href=\"#/ghost\">Ghost</a>"

        def turns_for(agent_id, thread_id, is_fix, task_num):
            if is_fix:
                # The internal fix: remove the dead link via edit_file.
                return [
                    _ScriptedTurn(
                        texts=["fixing "],
                        tool_calls=[(
                            "edit_file",
                            json.dumps({"file_path": "prototype.html", "old_string": ghost_anchor, "new_string": "<p>fixed</p>"}),
                            "fix_ed",
                        )],
                        usage=(6, 3),
                    ),
                    _final_text_turn(),
                ]
            if task_num == 1:
                return [_write_shell_turn(1, "Shell"), _final_text_turn()]
            return [
                _edit_slot_turn(2, "Reports", "<!--REPORTS_SLOT-->", broken_page),
                _final_text_turn(),
            ]

        calls = _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "fix-run"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()
        events = await _run_loop(
            engine, _build_spec(), run_id,
            {"prototype-specify": "spec", "prototype-plan": _plan(2)}, sandbox, ectx,
        )

        # ── The internal fix sub-agent fired on the SAME task, a distinct :fix thread. ──
        fix_threads = [t for (_aid, t) in calls if ":fix" in t]
        assert fix_threads, f"a repairable defect must re-invoke the fix sub-agent; calls={calls}"
        assert all(t.endswith(":fix1") for t in fix_threads), (
            f"a one-shot fix must run on the :fix1 thread; got {fix_threads}"
        )
        assert len(fix_threads) == 1, f"the defect was repaired in one attempt; got {fix_threads}"
        # The fix thread targets the FAILING task (task 2), not task 1.
        assert all(":prototype-build:2:fix" in t for t in fix_threads), fix_threads

        # ── The fix stream is INTERNAL: NO extra agent_*/tool_* reached the caller. ──
        # 2 tasks → exactly 2 agent_start / 2 agent_complete (NOT 2+1 for the fix).
        counts = Counter(e["type"] for e in events)
        assert counts["agent_start"] == 2, f"fix must not emit agent_start; counts={dict(counts)}"
        assert counts["agent_complete"] == 2, (
            f"build agent_complete count must equal #tasks (2), not #tasks+fixes; counts={dict(counts)}"
        )
        # Two visible builds × (1 edit/write + 1 report_task_complete) = 4 tool_calls —
        # the fix's edit_file is NOT among them.
        assert counts["tool_call"] == 4, f"fix tool calls leaked into the stream; counts={dict(counts)}"
        assert counts["tool_result"] == 4, f"fix tool results leaked; counts={dict(counts)}"
        assert counts["agent_chunk"] == 4, f"fix chunks leaked; counts={dict(counts)}"
        # No fix-issued edit_file ever appears as a caller-visible tool_call.
        tool_call_names = [e["data"]["tool"] for e in events if e["type"] == "tool_call"]
        assert tool_call_names.count("edit_file") == 1, (
            f"only task 2's edit should be visible; the fix's edit must be internal; got {tool_call_names}"
        )

        # ── The repaired prototype.html is now clean. ──
        final_html = sandbox.read("prototype.html") or ""
        assert "#/ghost" not in final_html, "the fix must have removed the dead nav link"
        assert "fixed" in final_html
        assert static_check(final_html).ok, static_check(final_html).issues

    @pytest.mark.asyncio
    async def test_unrepairable_defect_stops_after_two_attempts_and_completes(
        self, tmp_path, monkeypatch, caplog
    ) -> None:
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)

        # A single task whose shell carries a permanent dead nav link, and a fix
        # that never repairs it (its edit targets a string that isn't present, so
        # prototype.html is unchanged and re-validation keeps failing).
        broken_shell = _SHELL.replace(
            "<a class=\"nav-item\" href=\"#/reports\">Reports</a>",
            "<a class=\"nav-item\" href=\"#/reports\">Reports</a>"
            "<a class=\"nav-item\" href=\"#/ghost\">Ghost</a>",
        )

        def turns_for(agent_id, thread_id, is_fix, task_num):
            if is_fix:
                # A no-op "fix": edits a string that does not exist → no change.
                return [
                    _ScriptedTurn(
                        texts=["attempting "],
                        tool_calls=[(
                            "edit_file",
                            json.dumps({"file_path": "prototype.html", "old_string": "STRING_THAT_DOES_NOT_EXIST", "new_string": "x"}),
                            "noop_fix",
                        )],
                        usage=(4, 2),
                    ),
                    _final_text_turn(),
                ]
            return [
                _ScriptedTurn(
                    texts=["shell "],
                    tool_calls=[
                        ("write_file", json.dumps({"file_path": "prototype.html", "content": broken_shell}), "wf"),
                        _rtc(1, "Shell"),
                    ],
                    usage=(20, 8),
                ),
                _final_text_turn(),
            ]

        calls = _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "unfix-run"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()

        with caplog.at_level(logging.WARNING, logger="agents.execution_engine.engine"):
            events = await _run_loop(
                engine, _build_spec(), run_id,
                {"prototype-specify": "spec", "prototype-plan": _plan(1)}, sandbox, ectx,
            )

        # ── Exactly 2 fix attempts (bounded N=2), on :fix1 then :fix2. ──
        fix_threads = [t for (_aid, t) in calls if ":fix" in t]
        assert len(fix_threads) == 2, f"unrepairable defect must try exactly twice; got {fix_threads}"
        assert any(t.endswith(":fix1") for t in fix_threads)
        assert any(t.endswith(":fix2") for t in fix_threads)

        # ── A warning is logged with the residual issue, and the build completes. ──
        assert any(
            "still failing after 2 fix attempt" in r.getMessage() for r in caplog.records
        ), "an unrepairable defect must log a 'still failing after 2' warning"
        # The build NEVER blocks: the one task still produced its agent_complete +
        # task_progress (the loop continued past the failed validation).
        counts = Counter(e["type"] for e in events)
        assert counts["agent_complete"] == 1, f"build must complete despite the defect; counts={dict(counts)}"
        assert counts["task_progress"] == 1
        # The defect remains (validation never blocked, just warned).
        assert "#/ghost" in (sandbox.read("prototype.html") or "")


# ===========================================================================
# Group 5 — final validity (static + render)
# ===========================================================================


class TestFinalValidity:
    """The final prototype.html passes BOTH static_check and render_check."""

    @pytest.mark.asyncio
    async def test_final_prototype_passes_static_and_render(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine, ectx = _fresh_engine(monkeypatch, tmp_path)

        page2 = "<p>dashboard content</p>"
        page3 = "<p>reports content</p>"

        def turns_for(agent_id, thread_id, is_fix, task_num):
            if task_num == 1:
                return [_write_shell_turn(1, "Shell"), _final_text_turn()]
            if task_num == 2:
                return [_edit_slot_turn(2, "Dashboard", "<!--DASHBOARD_SLOT-->", page2), _final_text_turn()]
            return [_edit_slot_turn(3, "Reports", "<!--REPORTS_SLOT-->", page3), _final_text_turn()]

        _install_scripted_runner_factory(monkeypatch, engine_mod, turns_for=turns_for)

        run_id = "final-run"
        engine._state_machine.transition(run_id, "generating")
        sandbox = RunSandbox("anon", run_id)
        sandbox.ensure()
        await _run_loop(
            engine, _build_spec(), run_id,
            {"prototype-specify": "spec", "prototype-plan": _plan(3)}, sandbox, ectx,
        )

        html_path = sandbox.path_for("prototype.html")
        assert html_path.is_file(), "the build must have produced prototype.html"

        # ── Static check: always available (stdlib), always asserted. ──
        sres = static_check(html_path)
        assert sres.ok, f"final prototype failed static_check: {sres.issues}"

        # ── Render check: assert pass when Chromium is available; skip cleanly if not. ──
        from app.agents.render_check import render_check

        rres = await render_check(html_path)
        if not rres.available:
            pytest.skip(f"render_check skipped — Chromium unavailable: {rres.note}")
        assert rres.ok, f"final prototype failed render_check: {rres.summary()}"
        # Every nav link activated a real section (no dead routes at render time).
        assert all(n.ok for n in rres.nav_results), (
            f"dead nav link(s) at render: {[n.href for n in rres.nav_results if not n.ok]}"
        )
        assert not rres.console_errors and not rres.page_errors
