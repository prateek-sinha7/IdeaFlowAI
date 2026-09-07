# Scanner Verdict Implementation — Task 3.6

## Overview

Implements fail-closed scanner report parsing and zero High/Critical vulnerability policy for all security scanners. Parsers validate schema/format and extract findings with consistent severity classification.

**Validates: Requirements 2.8, 2.9, 3.9, 3.15**

## Files Implemented

### 1. `scanner_verdict.py`
Core data models for vulnerability findings and verdict computation.

**Classes:**
- `SeverityLevel` enum: CRITICAL, HIGH, MEDIUM, LOW, INFO
- `Finding` dataclass: Represents a single security finding with id, severity, description, path, scanner, fixed_version
- `ScannerVerdict` dataclass: Complete verdict for a scanner report with success flag, findings list, high/critical counts

**Key Functions:**
- `map_severity(scanner_name, raw_severity) -> SeverityLevel`: Normalize scanner-specific severity strings (e.g., npm "moderate" → MEDIUM)
- `SeverityLevel.is_blocking() -> bool`: Check if severity is HIGH or CRITICAL

**Features:**
- Type-safe representation of all security findings
- Support for all scanner-specific severity strings
- Blocking count aggregation for policy evaluation

### 2. `scanner_parsers.py`
Fail-closed parsers for all 7 security scanners.

**Parsers:**
1. `parse_pip_audit_json(content) -> ScannerVerdict`
   - Validates JSON schema
   - Maps CVSS scores to severity (9.0+ → CRITICAL, 7.0+ → HIGH)
   - Extracts CVE ID, affected package, description
   - Fails on malformed JSON, missing fields, or non-array vulnerabilities

2. `parse_npm_audit_json(content) -> ScannerVerdict`
   - Validates npm audit JSON structure
   - Maps npm severity (critical/high/moderate/low) to standard levels
   - Extracts package names and advisory IDs
   - Fails on invalid format or unexpected structure

3. `parse_trivy_json(content, scanner_type) -> ScannerVerdict`
   - Handles both image and config scan formats
   - Extracts vulnerabilities and misconfigurations
   - Maps Trivy severity including UNKNOWN (treated conservatively as HIGH)
   - Parses target, package, version, fixed version

4. `parse_grype_json(content) -> ScannerVerdict`
   - Parses multi-format vulnerability database
   - Extracts CVSS scores and fix information
   - Maps severity and handles unknown cases
   - Validates all required fields

5. `parse_checkov_json(content) -> ScannerVerdict`
   - Parses IaC policy violations
   - Handles failed_checks with severity classification
   - Extracts file path, resource, and policy ID
   - Validates check structure

6. `parse_gitleaks_json(content) -> ScannerVerdict`
   - Parses secret scan findings
   - Treats all findings as CRITICAL severity
   - Handles both single finding and array formats
   - Empty report = success (no secrets found)

**Common Parser Features:**
- Empty/missing reports → failure (not attempted) 
- Malformed JSON → failure with error message
- Missing required fields → failure with descriptive error
- Invalid severity → failure (not silent downgrade)
- No suppression/baseline/ignore flags allowed

### 3. `scanner_policy.py`
Policy enforcement for zero High/Critical findings.

**Classes:**
- `ZeroHighCriticalPolicy`: Implements zero-finding policy

**Key Functions:**
- `compute_verdict(findings) -> bool`: Returns True only if zero HIGH/CRITICAL
- `validate_no_suppressions(report_content, scanner_name) -> tuple[bool, str]`: Detects suppression patterns (--ignore, MAX_HIGH, --ignore-unfixed, etc.)
- `apply_policy(verdict) -> ScannerVerdict`: Apply policy to verdict (documentation function)
- `validate_no_severity_exceptions(findings) -> tuple[bool, List[str]]`: Reject findings with waiver/exception markers
- `merge_verdicts(verdicts) -> ScannerVerdict`: Aggregate multiple scanner verdicts

**Policy Enforcement:**
- No exceptions for "fix available" or "actionability"
- No time-bound waivers ("exception granted until...")
- No baseline-based thresholds
- All HIGH/CRITICAL findings block CI

## Test Coverage

**File:** `tests/ci/test_scanner_verdict_properties.py`
**Test Count:** 40 tests across 11 test classes

### Test Classes:

1. **TestSeverityMapping** (2 tests)
   - Severity normalization across scanners
   - Blocking severity classification

2. **TestPipAuditParser** (7 tests)
   - Empty/malformed report handling
   - CVSS score mapping to severity
   - Missing field validation

3. **TestNpmAuditParser** (5 tests)
   - Severity classification (including "moderate")
   - HIGH/CRITICAL blocking
   - Structure validation

4. **TestTrivyParser** (5 tests)
   - Image and config scan parsing
   - Severity classification
   - Misconfiguration handling

5. **TestGrypeParser** (3 tests)
   - Multi-format parsing
   - Severity classification
   - Empty matches handling

6. **TestCheckovParser** (2 tests)
   - IaC policy violation parsing
   - HIGH severity blocking

7. **TestGitleaksParser** (3 tests)
   - Secret finding classification
   - Multiple secrets handling
   - All findings treated as CRITICAL

8. **TestZeroHighCriticalPolicy** (3 tests)
   - Policy blocks HIGH/CRITICAL
   - Policy allows MEDIUM/LOW/INFO
   - Suppression pattern detection

9. **TestMalformedReports** (4 tests)
   - Null/invalid structure handling
   - Invalid JSON across all parsers
   - Error message generation

10. **TestVerdictMerging** (3 tests)
    - Successful merging
    - Failure propagation
    - Finding aggregation

11. **TestSeverityExceptionValidation** (2 tests)
    - Waived finding detection
    - Exception marker detection

### Property-Based Testing:
- Hypothesis strategies for severity levels and findings
- Generated test data for:
  - All HIGH/CRITICAL combinations
  - Missing/malformed reports
  - Edge case severities
  - Suppression patterns

## Key Constraints Met

✅ **Fail-Closed**: Malformed/missing/timed-out reports = non-success
✅ **Zero High/Critical**: Any HIGH or CRITICAL finding → failure
✅ **No Suppressions**: Reject baseline/ignore flags, waivers, time-bound exceptions
✅ **No Actionability Filters**: Policy applies regardless of fix availability
✅ **Type Safety**: All fields validated before use
✅ **Scanner Coverage**: All 7 scanners (pip-audit, npm, Trivy, Grype, Checkov, gitleaks)
✅ **Schema Validation**: Each parser validates its specific output format
✅ **Error Messages**: Clear, actionable error messages for failures

## Usage Examples

```python
from agents.ci import (
    parse_pip_audit_json,
    parse_npm_audit_json,
    ZeroHighCriticalPolicy,
    merge_verdicts,
)

# Parse pip-audit report
pip_verdict = parse_pip_audit_json(pip_output_json)
if not pip_verdict.success:
    print(f"Pip audit failed: {pip_verdict.error}")

# Parse npm audit report
npm_verdict = parse_npm_audit_json(npm_output_json)

# Merge verdicts from multiple scanners
aggregate = merge_verdicts([pip_verdict, npm_verdict])

# Check policy
if aggregate.has_blocking_findings():
    print(f"Found {aggregate.blocking_count} HIGH/CRITICAL findings")

# Validate no suppressions
is_valid, msg = ZeroHighCriticalPolicy.validate_no_suppressions(
    report_content, "pip-audit"
)
```

## Implementation Notes

1. **Conservative Severity Mapping**: Unknown/unmapped severities default to HIGH for safety
2. **CVSS Scoring**: pip-audit lacks severity, so CVSS used: 9.0+ → CRITICAL, 7.0+ → HIGH
3. **gitleaks Special Handling**: All secrets treated as CRITICAL, empty report = success
4. **Npm Terminology**: npm uses "moderate" for what other tools call "medium"
5. **Path Normalization**: Parsers extract logical paths without secrets or absolute paths
6. **Idempotent Parsing**: Same report always produces same verdict
7. **Early Failure**: Parsers fail on first schema violation, not after accumulating errors

## Design Decisions

- **Typed Data Classes**: Enables static type checking and validation
- **Separate Policy Module**: Policy enforced independently from parsing
- **Strict Validation**: No silent conversions or best-effort parsing
- **Scanner-Specific Details**: Each parser handles scanner-specific formats without generic fallback
- **Merging Support**: Enables aggregate verdict across multiple scanners

## Future Extensions

- Custom rule/exception namespace validation (separate from software vulnerability policy)
- SARIF format support for additional scanners
- Artifact tracking and evidence binding
- Remediation suggestion aggregation
- Time-based remediation tracking (separate from pass/fail policy)
