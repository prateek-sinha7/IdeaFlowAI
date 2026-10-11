"""
The ONE reviewed, dated exceptions list for Trivy and Grype.

WHAT THIS REPLACES
------------------
There used to be two inconsistent exception mechanisms for the same CVEs:

* `pip-audit --ignore-vuln PYSEC-2026-1325` in `.github/scripts/ci-pip-audit.sh`
* `tools/ci/npm_audit_accepts.py` for the two image-size advisories

while the container scans, which report the SAME findings, accepted nothing.
So the dependency-audit exceptions unblocked nothing: the image scan stayed red
on ecdsa and image-size regardless. pip-audit was redundant with the image scan
(the backend image installs the exact `uv export --frozen --no-dev` slice of
the same uv.lock) and npm audit was replaced by a Trivy scan of
`frontend/package-lock.json`, so every vulnerability verdict now comes from
Trivy or Grype, and every exception to it lives here.

WHERE THIS SITS, AND WHY IT IS NOT A HOLE IN THE GATE
-----------------------------------------------------
`tools.ci.ci_gate scan-gate` still has no way to downgrade a failure. This
module runs BEFORE it, on the report side: it removes a finding from a copy of
the report only when that finding is named here, for that exact package, in a
scope this entry declares, before this entry's expiry date. The raw report and
the gated report are both kept as evidence.

FAIL-CLOSED IN EVERY DIRECTION
------------------------------
* EXACT MATCH ONLY. A finding is removed only when its vulnerability id (or one
  of its Grype-reported aliases) is listed on an entry AND its package name is
  that entry's package. A new advisory on an accepted package is a different
  decision and stays red. There are no wildcards, no severity filters, and no
  `--ignore-unfixed`.
* EXPIRY IS ENFORCED. An entry past `expires` is an error for every scope it
  declares. It does not quietly stop matching; the build fails and names it, so
  the renewal (or the fix) is a reviewed change.
* STALE ENTRIES FAIL. An entry that matches nothing in ANY report of a scope it
  declares is an error. Staleness is judged across all reports of one scope at
  once (Trivy and Grype together), so a naming difference between the two
  engines cannot turn it red, but an entry that protects nothing cannot linger.
* A MISSING OR UNPARSEABLE REPORT FAILS. Nothing is written for it, so the gate
  that follows also fails on "report not found".

Usage (paths relative to the repository root):

    python -m tools.ci.scan_accepts --scope backend-image \
        --trivy ci-results/trivy-backend-report.json \
        --grype ci-results/grype-backend-report.json \
        --out ci-results/scan-accepts-backend-image.json

Each input `<name>.json` produces `<name>-gated.json` next to it; that is the
file `scan-gate` must read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

#: Every scope an entry may declare. One per artifact the pipeline scans.
#:   backend-image      backend/Dockerfile image (Trivy + Grype)
#:   frontend-image     frontend/Dockerfile image (Trivy + Grype)
#:   frontend-lockfile  frontend/package-lock.json (Trivy fs). The image scan
#:                      cannot see most frontend dependencies: Next.js
#:                      `output: "standalone"` compiles them into .next/ chunks,
#:                      which carry no package.json for a scanner to read.
KNOWN_SCOPES: frozenset[str] = frozenset(
    {"backend-image", "frontend-image", "frontend-lockfile"}
)


@dataclass(frozen=True)
class AcceptedFinding:
    """One reviewed exception. Every field is required and reviewed in the diff."""

    #: Every identifier the scanners may report for this ONE vulnerability:
    #: the CVE, the GHSA, and any PYSEC alias. Trivy reports one id per finding;
    #: Grype reports one id plus `relatedVulnerabilities`, so listing the whole
    #: alias set is what lets one entry cover both engines.
    ids: frozenset[str]
    #: The package the finding must be on. Compared after normalisation
    #: (case-insensitive, `_`/`.` treated as `-`), so `python_jose` and
    #: `python-jose` are the same package, as they are to pip.
    package: str
    #: Which scanned artifacts this entry applies to. A subset of KNOWN_SCOPES.
    scopes: frozenset[str]
    #: Last day this entry is valid (inclusive), ISO-8601.
    expires: str
    #: Who owns removing the need for this entry.
    owner: str
    #: Why the finding is accepted, what limits its impact here, and what ends
    #: the acceptance.
    justification: str

    def is_expired(self, today: date) -> bool:
        """True once `today` is after the expiry date."""
        return today > date.fromisoformat(self.expires)


#: Reviewed exceptions. Keep this list SHORT and each entry specific.
#:
#: Rules for adding an entry:
#:   1. No published fix reachable from our pins. A finding with a fix is a
#:      bump or a Dockerfile change, not an exception. (setuptools
#:      CVE-2025-47273 was fixable and is fixed in backend/Dockerfile, so it is
#:      deliberately NOT here.)
#:   2. The reachable impact in THIS codebase is argued in `justification`.
#:   3. Expiry is at most one quarter out. Renewing is a reviewed change.
ACCEPTED_FINDINGS: tuple[AcceptedFinding, ...] = (
    AcceptedFinding(
        ids=frozenset({"CVE-2023-45853"}),
        package="zlib1g",
        scopes=frozenset({"backend-image", "frontend-image"}),
        expires="2026-12-31",
        owner="platform-engineering",
        justification=(
            "zlib CVE-2023-45853: integer overflow in MiniZip's "
            "zipOpenNewFileInZip4_64. MiniZip is zlib's contrib/minizip code; "
            "Debian's zlib1g binary package does not build or ship it, and "
            "neither image installs the separate minizip/libminizip packages. "
            "Debian bookworm has no fixed zlib1g (the tracker records it as "
            "not fixed for bookworm), so there is nothing to bump to on the "
            "pinned python:3.13-slim-bookworm, node:20-bookworm-slim (backend "
            "pptx stage) and node:24.11.0-bookworm-slim (frontend) bases. "
            "Ends when every base image moves to a release with zlib >= 1.3.1 "
            "(e.g. Debian trixie) or bookworm ships a fix."
        ),
    ),
    AcceptedFinding(
        ids=frozenset({"CVE-2024-23342", "GHSA-wj6h-64fc-37mp", "PYSEC-2026-1325"}),
        package="ecdsa",
        scopes=frozenset({"backend-image"}),
        expires="2026-12-31",
        owner="platform-engineering",
        justification=(
            "python-ecdsa CVE-2024-23342 (Minerva timing side channel in ECDSA "
            "signing on P-256). NO FIX: the ecdsa maintainers treat side "
            "channels as out of scope. It is present only as a transitive "
            "dependency of python-jose. The backend never signs with an EC "
            "key: app/core/cognito.py verifies Cognito tokens with "
            "algorithms=['RS256'] and app/api/auth.py only reads unverified "
            "claims; the local HS256 path was removed in the Cognito-only "
            "migration. The vulnerable signing path is therefore unreachable. "
            "Ends with the PyJWT migration, which removes python-jose and "
            "ecdsa from uv.lock."
        ),
    ),
    AcceptedFinding(
        ids=frozenset({"CVE-2025-71330", "GHSA-w3rx-r6r6-pgpr"}),
        package="image-size",
        scopes=frozenset({"backend-image", "frontend-lockfile"}),
        expires="2026-12-31",
        owner="frontend",
        justification=(
            "image-size CVE-2025-71330: infinite loop in the ICNS parser. NO "
            "FIX PUBLISHED: every release through 2.0.2 (the latest) is "
            "affected. Reaches us only through the pinned pptxgenjs@3.12.0, "
            "which reads image dimensions when embedding an image in a deck. "
            "Frontend: the impact is a hung tab for the user running their own "
            "client-side export (src/lib/exporters/pptExporter.ts). Backend "
            "image (/opt/pptx/node_modules): pptxgenjs runs in the "
            "app/services/pptx_export.py sandbox with RLIMIT_CPU=60s, a 120s "
            "wall-clock timeout and a 3-slot semaphore, so a hostile image "
            "costs at most one export slot for two minutes. Ends when the "
            "client-side .pptx export is dropped (the HTML deck pipeline "
            "supersedes it) and pptxgenjs is removed, or image-size ships a fix."
        ),
    ),
    AcceptedFinding(
        ids=frozenset({"CVE-2025-71329", "GHSA-5p2g-fcmc-qvqq"}),
        package="image-size",
        scopes=frozenset({"backend-image", "frontend-lockfile"}),
        expires="2026-12-31",
        owner="frontend",
        justification=(
            "image-size CVE-2025-71329: infinite loop in the JXL and HEIF "
            "parsers. Same package, same unfixed status (affected through "
            "2.0.2), same path through pptxgenjs, same sandbox bounds, and the "
            "same end condition as CVE-2025-71330 above."
        ),
    ),
)


class ReportError(ValueError):
    """A report is missing, empty, unparseable, or not the expected shape."""


def normalise_package(name: str) -> str:
    """Normalise a package name the way pip does (PEP 503), for npm/deb too."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def accepts_for_scope(
    scope: str, accepts: Iterable[AcceptedFinding] = ACCEPTED_FINDINGS
) -> list[AcceptedFinding]:
    """Return the entries that declare `scope`."""
    return [accept for accept in accepts if scope in accept.scopes]


def _match(
    finding_ids: set[str], package: str, candidates: list[AcceptedFinding]
) -> AcceptedFinding | None:
    """Return the entry covering this exact finding, if any."""
    normalised = normalise_package(package)
    for accept in candidates:
        if normalise_package(accept.package) != normalised:
            continue
        if finding_ids & accept.ids:
            return accept
    return None


def filter_trivy_report(
    report: dict[str, Any], candidates: list[AcceptedFinding]
) -> tuple[dict[str, Any], list[tuple[AcceptedFinding, str]]]:
    """
    Remove accepted findings from a Trivy JSON report (image or fs).

    Returns (gated copy, [(entry, "<id> <pkg>@<version>"), ...]). The input is
    not mutated. Misconfigurations and secrets are never touched.
    """
    results = report.get("Results", [])
    if not isinstance(results, list):
        raise ReportError("Trivy 'Results' must be an array")

    matched: list[tuple[AcceptedFinding, str]] = []
    gated_results: list[Any] = []
    for result in results:
        if not isinstance(result, dict):
            raise ReportError("each Trivy result must be an object")
        vulnerabilities = result.get("Vulnerabilities")
        if not isinstance(vulnerabilities, list):
            gated_results.append(result)
            continue
        kept: list[Any] = []
        for vuln in vulnerabilities:
            if not isinstance(vuln, dict):
                raise ReportError("each Trivy vulnerability must be an object")
            vuln_id = str(vuln.get("VulnerabilityID", ""))
            package = str(vuln.get("PkgName", ""))
            accept = _match({vuln_id}, package, candidates)
            if accept is None:
                kept.append(vuln)
                continue
            version = vuln.get("InstalledVersion", "")
            matched.append((accept, f"{vuln_id} {package}@{version}"))
        gated = dict(result)
        gated["Vulnerabilities"] = kept
        gated_results.append(gated)

    gated_report = dict(report)
    gated_report["Results"] = gated_results
    return gated_report, matched


def filter_grype_report(
    report: dict[str, Any], candidates: list[AcceptedFinding]
) -> tuple[dict[str, Any], list[tuple[AcceptedFinding, str]]]:
    """
    Remove accepted findings from a Grype JSON report.

    A Grype match is identified by `vulnerability.id` plus every
    `relatedVulnerabilities[].id`, because Grype often reports the GHSA while
    Trivy reports the CVE for the same issue.
    """
    matches = report.get("matches", [])
    if not isinstance(matches, list):
        raise ReportError("Grype 'matches' must be an array")

    matched: list[tuple[AcceptedFinding, str]] = []
    kept: list[Any] = []
    for entry in matches:
        if not isinstance(entry, dict):
            raise ReportError("each Grype match must be an object")
        vulnerability = entry.get("vulnerability")
        artifact = entry.get("artifact")
        if not isinstance(vulnerability, dict) or not isinstance(artifact, dict):
            raise ReportError("Grype match lacks a 'vulnerability' or 'artifact'")
        ids = {str(vulnerability.get("id", ""))}
        for related in entry.get("relatedVulnerabilities") or []:
            if isinstance(related, dict) and related.get("id"):
                ids.add(str(related["id"]))
        package = str(artifact.get("name", ""))
        accept = _match(ids, package, candidates)
        if accept is None:
            kept.append(entry)
            continue
        version = artifact.get("version", "")
        matched.append((accept, f"{vulnerability.get('id')} {package}@{version}"))

    gated_report = dict(report)
    gated_report["matches"] = kept
    return gated_report, matched


_FILTERS = {
    "trivy": filter_trivy_report,
    "grype": filter_grype_report,
}


def _load_report(path: Path) -> dict[str, Any]:
    """Read one scanner report, failing closed on anything unusable."""
    if not path.exists():
        raise ReportError(f"report not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ReportError(f"report is empty: {path}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportError(f"report is not parseable JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReportError(f"report root must be an object: {path}")
    return data


def gated_path(raw: Path) -> Path:
    """`<name>.json` -> `<name>-gated.json`, the file scan-gate must read."""
    return raw.with_name(f"{raw.stem}-gated.json")


def apply_accepts(
    scope: str,
    reports: list[tuple[str, Path]],
    today: date,
    accepts: Iterable[AcceptedFinding] = ACCEPTED_FINDINGS,
) -> tuple[list[str], dict[str, Any]]:
    """
    Apply every entry for `scope` to every report, and write the gated copies.

    Args:
        scope: one of KNOWN_SCOPES.
        reports: (engine, raw report path) pairs; engine is "trivy" or "grype".
        today: the evaluation date (injected so expiry is testable).
        accepts: the exceptions list (injected for tests).

    Returns:
        (errors, evidence). `errors` is empty only when every report was usable,
        no declared entry has expired, and every declared entry matched at least
        one finding in this scope. Gated reports are written for every usable
        report even when `errors` is non-empty, so the gate still records a
        per-engine verdict.
    """
    if scope not in KNOWN_SCOPES:
        return [f"unknown scope '{scope}'; expected one of {sorted(KNOWN_SCOPES)}"], {}

    candidates = accepts_for_scope(scope, accepts)
    errors: list[str] = []
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "scope": scope,
        "evaluated_on": today.isoformat(),
        "reports": {},
    }

    expired = [accept for accept in candidates if accept.is_expired(today)]
    for accept in expired:
        errors.append(
            f"exception for {sorted(accept.ids)} on '{accept.package}' expired on "
            f"{accept.expires} (owner {accept.owner}). Fix the finding or renew "
            f"the entry in tools/ci/scan_accepts.py in a reviewed change."
        )
    active = [accept for accept in candidates if accept not in expired]

    used: set[AcceptedFinding] = set()
    all_reports_usable = True
    for engine, raw in reports:
        filter_fn = _FILTERS.get(engine)
        if filter_fn is None:
            errors.append(f"unknown engine '{engine}' for {raw}")
            all_reports_usable = False
            continue
        try:
            gated, matched = filter_fn(_load_report(raw), active)
        except ReportError as exc:
            errors.append(f"{engine}: {exc}")
            all_reports_usable = False
            continue

        out = gated_path(raw)
        out.write_text(json.dumps(gated, indent=2), encoding="utf-8")
        used.update(accept for accept, _ in matched)
        evidence["reports"][engine] = {
            "raw": str(raw),
            "gated": str(out),
            "accepted": [
                {"finding": label, "ids": sorted(accept.ids), "owner": accept.owner}
                for accept, label in matched
            ],
        }

    # Staleness is only meaningful when every report was read: a crashed
    # scanner already fails the scope, and judging staleness on the survivors
    # would add a misleading second error.
    if all_reports_usable:
        for accept in active:
            if accept not in used:
                errors.append(
                    f"exception for {sorted(accept.ids)} on '{accept.package}' "
                    f"matched nothing in any {scope} report. Delete it from "
                    f"tools/ci/scan_accepts.py (or drop '{scope}' from its "
                    f"scopes) rather than keep an exception that protects nothing."
                )

    evidence["errors"] = errors
    return errors, evidence


def validate_accepts(
    accepts: Iterable[AcceptedFinding] = ACCEPTED_FINDINGS,
) -> list[str]:
    """Structural checks on the list itself. Empty means the list is well formed."""
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for accept in accepts:
        label = f"{sorted(accept.ids)} on '{accept.package}'"
        if not accept.ids or any(not vuln_id.strip() for vuln_id in accept.ids):
            problems.append(f"{label}: ids must be non-empty")
        if not accept.package.strip():
            problems.append(f"{label}: package must be non-empty")
        if not accept.scopes or not accept.scopes <= KNOWN_SCOPES:
            problems.append(
                f"{label}: scopes must be a non-empty subset of {sorted(KNOWN_SCOPES)}"
            )
        try:
            date.fromisoformat(accept.expires)
        except ValueError:
            problems.append(f"{label}: expires '{accept.expires}' is not an ISO date")
        if not accept.owner.strip():
            problems.append(f"{label}: owner must be non-empty")
        if len(accept.justification.strip()) < 40:
            problems.append(
                f"{label}: justification is too short to be a review record"
            )
        for vuln_id in accept.ids:
            key = (vuln_id, normalise_package(accept.package))
            if key in seen:
                problems.append(f"{label}: {vuln_id} is listed twice for this package")
            seen.add(key)
    return problems


def main(argv: list[str] | None = None, today: date | None = None) -> int:
    """Entrypoint. Returns the process exit code."""
    parser = argparse.ArgumentParser(prog="tools.ci.scan_accepts")
    parser.add_argument("--scope", required=True, choices=sorted(KNOWN_SCOPES))
    parser.add_argument("--trivy", help="raw Trivy JSON report")
    parser.add_argument("--grype", help="raw Grype JSON report")
    parser.add_argument("--out", required=True, help="evidence JSON to write")
    args = parser.parse_args(argv)

    reports: list[tuple[str, Path]] = []
    if args.trivy:
        reports.append(("trivy", Path(args.trivy)))
    if args.grype:
        reports.append(("grype", Path(args.grype)))
    if not reports:
        print("::error::scan_accepts needs at least one of --trivy / --grype")
        return 1

    structural = validate_accepts()
    if structural:
        for problem in structural:
            print(f"::error::tools/ci/scan_accepts.py: {problem}")
        return 1

    errors, evidence = apply_accepts(args.scope, reports, today or date.today())

    for engine, record in evidence.get("reports", {}).items():
        for item in record["accepted"]:
            print(
                f"{args.scope}/{engine}: accepted {item['finding']} (owner {item['owner']})"
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    for error in errors:
        print(f"::error::{args.scope}: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
