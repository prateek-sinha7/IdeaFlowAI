"""LIVE S1 diagnostic — does REAL Haiku fix the Save button? (opt-in, tokens!)

Run via ``./run-eval.sh live-s1``. Skipped without LLM credentials and
excluded from every default/offline mode (``requires_api_key``).

This is the prompt-iteration loop's measuring stick, NOT a CI gate: it sends
the EXACT production surface — the composed system prompt (via the real
``create_runner``) + the slimmed dispatch message + the seeded sandbox
(mini_prototype.html + design.md) — to the real model, then checks the
delivered file the same way a user would: is the Save button actually wired?

On failure it prints the agent's streamed text, its tool calls, and the
delivered Save-button region, so you can see HOW the model misunderstood and
iterate on `agents/prompts/prototype-revision-agent/AGENT.md`.

Budget: mini fixture (~3 KB) + one agent pass ≈ a few thousand tokens on
Haiku per run. Token usage is printed per run.
"""

from __future__ import annotations

import os
import re
import uuid

import pytest

from tests.evals.conftest import FIXTURES_DIR

pytestmark = [pytest.mark.eval, pytest.mark.requires_api_key]

INSTRUCTION = "Make the Save button on Settings actually save"


def _has_llm_credentials() -> bool:
    from app.core.config import settings

    return bool(
        settings.ANTHROPIC_API_KEY
        or settings.AWS_BEARER_TOKEN_BEDROCK
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
    )


@pytest.mark.skipif(not _has_llm_credentials(), reason="no LLM credentials configured")
@pytest.mark.asyncio
async def test_live_haiku_wires_the_save_button(runs_root, capsys) -> None:
    from agents.capabilities.context_providers.previous_run import (
        _slim_revision_message,
    )
    from agents.factory import AgentContext, create_runner
    from app.agents.sandbox import RunSandbox
    from app.agents.static_check import static_check

    mini_html = (FIXTURES_DIR / "mini_prototype.html").read_text(encoding="utf-8").strip()
    design_md = (FIXTURES_DIR / "design.md").read_text(encoding="utf-8")

    # ── Seed the sandbox exactly as the previous_run provider would ──────────
    run_id = f"live-s1-{uuid.uuid4().hex[:8]}"
    user_id = "eval-live"
    sandbox = RunSandbox(user_id, run_id)
    sandbox.ensure()
    sandbox.write("prototype.html", mini_html)
    sandbox.write("design.md", design_md)

    # ── The exact production dispatch message (slimmed user turn) ────────────
    framed = (
        "=== REVISION REQUEST ===\n"
        f"{INSTRUCTION}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{mini_html}\n"
        "=== END EXISTING HTML ==="
    )
    dispatch = _slim_revision_message(framed, "prototype.html")

    # ── Real runner: real composed system prompt, real model (Haiku default) ─
    ctx = AgentContext(
        user_request=dispatch,
        user_id=user_id,
        run_id=run_id,
        model=None,  # None ⇒ build_model default (Haiku)
    )
    runner = create_runner(
        "prototype-revision-agent", ctx, thread_id=f"{run_id}:live"
    )

    streamed_text: list[str] = []
    tool_calls: list[str] = []
    usage = {"input": 0, "output": 0}
    async for event in runner.astream_events(dispatch):
        etype = event.get("type")
        if etype == "chunk":
            streamed_text.append(event["chunk"])
        elif etype == "tool_call":
            args = str(event.get("args", ""))[:160]
            tool_calls.append(f"{event.get('tool')}({args})")
        elif etype == "usage":
            usage["input"] += event.get("input_tokens", 0)
            usage["output"] += event.get("output_tokens", 0)

    final_path = sandbox.path_for("prototype.html")
    final_html = final_path.read_text(encoding="utf-8")

    # ── Diagnostics (always printed — run with -s to see them live) ──────────
    save_region = "\n".join(
        line for line in final_html.splitlines() if "save" in line.lower()
    )
    print("\n=== LIVE S1 DIAGNOSTICS ===")
    print(f"tokens: in={usage['input']} out={usage['output']}")
    print(f"tool calls ({len(tool_calls)}):")
    for tc in tool_calls:
        print(f"  - {tc}")
    print(f"agent text:\n{''.join(streamed_text)[:1500]}")
    print(f"delivered Save-button region:\n{save_region or '(no line mentions save)'}")
    print("=== END DIAGNOSTICS ===\n")

    # ── The user's check: is the Save button actually wired? ─────────────────
    # Accept either wiring style (inline onclick, or script-side binding on the
    # button's id) — but the handler must EXIST as a function/listener, not
    # just be named.
    btn_match = re.search(r"<button[^>]*id=\"save-btn\"[^>]*>", final_html)
    assert btn_match, "Save button disappeared from the delivered file"
    btn_tag = btn_match.group(0)

    inline = re.search(r'onclick="([A-Za-z_$][\w$]*)\s*\(', btn_tag)
    script_bound = re.search(
        r"(getElementById\(['\"]save-btn['\"]\)|querySelector\(['\"]#save-btn['\"]\))"
        r"[\s\S]{0,120}addEventListener",
        final_html,
    )
    wired = False
    if inline:
        fn = inline.group(1)
        wired = bool(
            re.search(rf"function\s+{re.escape(fn)}\s*\(", final_html)
            or re.search(rf"{re.escape(fn)}\s*=\s*(async\s*)?\(", final_html)
        )
    wired = wired or bool(script_bound)
    assert wired, (
        "LIVE MISS: Haiku did not wire the Save button — see the diagnostics "
        "above (tool calls + delivered region) and iterate on "
        "agents/prompts/prototype-revision-agent/AGENT.md"
    )

    # And the edit must not have broken the document structurally.
    sres = static_check(final_path)
    assert sres.ok, f"Haiku's edit introduced static issues: {sres.issues}"
