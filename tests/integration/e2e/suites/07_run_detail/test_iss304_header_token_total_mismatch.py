"""ISS-304 — the run-detail chat header's token total must equal the run's
own API `token_usage.total_tokens`, not the (larger, inconsistent)
`pipeline_complete.total_tokens` event field.

`useWorkflow.ts`'s `pipeline_complete` case (~line 794) prefers
`msg.total_tokens` over the value already accumulated from `agent_complete`
events, and `LaneRunHeader.deriveLaneMeta` renders that verbatim in the
`lane-run-meta` row. On run `a0693fcd-9451-4c19-a9e7-61474ea03516` the API's
`token_usage.total_tokens` is 10428 (10.4K, matching the Run History list
card) but the header shows "17.9K tokens" (from `pipeline_complete`'s
independently-computed 17931).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

MISMATCHED_TOKEN_RUN = "a0693fcd-9451-4c19-a9e7-61474ea03516"
EXPECTED_TOKENS_K = "10.4K"


@pytest.mark.issue("ISS-304")
def test_run_detail_header_token_total_matches_api(page):
    """The chat header's token figure must match token_usage.total_tokens
    from the run's own API response (10.4K here), not disagree with it."""
    page.goto(f"/runs/{MISMATCHED_TOKEN_RUN}")

    meta = page.locator('[data-testid="lane-run-meta"]')
    expect(meta).to_contain_text(re.compile(r"tokens"))
    expect(meta).to_contain_text(EXPECTED_TOKENS_K)
