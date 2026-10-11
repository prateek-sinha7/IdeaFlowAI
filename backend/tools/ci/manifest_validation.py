"""
Validate the evaluator's aggregate manifest before `ci-required` is published.

The trusted PR finalizer (ci-authoritative.yml, via
.github/scripts/ci-validate-evidence.sh) runs this file with the runner's system
`python3` from the default-branch checkout:

    python3 backend/tools/ci/manifest_validation.py <manifest.json> <expected-sha>

so it is stdlib-only and imports nothing from `tools.ci`. It used to be a
heredoc inside the shell script; it moved here so every rule is unit-tested
(tests/unit/tools/ci/test_manifest_validation.py).

The point is that nothing downstream can upgrade a red evaluation. A manifest is
accepted only when it is schema-valid, names the attested SHA, carries a strict
`success`, records no advisory downgrade, holds only `success` verdicts, and —
F-15 — accounts for every required signal exactly once, either as a verdict in
`signal_states` or as a path-filtered signal in `policy_filtered`. Filtering is
only acceptable on `pull_request`, and never for the signals that evaluate the
whole repository (NEVER_FILTERABLE).

Rollout note: this file is effective for pull requests only once it is on the
default branch. The manifest format is backward compatible, because filtered
signals are absent from `signal_states`, which the previous finalizer reads.
"""

from __future__ import annotations

import json
import sys
from typing import Any

#: Signals that can never be path-filtered: their registry `path_filter_area`
#: is None. Mirrors tools/ci/signal_registry.py (asserted by
#: test_manifest_validation.py); duplicated because this file must not import
#: the registry.
NEVER_FILTERABLE = frozenset(
    {
        "repo-static/actionlint",
        "repo-static/bash-syntax",
        "repo-static/shellcheck",
        "repo-static/compose-config",
        "security[secrets]",
    }
)

_REQUIRED_FIELDS = ("schema_version", "producer", "evaluation_sha", "outcome")


def _check_header(manifest: dict[str, Any], expected_sha: str) -> list[str]:
    """Required fields, schema, producer, SHA and outcomes."""
    problems: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in manifest:
            problems.append(f"missing required field '{field}'")

    if manifest.get("schema_version") != 1:
        problems.append(
            f"unsupported schema_version {manifest.get('schema_version')!r}"
        )

    if manifest.get("producer") != "ci-evidence":
        problems.append(f"unexpected producer {manifest.get('producer')!r}")

    if manifest.get("evaluation_sha") != expected_sha:
        problems.append(
            f"manifest is for {manifest.get('evaluation_sha')!r}, "
            f"expected {expected_sha!r} (stale evidence)"
        )

    # This is the check whose absence once let the publisher's own steps decide
    # the verdict instead of the evaluation.
    if manifest.get("outcome") != "success":
        problems.append(
            f"evaluator aggregate outcome is {manifest.get('outcome')!r}; "
            "a failed evaluation cannot be finalized as green"
        )

    # F-03: a pull request is finalized on the STRICT verdict only. Two
    # independent refusals, because either one alone could be defeated by a
    # future edit: strict_outcome must be success AND nothing was downgraded.
    if manifest.get("strict_outcome") != "success":
        problems.append(
            f"evaluator strict outcome is {manifest.get('strict_outcome')!r}. A "
            "pull request is finalized on the strict verdict only; advisory "
            "downgrades are not acceptable here."
        )

    downgraded = manifest.get("advisory_downgraded") or {}
    for name, state in sorted(downgraded.items()):
        problems.append(
            f"signal {name} was downgraded to advisory ({state}); a pull request "
            "cannot be finalized with a downgraded signal"
        )
    return problems


def _check_signals(manifest: dict[str, Any]) -> list[str]:
    """Verdicts, the F-15 policy-filtered list, and completeness."""
    problems: list[str] = []
    states: dict[str, Any] = manifest.get("signal_states") or {}
    for name in sorted(states):
        if states[name] != "success":
            problems.append(f"signal {name} is {states[name]}")

    filtered = set(manifest.get("policy_filtered") or [])
    event = manifest.get("event")
    if filtered and event != "pull_request":
        problems.append(
            f"manifest records {len(filtered)} policy-filtered signal(s) for "
            f"event {event!r}; path filtering is only valid on pull_request"
        )
    for name in sorted(filtered & NEVER_FILTERABLE):
        problems.append(f"signal {name} can never be policy-filtered")
    for name in sorted(filtered & set(states)):
        problems.append(f"signal {name} is in both signal_states and policy_filtered")

    required = manifest.get("required_signals")
    if not isinstance(required, list) or not required:
        problems.append("manifest lists no required_signals")
        return problems
    accounted = set(states) | filtered
    for name in sorted(set(required) - accounted):
        problems.append(
            f"required signal {name} is in neither signal_states nor "
            "policy_filtered (missing verdict)"
        )
    return problems


def validate_manifest(manifest: dict[str, Any], expected_sha: str) -> list[str]:
    """
    Return every reason `manifest` cannot be finalized as green.

    An empty list means the manifest is accepted.
    """
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    return _check_header(manifest, expected_sha) + _check_signals(manifest)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: `manifest_validation.py <manifest> <expected-sha>`."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("::error::usage: manifest_validation.py <manifest.json> <expected-sha>")
        return 2
    manifest_path, expected_sha = args

    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::cannot read manifest {manifest_path}: {exc}")
        return 1

    problems = validate_manifest(manifest, expected_sha)
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 1

    states = manifest.get("signal_states") or {}
    filtered = manifest.get("policy_filtered") or []
    message = (
        f"Evaluator evidence accepted: {len(states)} signal(s) succeeded for "
        f"{expected_sha}."
    )
    if filtered:
        message += f" {len(filtered)} signal(s) were policy-filtered (pull request)."
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
