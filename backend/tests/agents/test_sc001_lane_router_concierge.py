"""tests/agents/test_sc001_lane_router_concierge.py — the SC-001 / INV-1 proof.

The milestone's non-negotiable core value (ROADMAP SC-4 / INV-1): a BRAND-NEW custom
workflow gets the run chat lane + the mechanical router + the run Concierge with ZERO
engine / FE / orchestrator code. The kernel knows NO workflow by name; all power lives
in registered capabilities + declared manifest DATA.

This suite proves that empirically with a THROWAWAY custom workflow named
``sc001_throwaway_wf`` (written to a tmp fixture dir — NEVER shipped under
``agents/workflows/``):

  1. Routing — a free-form turn (the generic ``ChatTurn.concierge`` marker, no gate
     action / no clarify responses) routes through ``route_chat_turn`` to
     ``CHANNEL_CONCIERGE``, and a gate turn routes to ``CHANNEL_GATE``. The router keys
     ONLY on the generic ``RunState`` — it takes NO workflow argument, so the throwaway
     workflow routes identically to every shipped one.
  2. Registry — ``registry.resolve("chat", "concierge")`` returns the SAME shared impl
     regardless of workflow (a pure ``(kind, name)`` static dict lookup, no workflow arg).
  3. Data — the manifest ``chat:`` block (33-05) compiles as pure DATA carried onto
     ``CompiledWorkflow.chat``, and the shared Concierge reads it via
     ``getattr(compiled, "chat", {})`` with NO workflow-name branch (INV-5 / INV-1).
  4. Grep gate — the throwaway workflow name appears 0 times in the engine, the router,
     and the Concierge, and NO name-keyed branch (``pipeline_type == / spec.id == /
     workflow_name ==``) exists in the chat surface. This is the SC-001 gate, mirroring
     ``test_sc001_gate_flag.py``'s source-gate.

Offline-safe: no Bedrock / Postgres / Chromium; no agent is run (compile + pure routing
+ static prompt composition + source-file greps only).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import load_manifest
from app.api.chat_router import (
    CHANNEL_CONCIERGE,
    CHANNEL_GATE,
    ChatTurn,
    RunState,
    route_chat_turn,
)

# The DISTINCTIVE throwaway workflow name. The whole SC-001 claim is that this name
# appears in NO engine / router / concierge code — the kernel knows no workflow by
# name. It is TEST-SCOPED (written to a tmp fixture dir), never shipped.
_THROWAWAY_WF = "sc001_throwaway_wf"

# A minimal, self-contained custom workflow manifest a user could author. ``steps: []``
# (the D-05 empty-plan shape) keeps the compile offline + capability-free; the point is
# the ``chat:`` DATA block a custom workflow authors for its Concierge.
_MANIFEST_YAML = f"""\
id: {_THROWAWAY_WF}
planner: skip
clarify:
  mode: auto
deliverable: {{}}
steps: []
chat:
  suggestions:
    - "Ask about this run's progress"
    - "Propose a revision of the deliverable"
  notes: "Concierge notes authored purely as manifest DATA (INV-5)."
"""


@pytest.fixture
def throwaway_manifest_home(tmp_path) -> Path:
    """Write the throwaway ``workflow.yaml`` to a tmp base dir and return the base.

    The manifest lives ONLY under ``tmp_path`` — never under the shipped
    ``agents/workflows/`` tree — so the SC-001 grep gate scans a repo that has never
    heard of this workflow.
    """
    wf_dir = tmp_path / _THROWAWAY_WF
    wf_dir.mkdir()
    (wf_dir / "workflow.yaml").write_text(_MANIFEST_YAML, encoding="utf-8")
    return tmp_path


# ===========================================================================
# 1. Routing — the throwaway workflow routes identically (name-free RunState)
# ===========================================================================


def test_freeform_turn_routes_to_concierge() -> None:
    """A free-form turn EXPLICITLY marked concierge (the generic FE marker) with no
    gate action / no clarify responses escalates to CHANNEL_CONCIERGE — keyed on the
    generic RunState phase alone, never the workflow name (SC-001/INV-1)."""
    run_state = RunState(status="running")
    turn = ChatTurn(text="what changed in this run?", concierge=True)
    dispatch = route_chat_turn(run_state, turn)
    assert dispatch.channel == CHANNEL_CONCIERGE
    assert dispatch.instruction == "what changed in this run?"


def test_gate_turn_routes_to_gate() -> None:
    """A run paused at a review gate + a gate action routes to CHANNEL_GATE — the
    generic gate seam, no workflow-name branch."""
    run_state = RunState(
        status="waiting_for_user", open_gate="review", gate_key="run-1:some-agent"
    )
    turn = ChatTurn(action="approve")
    dispatch = route_chat_turn(run_state, turn)
    assert dispatch.channel == CHANNEL_GATE
    assert dispatch.action == "approve"
    assert dispatch.gate_key == "run-1:some-agent"


def test_concierge_marker_is_opt_in_not_default() -> None:
    """A plain running turn WITHOUT the concierge marker does NOT escalate — it stays
    on the Phase-29 default (steering). Escalation is opt-in via the generic marker
    (33-03), so routable turns keep their existing zero-model channel (INV-12)."""
    run_state = RunState(status="running")
    plain = ChatTurn(text="tighten the header spacing")  # concierge defaults False
    dispatch = route_chat_turn(run_state, plain)
    assert dispatch.channel != CHANNEL_CONCIERGE


def test_router_takes_no_workflow_argument() -> None:
    """``route_chat_turn`` keys ONLY on the generic (RunState, ChatTurn) — its
    signature carries NO workflow / pipeline_type / spec.id parameter, so a brand-new
    workflow routes identically with zero router code (SC-001/INV-1)."""
    params = list(inspect.signature(route_chat_turn).parameters)
    assert params == ["run_state", "turn"], (
        f"route_chat_turn must key only on generic run state; got params {params}"
    )


# ===========================================================================
# 2. Registry — one shared Concierge impl, resolved name-free
# ===========================================================================


def test_registry_resolves_shared_concierge_impl() -> None:
    """``resolve("chat", "concierge")`` returns the SAME shared singleton on every
    call — a pure static ``(kind, name)`` dict lookup with NO workflow argument, so the
    throwaway workflow reuses the shipped Concierge with zero new code (SC-001)."""
    discover()
    registry = CapabilityRegistry()
    impl_a = registry.resolve("chat", "concierge")
    impl_b = registry.resolve("chat", "concierge")
    assert impl_a is impl_b
    assert getattr(impl_a, "name", None) == "concierge"
    assert hasattr(impl_a, "converse")
    # resolve keys ONLY on (kind, name) — no workflow / pipeline_type parameter.
    params = list(inspect.signature(registry.resolve).parameters)
    assert params == ["kind", "name"], (
        f"registry.resolve must key only on (kind, name); got {params}"
    )


# ===========================================================================
# 3. Data — the manifest chat: block compiles + is carried, read by the Concierge
# ===========================================================================


def test_chat_block_compiles_as_data(throwaway_manifest_home) -> None:
    """The authored ``chat:`` block compiles as pure DATA (INV-5): the manifest carries
    it and the compiler carries it VERBATIM onto ``CompiledWorkflow.chat`` — exactly the
    attribute the Concierge reads via ``getattr(compiled, "chat", {})``."""
    discover()
    registry = CapabilityRegistry()
    manifest = load_manifest(_THROWAWAY_WF, throwaway_manifest_home)
    assert manifest.chat.get("suggestions"), "manifest must carry the authored chat data"

    compiled = WorkflowCompiler().compile(manifest, registry)
    assert compiled.chat == manifest.chat, "compiler must carry chat verbatim (INV-5)"
    assert "suggestions" in compiled.chat


def test_concierge_reads_compiled_chat_data(throwaway_manifest_home) -> None:
    """The SHARED Concierge (resolved name-free) reads the throwaway workflow's authored
    chat DATA into its system prompt — the full SC-001 loop (lane + router + Concierge,
    driven purely by manifest data + a registered capability, ZERO workflow-name code)."""
    discover()
    registry = CapabilityRegistry()
    compiled = WorkflowCompiler().compile(
        load_manifest(_THROWAWAY_WF, throwaway_manifest_home), registry
    )
    concierge = registry.resolve("chat", "concierge")

    class _Ctx:
        run_id = "sc001-run"
        scoped_store = None
        owner_id = None
        workspace_id = None
        model = None
        conversation_context = None
        compiled = None

    ctx = _Ctx()
    ctx.compiled = compiled
    prompt = concierge._compose_system_prompt(ctx)
    # The authored suggestions reach the Concierge purely as DATA — no branch on the
    # workflow name (SC-001 / INV-1).
    assert "Suggested topics" in prompt


# ===========================================================================
# 4. The SC-001 GREP GATE — no workflow name, no name-keyed branch
# ===========================================================================


def _engine_dir() -> Path:
    import agents.execution_engine.engine as engine_mod

    return Path(engine_mod.__file__).parent


def _chat_surface_source_files() -> list[Path]:
    """The engine kernel + the router + the Concierge — the SC-001 scanned surface."""
    import app.agents.chat.concierge as concierge_mod
    import app.api.chat_router as chat_router_mod

    files = sorted(_engine_dir().glob("*.py"))
    files.append(Path(chat_router_mod.__file__))
    files.append(Path(concierge_mod.__file__))
    return files


def test_throwaway_name_absent_from_engine_router_concierge() -> None:
    """The throwaway workflow name appears in NONE of the engine / router / concierge
    source — the SC-001 gate. The kernel knows no workflow by name (SC-001/INV-1)."""
    for path in _chat_surface_source_files():
        src = path.read_text(encoding="utf-8")
        assert _THROWAWAY_WF not in src, (
            f"throwaway workflow name {_THROWAWAY_WF!r} leaked into {path} — the "
            f"engine/router/concierge must know NO workflow by name (SC-001/INV-1)"
        )


# A name-keyed control-flow branch: a comparison against pipeline_type / spec.id /
# a workflow_name literal. Comments/docstrings mention these terms WITHOUT ``==``, so
# requiring the operator matches only real branches (mirrors test_sc001_gate_flag).
_NAME_BRANCH_RE = re.compile(r"(pipeline_type|spec\.id|workflow_name)\s*==")


def test_no_name_keyed_branch_in_chat_surface() -> None:
    """No ``pipeline_type == / spec.id == / workflow_name ==`` branch exists in the chat
    surface (the router + the Concierge). Routing + Concierge dispatch are keyed on
    generic run state + capability names ONLY (SC-001/INV-1)."""
    import app.agents.chat.concierge as concierge_mod
    import app.api.chat_router as chat_router_mod

    for mod in (chat_router_mod, concierge_mod):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        offenders = _NAME_BRANCH_RE.findall(src)
        assert not offenders, (
            f"a name-keyed branch {offenders} exists in {mod.__file__} — the chat "
            f"surface must never branch on a workflow name (SC-001/INV-1)"
        )
