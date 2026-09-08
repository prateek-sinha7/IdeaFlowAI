"""
Auxiliary Test Registry for Non-Pytest Test Files.

Tracks test-like files outside pytest collection (shell scripts, manual checks,
etc.) with explicit ownership, commands, and execution evidence.

Requirements: 2.2, 2.3, 2.4, 3.1, 3.2, 3.4, 3.6
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class AuxiliaryTestType(str, Enum):
    """Classification of auxiliary test files."""

    SHELL_SCRIPT = "shell_script"
    JAVASCRIPT = "javascript"
    MANUAL_INTEGRATION = "manual_integration"
    PLACEHOLDER = "placeholder"


@dataclass(frozen=True)
class AuxiliaryTest:
    """Entry for a non-pytest test file."""

    file_path: str
    """Relative path to test-like file."""

    test_type: AuxiliaryTestType
    """Type of test file."""

    owner: str
    """CI job or named owner responsible for this test."""

    command: str
    """Exact command to execute the test; empty string means file should be deleted."""

    reason: str
    """Rationale for this classification or deletion decision."""

    alternate_owner: Optional[str] = None
    """If deleted/moved, where this test moved to or was replaced by."""

    created_at: str = ""
    """ISO timestamp of creation/decision."""

    expiry_date: Optional[str] = None
    """If temporary, when this entry expires."""


@dataclass
class AuxiliaryRegistry:
    """Registry of all non-pytest test files."""

    entries: list[AuxiliaryTest] = field(default_factory=list)
    """All registered auxiliary tests."""

    def add_entry(
        self,
        file_path: str,
        test_type: AuxiliaryTestType,
        owner: str,
        command: str,
        reason: str,
        alternate_owner: Optional[str] = None,
    ) -> None:
        """Add or update an auxiliary test entry."""
        # Remove existing entry if present
        self.entries = [e for e in self.entries if e.file_path != file_path]

        # Add new entry
        entry = AuxiliaryTest(
            file_path=file_path,
            test_type=test_type,
            owner=owner,
            command=command,
            reason=reason,
            alternate_owner=alternate_owner,
        )
        self.entries.append(entry)

    def mark_for_deletion(
        self,
        file_path: str,
        reason: str,
        alternate_owner: Optional[str] = None,
    ) -> None:
        """Mark a file for deletion with a reason."""
        self.add_entry(
            file_path=file_path,
            test_type=AuxiliaryTestType.PLACEHOLDER,
            owner="deleted",
            command="",
            reason=reason,
            alternate_owner=alternate_owner,
        )

    def validate(self) -> list[str]:
        """Validate registry for consistency."""
        errors: list[str] = []

        for entry in self.entries:
            # Every entry must have owner and command (unless deleted)
            if entry.command == "" and entry.owner != "deleted":
                errors.append(
                    f"{entry.file_path}: no command specified and not marked for deletion"
                )
            if not entry.owner:
                errors.append(f"{entry.file_path}: missing owner")

            # Deleted entries should have a reason
            if entry.owner == "deleted" and not entry.reason:
                errors.append(f"{entry.file_path}: deletion with no reason")

            # If alternate owner exists, command should be empty or describe migration
            if (
                entry.alternate_owner
                and entry.command
                and "moved to" not in entry.reason.lower()
            ):
                errors.append(
                    f"{entry.file_path}: has both command and alternate_owner"
                )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entries": [asdict(e) for e in self.entries],
            "total_count": len(self.entries),
            "active_count": sum(1 for e in self.entries if e.owner != "deleted"),
            "deleted_count": sum(1 for e in self.entries if e.owner == "deleted"),
        }

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> AuxiliaryRegistry:
        """Load from dictionary."""
        registry = AuxiliaryRegistry()
        for entry_data in data.get("entries", []):
            entry = AuxiliaryTest(
                file_path=entry_data["file_path"],
                test_type=AuxiliaryTestType(entry_data["test_type"]),
                owner=entry_data["owner"],
                command=entry_data["command"],
                reason=entry_data["reason"],
                alternate_owner=entry_data.get("alternate_owner"),
                created_at=entry_data.get("created_at", ""),
                expiry_date=entry_data.get("expiry_date"),
            )
            registry.entries.append(entry)
        return registry


def identify_tracked_test_files() -> list[Path]:
    """
    Identify tracked files that look like tests but aren't pytest-collected.

    Returns list of relative paths to investigate.
    """
    candidates: list[Path] = []
    repo_root = Path.cwd()

    # Look for shell test files
    for pattern in ["tests/**/*.sh", "scripts/**/*test*.sh", "**/test-*.sh"]:
        candidates.extend(repo_root.glob(pattern))

    # Look for standalone JavaScript test runners
    for pattern in [
        "frontend/ci/**/*.test.ts",
        "frontend/ci/**/*.test.js",
    ]:
        candidates.extend(repo_root.glob(pattern))

    # Look for manual integration/e2e markers
    for pattern in [
        "tests/**/*integration*.py",
        "tests/**/*e2e*.py",
        "tests/**/*manual*.py",
    ]:
        candidates.extend(repo_root.glob(pattern))

    # Deduplicate and filter tracked files
    candidates = list(set(candidates))
    return sorted(candidates)


def default_registry() -> AuxiliaryRegistry:
    """
    Build default auxiliary registry from current tree.

    This serves as a starting point; entries should be reviewed and
    either assigned owners + commands or marked for deletion.
    """
    registry = AuxiliaryRegistry()

    # Example: any unassigned tracked files would be added here
    # For now, return empty registry to be populated by tasks

    return registry
