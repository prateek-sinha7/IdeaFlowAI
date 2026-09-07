"""Evidence manifest for CI evaluation tracking and validation.

Binds producer outputs, checksums, formats, command/tool versions, inventory digest,
run/attempt, and outcome to the exact evaluation SHA for later evidence aggregation
and validation.
"""

import hashlib
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional


def normalize_path(filepath: str, root: str = "") -> str:
    """Normalize file path to repository-relative format.

    Args:
        filepath: Path to normalize
        root: Optional root prefix to resolve within (e.g., 'frontend' or 'backend')

    Returns:
        Normalized repository-relative path with forward slashes

    Raises:
        ValueError: If path is absolute, contains traversal, or is unsafe
    """
    # Reject absolute paths
    if filepath.startswith("/") or (len(filepath) > 2 and filepath[1] == ":"):
        raise ValueError(f"Absolute path not allowed: {filepath}")

    # Reject directory traversal
    if ".." in filepath:
        raise ValueError(f"Directory traversal not allowed: {filepath}")

    path = Path(filepath)
    parts = path.parts

    # Try to find the root in the path
    if root and root in parts:
        root_idx = parts.index(root)
        normalized = str(Path(*parts[root_idx:]))
    else:
        # Otherwise return as-is
        normalized = filepath

    # Convert to forward slashes for consistency
    return normalized.replace("\\", "/")


@dataclass
class FileRecord:
    """Single file in an evidence artifact."""

    path: str
    format: str  # junit, coverage-data, coverage-report, etc.
    bytes: int
    sha256: str


@dataclass
class EvidenceManifest:
    """Manifest binding producer outputs and metadata to evaluation SHA."""

    schema_version: int = 1
    repository: str = ""
    evaluation_sha: str = ""
    run_id: int = 0
    run_attempt: int = 1
    producer: str = ""
    inventory_sha256: Optional[str] = None
    command_sha256: Optional[str] = None
    tool_versions: dict[str, str] = field(default_factory=dict)
    outcome: str = "success"  # success, failure, cancelled, skipped, timed_out, missing
    files: list[FileRecord] = field(default_factory=list)
    timestamps: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, recursively converting nested dataclasses."""
        d = asdict(self)
        d["files"] = [asdict(f) for f in self.files]
        return d

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        """Save manifest to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @staticmethod
    def load(path: Path) -> "EvidenceManifest":
        """Load manifest from file."""
        data = json.loads(path.read_text())
        files = [FileRecord(**f) for f in data.pop("files", [])]
        manifest = EvidenceManifest(**data)
        manifest.files = files
        return manifest

    def add_file(
        self,
        file_path: Path,
        format_type: str,
        allow_missing: bool = False,
    ) -> bool:
        """Add a file to the manifest with checksum validation.

        Args:
            file_path: Path to file to add
            format_type: Format classifier (junit, coverage-data, etc.)
            allow_missing: If True, return False instead of raising on missing file

        Returns:
            True if file was added, False if missing and allow_missing=True

        Raises:
            FileNotFoundError: If file doesn't exist and allow_missing=False
            ValueError: If file path is absolute or contains traversal
        """
        if not file_path.exists():
            if allow_missing:
                return False
            raise FileNotFoundError(f"Evidence file not found: {file_path}")

        # Reject absolute paths, traversal, and symlinks
        file_path_str = str(file_path)
        if file_path.is_absolute():
            raise ValueError(f"Absolute paths not allowed: {file_path}")
        if ".." in file_path_str or file_path.is_symlink():
            raise ValueError(f"Traversal or symlink not allowed: {file_path}")

        # Calculate file checksum
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        file_size = file_path.stat().st_size
        file_record = FileRecord(
            path=file_path_str,
            format=format_type,
            bytes=file_size,
            sha256=sha256_hash.hexdigest(),
        )

        self.files.append(file_record)
        return True

    def validate_completeness(
        self,
        expected_producers: list[str],
        expected_formats: dict[str, list[str]],
    ) -> tuple[bool, list[str]]:
        """Validate that all expected producers and formats are present.

        Args:
            expected_producers: List of required producer names
            expected_formats: Map of producer -> list of required formats

        Returns:
            Tuple of (is_complete, list of missing items)
        """
        errors = []

        if self.producer not in expected_producers:
            errors.append(f"Unknown producer: {self.producer}")

        if self.producer in expected_formats:
            required_formats = set(expected_formats[self.producer])
            found_formats = {f.format for f in self.files}
            missing = required_formats - found_formats
            if missing:
                errors.append(
                    f"Producer {self.producer} missing formats: {', '.join(missing)}"
                )

        return len(errors) == 0, errors
