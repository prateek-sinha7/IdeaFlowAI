"""
Typed parsers for security scanner outputs.

Each scanner has distinct output format (JSON, SARIF, CSV, custom).
Parsers validate schema/format and fail on malformed/missing reports.
"""

import json

from .scanner_verdict import Finding, ScannerVerdict, SeverityLevel, map_severity


class ParserError(Exception):
    """Raised when scanner output cannot be parsed."""

    pass


def parse_pip_audit_json(content: str) -> ScannerVerdict:
    """
    Parse pip-audit JSON output.

    pip-audit output format:
    {
      "vulnerabilities": [
        {
          "id": "CVE-2024-...",
          "description": "...",
          "fix_available": true|false,
          "fixed_version": "1.2.3" or null,
          "advisory": "...",
          "vulnerability_type": "...",
          "affected_versions": ["<1.0.0"],
          "affected_version_range": "<1.0.0",
          "cvss_v3_score": 7.5,
          "cvss_v2_score": null,
          "service_version": "1.5.0",
          "advisory_url": "https://...",
          "service": "package-name"
        }
      ],
      "scanned_file": "requirements.txt",
      "scanned_version": "...",
      "timestamp": "..."
    }
    """
    if not content or not content.strip():
        return ScannerVerdict(success=False, error="Empty pip-audit report")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ScannerVerdict(
            success=False, error=f"Malformed JSON in pip-audit report: {e}"
        )

    if not isinstance(data, dict):
        return ScannerVerdict(
            success=False,
            error="pip-audit report root must be object",
        )

    vulnerabilities = data.get("vulnerabilities")

    # Real `pip-audit --format json` output does NOT use a flat
    # "vulnerabilities" array. It emits:
    #   {"dependencies": [{"name", "version", "vulns": [...]}], "fixes": [...]}
    # The flat form below is retained because the existing fixtures use it, but
    # the dependency form is what the tool actually produces, and parsing only
    # the invented shape is why this parser previously rejected every real
    # report as "invalid" — which, wired into a gate, would have failed closed
    # on a formatting detail rather than on a vulnerability.
    if vulnerabilities is None and isinstance(data.get("dependencies"), list):
        return _parse_pip_audit_dependency_form(data["dependencies"])

    if vulnerabilities is None:
        return ScannerVerdict(
            success=False,
            error=(
                "pip-audit report has neither a 'vulnerabilities' array nor a "
                "'dependencies' array"
            ),
        )

    if not isinstance(vulnerabilities, list):
        return ScannerVerdict(
            success=False,
            error="pip-audit 'vulnerabilities' must be array",
        )

    findings: list[Finding] = []
    high_count = 0
    critical_count = 0

    for vuln in vulnerabilities:
        if not isinstance(vuln, dict):
            return ScannerVerdict(
                success=False,
                error="Each pip-audit vulnerability must be object",
            )

        # Extract required fields
        vuln_id = vuln.get("id")
        if not vuln_id:
            return ScannerVerdict(
                success=False,
                error="Vulnerability missing 'id' field",
            )

        service = vuln.get("service", "unknown")
        description = vuln.get("description", "")

        # Map CVSS score to severity since pip-audit doesn't provide severity
        # Use conservative mapping: CVSS 7.0+ = HIGH, 9.0+ = CRITICAL
        cvss_v3 = vuln.get("cvss_v3_score")
        if cvss_v3 is not None:
            try:
                score = float(cvss_v3)
                if score >= 9.0:
                    severity = SeverityLevel.CRITICAL
                elif score >= 7.0:
                    severity = SeverityLevel.HIGH
                elif score >= 4.0:
                    severity = SeverityLevel.MEDIUM
                else:
                    severity = SeverityLevel.LOW
            except (ValueError, TypeError):
                severity = SeverityLevel.MEDIUM
        else:
            # No CVSS score, treat unknown conservatively
            severity = SeverityLevel.HIGH

        fixed_version = vuln.get("fixed_version")

        finding = Finding(
            id=vuln_id,
            severity=severity,
            description=description,
            path=service,
            scanner="pip-audit",
            fixed_version=fixed_version,
        )
        findings.append(finding)

        if severity == SeverityLevel.CRITICAL:
            critical_count += 1
        elif severity == SeverityLevel.HIGH:
            high_count += 1

    # Policy: zero HIGH/CRITICAL regardless of fix availability
    success = critical_count == 0 and high_count == 0

    return ScannerVerdict(
        success=success,
        findings=findings,
        high_count=high_count,
        critical_count=critical_count,
    )


def _parse_pip_audit_dependency_form(dependencies: list) -> ScannerVerdict:
    """
    Parse the dependency-keyed form that `pip-audit --format json` really emits.

    Each entry is ``{"name", "version", "vulns": [{"id", "fix_versions",
    "aliases", "description"}]}``. pip-audit does not report a severity or a
    CVSS score, so every finding is classified HIGH: an unclassified dependency
    vulnerability is treated conservatively until it has been triaged, which is
    the fail-closed reading the requirements ask for. Fix availability is
    recorded for remediation guidance but never affects the verdict.
    """
    findings: list[Finding] = []
    high_count = 0

    for dependency in dependencies:
        if not isinstance(dependency, dict):
            return ScannerVerdict(
                success=False,
                error="each pip-audit dependency entry must be an object",
            )

        package = dependency.get("name") or "unknown"
        version = dependency.get("version") or "unknown"
        vulns = dependency.get("vulns") or []
        if not isinstance(vulns, list):
            return ScannerVerdict(
                success=False,
                error=f"pip-audit 'vulns' for {package} must be an array",
            )

        for vuln in vulns:
            if not isinstance(vuln, dict):
                return ScannerVerdict(
                    success=False,
                    error=f"each pip-audit vuln for {package} must be an object",
                )
            vuln_id = vuln.get("id")
            if not vuln_id:
                return ScannerVerdict(
                    success=False,
                    error=f"pip-audit vuln for {package} is missing 'id'",
                )

            fix_versions = vuln.get("fix_versions") or []
            findings.append(
                Finding(
                    id=str(vuln_id),
                    severity=SeverityLevel.HIGH,
                    description=vuln.get("description", ""),
                    path=f"{package}@{version}",
                    scanner="pip-audit",
                    fixed_version=(
                        ", ".join(str(v) for v in fix_versions)
                        if fix_versions
                        else None
                    ),
                )
            )
            high_count += 1

    return ScannerVerdict(
        success=high_count == 0,
        findings=findings,
        high_count=high_count,
        critical_count=0,
    )


def parse_npm_audit_json(content: str) -> ScannerVerdict:
    """
    Parse npm audit JSON output.

    npm audit output format:
    {
      "vulnerabilities": {
        "package-name": {
          "name": "package-name",
          "severity": "high|critical|moderate|low",
          "vulnerabilities": [
            {
              "node_id": "package-name@1.0.0",
              "advisory": 12345,
              "resolved": "1.1.0",
              "...": "..."
            }
          ]
        }
      },
      "metadata": {
        "vulnerabilities": {
          "info": 0,
          "low": 0,
          "moderate": 0,
          "high": 1,
          "critical": 0
        },
        "...": "..."
      }
    }
    """
    if not content or not content.strip():
        return ScannerVerdict(success=False, error="Empty npm audit report")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ScannerVerdict(
            success=False, error=f"Malformed JSON in npm audit report: {e}"
        )

    if not isinstance(data, dict):
        return ScannerVerdict(
            success=False,
            error="npm audit report root must be object",
        )

    vulnerabilities = data.get("vulnerabilities", {})
    if not isinstance(vulnerabilities, dict):
        return ScannerVerdict(
            success=False,
            error="npm audit 'vulnerabilities' must be object",
        )

    findings: list[Finding] = []
    high_count = 0
    critical_count = 0

    for package_name, vuln_info in vulnerabilities.items():
        if not isinstance(vuln_info, dict):
            return ScannerVerdict(
                success=False,
                error=f"Vulnerability info for {package_name} must be object",
            )

        severity_str = vuln_info.get("severity", "unknown")
        try:
            severity = map_severity("npm", severity_str)
        except ValueError:
            return ScannerVerdict(
                success=False,
                error=f"Unknown severity '{severity_str}' in npm audit",
            )

        # Get list of specific vulnerabilities
        vulns = vuln_info.get("vulnerabilities", [])
        if not isinstance(vulns, list):
            vulns = []

        if not vulns:
            # No specific vulnerabilities listed, add package-level finding
            finding = Finding(
                id=f"{package_name}:{severity_str}",
                severity=severity,
                description=vuln_info.get(
                    "description", f"Vulnerability in {package_name}"
                ),
                path=package_name,
                scanner="npm",
            )
            findings.append(finding)

            if severity == SeverityLevel.CRITICAL:
                critical_count += 1
            elif severity == SeverityLevel.HIGH:
                high_count += 1
        else:
            # Add individual vulnerabilities
            for vuln in vulns:
                if not isinstance(vuln, dict):
                    continue

                advisory = vuln.get("advisory")
                node_id = vuln.get("node_id", package_name)
                resolved = vuln.get("resolved")

                finding = Finding(
                    id=str(advisory) if advisory else node_id,
                    severity=severity,
                    description=f"Vulnerability in {node_id}",
                    path=node_id,
                    scanner="npm",
                    fixed_version=resolved,
                )
                findings.append(finding)

                if severity == SeverityLevel.CRITICAL:
                    critical_count += 1
                elif severity == SeverityLevel.HIGH:
                    high_count += 1

    # Policy: zero HIGH/CRITICAL regardless of fix availability
    success = critical_count == 0 and high_count == 0

    return ScannerVerdict(
        success=success,
        findings=findings,
        high_count=high_count,
        critical_count=critical_count,
    )


def parse_trivy_json(content: str, scanner_type: str = "image") -> ScannerVerdict:
    """
    Parse Trivy JSON output (image or config scan).

    Args:
        content: JSON content from Trivy
        scanner_type: "image" or "config"

    Trivy output format:
    {
      "SchemaVersion": 2,
      "Results": [
        {
          "Target": "...",
          "Class": "os-pkg|lang-pkg|config",
          "Type": "alpine|debian|python|...",
          "Vulnerabilities": [
            {
              "VulnerabilityID": "CVE-2024-...",
              "PkgName": "package-name",
              "InstalledVersion": "1.0.0",
              "FixedVersion": "1.1.0",
              "Severity": "CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN",
              "Description": "...",
              "...": "..."
            }
          ],
          "Misconfigurations": [
            {
              "ID": "AVD-...",
              "Title": "...",
              "Description": "...",
              "Severity": "CRITICAL|HIGH|MEDIUM|LOW",
              "...": "..."
            }
          ]
        }
      ]
    }
    """
    if not content or not content.strip():
        return ScannerVerdict(success=False, error=f"Empty Trivy {scanner_type} report")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ScannerVerdict(
            success=False,
            error=f"Malformed JSON in Trivy {scanner_type} report: {e}",
        )

    if not isinstance(data, dict):
        return ScannerVerdict(
            success=False,
            error=f"Trivy {scanner_type} report root must be object",
        )

    results = data.get("Results", [])
    if not isinstance(results, list):
        return ScannerVerdict(
            success=False,
            error=f"Trivy {scanner_type} 'Results' must be array",
        )

    findings: list[Finding] = []
    high_count = 0
    critical_count = 0

    for result in results:
        if not isinstance(result, dict):
            return ScannerVerdict(
                success=False,
                error="Each Trivy result must be object",
            )

        target = result.get("Target", "unknown")

        # Parse vulnerabilities
        vulnerabilities = result.get("Vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            vulnerabilities = []

        for vuln in vulnerabilities:
            if not isinstance(vuln, dict):
                return ScannerVerdict(
                    success=False,
                    error="Each vulnerability must be object",
                )

            vuln_id = vuln.get("VulnerabilityID")
            if not vuln_id:
                return ScannerVerdict(
                    success=False,
                    error="Vulnerability missing 'VulnerabilityID'",
                )

            severity_str = vuln.get("Severity", "UNKNOWN")
            try:
                severity = map_severity("trivy", severity_str)
            except ValueError:
                return ScannerVerdict(
                    success=False,
                    error=f"Unknown severity '{severity_str}' in Trivy report",
                )

            pkg_name = vuln.get("PkgName", "unknown")
            installed_version = vuln.get("InstalledVersion", "")
            fixed_version = vuln.get("FixedVersion")
            description = vuln.get("Description", "")

            path = f"{pkg_name}@{installed_version}" if installed_version else pkg_name

            finding = Finding(
                id=vuln_id,
                severity=severity,
                description=description,
                path=path,
                scanner="trivy",
                fixed_version=fixed_version,
            )
            findings.append(finding)

            if severity == SeverityLevel.CRITICAL:
                critical_count += 1
            elif severity == SeverityLevel.HIGH:
                high_count += 1

        # Parse misconfigurations (IaC)
        if scanner_type == "config":
            misconfigurations = result.get("Misconfigurations", [])
            if not isinstance(misconfigurations, list):
                misconfigurations = []

            for misconfig in misconfigurations:
                if not isinstance(misconfig, dict):
                    return ScannerVerdict(
                        success=False,
                        error="Each misconfiguration must be object",
                    )

                config_id = misconfig.get("ID")
                if not config_id:
                    return ScannerVerdict(
                        success=False,
                        error="Misconfiguration missing 'ID'",
                    )

                severity_str = misconfig.get("Severity", "UNKNOWN")
                try:
                    severity = map_severity("trivy", severity_str)
                except ValueError:
                    return ScannerVerdict(
                        success=False,
                        error=f"Unknown severity '{severity_str}' in Trivy config",
                    )

                title = misconfig.get("Title", "")
                description = misconfig.get("Description", "")

                finding = Finding(
                    id=config_id,
                    severity=severity,
                    description=f"{title}: {description}",
                    path=target,
                    scanner="trivy-config",
                )
                findings.append(finding)

                if severity == SeverityLevel.CRITICAL:
                    critical_count += 1
                elif severity == SeverityLevel.HIGH:
                    high_count += 1

    # Policy: zero HIGH/CRITICAL regardless of fix availability
    success = critical_count == 0 and high_count == 0

    return ScannerVerdict(
        success=success,
        findings=findings,
        high_count=high_count,
        critical_count=critical_count,
    )


def parse_grype_json(content: str) -> ScannerVerdict:
    """
    Parse Grype JSON output.

    Grype output format:
    {
      "matches": [
        {
          "vulnerability": {
            "id": "CVE-2024-...",
            "severity": "critical|high|medium|low|unknown",
            "cvssV3": {
              "score": 7.5,
              "vector": "..."
            },
            "description": "...",
            "fix": {
              "versions": ["1.1.0"],
              "state": "fixed|unknown|wont-fix",
              "url": "https://..."
            }
          },
          "artifact": {
            "id": "package-id",
            "name": "package-name",
            "version": "1.0.0",
            "type": "python|javascript|...",
            "..."
          },
          "..."
        }
      ],
      "metadata": {
        "version": "...",
        "timestamp": "...",
        "...": "..."
      }
    }
    """
    if not content or not content.strip():
        return ScannerVerdict(success=False, error="Empty Grype report")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ScannerVerdict(
            success=False, error=f"Malformed JSON in Grype report: {e}"
        )

    if not isinstance(data, dict):
        return ScannerVerdict(
            success=False,
            error="Grype report root must be object",
        )

    matches = data.get("matches", [])
    if not isinstance(matches, list):
        return ScannerVerdict(
            success=False,
            error="Grype 'matches' must be array",
        )

    findings: list[Finding] = []
    high_count = 0
    critical_count = 0

    for match in matches:
        if not isinstance(match, dict):
            return ScannerVerdict(
                success=False,
                error="Each Grype match must be object",
            )

        vulnerability = match.get("vulnerability")
        if not isinstance(vulnerability, dict):
            return ScannerVerdict(
                success=False,
                error="Match missing 'vulnerability' object",
            )

        vuln_id = vulnerability.get("id")
        if not vuln_id:
            return ScannerVerdict(
                success=False,
                error="Vulnerability missing 'id'",
            )

        severity_str = vulnerability.get("severity", "unknown")
        try:
            severity = map_severity("grype", severity_str)
        except ValueError:
            return ScannerVerdict(
                success=False,
                error=f"Unknown severity '{severity_str}' in Grype report",
            )

        description = vulnerability.get("description", "")
        artifact = match.get("artifact", {})
        pkg_name = artifact.get("name", "unknown")
        version = artifact.get("version", "")

        fix_info = vulnerability.get("fix", {})
        versions = fix_info.get("versions", [])
        fixed_version = versions[0] if versions else None

        path = f"{pkg_name}@{version}" if version else pkg_name

        finding = Finding(
            id=vuln_id,
            severity=severity,
            description=description,
            path=path,
            scanner="grype",
            fixed_version=fixed_version,
        )
        findings.append(finding)

        if severity == SeverityLevel.CRITICAL:
            critical_count += 1
        elif severity == SeverityLevel.HIGH:
            high_count += 1

    # Policy: zero HIGH/CRITICAL regardless of fix availability
    success = critical_count == 0 and high_count == 0

    return ScannerVerdict(
        success=success,
        findings=findings,
        high_count=high_count,
        critical_count=critical_count,
    )


def parse_checkov_json(content: str) -> ScannerVerdict:
    """
    Parse Checkov JSON output (IaC policy scanning).

    Checkov output format:
    {
      "check_type": "terraform|dockerfile|...",
      "summary": {
        "passed": 10,
        "failed": 2,
        "skipped": 0,
        "parsing_errors": 0,
        "resource_count": 12,
        "check_type_to_results": {}
      },
      "results": {
        "passed_checks": [...],
        "failed_checks": [
          {
            "check_id": "CKV_...",
            "check_name": "...",
            "check_result": {
              "result": "failed",
              "evaluated_keys": ["..."]
            },
            "code_block": [...],
            "file_path": "...",
            "file_abs_path": "...",
            "repo_file_path": "...",
            "evaluations": {},
            "check_class": "...",
            "file_line_range": [1, 10],
            "resource": "...",
            "evaluations": {},
            "check_severity": "high|medium|low",
            "bc_check_id": "BC_...",
            "description": "...",
            "severity": "high|medium|low"
          }
        ],
        "skipped_checks": []
      },
      "framework": "terraform|...",
      "runner_filter": {}
    }
    """
    if not content or not content.strip():
        return ScannerVerdict(success=False, error="Empty Checkov report")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ScannerVerdict(
            success=False, error=f"Malformed JSON in Checkov report: {e}"
        )

    if not isinstance(data, dict):
        return ScannerVerdict(
            success=False,
            error="Checkov report root must be object",
        )

    results = data.get("results", {})
    if not isinstance(results, dict):
        return ScannerVerdict(
            success=False,
            error="Checkov 'results' must be object",
        )

    failed_checks = results.get("failed_checks", [])
    if not isinstance(failed_checks, list):
        return ScannerVerdict(
            success=False,
            error="Checkov 'failed_checks' must be array",
        )

    findings: list[Finding] = []
    high_count = 0
    critical_count = 0

    for check in failed_checks:
        if not isinstance(check, dict):
            return ScannerVerdict(
                success=False,
                error="Each failed check must be object",
            )

        check_id = check.get("check_id")
        if not check_id:
            return ScannerVerdict(
                success=False,
                error="Check missing 'check_id'",
            )

        # Checkov uses 'severity' or 'check_severity'
        severity_str = check.get("severity") or check.get("check_severity", "medium")
        try:
            severity = map_severity("checkov", severity_str)
        except ValueError:
            return ScannerVerdict(
                success=False,
                error=f"Unknown severity '{severity_str}' in Checkov report",
            )

        check_name = check.get("check_name", "")
        description = check.get("description", check_name)
        file_path = check.get("file_path", "")
        resource = check.get("resource", "")

        path = f"{file_path}:{resource}" if resource else file_path

        finding = Finding(
            id=check_id,
            severity=severity,
            description=description,
            path=path,
            scanner="checkov",
        )
        findings.append(finding)

        if severity == SeverityLevel.CRITICAL:
            critical_count += 1
        elif severity == SeverityLevel.HIGH:
            high_count += 1

    # Policy: zero HIGH/CRITICAL - Checkov violations are treated as policy failures
    # Note: High/Critical IaC violations block deployment, but this depends on
    # the use case. For now, we apply the same zero-finding policy.
    success = critical_count == 0 and high_count == 0

    return ScannerVerdict(
        success=success,
        findings=findings,
        high_count=high_count,
        critical_count=critical_count,
    )


def parse_gitleaks_json(content: str) -> ScannerVerdict:
    """
    Parse gitleaks JSON output (secret scanning).

    gitleaks output format:
    {
      "Description": "GitLab Personal Access Token",
      "StartLine": 5,
      "EndLine": 5,
      "Match": "glpat-...",
      "Secret": "glpat-...",
      "File": "path/to/file",
      "Commit": "...",
      "Entropy": 3.2,
      "Author": "...",
      "Email": "...",
      "Date": "...",
      "Message": "...",
      "Tags": ["gitlab", "pat"],
      "RuleID": "gitlab-pat"
    }

    When run with --json-report, output is an array of findings.
    """
    if not content or not content.strip():
        # Empty report = success (no secrets found)
        return ScannerVerdict(success=True, findings=[])

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return ScannerVerdict(
            success=False, error=f"Malformed JSON in gitleaks report: {e}"
        )

    # gitleaks can output either array of findings or single finding
    if isinstance(data, dict):
        findings_list = [data]
    elif isinstance(data, list):
        findings_list = data
    else:
        return ScannerVerdict(
            success=False,
            error="gitleaks report must be object or array",
        )

    findings: list[Finding] = []

    for finding_data in findings_list:
        if not isinstance(finding_data, dict):
            return ScannerVerdict(
                success=False,
                error="Each gitleaks finding must be object",
            )

        # gitleaks considers any finding a CRITICAL secret
        rule_id = finding_data.get("RuleID", "unknown-secret")
        description = finding_data.get("Description", "Secret found")
        file_path = finding_data.get("File", "unknown")
        # For gitleaks, treat all findings as CRITICAL
        severity = SeverityLevel.CRITICAL

        # Do not include the actual secret in the path
        path = f"{file_path}:{finding_data.get('StartLine', '?')}"

        finding = Finding(
            id=rule_id,
            severity=severity,
            description=description,
            path=path,
            scanner="gitleaks",
        )
        findings.append(finding)

    # Gitleaks policy: zero secrets
    success = len(findings) == 0

    return ScannerVerdict(
        success=success,
        findings=findings,
        high_count=0,
        critical_count=len(findings),  # All gitleaks findings are treated as critical
    )
