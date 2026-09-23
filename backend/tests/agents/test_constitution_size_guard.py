"""tests/agents/test_constitution_size_guard.py — ISS-402.

``_inject_constitution`` (``agents/factory.py``) injects the full, verbatim saved
Constitution into every governed agent's system prompt on every run, with no size
or token guard anywhere in the path. A user who saves an oversized Constitution
(the UI displays a fictitious "4000 chars" limit — see ISS-293 — but the backend
accepts up to 1,048,576) gets that entire block silently prepended to every
agent's system prompt, inflating every future run's prompt cost invisibly.

This test proves the missing guard directly against ``_inject_constitution``: a
Constitution well past any reasonable per-run budget is expected to be bounded
(truncated with a marker) before injection. It fails today because the function
performs no truncation at all.
"""

from __future__ import annotations

import pytest

from agents.factory import AgentContext, _inject_constitution

# Larger than any plausible per-agent prompt budget; small next to the backend's
# real 1_048_576-char cap (ConstitutionRequest.content, app/api/settings.py:355),
# so this is well within what a user can actually save.
_OVERSIZED_CONSTITUTION = "PRINCIPLE: never conflict with policy.\n" * 5000  # ~200K chars


@pytest.mark.issue("ISS-402")
def test_oversized_constitution_is_bounded_before_injection() -> None:
    """An oversized Constitution must be truncated, not injected verbatim.

    ISS-402: nothing between the DB read and the composed prompt string applies a
    length check, a token budget, or a truncation marker. The fix must cap the
    injected block; today the full ~200K-char body is injected unchanged.
    """
    ctx = AgentContext(
        user_request="Analyze the lending domain.",
        user_id="owner-oversized-constitution",
        prewarmed_constitution=_OVERSIZED_CONSTITUTION,
    )

    injected = _inject_constitution(ctx)

    assert len(injected) < len(_OVERSIZED_CONSTITUTION), (
        "an oversized Constitution must be bounded/truncated before injection, "
        "not passed through verbatim into every agent's system prompt"
    )
