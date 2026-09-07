"""
Blocking CI gate entrypoints.

This module is the ONLY thing standing between the policy code in this package
and the GitHub Actions workflow. Before it existed, `scanner_parsers`,
`scanner_policy`, `aggregate_truth` and the coverage thresholds were fully
implemented and unit-tested but had no production caller: every mandatory step
in the workflow ended in `exit 0`, `|| true` or `continue-on-error: true`, so a
High/Critical finding or a failed job could not fail the build.

Every subcommand here obeys the same contract:

* exit 0  -> the signal is SUCCESS
* exit 1  -> the signal is FAILURE (policy violation, threshold miss, or a
             malformed / missing / unparseable mandatory report)

There is deliberately no "warn" exit code and no way to downgrade a failure.
A missing or corrupt mandatory report is a failure, not a skip: fail-closed is
the whole point (Requirements 2.5, 2.6, 2.8, 2.14).

Usage (all paths are relative to the repository root unless stated otherwise):

    python -m agents.ci.ci_gate scan-gate \
        --scanner pip-audit --report ci-results/pip-audit.json \
        --producer 'security[backend-deps]' --out ci-results/verdict.json

    python -m agents.ci.ci_gate coverage-gate-backend \
        --coverage-xml ci-results/backend-coverage.xml --min 80

    python -m agents.ci.ci_gate coverage-gate-frontend \
        --summary frontend/coverage/coverage-summary.json --min 80

    python -m agents.ci.ci_gate aggregate \
        --sha "$EVALUATION_SHA" --job repo-static=success --job security=failure ...
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .aggregate_truth import (
    SignalResult,
    SignalState,
    aggregate_truth,
    compute_aggregate_required_signals,
    explain_aggregate_failure,
)
from .scanner_parsers import (
    ParserError,
    parse_checkov_json,
    parse_gitleaks_json,
    parse_grype_json,
    parse_npm_audit_json,
    parse_pip_audit_json,
    parse_trivy_json,
)
from .scanner_verdict import ScannerVerdict
from .signal_registry import SIGNAL_REGISTRY

# --------------------------------------------------------------------------
# Scanner gate
# --------------------------------------------------------------------------

#: Maps the `--scanner` value to the parser that understands that report
#: format. Each parser already returns a `ScannerVerdict` carrying normalised
#: severities, so this module never re-implements severity classification.
_SCANNER_PARSERS: dict[str, Callable[[str], ScannerVerdict]] = {
    "pip-audit": parse_pip_audit_json,
    "npm": parse_npm_audit_json,
    "trivy-image": lambda c: parse_trivy_json(c, scanner_type="image"),
    "trivy-config": lambda c: parse_trivy_json(c, scanner_type="config"),
    "grype": parse_grype_json,
    "checkov": parse_checkov_json,
    "gitleaks": parse_gitleaks_json,
}


def _load_report_text(path: Path) -> str:
    """
    Read a scanner report as text.

    Raises:
        FileNotFoundError: the mandatory report is absent.
        ValueError: the report is empty.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"mandatory scanner report not found: {path}. "
            "An absent report is a failed signal, never a pass."
        )

    raw = path.read_bytes()
    # Decode defensively. Reports are produced by whatever shell redirected the
    # scanner's stdout, and some shells (notably PowerShell 5.1's `>`) emit
    # UTF-16 with a BOM. Guessing wrong here would surface as "malformed JSON"
    # and fail a signal for an encoding detail rather than a real finding.
    for bom, encoding in (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
        if raw.startswith(bom):
            text = raw.decode(encoding, errors="replace")
            break
    else:
        text = raw.decode("utf-8", errors="replace")

    if not text.strip():
        raise ValueError(
            f"mandatory scanner report is empty: {path}. "
            "An empty report is not evidence of zero findings."
        )
    return text


def cmd_scan_gate(args: argparse.Namespace) -> int:
    """
    Apply the zero High/Critical policy to one scanner report.

    Fails on a blocking finding regardless of fix availability, and equally
    on a missing, empty or unparseable report.
    """
    parser_fn = _SCANNER_PARSERS[args.scanner]
    report_path = Path(args.report)

    try:
        verdict = parser_fn(_load_report_text(report_path))
    except (FileNotFoundError, ValueError, ParserError) as exc:
        print(f"::error::{args.producer}: {exc}")
        _write_verdict_json(
            args.out,
            producer=args.producer,
            scanner=args.scanner,
            success=False,
            error=str(exc),
            findings=[],
        )
        return 1

    blocking = [f for f in verdict.findings if f.severity.is_blocking()]

    _write_verdict_json(
        args.out,
        producer=args.producer,
        scanner=args.scanner,
        success=verdict.success and not blocking,
        error=verdict.error,
        findings=blocking,
    )

    if verdict.error:
        print(
            f"::error::{args.producer}: {args.scanner} report invalid: {verdict.error}"
        )
        return 1

    if blocking:
        print(
            f"::error::{args.producer}: {args.scanner} found {len(blocking)} "
            f"High/Critical finding(s). Policy threshold is zero, independent of "
            f"fix availability."
        )
        for finding in blocking:
            fixed = finding.fixed_version or "no fix published"
            print(
                f"  [{finding.severity.value.upper()}] {finding.id} "
                f"in {finding.path} ({fixed}): {finding.description[:160]}"
            )
        return 1

    print(
        f"{args.producer}: {args.scanner} OK — 0 High/Critical findings "
        f"({len(verdict.findings)} finding(s) at or below Medium)."
    )
    return 0


def _write_verdict_json(
    out: str | None,
    *,
    producer: str,
    scanner: str,
    success: bool,
    error: str | None,
    findings: list,
) -> None:
    """Persist a machine-readable verdict next to the raw report."""
    if not out:
        return
    payload = {
        "schema_version": 1,
        "producer": producer,
        "scanner": scanner,
        "success": success,
        "error": error,
        "high_critical_count": len(findings),
        # Findings are recorded by identity and location only. Descriptions are
        # truncated and no scanner environment is echoed, so this file is safe
        # to upload as an artifact.
        "findings": [
            {
                "id": f.id,
                "severity": f.severity.value,
                "path": f.path,
                "fixed_version": f.fixed_version,
            }
            for f in findings
        ],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Coverage gates
# --------------------------------------------------------------------------


def cmd_coverage_gate_backend(args: argparse.Namespace) -> int:
    """
    Enforce overall backend line coverage from a merged Cobertura report.

    The report must be the *merged* product of every mandatory producer. A
    per-shard report would understate the numerator and is rejected upstream by
    the evidence job, not here.
    """
    path = Path(args.coverage_xml)
    if not path.exists():
        print(f"::error::backend coverage report missing: {path}")
        return 1

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        print(f"::error::backend coverage report is not parseable XML: {exc}")
        return 1

    # Cobertura records `lines-valid` / `lines-covered` on the root element.
    # Prefer those; fall back to `line-rate` when a generator omits the counts.
    valid = root.get("lines-valid")
    covered = root.get("lines-covered")
    if valid is not None and covered is not None and int(valid) > 0:
        pct = 100.0 * int(covered) / int(valid)
        detail = f"{covered}/{valid} lines"
    else:
        line_rate = root.get("line-rate")
        if line_rate is None:
            print(
                "::error::backend coverage report has neither lines-valid/"
                "lines-covered nor line-rate; cannot enforce a threshold"
            )
            return 1
        pct = 100.0 * float(line_rate)
        detail = f"line-rate={line_rate}"

    if pct + 1e-9 < args.min:
        print(
            f"::error::backend coverage {pct:.2f}% ({detail}) is below the "
            f"required {args.min}%"
        )
        return 1

    print(f"backend coverage {pct:.2f}% ({detail}) meets the {args.min}% threshold.")
    return 0


#: The four metrics Requirement 2.5 enforces independently. All four must pass;
#: a high statement percentage does not excuse low branch coverage.
_FRONTEND_METRICS = ("statements", "branches", "functions", "lines")


def cmd_coverage_gate_frontend(args: argparse.Namespace) -> int:
    """Enforce all four frontend coverage metrics from Vitest's json-summary."""
    path = Path(args.summary)
    if not path.exists():
        print(f"::error::frontend coverage summary missing: {path}")
        return 1

    try:
        total = json.loads(path.read_text(encoding="utf-8"))["total"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"::error::frontend coverage summary is malformed: {exc}")
        return 1

    failures: list[str] = []
    for metric in _FRONTEND_METRICS:
        entry = total.get(metric)
        if not isinstance(entry, dict) or "pct" not in entry:
            failures.append(f"{metric}: absent from summary")
            continue
        pct = float(entry["pct"])
        marker = "OK " if pct + 1e-9 >= args.min else "LOW"
        print(f"  {marker} {metric:<11} {pct:6.2f}%  (need >= {args.min}%)")
        if pct + 1e-9 < args.min:
            failures.append(f"{metric}={pct:.2f}%")

    if failures:
        print(
            "::error::frontend coverage below the required "
            f"{args.min}% on: {', '.join(failures)}"
        )
        return 1

    print(f"frontend coverage meets the {args.min}% threshold on all four metrics.")
    return 0


# --------------------------------------------------------------------------
# Aggregate gate
# --------------------------------------------------------------------------

#: GitHub job results (`needs.<job>.result`) mapped onto the fail-closed signal
#: states. `skipped` is NOT success: a mandatory job that did not run has no
#: verdict, and an absent verdict must block (Requirement 2.14).
_JOB_RESULT_TO_STATE: dict[str, SignalState] = {
    "success": SignalState.SUCCESS,
    "failure": SignalState.FAILURE,
    "cancelled": SignalState.CANCELLED,
    "skipped": SignalState.SKIPPED,
    "": SignalState.MISSING,
}


def _expand_job_results(
    job_results: dict[str, str], sha: str, now: datetime
) -> tuple[dict[str, SignalResult], list[str]]:
    """
    Expand job-level GitHub results into per-signal results.

    A job owns one or more signals. `run_checks.py` exits non-zero if any of its
    sub-checks failed, so job success implies every sub-signal it owns
    succeeded, and job failure is attributed to all of them. That direction is
    the safe one: it can never turn a red sub-check green.
    """
    results: dict[str, SignalResult] = {}
    problems: list[str] = []

    for job_name, raw_result in job_results.items():
        owned = SIGNAL_REGISTRY.get_signals_by_owner(job_name)
        if not owned:
            problems.append(f"job '{job_name}' owns no registered signal")
            continue

        state = _JOB_RESULT_TO_STATE.get(raw_result.strip().lower())
        if state is None:
            problems.append(
                f"job '{job_name}' reported unrecognised result '{raw_result}'"
            )
            state = SignalState.MISSING

        for signal in owned:
            results[signal.id] = SignalResult(
                signal_name=signal.id,
                state=state,
                sha=sha,
                timestamp=now,
            )

    return results, problems


def cmd_aggregate(args: argparse.Namespace) -> int:
    """
    Compute the authoritative aggregate verdict for the exact evaluated SHA.

    This replaces the previous `exit 0` placeholder. It succeeds only when every
    mandatory signal in the registry reported success for this SHA.
    """
    sha = args.sha.strip().lower()
    now = datetime.now(timezone.utc)

    job_results: dict[str, str] = {}
    for pair in args.job:
        name, _, result = pair.partition("=")
        if not name or not _:
            print(f"::error::--job expects NAME=RESULT, got '{pair}'")
            return 1
        job_results[name.strip()] = result

    try:
        results, problems = _expand_job_results(job_results, sha, now)
    except ValueError as exc:
        print(f"::error::invalid evaluation SHA: {exc}")
        return 1

    required = compute_aggregate_required_signals()

    # Signals owned by a deferred job are evaluated by a different, trusted
    # workflow (the pull-request finalizer owns Sonar, because the unprivileged
    # evaluator holds no SONAR_TOKEN). Deferral is explicit and logged: it moves
    # a signal to another owner, it does not excuse it. If the deferring owner
    # never publishes, the required status is never published either, so the
    # branch stays blocked.
    deferred_signals: set[str] = set()
    for job_name in args.defer:
        owned = SIGNAL_REGISTRY.get_signals_by_owner(job_name)
        if not owned:
            print(f"::error::--defer names '{job_name}', which owns no signal")
            return 1
        deferred_signals.update(s.id for s in owned)

    required = required - deferred_signals
    missing = sorted(required - set(results))

    print(f"Aggregate evaluation for SHA {sha}")
    print(f"  mandatory signals: {len(required)}")
    print(f"  reported signals:  {len(results)}")
    for name in sorted(deferred_signals):
        print(f"  deferred to a trusted owner: {name}")

    for problem in problems:
        print(f"::error::{problem}")

    if missing:
        for name in missing:
            print(f"::error::mandatory signal has no verdict: {name}")

    # Fail-closed evaluation over the (possibly deferral-reduced) required set.
    # Same three rules as `aggregate_truth`: the signal must be present, carry
    # this exact SHA, and be SUCCESS.
    ok = True
    for name in sorted(required):
        result = results.get(name)
        if result is None:
            ok = False
        elif result.sha != sha or result.state != SignalState.SUCCESS:
            ok = False

    if not deferred_signals:
        # No deferral: this is the authoritative full-set evaluation, so also
        # run it through the unit-tested truth function and refuse to disagree
        # with it in the optimistic direction.
        try:
            authoritative = aggregate_truth(results, sha)
        except ValueError as exc:
            print(f"::error::aggregate inputs rejected: {exc}")
            return 1
        if authoritative != ok:
            print(
                "::error::internal inconsistency between the local check and "
                "aggregate_truth(); failing closed"
            )
            ok = False

    if not ok or missing or problems:
        print("::error::ci-required = FAILURE")
        if deferred_signals:
            # `explain_aggregate_failure` reasons over the full registry, so it
            # would report the deliberately deferred Sonar signals as "missing"
            # and bury the real cause. Report only the signals this evaluator
            # actually owns.
            for name in sorted(required):
                result = results.get(name)
                if result is None:
                    print(f"  {name}: no verdict")
                elif result.sha != sha:
                    print(f"  {name}: stale SHA {result.sha[:8]} (expected {sha[:8]})")
                elif result.state != SignalState.SUCCESS:
                    print(f"  {name}: {result.state.value}")
        else:
            # `explain_aggregate_failure` returns a single human-readable
            # string; split it so multi-reason explanations stay readable.
            for line in explain_aggregate_failure(results, sha).splitlines():
                if line.strip():
                    print(f"  {line}")
        _write_aggregate_json(args.out, sha, results, sorted(required), False)
        return 1

    print("ci-required = SUCCESS (every mandatory signal succeeded for this SHA)")
    _write_aggregate_json(args.out, sha, results, sorted(required), True)
    return 0


def _write_aggregate_json(
    out: str | None,
    sha: str,
    results: dict[str, SignalResult],
    required: list[str],
    success: bool,
) -> None:
    """Persist the aggregate verdict for the trusted finalizer to consume."""
    if not out:
        return
    payload = {
        "schema_version": 1,
        "producer": "ci-evidence",
        "evaluation_sha": sha,
        "outcome": "success" if success else "failure",
        "required_signals": required,
        "signal_states": {
            name: result.state.value for name, result in sorted(results.items())
        },
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for all gate subcommands."""
    parser = argparse.ArgumentParser(
        prog="agents.ci.ci_gate",
        description="Blocking CI policy gates (fail-closed).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser(
        "scan-gate", help="Apply the zero High/Critical policy to a scanner report."
    )
    scan.add_argument("--scanner", required=True, choices=sorted(_SCANNER_PARSERS))
    scan.add_argument("--report", required=True)
    scan.add_argument("--producer", required=True)
    scan.add_argument("--out", default=None)
    scan.set_defaults(func=cmd_scan_gate)

    cov_be = sub.add_parser(
        "coverage-gate-backend", help="Enforce merged backend coverage."
    )
    cov_be.add_argument("--coverage-xml", required=True)
    cov_be.add_argument("--min", type=float, default=80.0)
    cov_be.set_defaults(func=cmd_coverage_gate_backend)

    cov_fe = sub.add_parser(
        "coverage-gate-frontend", help="Enforce all four frontend coverage metrics."
    )
    cov_fe.add_argument("--summary", required=True)
    cov_fe.add_argument("--min", type=float, default=80.0)
    cov_fe.set_defaults(func=cmd_coverage_gate_frontend)

    agg = sub.add_parser(
        "aggregate", help="Compute the authoritative aggregate verdict."
    )
    agg.add_argument("--sha", required=True)
    agg.add_argument(
        "--job",
        action="append",
        default=[],
        metavar="NAME=RESULT",
        help="A GitHub job name and its needs.<job>.result value.",
    )
    agg.add_argument(
        "--defer",
        action="append",
        default=[],
        metavar="OWNER_JOB",
        help=(
            "An owner job whose signals are evaluated by a different trusted "
            "workflow (e.g. sonar-pr on the pull-request path)."
        ),
    )
    agg.add_argument("--out", default=None)
    agg.set_defaults(func=cmd_aggregate)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
