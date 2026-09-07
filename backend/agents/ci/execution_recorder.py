"""
Pytest plugin that records what was collected and what actually executed.

Two problems this solves, both of which the previous CI could not detect.

1. Partition classification. The old inventory job classified a test as
   PostgreSQL-requiring by testing whether the string "postgres" appeared in its
   node ID. Pytest markers never appear in a node ID, so that check was reading
   filenames and test names, while the actual test runs selected by marker
   (`-m "requires_postgres"`). The two disagreed and nothing compared them. This
   plugin reads the real marker set off each collected item.

2. Exactly-once execution. "Every mandatory node ran once" was asserted in prose
   but never measured: the offline job downloaded the inventory, checked its SHA,
   then ignored its contents. This plugin records every terminal outcome by
   canonical node ID so `inventory_cli verify-execution` can compare the two sets
   and fail on an omission, a duplicate, or an unexpected skip.

Enable with `-p agents.ci.execution_recorder` plus one of the two output flags.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pytest

#: Markers that place a node in the credential-gated live partition. A node
#: carrying any of these is excluded from every mandatory partition.
LIVE_MARKERS = frozenset({"live", "requires_api_key"})

#: Markers that place a node in the service-backed PostgreSQL partition.
POSTGRES_MARKERS = frozenset(
    {"requires_postgres", "requires_postgres_populated_migration"}
)


def pytest_addoption(parser: Any) -> None:
    """Register the two output paths this plugin can write."""
    group = parser.getgroup("ci-evidence")
    group.addoption(
        "--inventory-record",
        action="store",
        default=None,
        metavar="PATH",
        help="Write the canonical collected inventory (with markers) to PATH.",
    )
    group.addoption(
        "--execution-record",
        action="store",
        default=None,
        metavar="PATH",
        help="Write the per-node execution record to PATH.",
    )


def _partition_for(marker_names: set[str]) -> str:
    """
    Assign exactly one partition to a node from its marker set.

    Live wins over PostgreSQL so a node marked both is never pulled into a
    mandatory partition by accident; `inventory_cli` reports that combination as
    an ambiguity rather than silently choosing.
    """
    if marker_names & LIVE_MARKERS:
        return "live"
    if marker_names & POSTGRES_MARKERS:
        return "postgres"
    return "offline"


class _Recorder:
    """Accumulates collection and execution facts for one pytest session."""

    def __init__(self, inventory_path: str | None, execution_path: str | None):
        self.inventory_path = inventory_path
        self.execution_path = execution_path
        self.collected: dict[str, dict[str, Any]] = {}
        self.collection_errors: list[str] = []
        #: nodeid -> Counter of phase outcomes, so a node executed twice is
        #: visible rather than collapsing into one entry.
        self.outcomes: dict[str, Counter] = {}
        self.skip_reasons: dict[str, str] = {}

    # -- collection ------------------------------------------------------
    def record_item(self, item: pytest.Item) -> None:
        """Record one collected item and its real marker set."""
        marker_names = {mark.name for mark in item.iter_markers()}
        self.collected[item.nodeid] = {
            "nodeid": item.nodeid,
            "path": str(getattr(item, "path", "") or ""),
            "markers": sorted(marker_names),
            "partition": _partition_for(marker_names),
        }

    def record_collection_error(self, message: str) -> None:
        """Record a collection failure. Any of these invalidates the inventory."""
        self.collection_errors.append(message)

    # -- execution -------------------------------------------------------
    def record_report(self, report: Any) -> None:
        """Record a terminal phase outcome for one node."""
        counter = self.outcomes.setdefault(report.nodeid, Counter())

        if report.when == "call":
            counter[report.outcome] += 1
        elif report.when == "setup" and report.outcome in ("failed", "skipped"):
            # A setup error or a skip during setup means `call` never runs, so
            # this is the node's terminal outcome.
            counter[report.outcome] += 1
        elif report.when == "teardown" and report.outcome == "failed":
            counter["failed"] += 1

        if report.outcome == "skipped":
            reason = ""
            longrepr = getattr(report, "longrepr", None)
            if isinstance(longrepr, tuple) and len(longrepr) == 3:
                reason = str(longrepr[2])
            self.skip_reasons.setdefault(report.nodeid, reason)

    # -- output ----------------------------------------------------------
    def write(self) -> None:
        """Write whichever records were requested."""
        if self.inventory_path:
            self._write_json(
                self.inventory_path,
                {
                    "schema_version": 1,
                    "collection_errors": self.collection_errors,
                    "nodes": [
                        self.collected[nodeid] for nodeid in sorted(self.collected)
                    ],
                },
            )

        if self.execution_path:
            self._write_json(
                self.execution_path,
                {
                    "schema_version": 1,
                    "nodes": [
                        {
                            "nodeid": nodeid,
                            "outcomes": dict(counter),
                            "terminal_count": sum(counter.values()),
                            "skip_reason": self.skip_reasons.get(nodeid),
                        }
                        for nodeid, counter in sorted(self.outcomes.items())
                    ],
                },
            )

    @staticmethod
    def _write_json(path: str, payload: dict[str, Any]) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


_recorder: _Recorder | None = None


def pytest_configure(config: Any) -> None:
    """Create the recorder if either output was requested."""
    global _recorder
    inventory_path = config.getoption("--inventory-record")
    execution_path = config.getoption("--execution-record")
    if inventory_path or execution_path:
        _recorder = _Recorder(inventory_path, execution_path)


def pytest_collection_modifyitems(session: Any, config: Any, items: list) -> None:
    """Record every collected item after selection has been applied."""
    if _recorder is None:
        return
    for item in items:
        _recorder.record_item(item)


def pytest_collectreport(report: Any) -> None:
    """Record a collection error so the inventory cannot silently shrink."""
    if _recorder is None:
        return
    if report.failed:
        _recorder.record_collection_error(str(report.nodeid or report.longrepr))


def pytest_runtest_logreport(report: Any) -> None:
    """Record each phase report for the execution record."""
    if _recorder is None:
        return
    _recorder.record_report(report)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Flush the records. Runs even when the session failed."""
    if _recorder is not None:
        _recorder.write()
