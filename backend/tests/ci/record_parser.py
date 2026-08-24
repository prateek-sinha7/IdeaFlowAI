"""
Remediation Record parser and completeness checker.

Validates the `.planning/REMEDIATION-RECORD.md` document structure and enforces
required fields on all entries. Every skip, waiver, disposition, and threshold
deviation must have an owner, reason, and non-expired date.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import re


#: Field values that mean "not filled in yet".
_PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "(owner name or tbd)",
    "(approver name or tbd)",
    "(iss-xxx or other reference)",
    "(reason)",
    "pr #xxx or tbd",
    "ci run #xxx or tbd",
}


def _is_unfilled(value: Optional[str]) -> bool:
    """Return True when a cell value is absent or still a template placeholder."""
    if value is None:
        return True
    return value.strip().lower() in _PLACEHOLDER_VALUES


@dataclass
class RemediationEntry:
    """A single entry in a remediation record section."""
    case_id: str
    owner: Optional[str] = None
    reason: Optional[str] = None
    expiry: Optional[datetime] = None
    classification: Optional[str] = None
    directive: Optional[str] = None
    extra_fields: dict = None
    #: Section this entry came from, for error messages.
    section: Optional[str] = None
    #: Fields this section's column set actually carries and therefore requires.
    required_fields: tuple = ("owner", "reason", "expiry")
    #: True when `expiry` is a waiver deadline (a past date invalidates the
    #: entry). False when it is a historical date such as an approval date.
    expiry_is_deadline: bool = True

    def __post_init__(self):
        if self.extra_fields is None:
            self.extra_fields = {}

    def is_valid(self) -> tuple[bool, list[str]]:
        """
        Check if the entry is valid.

        Only the fields the entry's section actually carries are required, so a
        section without an expiry column is not reported as missing an expiry.

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        if "owner" in self.required_fields and _is_unfilled(self.owner):
            errors.append(f"{self.case_id}: missing or TBD owner")

        if "reason" in self.required_fields and _is_unfilled(self.reason):
            errors.append(f"{self.case_id}: missing reason")

        if "expiry" in self.required_fields:
            if self.expiry is None:
                errors.append(f"{self.case_id}: missing expiry date")
            elif self.expiry_is_deadline and self.expiry < datetime.now():
                errors.append(
                    f"{self.case_id}: expiry date {self.expiry.isoformat()} is in the past"
                )

        return len(errors) == 0, errors


class RemediationRecordParser:
    """Parses the remediation record and validates entries."""

    def __init__(self, record_path: Path):
        self.record_path = Path(record_path)
        self.dispositions: list[RemediationEntry] = []
        self.disabled_tests: list[RemediationEntry] = []
        self.coverage_exclusions: list[RemediationEntry] = []
        self.accessibility_waivers: list[RemediationEntry] = []
        self.coverage_thresholds: list[RemediationEntry] = []
        self.performance_thresholds: list[RemediationEntry] = []
        self.security_approvals: list[RemediationEntry] = []
        self.completion_links: list[RemediationEntry] = []

    def parse(self) -> None:
        """Parse the remediation record file."""
        if not self.record_path.exists():
            raise FileNotFoundError(f"Remediation record not found: {self.record_path}")

        content = self.record_path.read_text(encoding="utf-8", errors="replace")

        # Extract each section and parse its table
        self._parse_section(content, "## Dispositions", self.dispositions, ["Case ID", "Classification", "Owner", "Date", "Resolving Change"])
        self._parse_section(content, "## Disabled Tests", self.disabled_tests, ["Case ID", "Suite", "Directive", "Owner", "Reason", "Expiry"])
        self._parse_section(content, "## Coverage Exclusions", self.coverage_exclusions, ["Pattern", "Justification", "Owner", "Expiry"])
        self._parse_section(content, "## Accessibility Waivers", self.accessibility_waivers, ["Violation", "Surface", "Rationale", "Owner", "Expiry"])
        self._parse_section(content, "## Coverage Thresholds", self.coverage_thresholds, ["Module", "Metric", "Baseline", "Target", "Owner", "Target Date"])
        self._parse_section(content, "## Performance Thresholds", self.performance_thresholds, ["Scenario", "Metric", "Threshold", "Owner"])
        self._parse_section(content, "## Security Approvals", self.security_approvals, ["Change", "Approver", "Date"])
        self._parse_section(content, "## Completion Links", self.completion_links, ["Task ID", "Verifying Test", "Execution Evidence"])

    def _parse_section(self, content: str, section_header: str, target_list: list, expected_columns: list) -> None:
        """
        Parse a single markdown table section.

        Args:
            content: Full document content
            section_header: The section header to find (e.g., "## Dispositions")
            target_list: List to populate with parsed entries
            expected_columns: Column names expected in the table
        """
        # Find the section
        if section_header not in content:
            return

        start_idx = content.find(section_header)
        # Find the end (next ## section or end of file)
        next_section = content.find("\n##", start_idx + 1)
        if next_section == -1:
            section_content = content[start_idx:]
        else:
            section_content = content[start_idx:next_section]

        # Extract markdown table (skip the header line and separator)
        lines = section_content.split("\n")
        table_start = None
        for i, line in enumerate(lines):
            if line.startswith("|"):
                table_start = i
                break

        if table_start is None:
            return

        # Parse table rows (skip header and separator)
        for i in range(table_start + 2, len(lines)):
            line = lines[i].strip()
            if not line.startswith("|"):
                break
            if "placeholder" in line.lower():
                continue  # Skip placeholder rows

            # Skip template example rows: their identifier is a parenthesised
            # description of the column rather than a real case or module, e.g.
            # "| (scenario name) | ... |". Real debt never uses that form.
            first_cell = line.split("|")[1].strip() if line.count("|") >= 2 else ""
            if first_cell.startswith("(") and first_cell.endswith(")"):
                continue

            # Split the row by pipes and clean
            cells = [cell.strip() for cell in line.split("|")[1:-1]]  # Skip empty first/last
            if len(cells) == 0:
                continue

            # Parse based on section type
            entry = self._create_entry(section_header, cells, expected_columns)
            if entry and entry.case_id != "(placeholder)":
                target_list.append(entry)

    def _create_entry(self, section_header: str, cells: list[str], expected_columns: list) -> Optional[RemediationEntry]:
        """Create a RemediationEntry from table cells."""
        if len(cells) == 0:
            return None

        try:
            if "Dispositions" in section_header and len(cells) >= 5:
                return RemediationEntry(
                    case_id=cells[0],
                    classification=cells[1],
                    owner=cells[2],
                    reason=cells[4],  # Resolving Change as reason
                    expiry=None,  # Dispositions have no expiry in the design
                    section="Dispositions",
                    required_fields=("owner", "reason"),
                )
            elif "Disabled Tests" in section_header and len(cells) >= 6:
                expiry = self._parse_date(cells[5])
                return RemediationEntry(
                    case_id=cells[0],
                    directive=cells[2],
                    owner=cells[3],
                    reason=cells[4],
                    expiry=expiry,
                    section="Disabled Tests",
                )
            elif "Coverage Exclusions" in section_header and len(cells) >= 4:
                expiry = self._parse_date(cells[3])
                return RemediationEntry(
                    case_id=cells[0],  # Pattern as case_id
                    reason=cells[1],  # Justification
                    owner=cells[2],
                    expiry=expiry,
                    section="Coverage Exclusions",
                )
            elif "Accessibility Waivers" in section_header and len(cells) >= 5:
                expiry = self._parse_date(cells[4])
                return RemediationEntry(
                    case_id=cells[0],  # Violation as case_id
                    reason=cells[2],  # Rationale
                    owner=cells[3],
                    expiry=expiry,
                    section="Accessibility Waivers",
                )
            elif "Coverage Thresholds" in section_header and len(cells) >= 6:
                return RemediationEntry(
                    case_id=cells[0],  # Module as case_id
                    owner=cells[4],
                    expiry=self._parse_date(cells[5]),  # Target Date
                    section="Coverage Thresholds",
                    required_fields=("owner", "expiry"),
                )
            elif "Performance Thresholds" in section_header and len(cells) >= 4:
                return RemediationEntry(
                    case_id=cells[0],  # Scenario as case_id
                    owner=cells[3],
                    expiry=None,  # No expiry for performance thresholds
                    section="Performance Thresholds",
                    required_fields=("owner",),
                )
            elif "Security Approvals" in section_header and len(cells) >= 3:
                return RemediationEntry(
                    case_id=cells[0],  # Change as case_id
                    owner=cells[1],  # Approver
                    expiry=self._parse_date(cells[2]),  # Approval date (historical)
                    section="Security Approvals",
                    required_fields=("owner", "expiry"),
                    expiry_is_deadline=False,
                )
            elif "Completion Links" in section_header and len(cells) >= 3:
                return RemediationEntry(
                    case_id=cells[0],  # Task ID
                    reason=cells[1],  # Verifying Test
                    expiry=None,  # No expiry for completion links
                    section="Completion Links",
                    required_fields=("reason",),
                    extra_fields={"execution_evidence": cells[2]},
                )
        except (IndexError, ValueError):
            return None

        return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string in YYYY-MM-DD format."""
        if not date_str or date_str == "YYYY-MM-DD" or date_str == "TBD":
            return None
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except ValueError:
            return None

    def validate_completeness(self) -> tuple[bool, list[str]]:
        """
        Validate that all entries are complete (have owner, reason, non-expired dates).

        Returns:
            (is_valid, error_messages)
        """
        all_errors = []

        all_entries = (
            self.dispositions
            + self.disabled_tests
            + self.coverage_exclusions
            + self.accessibility_waivers
            + self.coverage_thresholds
            + self.performance_thresholds
            + self.security_approvals
            + self.completion_links
        )

        for entry in all_entries:
            is_valid, errors = entry.is_valid()
            if not is_valid:
                all_errors.extend(errors)

        return len(all_errors) == 0, all_errors

    def get_expired_entries(self) -> list[RemediationEntry]:
        """Return all entries with expired dates."""
        expired = []
        now = datetime.now()

        all_entries = (
            self.dispositions
            + self.disabled_tests
            + self.coverage_exclusions
            + self.accessibility_waivers
            + self.coverage_thresholds
            + self.performance_thresholds
            + self.security_approvals
            + self.completion_links
        )

        for entry in all_entries:
            if entry.expiry_is_deadline and entry.expiry and entry.expiry < now:
                expired.append(entry)

        return expired

    def get_incomplete_entries(self) -> list[RemediationEntry]:
        """Return all entries that are missing required fields."""
        incomplete = []

        all_entries = (
            self.dispositions
            + self.disabled_tests
            + self.coverage_exclusions
            + self.accessibility_waivers
            + self.coverage_thresholds
            + self.performance_thresholds
            + self.security_approvals
            + self.completion_links
        )

        for entry in all_entries:
            is_valid, _ = entry.is_valid()
            if not is_valid:
                incomplete.append(entry)

        return incomplete
