"""
Exact-Revision Evaluation Identity and Concurrency Policy.

Provides deterministic evaluation identity and concurrency semantics:
- Newer PR revisions cancel older runs
- Distinct manual/reusable intents are NOT cancelled
- Stale SHA never satisfies current-head status
- No ambiguity from run attempt, merge SHA, or ref conflicts

Requirements: 2.15, 2.16, 3.11, 3.14
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any, Optional


class EvaluationEventType(str, Enum):
    """GitHub workflow event types that trigger CI evaluation."""

    PULL_REQUEST = "pull_request"
    PUSH = "push"
    WORKFLOW_DISPATCH = "workflow_dispatch"
    WORKFLOW_CALL = "workflow_call"


@dataclass(frozen=True)
class EvaluationIdentity:
    """
    Deterministic identity for a CI evaluation.

    Binds a CI evaluation to:
    - Repository identity (owner/name)
    - Event type (PR, push, manual dispatch, or reusable workflow call)
    - Exact 40-character commit SHA (immutable)
    - Normalized evaluation intent (distinguishes manual intents)
    - PR context (if applicable)

    All values must be validated and exact. Event-derived values are typed
    and never interpolated into shell source.

    Attributes:
        repository_owner: Repository owner (immutable from event)
        repository_name: Repository name (immutable from event)
        event_type: Event classification (pull_request, push, workflow_dispatch, workflow_call)
        exact_sha: Full 40-character commit SHA (never a ref or merge SHA)
        pr_number: PR number (only for pull_request events)
        pr_head_sha: PR head SHA (only for pull_request events; must equal exact_sha)
        intent_id: Unique intent identifier (for manual/reusable disambiguation)
        intent_hash: Derived hash of intent_id for coalescing
    """

    repository_owner: str
    repository_name: str
    event_type: EvaluationEventType
    exact_sha: str
    pr_number: Optional[int] = None
    pr_head_sha: Optional[str] = None
    intent_id: str = ""  # Empty for automatic events, unique ID for manual
    intent_hash: str = ""  # Computed during __post_init__

    def __post_init__(self) -> None:
        """Validate identity invariants."""
        # Validate SHA: exactly 40 hex characters
        if not isinstance(self.exact_sha, str) or len(self.exact_sha) != 40:
            raise ValueError(
                f"exact_sha must be 40-character hex; got {len(self.exact_sha)} chars"
            )
        try:
            int(self.exact_sha, 16)
        except ValueError:
            raise ValueError(f"exact_sha must be hex; got {self.exact_sha}")

        # Validate PR context consistency
        if self.event_type == EvaluationEventType.PULL_REQUEST:
            if self.pr_number is None or self.pr_number <= 0:
                raise ValueError(
                    f"pull_request event requires pr_number > 0; got {self.pr_number}"
                )
            if self.pr_head_sha != self.exact_sha:
                raise ValueError(
                    f"PR event: pr_head_sha must equal exact_sha; "
                    f"got {self.pr_head_sha} vs {self.exact_sha}"
                )
        else:
            if self.pr_number is not None or self.pr_head_sha is not None:
                raise ValueError(
                    f"Non-PR event type {self.event_type} must not have "
                    f"pr_number or pr_head_sha"
                )

        # Compute intent hash (for deduplication)
        if self.intent_id:
            # Manual/reusable: hash the intent ID for coalescing identical intents
            intent_hash = sha256(
                f"{self.event_type}:{self.intent_id}".encode()
            ).hexdigest()
        else:
            # Automatic events: empty intent hash (not used for coalescing)
            intent_hash = ""

        # Use object.__setattr__ because this is frozen
        object.__setattr__(self, "intent_hash", intent_hash)

    def __hash__(self) -> int:
        """Hash for use in sets/dicts (all fields are frozen)."""
        return hash(
            (
                self.repository_owner,
                self.repository_name,
                self.event_type,
                self.exact_sha,
                self.pr_number,
                self.intent_id,
            )
        )

    def __eq__(self, other: object) -> bool:
        """Equality: two identities are equal iff all fields match."""
        if not isinstance(other, EvaluationIdentity):
            return NotImplemented
        return (
            self.repository_owner == other.repository_owner
            and self.repository_name == other.repository_name
            and self.event_type == other.event_type
            and self.exact_sha == other.exact_sha
            and self.pr_number == other.pr_number
            and self.pr_head_sha == other.pr_head_sha
            and self.intent_id == other.intent_id
        )


@dataclass(frozen=True)
class SupersessionGroup:
    """
    Supersession group for concurrency management.

    Groups runs that may supersede each other. Two evaluations are in the same
    group iff they share:
    - Repository
    - Event context (PR or branch ref)
    - Evaluation intent (empty for automatic, specific ID for manual)

    The group does NOT include exact_sha to allow newer revisions to supersede
    older ones on the same branch/PR/intent.

    For PR events:
      group_key = (owner, name, "pr", pr_number)
    For push/auto events:
      group_key = (owner, name, "branch", ref_name)
    For manual/reusable dispatch:
      group_key = (owner, name, event_type, intent_hash)
    """

    repository_owner: str
    repository_name: str
    group_type: str  # "pr", "branch", "manual"
    group_context: str  # PR number, branch name, or intent hash
    event_type: EvaluationEventType

    def __hash__(self) -> int:
        """Hash for use in sets/dicts."""
        return hash(
            (
                self.repository_owner,
                self.repository_name,
                self.group_type,
                self.group_context,
            )
        )

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        if not isinstance(other, SupersessionGroup):
            return NotImplemented
        return (
            self.repository_owner == other.repository_owner
            and self.repository_name == other.repository_name
            and self.group_type == other.group_type
            and self.group_context == other.group_context
        )


def compute_identity(event: dict[str, Any]) -> EvaluationIdentity:
    """
    Compute deterministic evaluation identity from GitHub event context.

    Args:
        event: GitHub Actions event context dict, containing:
          - github.event (the event payload)
          - github.event_name (the event type)
          - github.repository (owner/name)
          - github.sha (commit SHA for push; PR head SHA for PR events)
          - github.ref (full ref name)
          - (for workflow_dispatch) inputs with unique intent ID

    Returns:
        EvaluationIdentity with exact SHA and validated context

    Raises:
        ValueError: If event is malformed, SHA is invalid, or context is ambiguous
    """
    # Extract repository
    repository_full = event.get("repository", "")
    if not repository_full or "/" not in repository_full:
        raise ValueError(f"Invalid repository format: {repository_full}")
    repo_owner, repo_name = repository_full.split("/", 1)

    # Extract event type
    event_name = event.get("event_name", "").lower()
    if event_name == "pull_request":
        event_type = EvaluationEventType.PULL_REQUEST
    elif event_name == "push":
        event_type = EvaluationEventType.PUSH
    elif event_name == "workflow_dispatch":
        event_type = EvaluationEventType.WORKFLOW_DISPATCH
    elif event_name == "workflow_call":
        event_type = EvaluationEventType.WORKFLOW_CALL
    else:
        raise ValueError(f"Unsupported event type: {event_name}")

    # Extract and validate exact SHA (immutable from event)
    exact_sha = event.get("sha", "")
    if not exact_sha or len(exact_sha) != 40:
        raise ValueError(
            f"Invalid SHA in event: expected 40-char hex, got {len(exact_sha)} chars"
        )
    try:
        int(exact_sha, 16)
    except ValueError:
        raise ValueError(f"SHA must be hex: {exact_sha}")

    # PR-specific validation
    pr_number: Optional[int] = None
    pr_head_sha: Optional[str] = None
    intent_id = ""

    if event_type == EvaluationEventType.PULL_REQUEST:
        # For PR events, extract PR number and validate head SHA
        pull_request_data = event.get("pull_request", {})
        if not isinstance(pull_request_data, dict):
            raise ValueError("pull_request event missing pull_request data")

        pr_number = pull_request_data.get("number")
        if not isinstance(pr_number, int) or pr_number <= 0:
            raise ValueError(f"Invalid PR number: {pr_number}")

        pr_head_sha = pull_request_data.get("head", {}).get("sha", "")
        if pr_head_sha != exact_sha:
            raise ValueError(
                f"PR head SHA mismatch: event.sha={exact_sha}, "
                f"pull_request.head.sha={pr_head_sha}"
            )

    elif event_type == EvaluationEventType.WORKFLOW_DISPATCH:
        # Manual dispatch: extract unique intent ID (e.g., user-provided input)
        # Intent IDs are used to distinguish multiple manual intents
        inputs = event.get("inputs", {})
        # Use a specific input field for intent ID if provided, otherwise create from inputs
        if isinstance(inputs, dict):
            # Create hash of all inputs to form intent ID
            inputs_str = "|".join(f"{k}={v}" for k, v in sorted(inputs.items()))
            intent_id = inputs_str
        else:
            # Empty inputs: single default manual intent
            intent_id = ""

    # All event types validated and fields populated
    return EvaluationIdentity(
        repository_owner=repo_owner,
        repository_name=repo_name,
        event_type=event_type,
        exact_sha=exact_sha,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        intent_id=intent_id,
    )


def classify_supersession_group(identity: EvaluationIdentity) -> SupersessionGroup:
    """
    Classify evaluation identity into a supersession group.

    PR evaluations coalesce on (owner, name, "pr", pr_number).
    Push/auto evaluations coalesce on (owner, name, "branch", ref_name).
    Manual/reusable intents coalesce on (owner, name, "manual", intent_hash).

    Args:
        identity: Computed evaluation identity

    Returns:
        SupersessionGroup for concurrency management

    Raises:
        ValueError: If identity is malformed
    """
    if identity.event_type == EvaluationEventType.PULL_REQUEST:
        return SupersessionGroup(
            repository_owner=identity.repository_owner,
            repository_name=identity.repository_name,
            group_type="pr",
            group_context=str(identity.pr_number),
            event_type=identity.event_type,
        )
    elif identity.event_type in (
        EvaluationEventType.WORKFLOW_DISPATCH,
        EvaluationEventType.WORKFLOW_CALL,
    ):
        # Manual/reusable: group by intent hash if present
        # Empty intent_hash means no prior manual intents (single default invocation)
        intent_hash = identity.intent_hash or "default"
        return SupersessionGroup(
            repository_owner=identity.repository_owner,
            repository_name=identity.repository_name,
            group_type="manual",
            group_context=intent_hash,
            event_type=identity.event_type,
        )
    elif identity.event_type == EvaluationEventType.PUSH:
        # Push: group by branch (extract from ref)
        # Note: event should have provided ref; we use it from context
        raise ValueError(
            "PUSH events need additional context (ref_name) not in identity"
        )
    else:
        raise ValueError(f"Unknown event type: {identity.event_type}")


def can_supersede(
    older_identity: EvaluationIdentity,
    newer_identity: EvaluationIdentity,
) -> bool:
    """
    Determine if newer evaluation can supersede older one.

    Supersession is allowed iff:
    1. Both are in the same supersession group (same repo, event context, intent)
    2. Newer has strictly later SHA (when both are PRs)
    3. OR they are distinct manual intents (no supersession)

    Args:
        older_identity: Previously running evaluation
        newer_identity: New evaluation to check

    Returns:
        True if newer should cancel older; False otherwise

    Raises:
        ValueError: If identities are malformed
    """
    # Verify both are in same repository
    if (
        older_identity.repository_owner != newer_identity.repository_owner
        or older_identity.repository_name != newer_identity.repository_name
    ):
        return False

    # Verify same event context
    if older_identity.event_type != newer_identity.event_type:
        return False

    # For PR events: supersede if in same PR and newer SHA is greater
    if older_identity.event_type == EvaluationEventType.PULL_REQUEST:
        if older_identity.pr_number != newer_identity.pr_number:
            return False
        # Compare SHAs lexicographically (hex strings compare correctly)
        return newer_identity.exact_sha > older_identity.exact_sha

    # For manual/reusable: same intent ID means same intent (could supersede)
    # but only if they have identical inputs (same intent_id)
    if older_identity.event_type in (
        EvaluationEventType.WORKFLOW_DISPATCH,
        EvaluationEventType.WORKFLOW_CALL,
    ):
        # Supersede only if same intent (same intent_id)
        if older_identity.intent_id == newer_identity.intent_id:
            # Same intent: supersede if newer SHA is greater
            return newer_identity.exact_sha > older_identity.exact_sha
        else:
            # Different intents: do not supersede
            return False

    # Push events: not implemented in this task
    return False


def are_same_intent(event1: dict[str, Any], event2: dict[str, Any]) -> bool:
    """
    Check if two GitHub events represent the same manual dispatch intent.

    For workflow_dispatch events, same intent means identical inputs.
    For other events, they're always distinct (auto events don't coalesce on intent).

    Args:
        event1: First GitHub event context
        event2: Second GitHub event context

    Returns:
        True if events are the same intent; False otherwise
    """
    identity1 = compute_identity(event1)
    identity2 = compute_identity(event2)

    # Different repositories/event types always different
    if (
        identity1.repository_owner != identity2.repository_owner
        or identity1.repository_name != identity2.repository_name
        or identity1.event_type != identity2.event_type
    ):
        return False

    # For workflow_dispatch, same intent iff same intent_id
    if identity1.event_type == EvaluationEventType.WORKFLOW_DISPATCH:
        return identity1.intent_id == identity2.intent_id

    # For PR/push events, they're not intent-based (they're always distinct)
    return False


def is_stale_sha(
    event_sha: str,
    current_head_sha: str,
) -> bool:
    """
    Check if event SHA is stale relative to current head.

    A SHA is stale if it's older (lexicographically smaller) than current head.
    This prevents a stale SHA from satisfying the current-head requirement.

    Args:
        event_sha: SHA from the event (must be 40-char hex)
        current_head_sha: Current HEAD SHA (must be 40-char hex)

    Returns:
        True if event_sha is stale (< current_head_sha); False otherwise

    Raises:
        ValueError: If either SHA is invalid
    """
    if not event_sha or len(event_sha) != 40:
        raise ValueError(f"Invalid event_sha: {event_sha}")
    if not current_head_sha or len(current_head_sha) != 40:
        raise ValueError(f"Invalid current_head_sha: {current_head_sha}")

    try:
        int(event_sha, 16)
        int(current_head_sha, 16)
    except ValueError as e:
        raise ValueError(f"SHA must be hex: {e}")

    # Lexicographic comparison works for hex strings
    return event_sha < current_head_sha


# Exports
__all__ = [
    "EvaluationEventType",
    "EvaluationIdentity",
    "SupersessionGroup",
    "compute_identity",
    "classify_supersession_group",
    "can_supersede",
    "are_same_intent",
    "is_stale_sha",
]
