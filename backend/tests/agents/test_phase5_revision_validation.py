"""Phase-5 verify gate (task T6) — the durable, deterministic, OFFLINE regression
net for the integrated ``prototype_revision`` behavior that tasks T1–T5 landed:

  * **Parent-context seeding** — ``execute(..., parent_run_id=<id>)`` reads
    ``spec.md`` / ``design.md`` / ``tasks.md`` from the PARENT run's sandbox
    (``RunSandbox(user_id, parent_run_id)``) and writes them into THIS revision
    run's sandbox so the revision agent (and its internal fix sub-agent) can
    ``read_file`` the original requirements + design system. Graceful degrade
    (log + proceed on HTML + instruction only) when the parent is absent.

  * **Post-revision validation + bounded INTERNAL fix-loop** — after the visible
    ``prototype-revision-agent`` edits ``prototype.html``, the engine computes a
    **baseline** (``static_check`` + ``render_check``) on the seeded ORIGINAL
    *before* the edit, then runs the generalized
    ``_run_validation_fix_loop(agent_id="prototype-revision-agent",
    baseline_static, baseline_console, user_instruction, label="revision")``.
    The fix-loop feeds back **regressions** (NEW static/render issues vs. the
    baseline) ∪ **hard render-breakage** (page errors / dead nav), while
    **ignoring pre-existing static nits** captured in the baseline. It is bounded
    ``N=2``, INTERNAL (non-yielding → emits NO new events), and never blocks.

THE TWO INVARIANTS THIS GUARDS (plan §3): the WS/UI event contract is
byte-identical to pre-migration (the fix-loop adds NO event types and leaks NO
phantom-second-agent stream), and the revision deliverable is the validated
edited ``prototype.html``.

────────────────────────────────────────────────────────────────────────────
DESIGN — how the scripted revision model edits prototype.html + how the fix
message is captured (the recipe the task mandates)
────────────────────────────────────────────────────────────────────────────
The engine PRE-SEEDS the ORIGINAL ``prototype.html`` into the sandbox before the
revision agent runs (``engine.py`` ``execute()`` ``prototype_revision`` block),
so — exactly like a real revision and like the Phase-4 build's tasks-2+ — the
agent and the fix sub-agent must use ``edit_file`` (native ``write_file`` REFUSES
to overwrite an existing file; see ``test_phase4_build_loop.py``'s protocol note).

The model is a STATEFUL scripted ``BaseChatModel`` (the proven
``_scripted_model.ScriptedFakeChatModel`` recipe) whose turns are chosen by the
factory per invocation. The deepagents loop calls the model, and the fix-loop
re-invokes a FRESH ``create_runner`` (a NEW model instance) on a distinct
``…:revision:fix{n}`` thread, so we cannot use one mutable counter safely across
both. Instead the patched ``create_runner`` routes by ``is_fix = ":fix" in
thread_id`` and hands the visible vs. the fix invocation their own scripted
turns. Each model is a ``_RecordingScriptedModel`` that appends the inbound
``messages`` of every ``_stream`` call to a shared ``transcripts`` log keyed by
``(agent_id, thread_id)`` — so the test reads back the EXACT fix message the fix
sub-agent received and asserts on it (it must contain the regression, must NOT
contain the baselined nit, and must re-inject the user's revision instruction).

The models edit ``prototype.html`` for real via ``edit_file`` tool calls over a
REAL ``DeepAgentRunner`` + a temp ``RunSandbox`` (native deepagents filesystem
tools execute), so the engine's post-fix read-back is end-to-end genuine.

DETERMINISM / no Chromium: the regression + the pre-existing nit are both
**pure-static** issues (a routes-map "extra id" and a routes-map "missing page
id" respectively — neither is a dead nav link or a page error), so ``static_check``
catches them with the stdlib alone and ``render_check`` (if Chromium is present)
stays GREEN on them — the selection is byte-identical whether or not a browser is
available (verified against ``_select_issues_to_fix``). Render-dependent
assertions degrade to a clean skip.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

import pytest

from app.agents.deep_agent_runner import DeepAgentRunner
from app.agents.sandbox import RunSandbox
from app.agents.static_check import static_check
from app.agents.tools.runner_tools import report_task_complete
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn
from tests.agents.test_phase3_cutover_verify import (
    _DOCUMENTED_EVENT_TYPES,
    _REQUIRED_DATA_KEYS,
)

# ===========================================================================
# HTML fixtures — a clean SPA carrying a KNOWN pre-existing static nit, and the
# regression the revision introduces. Both are PURE-STATIC (no dead nav / no
# page error), so static_check is the deterministic primary signal and a real
# render_check stays GREEN on them (no browser dependency in the assertions).
# ===========================================================================

# Routes-map literals we swap with edit_file (anchors must be EXACT + UNIQUE in
# the document — the native edit_file replaces one occurrence).
_ROUTES_ORIGINAL = 'const routes={dashboard:"#/dashboard"};'
_ROUTES_WITH_GHOST = 'const routes={dashboard:"#/dashboard",ghost:"#/ghost"};'

# A valid SPA shell. nav↔sections resolve (dashboard + settings both have a nav
# link and a section), the first page is is-active, route() is defined. The ONE
# pre-existing static ISSUE static_check flags here is a routes-map "missing page
# id 'settings'": the `settings` section has a nav link + a section but NO key in
# the routes map. That is a pure-static nit (NOT a dead nav, NOT a render break)
# → it lands in the fix-loop's baseline and must be IGNORED by the fix.
_ORIGINAL_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>App</title>'
    "<style>[data-page]{display:none}[data-page].is-active{display:block}</style></head><body>"
    '<nav class="sidebar">'
    '<a class="nav-item" href="#/dashboard">Dashboard</a>'
    '<a class="nav-item" href="#/settings">Settings</a>'
    "</nav><main>"
    '<section data-page="dashboard" class="is-active"><h1>Dashboard</h1></section>'
    '<section data-page="settings"><h1>Settings</h1></section>'
    "</main><script>"
    f"{_ROUTES_ORIGINAL}"
    "function route(){var id=(location.hash||'#/dashboard').slice(2);"
    "document.querySelectorAll('[data-page]').forEach(function(e){"
    "e.classList.toggle('is-active',e.dataset.page===id);});}"
    "window.addEventListener('hashchange',route);"
    "window.addEventListener('DOMContentLoaded',route);"
    "</script></body></html>"
)

# The PRE-EXISTING static nit static_check reports on _ORIGINAL_HTML (verified in
# the task probe). It is the EXACT issue string the baseline captures.
_PREEXISTING_NIT = (
    "routes map missing page id 'settings' "
    '(section <section data-page="settings"> has no routes entry)'
)

# quick-260701-erg / STATIC-ROUTER-DEAD: the ORIGINAL fixture navigates to
# ``#/settings`` (a real <section data-page="settings">) but the routes map omits it,
# so the new routes-map RESOLUTION cross-check flags it as ROUTER-DEAD — a SECOND
# pre-existing nit on the same fixture. Like the routes-map-missing nit it predates the
# revision edit, so it is baselined (excluded from the fix-loop) alongside it.
_PREEXISTING_ROUTER_DEAD = (
    "router-dead nav link: nav route target 'settings' has a "
    '<section data-page="settings"> but no routes-map entry — '
    "the hash router will not reach it"
)

# The full set of pre-existing (baselined) static nits on _ORIGINAL_HTML.
_PREEXISTING_NITS = {_PREEXISTING_NIT, _PREEXISTING_ROUTER_DEAD}

# The NEW static REGRESSION the revision introduces by adding a `ghost` key to the
# routes map with no matching <section data-page="ghost"> (pure static; render
# stays green). The EXACT issue string static_check reports for it.
_REGRESSION_ISSUE = (
    "routes map has extra id 'ghost' with no matching "
    '<section data-page="ghost">'
)

# The revision request the user made (re-injected into the fix prompt).
_USER_INSTRUCTION = "Add a ghost route to the navigation map."

# The frontend's wire markers the engine extracts the HTML + instruction from.
_REVISION_MESSAGE = (
    "=== EXISTING PROTOTYPE HTML ===\n"
    f"{_ORIGINAL_HTML}\n"
    "=== END EXISTING HTML ===\n\n"
    "=== REVISION REQUEST ===\n"
    f"{_USER_INSTRUCTION}\n"
    "=== END REQUEST ==="
)


def _final_text_turn() -> _ScriptedTurn:
    """The sub-agent's wrap-up turn (no tool calls)."""
    return _ScriptedTurn(texts=["done."], usage=(3, 2))


def _edit_turn(old: str, new: str, *, text: str, call_id: str) -> _ScriptedTurn:
    """One ``edit_file(prototype.html, old, new)`` call + a wrap-up text turn's
    lead text. Models the real revision protocol (edit, never write_file — the
    file already exists in the sandbox)."""
    return _ScriptedTurn(
        texts=[text],
        tool_calls=[
            (
                "edit_file",
                json.dumps({"file_path": "prototype.html", "old_string": old, "new_string": new}),
                call_id,
            )
        ],
        usage=(12, 6),
    )


# The visible revision turn: introduce the ghost route (the user's requested
# change) — which also introduces the static regression.
def _revision_introduce_regression_turns() -> list[_ScriptedTurn]:
    return [
        _edit_turn(
            _ROUTES_ORIGINAL, _ROUTES_WITH_GHOST,
            text="Adding the ghost route to the map. ", call_id="rev_edit",
        ),
        _final_text_turn(),
    ]


# The internal fix turn: remove the ghost key again → file becomes clean of the
# regression (only the baselined nit remains, which the fix-loop ignores).
def _fix_remove_regression_turns() -> list[_ScriptedTurn]:
    return [
        _edit_turn(
            _ROUTES_WITH_GHOST, _ROUTES_ORIGINAL,
            text="Fixing the stray route. ", call_id="fix_edit",
        ),
        _final_text_turn(),
    ]


# A clean revision that edits the file but introduces NO regression (for the
# graceful-degrade scenario): rename a heading. Keeps prototype.html valid.
def _clean_revision_turns() -> list[_ScriptedTurn]:
    return [
        _edit_turn(
            "<h1>Dashboard</h1>", "<h1>Home</h1>",
            text="Renaming the dashboard heading. ", call_id="clean_edit",
        ),
        _final_text_turn(),
    ]


_OD_CONTEXT = {
    "template_body": "## Workflow\nUse .card / .grid. Build into <section data-page>.",
    "template_id": "web-prototype",
    "ds_id": "acme-ds",
    "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;}",
    "craft_block": "Wire every nav link.",
    "is_design_system_required": True,
}


# ===========================================================================
# Scripted model that RECORDS the inbound messages of every _stream call, so the
# test can read back the EXACT fix message the fix sub-agent received.
# ===========================================================================


class _RecordingScriptedModel(ScriptedFakeChatModel):
    """``ScriptedFakeChatModel`` that appends every ``_stream`` call's inbound
    ``messages`` (rendered to plain text) to a shared ``log`` under ``key``.

    The fix message is a HumanMessage the engine builds in
    ``_run_validation_fix_loop`` and passes to ``astream_events`` → the runner's
    graph → the model's ``_stream``; recording the inbound messages there
    captures it verbatim regardless of how the graph wraps it.
    """

    def __init__(self, turns: list[_ScriptedTurn], *, log: list, key: tuple, **kw: Any) -> None:
        super().__init__(turns, **kw)
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "_key", key)

    def _stream(self, messages: list, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        rendered = "\n".join(_message_text(m) for m in messages)
        self._log.append((self._key, rendered))
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def _message_text(m: Any) -> str:
    """Best-effort plain-text rendering of a LangChain message (or anything)."""
    content = getattr(m, "content", m)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")) or json.dumps(block))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


# ===========================================================================
# Engine harness — drive the REAL execute() / _run_validation_fix_loop offline.
# ===========================================================================


def _fresh_engine(monkeypatch, tmp_path):
    """An ``ExecutionEngine`` wired for an offline run: temp ``RUNS_ROOT``, no-op
    artifact store, no inter-agent gate, an InMemory-free checkpointer, and a
    stubbed planner (the revision pipeline skips the planner, but stub defensively
    so no live LLM call can ever happen)."""
    import agents.execution_engine.engine as engine_mod
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "RUNS_ROOT", str(tmp_path))

    engine = engine_mod.ExecutionEngine()
    # Per-run state is no longer stashed on the engine singleton (CTX-01/CTX-02):
    # execute() constructs its own per-run ExecutionContext from the call args
    # (gate_agent_ids=[], od_context=_OD_CONTEXT are passed by _execute_revision).
    # Nothing to pre-seed on `engine` here.

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    # Disable the auto-clarify override (the clarifier needs live WS round-trips this
    # offline harness cannot do). The former module-level ALWAYS_CLARIFY=False knob was
    # deleted in 07-05; the "force CLARIFY_REQUIRED on every run" behavior is now declared
    # by the manifest clarify.mode == "auto", read off the CompiledWorkflow at run entry.
    # Wrap compile_for_run to flip the compiled clarify.mode to "off" — suppressing the
    # PROCEED→CLARIFY_REQUIRED forcing exactly as the old knob did (monkeypatch auto-restores).
    _orig_compile_for_run = engine_mod.compile_for_run

    def _patched_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    monkeypatch.setattr(engine_mod, "compile_for_run", _patched_compile_for_run)

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover — make it an async generator

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]
    return engine_mod, engine


def _provision_parent_run_db(monkeypatch, *, parent_run_id, owner_id="anon"):
    """Provision an in-memory DB with a SAME-OWNER parent ``workflow_runs`` row.

    WR-04 (fail-closed): ``ScopedStore.assert_owns`` does a REAL store lookup of
    the parent run's ``owner_id`` before the parent-context seed. After the
    WR-04 fix the seed FAILS CLOSED on any UNEXPECTED store error (so an
    ownership check that cannot be completed never degrades OPEN to seeding). The
    offline harness previously had NO DB at all, so ``assert_owns`` raised
    ``OperationalError: no such table`` and the OLD fail-open code degraded into
    seeding — i.e. the seeding tests only passed via the very bug WR-04 fixes.

    To keep these tests exercising the REAL production seed path (a same-owner
    parent that ``assert_owns`` confirms → ``None`` → seed proceeds), back the
    harness with an in-memory SQLite DB carrying a same-owner parent run row, and
    point ``SessionLocal`` at it (sqlite does not enforce the ``users`` FK, so no
    user row is needed). Mirrors the parent-existence the production revision
    path always has (the parent is a completed run with a ``workflow_runs`` row).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models.database as _db
    from app.models.database import Base
    from app.models.workflow import WorkflowRun

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=db_engine)
    TestingSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    seed = TestingSession()
    try:
        seed.add(
            WorkflowRun(
                id=parent_run_id,
                user_id=owner_id,
                title="parent",
                type="prototype",
                status="completed",
                input="idea",
                owner_id=owner_id,
            )
        )
        seed.commit()
    finally:
        seed.close()

    # Point ScopedStore's lazily-opened SessionLocal() at the in-memory DB.
    monkeypatch.setattr(_db, "SessionLocal", TestingSession)
    return TestingSession


def _install_recording_runner_factory(monkeypatch, engine_mod, *, turns_for, transcripts):
    """Patch ``engine.create_runner`` to return a REAL ``DeepAgentRunner`` over a
    ``_RecordingScriptedModel`` and RECORD every call.

    ``turns_for(agent_id, thread_id, is_fix)`` returns the scripted turns for that
    invocation. Records ``(agent_id, thread_id)`` in the returned ``calls`` list so
    tests can assert which threads ran (visible ``<run>:<agent>`` vs internal fix
    ``<run>:<agent>:revision:fix{n}``). Inbound messages of every model call land
    in ``transcripts`` keyed by ``(agent_id, thread_id)``.
    """
    calls: list[tuple[str, str]] = []

    def _factory(agent_id, ctx, **kw):
        thread_id = kw.get("thread_id") or ""
        calls.append((agent_id, thread_id))
        is_fix = ":fix" in thread_id
        rs = RunSandbox(ctx.user_id or "anon", ctx.run_id)
        rs.ensure()
        model = _RecordingScriptedModel(
            turns_for(agent_id, thread_id, is_fix),
            log=transcripts,
            key=(agent_id, thread_id),
        )
        return DeepAgentRunner(
            system_prompt="revision agent",
            tools=[report_task_complete],
            model=model,
            run_sandbox=rs,
            checkpointer=kw.get("checkpointer"),
            thread_id=thread_id,
        )

    monkeypatch.setattr(engine_mod, "create_runner", _factory)
    return calls


def _revision_specs():
    from agents.registry import get_pipeline_agents

    return list(get_pipeline_agents("prototype_revision"))


async def _execute_revision(
    engine,
    run_id,
    *,
    parent_run_id,
    turns_for,
    transcripts,
    monkeypatch,
    engine_mod,
    user_message=_REVISION_MESSAGE,
    user_id="anon",
):
    """Drive the REAL ``execute()`` for a ``prototype_revision`` run and collect
    every yielded event dict."""
    calls = _install_recording_runner_factory(
        monkeypatch, engine_mod, turns_for=turns_for, transcripts=transcripts
    )
    events: list[dict] = []
    async for ev in engine.execute(
        agents=_revision_specs(),
        user_message=user_message,
        pipeline_run_id=run_id,
        pipeline_type="prototype_revision",
        user_id=user_id,
        od_context=_OD_CONTEXT,
        gate_agent_ids=[],
        parent_run_id=parent_run_id,
    ):
        events.append(ev)
    return events, calls


def _final_output(events: list[dict]) -> str:
    pc = next(e for e in events if e.get("type") == "pipeline_complete")
    return pc["data"]["final_output"]


# ===========================================================================
# Scenario 1 — Parent seeding populates the revision sandbox.
# ===========================================================================


class TestParentSeeding:
    """``execute(parent_run_id=<id>)`` copies spec.md / design.md / tasks.md from
    the PARENT run's sandbox into THIS revision run's sandbox."""

    @pytest.mark.asyncio
    async def test_parent_spec_design_tasks_seeded_into_revision_sandbox(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        # Pre-write the parent run's sandbox with reference files + a valid SPA.
        parent_run_id = "parent-run-001"
        # WR-04: back the harness with a same-owner parent run row so the
        # assert_owns ownership check resolves cleanly (the seed no longer
        # degrades open on a missing-DB error).
        _provision_parent_run_db(monkeypatch, parent_run_id=parent_run_id)
        parent_sb = RunSandbox("anon", parent_run_id)
        parent_sb.ensure()
        spec_text = "# Specification\nThe app manages tasks.\n## Architecture\nSPA, hash routing."
        design_text = "# ACTIVE TEMPLATE (web-prototype)\n## Workflow\nUse .card / .grid."
        tasks_text = "## Task 1: Build the HTML shell\nCreate the skeleton.\n"
        parent_sb.write("spec.md", spec_text)
        parent_sb.write("design.md", design_text)
        parent_sb.write("tasks.md", tasks_text)
        parent_sb.write("prototype.html", _ORIGINAL_HTML)

        def turns_for(agent_id, thread_id, is_fix):
            # A clean revision (no regression) so the fix-loop is a no-op here —
            # this scenario isolates the seeding behavior.
            return _clean_revision_turns()

        transcripts: list = []
        run_id = "revision-seed-001"
        await _execute_revision(
            engine, run_id, parent_run_id=parent_run_id,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )

        # The REVISION run's sandbox now holds the parent's reference files,
        # byte-identical to the seeded contents.
        rev_sb = RunSandbox("anon", run_id)
        assert rev_sb.read("spec.md") == spec_text, "parent spec.md must be seeded verbatim"
        assert rev_sb.read("design.md") == design_text, "parent design.md must be seeded verbatim"
        assert rev_sb.read("tasks.md") == tasks_text, "parent tasks.md must be seeded verbatim"

    @pytest.mark.asyncio
    async def test_partial_parent_seeds_only_present_files(
        self, tmp_path, monkeypatch
    ) -> None:
        """A parent sandbox with only spec.md (no design.md/tasks.md) seeds spec.md
        and silently skips the absent files — never errors."""
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        parent_run_id = "parent-run-002"
        # WR-04: same-owner parent run row so assert_owns resolves cleanly.
        _provision_parent_run_db(monkeypatch, parent_run_id=parent_run_id)
        parent_sb = RunSandbox("anon", parent_run_id)
        parent_sb.ensure()
        parent_sb.write("spec.md", "# Spec only\n")
        # No design.md / tasks.md written.

        def turns_for(agent_id, thread_id, is_fix):
            return _clean_revision_turns()

        transcripts: list = []
        run_id = "revision-seed-002"
        await _execute_revision(
            engine, run_id, parent_run_id=parent_run_id,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )

        rev_sb = RunSandbox("anon", run_id)
        assert rev_sb.read("spec.md") == "# Spec only\n"
        assert rev_sb.read("design.md") is None, "absent parent design.md must not be fabricated"
        assert rev_sb.read("tasks.md") is None, "absent parent tasks.md must not be fabricated"


# ===========================================================================
# Scenario 2 — Fix policy end-to-end (THE CORE ASSERTION).
# ===========================================================================


class TestFixPolicyEndToEnd:
    """The seeded ORIGINAL carries a KNOWN pre-existing static nit; the revision
    introduces a NEW static regression. The internal fix-loop fixes ONLY the
    regression (re-injecting the user's instruction), LEAVES the pre-existing nit
    (baseline exclusion), and the final deliverable is the clean HTML."""

    @pytest.mark.asyncio
    async def test_fix_message_targets_regression_not_baseline_and_reinjects_instruction(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        # Sanity-pin the fixtures so a future edit can't silently break the policy:
        # the ORIGINAL has EXACTLY the pre-existing nit; the introduced-regression
        # HTML has the nit PLUS the regression.
        orig_issues = set(static_check(_ORIGINAL_HTML).issues)
        assert orig_issues == _PREEXISTING_NITS, (
            f"fixture drift: ORIGINAL must carry exactly the pre-existing nits; got {orig_issues}"
        )
        revised_html = _ORIGINAL_HTML.replace(_ROUTES_ORIGINAL, _ROUTES_WITH_GHOST)
        revised_issues = set(static_check(revised_html).issues)
        assert revised_issues == _PREEXISTING_NITS | {_REGRESSION_ISSUE}, (
            f"fixture drift: revised HTML must carry nits + regression; got {revised_issues}"
        )

        def turns_for(agent_id, thread_id, is_fix):
            # Visible revision: introduce the regression. Internal fix: remove it.
            return (
                _fix_remove_regression_turns()
                if is_fix
                else _revision_introduce_regression_turns()
            )

        transcripts: list = []
        run_id = "revision-fix-core"
        events, calls = await _execute_revision(
            engine, run_id, parent_run_id=None,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )

        # ── The internal fix sub-agent fired on a distinct :revision:fix thread. ──
        fix_calls = [(a, t) for (a, t) in calls if ":fix" in t]
        assert fix_calls, f"a regression must re-invoke the fix sub-agent; calls={calls}"
        assert all(a == "prototype-revision-agent" for (a, t) in fix_calls), (
            f"the fix must reuse the SAME revision agent id; got {fix_calls}"
        )
        assert all(":prototype-revision-agent:revision:fix" in t for (a, t) in fix_calls), (
            f"fix thread must be the generalized revision fix thread; got {fix_calls}"
        )
        # Repaired in one attempt (the post-fix file has only the baselined nit).
        assert len(fix_calls) == 1, f"the regression was repaired in one fix attempt; got {fix_calls}"
        assert fix_calls[0][1].endswith(":revision:fix1")

        # ── Capture the fix message the fix sub-agent received and assert policy. ──
        fix_key = fix_calls[0]
        fix_msgs = [text for (key, text) in transcripts if key == fix_key]
        assert fix_msgs, f"no recorded fix message for {fix_key}; transcripts keys={[k for k, _ in transcripts]}"
        # The FIRST inbound message to the fix model is the engine's fix prompt.
        fix_message = fix_msgs[0]

        # (a) It CONTAINS the regression issue (fed back for fixing).
        assert _REGRESSION_ISSUE in fix_message, (
            f"fix message must list the NEW regression; got:\n{fix_message}"
        )
        # (b) It does NOT contain the pre-existing baselined nits (suppressed).
        assert _PREEXISTING_NIT not in fix_message, (
            f"fix message must NOT list the pre-existing baselined nit; got:\n{fix_message}"
        )
        assert _PREEXISTING_ROUTER_DEAD not in fix_message, (
            f"fix message must NOT list the pre-existing router-dead nit; got:\n{fix_message}"
        )
        # (c) It re-injects the user's revision instruction (stay focused).
        assert _USER_INSTRUCTION in fix_message, (
            f"fix message must re-inject the user's revision instruction; got:\n{fix_message}"
        )

        # ── The final deliverable is the CLEAN HTML (regression removed). ──
        rev_sb = RunSandbox("anon", run_id)
        final_html = rev_sb.read("prototype.html") or ""
        assert _ROUTES_WITH_GHOST not in final_html, "the fix must have removed the ghost route"
        # Only the pre-existing baselined nits remain (the fix left them alone).
        assert set(static_check(final_html).issues) == _PREEXISTING_NITS, (
            f"final HTML must carry ONLY the untouched pre-existing nits; "
            f"got {static_check(final_html).issues}"
        )
        # The engine's pipeline_complete.final_output IS that clean read-back.
        assert _final_output(events) == final_html, (
            "pipeline_complete.final_output must be the validated edited prototype.html"
        )
        assert _ROUTES_WITH_GHOST not in _final_output(events)

    @pytest.mark.asyncio
    async def test_baseline_is_computed_on_the_seeded_original_pre_edit(
        self, tmp_path, monkeypatch
    ) -> None:
        """The baseline (the set of pre-existing static signatures to ignore) is
        computed on the ORIGINAL prototype.html BEFORE the agent edits it — proven
        by capturing the ``baseline_static`` / ``user_instruction`` the engine threads
        into ``_run_validation_fix_loop``. Post-CTX-01/02 the run state lives on the
        per-run ExecutionContext (not the engine singleton), so the observable seam is
        the args handed to the fix-loop, which carry ``ectx.revision_baseline_static``
        and ``ectx.revision_instruction``. (Guards 'baseline on the seeded original'.)"""
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        # Capture the fix-loop's baseline + instruction args (== ectx.revision_*).
        captured: dict = {}
        orig_fix_loop = engine_mod.ExecutionEngine._run_validation_fix_loop

        async def _spy_fix_loop(self, **kwargs):
            captured["baseline_static"] = kwargs.get("baseline_static")
            captured["user_instruction"] = kwargs.get("user_instruction")
            return await orig_fix_loop(self, **kwargs)

        monkeypatch.setattr(
            engine_mod.ExecutionEngine, "_run_validation_fix_loop", _spy_fix_loop
        )

        def turns_for(agent_id, thread_id, is_fix):
            return (
                _fix_remove_regression_turns()
                if is_fix
                else _revision_introduce_regression_turns()
            )

        transcripts: list = []
        run_id = "revision-baseline"
        await _execute_revision(
            engine, run_id, parent_run_id=None,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )

        # The baseline captured the ORIGINAL's pre-existing nit (so the fix-loop
        # treats it as not-a-regression), and did NOT capture the ghost regression
        # (which only exists AFTER the edit).
        baseline_static = captured.get("baseline_static") or set()
        assert _PREEXISTING_NIT in baseline_static, (
            "baseline must capture the pre-existing nit from the seeded ORIGINAL"
        )
        assert _REGRESSION_ISSUE not in baseline_static, (
            "baseline must be pre-edit — the regression must NOT be in it"
        )
        # The instruction threaded into the fix prompt is the user's verbatim request.
        assert captured.get("user_instruction") == _USER_INSTRUCTION


# ===========================================================================
# Scenario 3 — Graceful degrade with no parent.
# ===========================================================================


class TestGracefulDegradeNoParent:
    """``execute(parent_run_id=None)`` and a non-existent parent id both complete
    without error: no spec.md is seeded, the deliverable is the edited HTML, and
    no exception escapes."""

    @pytest.mark.asyncio
    async def test_no_parent_id_completes_without_seeding(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        def turns_for(agent_id, thread_id, is_fix):
            return _clean_revision_turns()

        transcripts: list = []
        run_id = "revision-no-parent"
        events, _calls = await _execute_revision(
            engine, run_id, parent_run_id=None,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )

        rev_sb = RunSandbox("anon", run_id)
        # No spec.md seeded (no parent).
        assert rev_sb.read("spec.md") is None, "no parent ⇒ no spec.md seeded"
        # The deliverable is the edited prototype.html (clean revision applied).
        final_html = rev_sb.read("prototype.html") or ""
        assert "<h1>Home</h1>" in final_html, "the clean revision edit must be applied"
        assert "<h1>Dashboard</h1>" not in final_html
        assert _final_output(events) == final_html
        # The run reached completion (pipeline_complete present, no error event).
        assert any(e["type"] == "pipeline_complete" for e in events)
        assert not [e for e in events if e["type"] in ("error", "agent_error")]

    @pytest.mark.asyncio
    async def test_nonexistent_parent_sandbox_degrades_gracefully(
        self, tmp_path, monkeypatch, caplog
    ) -> None:
        """A ``parent_run_id`` whose sandbox dir does not exist seeds nothing and
        never raises — the revision completes on HTML + instruction only."""
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        def turns_for(agent_id, thread_id, is_fix):
            return _clean_revision_turns()

        transcripts: list = []
        run_id = "revision-ghost-parent"
        with caplog.at_level(logging.WARNING, logger="agents.execution_engine.engine"):
            events, _calls = await _execute_revision(
                engine, run_id, parent_run_id="parent-that-was-swept-by-ttl",
                turns_for=turns_for, transcripts=transcripts,
                monkeypatch=monkeypatch, engine_mod=engine_mod,
            )

        rev_sb = RunSandbox("anon", run_id)
        assert rev_sb.read("spec.md") is None, "missing parent ⇒ nothing seeded"
        assert rev_sb.read("design.md") is None
        assert rev_sb.read("tasks.md") is None
        # The deliverable is still the edited HTML; the run completed cleanly.
        final_html = rev_sb.read("prototype.html") or ""
        assert "<h1>Home</h1>" in final_html
        assert _final_output(events) == final_html
        assert any(e["type"] == "pipeline_complete" for e in events)
        assert not [e for e in events if e["type"] in ("error", "agent_error")]


# ===========================================================================
# Scenario 4 — WS event vocabulary unchanged (the UI-identical invariant).
# ===========================================================================


class TestEventVocabularyUnchanged:
    """The set of event types ``execute()`` yields for the revision run is a subset
    of the established (pre-Phase-5) vocabulary, and the internal fix re-invocation
    leaks NO extra agent/tool events for a phantom second agent — the UI sees ONE
    revision agent."""

    @pytest.mark.asyncio
    async def test_event_types_subset_of_documented_vocabulary(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        # Run WITH a regression so the fix-loop actually fires (the strongest test
        # of "the fix-loop introduced no new event types").
        def turns_for(agent_id, thread_id, is_fix):
            return (
                _fix_remove_regression_turns()
                if is_fix
                else _revision_introduce_regression_turns()
            )

        transcripts: list = []
        run_id = "revision-vocab"
        events, calls = await _execute_revision(
            engine, run_id, parent_run_id=None,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )
        assert events, "revision run produced no events"

        # ── Every emitted type is in the documented vocabulary (nothing new). ──
        seen_types = {e.get("type") for e in events}
        unknown = seen_types - _DOCUMENTED_EVENT_TYPES
        assert not unknown, (
            f"revision (with fix-loop) emitted UNDOCUMENTED event type(s) the "
            f"frontend does not handle: {sorted(unknown)}"
        )

        # ── Load-bearing events keep their documented data key-shapes. ──
        for ev in events:
            required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
            if required is None:
                continue
            missing = required - set(ev.get("data", {}).keys())
            assert not missing, (
                f"event '{ev['type']}' dropped required keys {sorted(missing)}"
            )

    @pytest.mark.asyncio
    async def test_internal_fix_loop_leaks_no_phantom_second_agent(
        self, tmp_path, monkeypatch
    ) -> None:
        engine_mod, engine = _fresh_engine(monkeypatch, tmp_path)

        def turns_for(agent_id, thread_id, is_fix):
            return (
                _fix_remove_regression_turns()
                if is_fix
                else _revision_introduce_regression_turns()
            )

        transcripts: list = []
        run_id = "revision-no-leak"
        events, calls = await _execute_revision(
            engine, run_id, parent_run_id=None,
            turns_for=turns_for, transcripts=transcripts,
            monkeypatch=monkeypatch, engine_mod=engine_mod,
        )

        # ── The fix sub-agent DID run internally (a :fix thread create_runner). ──
        fix_threads = [t for (_a, t) in calls if ":fix" in t]
        assert fix_threads, f"the regression must trigger an internal fix; calls={calls}"

        # ── …but the UI saw exactly ONE revision agent: one agent_start /
        #    one agent_complete, NOT two (the fix must not emit a second pair). ──
        counts = Counter(e["type"] for e in events)
        assert counts["agent_start"] == 1, (
            f"the internal fix must NOT emit a second agent_start; counts={dict(counts)}"
        )
        assert counts["agent_complete"] == 1, (
            f"the internal fix must NOT emit a second agent_complete; counts={dict(counts)}"
        )

        # ── The fix's edit_file tool call is INTERNAL — not in the visible stream. ──
        # The visible revision made exactly ONE edit_file (introduce the ghost
        # route); the fix's edit_file (remove it) must NOT reach the caller.
        visible_tool_calls = [e["data"]["tool"] for e in events if e["type"] == "tool_call"]
        assert visible_tool_calls.count("edit_file") == 1, (
            f"only the visible revision's edit should appear; the fix's edit must be "
            f"internal; got tool_calls={visible_tool_calls}"
        )
        # And there is exactly ONE agent_start for the single revision agent id.
        starts = [e["data"]["agent_id"] for e in events if e["type"] == "agent_start"]
        assert starts == ["prototype-revision-agent"], (
            f"the UI must see ONE revision agent (no phantom fix agent); got {starts}"
        )
