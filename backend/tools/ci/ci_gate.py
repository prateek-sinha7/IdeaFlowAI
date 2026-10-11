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

TEMPORARY EXCEPTION: ``scan-gate --mode warn`` still computes and records the
real verdict (success:false in the verdict JSON) but reports problems as
::warning:: annotations plus a step summary and exits 0. Default is ``block``.
TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of
2026-10-11. In future this must be changed back to BLOCKING, and the outstanding
High/Critical vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py
and scan reports).

Usage (all paths are relative to the repository root unless stated otherwise):

    python -m tools.ci.ci_gate scan-gate \
        --scanner trivy-image --report ci-results/trivy-backend-report-gated.json \
        --producer 'container-scan[backend]/trivy' --out ci-results/verdict.json

    python -m tools.ci.ci_gate coverage-gate-backend \
        --coverage-xml ci-results/backend-coverage.xml --min 80

    python -m tools.ci.ci_gate coverage-gate-frontend \
        --summary frontend/coverage/coverage-summary.json --min 80

    python -m tools.ci.ci_gate aggregate \
        --sha "$EVALUATION_SHA" --job repo-static=success --job security=failure ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import parse as safe_parse

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
from .signal_registry import PATH_FILTER_AREAS, SIGNAL_REGISTRY

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
    # `trivy fs <lockfile>` emits the same Results[].Vulnerabilities[] schema as
    # an image scan; the separate name keeps verdict files and logs honest about
    # what was scanned (used for frontend/package-lock.json).
    "trivy-fs": lambda c: parse_trivy_json(c, scanner_type="filesystem"),
    "trivy-config": lambda c: parse_trivy_json(c, scanner_type="config"),
    "grype": parse_grype_json,
    "checkov": parse_checkov_json,
    "gitleaks": parse_gitleaks_json,
}


# TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
# In future this must be changed back to BLOCKING, and the outstanding High/Critical
# vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
SCAN_GATE_MODES: tuple[str, ...] = ("block", "warn")

_WARN_TITLE = "Vulnerability scan (advisory, TEMPORARY)"


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


# TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
# In future this must be changed back to BLOCKING, and the outstanding High/Critical
# vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
def _emit_scan_problem(args: argparse.Namespace, message: str) -> int:
    """Report a scan problem as an error (block, exit 1) or warning (warn, exit 0)."""
    if args.mode == "warn":
        print(
            f"::warning title={_WARN_TITLE}::{args.producer}: {message} "
            "Not blocking: scan-gate --mode warn (TEMPORARY)."
        )
        return 0
    print(f"::error::{args.producer}: {message}")
    return 1


def _md_cell(value: str) -> str:
    """Escape a value for a Markdown table cell."""
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _append_scan_step_summary(
    producer: str, scanner: str, headline: str, findings: list
) -> None:
    """Append an advisory section to $GITHUB_STEP_SUMMARY (no-op when unset)."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        f"### \u26a0\ufe0f {producer} ({scanner}): advisory, TEMPORARY",
        "",
        headline,
        "",
        "TODO(security): scans are warn-only; this must be reverted to blocking and "
        "the findings fixed (see backend/tools/ci/scan_accepts.py).",
        "",
    ]
    if findings:
        lines += ["| Severity | ID | Package / path | Fixed in |", "|---|---|---|---|"]
        for f in findings:
            lines.append(
                f"| {_md_cell(f.severity.value.upper())} | {_md_cell(f.id)} | "
                f"{_md_cell(f.path)} | "
                f"{_md_cell(f.fixed_version or 'no fix published')} |"
            )
        lines.append("")
    try:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"::warning::could not write step summary: {exc}")


def cmd_scan_gate(args: argparse.Namespace) -> int:
    """
    Apply the zero High/Critical policy to one scanner report.

    Fails on a blocking finding regardless of fix availability, and equally
    on a missing, empty or unparseable report. With ``--mode warn`` (TEMPORARY)
    the same problems are reported as warnings and the exit code is 0.
    """
    parser_fn = _SCANNER_PARSERS[args.scanner]
    report_path = Path(args.report)
    mode = args.mode

    try:
        verdict = parser_fn(_load_report_text(report_path))
    except (FileNotFoundError, ValueError, ParserError) as exc:
        _write_verdict_json(
            args.out,
            producer=args.producer,
            scanner=args.scanner,
            success=False,
            error=str(exc),
            findings=[],
            mode=mode,
        )
        if mode == "warn":
            _append_scan_step_summary(
                args.producer,
                args.scanner,
                "Report could not be evaluated - no vulnerability verdict for "
                f"this run: {exc}",
                [],
            )
        return _emit_scan_problem(args, str(exc))

    blocking = [f for f in verdict.findings if f.severity.is_blocking()]

    _write_verdict_json(
        args.out,
        producer=args.producer,
        scanner=args.scanner,
        success=verdict.success and not blocking,
        error=verdict.error,
        findings=blocking,
        mode=mode,
    )

    if verdict.error:
        message = f"{args.scanner} report invalid: {verdict.error}"
        if mode == "warn":
            _append_scan_step_summary(
                args.producer,
                args.scanner,
                f"Report could not be evaluated - no vulnerability verdict for this run: {message}",
                [],
            )
        return _emit_scan_problem(args, message)

    if blocking:
        code = _emit_scan_problem(
            args,
            f"{args.scanner} found {len(blocking)} High/Critical finding(s). "
            "Policy threshold is zero, independent of fix availability.",
        )
        for finding in blocking:
            fixed = finding.fixed_version or "no fix published"
            print(
                f"  [{finding.severity.value.upper()}] {finding.id} "
                f"in {finding.path} ({fixed}): {finding.description[:160]}"
            )
        if mode == "warn":
            _append_scan_step_summary(
                args.producer,
                args.scanner,
                f"{len(blocking)} High/Critical finding(s) (not blocking).",
                blocking,
            )
        return code

    suffix = " [mode=warn: findings would not block]" if mode == "warn" else ""
    print(
        f"{args.producer}: {args.scanner} OK — 0 High/Critical findings "
        f"({len(verdict.findings)} finding(s) at or below Medium).{suffix}"
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
    mode: str = "block",
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
        "mode": mode,
        "enforced": mode == "block",
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
        # defusedxml, not xml.etree, for the same reason the gate exists at
        # all: fail closed. It rejects entity-expansion and external-entity
        # constructs instead of resolving them (bandit B314).
        root = safe_parse(path).getroot()
    except (ET.ParseError, DefusedXmlException) as exc:
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

#: The ONLY state an advisory downgrade may excuse (F-03).
#:
#: `FAILURE` is a measurement: the check ran to completion and reported a red
#: verdict, which is exactly the situation the four allowlisted signals are in.
#: Every other non-success state is an ABSENCE of measurement — `SKIPPED` and
#: `MISSING` mean the check never produced a verdict, `CANCELLED` and `TIMED_OUT`
#: mean it was interrupted partway. Downgrading those would let a deleted or
#: silently-skipped job satisfy the gate, which is the failure mode this whole
#: pipeline is built to prevent ("a missing, empty or unparseable mandatory
#: report is a failure, not a skip"). So an advisory signal must still RUN and
#: still REPORT; it is only permitted to report red.
_ADVISORY_EXCUSABLE_STATES: frozenset[SignalState] = frozenset({SignalState.FAILURE})


#: Job results that mean the job actually executed and reported a verdict.
_RAN_STATES: frozenset[SignalState] = frozenset(
    {SignalState.SUCCESS, SignalState.FAILURE, SignalState.CANCELLED}
)


def _signal_state_for(
    job_state: SignalState, is_filtered: bool, job_partially_filtered: bool
) -> SignalState:
    """
    Decide one signal's state from its job's result and the path filter (F-15).

    * job skipped            -> filtered signals FILTERED, the rest SKIPPED;
    * job ran, every signal filtered -> the real job result for all of them
      (the filter did not stop it, so its verdict stands);
    * job ran, partially filtered (a dynamic matrix excluded some legs) ->
      filtered signals FILTERED, the rest the real job result. A failed live
      leg therefore still fails the job's live signals.
    """
    if not is_filtered:
        return job_state
    if job_state == SignalState.SKIPPED:
        return SignalState.FILTERED
    if job_state in _RAN_STATES and job_partially_filtered:
        return SignalState.FILTERED
    return job_state


def _expand_job_results(
    job_results: dict[str, str],
    sha: str,
    now: datetime,
    filtered_areas: frozenset[str] = frozenset(),
) -> tuple[dict[str, SignalResult], list[str]]:
    """
    Expand job-level GitHub results into per-signal results.

    A job owns one or more signals. `run_checks.py` exits non-zero if any of its
    sub-checks failed, so job success implies every sub-signal it owns
    succeeded, and job failure is attributed to all of them. That direction is
    the safe one: it can never turn a red sub-check green.

    `filtered_areas` (pull requests only, validated by the caller) lets a
    signal whose `path_filter_area` is in it become FILTERED, following
    `_signal_state_for`. A signal with no area is never filtered.
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

        filtered_ids = {
            signal.id
            for signal in owned
            if signal.path_filter_area is not None
            and signal.path_filter_area in filtered_areas
        }
        partially_filtered = 0 < len(filtered_ids) < len(owned)

        for signal in owned:
            results[signal.id] = SignalResult(
                signal_name=signal.id,
                state=_signal_state_for(
                    state, signal.id in filtered_ids, partially_filtered
                ),
                sha=sha,
                timestamp=now,
            )

    return results, problems


def _validate_filtered_areas(
    event: str, raw_areas: list[str]
) -> tuple[frozenset[str], list[str]]:
    """
    Validate `--filtered-area` values against the F-15 policy.

    Returns (areas, problems). On any problem the returned set is EMPTY, so an
    invalid request filters nothing and the caller fails on the problem.
    """
    areas = {value.strip() for value in raw_areas}
    problems: list[str] = []
    if not areas:
        return frozenset(), problems

    if event != "pull_request":
        problems.append(
            f"--filtered-area is only valid for pull_request events, got event "
            f"'{event}'. push, workflow_dispatch and workflow_call always run "
            f"every signal."
        )
    for area in sorted(areas - PATH_FILTER_AREAS):
        problems.append(
            f"--filtered-area names unknown area '{area}'; expected one of "
            f"{sorted(PATH_FILTER_AREAS)}"
        )
    if problems:
        return frozenset(), problems
    return frozenset(areas), problems


def _is_policy_filtered(result: SignalResult, allow_filtered: bool) -> bool:
    """True when a result is an accepted FILTERED signal (F-15)."""
    if not allow_filtered or result.state != SignalState.FILTERED:
        return False
    signal = SIGNAL_REGISTRY.get_signal(result.signal_name)
    return signal is not None and signal.path_filter_area is not None


def _parse_advisory_args(raw: list[str]) -> list[str]:
    """
    Flatten `--advisory` values into a list of signal ids.

    Accepts one id per flag and also comma- or newline-separated groups, because
    the workflow passes a single multi-line input through one variable. Blank
    entries are dropped so a trailing newline in the workflow input is not an
    error.
    """
    ids: list[str] = []
    for value in raw:
        for token in value.replace(",", "\n").splitlines():
            candidate = token.strip()
            if candidate:
                ids.append(candidate)
    return ids


def cmd_aggregate(args: argparse.Namespace) -> int:
    """
    Compute the authoritative aggregate verdict for the exact evaluated SHA.

    This replaces the previous `exit 0` placeholder. It succeeds only when every
    mandatory signal in the registry reported success for this SHA — except for
    signals explicitly downgraded to advisory via `--advisory`, which is itself
    gated by the registry allowlist and each entry's expiry date (F-03).
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

    # F-15 path filter. Validated BEFORE expansion: an invalid request (wrong
    # event, unknown area) filters nothing and fails the aggregate below.
    event = args.event.strip()
    filtered_areas, filter_problems = _validate_filtered_areas(
        event, args.filtered_area
    )
    allow_filtered = bool(filtered_areas)

    try:
        results, problems = _expand_job_results(job_results, sha, now, filtered_areas)
    except ValueError as exc:
        print(f"::error::invalid evaluation SHA: {exc}")
        return 1
    problems = filter_problems + problems
    policy_filtered = sorted(
        name
        for name, result in results.items()
        if _is_policy_filtered(result, allow_filtered)
    )

    # Every mandatory signal is owned by a job in ci.yml on every event type, so
    # the required set is always the full registry set. Nothing is deferred to
    # another workflow and there is no flag to reduce this set: a signal with no
    # reported verdict is missing, and missing is a failure.
    required = compute_aggregate_required_signals()
    missing = sorted(required - set(results))

    # ------------------------------------------------------------------
    # Advisory downgrades (F-03)
    # ------------------------------------------------------------------
    # A downgrade NEVER reduces the required set and NEVER suppresses output. The
    # signal is still required to have reported, still recorded in the manifest
    # with its real state, and still printed. The single thing it changes is
    # whether a non-success state contributes to the aggregate verdict.
    #
    # An invalid request is a hard failure, not a silently ignored one: if the
    # caller believes a signal is downgradable and the registry disagrees, the
    # two must be reconciled by a human before anything ships.
    requested_advisory = _parse_advisory_args(args.advisory)
    advisory: set[str] = set()
    if requested_advisory:
        advisory, advisory_problems = SIGNAL_REGISTRY.resolve_advisory_request(
            requested_advisory
        )
        problems.extend(advisory_problems)

        # A downgrade is only meaningful for a signal that is actually required.
        for signal_id in sorted(advisory - required):
            problems.append(
                f"advisory request names '{signal_id}', which is not part of the "
                f"mandatory aggregate; nothing to downgrade"
            )

    print(f"Aggregate evaluation for SHA {sha}")
    print(f"  event:             {event or '(not given)'}")
    print(f"  mandatory signals: {len(required)}")
    print(f"  reported signals:  {len(results)}")
    if filtered_areas:
        print(
            f"  policy-filtered (pull request, unchanged areas "
            f"{', '.join(sorted(filtered_areas))}): {len(policy_filtered)}"
        )
        for signal_id in policy_filtered:
            area = SIGNAL_REGISTRY[signal_id].path_filter_area
            print(f"    - {signal_id}: filtered (area {area} unchanged)")
    if advisory:
        print(f"  advisory (non-blocking this run): {len(advisory)}")
        for signal_id in sorted(advisory):
            signal = SIGNAL_REGISTRY.get_signal(signal_id)
            state = (
                results[signal_id].state.value if signal_id in results else "missing"
            )
            expires = signal.advisory_expires if signal else "?"
            owner = signal.advisory_owner if signal else "?"
            print(
                f"    - {signal_id}: {state} "
                f"(advisory until {expires}, owner {owner})"
            )

    for problem in problems:
        print(f"::error::{problem}")

    # A missing verdict is a failure even for an advisory signal. "Advisory"
    # means its result does not block; it does not mean the job may vanish.
    if missing:
        for name in missing:
            print(f"::error::mandatory signal has no verdict: {name}")

    # Fail-closed evaluation over the full required set. Same three rules as
    # `aggregate_truth`: the signal must be present, carry this exact SHA, and be
    # SUCCESS — with advisory signals exempt from the state rule only.
    ok = True
    downgraded: dict[str, str] = {}
    for name in sorted(required):
        result = results.get(name)
        if result is None:
            ok = False
            continue
        if result.sha != sha:
            # A stale SHA is never excusable, advisory or not: it means the
            # verdict describes different code.
            ok = False
            continue
        if result.state == SignalState.SUCCESS:
            continue
        if _is_policy_filtered(result, allow_filtered):
            # Recorded apart from verdicts (manifest `policy_filtered`).
            continue
        if name in advisory and result.state in _ADVISORY_EXCUSABLE_STATES:
            downgraded[name] = result.state.value
            print(
                f"::warning title=Advisory signal not green::{name} is "
                f"{result.state.value}. It is advisory for this evaluation and "
                f"does not block, but it is recorded in the manifest and the "
                f"merge status is withheld."
            )
            continue
        if name in advisory:
            # Allowlisted, but this is not a measured red — it is an absence of
            # evidence. See _ADVISORY_EXCUSABLE_STATES.
            print(
                f"::error::{name} is advisory-eligible but reported "
                f"'{result.state.value}', which an advisory downgrade does not "
                f"cover. Only 'failure' does: an advisory signal must still run "
                f"and still report a verdict."
            )
        ok = False

    # Cross-check against the unit-tested truth function. It knows nothing about
    # advisory downgrades, so it is the STRICT verdict: compare against it only
    # when no downgrade was applied, and otherwise require that it is the only
    # thing the downgrades explain.
    try:
        strict = aggregate_truth(results, sha, allow_filtered=allow_filtered)
    except ValueError as exc:
        print(f"::error::aggregate inputs rejected: {exc}")
        return 1
    if not advisory and strict != ok:
        print(
            "::error::internal inconsistency between the local check and "
            "aggregate_truth(); failing closed"
        )
        ok = False
    if advisory and strict and not ok:
        # Strict says green but the downgrade path says red — that can only be a
        # logic error here, and the safe direction is red.
        print(
            "::error::advisory bookkeeping disagrees with the strict verdict; "
            "failing closed"
        )
        ok = False

    if not ok or missing or problems:
        print("::error::ci-required = FAILURE")
        # `explain_aggregate_failure` returns a single human-readable string;
        # split it so multi-reason explanations stay readable.
        explanation = explain_aggregate_failure(
            results, sha, allow_filtered=allow_filtered
        )
        for line in explanation.splitlines():
            if line.strip():
                print(f"  {line}")
        _write_aggregate_json(
            args.out,
            sha,
            results,
            sorted(required),
            False,
            advisory,
            downgraded,
            event=event,
            filtered_areas=filtered_areas,
            policy_filtered=policy_filtered,
        )
        return 1

    if downgraded:
        print(
            f"ci-required = SUCCESS WITH {len(downgraded)} ADVISORY SIGNAL(S) "
            f"({', '.join(sorted(downgraded))}). This is NOT a strict pass: the "
            f"commit status is deliberately withheld for this evaluation."
        )
    else:
        print("ci-required = SUCCESS (every mandatory signal succeeded for this SHA)")
    if policy_filtered:
        print(
            f"  {len(policy_filtered)} signal(s) were policy-filtered on this pull "
            f"request; they are recorded in the manifest's `policy_filtered`, "
            f"not as verdicts."
        )
    _write_aggregate_json(
        args.out,
        sha,
        results,
        sorted(required),
        True,
        advisory,
        downgraded,
        event=event,
        filtered_areas=filtered_areas,
        policy_filtered=policy_filtered,
    )
    return 0


def _write_aggregate_json(
    out: str | None,
    sha: str,
    results: dict[str, SignalResult],
    required: list[str],
    success: bool,
    advisory: set[str] | None = None,
    downgraded: dict[str, str] | None = None,
    *,
    event: str = "",
    filtered_areas: frozenset[str] = frozenset(),
    policy_filtered: list[str] | None = None,
) -> None:
    """
    Persist the aggregate verdict for the trusted finalizer to consume.

    F-15: path-filtered signals are listed in `policy_filtered` and EXCLUDED
    from `signal_states`, which holds verdicts only. That also keeps a green
    filtered PR acceptable to the previous finalizer (which rejects any
    `signal_states` entry other than success) while this change is rolled out;
    the new finalizer (tools/ci/manifest_validation.py) additionally requires
    every required signal in exactly one of the two. `schema_version` stays 1
    because both additions are backward compatible.

    `signal_states` always records the REAL state of every signal, including
    advisory ones — the manifest is evidence, not a summary, so a downgraded
    signal must still read `failure` here. `advisory_signals` records what was
    permitted to be advisory and `advisory_downgraded` records which of those
    actually needed it, so a reader can tell "allowed but green" from "allowed
    and red". `strict_outcome` is what the verdict would have been with no
    downgrades at all, which is the field
    `.github/scripts/ci-validate-evidence.sh` uses to refuse to finalize a pull
    request on anything but a strict pass.
    """
    if not out:
        return
    advisory = advisory or set()
    downgraded = downgraded or {}
    payload = {
        "schema_version": 1,
        "producer": "ci-evidence",
        "evaluation_sha": sha,
        "outcome": "success" if success else "failure",
        "strict_outcome": "success" if success and not downgraded else "failure",
        "event": event,
        "filtered_areas": sorted(filtered_areas),
        "required_signals": required,
        "signal_states": {
            name: result.state.value
            for name, result in sorted(results.items())
            if result.state != SignalState.FILTERED
        },
        "policy_filtered": sorted(policy_filtered or []),
        "advisory_signals": sorted(advisory),
        "advisory_downgraded": dict(sorted(downgraded.items())),
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
        prog="tools.ci.ci_gate",
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
    # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
    # In future this must be changed back to BLOCKING, and the outstanding High/Critical
    # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
    scan.add_argument(
        "--mode",
        choices=SCAN_GATE_MODES,
        default="block",
        help=(
            "warn reports High/Critical findings and unusable reports as "
            "warnings and exits 0. TEMPORARY, see TODO."
        ),
    )
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
        "--advisory",
        action="append",
        default=[],
        metavar="SIGNAL_ID",
        help=(
            "Treat a signal as advisory for THIS evaluation: it must still "
            "report, its real state is still recorded, but a non-success state "
            "does not fail the aggregate. Repeatable, and also accepts a "
            "comma- or newline-separated list. Only ids allowlisted as "
            "advisory_eligible in tools/ci/signal_registry.py are accepted, and "
            "only before their advisory_expires date; anything else fails."
        ),
    )
    agg.add_argument(
        "--event",
        default="",
        help="github.event_name of the evaluation (recorded in the manifest).",
    )
    agg.add_argument(
        "--filtered-area",
        action="append",
        default=[],
        metavar="AREA",
        help=(
            "A change area ci.yml's `changes` job reported unchanged (F-15). "
            "Repeatable. Only valid with --event pull_request and only for "
            "areas in signal_registry.PATH_FILTER_AREAS; a skipped job whose "
            "signals are all in a filtered area is then FILTERED, not SKIPPED."
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
