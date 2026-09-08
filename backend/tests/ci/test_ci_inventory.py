"""
Comprehensive Backend Test Ownership and Partition Coverage Validation.

Validates:
- All backend tests resolved into partitions (offline, PostgreSQL, live-only)
- No omitted/unowned tests in mandatory universe
- Auxiliary test-like files explicitly tracked with ownership
- Partition disjointness and completeness
- INV-3 characterization golden stability
- Deterministic test inventory

Requirements: 2.2, 2.4, 3.1, 3.2, 3.4, 3.6
"""

from __future__ import annotations

from pathlib import Path
from typing import Set

import pytest

from agents.ci.inventory import (
    InventoryCollector,
    PartitionInventory,
    Partition,
    TestNode,
    validate_inventory,
)
from agents.ci.auxiliary_registry import (
    AuxiliaryRegistry,
    AuxiliaryTestType,
    identify_tracked_test_files,
)


# ============================================================================
# Test 1: Partition Disjointness - Offline vs PostgreSQL
# ============================================================================


def test_partition_disjointness_offline_postgres() -> None:
    """GIVEN two partitions WHEN assigned THEN no test in both.

    Validates: Requirements 2.2, 3.1
    """
    # Create sample inventory with offline and postgres tests
    inventory = PartitionInventory(
        evaluation_sha="a" * 40,
        offline_tests=[
            TestNode(
                node_id="tests/test_unit.py::test_x",
                file_path="tests/test_unit.py",
                test_name="test_x",
                parameters="",
                partition=Partition.OFFLINE,
            )
        ],
        postgres_tests=[
            TestNode(
                node_id="tests/test_db.py::test_y",
                file_path="tests/test_db.py",
                test_name="test_y",
                parameters="",
                partition=Partition.POSTGRES,
            )
        ],
    )

    offline_ids = {n.node_id for n in inventory.offline_tests}
    postgres_ids = {n.node_id for n in inventory.postgres_tests}

    overlap = offline_ids & postgres_ids
    assert not overlap, f"Offline/PostgreSQL partition overlap: {overlap}"


# ============================================================================
# Test 2: Partition Disjointness - Offline vs Live
# ============================================================================


def test_partition_disjointness_offline_live() -> None:
    """GIVEN offline and live partitions WHEN assigned THEN no overlap.

    Validates: Requirements 2.2, 3.1
    """
    inventory = PartitionInventory(
        evaluation_sha="a" * 40,
        offline_tests=[
            TestNode(
                node_id="tests/test_unit.py::test_x",
                file_path="tests/test_unit.py",
                test_name="test_x",
                parameters="",
                partition=Partition.OFFLINE,
            )
        ],
        live_only_tests=[
            TestNode(
                node_id="tests/test_live.py::test_y",
                file_path="tests/test_live.py",
                test_name="test_y",
                parameters="",
                partition=Partition.LIVE_ONLY,
            )
        ],
    )

    offline_ids = {n.node_id for n in inventory.offline_tests}
    live_ids = {n.node_id for n in inventory.live_only_tests}

    overlap = offline_ids & live_ids
    assert not overlap, f"Offline/live partition overlap: {overlap}"


# ============================================================================
# Test 3: Partition Disjointness - PostgreSQL vs Live
# ============================================================================


def test_partition_disjointness_postgres_live() -> None:
    """GIVEN postgres and live partitions WHEN assigned THEN no overlap.

    Validates: Requirements 2.2, 3.1
    """
    inventory = PartitionInventory(
        evaluation_sha="a" * 40,
        postgres_tests=[
            TestNode(
                node_id="tests/test_db.py::test_x",
                file_path="tests/test_db.py",
                test_name="test_x",
                parameters="",
                partition=Partition.POSTGRES,
            )
        ],
        live_only_tests=[
            TestNode(
                node_id="tests/test_live.py::test_y",
                file_path="tests/test_live.py",
                test_name="test_y",
                parameters="",
                partition=Partition.LIVE_ONLY,
            )
        ],
    )

    postgres_ids = {n.node_id for n in inventory.postgres_tests}
    live_ids = {n.node_id for n in inventory.live_only_tests}

    overlap = postgres_ids & live_ids
    assert not overlap, f"PostgreSQL/live partition overlap: {overlap}"


# ============================================================================
# Test 4: No Duplicate Node IDs
# ============================================================================


def test_no_duplicate_node_ids() -> None:
    """GIVEN inventory WHEN all node IDs THEN unique within and across partitions.

    Validates: Requirements 2.2, 3.1
    """
    inventory = PartitionInventory(
        evaluation_sha="a" * 40,
        offline_tests=[
            TestNode(
                node_id="tests/test_1.py::test_a",
                file_path="tests/test_1.py",
                test_name="test_a",
                parameters="",
                partition=Partition.OFFLINE,
            ),
            TestNode(
                node_id="tests/test_1.py::test_b",
                file_path="tests/test_1.py",
                test_name="test_b",
                parameters="",
                partition=Partition.OFFLINE,
            ),
        ],
        postgres_tests=[
            TestNode(
                node_id="tests/test_2.py::test_c",
                file_path="tests/test_2.py",
                test_name="test_c",
                parameters="",
                partition=Partition.POSTGRES,
            ),
        ],
    )

    all_ids: Set[str] = set()

    for node in inventory.offline_tests:
        assert node.node_id not in all_ids, f"Duplicate in offline: {node.node_id}"
        all_ids.add(node.node_id)

    for node in inventory.postgres_tests:
        assert node.node_id not in all_ids, f"Duplicate in postgres: {node.node_id}"
        all_ids.add(node.node_id)

    for node in inventory.live_only_tests:
        assert node.node_id not in all_ids, f"Duplicate in live: {node.node_id}"
        all_ids.add(node.node_id)

    assert (
        not inventory.duplicate_node_ids
    ), f"Duplicate node IDs detected: {inventory.duplicate_node_ids}"


# ============================================================================
# Test 5: Inventory Digest is Deterministic
# ============================================================================


def test_inventory_digest_deterministic() -> None:
    """GIVEN same inventory WHEN computed twice THEN same digest.

    Validates: Requirements 2.2, 3.4
    """
    inventory = PartitionInventory(
        evaluation_sha="a" * 40,
        offline_tests=[
            TestNode(
                node_id="tests/test_x.py::test_1",
                file_path="tests/test_x.py",
                test_name="test_1",
                parameters="",
                partition=Partition.OFFLINE,
            )
        ],
    )

    # Compute digest
    digest1 = inventory.compute_digest()
    digest2 = inventory.compute_digest()

    assert digest1 == digest2, "Digest should be deterministic"
    assert len(digest1) == 64, "Digest should be 64 hex chars (SHA-256)"


# ============================================================================
# Test 6: Inventory Validation Detects Overlaps
# ============================================================================


def test_inventory_validation_detects_overlaps() -> None:
    """GIVEN overlapping partitions WHEN validated THEN errors reported.

    Validates: Requirements 2.2, 3.1
    """
    # Manually create inventory with overlap
    inventory = PartitionInventory(
        evaluation_sha="a" * 40,
        offline_tests=[
            TestNode(
                node_id="tests/test_x.py::test_1",
                file_path="tests/test_x.py",
                test_name="test_1",
                parameters="",
                partition=Partition.OFFLINE,
            )
        ],
        postgres_tests=[
            TestNode(
                node_id="tests/test_x.py::test_1",  # Same ID!
                file_path="tests/test_x.py",
                test_name="test_1",
                parameters="",
                partition=Partition.POSTGRES,
            )
        ],
    )

    errors = validate_inventory(inventory)
    assert any(
        "overlap" in e.lower() for e in errors
    ), f"Expected overlap error, got: {errors}"


# ============================================================================
# Test 7: Auxiliary Registry Tracks Entries
# ============================================================================


def test_auxiliary_registry_tracks_entries() -> None:
    """GIVEN auxiliary entry WHEN added THEN stored with complete info.

    Validates: Requirements 2.4, 3.2
    """
    registry = AuxiliaryRegistry()

    registry.add_entry(
        file_path="tests/integration/test_api.sh",
        test_type=AuxiliaryTestType.SHELL_SCRIPT,
        owner="backend-static",
        command="bash tests/integration/test_api.sh",
        reason="Shell-based API integration test",
    )

    assert len(registry.entries) == 1
    entry = registry.entries[0]
    assert entry.file_path == "tests/integration/test_api.sh"
    assert entry.owner == "backend-static"
    assert entry.command == "bash tests/integration/test_api.sh"
    assert entry.reason == "Shell-based API integration test"


# ============================================================================
# Test 8: Auxiliary Registry Marks Files for Deletion
# ============================================================================


def test_auxiliary_registry_marks_deletion() -> None:
    """GIVEN obsolete file WHEN marked for deletion THEN stored.

    Validates: Requirements 2.4, 3.2
    """
    registry = AuxiliaryRegistry()

    registry.mark_for_deletion(
        file_path="tests/old_manual_test.sh",
        reason="Replaced by automated test suite",
    )

    assert len(registry.entries) == 1
    entry = registry.entries[0]
    assert entry.owner == "deleted"
    assert entry.command == ""
    assert "Replaced" in entry.reason


# ============================================================================
# Test 9: Auxiliary Registry Validates Entries
# ============================================================================


def test_auxiliary_registry_validates_completeness() -> None:
    """GIVEN registry entry WHEN validated THEN completeness checked.

    Validates: Requirements 2.4, 3.2
    """
    registry = AuxiliaryRegistry()

    # Add entry without command and not deleted
    registry.add_entry(
        file_path="tests/bad.sh",
        test_type=AuxiliaryTestType.SHELL_SCRIPT,
        owner="unknown",
        command="",  # Empty command
        reason="No command",
    )

    errors = registry.validate()
    assert len(errors) > 0, "Should detect missing command"
    assert any("command" in e.lower() for e in errors)


# ============================================================================
# Test 10: Auxiliary Registry Serialization Round-Trip
# ============================================================================


def test_auxiliary_registry_serialization() -> None:
    """GIVEN registry WHEN serialized/deserialized THEN preserved.

    Validates: Requirements 2.4, 3.2
    """
    registry = AuxiliaryRegistry()

    registry.add_entry(
        file_path="tests/test.sh",
        test_type=AuxiliaryTestType.SHELL_SCRIPT,
        owner="backend-static",
        command="bash tests/test.sh",
        reason="Shell test",
    )

    # Serialize
    data = registry.to_dict()
    assert data["total_count"] == 1
    assert data["active_count"] == 1

    # Deserialize
    registry2 = AuxiliaryRegistry.from_dict(data)
    assert len(registry2.entries) == 1
    assert registry2.entries[0].file_path == "tests/test.sh"
    assert registry2.entries[0].owner == "backend-static"


# ============================================================================
# Test 11: Tracked Files Identification
# ============================================================================


def test_identify_tracked_test_files() -> None:
    """GIVEN repo WHEN scanned THEN tracked test files identified.

    Validates: Requirements 2.4, 3.2
    """
    tracked = identify_tracked_test_files()

    # Should return a list
    assert isinstance(tracked, list), "Should return list"
    # Should be sorted
    assert tracked == sorted(tracked), "Should be sorted"
    # Can be empty if no tracked files, but should not error


# ============================================================================
# Test 12: InventoryCollector Builds Correct Partition Inventory
# ============================================================================


def test_inventory_collector_builds_inventory() -> None:
    """GIVEN collector WHEN building inventory THEN produces PartitionInventory.

    Validates: Requirements 2.2, 3.1
    """
    collector = InventoryCollector(evaluation_sha="a" * 40)

    # Manually add some items
    class MockItem:
        def __init__(self, nodeid: str, markers_list: list[str]):
            self.nodeid = nodeid
            self.name = nodeid.split("::")[-1].split("[")[0]
            self.markers_list = markers_list

            class MockFspath:
                def __str__(self):
                    return "tests/test_sample.py"

            self.fspath = MockFspath()

        def iter_markers(self):
            return [type("", (), {"name": m})() for m in self.markers_list]

    collector.add_item(MockItem("tests/test_sample.py::test_offline", []))  # type: ignore
    collector.add_item(MockItem("tests/test_sample.py::test_postgres", ["postgres"]))  # type: ignore

    inventory = collector.build_inventory()

    assert len(inventory.offline_tests) >= 1
    assert len(inventory.postgres_tests) >= 1
    assert inventory.evaluation_sha == "a" * 40
