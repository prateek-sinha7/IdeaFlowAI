"""Generic LIVE (real-model) test — one parametrized test per scenario YAML
discovered in this phase's scenarios/ folder (opt-in, tokens!).

Run via ``./run-eval.sh <scenario-id> --live`` (e.g. ``./run-eval.sh
prototype_multi_issue_repair --live``), or directly: ``pytest
tests/evals/workflow/prototype/revision/test_live.py -m "eval and
requires_api_key" -k prototype_multi_issue_repair -s -v``. Skipped without
LLM credentials and excluded from every default/offline mode
(``requires_api_key``).

One generic parametrized test per scenario YAML discovered in this folder's
scenarios/ — adding a new scenario YAML automatically gets test coverage
here, no new Python needed. Copy this file verbatim into a new
workflow/<domain>/<variant>/test_live.py for a future pipeline; only the
checkers import line changes.

Trade-off accepted vs. one file per scenario: no per-scenario custom
diagnostics (e.g. a grep for the "Save button" region specifically) —
diagnostics here are generic (tokens, tool call count, run folder path).
``validate_scenario.py``/``./run-eval.sh <id>`` already covers "does this
scenario load and is its checker sane" for every scenario, offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.evals.common.live_scenario import run_live_scenario_once
from tests.evals.common.scenario_discovery import discover_scenarios_in
from tests.evals.workflow.prototype.revision.checkers import CHECKERS

pytestmark = [pytest.mark.eval, pytest.mark.requires_api_key]

PHASE_DIR = Path(__file__).resolve().parent
SCENARIOS = discover_scenarios_in(PHASE_DIR, CHECKERS)


def _has_llm_credentials() -> bool:
    from app.core.config import settings

    return bool(
        settings.ANTHROPIC_API_KEY
        or settings.AWS_BEARER_TOKEN_BEDROCK
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or os.environ.get("AWS_PROFILE")
    )


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS), ids=sorted(SCENARIOS))
@pytest.mark.asyncio
async def test_live_scenario(scenario_id: str) -> None:
    if not _has_llm_credentials():
        pytest.skip("no LLM credentials configured")

    scenario = SCENARIOS[scenario_id]
    print()  # blank line before live progress starts
    result = await run_live_scenario_once(scenario, on_event=print)

    print(f"\n=== LIVE {scenario_id.upper()} DIAGNOSTICS ===")
    print(f"tokens: in={result.tokens_in} out={result.tokens_out}")
    print(f"tool calls ({len(result.tool_calls)}):")
    for tc in result.tool_calls:
        print(f"  - {tc}")
    print(f"agent text:\n{result.streamed_text[:1500]}")
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
        f"LIVE MISS: {result.reason} — see the diagnostics above and iterate on "
        f"agents/prompts/{scenario.agent_id}/AGENT.md"
    )
