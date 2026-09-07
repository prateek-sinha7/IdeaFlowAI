"""
Apply reviewed, per-advisory accepts to an `npm audit --json` report.

WHERE THIS SITS, AND WHY IT IS NOT A HOLE IN THE GATE
-----------------------------------------------------
`agents.ci.ci_gate scan-gate` has, deliberately, no way to downgrade a failure:
a resolved High or Critical finding fails the signal whether or not a fix
exists. That property is preserved here. This module runs BEFORE the gate, on
the report-production side, and is the npm equivalent of the `--ignore-vuln`
flag `.github/scripts/ci-pip-audit.sh` already passes to pip-audit for
PYSEC-2026-1325. `npm audit` has no such flag, so the accept has to be applied
to its JSON instead — the placement differs, the reviewability does not.

WHY A MODULE RATHER THAN A `jq` ONE-LINER
-----------------------------------------
npm reports one entry per affected package, and an entry's `via` list either
holds advisory objects (the package is the root cause) or the NAMES of other
packages (the package is only affected through them). Dropping the root cause
without dropping its propagators leaves the propagator entry behind and the
gate still red, so the accept has to be resolved transitively across `via`.
That is real logic, and it is covered by tests/ci/test_npm_audit_accepts.py.

FAIL-CLOSED IN BOTH DIRECTIONS
------------------------------
* An entry is dropped ONLY when EVERY advisory reachable from it is accepted.
  One new advisory on an accepted package keeps the entry, so the signal turns
  red again instead of hiding the newcomer behind an old decision.
* An accept that no longer matches anything in the report is an ERROR, not a
  silent no-op. A stale accept is exactly the sort of config that reads as
  active while protecting nothing, so it has to be deleted deliberately.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AcceptedAdvisory:
    """One reviewed npm advisory accept."""

    #: GitHub advisory identifier, as it appears in the `url` of an npm
    #: `via` entry. Matching on the GHSA rather than on the package name is
    #: what keeps the accept narrow: a different advisory on the same package
    #: is a different decision.
    ghsa: str
    #: Why this finding is accepted, and what would end the acceptance.
    #: Reviewed in the diff — this is the record, not a comment about one.
    justification: str


#: Reviewed accepts. Keep this list SHORT and each entry specific.
#:
#: These may only ever hold IaC-unrelated software advisories that are (a)
#: unfixable upstream today and (b) triaged for reachability. Anything with a
#: published fix is a bump, not an accept.
ACCEPTED_ADVISORIES: tuple[AcceptedAdvisory, ...] = (
    AcceptedAdvisory(
        ghsa="GHSA-w3rx-r6r6-pgpr",
        justification=(
            "image-size CVE-2025-71330 — infinite loop in the ICNS parser. "
            "NO FIX PUBLISHED: every release through 2.0.2 (the latest) is "
            "affected and the image-size repository has issues disabled, so "
            "there is no upstream to bump to. Reaches us only transitively, "
            "via the pinned pptxgenjs (frontend/package.json), which calls "
            "image-size when embedding an image in a generated deck. Impact "
            "is a hung tab in the browser of the user who triggered their own "
            "export — no server-side component parses images with it. "
            "Remediation is tracked as dropping the client-side .pptx export "
            "path (src/lib/exporters/pptExporter.ts), which the HTML deck "
            "pipeline already supersedes; this accept ends when that lands or "
            "when image-size ships a fix, whichever is first."
        ),
    ),
    AcceptedAdvisory(
        ghsa="GHSA-5p2g-fcmc-qvqq",
        justification=(
            "image-size CVE-2025-71329 — infinite loop in the JXL and HEIF "
            "parsers. Same package, same unfixed status (affected through "
            "2.0.2, no patched release), same transitive path through "
            "pptxgenjs, and the same remediation and end condition as "
            "GHSA-w3rx-r6r6-pgpr above."
        ),
    ),
)


def _advisory_ids(entry: dict[str, Any]) -> set[str]:
    """
    Return the GHSA ids declared directly on one `vulnerabilities` entry.

    npm puts the advisory's GitHub URL in `via[].url`; the id is its last path
    segment. `via` members that are plain strings are package names, not
    advisories, and are resolved by the caller.
    """
    ids: set[str] = set()
    for via in entry.get("via", []):
        if isinstance(via, dict):
            url = str(via.get("url", ""))
            if "/advisories/" in url:
                ids.add(url.rsplit("/", 1)[-1])
    return ids


def _reachable_advisories(
    package: str,
    vulnerabilities: dict[str, Any],
    seen: frozenset[str] = frozenset(),
) -> set[str] | None:
    """
    Collect every advisory reachable from `package` through the `via` graph.

    Returns None when the graph cannot be fully resolved — an unknown package
    name in `via`, or a cycle — because a partially known cause set must never
    be treated as "entirely accepted".
    """
    if package in seen:
        return None
    entry = vulnerabilities.get(package)
    if not isinstance(entry, dict):
        return None

    advisories = _advisory_ids(entry)
    for via in entry.get("via", []):
        if isinstance(via, str):
            nested = _reachable_advisories(via, vulnerabilities, seen | {package})
            if nested is None:
                return None
            advisories |= nested
    return advisories


def filter_report(
    report: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Drop fully-accepted entries from an npm audit report.

    Args:
        report: the parsed `npm audit --json` document.

    Returns:
        (filtered report, dropped package names, unused accept ids). The input
        is not mutated. `unused` lists accepted GHSA ids that matched nothing,
        which the CLI treats as an error.
    """
    accepted = {accept.ghsa for accept in ACCEPTED_ADVISORIES}
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return report, [], sorted(accepted)

    matched: set[str] = set()
    kept: dict[str, Any] = {}
    dropped: list[str] = []

    for package, entry in vulnerabilities.items():
        causes = _reachable_advisories(package, vulnerabilities)
        if causes and causes <= accepted:
            matched |= causes
            dropped.append(package)
            continue
        kept[package] = entry

    filtered = dict(report)
    filtered["vulnerabilities"] = kept
    filtered["metadata"] = _recount(report.get("metadata"), kept)
    return filtered, dropped, sorted(accepted - matched)


def _recount(metadata: Any, kept: dict[str, Any]) -> Any:
    """
    Rebuild `metadata.vulnerabilities` so the report stays self-consistent.

    The gate derives its verdict from the `vulnerabilities` map, not from these
    counters, but the filtered report is also uploaded as evidence and a
    document whose summary contradicts its body is a trap for the next reader.
    """
    if not isinstance(metadata, dict):
        return metadata

    counts = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0}
    for entry in kept.values():
        severity = entry.get("severity") if isinstance(entry, dict) else None
        if severity in counts:
            counts[severity] += 1
    counts["total"] = sum(counts.values())

    updated = dict(metadata)
    updated["vulnerabilities"] = counts
    return updated


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. Returns the process exit code."""
    parser = argparse.ArgumentParser(prog="agents.ci.npm_audit_accepts")
    parser.add_argument("--report", required=True, help="raw npm audit JSON")
    parser.add_argument("--out", required=True, help="filtered JSON for the gate")
    args = parser.parse_args(argv)

    raw = Path(args.report)
    if not raw.exists() or raw.stat().st_size == 0:
        print(f"::error::npm audit report missing or empty: {raw}")
        return 1

    try:
        report = json.loads(raw.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"::error::npm audit report is not parseable JSON: {exc}")
        return 1

    filtered, dropped, unused = filter_report(report)

    for accept in ACCEPTED_ADVISORIES:
        if accept.ghsa not in unused:
            print(f"Accepted {accept.ghsa}: {accept.justification}")

    if unused:
        # A stale accept is a failure, not a courtesy. Either the dependency
        # moved and the entry should be deleted, or the report shape changed
        # and the accept silently stopped applying — both need a human.
        for ghsa in unused:
            print(
                f"::error::accepted advisory {ghsa} matched nothing in "
                f"{raw}. Delete the stale accept in "
                f"agents/ci/npm_audit_accepts.py rather than leaving a "
                f"suppression that protects nothing."
            )
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
    print(
        f"Applied {len(ACCEPTED_ADVISORIES)} reviewed accept(s); "
        f"dropped {len(dropped)} fully-accepted entr(y/ies): "
        f"{', '.join(dropped) or 'none'}. Wrote {out}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
