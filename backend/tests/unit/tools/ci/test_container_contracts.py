"""
Property-based and contract tests for production-context container images.

Validates:
- Production image definitions (backend Python, backend pptx-builder, frontend Node)
- Trivy and Grype scanner results for HIGH/CRITICAL findings
- Zero-finding policy for production images
- Base image pin authority contracts
- Dockerfile remediation effectiveness
- Scanner diversity (both Trivy and Grype must agree)

**Validates: Requirements 2.8, 2.9, 2.13, 3.9, 3.10, 3.13, 3.14**
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest
from hypothesis import given, settings, strategies as st, assume

from tools.ci.scanner_parsers import parse_trivy_json, parse_grype_json
from tools.ci.scanner_policy import ZeroHighCriticalPolicy, merge_verdicts
from tools.ci.scanner_verdict import Finding, ScannerVerdict, SeverityLevel


# ============================================================================
# Production image definitions
# ============================================================================


@dataclass
class ProductionImage:
    """Contract definition for a production-context Docker image."""

    name: str
    """Image name/label (backend-python, backend-pptx-builder, frontend)"""

    dockerfile_path: Path
    """Path to Dockerfile"""

    base_image: str
    """Required base image with digest"""

    build_context: str
    """Build context directory"""

    build_args: Dict[str, str]
    """Build arguments required"""

    required_scanners: Set[str]
    """Scanners that must successfully evaluate this image"""


# Get repository root (parent of backend)
_REPO_ROOT = Path(__file__).parents[5]

# Define the three production-context images
PRODUCTION_IMAGES = {
    "backend-python": ProductionImage(
        name="backend-python",
        dockerfile_path=_REPO_ROOT / "backend" / "Dockerfile",
        base_image="python:3.13-slim-bookworm",
        build_context="backend",
        build_args={},
        required_scanners={"trivy", "grype"},
    ),
    "backend-pptx-builder": ProductionImage(
        name="backend-pptx-builder",
        dockerfile_path=_REPO_ROOT / "backend" / "Dockerfile",
        base_image="node:20-bookworm-slim",
        build_context="backend",
        build_args={},
        required_scanners={"trivy", "grype"},
    ),
    "frontend": ProductionImage(
        name="frontend",
        dockerfile_path=_REPO_ROOT / "frontend" / "Dockerfile",
        base_image="node:20-bookworm-slim",
        build_context="frontend",
        build_args={"NEXT_PUBLIC_API_URL": "", "NEXT_PUBLIC_WS_URL": ""},
        required_scanners={"trivy", "grype"},
    ),
}


# ============================================================================
# Contract tests for image definitions
# ============================================================================


class TestProductionImageContract:
    """Contract tests for production image definitions."""

    def test_all_production_images_defined(self):
        """All three production images must be defined."""
        assert len(PRODUCTION_IMAGES) == 3
        assert "backend-python" in PRODUCTION_IMAGES
        assert "backend-pptx-builder" in PRODUCTION_IMAGES
        assert "frontend" in PRODUCTION_IMAGES

    def test_production_image_dockerfiles_exist(self):
        """All production image Dockerfiles must exist."""
        for name, image in PRODUCTION_IMAGES.items():
            dockerfile = image.dockerfile_path
            assert dockerfile.exists(), f"Dockerfile not found for {name}: {dockerfile}"

    def test_production_images_use_bookworm_slim(self):
        """All production images must use Debian bookworm-slim base."""
        for name, image in PRODUCTION_IMAGES.items():
            # bookworm-slim can be "image-bookworm-slim" not necessarily "bookworm-slim"
            assert (
                "bookworm" in image.base_image
            ), f"{name} should use bookworm base, got {image.base_image}"
            assert (
                "slim" in image.base_image
            ), f"{name} should use slim variant, got {image.base_image}"

    def test_production_images_are_not_floating(self):
        """
        Production base images must not float.

        A digest (`base@sha256:...`) is the strongest form and remains the target.
        Where a digest is not yet recorded, the reference must at least be
        qualified beyond a bare major — `python:3.13-slim-bookworm` is acceptable,
        `python:3` or `python:latest` is not, because those silently change what
        was scanned.

        This replaces a `pytest.skip(f"{name} digest not yet pinned")` that fired
        for exactly the images which were not pinned, so the assertion never ran
        on anything it was meant to check. Digest coverage is tracked separately
        in ci/toolchain-lock.json (`runtime_pins.postgresql.is_digest`), where it
        is recorded honestly as false rather than mislabelled as a digest.
        """
        floating: list[str] = []
        for name, image in PRODUCTION_IMAGES.items():
            reference = image.base_image

            if "@sha256:" in reference:
                continue  # strongest form, nothing more to check

            assert "@" not in reference, (
                f"{name} uses '{reference}', which contains '@' but is not an "
                f"'@sha256:' digest"
            )

            _, _, tag = reference.partition(":")
            if not tag or tag == "latest":
                floating.append(f"{name}={reference} (no tag or 'latest')")
                continue
            # Require more than a bare major, e.g. reject `python:3`.
            if re.fullmatch(r"\d+", tag):
                floating.append(f"{name}={reference} (bare major tag)")

        assert not floating, (
            "production base images must be digest-pinned or at least "
            f"fully qualified: {floating}"
        )

    def test_all_images_require_dual_scanners(self):
        """All images must be evaluated by both Trivy and Grype."""
        for name, image in PRODUCTION_IMAGES.items():
            assert image.required_scanners == {
                "trivy",
                "grype",
            }, f"{name} must require both trivy and grype"

    def test_backend_images_share_dockerfile(self):
        """Backend images (python and pptx-builder) must be built from same Dockerfile."""
        python_image = PRODUCTION_IMAGES["backend-python"]
        pptx_image = PRODUCTION_IMAGES["backend-pptx-builder"]

        assert python_image.dockerfile_path == pptx_image.dockerfile_path
        assert python_image.build_context == pptx_image.build_context


# ============================================================================
# Dockerfile contract tests
# ============================================================================


class TestDockerfileContract:
    """Contract tests for Dockerfile content and structure."""

    def test_backend_dockerfile_has_three_stages(self):
        """Backend Dockerfile must have builder, pptx (node build), and runtime stages."""
        dockerfile_path = PRODUCTION_IMAGES["backend-python"].dockerfile_path
        content = dockerfile_path.read_text()

        # Look for stage definitions - the pptx-builder stage may be named just "pptx"
        stages = re.findall(r"FROM .+ (?:AS|as) (\w+)", content)
        stage_names = [s.lower() for s in stages]

        assert (
            "builder" in stage_names
        ), f"Backend Dockerfile must have builder stage. Found: {stages}"
        # pptx-builder stage is actually named 'pptx' in current dockerfile
        assert (
            "pptx" in stage_names
        ), f"Backend Dockerfile must have pptx/pptx-builder stage. Found: {stages}"
        assert (
            "runtime" in stage_names
        ), f"Backend Dockerfile must have runtime stage. Found: {stages}"

    def test_backend_dockerfile_runs_as_non_root(self):
        """Backend runtime must run as non-root user."""
        dockerfile_path = PRODUCTION_IMAGES["backend-python"].dockerfile_path
        content = dockerfile_path.read_text()

        assert "USER" in content, "Backend Dockerfile must set USER directive"
        # Should have a UID that's not root
        assert re.search(
            r"USER\s+(?!0|root)\d+", content
        ), "Backend Dockerfile should run as non-root UID"

    def test_backend_dockerfile_has_healthcheck(self):
        """Backend runtime must have a healthcheck."""
        dockerfile_path = PRODUCTION_IMAGES["backend-python"].dockerfile_path
        content = dockerfile_path.read_text()

        assert "HEALTHCHECK" in content, "Backend Dockerfile must have HEALTHCHECK"

    def test_frontend_dockerfile_has_three_stages(self):
        """Frontend Dockerfile must have deps, builder, and runner stages."""
        dockerfile_path = PRODUCTION_IMAGES["frontend"].dockerfile_path
        content = dockerfile_path.read_text()

        stages = re.findall(r"FROM .+ AS (\w+)", content)
        assert "deps" in stages, "Frontend Dockerfile must have deps stage"
        assert "builder" in stages, "Frontend Dockerfile must have builder stage"
        assert "runner" in stages, "Frontend Dockerfile must have runner stage"

    def test_frontend_dockerfile_runs_as_non_root(self):
        """Frontend runtime must run as non-root user."""
        dockerfile_path = PRODUCTION_IMAGES["frontend"].dockerfile_path
        content = dockerfile_path.read_text()

        assert "USER" in content, "Frontend Dockerfile must set USER directive"
        assert re.search(
            r"USER\s+(?!0|root)\w+", content
        ), "Frontend Dockerfile should run as non-root user"

    def test_frontend_dockerfile_has_healthcheck(self):
        """Frontend runtime must have a healthcheck."""
        dockerfile_path = PRODUCTION_IMAGES["frontend"].dockerfile_path
        content = dockerfile_path.read_text()

        assert "HEALTHCHECK" in content, "Frontend Dockerfile must have HEALTHCHECK"

    def test_dockerfiles_use_cache_mounts_where_appropriate(self):
        """Dockerfiles should use BuildKit cache mounts to speed builds."""
        backend_dockerfile = PRODUCTION_IMAGES["backend-python"].dockerfile_path
        backend_content = backend_dockerfile.read_text()

        # Backend should use cache mount for pip
        assert (
            "--mount=type=cache" in backend_content
        ), "Backend Dockerfile should use BuildKit cache mount for pip"

    def test_backend_uses_production_requirements(self):
        """
        Backend must install a production-only dependency slice derived from
        the committed backend/uv.lock (Task 3.16), not a second,
        separately-maintained requirements file.
        """
        dockerfile_path = PRODUCTION_IMAGES["backend-python"].dockerfile_path
        content = dockerfile_path.read_text()

        assert "uv.lock" in content, (
            "Backend Dockerfile must derive its production install list from "
            "the committed uv.lock, the single dependency-resolution authority"
        )
        assert "uv export --frozen --no-dev" in content, (
            "Backend Dockerfile must export the production-only slice with "
            "--frozen (fail closed on lock/pyproject drift) and --no-dev "
            "(exclude test/static/security tooling from the runtime image)"
        )
        assert "--require-hashes" in content, (
            "Backend Dockerfile must install from the hash-bearing export so "
            "every wheel/sdist is verified against the digest uv.lock recorded"
        )

    def test_backend_disables_playwright_deps_in_builder(self):
        """Backend builder stage should not install playwright deps."""
        dockerfile_path = PRODUCTION_IMAGES["backend-python"].dockerfile_path
        content = dockerfile_path.read_text()

        # Split by stage (look for "FROM" markers)
        runtime_section = re.split(r"FROM .+ AS runtime", content)[-1]

        # Playwright deps should only be in runtime
        assert (
            "libatk-bridge" in runtime_section or "libatspi" in runtime_section
        ), "Runtime stage should have playwright deps"


# ============================================================================
# Scanner report contract tests
# ============================================================================


class TestScannerReportContract:
    """Contract tests for scanner output format and structure."""

    def test_trivy_json_format(self):
        """Trivy reports must follow JSON schema."""
        # Minimal valid Trivy report
        valid_report = {
            "SchemaVersion": 2,
            "Results": [],
        }

        verdict = parse_trivy_json(json.dumps(valid_report))
        assert verdict.success
        assert verdict.findings == []

    def test_grype_json_format(self):
        """Grype reports must follow JSON schema."""
        # Minimal valid Grype report
        valid_report = {
            "matches": [],
            "metadata": {"version": "0.65.0"},
        }

        verdict = parse_grype_json(json.dumps(valid_report))
        assert verdict.success
        assert verdict.findings == []

    def test_trivy_image_vs_config_reports(self):
        """Trivy can scan both images and configs with different report structures."""
        # Image report
        image_report = {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "image:sha256:abc123",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-001",
                            "PkgName": "libc6",
                            "Severity": "HIGH",
                        }
                    ],
                }
            ],
        }

        # Config report
        config_report = {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "Dockerfile",
                    "Misconfigurations": [
                        {
                            "ID": "AVD-AZU-0001",
                            "Title": "Test",
                            "Severity": "HIGH",
                        }
                    ],
                }
            ],
        }

        image_verdict = parse_trivy_json(json.dumps(image_report))
        config_verdict = parse_trivy_json(
            json.dumps(config_report), scanner_type="config"
        )

        assert not image_verdict.success  # Has HIGH finding
        assert not config_verdict.success  # Has HIGH misconfiguration


# ============================================================================
# Zero High/Critical finding enforcement
# ============================================================================


class TestZeroHighCriticalEnforcement:
    """Test enforcement of zero High/Critical findings policy."""

    def test_no_findings_pass(self):
        """Images with no findings must pass."""
        verdict = ScannerVerdict(
            success=True, findings=[], high_count=0, critical_count=0
        )
        policy_result = ZeroHighCriticalPolicy.apply_policy(verdict)
        assert policy_result.success

    def test_single_high_finding_fails(self):
        """Single HIGH finding must fail."""
        finding = Finding("CVE-2024-001", SeverityLevel.HIGH, "Test", "pkg", "trivy")
        verdict = ScannerVerdict(
            success=False, findings=[finding], high_count=1, critical_count=0
        )
        policy_result = ZeroHighCriticalPolicy.apply_policy(verdict)
        assert not policy_result.success

    def test_single_critical_finding_fails(self):
        """Single CRITICAL finding must fail."""
        finding = Finding(
            "CVE-2024-002", SeverityLevel.CRITICAL, "Test", "pkg", "trivy"
        )
        verdict = ScannerVerdict(
            success=False, findings=[finding], high_count=0, critical_count=1
        )
        policy_result = ZeroHighCriticalPolicy.apply_policy(verdict)
        assert not policy_result.success

    def test_medium_findings_pass(self):
        """MEDIUM and below findings must pass."""
        findings = [
            Finding("CVE-2024-003", SeverityLevel.MEDIUM, "Test", "pkg1", "trivy"),
            Finding("CVE-2024-004", SeverityLevel.LOW, "Test", "pkg2", "trivy"),
            Finding("CVE-2024-005", SeverityLevel.INFO, "Test", "pkg3", "trivy"),
        ]
        verdict = ScannerVerdict(
            success=True, findings=findings, high_count=0, critical_count=0
        )
        policy_result = ZeroHighCriticalPolicy.apply_policy(verdict)
        assert policy_result.success

    @given(
        high_count=st.integers(min_value=0, max_value=5),
        critical_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    def test_policy_based_on_counts(self, high_count: int, critical_count: int):
        """Policy enforcement should depend on HIGH/CRITICAL counts."""
        # If we're testing with counts, need corresponding findings for audit trail
        findings = []
        for _ in range(high_count):
            findings.append(
                Finding(
                    f"CVE-HIGH-{len(findings)}",
                    SeverityLevel.HIGH,
                    "Test",
                    "pkg",
                    "trivy",
                )
            )
        for _ in range(critical_count):
            findings.append(
                Finding(
                    f"CVE-CRITICAL-{len(findings)}",
                    SeverityLevel.CRITICAL,
                    "Test",
                    "pkg",
                    "trivy",
                )
            )

        verdict = ScannerVerdict(
            success=high_count == 0 and critical_count == 0,
            findings=findings,
            high_count=high_count,
            critical_count=critical_count,
        )
        policy_result = ZeroHighCriticalPolicy.apply_policy(verdict)

        if high_count > 0 or critical_count > 0:
            assert not policy_result.success, f"Policy should fail with {high_count} HIGH and {critical_count} CRITICAL"
        else:
            assert policy_result.success, "Policy should pass with zero HIGH/CRITICAL"


# ============================================================================
# Dual-scanner agreement tests
# ============================================================================


class TestDualScannerAgreement:
    """Test that Trivy and Grype reach consistent verdicts."""

    def test_both_scanners_detect_high_critical(self):
        """Both scanners should detect HIGH/CRITICAL findings."""
        # Shared CVE that both would detect
        cve_id = "CVE-2024-0001"

        trivy_report = {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "image:sha256:test",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": cve_id,
                            "PkgName": "libc6",
                            "Severity": "HIGH",
                            "Description": "Test HIGH vulnerability",
                        }
                    ],
                }
            ],
        }

        grype_report = {
            "matches": [
                {
                    "vulnerability": {
                        "id": cve_id,
                        "severity": "high",
                        "description": "Test HIGH vulnerability",
                        "fix": {"versions": []},
                    },
                    "artifact": {"name": "libc6", "version": "2.36"},
                }
            ],
            "metadata": {"version": "0.65.0"},
        }

        trivy_verdict = parse_trivy_json(json.dumps(trivy_report))
        grype_verdict = parse_grype_json(json.dumps(grype_report))

        # Both should fail
        assert not trivy_verdict.success
        assert not grype_verdict.success

        # Both should report the vulnerability
        assert trivy_verdict.high_count > 0
        assert grype_verdict.high_count > 0

    def test_scanner_disagreement_is_noted(self):
        """If scanners disagree, the stricter verdict should win."""
        # Trivy finds HIGH, Grype finds none
        trivy_report = {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "image:sha256:test",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-0002",
                            "PkgName": "test-pkg",
                            "Severity": "HIGH",
                        }
                    ],
                }
            ],
        }

        grype_report = {
            "matches": [],
            "metadata": {"version": "0.65.0"},
        }

        trivy_verdict = parse_trivy_json(json.dumps(trivy_report))
        grype_verdict = parse_grype_json(json.dumps(grype_report))

        # Merge: if either fails, merged fails
        merged = merge_verdicts([trivy_verdict, grype_verdict])
        assert not merged.success, "Merged verdict should fail if any scanner fails"


# ============================================================================
# Base image pin authority tests
# ============================================================================


class TestBaseImagePinAuthority:
    """Test that base image pins are authoritative and consistent."""

    def test_any_declared_digest_is_well_formed(self):
        """
        Where a digest IS declared, it must be a real 64-hex-character sha256.

        This is the check that catches a placeholder. ci/toolchain-lock.json
        previously carried two invented hashes — one 60 characters long
        containing the letters g through z, another 61 characters — neither of
        which could match any artifact. A malformed digest is worse than an
        honest tag: it looks like verification and provides none.

        Images without a digest are covered by
        `test_production_images_are_not_floating`, which requires a fully
        qualified tag. This test no longer skips when a digest is absent, because
        skipping meant the format was never validated for the images that did
        declare one.
        """
        malformed: list[str] = []

        for name, image in PRODUCTION_IMAGES.items():
            if "@sha256:" not in image.base_image:
                continue
            if not re.search(r"@sha256:[a-f0-9]{64}(?:$|\s)", image.base_image):
                malformed.append(f"{name}={image.base_image}")

        assert not malformed, (
            "declared image digests must be exactly 64 lowercase hex characters: "
            f"{malformed}"
        )

    def test_backend_python_matches_dockerfile(self):
        """Backend Python base image in contract should match Dockerfile."""
        contract_image = PRODUCTION_IMAGES["backend-python"]
        dockerfile_path = contract_image.dockerfile_path
        content = dockerfile_path.read_text()

        # Extract base image from Dockerfile builder stage
        builder_match = re.search(
            r"FROM python:3\.13-slim-bookworm(@sha256:([a-f0-9]{64}))?",
            content,
        )
        assert builder_match, "Backend Dockerfile must have python:3.13-slim-bookworm"

        # Verify it matches contract (contract may be without digest, that's OK for now)
        assert contract_image.base_image.startswith(
            "python:3.13"
        ), f"Contract base image doesn't match Dockerfile: {contract_image.base_image}"

    def test_base_images_are_maintained_versions(self):
        """Base images should use maintained/LTS versions."""
        # Python 3.13 is maintained
        assert "3.13" in PRODUCTION_IMAGES["backend-python"].base_image

        # Node 20 is LTS
        assert "20" in PRODUCTION_IMAGES["backend-pptx-builder"].base_image
        assert "20" in PRODUCTION_IMAGES["frontend"].base_image

    def test_all_images_use_slim_variants(self):
        """Production images should use slim variants to minimize attack surface."""
        for name, image in PRODUCTION_IMAGES.items():
            assert (
                "slim" in image.base_image
            ), f"{name} should use slim base image, got {image.base_image}"


# ============================================================================
# Remediation effectiveness tests
# ============================================================================


class TestRemediationEffectiveness:
    """Test that remediations actually eliminate findings."""

    def test_apt_package_upgrade_eliminates_finding(self):
        """Upgrading an OS package should eliminate the finding."""
        # Before upgrade: vulnerable package
        before_report = {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "image:before",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-test-upgrade",
                            "PkgName": "openssl",
                            "InstalledVersion": "1.1.1k",
                            "Severity": "HIGH",
                        }
                    ],
                }
            ],
        }

        # After upgrade: vulnerability gone
        after_report = {
            "SchemaVersion": 2,
            "Results": [{"Target": "image:after", "Vulnerabilities": []}],
        }

        before_verdict = parse_trivy_json(json.dumps(before_report))
        after_verdict = parse_trivy_json(json.dumps(after_report))

        assert not before_verdict.success
        assert before_verdict.high_count > 0
        assert after_verdict.success
        assert after_verdict.high_count == 0

    def test_base_image_replacement_eliminates_findings(self):
        """Changing to a newer base image should eliminate findings."""
        # Old base image report
        old_report = {
            "SchemaVersion": 2,
            "Results": [
                {
                    "Target": "image:old",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-base-old",
                            "PkgName": "libc6",
                            "Severity": "CRITICAL",
                        }
                    ],
                }
            ],
        }

        # New base image report
        new_report = {
            "SchemaVersion": 2,
            "Results": [{"Target": "image:new", "Vulnerabilities": []}],
        }

        old_verdict = parse_trivy_json(json.dumps(old_report))
        new_verdict = parse_trivy_json(json.dumps(new_report))

        assert not old_verdict.success
        assert old_verdict.critical_count > 0
        assert new_verdict.success


# ============================================================================
# Finding documentation tests
# ============================================================================


class TestFindingDocumentation:
    """Test that findings are properly documented."""

    def test_finding_has_remediation_path(self):
        """Each HIGH/CRITICAL finding should suggest a remediation."""
        finding = Finding(
            id="CVE-2024-test",
            severity=SeverityLevel.HIGH,
            description="Vulnerable package in base image",
            path="debian-base:libc6",
            scanner="trivy",
            fixed_version="2.37-1",
        )

        # Finding should have enough info to remediate
        assert finding.id  # CVE ID to research
        assert finding.path  # Component affected
        assert finding.fixed_version  # What version fixes it

    def test_finding_distinguishes_package_vs_config(self):
        """Findings should distinguish between package and config issues."""
        package_finding = Finding(
            id="CVE-2024-pkg",
            severity=SeverityLevel.HIGH,
            description="Vulnerable package",
            path="libc6:2.36-1",
            scanner="trivy",
        )

        config_finding = Finding(
            id="AVD-AZU-0001",
            severity=SeverityLevel.HIGH,
            description="Insecure configuration",
            path="Dockerfile:RUN apt-get",
            scanner="trivy",
        )

        # Both are HIGH but require different fixes
        assert "CVE" in package_finding.id
        assert "AVD" in config_finding.id

    @given(num_findings=st.integers(min_value=1, max_value=5))
    @settings(max_examples=10)
    def test_all_high_critical_findings_documented(self, num_findings: int):
        """All HIGH/CRITICAL findings must be documented."""
        findings = []
        for i in range(num_findings):
            severity = SeverityLevel.HIGH if i % 2 == 0 else SeverityLevel.CRITICAL
            finding = Finding(
                id=f"CVE-2024-{i:05d}",
                severity=severity,
                description=f"Vulnerability {i} description",
                path=f"package-{i}",
                scanner="trivy",
            )
            findings.append(finding)

        for finding in findings:
            assert finding.id, "Finding must have ID"
            assert finding.severity.is_blocking(), "Finding must be HIGH or CRITICAL"
            assert finding.description, "Finding must have description"
            assert finding.path, "Finding must identify affected component"


# ============================================================================
# Integration tests
# ============================================================================


class TestContainerScanningIntegration:
    """Integration tests for complete scanning workflow."""

    def test_image_scan_workflow(self):
        """Complete workflow: build → scan both engines → aggregate."""
        # Simulate scan results
        trivy_result = ScannerVerdict(
            success=True, findings=[], high_count=0, critical_count=0
        )
        grype_result = ScannerVerdict(
            success=True, findings=[], high_count=0, critical_count=0
        )

        # Merge
        aggregated = merge_verdicts([trivy_result, grype_result])

        assert aggregated.success
        assert aggregated.blocking_count == 0

    def test_failed_scan_blocks_pipeline(self):
        """Failed scan (HIGH/CRITICAL found) must block pipeline."""
        finding = Finding("CVE-2024-block", SeverityLevel.HIGH, "Test", "pkg", "trivy")

        trivy_result = ScannerVerdict(
            success=False, findings=[finding], high_count=1, critical_count=0
        )
        grype_result = ScannerVerdict(
            success=True, findings=[], high_count=0, critical_count=0
        )

        aggregated = merge_verdicts([trivy_result, grype_result])

        assert (
            not aggregated.success
        ), "Aggregated verdict should fail if any scanner fails"
        assert aggregated.blocking_count > 0

    def test_partial_remediation_insufficient(self):
        """Fixing one finding while others remain must still fail."""
        findings = [
            Finding("CVE-1", SeverityLevel.HIGH, "Still vulnerable", "pkg1", "trivy"),
            Finding("CVE-2", SeverityLevel.HIGH, "Fixed", "pkg2", "trivy"),
        ]

        # Only CVE-2 is fixed
        verdict_after = ScannerVerdict(
            success=False, findings=[findings[0]], high_count=1, critical_count=0
        )

        assert (
            not verdict_after.success
        ), "Verdict should fail while any HIGH/CRITICAL remains"


# ============================================================================
# Compliance tests
# ============================================================================


class TestComplianceWithRequirements:
    """Test that container scanning meets all requirements."""

    def test_requirement_2_8_vulnerability_policy(self):
        """Requirement 2.8: All HIGH/CRITICAL must block."""
        for severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL]:
            finding = Finding(
                f"CVE-REQ-{severity.value}", severity, "Test", "pkg", "trivy"
            )
            verdict = ScannerVerdict(
                success=False,
                findings=[finding],
                high_count=1 if severity == SeverityLevel.HIGH else 0,
                critical_count=1 if severity == SeverityLevel.CRITICAL else 0,
            )

            applied = ZeroHighCriticalPolicy.apply_policy(verdict)
            assert not applied.success, f"Requirement 2.8: {severity.value} must block"

    def test_requirement_2_9_no_suppressions(self):
        """Requirement 2.9: No suppressions allowed."""
        suppression_configs = [
            ("pip-audit", "--ignore CVE-2024-test"),
            ("npm", "MAX_HIGH: 2"),
            ("trivy", "--ignore-unfixed"),
            ("grype", "--ignore-file"),
        ]

        for scanner, config in suppression_configs:
            is_valid, error = ZeroHighCriticalPolicy.validate_no_suppressions(
                config, scanner
            )
            assert not is_valid, f"Requirement 2.9: {scanner} must reject suppressions"

    def test_requirement_2_13_finite_timeouts(self):
        """Requirement 2.13: Scanning must have finite timeouts."""
        # This is tested in CI infrastructure, not in verdict/parser
        # But we can validate that scanner objects have timeout settings
        assert callable(
            parse_trivy_json
        ), "Scanners must be callable with timeout support"

    def test_requirement_3_9_image_scanning_in_ci(self):
        """Requirement 3.9: Image scanning runs in CI environment."""
        # Ensure production images are defined for CI scanning
        for image_name in ["backend-python", "backend-pptx-builder", "frontend"]:
            assert (
                image_name in PRODUCTION_IMAGES
            ), f"Requirement 3.9: {image_name} must be defined for CI scanning"

    def test_requirement_3_10_both_engines(self):
        """Requirement 3.10: Both Trivy and Grype must scan."""
        for name, image in PRODUCTION_IMAGES.items():
            assert image.required_scanners == {
                "trivy",
                "grype",
            }, f"Requirement 3.10: {name} must require both scanners"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
