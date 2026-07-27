"""LIVE example1 diagnostic — real-world artifact, real user complaint (opt-in, tokens!).

Run via ``./run-eval.sh live-example1``. Skipped without LLM credentials and
excluded from every default/offline mode (``requires_api_key``).

Unlike S1/S2 (hand-authored, ~3KB), this scenario uses a REAL prototype
(``.investigations/revision-pipeline-thinking-issue/artifacts/example-1/``,
1,885 lines / ~124KB) and the REAL revision request a user filed against it:
"all the pages seems blank, contains no data only menus are showing, please
add content to all the pages." No ``design.md`` is provided for this
fixture — it exercises the AGENT.md's documented no-design.md fallback path.

Direct inspection of the fixture found the actual defect: the entire
document is DUPLICATED (every ``<section data-page="...">`` appears twice,
each copy already holding real content) — a rendering bug, not literally
empty markup. The checker (``live_driver._example1_pages_have_real_content``)
verifies the STRUCTURAL half of a correct fix: every known page exists
EXACTLY ONCE post-edit and still has substantive content (not stripped to a
placeholder while deduplicating). It cannot observe whether the fixed page
actually RENDERS correctly in a browser — that would need ``render_check``
(headless Chromium), out of scope for this static-diagnostic tier.

Budget: this fixture is ~40x larger than S1/S2's — expect materially higher
token cost per run (the September session's S1/S2 runs were ~50-130K tokens;
this fixture is proportionally bigger going in). Token usage is printed.

For a MULTI-sample pass rate, use ``./run-eval.sh benchmark example1 [N]``.
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


def test_example1_fixture_is_self_validating() -> None:
    """The raw (unfixed) fixture must FAIL the checker — proves the checker
    actually detects the real defect instead of trivially passing everything.
    Offline, 0 tokens — runs in every mode, not just requires_api_key.
    """
    from tests.evals.revision_fulfillment.live_driver import LIVE_SCENARIOS

    scenario = LIVE_SCENARIOS["example1"]
    passed, reason = scenario.checker(scenario.html)
    assert not passed, "the raw, unfixed fixture unexpectedly passed the checker"
    assert "still appears" in reason  # the known duplication defect


@pytest.mark.skipif(not _has_llm_credentials(), reason="no LLM credentials configured")
@pytest.mark.asyncio
async def test_live_haiku_fixes_the_blank_pages(runs_root, capsys) -> None:
    print()  # blank line before live progress starts
    result = await run_live_scenario_once("example1", on_event=print)

    print("\n=== LIVE example1 DIAGNOSTICS ===")
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
        f"agents/prompts/prototype-revision-agent/AGENT.md"
    )
