"""
Test Inventory and Partition Management for CI Pipeline.

Establishes authoritative backend test inventory with canonical collection,
partition assignment (offline, PostgreSQL, live-only), and validation of
exhaustive/disjoint ownership.

Requirements: 2.2, 2.3, 2.4, 2.11, 2.12, 3.1, 3.2, 3.4, 3.5, 3.6, 3.7
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Union

import pytest


class Partition(str, Enum):
    """Partition classifications for test execution."""

    OFFLINE = "offline"
    """No provider credentials, no live calls, deterministic fakes injected."""

    POSTGRES = "postgres"
    """Requires PostgreSQL service; real isolated database provided."""

    LIVE_ONLY = "live_only"
    """Live provider or external service required; outside mandatory universe."""


# Backwards compatibility alias
TestPartition = Partition


@dataclass(frozen=True)
class TestNode:
    """Atomic test identity with partition and marker information."""

    node_id: str
    """Unique canonical pytest node ID (e.g., 'tests/agents/test_x.py::test_y[param]')."""

    file_path: str
    """Relative file path."""

    test_name: str
    """Function or method name."""

    parameters: str
    """Stringified parameter values or empty string."""

    partition: Partition
    """Assigned partition: offline, postgres, or live_only."""

    markers: list[str] = field(default_factory=list)
    """Marker names present on this node (e.g., ['property', 'slow'])."""

    is_parametrized: bool = False
    """True if this is a parametrized case."""

    suite_classification: str = ""
    """Suite tag: 'characterization', 'kernel', 'banned_pattern', 'workflow_contract', 'property', etc."""


@dataclass
class PartitionInventory:
    """Complete test inventory with partition assignment proof."""

    evaluation_sha: str
    """Exact 40-character commit SHA."""

    offline_tests: list[TestNode] = field(default_factory=list)
    """Offline partition nodes."""

    postgres_tests: list[TestNode] = field(default_factory=list)
    """PostgreSQL partition nodes."""

    live_only_tests: list[TestNode] = field(default_factory=list)
    """Live-only (outside mandatory) nodes."""

    mandatory_presence: dict[str, list[str]] = field(default_factory=dict)
    """
    Mandatory suite classifications and their discovered node counts.
    Keys: 'characterization', 'kernel', 'banned_pattern', 'workflow_contract', 'property', 'root', 'ci'
    Values: List of discovered node IDs in each classification.
    """

    collection_errors: list[str] = field(default_factory=list)
    """Any errors during collection."""

    deselection_anomalies: list[str] = field(default_factory=list)
    """Tests that were deselected unexpectedly."""

    duplicate_node_ids: list[str] = field(default_factory=list)
    """Node IDs discovered more than once."""

    unowned_tracked_files: list[str] = field(default_factory=list)
    """Tracked test-like files without explicit ownership."""

    inventory_digest: str = ""
    """SHA-256 digest of the complete inventory (computed on serialization)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "evaluation_sha": self.evaluation_sha,
            "offline_count": len(self.offline_tests),
            "postgres_count": len(self.postgres_tests),
            "live_only_count": len(self.live_only_tests),
            "mandatory_presence": self.mandatory_presence,
            "collection_errors": self.collection_errors,
            "deselection_anomalies": self.deselection_anomalies,
            "duplicate_node_ids": self.duplicate_node_ids,
            "unowned_tracked_files": self.unowned_tracked_files,
            "inventory_digest": self.inventory_digest,
        }

    def compute_digest(self) -> str:
        """Compute SHA-256 digest of canonical inventory."""
        # Build canonical representation: sorted node IDs per partition
        canonical_parts = [
            self.evaluation_sha,
            json.dumps(sorted([n.node_id for n in self.offline_tests])),
            json.dumps(sorted([n.node_id for n in self.postgres_tests])),
            json.dumps(sorted([n.node_id for n in self.live_only_tests])),
            json.dumps(self.mandatory_presence, sort_keys=True),
        ]
        canonical = "|".join(canonical_parts).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        object.__setattr__(self, "inventory_digest", digest)
        return digest


class InventoryCollector:
    """Collects pytest items and assigns partitions."""

    def __init__(self, evaluation_sha: str = "") -> None:
        self.evaluation_sha = evaluation_sha
        self.offline_tests: list[TestNode] = []
        self.postgres_tests: list[TestNode] = []
        self.live_only_tests: list[TestNode] = []
        self.collection_errors: list[str] = []
        self.deselection_anomalies: list[str] = []
        self.duplicate_node_ids: set[str] = set()
        self.seen_node_ids: set[str] = set()
        self.mandatory_presence: dict[str, list[str]] = {
            "characterization": [],
            "kernel": [],
            "banned_pattern": [],
            "workflow_contract": [],
            "property": [],
            "root": [],
            "ci": [],
        }

    def add_item(self, item: Union[pytest.Item, Any]) -> None:
        """Add a collected pytest item to the inventory."""
        node_id = item.nodeid

        # Handle fspath safely for both pytest.Item and mock objects
        try:
            if hasattr(item, "fspath") and item.fspath:
                fspath_str = str(item.fspath)
                if fspath_str and fspath_str != "":
                    file_path = str(Path(fspath_str).relative_to(Path.cwd()))
                else:
                    file_path = "unknown"
            else:
                file_path = "unknown"
        except (ValueError, TypeError):
            file_path = "unknown"

        # Detect duplicates
        if node_id in self.seen_node_ids:
            self.duplicate_node_ids.add(node_id)
            return
        self.seen_node_ids.add(node_id)

        # Extract test name and parameters
        test_name = item.name.split("[")[0] if "[" in item.name else item.name
        parameters = "[" + item.name.split("[", 1)[1] if "[" in item.name else ""

        # Determine partition from markers
        markers = [m.name for m in item.iter_markers()]
        partition = self._determine_partition(markers, item)

        # Classify into mandatory suites
        suite_classification = self._classify_suite(file_path, test_name)

        node = TestNode(
            node_id=node_id,
            file_path=file_path,
            test_name=test_name,
            parameters=parameters,
            partition=partition,
            markers=markers,
            is_parametrized="[" in item.name,
            suite_classification=suite_classification,
        )

        # Assign to appropriate partition list
        if partition == Partition.OFFLINE:
            self.offline_tests.append(node)
        elif partition == Partition.POSTGRES:
            self.postgres_tests.append(node)
        else:
            self.live_only_tests.append(node)

        # Track mandatory presence
        if suite_classification:
            self.mandatory_presence[suite_classification].append(node_id)

    def _determine_partition(
        self, markers: list[str], item: Union[pytest.Item, Any]
    ) -> Partition:
        """Determine test partition from markers."""
        # Check for explicit markers
        if "offline" in markers or "requires_offline" in markers:
            return Partition.OFFLINE
        if "postgres" in markers or "requires_postgres" in markers:
            return Partition.POSTGRES
        if (
            "live" in markers
            or "requires_api_key" in markers
            or "requires_live" in markers
        ):
            return Partition.LIVE_ONLY

        # Default to offline for unit/component tests (most tests)
        # Only classify as live if explicitly marked or in live directory
        try:
            if hasattr(item, "fspath") and item.fspath:
                fspath_str = str(item.fspath)
                if fspath_str and "live" in fspath_str.lower():
                    return Partition.LIVE_ONLY
        except (AttributeError, ValueError):
            pass

        # Default: offline
        return Partition.OFFLINE

    def _classify_suite(self, file_path: str, test_name: str) -> str:
        """Classify test into a mandatory suite category."""
        path_lower = file_path.lower()

        if "characterization" in path_lower:
            return "characterization"
        if "kernel" in path_lower or "banned_pattern" in path_lower:
            return "kernel"
        if "banned_pattern" in path_lower:
            return "banned_pattern"
        if "workflow" in path_lower and "contract" in path_lower:
            return "workflow_contract"
        if "test_" in path_lower and path_lower.startswith("tests/ci/"):
            return "ci"
        if path_lower.startswith("tests/") and "/" not in path_lower.split("tests/")[1]:
            return "root"
        if "property" in test_name.lower() or "property" in path_lower:
            return "property"

        return ""

    def build_inventory(self) -> PartitionInventory:
        """Build complete inventory."""
        inventory = PartitionInventory(
            evaluation_sha=self.evaluation_sha,
            offline_tests=self.offline_tests,
            postgres_tests=self.postgres_tests,
            live_only_tests=self.live_only_tests,
            mandatory_presence=self.mandatory_presence,
            collection_errors=self.collection_errors,
            deselection_anomalies=self.deselection_anomalies,
            duplicate_node_ids=sorted(self.duplicate_node_ids),
        )
        inventory.compute_digest()
        return inventory


def validate_inventory(inventory: PartitionInventory) -> list[str]:
    """Validate inventory for correctness properties."""
    errors: list[str] = []

    # Check for disjointness
    offline_ids = {n.node_id for n in inventory.offline_tests}
    postgres_ids = {n.node_id for n in inventory.postgres_tests}
    live_ids = {n.node_id for n in inventory.live_only_tests}

    overlap_offline_postgres = offline_ids & postgres_ids
    if overlap_offline_postgres:
        errors.append(
            f"Offline/PostgreSQL partition overlap: {overlap_offline_postgres}"
        )

    overlap_offline_live = offline_ids & live_ids
    if overlap_offline_live:
        errors.append(f"Offline/live partition overlap: {overlap_offline_live}")

    overlap_postgres_live = postgres_ids & live_ids
    if overlap_postgres_live:
        errors.append(f"PostgreSQL/live partition overlap: {overlap_postgres_live}")

    # Check for mandatory suites
    mandatory_suites = [
        "characterization",
        "kernel",
        "banned_pattern",
        "workflow_contract",
        "property",
    ]
    for suite in mandatory_suites:
        if suite not in inventory.mandatory_presence:
            errors.append(f"Missing mandatory suite classification: {suite}")
        elif not inventory.mandatory_presence[suite]:
            errors.append(f"Mandatory suite has no tests: {suite}")

    # Check for collection errors
    if inventory.collection_errors:
        errors.extend(inventory.collection_errors)

    # Check for duplicates
    if inventory.duplicate_node_ids:
        errors.append(f"Duplicate node IDs found: {inventory.duplicate_node_ids}")

    # Check for deselection anomalies
    if inventory.deselection_anomalies:
        errors.extend(inventory.deselection_anomalies)

    return errors


@pytest.hookimpl(tryfirst=True)
def pytest_collection_finish(session: pytest.Session) -> None:
    """
    Pytest hook: after collection, build and validate inventory.

    This hook runs after collection is complete and allows us to build
    the canonical inventory and optionally fail on validation errors.
    """
    # Store inventory on session for access in tests
    collector = InventoryCollector()

    # Collect all items
    for item in session.items:
        collector.add_item(item)

    inventory = collector.build_inventory()
    session.inventory = inventory

    # Validation is optional here; tests can check it explicitly
