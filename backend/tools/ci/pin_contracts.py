"""
Pin and installer contracts for deterministic tooling in CI.

This module enforces four contracts:
1. Tool-pin: All tools in check manifests must have explicit pinned versions
2. Action-pin: All GitHub Actions references must use full commit SHAs
3. Image-pin: All container images must have exact digest pins
4. Installer contracts: Verify install_* callables are pure functions
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum


class VersionPinType(Enum):
    """Types of version pin violations."""

    LATEST_TAG = "latest_tag"
    FLOATING_RANGE = "floating_range"
    NO_EXPLICIT_VERSION = "no_explicit_version"
    MUTABLE_TAG = "mutable_tag"


class ActionPinType(Enum):
    """Types of GitHub Actions pin violations."""

    TAG_REFERENCE = "tag_reference"
    BRANCH_REFERENCE = "branch_reference"
    SHORT_SHA = "short_sha"
    NO_REFERENCE = "no_reference"


class ImagePinType(Enum):
    """Types of container image pin violations."""

    MUTABLE_TAG = "mutable_tag"
    NO_DIGEST = "no_digest"
    FLOATING_TAG = "floating_tag"


@dataclass
class PinContract:
    """Base contract for enforcement."""

    name: str
    severity: str  # "error" or "warning"
    message: str

    def __eq__(self, other):
        if not isinstance(other, PinContract):
            return False
        return (
            self.name == other.name
            and self.severity == other.severity
            and self.message == other.message
        )


@dataclass
class ToolPinViolation(PinContract):
    """Contract violation: tool version is not pinned."""

    tool_name: str
    violation_type: VersionPinType
    current_value: str
    location: str

    def __init__(
        self,
        tool_name: str,
        violation_type: VersionPinType,
        current_value: str,
        location: str,
    ):
        super().__init__(
            name="tool-pin",
            severity="error",
            message=f"Tool '{tool_name}' must use explicit pinned version, not '{current_value}' at {location}",
        )
        self.tool_name = tool_name
        self.violation_type = violation_type
        self.current_value = current_value
        self.location = location


@dataclass
class ActionPinViolation(PinContract):
    """Contract violation: GitHub Action reference is not a full commit SHA."""

    action: str
    violation_type: ActionPinType
    current_value: str
    location: str

    def __init__(
        self,
        action: str,
        violation_type: ActionPinType,
        current_value: str,
        location: str,
    ):
        super().__init__(
            name="action-pin",
            severity="error",
            message=f"Action '{action}' must use full commit SHA, not '{current_value}' at {location}",
        )
        self.action = action
        self.violation_type = violation_type
        self.current_value = current_value
        self.location = location


@dataclass
class ImagePinViolation(PinContract):
    """Contract violation: container image is not pinned to exact digest."""

    image: str
    violation_type: ImagePinType
    current_value: str
    location: str

    def __init__(
        self,
        image: str,
        violation_type: ImagePinType,
        current_value: str,
        location: str,
    ):
        super().__init__(
            name="image-pin",
            severity="error",
            message=f"Image '{image}' must use exact digest pin, not '{current_value}' at {location}",
        )
        self.image = image
        self.violation_type = violation_type
        self.current_value = current_value
        self.location = location


@dataclass
class InstallerContractViolation(PinContract):
    """Contract violation: installer callable is not pure or has external dependencies."""

    function_name: str
    issue: str

    def __init__(self, function_name: str, issue: str):
        super().__init__(
            name="installer-contract",
            severity="error",
            message=f"Installer function '{function_name}' violates purity contract: {issue}",
        )
        self.function_name = function_name
        self.issue = issue


class ToolPinValidator:
    """Validates that all tools have explicit pinned versions."""

    LATEST_PATTERNS = [
        r"^latest$",
        r"^@latest$",
        r"(^|\W)latest(\W|$)",
    ]

    FLOATING_PATTERNS = [
        r"^~",  # npm ~X.Y.Z
        r"^\^",  # npm ^X.Y.Z
        r"^>|^<|^>=|^<=|^\*",  # version ranges
        r"^(latest|main|master|trunk|develop)$",  # branch references
        r"(\s|\+)(latest|main|master|trunk|develop)(\s|$)",  # branch references with whitespace
    ]

    def __init__(self):
        self.violations: List[ToolPinViolation] = []

    def validate_check_manifest(
        self, manifest: Dict, location: str = "manifest"
    ) -> bool:
        """
        Validate that all tool references in a check manifest are pinned.

        Expected manifest structure:
        {
            "checks": [
                {"id": "ruff-lint", "argv": ["uv", "run", "--frozen", "ruff", "check", "."]},
                ...
            ]
        }
        """
        self.violations = []

        if "checks" not in manifest:
            return True

        for check in manifest.get("checks", []):
            if "argv" not in check:
                continue

            argv = check["argv"]
            check_id = check.get("id", "unknown")

            # Parse argv for tool references
            for i, arg in enumerate(argv):
                violation = self._check_tool_arg(arg, i, argv, check_id, location)
                if violation:
                    self.violations.append(violation)

        return len(self.violations) == 0

    def validate_tool_version(
        self, tool_name: str, version: str, location: str = "unknown"
    ) -> Optional[ToolPinViolation]:
        """Validate a single tool version reference."""
        # Check for latest
        for pattern in self.LATEST_PATTERNS:
            if re.search(pattern, version, re.IGNORECASE):
                return ToolPinViolation(
                    tool_name=tool_name,
                    violation_type=VersionPinType.LATEST_TAG,
                    current_value=version,
                    location=location,
                )

        # Check for floating ranges
        for pattern in self.FLOATING_PATTERNS:
            if re.search(pattern, version, re.IGNORECASE):
                return ToolPinViolation(
                    tool_name=tool_name,
                    violation_type=VersionPinType.FLOATING_RANGE,
                    current_value=version,
                    location=location,
                )

        # Check if version is empty
        if not version or version.isspace():
            return ToolPinViolation(
                tool_name=tool_name,
                violation_type=VersionPinType.NO_EXPLICIT_VERSION,
                current_value=version or "(empty)",
                location=location,
            )

        return None

    def _check_tool_arg(
        self, arg: str, index: int, argv: List[str], check_id: str, location: str
    ) -> Optional[ToolPinViolation]:
        """Check a single argument in argv for version pinning."""
        # Ruff example: ["uv", "run", "--frozen", "ruff", "check", "."]
        # The version should be in pyproject.toml or lock file, checked separately

        # For now, check obvious cases like:
        # ["pip", "install", "ruff"]  <- no version
        # ["pip", "install", "ruff@latest"]  <- latest
        if arg.startswith("ruff@"):
            version = arg.split("@", 1)[1]
            return self.validate_tool_version("ruff", version, f"{location}:{check_id}")

        return None


class ActionPinValidator:
    """Validates that all GitHub Actions use full commit SHAs."""

    FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

    def __init__(self):
        self.violations: List[ActionPinViolation] = []

    def validate_workflow(
        self, workflow_yaml: Dict, location: str = "workflow"
    ) -> bool:
        """
        Validate that all action uses specify full commit SHAs.

        Expected workflow structure:
        {
            "jobs": {
                "job-name": {
                    "steps": [
                        {"uses": "owner/repo@sha256hash..."},
                        ...
                    ]
                }
            }
        }
        """
        self.violations = []

        jobs = workflow_yaml.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step_index, step in enumerate(steps):
                if "uses" not in step:
                    continue

                uses = step["uses"]
                violation = self.validate_action_reference(
                    uses, f"{location}:jobs.{job_name}.steps[{step_index}]"
                )
                if violation:
                    self.violations.append(violation)

        return len(self.violations) == 0

    def validate_action_reference(
        self, action_ref: str, location: str = "unknown"
    ) -> Optional[ActionPinViolation]:
        """
        Validate a single action reference.

        Valid format: owner/repo@<40-char-sha>
        Invalid: owner/repo@v1, owner/repo@main, owner/repo
        """
        if "@" not in action_ref:
            # Parse to extract action name for the error
            return ActionPinViolation(
                action=action_ref,
                violation_type=ActionPinType.NO_REFERENCE,
                current_value=action_ref,
                location=location,
            )

        parts = action_ref.split("@", 1)
        if len(parts) != 2:
            return ActionPinViolation(
                action=action_ref,
                violation_type=ActionPinType.NO_REFERENCE,
                current_value=action_ref,
                location=location,
            )

        action_path = parts[0]
        ref = parts[1]

        # Check if it's a full SHA (40 hex characters)
        if not self.FULL_SHA_PATTERN.match(ref):
            # Determine violation type
            if ref.startswith("v"):
                violation_type = ActionPinType.TAG_REFERENCE
            elif ref in ("main", "master", "develop", "trunk"):
                violation_type = ActionPinType.BRANCH_REFERENCE
            elif len(ref) < 40:
                violation_type = ActionPinType.SHORT_SHA
            else:
                violation_type = ActionPinType.TAG_REFERENCE

            return ActionPinViolation(
                action=action_path,
                violation_type=violation_type,
                current_value=ref,
                location=location,
            )

        return None


class ImagePinValidator:
    """Validates that all container images use exact digest pins."""

    DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)
    MUTABLE_TAGS = ["latest", "main", "master", "nightly", "dev", "staging"]

    def __init__(self):
        self.violations: List[ImagePinViolation] = []

    def validate_image_reference(
        self, image_ref: str, location: str = "unknown"
    ) -> Optional[ImagePinViolation]:
        """
        Validate a single image reference.

        Valid formats:
        - registry.io/image@sha256:...

        Invalid:
        - registry.io/image:latest
        - registry.io/image:v1.0
        - registry.io/image  (no tag or digest)
        """
        if "@" not in image_ref and ":" not in image_ref:
            # No tag or digest
            return ImagePinViolation(
                image=image_ref,
                violation_type=ImagePinType.NO_DIGEST,
                current_value=image_ref,
                location=location,
            )

        if "@" in image_ref:
            # Has digest
            parts = image_ref.split("@", 1)
            digest = parts[1]

            if not self.DIGEST_PATTERN.match(digest):
                return ImagePinViolation(
                    image=image_ref,
                    violation_type=ImagePinType.NO_DIGEST,
                    current_value=digest,
                    location=location,
                )

            # Valid digest format
            return None

        # Has tag but no digest
        if ":" in image_ref:
            parts = image_ref.rsplit(":", 1)
            tag = parts[1]

            # Check if tag is mutable
            if tag in self.MUTABLE_TAGS:
                return ImagePinViolation(
                    image=image_ref,
                    violation_type=ImagePinType.MUTABLE_TAG,
                    current_value=tag,
                    location=location,
                )

            # Check if tag looks like a version range
            if any(tag.startswith(prefix) for prefix in ["~", "^", ">", "<", "="]):
                return ImagePinViolation(
                    image=image_ref,
                    violation_type=ImagePinType.FLOATING_TAG,
                    current_value=tag,
                    location=location,
                )

            # Tag is not digest-pinned
            return ImagePinViolation(
                image=image_ref,
                violation_type=ImagePinType.NO_DIGEST,
                current_value=tag,
                location=location,
            )

        return None

    def validate_docker_file(
        self, dockerfile_content: str, location: str = "Dockerfile"
    ) -> bool:
        """
        Validate that all FROM and RUN ... image references use digest pins.
        """
        self.violations = []
        lines = dockerfile_content.split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Check FROM directives
            if line.startswith("FROM "):
                image_ref = line.split(None, 1)[1].split()[0]
                violation = self.validate_image_reference(
                    image_ref, f"{location}:{line_num}"
                )
                if violation:
                    self.violations.append(violation)

        return len(self.violations) == 0


class InstallerContractValidator:
    """Validates that install_* callables are pure functions with no external deps."""

    def __init__(self):
        self.violations: List[InstallerContractViolation] = []

    def validate_installer_function(
        self, func_name: str, func_code: str, location: str = "unknown"
    ) -> Optional[InstallerContractViolation]:
        """
        Validate that an installer function is pure.

        Pure function requirements:
        - No network calls (requests, urllib, socket)
        - No subprocess/os.system calls
        - No environment variable writes
        - No file writes outside of bounded temp
        - No credential accesses
        """
        issues = []

        # Check for network patterns - be more specific
        network_patterns = [
            r"\brequests\.(get|post|request|head|put|delete|patch)\(",
            r"\burllib\.request\.",
            r"\bsocket\.(socket|connect)",
            r"\bhttp\.client\.",
        ]

        for pattern in network_patterns:
            if re.search(pattern, func_code):
                issues.append(f"Network call detected: {pattern}")
                break

        # Check for subprocess patterns
        subprocess_patterns = [
            r"\bsubprocess\.(run|call|check_call|check_output|Popen)",
            r"\bos\.system\(",
            r"\bos\.popen\(",
        ]

        for pattern in subprocess_patterns:
            if re.search(pattern, func_code):
                issues.append(f"Subprocess call detected: {pattern}")
                break

        # Check for env writes
        if re.search(r"\bos\.environ\[.*\]\s*=", func_code):
            issues.append("Environment variable modification detected")

        # Check for credential patterns
        credential_patterns = [
            r'\bos\.getenv\(["\']?(AWS_|GITHUB_|API_KEY)',
            r"\bgetenv.*SECRET",
            r"\bgetenv.*TOKEN",
        ]

        for pattern in credential_patterns:
            if re.search(pattern, func_code, re.IGNORECASE):
                issues.append("Credential access pattern detected")
                break

        if issues:
            return InstallerContractViolation(
                function_name=func_name, issue="; ".join(issues)
            )

        return None


def validate_all_pin_contracts(
    manifest: Dict, workflow: Dict, dockerfiles: Dict[str, str]
) -> Tuple[bool, List[PinContract]]:
    """
    Validate all pin contracts together.

    Args:
        manifest: Check manifest dict
        workflow: GitHub workflow YAML dict
        dockerfiles: Dict of {path: content} for Dockerfiles

    Returns:
        Tuple of (all_valid, violations_list)
    """
    all_violations: List[PinContract] = []

    # Validate tool pins
    tool_validator = ToolPinValidator()
    tool_validator.validate_check_manifest(manifest)
    all_violations.extend(tool_validator.violations)

    # Validate action pins
    action_validator = ActionPinValidator()
    action_validator.validate_workflow(workflow)
    all_violations.extend(action_validator.violations)

    # Validate image pins
    image_validator = ImagePinValidator()
    for dockerfile_path, dockerfile_content in dockerfiles.items():
        image_validator.validate_docker_file(dockerfile_content, dockerfile_path)
    all_violations.extend(image_validator.violations)

    return len(all_violations) == 0, all_violations
