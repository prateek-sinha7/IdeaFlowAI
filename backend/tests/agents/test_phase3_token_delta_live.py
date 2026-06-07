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


# Module-level gate: evaluated at collection so the whole module skips cleanly
# (rather than erroring) in a credential-less / CI environment. Keeping the
# default suite green is the point of the opt-in design.
pytestmark = pytest.mark.skipif(_skip_reason() is not None, reason=_skip_reason() or "")


# ---------------------------------------------------------------------------
# Live drive helpers.
# ---------------------------------------------------------------------------

# The full-HTML injection block the OLD (pre-0C) path emitted for build tasks 2+.
# We reconstruct it here so the compaction-OFF baseline run injects exactly what the
# engine did before the 03-01 edit (cap at 120k, matching engine.py:2545).
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

    With ``compaction_on=False`` we monkeypatch ``_build_context_message`` so the
    ``is_build_task_2_plus`` skeleton branch is swapped back to the full-HTML block —
    the least-invasive way to reproduce the pre-0C prompt for the baseline run
    (D-04). With ``compaction_on=True`` the live engine edit runs unchanged.
    """
    import agents.execution_engine.engine as engine_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.factory import create_runner as _real_create_runner
    from agents.registry import get_pipeline_agents
    from app.agents.model_factory import build_model
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _scripted_model._RUNS_ROOT  # type: ignore[attr-defined]
    engine_mod.ALWAYS_CLARIFY = False

    # Live model for every agent (Bedrock Haiku via build_model, or a local
    # Anthropic key if configured) — NOT the scripted fake.
    def _live_create_runner(agent_id, ctx, **kw):
        ctx.model = build_model(getattr(ctx, "model", None))
        return _real_create_runner(agent_id, ctx, **kw)

    engine_mod.create_runner = _live_create_runner
    factory_create_runner_orig = None
    try:
        import agents.factory as factory_mod

        factory_create_runner_orig = factory_mod.create_runner
        factory_mod.create_runner = _live_create_runner

        engine = ExecutionEngine()

        # ── compaction OFF: restore the pre-0C full-HTML injection ──────────────
        _orig_build_ctx = engine._build_context_message
        if not compaction_on:
            # NOTE: the engine calls `self._build_context_message(...)` POSITIONALLY
            # (engine.py:1174). This override is assigned as an instance attribute (an
            # unbound plain function), so it must accept the same POSITIONAL shape — a
            # keyword-only signature here raises `TypeError: takes 0 positional
            # arguments but 6 were given` on the first (baseline) call. (#WR-01)
            def _full_html_build_ctx(spec, ordered_agents, user_message,
                                     accumulated_outputs, planning_context, ectx):
                msg = _orig_build_ctx(
                    spec=spec, ordered_agents=ordered_agents,
                    user_message=user_message,
                    accumulated_outputs=accumulated_outputs,
                    planning_context=planning_context, ectx=ectx,
                )
                if spec.id == "prototype-build":
                    task_num_str = accumulated_outputs.get("_build_task_number", "")
                    is_2_plus = task_num_str not in ("", "1")
                    current_html = accumulated_outputs.get("prototype-build", "")
                    if is_2_plus and current_html and not current_html.startswith("[Error:"):
                        skeleton = engine._extract_html_skeleton(current_html)
                        skeleton_block = (
                            f"\n=== CURRENT PROTOTYPE (skeleton — call "
                            f"read_file('prototype.html') for full content before "
                            f"editing) ===\n{skeleton}\n=== END CURRENT PROTOTYPE ==="
                        )
                        msg = msg.replace(skeleton_block, _full_html_block(current_html))
                return msg

            engine._build_context_message = _full_html_build_ctx  # type: ignore[assignment]

        async def _fake_run_planner(user_message, pipeline_run_id, model_id,
                                    cancel_event, ptype="custom"):
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
        if factory_create_runner_orig is not None:
            factory_mod.create_runner = factory_create_runner_orig


# ---------------------------------------------------------------------------
# The test.
# ---------------------------------------------------------------------------


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
