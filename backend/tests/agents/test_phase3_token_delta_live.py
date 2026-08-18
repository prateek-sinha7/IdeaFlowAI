"""tests/agents/test_phase3_token_delta_live.py — opt-in LIVE token-delta evidence.

Records the REAL multi-task prototype build's token reduction from the 0C build-task-2+
context compaction (COMPACT-03 / Req 3 / D-04). It runs the SAME multi-task build twice
against a real model — once with compaction ON (the live engine edit from 03-01) and
once with it forced OFF (the pre-compaction full-HTML injection) — accumulates the
`input_tokens` from the runner's `usage` events for each run, and prints the measured
delta + percentage reduction plus the reproduction command.

This is EVIDENCE-ONLY, NEVER a CI gate. The deterministic ≥50% CI gate lives in
`test_phase3_compaction.py` (03-01). The measured figure from a live run (or, if no
live run is available, the manual-run procedure) is copied into `03-02-SUMMARY.md`
under the COMPACT-03 evidence heading.

Opt-in / self-skipping — the default offline suite and credential-less CI stay green.
This test runs ONLY when BOTH hold (the exact dual gate copied from
`test_deep_agent_runner_hitl_live.py`):
  * env ``RUN_LIVE_BEDROCK=1`` is set (explicit opt-in), AND
  * AWS credentials actually resolve (SSO not expired) — probed via STS.
Otherwise it ``pytest.skip(...)``\\s with the exact command to run it live.

Run it live (creds via SSO):
    aws sso login --profile personal-sso
    RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso \\
        python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -v -s
"""

from __future__ import annotations

import os

import pytest

# Importing the scripted-model harness wires RUNS_ROOT→temp + ENV=development at
# import time (so even the live run's sandbox lands in a temp dir, not /app/runs).
from tests.agents import _scripted_model  # noqa: F401  (import for side effects)


# ---------------------------------------------------------------------------
# Skip gate — opt-in (RUN_LIVE_BEDROCK=1) AND credentials must actually resolve.
# Copied VERBATIM from test_deep_agent_runner_hitl_live.py (the established
# double-gated SSO/Bedrock pattern), retargeted to this test's run command.
# ---------------------------------------------------------------------------

_RUN_LIVE_HINT = (
    "LIVE token-delta evidence is opt-in. To run it:\n"
    "    aws sso login --profile personal-sso\n"
    "    RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso "
    "python3.11 -m pytest tests/agents/test_phase3_token_delta_live.py -v -s"
)


def _aws_creds_resolve() -> tuple[bool, str]:
    """Return ``(ok, detail)`` — whether usable AWS credentials resolve right now.

    Probes ``sts.get_caller_identity()`` (cheap, no Bedrock charge). Catches the
    botocore credential/token errors raised when the SSO session is missing or
    expired so the test SKIPS cleanly with a helpful message rather than erroring
    deep inside a live model call.
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
    """Return a skip reason if the live evidence test must not run, else ``None``."""
    if os.getenv("RUN_LIVE_BEDROCK") != "1":
        return f"RUN_LIVE_BEDROCK!=1 — live token-delta evidence is opt-in.\n{_RUN_LIVE_HINT}"

    # Opted in. If a local Anthropic key is configured, build_model() uses that
    # provider and no AWS creds are needed; otherwise require resolvable AWS creds.
    from app.core.config import settings

    if settings.ANTHROPIC_API_KEY:
        return None

    ok, detail = _aws_creds_resolve()
    if not ok:
        return f"{detail}\n{_RUN_LIVE_HINT}"
    return None


# Live gate — evaluated at collection so the LIVE evidence test skips cleanly
# (rather than erroring) in a credential-less / CI environment. Keeping the
# default suite green is the point of the opt-in design. This is a per-TEST
# decorator (not a module ``pytestmark``) so the OFFLINE fault-injection
# regression test below still runs without creds, while ``test_token_delta_live``
# remains opt-in / SSO-gated exactly as before.
_requires_live_bedrock = pytest.mark.skipif(
    _skip_reason() is not None, reason=_skip_reason() or ""
)


# ---------------------------------------------------------------------------
# Seam-existence gate (13-04 / F7) — evaluated at COLLECTION, offline.
#
# The compaction-OFF baseline monkeypatches the engine's generic context
# injector. The Phase-7 decoupling renamed the legacy context-message seam to
# the async `_compose_context_message` (gaining the positional `index` param)
# and relocated the legacy skeleton helper into the registered ``html_skeleton``
# compaction capability — which previously made this module error at live
# setup with AttributeError. Asserting the seam at import time means a future
# rename is caught by the OFFLINE collection pass, not by a paid live run.
# ---------------------------------------------------------------------------

from agents.execution_engine.engine import ExecutionEngine as _Engine  # noqa: E402

assert hasattr(_Engine, "_compose_context_message"), (
    "ExecutionEngine._compose_context_message is gone — the live token-delta "
    "baseline override targets a renamed seam; re-point this module (13-04/F7)"
)


# ---------------------------------------------------------------------------
# Live drive helpers.
# ---------------------------------------------------------------------------

# The full-HTML injection block the OLD (pre-0C) path emitted for build tasks 2+.
# We reconstruct it here so the compaction-OFF baseline run injects exactly what the
# engine did before the 03-01 edit (cap at 120k, matching the legacy pre-0C branch —
# since deleted with the rest of the inline compaction path in Phase 7).
def _full_html_block(current_html: str) -> str:
    html_to_pass = current_html[:120000]
    truncated = len(current_html) > 120000
    return (
        f"\n--- CURRENT HTML (modify this — do NOT rebuild from scratch) ---\n"
        f"{html_to_pass}"
        f"{'...[truncated at 120k]' if truncated else ''}\n"
        f"--- END CURRENT HTML ---"
    )


def _total_input_tokens(events: list[dict]) -> int:
    """Accumulate ``input_tokens`` across a drive's ``usage`` / ``agent_complete``
    events. The runner surfaces per-turn token usage; the engine forwards it on the
    ``agent_complete`` event ``data.input_tokens`` (see backend/CLAUDE.md data-flow).
    """
    total = 0
    for e in events:
        data = e.get("data") or {}
        val = data.get("input_tokens")
        if isinstance(val, int):
            total += val
    return total


async def _drive_live(*, compaction_on: bool) -> list[dict]:
    """Run the real multi-task prototype build against a LIVE model.

    With ``compaction_on=False`` we monkeypatch ``_compose_context_message`` (the
    Phase-7 generic context injector — the successor of the legacy per-agent
    context-message seam) so the build-task-2+ skeleton block is swapped back to
    the full-HTML block — the least-invasive way to reproduce the pre-0C prompt
    for the baseline run (D-04). The skeleton bytes come from the registered
    ``html_skeleton`` compaction capability (where 07-03/07-05 relocated the
    legacy engine skeleton helper). With ``compaction_on=True`` the live engine
    runs unchanged.
    """
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.factory import create_runner as _real_create_runner
    from agents.registry import get_pipeline_agents
    from app.agents.model_factory import build_model
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _scripted_model._RUNS_ROOT  # type: ignore[attr-defined]

    # ── Disable the auto-clarify gate (the clarifier needs live WS round-trips). ─
    # The former module-level auto-clarify flag was DELETED in 07-05; the
    # "force CLARIFY_REQUIRED on every run" behavior is now declared per-workflow by
    # the manifest ``clarify.mode`` ("auto"), read off the CompiledWorkflow at run
    # entry. This driver has no live WS round-trip, so — exactly as the other live
    # harnesses do (`_scripted_model.py:506-513`, `live_harness.py:556-563`) — we wrap
    # ``compile_for_run`` to flip the compiled ``clarify.mode`` to "off", disabling the
    # auto-clarify override precisely as the deleted module flag (set False) used
    # to. The planner still runs; only the PROCEED→CLARIFY_REQUIRED forcing is
    # suppressed (clarify emits no ``input_tokens``), so this removes a HANG, not the
    # A/B token-delta measurement. ``ClarifySpec`` is a mutable dataclass
    # (``agents/workflows/plan.py:289-298``) so the in-place write is valid. Restored
    # in the existing ``finally`` (across both OFF then ON ``_drive_live`` calls).
    _orig_compile_for_run = engine_mod.compile_for_run

    # Live model for every agent (Bedrock Haiku via build_model, or a local
    # Anthropic key if configured) — NOT the scripted fake.
    def _live_create_runner(agent_id, ctx, **kw):
        ctx.model = build_model(getattr(ctx, "model", None))
        return _real_create_runner(agent_id, ctx, **kw)

    # Snapshot the engine-module ``create_runner`` global BEFORE patching it (the
    # engine resolves the bare ``create_runner`` name against its own module
    # namespace), and restore it in the ``finally`` — mirroring the established
    # ``_scripted_model._drive`` precedent (it snapshots ``_orig_engine_create_runner``
    # for this same global because "leaking a nested wrapper or a stale patch would
    # corrupt later runs"). Without this, ``engine_mod.create_runner`` would stay bound
    # to ``_live_create_runner`` after ``_drive_live`` returns, silently routing any
    # later engine-driving test in the session through live Bedrock. (WR-01)
    _orig_engine_create_runner = engine_mod.create_runner
    engine_mod.create_runner = _live_create_runner
    factory_create_runner_orig = None
    try:
        import agents.factory as factory_mod

        factory_create_runner_orig = factory_mod.create_runner
        factory_mod.create_runner = _live_create_runner

        def _patched_compile_for_run(pipeline_type, _orig=_orig_compile_for_run):
            compiled = _orig(pipeline_type)
            compiled.clarify.mode = "off"
            return compiled

        engine_mod.compile_for_run = _patched_compile_for_run

        engine = ExecutionEngine()

        # ── compaction OFF: restore the pre-0C full-HTML injection ──────────────
        _orig_compose_ctx = engine._compose_context_message
        if not compaction_on:
            # NOTE: the engine awaits `self._compose_context_message(...)` — the
            # Phase-7 GENERIC context injector (the rename of the legacy context-
            # message seam, now ASYNC with an added positional `index` param). This
            # override is assigned as an instance attribute (an unbound plain async
            # function), so it must accept the same POSITIONAL shape:
            # (spec, index, ordered_agents, user_message, planning_context, ectx).
            # The skeleton helper is the registered `html_skeleton` compaction
            # capability (07-03/07-05 relocated the legacy engine skeleton helper
            # there); the task_loop strategy compacts the typed prototype-build
            # content with it and the engine wraps the result in the STANDALONE
            # `=== CURRENT PROTOTYPE (skeleton — …) ===` block — so recomputing
            # compact(current_html) here reproduces the injected block byte-exact
            # for the replace. (13-04 / F7)
            from agents.capabilities.registry import CapabilityRegistry, discover

            discover()
            _skeleton_compactor = CapabilityRegistry().resolve(
                "compaction", "html_skeleton"
            )

            async def _full_html_compose_ctx(spec, index, ordered_agents,
                                             user_message, planning_context, ectx):
                msg = await _orig_compose_ctx(
                    spec=spec, index=index, ordered_agents=ordered_agents,
                    user_message=user_message,
                    planning_context=planning_context, ectx=ectx,
                )
                if spec.id == "prototype-build":
                    task_num_str = ectx.build_task_number
                    is_2_plus = task_num_str not in ("", "1")
                    current_html = engine._latest_typed_content(
                        ectx, "prototype-build"
                    ) or ""
                    if is_2_plus and current_html and not current_html.startswith("[Error:"):
                        skeleton = _skeleton_compactor.compact(current_html)
                        skeleton_block = (
                            f"\n=== CURRENT PROTOTYPE (skeleton — call "
                            f"read_file('prototype.html') for full content before "
                            f"editing) ===\n{skeleton}\n=== END CURRENT PROTOTYPE ==="
                        )
                        msg = msg.replace(skeleton_block, _full_html_block(current_html))
                return msg

            # Safe with NO restore ONLY because ``engine`` is a fresh per-call
            # ``ExecutionEngine()`` instance (this is an instance-attribute override,
            # not a class/module patch), so the override dies with this local engine.
            # If a future refactor reused one engine across both A/B drives, this would
            # silently carry into the compaction-ON run — restore it then. (IN-02)
            engine._compose_context_message = _full_html_compose_ctx  # type: ignore[assignment]

        async def _fake_run_planner(user_message, pipeline_run_id, model_id,
                                    cancel_event, ptype="custom", **kwargs):
            return engine._default_planning_context(user_message), "PROCEED"

        engine._run_planner = _fake_run_planner  # type: ignore[assignment]

        async def _noop_store(*a, **k):
            return "artifact-id"

        engine._store.store = _noop_store  # type: ignore[assignment]

        async def _noop_gate(*a, **k):
            return
            yield  # pragma: no cover

        engine._run_review_gate = _noop_gate  # type: ignore[assignment]

        import uuid as _uuid

        specs = get_pipeline_agents("prototype")
        od_context = {
            "template_body": "## Workflow\nUse .card and .grid classes. Build pages "
            "into <section data-page>.",
            "template_id": "web-prototype",
            "ds_id": "default",
            "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;"
            "--border:#ddd;--muted:#888;}",
            "craft_block": "Keep markup semantic; wire every nav link.",
            "is_design_system_required": True,
        }
        run_id = f"live-tokdelta-{'on' if compaction_on else 'off'}-{_uuid.uuid4().hex[:8]}"
        events: list[dict] = []
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Build a multi-page task-management dashboard prototype "
            "with dashboard, tasks, and settings pages.",
            pipeline_run_id=run_id,
            pipeline_type="prototype",
            user_id="live-tokdelta-user",
            od_context=od_context,
            gate_agent_ids=[],
        ):
            events.append(ev)
        return events
    finally:
        engine_mod.compile_for_run = _orig_compile_for_run
        engine_mod.create_runner = _orig_engine_create_runner
        if factory_create_runner_orig is not None:
            factory_mod.create_runner = factory_create_runner_orig


# ---------------------------------------------------------------------------
# Offline fault-injection regression test (ISS-003) — runs WITHOUT live Bedrock.
#
# Pre-fix, ``_drive_live`` poked a DEAD module attribute (the auto-clarify flag set
# False, deleted in 07-05) and NEVER set ``compiled.clarify.mode="off"``,
# so ``prototype``'s ``clarify.mode="auto"`` forced the gate and the run blocked
# forever at ``clarify_engine.py await event.wait()`` (no answerer / no WS client) —
# an ``asyncio.wait_for(_drive_live(...), 10)`` would raise ``TimeoutError``. Post-fix
# the ``compile_for_run`` clarify-off wrap suppresses the gate and the drive RETURNS.
# This test reproduces that bound deterministically: it injects a per-agent scripted
# model (NO Bedrock) so the whole multi-task prototype build runs offline, then asserts
# the drive returns inside a 10s timeout (no hang). It is NOT gated on live creds.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drive_live_does_not_hang_at_clarify_gate(monkeypatch) -> None:
    """ISS-003 regression: the clarify-off wrap defeats the auto-clarify hang offline.

    Drives the real ``_drive_live`` multi-task prototype build with a per-agent
    scripted model (no live Bedrock) and asserts ``asyncio.wait_for(..., 10)`` RETURNS
    instead of hanging at the clarify ``event.wait()``. Documented evidence: pre-fix
    (dead auto-clarify module flag, no ``clarify.mode="off"``) this drive raised
    ``asyncio.TimeoutError`` at the forced clarify gate; post-fix it returns.
    """
    import asyncio

    import agents.factory as factory_mod
    from app.agents import model_factory as model_factory_mod

    from tests.agents._scripted_model import ScriptedFakeChatModel, _scripts_for

    _orig_create_runner = factory_mod.create_runner

    # Per-agent scripted runner: inject a scripted model (so each agent's stream
    # terminates immediately) then defer to the REAL create_runner — the same
    # pattern _scripted_model._drive uses. _drive_live's _live_create_runner first
    # calls build_model(ctx.model); we stub that to a no-op passthrough so no
    # Bedrock client is ever constructed (the scripted ctx.model is what runs).
    def _scripted_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    monkeypatch.setattr(factory_mod, "create_runner", _scripted_create_runner)
    # build_model is called by _drive_live's _live_create_runner BEFORE the real
    # create_runner; stub it so it never touches Bedrock and returns the already-set
    # scripted instance (create_runner re-sets ctx.model to the scripted model anyway).
    monkeypatch.setattr(
        model_factory_mod, "build_model", lambda *a, **k: ScriptedFakeChatModel([])
    )

    # The drive MUST return within the bound. Pre-fix this raised asyncio.TimeoutError
    # at the forced clarify gate; post-fix the clarify-off wrap lets it complete.
    #
    # HANG detector, not a latency assertion: the regression blocks forever waiting on
    # a clarify answer that never arrives, so detection power is the same at any finite
    # bound. The bound is therefore sized for false-positive immunity. At 10s this
    # failed intermittently under ``-n auto`` — the drive runs REAL headless Chromium
    # (``render_check`` -> ``page.goto``) four times (2 tasks x a 2-attempt validation
    # fix loop), which does not fit a 10s budget on a loaded box; the run was still
    # progressing through task 2/2 when the bound cancelled it. Do not lower this to
    # "keep the test fast" — a slow-but-live drive is not the failure being guarded.
    events = await asyncio.wait_for(_drive_live(compaction_on=True), timeout=120)

    assert isinstance(events, list), "the offline drive must return its event list"


# ---------------------------------------------------------------------------
# The live evidence test.
# ---------------------------------------------------------------------------


@_requires_live_bedrock
@pytest.mark.asyncio
async def test_token_delta_live() -> None:
    """Live evidence: build-task-2+ compaction reduces accumulated input tokens.

    Runs the multi-task prototype build twice against a real model (compaction ON
    vs OFF), accumulates `input_tokens`, prints the delta + reduction + reproduction
    command, and asserts the compacted run used strictly fewer input tokens. This is
    EVIDENCE-ONLY and NEVER a CI gate (it self-skips without the dual opt-in gate).
    """
    events_off = await _drive_live(compaction_on=False)
    events_on = await _drive_live(compaction_on=True)

    tokens_off = _total_input_tokens(events_off)
    tokens_on = _total_input_tokens(events_on)

    assert tokens_off > 0, (
        "baseline (compaction OFF) accumulated zero input tokens — no usage events "
        "captured; the live run did not produce token telemetry"
    )

    delta = tokens_off - tokens_on
    pct = (delta / tokens_off * 100.0) if tokens_off else 0.0

    print("\n" + "=" * 72)
    print("COMPACT-03 LIVE token-delta evidence (multi-task prototype build)")
    print("-" * 72)
    print(f"  input_tokens (compaction OFF / pre-0C): {tokens_off}")
    print(f"  input_tokens (compaction ON  / 0C):     {tokens_on}")
    print(f"  delta (tokens saved):                    {delta}")
    print(f"  reduction:                               {pct:.1f}%")
    print("-" * 72)
    print("  Reproduction:")
    print("    aws sso login --profile personal-sso")
    print("    RUN_LIVE_BEDROCK=1 AWS_PROFILE=personal-sso \\")
    print("      python3.11 -m pytest "
          "tests/agents/test_phase3_token_delta_live.py -v -s")
    print("=" * 72)

    assert tokens_on < tokens_off, (
        f"compaction-ON build must use fewer accumulated input tokens than the "
        f"pre-0C full-HTML build: on={tokens_on} vs off={tokens_off}"
    )
