"""LIVE S2 diagnostic — does REAL Haiku make the Reports page reachable? (opt-in, tokens!)

Run via ``./run-eval.sh live-s2``. Skipped without LLM credentials and
excluded from every default/offline mode (``requires_api_key``).

Mirrors ``test_live_s1.py`` exactly (same driver, same production surface —
see ``live_driver.py``), but for the S2 instruction: "Add a Reports page
reachable from the sidebar". The scripted S2 eval
(``test_scenarios.py::test_s2_partial_fix_is_caught_and_completed``) showed
the PIPELINE has no backstop for a half-done edit (section + route, no nav
link); this test asks the separate question — on THIS instruction, does the
real model do the whole job on its own?

For a MULTI-sample pass-rate, use ``./run-eval.sh benchmark s2`` instead —
this single-shot test only tells you pass/fail on one roll of the dice.
"""

from __future__ import annotations

import os

import pytest

from tests.evals.revision_fulfillment.live_driver import run_live_scenario_once

pytestmark = [pytest.mark.eval, pytest.mark.requires_api_key]


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
async def test_live_haiku_makes_reports_page_reachable(runs_root, capsys) -> None:
    print()  # blank line before live progress starts
    result = await run_live_scenario_once("s2", on_event=print)

    reports_region = "\n".join(
        line for line in result.final_html.splitlines()
        if "report" in line.lower() or "nav-item" in line.lower()
    )
    print("\n=== LIVE S2 DIAGNOSTICS ===")
    print(f"tokens: in={result.tokens_in} out={result.tokens_out}")
    print(f"tool calls ({len(result.tool_calls)}):")
    for tc in result.tool_calls:
        print(f"  - {tc}")
    print(f"agent text:\n{result.streamed_text[:1500]}")
    print(f"delivered Reports/nav region:\n{reports_region or '(no matching line)'}")
    status = "ERROR" if result.errored else ("PASS" if result.passed else "MISS")
    print(f"result: {status} — {result.reason or 'satisfied'}")
    print(f"run folder (input/output/log.txt): {result.run_dir}")
    print("=== END DIAGNOSTICS ===\n")

    if result.errored:
        pytest.fail(
            f"INFRASTRUCTURE ERROR (model call itself failed — NOT a prompt/model "
            f"quality issue, do not iterate on AGENT.md for this): {result.reason}. "
            f"See {result.run_dir}/log.txt for the full traceback context."
        )

    assert result.passed, (
        f"LIVE MISS: {result.reason} — see the diagnostics above (tool calls + "
        f"delivered region) and iterate on "
        f"agents/prompts/prototype-revision-agent/AGENT.md"
    )
