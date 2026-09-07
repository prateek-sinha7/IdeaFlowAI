"""
Concurrency Policy for CI Evaluation Management.

Provides concurrency semantics for GitHub workflow runs:
- Newer PR revisions cancel older runs
- Distinct manual/reusable intents remain independent
- No ambiguity from run attempt, merge SHA, or ref conflicts
- Deterministic supersession group classification

This module wraps evaluation_identity for run-management use cases.

Requirements: 2.15, 2.16, 3.11, 3.14
"""

from __future__ import annotations

from typing import Any
from agents.ci.evaluation_identity import (
    EvaluationIdentity,
    SupersessionGroup,
    compute_identity,
    classify_supersession_group,
    can_supersede,
    is_stale_sha,
)


def classify_event(event: dict[str, Any]) -> SupersessionGroup:
    """
    Classify a GitHub event into a supersession group for concurrency management.

    Runs in the same group may supersede each other based on SHA and intent.
    - PR runs coalesce by (owner, name, "pr", pr_number)
    - Manual dispatch runs coalesce by (owner, name, "manual", intent_hash)
    - Distinct intents remain independent

    Args:
        event: GitHub Actions event context dict containing:
          - repository (owner/name)
          - event_name (event type)
          - sha (commit SHA)
          - pull_request (for PR events)
          - inputs (for workflow_dispatch events)

    Returns:
        SupersessionGroup for concurrency management

    Raises:
        ValueError: If event is malformed or invalid
    """
    identity = compute_identity(event)
    return classify_supersession_group(identity)


def should_cancel_previous(
    new_run_event: dict[str, Any],
    in_progress_run_event: dict[str, Any],
) -> bool:
    """
    Determine if a new run should cancel an in-progress run.

    Supersession is allowed when:
    1. Both runs are in the same supersession group (same PR, same intent, etc.)
    2. New run has strictly later SHA (for PR events)
    3. OR they are distinct manual intents (no cancellation)

    Args:
        new_run_event: GitHub event for the new run
        in_progress_run_event: GitHub event for the in-progress run

    Returns:
        True if new run should cancel in-progress run; False otherwise

    Raises:
        ValueError: If either event is malformed
    """
    older_identity = compute_identity(in_progress_run_event)
    newer_identity = compute_identity(new_run_event)

    return can_supersede(older_identity, newer_identity)


def verify_evaluation_sha(
    event: dict[str, Any],
    current_head_sha: str,
) -> bool:
    """
    Verify that an evaluation's SHA matches the current head.

    An evaluation with a stale SHA does not satisfy the current-head requirement.
    This prevents outdated evaluation results from being mistaken for current status.

    Args:
        event: GitHub event context with SHA
        current_head_sha: Current HEAD SHA (must be 40-char hex)

    Returns:
        True if event SHA matches or supersedes current head; False if stale

    Raises:
        ValueError: If either SHA is invalid
    """
    identity = compute_identity(event)
    # Stale if event SHA is lexicographically less than current
    return not is_stale_sha(identity.exact_sha, current_head_sha)


# Exports
__all__ = [
    "classify_event",
    "should_cancel_previous",
    "verify_evaluation_sha",
    "SupersessionGroup",
    "EvaluationIdentity",
]
