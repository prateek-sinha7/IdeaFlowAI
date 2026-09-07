"""
Create the merged JUnit report that the evidence uploads reference.

The original pipeline advertised `junit-merged.xml` as an artifact but no step
ever produced it, so a missing file was uploaded (or silently skipped) and
nothing noticed. This module actually creates it, by parsing each producer's
report and recomputing the suite totals rather than concatenating XML text —
concatenated JUnit is not valid XML and consumers reject it.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _iter_suites(root: ET.Element):
    """Yield every <testsuite> element, whether or not it is wrapped."""
    if root.tag == "testsuite":
        yield root
    else:
        yield from root.iter("testsuite")


def cmd_junit(args: argparse.Namespace) -> int:
    """Merge several JUnit files into one, recomputing totals."""
    merged = ET.Element("testsuites")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    total_time = 0.0

    missing: list[str] = []
    for raw_path in args.inputs:
        path = Path(raw_path)
        if not path.exists() or path.stat().st_size == 0:
            missing.append(raw_path)
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            print(f"::error::{path} is not parseable JUnit XML: {exc}")
            return 1

        for suite in _iter_suites(root):
            merged.append(suite)
            for key in totals:
                totals[key] += int(suite.get(key, "0") or 0)
            total_time += float(suite.get("time", "0") or 0)

    if missing:
        # A mandatory producer report that is absent means the merged artifact
        # would misrepresent the run. Fail rather than publish a partial total.
        for raw_path in missing:
            print(f"::error::mandatory JUnit input missing or empty: {raw_path}")
        return 1

    if totals["tests"] == 0:
        print("::error::merged JUnit contains zero tests; refusing to publish it")
        return 1

    for key, value in totals.items():
        merged.set(key, str(value))
    merged.set("time", f"{total_time:.3f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(merged).write(out, encoding="utf-8", xml_declaration=True)

    print(
        f"Merged {len(args.inputs)} report(s) into {out}: "
        f"{totals['tests']} tests, {totals['failures']} failures, "
        f"{totals['errors']} errors, {totals['skipped']} skipped."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI."""
    parser = argparse.ArgumentParser(prog="agents.ci.report_merger_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    junit = sub.add_parser("junit", help="Merge JUnit XML reports.")
    junit.add_argument("--out", required=True)
    junit.add_argument("inputs", nargs="+")
    junit.set_defaults(func=cmd_junit)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
