"""
CI entrypoint for test-debt enforcement.

Three checks, each failing the PR check on any violation:

1. ``counts``  — collected pytest / Vitest / Playwright-mocked counts must equal
   the recorded baselines in ``.planning/test-baselines.yml``. A mismatch is
   reported with suite name, recorded count, and collected count.
2. ``record``  — every entry in ``.planning/REMEDIATION-RECORD.md`` must carry
   the fields its section declares: owner, reason, and an unexpired date.
3. ``skips``   — every ``skip`` / ``fixme`` directive in the backend and frontend
   suites must have a matching Disabled Tests entry in the record.

Usage (from the ``backend`` directory):

    python -m tests.ci.enforce_debt counts
    python -m tests.ci.enforce_debt record
    python -m tests.ci.enforce_debt skips
    python -m tests.ci.enforce_debt all

Exit code 0 on pass, 1 on any violation.

Requirements: 32.3, 32.4, 32.5, 2.7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_parser import RemediationRecordParser  # noqa: E402
from test_count_enforcement import (  # noqa: E402
    SkipEnforcementLinter,
    TestCountValidator,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def check_counts() -> int:
    """Compare collected test counts against the recorded baselines."""
    validator = TestCountValidator(repo_root=REPO_ROOT)
    ok, results = validator.validate_counts()

    for suite, data in results.items():
        print(
            f"{suite}: recorded={data.get('baseline')} "
            f"collected={data.get('collected')} "
            f"{'OK' if data.get('match') else 'MISMATCH'}"
        )

    for err in validator.errors:
        print(f"collection error: {err}", file=sys.stderr)

    if not ok:
        print(validator.format_failure_message(results), file=sys.stderr)
        return 1

    print("Test counts match the recorded baselines.")
    return 0


def check_record() -> int:
    """Enforce completeness of every Remediation Record entry."""
    record_path = REPO_ROOT / ".planning" / "REMEDIATION-RECORD.md"
    parser = RemediationRecordParser(record_path)
    parser.parse()

    complete, errors = parser.validate_completeness()
    if not complete:
        print("Incomplete Remediation Record entries:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print("Remediation Record entries are complete.")
    return 0


def check_skips() -> int:
    """Enforce that every skip or fixme directive has a complete record entry."""
    linter = SkipEnforcementLinter(repo_root=REPO_ROOT)
    linter.lint_backend_tests()
    linter.lint_frontend_tests()

    if linter.has_findings():
        print(linter.format_findings(), file=sys.stderr)
        print(
            f"\n{len(linter.findings)} unrecorded skip/disable directive(s). "
            "Each needs a Disabled Tests entry (owner, reason, expiry) in "
            ".planning/REMEDIATION-RECORD.md.",
            file=sys.stderr,
        )
        return 1

    print("No unrecorded test skips or disables found.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("check", choices=["counts", "record", "skips", "all"])
    args = ap.parse_args(argv)

    if args.check == "counts":
        return check_counts()
    if args.check == "record":
        return check_record()
    if args.check == "skips":
        return check_skips()
    return max(check_counts(), check_record(), check_skips())


if __name__ == "__main__":
    raise SystemExit(main())
