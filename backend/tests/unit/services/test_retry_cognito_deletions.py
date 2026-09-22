"""The retry pause curve for queued Cognito deletions: ``min(2 * attempt, 300)``.

Pinned because the formula is a stated requirement rather than an implementation detail,
and because it is the kind of expression that silently degrades (an off-by-one, a lost cap)
without any test noticing.

Pure arithmetic — no queue, no pool, no session. The script's BATCH behaviour (what a run
does to ``pending_cognito_deletions`` rows, and that a fully successful batch never sleeps)
lives in ``tests/integration/external/test_retry_cognito_deletions_external.py``.
"""

from __future__ import annotations

import pytest

from app.scripts import retry_cognito_deletions as script


class TestBackoffSeconds:
    """The retry pause curve: ``min(2 * attempt, 300)``.

    Pinned because the formula is a stated requirement rather than an
    implementation detail, and because it is the kind of expression that silently
    survives being changed to something plausible-looking. The cap matters most:
    without it a long-lived pending row would eventually make one scheduled run
    sleep past the workflow's 15-minute timeout and get killed mid-drain.
    """

    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [
            (1, 2),
            (2, 4),
            (3, 6),
            # --max-attempts 3 is what the scheduled job passes, so the three
            # rows above are the only values it can produce in practice.
            (149, 298),
            (150, 300),  # first attempt that reaches the cap exactly
            (151, 300),  # and it never exceeds it
            (10_000, 300),
        ],
    )
    def test_backoff_follows_two_times_attempt_capped_at_300(self, attempt, expected):
        assert script.backoff_seconds(attempt) == expected

    def test_backoff_is_monotonic_and_never_negative(self):
        """No attempt count may produce a shorter or negative wait than a lower one.

        A negative value would be a ``ValueError`` from ``time.sleep`` in the
        middle of a drain, which is a far worse outcome than a slow retry.
        """
        values = [script.backoff_seconds(n) for n in range(1, 400)]
        assert all(v >= 0 for v in values)
        assert values == sorted(values)
        assert max(values) == script.BACKOFF_CAP_SECONDS

