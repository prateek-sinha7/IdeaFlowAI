"""
Canonical backend test inventory, partition proof, and execution verification.

Two subcommands:

  (default)          Collect the complete test universe once, assign every node
                     to exactly one partition from its real pytest markers, and
                     prove the partitions are exhaustive and disjoint.

  verify-execution   Compare a partition from that inventory against what a test
                     run actually executed, and fail on an omitted node, a node
                     executed twice, or a skip inside a mandatory partition
                     (the one exemption: an xfail(strict=True) carrying an
                     ``issue`` marker — a tracked known bug that still runs).

Both fail closed. A collection error, an ambiguous marker combination, an
unowned test-like file, or a missing mandatory suite is a failure, not a warning:
an inventory that quietly shrinks is worse than no inventory, because the jobs
downstream would report success over a smaller universe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .execution_recorder import LIVE_MARKERS, POSTGRES_MARKERS

#: Suites whose absence means the inventory is not the complete universe.
#: These encode invariants the project must never stop checking (INV-3, the
#: name-free kernel, and the retired-transport ratchet), so "collection found
#: nothing here" has to be an error rather than an empty partition.
#:
#: Every path below is a SUBSTRING of a pytest node id, so it must track the
#: real tree. All four drifted when the suites were migrated into the canonical
#: tests/<suite>/ layout, and three of them started failing the gate outright:
#: test_banned_patterns.py and test_sse_cutover_banned_patterns.py moved to
#: tests/unit/agents/, and test_workflow_contracts.py to tests/unit/tools/ci/.
#:
#: The characterization entry was the dangerous one, because it did NOT fail. It
#: still matched a single straggler, tests/agents/test_characterization_sample_
#: subagents_parallel.py, while the six actual INV-3 golden suites had moved to
#: tests/contract/agents/. The guard was green while guarding almost nothing —
#: the same "matching on names that cannot occur" failure this repo calls out
#: elsewhere. It now points at the goldens themselves.
REQUIRED_SUITE_MARKERS: dict[str, str] = {
    "characterization goldens (INV-3)": "tests/contract/agents/test_characterization_",
    "name-free kernel banned patterns": "tests/unit/agents/test_banned_patterns.py",
    "retired transport banned patterns": (
        "tests/unit/agents/test_sse_cutover_banned_patterns.py"
    ),
    "workflow contract tests": "tests/unit/tools/ci/test_workflow_contracts.py",
}

#: Extensions pytest will never collect. A test-like file with one of these
#: needs an explicit owner in ci/test-suites.toml or it is invisible work.
UNCOLLECTABLE_TEST_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".tsx")


def _run_collection(tests_dir: str, record_path: Path) -> None:
    """Collect the whole tree once with the recorder plugin attached."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            "-m",
            "pytest",
            tests_dir,
            "--collect-only",
            "-q",
            "-p",
            "tools.ci.execution_recorder",
            f"--inventory-record={record_path}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if not record_path.exists():
        sys.stderr.write(completed.stdout[-4000:])
        sys.stderr.write(completed.stderr[-4000:])
        raise RuntimeError(
            "pytest collection produced no inventory record; treating as a "
            "collection failure"
        )


def _find_unowned_test_like_files(repo_root: Path) -> list[str]:
    """
    Find tracked test-like files pytest cannot collect and nothing else owns.

    A file named like a test but never executed is the most expensive kind of
    dead weight: it looks like coverage and provides none.
    """
    registry = repo_root / "ci" / "test-suites.toml"
    registered_text = registry.read_text(encoding="utf-8") if registry.exists() else ""

    unowned: list[str] = []
    tests_root = repo_root / "backend" / "tests"
    if not tests_root.exists():
        return unowned

    for path in sorted(tests_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in UNCOLLECTABLE_TEST_SUFFIXES:
            continue
        name = path.name
        if not (name.startswith("test_") or name.endswith(("_test" + path.suffix,))):
            continue
        relative = path.relative_to(repo_root).as_posix()
        if relative not in registered_text:
            unowned.append(relative)
    return unowned


def cmd_build(args: argparse.Namespace) -> int:
    """Build the canonical inventory and prove the partition."""
    repo_root = Path(__file__).resolve().parents[3]
    problems: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        record_path = Path(tmp) / "inventory-record.json"
        try:
            _run_collection(args.tests_dir, record_path)
        except RuntimeError as exc:
            print(f"::error::{exc}")
            return 1
        record = json.loads(record_path.read_text(encoding="utf-8"))

    if record["collection_errors"]:
        for err in record["collection_errors"]:
            print(f"::error::collection error: {err}")
        return 1

    nodes: list[dict[str, Any]] = record["nodes"]
    if not nodes:
        print("::error::collection produced zero nodes; the inventory is empty")
        return 1

    partitions: dict[str, list[str]] = {"offline": [], "postgres": [], "live": []}
    for node in nodes:
        markers = set(node["markers"])
        # A node marked both live and PostgreSQL has no unambiguous owner. Guessing
        # could pull a credential-requiring test into a mandatory partition.
        if markers & LIVE_MARKERS and markers & POSTGRES_MARKERS:
            problems.append(
                f"{node['nodeid']} carries both live and PostgreSQL markers "
                f"({sorted(markers)}); its partition is ambiguous"
            )
        partitions[node["partition"]].append(node["nodeid"])

    all_ids = [node["nodeid"] for node in nodes]
    duplicates = sorted({nid for nid in all_ids if all_ids.count(nid) > 1})
    if duplicates:
        for nid in duplicates:
            problems.append(f"duplicate collected node ID: {nid}")

    # Exhaustive and disjoint.
    union = set().union(*(set(v) for v in partitions.values()))
    if union != set(all_ids):
        problems.append("partition union does not equal the collected universe")
    for left in partitions:
        for right in partitions:
            if left < right:
                overlap = set(partitions[left]) & set(partitions[right])
                if overlap:
                    problems.append(
                        f"partitions {left} and {right} overlap on "
                        f"{sorted(overlap)[:5]}"
                    )

    for label, needle in REQUIRED_SUITE_MARKERS.items():
        if not any(needle in nid for nid in all_ids):
            problems.append(f"required suite absent from the inventory: {label}")

    for relative in _find_unowned_test_like_files(repo_root):
        problems.append(
            f"test-like file is neither collected by pytest nor registered in "
            f"ci/test-suites.toml: {relative}"
        )

    payload = {
        "schema_version": 1,
        "evaluation_sha": args.evaluation_sha,
        "counts": {name: len(ids) for name, ids in partitions.items()},
        "total_collected": len(all_ids),
        "partitions": {name: sorted(ids) for name, ids in partitions.items()},
    }
    payload["inventory_digest"] = hashlib.sha256(
        json.dumps(payload["partitions"], sort_keys=True).encode("utf-8")
    ).hexdigest()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Collected {len(all_ids)} node(s) for {args.evaluation_sha}")
    for name in ("offline", "postgres", "live"):
        print(f"  {name:<9} {len(partitions[name])}")
    print(f"  digest    {payload['inventory_digest']}")

    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 1

    print("Partition is exhaustive, disjoint, and complete.")
    return 0


def _is_tracked_known_bug(node: dict[str, Any]) -> bool:
    """True iff a skipped node is an xfail(strict=True) carrying an issue marker."""
    return bool(node.get("xfailed") and node.get("strict_xfail") and node.get("issues"))


def cmd_verify_execution(args: argparse.Namespace) -> int:
    """Compare an inventory partition against what actually executed."""
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    expected = set(inventory["partitions"][args.partition])

    execution_path = Path(args.execution)
    if not execution_path.exists():
        print(
            f"::error::execution record {execution_path} is missing; cannot prove "
            f"the {args.partition} partition ran"
        )
        return 1
    execution = json.loads(execution_path.read_text(encoding="utf-8"))

    observed: dict[str, dict[str, Any]] = {
        node["nodeid"]: node for node in execution["nodes"]
    }

    problems: list[str] = []
    known_bugs: list[str] = []

    for nodeid in sorted(expected - set(observed)):
        problems.append(f"inventoried node never executed: {nodeid}")

    for nodeid in sorted(set(observed) - expected):
        problems.append(
            f"node executed but not in the {args.partition} partition: {nodeid}"
        )

    for nodeid in sorted(expected & set(observed)):
        node = observed[nodeid]
        if node["terminal_count"] > 1:
            problems.append(
                f"node executed {node['terminal_count']} times (expected once): {nodeid}"
            )
        outcomes = node["outcomes"]
        if outcomes.get("failed"):
            problems.append(f"node failed: {nodeid}")
        if outcomes.get("skipped"):
            if _is_tracked_known_bug(node):
                # A strict xfail tied to an issue card still RUNS every time and
                # turns red (XPASS strict → failed) the moment the bug is fixed —
                # the `issue` marker's "paired with xfail until the fix lands"
                # contract. It is visible, not an accepted-red baseline.
                known_bugs.append(f"{nodeid} ({', '.join(node['issues'])})")
                continue
            # Anything else — a plain skip, a non-strict xfail, an imperative
            # pytest.xfail(), or a strict xfail with no issue card — is an
            # accepted-red baseline inside a mandatory partition.
            reason = node.get("skip_reason") or "no reason recorded"
            problems.append(
                f"node skipped inside the mandatory {args.partition} partition: "
                f"{nodeid} ({reason})"
            )

    print(
        f"{args.partition}: expected {len(expected)}, observed {len(observed)}, "
        f"{len(problems)} problem(s), {len(known_bugs)} tracked known bug(s)"
    )
    for known in known_bugs:
        print(f"::notice::known bug (strict xfail, issue-linked): {known}")

    if problems:
        for problem in problems[:200]:
            print(f"::error::{problem}")
        if len(problems) > 200:
            print(f"::error::... and {len(problems) - 200} more")
        return 1

    print(f"Every {args.partition} node executed exactly once and passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI."""
    parser = argparse.ArgumentParser(prog="tools.ci.inventory_cli")
    sub = parser.add_subparsers(dest="command")

    parser.add_argument("--tests-dir", default="tests")
    parser.add_argument("--evaluation-sha", default="")
    parser.add_argument("--out", default="backend-inventory.json")
    parser.set_defaults(func=cmd_build)

    verify = sub.add_parser("verify-execution")
    verify.add_argument("--inventory", required=True)
    verify.add_argument("--execution", required=True)
    verify.add_argument(
        "--partition", required=True, choices=["offline", "postgres", "live"]
    )
    verify.set_defaults(func=cmd_verify_execution)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
