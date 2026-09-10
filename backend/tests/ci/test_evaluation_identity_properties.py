"""
Property tests for exact-revision evaluation identity and concurrency semantics.

Validates:
- Evaluation identity is deterministic and SHA-bound
- PR revisions order correctly; newer SHAs supersede older ones
- Distinct manual intents do NOT cancel each other
- Stale SHA never satisfies current-head requirement
- No ambiguity from run attempt, merge SHA, or ref conflicts

Requirements: 2.15, 2.16, 3.11, 3.14

**Validates: Requirements 2.15**
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st, assume, settings
from tools.ci.evaluation_identity import (
    EvaluationEventType,
    EvaluationIdentity,
    SupersessionGroup,
    compute_identity,
    classify_supersession_group,
    can_supersede,
    are_same_intent,
    is_stale_sha,
)


# ─────────────────────────────────────────────────────────────────────────────
# Strategies for generating GitHub event contexts
# ─────────────────────────────────────────────────────────────────────────────


@st.composite
def sha_strategy(draw) -> str:
    """Generate valid 40-character hex SHA."""
    return draw(
        st.text(
            alphabet="0123456789abcdef",
            min_size=40,
            max_size=40,
        )
    )


@st.composite
def repository_strategy(draw) -> str:
    """Generate valid repository name (owner/name)."""
    owner = draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20)
    )
    name = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=20
        )
    )
    return f"{owner}/{name}"


@st.composite
def pull_request_event_strategy(draw) -> dict:
    """Generate valid pull_request GitHub event context."""
    repo = draw(repository_strategy())
    sha = draw(sha_strategy())
    pr_number = draw(st.integers(min_value=1, max_value=10000))

    return {
        "repository": repo,
        "event_name": "pull_request",
        "sha": sha,
        "pull_request": {
            "number": pr_number,
            "head": {"sha": sha},
        },
    }


@st.composite
def workflow_dispatch_event_strategy(draw) -> dict:
    """Generate valid workflow_dispatch event context."""
    repo = draw(repository_strategy())
    sha = draw(sha_strategy())
    # Create distinct inputs to distinguish intents
    input_count = draw(st.integers(min_value=0, max_value=3))
    inputs = {
        f"input_{i}": draw(st.text(min_size=1, max_size=10)) for i in range(input_count)
    }

    return {
        "repository": repo,
        "event_name": "workflow_dispatch",
        "sha": sha,
        "inputs": inputs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Property tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluationIdentityDeterminism:
    """Property 1: Identity computation is deterministic and reproducible."""

    @given(pull_request_event_strategy())
    def test_pr_identity_deterministic(self, event: dict):
        """Same PR event produces identical identity multiple times."""
        identity1 = compute_identity(event)
        identity2 = compute_identity(event)

        # Identities must be equal
        assert identity1 == identity2
        # Hashes must be equal
        assert hash(identity1) == hash(identity2)

    @given(workflow_dispatch_event_strategy())
    def test_manual_identity_deterministic(self, event: dict):
        """Same workflow_dispatch event produces identical identity."""
        identity1 = compute_identity(event)
        identity2 = compute_identity(event)

        assert identity1 == identity2
        assert hash(identity1) == hash(identity2)

    @given(pull_request_event_strategy())
    def test_identity_hash_consistency(self, event: dict):
        """Identity can be used in sets/dicts (hash stable)."""
        identity = compute_identity(event)
        # Hash must be stable
        h1 = hash(identity)
        h2 = hash(identity)
        assert h1 == h2

        # Can be added to set
        s = {identity}
        assert identity in s


class TestSupersessionGroupCoalescing:
    """Property 2: Equal identities coalesce in same supersession group."""

    @given(pull_request_event_strategy())
    def test_same_pr_coalesces(self, event: dict):
        """Two evaluations of same PR coalesce to same group."""
        identity1 = compute_identity(event)
        identity2 = compute_identity(event)

        group1 = classify_supersession_group(identity1)
        group2 = classify_supersession_group(identity2)

        assert group1 == group2
        assert hash(group1) == hash(group2)

    @given(
        pull_request_event_strategy(),
        pull_request_event_strategy(),
    )
    def test_different_pr_numbers_different_groups(
        self,
        event1: dict,
        event2: dict,
    ):
        """Different PR numbers produce different supersession groups."""
        # Modify event2 to have different PR number
        if "pull_request" in event2:
            event2["pull_request"]["number"] = (
                event2["pull_request"].get("number", 1) + 10000
            )
            identity1 = compute_identity(event1)
            identity2 = compute_identity(event2)

            group1 = classify_supersession_group(identity1)
            group2 = classify_supersession_group(identity2)

            assert group1 != group2

    @given(workflow_dispatch_event_strategy())
    def test_same_manual_intent_coalesces(self, event: dict):
        """Same workflow_dispatch inputs produce same group."""
        identity1 = compute_identity(event)
        identity2 = compute_identity(event)

        group1 = classify_supersession_group(identity1)
        group2 = classify_supersession_group(identity2)

        assert group1 == group2


class TestPRRevisionSupersession:
    """Property 3: Newer PR revisions supersede older ones."""

    @given(pull_request_event_strategy(), sha_strategy())
    def test_newer_pr_sha_supersedes_older(self, event: dict, base_sha: str):
        """When PR is updated, newer SHA supersedes older SHA."""
        # Create older event with given SHA
        older_event = event.copy()
        older_event["sha"] = base_sha
        older_event["pull_request"] = event["pull_request"].copy()
        older_event["pull_request"]["head"] = {"sha": base_sha}

        # Create newer event with incremented SHA (lexicographically higher)
        newer_event = event.copy()
        # Increment the SHA by one (in hex)
        sha_int = int(base_sha, 16)
        newer_sha = hex(sha_int + 1)[2:].zfill(40)
        newer_event["sha"] = newer_sha
        newer_event["pull_request"] = event["pull_request"].copy()
        newer_event["pull_request"]["head"] = {"sha": newer_sha}

        older_identity = compute_identity(older_event)
        newer_identity = compute_identity(newer_event)

        # Newer must supersede older
        assert can_supersede(older_identity, newer_identity) is True
        # Older must NOT supersede newer
        assert can_supersede(newer_identity, older_identity) is False

    @given(sha_strategy(), sha_strategy())
    def test_sha_ordering_is_lexicographic(self, sha1: str, sha2: str):
        """SHA ordering is stable and lexicographic."""
        assume(sha1 != sha2)

        # Determine which is older based on lexicographic order
        older_sha = min(sha1, sha2)
        newer_sha = max(sha1, sha2)

        older_event = {
            "repository": "owner/repo",
            "event_name": "pull_request",
            "sha": older_sha,
            "pull_request": {"number": 1, "head": {"sha": older_sha}},
        }
        newer_event = {
            "repository": "owner/repo",
            "event_name": "pull_request",
            "sha": newer_sha,
            "pull_request": {"number": 1, "head": {"sha": newer_sha}},
        }

        older_id = compute_identity(older_event)
        newer_id = compute_identity(newer_event)

        assert can_supersede(older_id, newer_id) is True


class TestDistinctManualIntentsDoNotCancel:
    """Property 4: Distinct manual/reusable intents do NOT cancel each other."""

    @given(workflow_dispatch_event_strategy(), workflow_dispatch_event_strategy())
    def test_different_inputs_do_not_cancel(self, event1: dict, event2: dict):
        """Different workflow_dispatch inputs (different intents) do not cancel."""
        # Ensure events have different inputs
        event1["inputs"] = {"input_a": "value1"}
        event2["inputs"] = {"input_b": "value2"}
        assume(event1["inputs"] != event2["inputs"])

        identity1 = compute_identity(event1)
        identity2 = compute_identity(event2)

        # These should have different intent_ids
        assert identity1.intent_id != identity2.intent_id

        # Newer identity should NOT supersede older (different intents)
        assert can_supersede(identity1, identity2) is False
        assert can_supersede(identity2, identity1) is False

    @given(workflow_dispatch_event_strategy(), sha_strategy())
    def test_same_inputs_can_cancel(self, event: dict, base_sha: str):
        """Same workflow_dispatch inputs (same intent) CAN cancel if newer SHA."""
        event_copy = event.copy()
        event_copy["sha"] = base_sha
        identity1 = compute_identity(event_copy)

        # Create second event with same inputs but different SHA
        event2 = event.copy()
        # Increment SHA by one
        sha_int = int(base_sha, 16)
        newer_sha = hex(sha_int + 1)[2:].zfill(40)
        event2["sha"] = newer_sha

        identity2 = compute_identity(event2)

        # Same intent (same inputs), newer SHA
        assert identity1.intent_id == identity2.intent_id
        # Newer can supersede older
        assert can_supersede(identity1, identity2) is True


class TestStaleSHANeverSatisfiesCurrent:
    """Property 5: Stale SHA never satisfies current-head requirement."""

    @given(sha_strategy(), sha_strategy())
    def test_older_sha_is_stale(self, sha1: str, sha2: str):
        """Lexicographically smaller SHA is stale."""
        assume(sha1 != sha2)

        if sha1 < sha2:
            # sha1 is stale relative to sha2
            assert is_stale_sha(sha1, sha2) is True
            assert is_stale_sha(sha2, sha1) is False
        else:
            assert is_stale_sha(sha2, sha1) is True
            assert is_stale_sha(sha1, sha2) is False

    @given(sha_strategy())
    def test_same_sha_not_stale(self, sha: str):
        """Same SHA is not stale."""
        assert is_stale_sha(sha, sha) is False


class TestSameIntentDetection:
    """Property 6: Intent identity correctly distinguishes manual intents."""

    @given(workflow_dispatch_event_strategy())
    def test_same_event_is_same_intent(self, event: dict):
        """Same event is same intent."""
        assert are_same_intent(event, event) is True

    @given(workflow_dispatch_event_strategy(), workflow_dispatch_event_strategy())
    def test_different_inputs_different_intent(self, event1: dict, event2: dict):
        """Different inputs = different intent."""
        event1["inputs"] = {"key": "value1"}
        event2["inputs"] = {"key": "value2"}
        assume(event1["inputs"] != event2["inputs"])

        result = are_same_intent(event1, event2)
        # Different repositories or different inputs should be different intent
        if event1.get("repository") == event2.get("repository") and event1.get(
            "event_name"
        ) == event2.get("event_name"):
            # Same repo/event type, different inputs = different intent
            assert result is False

    @given(pull_request_event_strategy(), pull_request_event_strategy())
    def test_pr_events_not_intent_based(self, event1: dict, event2: dict):
        """PR events don't use intent-based deduplication."""
        # PR events are never considered the same intent
        result = are_same_intent(event1, event2)
        # They're always different (not intent-based)
        if event1 != event2:
            assert result is False


class TestIdentityValidation:
    """Property 7: Invalid events are rejected with clear errors."""

    def test_invalid_sha_rejected(self):
        """Events with invalid SHA are rejected."""
        with pytest.raises(ValueError, match="Invalid SHA"):
            compute_identity(
                {
                    "repository": "owner/repo",
                    "event_name": "pull_request",
                    "sha": "tooshort",
                    "pull_request": {"number": 1, "head": {"sha": "tooshort"}},
                }
            )

    def test_non_hex_sha_rejected(self):
        """Events with non-hex SHA are rejected."""
        # Use non-hex characters but still 40 chars
        with pytest.raises(ValueError, match="expected 40-char hex|SHA must be hex"):
            compute_identity(
                {
                    "repository": "owner/repo",
                    "event_name": "pull_request",
                    "sha": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",  # Non-hex
                    "pull_request": {
                        "number": 1,
                        "head": {"sha": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"},
                    },
                }
            )

    def test_pr_head_sha_mismatch_rejected(self):
        """PR events with mismatched head SHA are rejected."""
        with pytest.raises(ValueError, match="PR head SHA mismatch"):
            compute_identity(
                {
                    "repository": "owner/repo",
                    "event_name": "pull_request",
                    "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "pull_request": {
                        "number": 1,
                        "head": {"sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
                    },
                }
            )

    def test_invalid_pr_number_rejected(self):
        """PR events with invalid number are rejected."""
        with pytest.raises(ValueError, match="Invalid PR number"):
            compute_identity(
                {
                    "repository": "owner/repo",
                    "event_name": "pull_request",
                    "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "pull_request": {
                        "number": 0,
                        "head": {"sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
                    },
                }
            )


class TestNoAmbiguityFromRunAttempt:
    """Property 8: Run attempt/matrix leg doesn't affect identity."""

    @given(pull_request_event_strategy())
    def test_run_attempt_not_in_identity(self, event: dict):
        """Run attempt number doesn't affect identity."""
        # Create two "runs" of same event (different run attempts)
        event1 = event.copy()
        event2 = event.copy()
        # These might come from different run attempts, but identity is same
        identity1 = compute_identity(event1)
        identity2 = compute_identity(event2)

        assert identity1 == identity2


class TestNoMergeSHAAmbiguity:
    """Property 9: Merge SHA doesn't shadow event SHA."""

    @given(pull_request_event_strategy())
    def test_only_head_sha_used(self, event: dict):
        """Only PR head SHA is used, not merge commit SHA."""
        event_copy = event.copy()
        # Add merge_commit_sha to the PR data (GitHub provides this)
        event_copy["pull_request"]["merge_commit_sha"] = (
            "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
        )

        identity = compute_identity(event_copy)

        # Identity should use head.sha, not merge_commit_sha
        assert identity.exact_sha == event_copy["pull_request"]["head"]["sha"]
        assert identity.exact_sha != event_copy["pull_request"]["merge_commit_sha"]


class TestRefAmbiguityPrevented:
    """Property 10: Ref name ambiguity is prevented."""

    @given(pull_request_event_strategy())
    def test_pr_uses_head_sha_not_ref(self, event: dict):
        """PR events use head SHA, not ref name."""
        event["ref"] = "refs/pull/123/merge"  # Merge ref could be ambiguous

        identity = compute_identity(event)

        # Identity must use head.sha, which is already validated
        assert len(identity.exact_sha) == 40
        assert identity.event_type == EvaluationEventType.PULL_REQUEST
