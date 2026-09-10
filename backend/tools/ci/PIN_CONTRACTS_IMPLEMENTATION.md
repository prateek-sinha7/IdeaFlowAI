# Pin and Installer Contracts Implementation

## Overview

This document describes the implementation of four deterministic tooling contracts for the CI pipeline, ensuring reproducible and secure CI evaluations.

**Status**: ✅ Complete with 41 passing tests
**Coverage**: All 4 contracts implemented with comprehensive validation
**INV-3 Preservation**: ✅ Characterization goldens remain byte-identical

## Implemented Contracts

### Contract 1: Tool-Pin (ToolPinValidator)

**Purpose**: Enforce explicit version pinning for all tools in check manifests.

**Rules**:
- Rejects `latest` tag
- Rejects floating ranges (`~X.Y.Z`, `^X.Y.Z`, `>=`, `<=`, etc.)
- Rejects branch references (`main`, `master`, `trunk`, `develop`)
- Requires exact pinned versions (e.g., `1.0.0`)

**Validation Methods**:
- `validate_check_manifest(manifest, location)` - Validates full check manifest structure
- `validate_tool_version(tool_name, version, location)` - Validates individual tool version

**Example**:
```python
validator = ToolPinValidator()
violation = validator.validate_tool_version("ruff", "latest", "pyproject.toml")
# Returns: ToolPinViolation with type LATEST_TAG
```

### Contract 2: Action-Pin (ActionPinValidator)

**Purpose**: Enforce full commit SHA references for GitHub Actions.

**Rules**:
- Requires full 40-character commit SHA (hex)
- Rejects tag references (`v1`, `v2.0`)
- Rejects branch references (`main`, `master`)
- Rejects short SHAs (< 40 characters)
- Rejects missing references (action without `@`)

**Validation Methods**:
- `validate_workflow(workflow_yaml, location)` - Validates full workflow
- `validate_action_reference(action_ref, location)` - Validates single action reference

**Example**:
```python
validator = ActionPinValidator()
violation = validator.validate_action_reference(
    "actions/checkout@b4ffbf834f165fc686d8b07a0f14b482fa080601",
    "workflow.yml"
)
# Returns: None (valid full SHA)
```

### Contract 3: Image-Pin (ImagePinValidator)

**Purpose**: Enforce exact digest pins for container images.

**Rules**:
- Requires `sha256:<64-hex-chars>` digest format
- Rejects mutable tags (`latest`, `main`, `master`, `dev`, `staging`, `nightly`)
- Rejects version tags without digests (`postgres:15.2`)
- Rejects images without tag or digest
- Case-insensitive digest validation

**Validation Methods**:
- `validate_docker_file(dockerfile_content, location)` - Validates Dockerfile FROM directives
- `validate_image_reference(image_ref, location)` - Validates single image reference

**Example**:
```python
validator = ImagePinValidator()
violation = validator.validate_image_reference(
    "nginx:latest",
    "Dockerfile"
)
# Returns: ImagePinViolation with type MUTABLE_TAG
```

### Contract 4: Installer Contracts (InstallerContractValidator)

**Purpose**: Verify that `install_*` callables are pure functions without external dependencies.

**Purity Rules**:
- No network calls (`requests`, `urllib`, `socket`, `http.client`)
- No subprocess execution (`subprocess`, `os.system`, `os.popen`)
- No environment variable writes
- No credential accesses (AWS_, GITHUB_, SONAR_, API_KEY)

**Validation Methods**:
- `validate_installer_function(func_name, func_code, location)` - Validates function source code

**Example**:
```python
validator = InstallerContractValidator()
func_code = """
def install_tool():
    import requests
    requests.get("https://example.com")
"""
violation = validator.validate_installer_function("install_tool", func_code)
# Returns: InstallerContractViolation detecting network call
```

## Aggregate Validation

The `validate_all_pin_contracts()` function validates all four contracts together:

```python
from tools.ci.pin_contracts import validate_all_pin_contracts

all_valid, violations = validate_all_pin_contracts(
    manifest=check_manifest,
    workflow=github_workflow,
    dockerfiles={"Dockerfile": content}
)
```

## Integration with Scope Guard

Pin contracts are integrated into `scope_guard.py` via the `validate_pin_contracts_in_scope()` function, which:
- Validates all GitHub workflows in `.github/workflows/`
- Validates Dockerfile references
- Returns violations for any unpinned tools, actions, or images

## Test Coverage (41 tests)

### Tool-Pin Contract (7 tests)
- Rejects latest tag
- Rejects floating ranges (~, ^, >=, <=, *)
- Accepts exact versions
- Rejects empty versions
- Validates manifest structure
- Property test: all unpinned formats rejected

### Action-Pin Contract (7 tests)
- Requires full SHA
- Rejects tag references
- Rejects branch references
- Rejects short SHAs
- Rejects missing references
- Workflow validation (valid/invalid)
- Property test: all non-SHA refs rejected

### Image-Pin Contract (8 tests)
- Requires digest
- Rejects mutable tags (latest, main, master, nightly, dev, staging)
- Rejects version tags without digest
- Rejects images without tag/digest
- Dockerfile validation (valid/invalid)
- Case-insensitive digest validation
- Property test: all undigested images rejected
- Registry and namespace handling

### Installer Contracts (6 tests)
- Detects network calls (requests, urllib, socket)
- Detects subprocess calls
- Detects env variable writes
- Detects credential access
- Accepts pure functions
- Detects urllib specifically

### Aggregate & Edge Cases (13 tests)
- Aggregate validation valid/invalid
- Action SHA case sensitivity
- Image digest case sensitivity
- Action references with paths
- Images with registry/namespace
- Violation messages include location/details
- Robustness tests

## Requirements Met

| Requirement | Status |
|---|---|
| 2.9 - Frozen dependency setup | ✅ Tool-pin validates frozen setup |
| 2.10 - Pinned runtimes/tools | ✅ Tool-pin enforces exact versions |
| 2.13 - Independent CI checks | ✅ Contracts ensure determinism |
| 2.14 - Repository-managed merge | ✅ Action-pin validates automation |
| 2.16 - Secure GitHub Actions | ✅ Action-pin requires full SHAs |
| 3.10 - Publisher-backed checksums | ✅ Image-pin enforces digests |

## Key Features

1. **Deterministic**: All contracts produce consistent results across runs
2. **Fail-Closed**: Unknown or malformed inputs are rejected by default
3. **Property-Based Testing**: Comprehensive coverage using Hypothesis
4. **Clear Error Messages**: Violations include location, current value, and expected format
5. **Modular**: Each validator can be used independently or together
6. **Extensible**: New validators can be added following the same pattern

## Example Usage

```python
# Individual validators
tool_validator = ToolPinValidator()
if tool_validator.validate_check_manifest(manifest):
    print("All tools properly pinned!")

# Aggregate validation
all_valid, violations = validate_all_pin_contracts(manifest, workflow, dockerfiles)
if not all_valid:
    for violation in violations:
        print(f"ERROR: {violation.message}")
```

## References

- Requirements: specs/003-workflow-engine-decoupling/ci-pipeline-remediation/plan.md section 3.8
- Contracts: Tool-pin, Action-pin, Image-pin, Installer-contract
- Test file: backend/tests/ci/test_ci_pin_contracts.py (41 tests)
