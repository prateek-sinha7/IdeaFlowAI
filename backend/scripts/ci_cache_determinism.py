#!/usr/bin/env python3
"""
Cache Determinism Comparison Script

Compares two CI evaluation results (from same SHA with different cache states)
and validates that verdicts, coverage, and findings are identical after
normalizing for run-specific fields (run ID, attempt, timestamps).

Usage:
    python scripts/ci_cache_determinism.py \
        --empty-cache-result empty_cache_result.json \
        --warm-cache-result warm_cache_result.json \
        --output comparison_report.json

Exit codes:
    0 - Results are deterministic (cache-equivalent)
    1 - Results differ (non-deterministic/cache-dependent)
    2 - Error processing files
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime


def normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a result for comparison by removing run-specific fields.

    Fields removed:
    - run_id
    - run_attempt
    - timestamp
    - Individual producer timestamps

    These fields are expected to differ between cache states.
    """
    normalized = result.copy()

    # Remove run-specific top-level fields
    normalized.pop("run_id", None)
    normalized.pop("run_attempt", None)
    normalized.pop("timestamp", None)

    # Normalize producer evidences
    if "producer_evidences" in normalized:
        normalized_producers = []
        for producer in normalized["producer_evidences"]:
            prod_copy = producer.copy()
            prod_copy.pop("run_id", None)
            prod_copy.pop("run_attempt", None)
            prod_copy.pop("timestamp", None)
            normalized_producers.append(prod_copy)
        normalized["producer_evidences"] = normalized_producers

    return normalized


def compare_field(name: str, value1: Any, value2: Any) -> Tuple[bool, str]:
    """
    Compare two field values.

    Returns (is_equal, description)
    """
    if value1 == value2:
        return True, ""

    if isinstance(value1, (int, float, str, bool, type(None))):
        return False, f"  {name}: {value1} vs {value2}"

    if isinstance(value1, dict) and isinstance(value2, dict):
        if set(value1.keys()) != set(value2.keys()):
            return (
                False,
                f"  {name} keys differ: {set(value1.keys())} vs {set(value2.keys())}",
            )

        for key in value1.keys():
            equal, desc = compare_field(f"{name}[{key}]", value1[key], value2[key])
            if not equal:
                return False, desc

        return True, ""

    if isinstance(value1, list) and isinstance(value2, list):
        if len(value1) != len(value2):
            return (
                False,
                f"  {name} length: {len(value1)} vs {len(value2)}",
            )

        for i, (item1, item2) in enumerate(zip(value1, value2, strict=False)):
            equal, desc = compare_field(f"{name}[{i}]", item1, item2)
            if not equal:
                return False, desc

        return True, ""

    return False, f"  {name}: {type(value1).__name__} vs {type(value2).__name__}"


def compare_results(
    empty_result: Dict[str, Any],
    warm_result: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Compare two normalized evaluation results.

    Returns (are_equivalent, differences)
    """
    norm_empty = normalize_result(empty_result)
    norm_warm = normalize_result(warm_result)

    differences = []

    # Compare all fields
    all_keys = set(norm_empty.keys()) | set(norm_warm.keys())

    for key in sorted(all_keys):
        if key not in norm_empty:
            differences.append(f"Missing in empty-cache result: {key}")
            continue

        if key not in norm_warm:
            differences.append(f"Missing in warm-cache result: {key}")
            continue

        equal, desc = compare_field(key, norm_empty[key], norm_warm[key])
        if not equal:
            differences.append(desc)

    return len(differences) == 0, differences


def validate_required_fields(result: Dict[str, Any], label: str) -> List[str]:
    """
    Validate that all required fields are present.

    Returns list of validation errors.
    """
    errors = []

    required_fields = [
        "evaluation_sha",
        "ci_evidence_outcome",
        "ci_required_shadow_outcome",
        "signal_verdicts",
        "backend_coverage_overall",
        "frontend_coverage_statements",
        "frontend_coverage_branches",
        "frontend_coverage_functions",
        "frontend_coverage_lines",
        "high_critical_software_findings",
        "sonar_analysis_outcome",
        "sonar_quality_gate_outcome",
        "producer_evidences",
    ]

    for field in required_fields:
        if field not in result:
            errors.append(f"{label}: Missing required field: {field}")

    # Check coverage metrics are numeric
    for metric in [
        "backend_coverage_overall",
        "frontend_coverage_statements",
        "frontend_coverage_branches",
        "frontend_coverage_functions",
        "frontend_coverage_lines",
    ]:
        if metric in result and not isinstance(result[metric], (int, float)):
            errors.append(
                f"{label}: {metric} must be numeric, got {type(result[metric])}"
            )

    # Check verdicts are strings
    if "signal_verdicts" in result and not isinstance(result["signal_verdicts"], dict):
        errors.append(
            f"{label}: signal_verdicts must be dict, got {type(result['signal_verdicts'])}"
        )

    return errors


def format_report(
    empty_sha: str,
    warm_sha: str,
    equivalent: bool,
    differences: List[str],
    validation_empty: List[str],
    validation_warm: List[str],
) -> str:
    """Format a human-readable comparison report."""
    report = []

    report.append("=" * 80)
    report.append("CI Cache Determinism Comparison Report")
    report.append("=" * 80)
    report.append("")

    report.append("Evaluated SHA:")
    report.append(f"  Empty cache: {empty_sha}")
    report.append(f"  Warm cache:  {warm_sha}")
    report.append("")

    if empty_sha != warm_sha:
        report.append("ERROR: Different SHAs evaluated")
        report.append(f"  Empty: {empty_sha}")
        report.append(f"  Warm:  {warm_sha}")
        report.append("")

    # Validation results
    if validation_empty:
        report.append("VALIDATION ERRORS (Empty Cache):")
        for error in validation_empty:
            report.append(f"  - {error}")
        report.append("")

    if validation_warm:
        report.append("VALIDATION ERRORS (Warm Cache):")
        for error in validation_warm:
            report.append(f"  - {error}")
        report.append("")

    # Comparison result
    report.append("Determinism Result:")
    if equivalent:
        report.append("  ✓ DETERMINISTIC - Results are cache-equivalent")
    else:
        report.append("  ✗ NON-DETERMINISTIC - Cache affects results")
    report.append("")

    if differences:
        report.append("Differences Found:")
        for diff in differences:
            report.append(diff)
        report.append("")
    else:
        report.append("No differences found between cache states.")
        report.append("")

    report.append("=" * 80)

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Compare CI evaluation results for cache determinism"
    )
    parser.add_argument(
        "--empty-cache-result",
        type=Path,
        required=True,
        help="Path to evaluation result from empty cache",
    )
    parser.add_argument(
        "--warm-cache-result",
        type=Path,
        required=True,
        help="Path to evaluation result from warm cache",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cache_determinism_report.txt"),
        help="Path to write comparison report",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional: Path to write detailed JSON comparison",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any non-fatal differences found",
    )

    args = parser.parse_args()

    # Load results
    try:
        empty_result = json.loads(args.empty_cache_result.read_text())
    except Exception as e:
        print(f"ERROR: Failed to load empty cache result: {e}", file=sys.stderr)
        return 2

    try:
        warm_result = json.loads(args.warm_cache_result.read_text())
    except Exception as e:
        print(f"ERROR: Failed to load warm cache result: {e}", file=sys.stderr)
        return 2

    # Validate results
    validation_empty = validate_required_fields(empty_result, "Empty Cache")
    validation_warm = validate_required_fields(warm_result, "Warm Cache")

    # Compare
    equivalent, differences = compare_results(empty_result, warm_result)

    empty_sha = empty_result.get("evaluation_sha", "unknown")
    warm_sha = warm_result.get("evaluation_sha", "unknown")

    # Generate report
    report = format_report(
        empty_sha,
        warm_sha,
        equivalent and not validation_empty and not validation_warm,
        differences,
        validation_empty,
        validation_warm,
    )

    # Write report
    args.output.write_text(report)
    print(report)

    # Write JSON if requested
    if args.json:
        json_report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "empty_cache_sha": empty_sha,
            "warm_cache_sha": warm_sha,
            "equivalent": equivalent and not validation_empty and not validation_warm,
            "validation_errors_empty": validation_empty,
            "validation_errors_warm": validation_warm,
            "differences": differences,
            "normalized_empty": normalize_result(empty_result),
            "normalized_warm": normalize_result(warm_result),
        }
        args.json.write_text(json.dumps(json_report, indent=2))

    # Exit with appropriate code
    if not equivalent or validation_empty or validation_warm:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
