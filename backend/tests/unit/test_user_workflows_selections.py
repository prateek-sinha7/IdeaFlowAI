"""Phase 22-04 — EMP-01/02/03 saved-workflow capability-selections verify gate.

Activates the built-but-dormant ``trust="user"`` compile path (compiler.py
``_check_trust``) as the AUTHORITATIVE server-side gate for user-composed
workflows, and persists the richer per-step selections in the REUSED
``workflows.manifest_json`` column (zero migration, D-11). These are the verify
gate for the threat-model ``mitigate`` rows:

* **T-22-04-01 (Elevation @ SAVE):** a save payload smuggling a
  ``user_allowed=False`` capability (``gate: security`` / approval) is rejected
  422 — the underlying ``compile(trust="user")`` raised ``CompilerError`` naming
  the ``(kind, name)`` (CAP-03). The FE lock is advisory only; THIS is the control.
* **T-22-04-02 (Elevation @ LAUNCH):** a row TAMPERED after save (its
  ``manifest_json`` mutated to reference a non-user-allowed cap) is REJECTED at
  launch by re-compiling ``trust="user"`` BEFORE execute (Pitfall 3).
* **T-22-04-03 (Limits ceiling):** a ceiling-raising Limits cap in the selections
  is rejected at save (``_compile_limits`` untrusted ceiling).
* **T-22-04-04 (IDOR):** a cross-owner GET on a saved workflow → 404, never leak.
* **EMP-01 (selection reaches execution):** a persisted validator + non-default
  model + retry, launched through the EXISTING run path, demonstrably reaches the
  compiled plan the engine drives — the validator's ``validation`` gate fires, the
  chosen model is what ``ModelResolver`` resolves, and the retry wrapper activates
  under an injected transient fault. No new run endpoint, no kernel branch (SC-001).

Save-side tests drive a FastAPI ``TestClient`` (the ``test_user_workflows.py``
harness — in-memory SQLite, overridden ``get_current_user``/``get_db``). The
EMP-01 + launch-reject proofs drive the compiler/engine seams directly (the
``trust="user"`` re-compile + the per-step overlay) without a live model.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.user_workflows import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.workflow_definition import WorkflowDefinition

# CWF-001 D1: _AGENT_B is swot-analyst (consumes _AGENT_A's produced type), so the
# default [_AGENT_A, _AGENT_B] composition is producer-first satisfiable (presorts
# to itself). report-generator (consumes documentation-agent, never produced) would
# now be rejected by the compose-time satisfiability guard.
_AGENT_A = "market-research-agent"
_AGENT_B = "swot-analyst"
_DEFAULT_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
_NON_DEFAULT_MODEL = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
_USER_VALIDATOR = "spec_plan_coverage"  # user_allowed=True


class _FakeUser:
    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.tier = tier


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api(db_session):
    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": _FakeUser(id="owner")}

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


def _save_body(selections=None, **kw):
    body = {
        "name": kw.get("name", "Composed WF"),
        "base_pipeline_type": "custom",
        "agent_ids": kw.get("agent_ids", [_AGENT_A, _AGENT_B]),
    }
    if selections is not None:
        body["selections"] = selections
    return body


# ---------------------------------------------------------------------------
# EMP-03 — round-trip: save → list → reopen shows the same selections
# ---------------------------------------------------------------------------


def test_selections_round_trip_save_list_reopen(api):
    client, _ = api
    selections = {
        _AGENT_A: {
            "validators": [_USER_VALIDATOR],
            "model": _NON_DEFAULT_MODEL,
            "retry": {"max_attempts": 2},
        }
    }
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 201, r.text
    saved_id = r.json()["id"]
    # The POST response round-trips the selections (auto-attached validation gate
    # is a compile-time concern; the persisted compact map is what the user sent).
    assert r.json()["selections"] == selections

    # list → the row carries the selections
    rl = client.get("/api/user-workflows")
    assert rl.status_code == 200
    listed = next(w for w in rl.json() if w["id"] == saved_id)
    assert listed["selections"] == selections

    # reopen (GET /{id}) → identical selections
    rg = client.get(f"/api/user-workflows/{saved_id}")
    assert rg.status_code == 200
    assert rg.json()["selections"] == selections


def test_no_selections_persists_null_parity(api):
    """A P21-style save with no selections → ``selections is None`` (parity)."""
    client, _ = api
    r = client.post("/api/user-workflows", json=_save_body())
    assert r.status_code == 201, r.text
    assert r.json()["selections"] is None


# ---------------------------------------------------------------------------
# T-22-04-01 — save rejects a smuggled user_allowed=False capability (CAP-03)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("smuggled_gate", ["security", "approval"])
def test_save_rejects_smuggled_privileged_gate(api, smuggled_gate):
    client, _ = api
    selections = {_AGENT_A: {"gates": [smuggled_gate]}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"].lower()
    assert "user-allowed" in detail or "user_allowed" in detail
    assert smuggled_gate in detail
    # No orphan row was created.
    assert client.get("/api/user-workflows").json() == []


def test_save_rejects_ceiling_raising_limits(api):
    """T-22-04-03 — a Limits cap raising above the untrusted ceiling → 422."""
    client, _ = api
    selections = {"__workflow__": {"limits": {"max_subagents": 999}}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 422, r.text
    assert "ceiling" in r.json()["detail"].lower()
    assert client.get("/api/user-workflows").json() == []


# ---------------------------------------------------------------------------
# T-22-04-04 — IDOR: cross-owner GET → 404 (never 403/leak)
# ---------------------------------------------------------------------------


def test_cross_owner_get_is_404(api):
    client, state = api
    selections = {_AGENT_A: {"validators": [_USER_VALIDATOR]}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 201
    other_id = r.json()["id"]

    # Switch principal — a different owner must NOT see the row (404, not 403).
    state["user"] = _FakeUser(id="attacker")
    rg = client.get(f"/api/user-workflows/{other_id}")
    assert rg.status_code == 404
    assert "not found" in rg.json()["detail"].lower()


# ===========================================================================
# Task 2 — LAUNCH-side trust=user re-validation + EMP-01 selection-reaches-exec
# ===========================================================================

import asyncio  # noqa: E402

import pytest as _pytest  # noqa: E402

from app.api.run_engine import _revalidate_selections_trust_user  # noqa: E402


# ---------------------------------------------------------------------------
# T-22-04-02 — a tampered persisted row is REJECTED at launch (Pitfall 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("smuggled_gate", ["security", "approval"])
def test_launch_rejects_tampered_row(smuggled_gate):
    """A row whose manifest_json was mutated AFTER save to reference a
    user_allowed=False cap is rejected at LAUNCH (not only at save)."""
    tampered = {_AGENT_A: {"gates": [smuggled_gate]}}
    err = _revalidate_selections_trust_user("custom", [_AGENT_A, _AGENT_B], tampered)
    assert err is not None
    assert smuggled_gate in err
    assert "user-allowed" in err.lower() or "user_allowed" in err.lower()


def test_launch_rejects_tampered_ceiling_limits():
    tampered = {"__workflow__": {"limits": {"max_subagents": 999}}}
    err = _revalidate_selections_trust_user("custom", [_AGENT_A], tampered)
    assert err is not None and "ceiling" in err.lower()


def test_launch_accepts_clean_selections():
    """A clean persisted map passes launch re-validation (None == no error)."""
    clean = {_AGENT_A: {"validators": [_USER_VALIDATOR], "retry": {"max_attempts": 2}}}
    assert _revalidate_selections_trust_user("custom", [_AGENT_A, _AGENT_B], clean) is None


def test_launch_empty_selections_is_noop_parity():
    assert _revalidate_selections_trust_user("custom", [_AGENT_A], None) is None
    assert _revalidate_selections_trust_user("custom", [_AGENT_A], {}) is None


# ---------------------------------------------------------------------------
# EMP-01 — the selection reaches execution through the EXISTING run path:
#   (a) the chosen validator + its validation gate land on the compiled Step,
#   (b) ModelResolver resolves the chosen non-default model from that Step,
#   (c) the retry wrapper activates under an injected transient fault.
# Driven save→launch via the SAME overlay the engine applies at run entry
# (ExecutionEngine._apply_selections over the file-compiled `custom` plan).
# ---------------------------------------------------------------------------


def _compose_launch_overlay():
    """Compose the selections a user would save, then apply them onto the
    file-compiled `custom` plan exactly as the engine does at run entry."""
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    selections = {
        _AGENT_A: {
            "validators": [_USER_VALIDATOR],
            "model": _NON_DEFAULT_MODEL,
            "retry": {"max_attempts": 3},
        }
    }
    base = compile_for_run("custom")
    overlaid, _ = ExecutionEngine._apply_selections(base, selections)
    step = next(s for s in overlaid.steps if s.agent_id == _AGENT_A)
    return base, overlaid, step, selections


def test_emp01_validator_and_gate_reach_compiled_step():
    base, overlaid, step, _ = _compose_launch_overlay()
    # (a) the user-selected validator + its EMP-04 auto-attached validation gate
    # land on the matching compiled step — so the validation gate FIRES the
    # validator at run time (validation_* events / gate_events rows).
    assert _USER_VALIDATOR in step.validators
    assert "validation" in step.gates
    # An untouched step is unchanged (no bleed).
    other = next(s for s in overlaid.steps if s.agent_id == _AGENT_B)
    base_other = next(s for s in base.steps if s.agent_id == _AGENT_B)
    assert other.validators == base_other.validators
    assert other.gates == base_other.gates


def test_emp01_chosen_model_resolves_via_modelresolver():
    _, _, step, _ = _compose_launch_overlay()
    from agents.model_policy import ModelResolver

    class _Spec:
        id = _AGENT_A
        model = None

    resolver = ModelResolver(haiku_default=_DEFAULT_MODEL)
    # (b) the chosen non-default per-step model (tier 2) is what ModelResolver
    # resolves for this agent — proving the selection reaches model selection.
    assert resolver.resolve(_Spec(), step) == _NON_DEFAULT_MODEL


def test_emp01_retry_activates_under_injected_transient_fault(monkeypatch):
    _, _, step, _ = _compose_launch_overlay()
    # (c) the overlaid step carries retry.max_attempts > 0, so the engine's single
    # retry wrapper activates under an injected transient fault (it would be DORMANT
    # — no step_retry — without the selection).
    assert step.retry is not None and step.retry.max_attempts == 3

    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine

    from tests.agents.test_step_retry import (
        _FakeCtx,
        _FakeStrategy,
        ScriptedThrottleError,
    )

    async def _noop(_s):
        return None

    monkeypatch.setattr(engine_mod, "_retry_sleep", _noop)

    engine = ExecutionEngine()
    # Throttle once then succeed — the wrapper must emit step_retry then complete.
    strategy = _FakeStrategy([ScriptedThrottleError(), None], step_agent=_AGENT_A)
    ctx = _FakeCtx()

    async def _drive():
        return [ev async for ev in engine._dispatch_step_with_retry(step, ctx, strategy)]

    events = asyncio.get_event_loop().run_until_complete(_drive())
    types = [e["type"] for e in events]
    assert "step_retry" in types          # retry ACTIVATED (would be absent if dormant)
    assert "step_completed" in types       # recovered after the transient fault
    assert strategy.calls == 2             # exactly one retry then success


# ---------------------------------------------------------------------------
# CR-01 / WR-04 — a per-step ``model`` selection NOT in the ModelCatalog allow-list
# is rejected at BOTH save and launch (the model-id allow-list bypass).
# ---------------------------------------------------------------------------

_DISALLOWED_MODEL = "openai-gpt-totally-not-allowed"


def test_save_rejects_disallowed_selection_model(api):
    """A selection ``model`` id outside the catalog → 422 at SAVE (no orphan row)."""
    client, _ = api
    selections = {_AGENT_A: {"model": _DISALLOWED_MODEL}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"].lower()
    assert "not an allowed model" in detail
    assert _DISALLOWED_MODEL in r.json()["detail"]
    # No orphan config persisted.
    assert client.get("/api/user-workflows").json() == []


def test_save_accepts_allowed_selection_model(api):
    """A catalog model id still saves cleanly (the check is not over-broad)."""
    client, _ = api
    selections = {_AGENT_A: {"model": _NON_DEFAULT_MODEL}}
    r = client.post("/api/user-workflows", json=_save_body(selections))
    assert r.status_code == 201, r.text


def test_launch_rejects_disallowed_selection_model():
    """A crafted/tampered selections payload requesting a disallowed model id is
    rejected at LAUNCH before execute (CR-01 — the WS chokepoint)."""
    tampered = {_AGENT_A: {"model": _DISALLOWED_MODEL}}
    err = _revalidate_selections_trust_user("custom", [_AGENT_A, _AGENT_B], tampered)
    assert err is not None
    assert "not an allowed model" in err.lower()
    assert _DISALLOWED_MODEL in err


def test_launch_accepts_allowed_selection_model():
    clean = {_AGENT_A: {"model": _NON_DEFAULT_MODEL}}
    assert _revalidate_selections_trust_user("custom", [_AGENT_A], clean) is None


def test_model_resolver_rejects_disallowed_step_model():
    """Defense-in-depth (CR-01): even if a disallowed id reaches a compiled Step,
    the ModelResolver tier-2 catalog check refuses it before build_model."""
    from agents.model_policy import ModelResolver
    from agents.workflows.plan import ModelPolicy, Step

    step = Step(agent_id=_AGENT_A, strategy="single_shot",
                model=ModelPolicy(model=_DISALLOWED_MODEL))

    class _Spec:
        id = _AGENT_A
        model = None

    resolver = ModelResolver(haiku_default=_DEFAULT_MODEL)
    with pytest.raises(ValueError, match="not a known, allowed catalog model"):
        resolver.resolve(_Spec(), step)


# ---------------------------------------------------------------------------
# CR-02 — a Retry lever emitted as a BARE numeric value (the FE <select> value)
# is coerced to the compiler's ``{max_attempts: N}`` shape so save+launch succeed
# and the RESUME-02 retry wrapper is reachable.
# ---------------------------------------------------------------------------


def test_save_accepts_bare_numeric_retry(api):
    """The FE emits ``retry`` as a bare value; save must NOT 422 (it is coerced)."""
    client, _ = api
    for retry_value in (2, "3"):
        selections = {_AGENT_A: {"retry": retry_value}}
        r = client.post("/api/user-workflows",
                        json=_save_body(selections, name=f"wf-{retry_value}"))
        assert r.status_code == 201, r.text


def test_launch_accepts_bare_numeric_retry():
    selections = {_AGENT_A: {"retry": 2}}
    assert _revalidate_selections_trust_user("custom", [_AGENT_A], selections) is None


def test_bare_retry_coerces_and_reaches_compiled_step():
    """A bare numeric retry overlays a live ``RetryPolicy(max_attempts=N>0)`` onto the
    compiled step — proving the RESUME-02 wrapper is reachable end-to-end (CR-02)."""
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    selections = {_AGENT_A: {"retry": 4}}
    overlaid, _ = ExecutionEngine._apply_selections(compile_for_run("custom"), selections)
    step = next(s for s in overlaid.steps if s.agent_id == _AGENT_A)
    assert step.retry is not None and step.retry.max_attempts == 4


def test_zero_retry_omits_no_wrapper():
    """A 0 / unset retry is treated as 'no retry' (omitted) — parity, the wrapper
    stays dormant (no step_retry path)."""
    from agents.workflows.selections import _coerce_retry, _synthesize_step

    assert _coerce_retry(0) is None
    assert _coerce_retry("0") is None
    step = _synthesize_step(_AGENT_A, {"retry": 0})
    assert "retry" not in step


# ===========================================================================
# FANOUT-03 (Plan 51-01, D5) — the synthesizer emits the user-selected strategy
# generically (no workflow/agent-name literal), so a composed fan-out selection
# becomes a fanout_batch step at the trust=user re-compile (unblocks the 51-04
# engine overlay, which reads ``user_step.strategy``).
# ===========================================================================


def test_synthesize_step_emits_selected_fanout_strategy():
    """A selection carrying ``strategy=fanout_batch`` (+ task_source/fanout) yields a
    step whose ``strategy`` is the SELECTED value, carrying task_source + fanout
    (which already ride the generic projection loop)."""
    from agents.workflows.selections import _synthesize_step

    sel = {
        "strategy": "fanout_batch",
        "task_source": {
            "kind": "parsed",
            "parser": "heading_tasks",
            "source_step": _AGENT_A,
        },
        "fanout": {"mode": "parallel", "max_parallel": 4},
    }
    step = _synthesize_step(_AGENT_B, sel)
    assert step["strategy"] == "fanout_batch"
    assert step["task_source"] == sel["task_source"]
    assert step["fanout"] == sel["fanout"]
    assert step["agent"] == _AGENT_B


def test_synthesize_step_defaults_single_shot_when_no_strategy():
    """No / empty / lever-only selection keeps the safe single_shot default and
    carries no task_source (parity with a lever-less saved step)."""
    from agents.workflows.selections import _synthesize_step

    for sel in (None, {}, {"validators": [_USER_VALIDATOR]}):
        step = _synthesize_step(_AGENT_A, sel)
        assert step["strategy"] == "single_shot"
        assert "task_source" not in step


def test_synthesize_step_ignores_empty_or_nonstring_strategy():
    """Only a NON-EMPTY STRING strategy overrides the default (an empty / non-string
    strategy falls back to single_shot) — the change keys solely on the generic
    ``strategy`` key, never a name literal (INV-1/SC-001)."""
    from agents.workflows.selections import _synthesize_step

    assert _synthesize_step(_AGENT_A, {"strategy": ""})["strategy"] == "single_shot"
    assert _synthesize_step(_AGENT_A, {"strategy": 123})["strategy"] == "single_shot"
    assert _synthesize_step(_AGENT_A, {"strategy": None})["strategy"] == "single_shot"


def test_fanout_selection_trust_compiles_under_user():
    """End-to-end trust boundary: a fan-out selection (``fanout_batch`` strategy +
    ``heading_tasks`` parser — both user_allowed=True) is ACCEPTED by the trust=user
    compile and yields a compiled Step whose ``.strategy`` is the selected
    fanout_batch, carrying the task_source + fanout. The producer step is untouched
    (safe single_shot default — parity)."""
    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import WorkflowCompiler
    from agents.workflows.selections import synthesize_manifest

    selections = {
        _AGENT_B: {
            "strategy": "fanout_batch",
            "task_source": {
                "kind": "parsed",
                "parser": "heading_tasks",
                "source_step": _AGENT_A,
            },
            "fanout": {"mode": "parallel", "max_parallel": 4},
        }
    }
    manifest = synthesize_manifest("custom", [_AGENT_A, _AGENT_B], selections)
    compiled = WorkflowCompiler().compile(
        manifest, CapabilityRegistry(), trust="user"
    )
    worker = next(s for s in compiled.steps if s.agent_id == _AGENT_B)
    assert worker.strategy == "fanout_batch"
    assert worker.task_source is not None
    assert worker.task_source.source_step == _AGENT_A
    assert worker.task_source.parser == "heading_tasks"
    assert worker.fanout is not None
    producer = next(s for s in compiled.steps if s.agent_id == _AGENT_A)
    assert producer.strategy == "single_shot"


def test_fanout_selection_with_smuggled_grant_is_rejected_naming_it():
    """A fan-out selection that ALSO smuggles a user_allowed=False grant (a
    ``security`` gate) is REJECTED by the trust=user compile with a ``CompilerError``
    NAMING the offending capability — the synthesizer only PROJECTS the strategy
    string; the compiler is the authority (T-51-01-E)."""
    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.selections import synthesize_manifest

    selections = {
        _AGENT_B: {
            "strategy": "fanout_batch",
            "task_source": {
                "kind": "parsed",
                "parser": "heading_tasks",
                "source_step": _AGENT_A,
            },
            "gates": ["security"],  # smuggled user_allowed=False grant
        }
    }
    manifest = synthesize_manifest("custom", [_AGENT_A, _AGENT_B], selections)
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust="user")
    msg = str(exc.value).lower()
    assert "security" in msg
    assert "user-allowed" in msg or "user_allowed" in msg


# ===========================================================================
# FANOUT-02 / FANOUT-06 (Plan 51-04, D3) — THE CRUX: the engine overlay
# ``_apply_selections`` carries strategy/fanout/task_source at BOTH the in-plan
# step and the absent-agent synthesis site, returns the trust-compiled user-step
# map, and keeps the empty path byte-identical + map empty (INV-3).
# ===========================================================================

# An agent that is NOT in the file-compiled ``custom`` base plan (the common case
# for a composed ``custom`` run — ``allowed_custom_agent_ids`` unions ALL non-revision
# base agents, so a composed run can carry agents absent from the base membership).
_ABSENT_AGENT = "domain-analyst"


def _fanout_sel(worker: str, source: str) -> dict:
    """A minimal, GENERIC fan-out selection (no name literal in the kernel path)."""
    return {
        worker: {
            "strategy": "fanout_batch",
            "task_source": {
                "kind": "parsed",
                "parser": "heading_tasks",
                "source_step": source,
            },
            "fanout": {"mode": "parallel", "max_parallel": 4},
        }
    }


def test_apply_selections_carries_fanout_onto_in_plan_step():
    """IN-PLAN carry: overlaying a fan-out selection onto a base-manifest step yields
    ``strategy == fanout_batch`` + the selected ``task_source.source_step`` + a
    populated ``fanout`` — the levers the old overlay DROPPED now reach the run plan."""
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    base = compile_for_run("custom")
    overlaid, user_map = ExecutionEngine._apply_selections(
        base, _fanout_sel(_AGENT_B, _AGENT_A)
    )
    step = next(s for s in overlaid.steps if s.agent_id == _AGENT_B)
    assert step.strategy == "fanout_batch"
    assert step.task_source is not None
    assert step.task_source.source_step == _AGENT_A
    assert step.task_source.parser == "heading_tasks"
    assert step.fanout is not None
    # A non-selected base step is untouched (no bleed) + the overlay REPLACES steps
    # in place (never adds/removes) so the membership assertion stays valid.
    assert [s.agent_id for s in overlaid.steps] == [s.agent_id for s in base.steps]
    producer = next(s for s in overlaid.steps if s.agent_id == _AGENT_A)
    assert producer.strategy == "single_shot"
    # The returned user-step map carries the trust-compiled worker.
    assert user_map[_AGENT_B].strategy == "fanout_batch"


def test_apply_selections_absent_agent_carried_in_user_step_map():
    """ABSENT-agent carry: for a composed agent NOT in the base manifest, passing it
    via ``run_agent_ids`` yields a user-step map whose entry carries the fan-out step
    the synthesis site would use (before the bare single_shot fallback)."""
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    base = compile_for_run("custom")
    base_ids = [s.agent_id for s in base.steps]
    assert _ABSENT_AGENT not in base_ids  # precondition: genuinely absent

    overlaid, user_map = ExecutionEngine._apply_selections(
        base, _fanout_sel(_ABSENT_AGENT, _AGENT_A), run_agent_ids=[_ABSENT_AGENT]
    )
    # The absent agent is NOT injected into the plan steps (membership assertion safe)…
    assert [s.agent_id for s in overlaid.steps] == base_ids
    # …but its trust-compiled fan-out step IS available in the returned map for the
    # synthesis site to consult.
    assert _ABSENT_AGENT in user_map
    absent_step = user_map[_ABSENT_AGENT]
    assert absent_step.strategy == "fanout_batch"
    assert absent_step.task_source is not None
    assert absent_step.task_source.source_step == _AGENT_A


def test_apply_selections_absent_step_carries_default_hooks_benign_delta():
    """BENIGN delta (Risk #6): the trust-compiled absent step carries the compiler's
    DEFAULT hooks (``audit_logger``/``secret_scan``) a bare ``_Step`` synthesis lacked.
    This is INTENDED (a composed absent agent now runs a real compiled step), asserted
    here so it is not mistaken for a regression."""
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    base = compile_for_run("custom")
    _, user_map = ExecutionEngine._apply_selections(
        base, _fanout_sel(_ABSENT_AGENT, _AGENT_A), run_agent_ids=[_ABSENT_AGENT]
    )
    hooks = list(getattr(user_map[_ABSENT_AGENT], "hooks", []) or [])
    assert "audit_logger" in hooks
    assert "secret_scan" in hooks


def test_apply_selections_empty_is_byte_identical_and_map_empty():
    """EMPTY/None selections → ``(compiled_unchanged, {})`` at the ``has_selections``
    short-circuit — the plan is the SAME object (byte-identical) and the user-step map
    is empty, so BOTH consumption sites behave identically to today (INV-3)."""
    from agents.execution_engine.engine import ExecutionEngine, compile_for_run

    base = compile_for_run("custom")
    for empty in (None, {}):
        overlaid, user_map = ExecutionEngine._apply_selections(base, empty)
        assert overlaid is base  # unchanged plan (no re-compile, no replace)
        assert user_map == {}
    # run_agent_ids is ignored on the empty path (short-circuit before synth).
    overlaid, user_map = ExecutionEngine._apply_selections(
        base, None, run_agent_ids=[_ABSENT_AGENT]
    )
    assert overlaid is base
    assert user_map == {}
