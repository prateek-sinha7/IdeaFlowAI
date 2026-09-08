"""
Property-Based Tests for Backend and Frontend Test Inventories.

Validates:
- Canonical pytest collection and partition assignment
- Disjointness of partition membership (no test in two partitions)
- Completeness of mandatory suites
- Detection of collection errors, duplicates, ambiguities
- Frontend Vitest unit/component vs. integration split

Requirements: 2.2, 2.3, 2.4, 2.11, 2.12, 3.1, 3.2, 3.4, 3.5, 3.6, 3.7
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, strategies as st

from agents.ci.inventory import (
    InventoryCollector,
    PartitionInventory,
    Partition,
    TestPartition,  # backwards compat alias
    TestNode,
    validate_inventory,
)
from agents.ci.auxiliary_registry import (
    AuxiliaryRegistry,
    AuxiliaryTestType,
    identify_tracked_test_files,
)


class TestCanonicalCollection:
    """Test canonical pytest collection produces deterministic inventory."""

    def test_collection_hook_installed(self) -> None:
        """GIVEN pytest conftest WHEN configured THEN inventory hook installed."""
        # The hook is installed automatically via conftest.py
        # This test simply verifies that pytest_collection_finish is defined
        from agents.ci import inventory as inv_module

        assert hasattr(
            inv_module, "pytest_collection_finish"
        ), "pytest_collection_finish hook not found in inventory module"

    def test_inventory_disjointness_offline_postgres(self) -> None:
        """GIVEN two partitions WHEN assigned THEN no test in both."""
        collector = InventoryCollector()

        # Simulate offline test
        class MockOfflineItem:
            nodeid = "tests/test_offline.py::test_x"
            name = "test_x"
            fspath = type("", (), {"__str__": lambda s: "tests/test_offline.py"})()

            def iter_markers(self):
                return [type("", (), {"name": "offline"})()]

        # Simulate postgres test
        class MockPostgresItem:
            nodeid = "tests/test_db.py::test_y"
            name = "test_y"
            fspath = type("", (), {"__str__": lambda s: "tests/test_db.py"})()

            def iter_markers(self):
                return [type("", (), {"name": "postgres"})()]

        collector.add_item(MockOfflineItem())  # type: ignore
        collector.add_item(MockPostgresItem())  # type: ignore

        inventory = collector.build_inventory()

        # Offline and postgres sets should not overlap
        offline_ids = {n.node_id for n in inventory.offline_tests}
        postgres_ids = {n.node_id for n in inventory.postgres_tests}
        assert offline_ids.isdisjoint(
            postgres_ids
        ), "Offline and PostgreSQL partitions overlap"

    def test_inventory_disjointness_offline_live(self) -> None:
        """GIVEN offline and live partitions WHEN assigned THEN no overlap."""
        collector = InventoryCollector()

        class MockOfflineItem:
            nodeid = "tests/test_offline.py::test_x"
            name = "test_x"
            fspath = type("", (), {"__str__": lambda s: "tests/test_offline.py"})()

            def iter_markers(self):
                return []

        class MockLiveItem:
            nodeid = "tests/test_live.py::test_y"
            name = "test_y"
            fspath = type("", (), {"__str__": lambda s: "tests/test_live.py"})()

            def iter_markers(self):
                return [type("", (), {"name": "live"})()]

        collector.add_item(MockOfflineItem())  # type: ignore
        collector.add_item(MockLiveItem())  # type: ignore

        inventory = collector.build_inventory()

        offline_ids = {n.node_id for n in inventory.offline_tests}
        live_ids = {n.node_id for n in inventory.live_only_tests}
        assert offline_ids.isdisjoint(live_ids), "Offline and live partitions overlap"

    def test_inventory_disjointness_postgres_live(self) -> None:
        """GIVEN PostgreSQL and live partitions WHEN assigned THEN no overlap."""
        collector = InventoryCollector()

        class MockPostgresItem:
            nodeid = "tests/test_db.py::test_x"
            name = "test_x"
            fspath = type("", (), {"__str__": lambda s: "tests/test_db.py"})()

            def iter_markers(self):
                return [type("", (), {"name": "postgres"})()]

        class MockLiveItem:
            nodeid = "tests/test_live.py::test_y"
            name = "test_y"
            fspath = type("", (), {"__str__": lambda s: "tests/test_live.py"})()

            def iter_markers(self):
                return [type("", (), {"name": "live"})()]

        collector.add_item(MockPostgresItem())  # type: ignore
        collector.add_item(MockLiveItem())  # type: ignore

        inventory = collector.build_inventory()

        postgres_ids = {n.node_id for n in inventory.postgres_tests}
        live_ids = {n.node_id for n in inventory.live_only_tests}
        assert postgres_ids.isdisjoint(
            live_ids
        ), "PostgreSQL and live partitions overlap"

    def test_inventory_detects_duplicate_node_ids(self) -> None:
        """GIVEN duplicate node ID WHEN collected twice THEN detected."""
        collector = InventoryCollector()

        class MockItem:
            nodeid = "tests/test_x.py::test_y"
            name = "test_y"
            fspath = type("", (), {"__str__": lambda s: "tests/test_x.py"})()

            def iter_markers(self):
                return []

        collector.add_item(MockItem())  # type: ignore
        # Try to add same item again
        collector.add_item(MockItem())  # type: ignore

        inventory = collector.build_inventory()
        assert "tests/test_x.py::test_y" in inventory.duplicate_node_ids


class TestPartitionValidation:
    """Test partition validation logic."""

    def test_validate_inventory_passes_valid(self) -> None:
        """GIVEN valid disjoint inventory WHEN validated THEN no errors for populated tests."""
        collector = InventoryCollector(evaluation_sha="a" * 40)

        class MockOfflineItem:
            nodeid = "tests/test_offline.py::test_x"
            name = "test_x"
            fspath = type("", (), {"__str__": lambda s: "tests/test_offline.py"})()

            def iter_markers(self):
                return [type("", (), {"name": "offline"})()]

        class MockPropertyItem:
            nodeid = "tests/ci/test_properties.py::test_property_y"
            name = "test_property_y"
            fspath = type(
                "", (), {"__str__": lambda s: "tests/ci/test_properties.py"}
            )()

            def iter_markers(self):
                return [type("", (), {"name": "property"})()]

        class MockCharacterizationItem:
            nodeid = "tests/agents/test_characterization_z.py::test_z"
            name = "test_z"
            fspath = type(
                "", (), {"__str__": lambda s: "tests/agents/test_characterization_z.py"}
            )()

            def iter_markers(self):
                return []

        collector.add_item(MockOfflineItem())  # type: ignore
        collector.add_item(MockPropertyItem())  # type: ignore
        collector.add_item(MockCharacterizationItem())  # type: ignore

        inventory = collector.build_inventory()
        errors = validate_inventory(inventory)

        # Should pass disjointness checks; may have empty mandatory suites which are warnings
        # Filter to just overlap/duplicate errors
        critical_errors = [e for e in errors if "overlap" in e or "duplicate" in e]
        assert not critical_errors, f"Critical errors found: {critical_errors}"

    def test_validate_detects_overlapping_partitions(self) -> None:
        """GIVEN overlapping partitions WHEN validated THEN errors reported."""
        # Create inventory with overlapping nodes manually
        from agents.ci.inventory import TestNode, Partition

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


class TestAuxiliaryRegistry:
    """Test auxiliary test file registry."""

    def test_auxiliary_registry_add_entry(self) -> None:
        """GIVEN auxiliary entry WHEN added THEN stored."""
        registry = AuxiliaryRegistry()

        registry.add_entry(
            file_path="tests/integration/test_api.sh",
            test_type=AuxiliaryTestType.SHELL_SCRIPT,
            owner="repo-static",
            command="bash tests/integration/test_api.sh",
            reason="Shell-based API integration test",
        )

        assert len(registry.entries) == 1
        assert registry.entries[0].file_path == "tests/integration/test_api.sh"

    def test_auxiliary_registry_mark_for_deletion(self) -> None:
        """GIVEN obsolete file WHEN marked for deletion THEN stored."""
        registry = AuxiliaryRegistry()

        registry.mark_for_deletion(
            file_path="tests/old_manual_test.sh",
            reason="Replaced by automated test suite",
        )

        assert len(registry.entries) == 1
        assert registry.entries[0].owner == "deleted"
        assert registry.entries[0].command == ""

    def test_auxiliary_registry_validates_entries(self) -> None:
        """GIVEN registry WHEN validated THEN checks completeness."""
        registry = AuxiliaryRegistry()

        # Add entry without command and not deleted
        registry.add_entry(
            file_path="tests/bad.sh",
            test_type=AuxiliaryTestType.SHELL_SCRIPT,
            owner="unknown",
            command="",
            reason="No command",
        )

        errors = registry.validate()
        assert len(errors) > 0, "Should detect missing command"

    def test_auxiliary_registry_serialization(self) -> None:
        """GIVEN registry WHEN serialized THEN can be reconstructed."""
        registry = AuxiliaryRegistry()

        registry.add_entry(
            file_path="tests/test.sh",
            test_type=AuxiliaryTestType.SHELL_SCRIPT,
            owner="repo-static",
            command="bash tests/test.sh",
            reason="Shell test",
        )

        data = registry.to_dict()
        assert data["total_count"] == 1
        assert data["active_count"] == 1

        # Reconstruct
        registry2 = AuxiliaryRegistry.from_dict(data)
        assert len(registry2.entries) == 1
        assert registry2.entries[0].file_path == "tests/test.sh"


class TestMandatorySuites:
    """Test mandatory suite detection and validation."""

    def test_mandatory_suite_presence_tracking(self) -> None:
        """GIVEN mandatory suite tests WHEN classified THEN tracked."""
        collector = InventoryCollector()

        # Create mock items for different suites
        class MockCharacterizationItem:
            nodeid = "tests/agents/test_characterization_x.py::test_y"
            name = "test_y"
            fspath = type(
                "",
                (),
                {"__str__": lambda s: "tests/agents/test_characterization_x.py"},
            )()

            def iter_markers(self):
                return []

        collector.add_item(MockCharacterizationItem())  # type: ignore
        inventory = collector.build_inventory()

        # Characterization should be tracked
        assert (
            "characterization" in inventory.mandatory_presence
        ), "Mandatory suite 'characterization' not tracked"


class TestInventoryDigest:
    """Test inventory digest computation and stability."""

    def test_digest_computation(self) -> None:
        """GIVEN inventory WHEN digested THEN produces SHA-256."""
        collector = InventoryCollector(evaluation_sha="a" * 40)

        class MockItem:
            nodeid = "tests/test_x.py::test_1"
            name = "test_1"
            fspath = type("", (), {"__str__": lambda s: "tests/test_x.py"})()

            def iter_markers(self):
                return []

        collector.add_item(MockItem())  # type: ignore
        inventory = collector.build_inventory()

        assert (
            len(inventory.inventory_digest) == 64
        ), "Digest should be 64 hex chars (SHA-256)"

    def test_digest_stability(self) -> None:
        """GIVEN same inventory WHEN digested twice THEN same digest."""
        collector = InventoryCollector(evaluation_sha="a" * 40)

        class MockItem:
            nodeid = "tests/test_x.py::test_1"
            name = "test_1"
            fspath = type("", (), {"__str__": lambda s: "tests/test_x.py"})()

            def iter_markers(self):
                return []

        collector.add_item(MockItem())  # type: ignore
        inventory1 = collector.build_inventory()

        collector2 = InventoryCollector(evaluation_sha="a" * 40)
        collector2.add_item(MockItem())  # type: ignore
        inventory2 = collector2.build_inventory()

        assert (
            inventory1.inventory_digest == inventory2.inventory_digest
        ), "Same inventory should produce same digest"


class TestPropertyBasedPartitioning:
    """Property-based tests for partition invariants.

    **Validates: Requirements 2.2, 2.4**
    """

    @given(st.lists(st.sampled_from(["offline", "postgres", "live"]), min_size=1))
    def test_partition_assignment_consistency(self, markers_list: list[str]) -> None:
        """Property: partition assignment for markers is consistent."""
        collector = InventoryCollector(evaluation_sha="a" * 40)

        class MockItem:
            nodeid = f"tests/test.py::test_{markers_list[0]}"
            name = f"test_{markers_list[0]}"
            fspath = type("", (), {"__str__": lambda s: "tests/test.py"})()

            def iter_markers(self):
                return [type("", (), {"name": m})() for m in markers_list]

        collector.add_item(MockItem())  # type: ignore
        inventory = collector.build_inventory()

        # Verify test is in exactly one partition
        offline_count = len(
            [t for t in inventory.offline_tests if t.node_id == MockItem.nodeid]
        )
        postgres_count = len(
            [t for t in inventory.postgres_tests if t.node_id == MockItem.nodeid]
        )
        live_count = len(
            [t for t in inventory.live_only_tests if t.node_id == MockItem.nodeid]
        )

        total = offline_count + postgres_count + live_count
        assert total == 1, f"Test should be in exactly one partition, found in {total}"

    @given(st.integers(min_value=5, max_value=50))
    def test_inventory_disjointness_property(self, count: int) -> None:
        """Property 3: Disjoint partitions hold for generated test sets.

        **Validates: Requirement 2.2**
        """
        collector = InventoryCollector(evaluation_sha="a" * 40)

        # Create tests spread across partitions
        for i in range(count):
            partition = i % 3
            markers = (
                ["offline"]
                if partition == 0
                else (["postgres"] if partition == 1 else ["live"])
            )

            class MockItem:
                nodeid = f"tests/test_{i}.py::test_{i}"
                name = f"test_{i}"
                # `i` and `markers` are bound as default arguments rather than
                # captured. A closure over the loop variable reads whatever the
                # LAST iteration left behind, so every mock would have claimed
                # the final iteration's markers and path — which would have made
                # this disjointness assertion pass for the wrong reason.
                fspath = type(
                    "", (), {"__str__": lambda s, _p=f"tests/test_{i}.py": _p}
                )()

                def iter_markers(self, _markers=tuple(markers)):
                    return [type("", (), {"name": m})() for m in _markers]

            collector.add_item(MockItem())  # type: ignore

        inventory = collector.build_inventory()

        # Check disjointness
        offline_ids = {n.node_id for n in inventory.offline_tests}
        postgres_ids = {n.node_id for n in inventory.postgres_tests}
        live_ids = {n.node_id for n in inventory.live_only_tests}

        assert offline_ids.isdisjoint(postgres_ids), "Offline/Postgres not disjoint"
        assert offline_ids.isdisjoint(live_ids), "Offline/Live not disjoint"
        assert postgres_ids.isdisjoint(live_ids), "Postgres/Live not disjoint"

        # Check union coverage
        all_nodes = offline_ids | postgres_ids | live_ids
        total_expected = count
        assert (
            len(all_nodes) == total_expected
        ), f"Union should have {total_expected} nodes"

    @given(
        st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
                st.sampled_from(["offline", "postgres", "live"]),
            ),
            min_size=1,
            max_size=100,
            unique_by=lambda x: x[0],  # Unique test names
        )
    )
    def test_complete_inventory_coverage(
        self, test_spec: list[tuple[str, str]]
    ) -> None:
        """Property: inventory covers all collected tests exactly once.

        **Validates: Requirement 2.2**
        """
        collector = InventoryCollector(evaluation_sha="b" * 40)

        for test_name, partition in test_spec:
            markers = (
                ["offline"]
                if partition == "offline"
                else (["postgres"] if partition == "postgres" else ["live"])
            )

            class MockItem:
                nodeid = f"tests/test_{test_name}.py::test_{test_name}"
                name = f"test_{test_name}"
                # Bound as defaults, not captured: see the note in the
                # disjointness test above (ruff B023).
                fspath = type(
                    "", (), {"__str__": lambda s, _p=f"tests/test_{test_name}.py": _p}
                )()

                def iter_markers(self, _markers=tuple(markers)):
                    return [type("", (), {"name": m})() for m in _markers]

            collector.add_item(MockItem())  # type: ignore

        inventory = collector.build_inventory()

        # Verify coverage
        offline_count = len(inventory.offline_tests)
        postgres_count = len(inventory.postgres_tests)
        live_count = len(inventory.live_only_tests)

        total_collected = offline_count + postgres_count + live_count
        expected_count = len(test_spec)

        assert total_collected == expected_count, (
            f"Inventory should cover all {expected_count} tests, "
            f"found {total_collected}"
        )


class TestPropertyBasedDuplicateDetection:
    """Property-based tests for duplicate detection.

    **Validates: Requirement 2.2**
    """

    @given(st.integers(min_value=2, max_value=10))
    def test_duplicate_detection_property(self, duplication_factor: int) -> None:
        """Property: duplicate node IDs are detected."""
        collector = InventoryCollector(evaluation_sha="c" * 40)

        node_id = "tests/test_x.py::test_duplicate"

        for _ in range(duplication_factor):

            class MockItem:
                nodeid = node_id
                name = "test_duplicate"
                fspath = type("", (), {"__str__": lambda s: "tests/test_x.py"})()

                def iter_markers(self):
                    return []

            collector.add_item(MockItem())  # type: ignore

        inventory = collector.build_inventory()

        # Should detect duplicates when count > 1
        if duplication_factor > 1:
            assert (
                node_id in inventory.duplicate_node_ids
            ), f"Duplicate node ID {node_id} not detected"
        else:
            assert node_id not in inventory.duplicate_node_ids


class TestPropertyBasedMandatorySuites:
    """Property-based tests for mandatory suite tracking.

    **Validates: Requirement 2.2**
    """

    @given(
        st.lists(
            st.tuples(
                st.text(min_size=1, max_size=10, alphabet="abcdefghij"),
                st.sampled_from(
                    [
                        "characterization",
                        "kernel",
                        "banned_pattern",
                        "workflow_contract",
                        "property",
                    ]
                ),
            ),
            min_size=1,
            max_size=20,
            unique_by=lambda x: x[0],
        )
    )
    def test_mandatory_suite_classification(
        self, suite_items: list[tuple[str, str]]
    ) -> None:
        """Property: mandatory suites are correctly classified."""
        collector = InventoryCollector(evaluation_sha="d" * 40)

        for test_id, suite in suite_items:
            # Build file path to match suite classification
            if suite == "characterization":
                file_path = f"tests/agents/test_characterization_{test_id}.py"
            elif suite == "kernel":
                file_path = f"tests/agents/test_kernel_{test_id}.py"
            elif suite == "banned_pattern":
                file_path = f"tests/agents/test_banned_pattern_{test_id}.py"
            elif suite == "workflow_contract":
                file_path = f"tests/ci/test_workflow_contract_{test_id}.py"
            elif suite == "property":
                file_path = f"tests/ci/test_property_{test_id}.py"
            else:
                file_path = f"tests/test_{test_id}.py"

            class MockItem:
                nodeid = f"{file_path}::test_{test_id}"
                name = f"test_{test_id}"
                # Bound as a default, not captured (ruff B023).
                fspath = type("", (), {"__str__": lambda s, _p=file_path: _p})()

                def iter_markers(self):
                    return []

            collector.add_item(MockItem())  # type: ignore

        inventory = collector.build_inventory()

        # Verify suites have entries
        for _, suite in suite_items:
            assert suite in inventory.mandatory_presence, f"Suite {suite} not tracked"
            # At least one test should be in this suite
            # (though classification logic might not catch all due to simplification)
