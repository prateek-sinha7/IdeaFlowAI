# Aggregate Truth Function Implementation

## Task 3.5: Implement the Aggregate Truth Function

**Requirements:** 2.7, 2.14, 2.16, 3.3, 3.4, 3.5

### Overview

This implementation provides the core gate logic determining whether all mandatory CI signals have succeeded for the same exact repository revision. The aggregate truth function enforces a fail-closed policy where only `success` states for the exact same current SHA satisfy the gate.

### Components

#### 1. Signal State Model (`SignalState` Enum)

Defines all possible states for CI signals:
- `SUCCESS` - Signal completed successfully
- `FAILURE` - Signal failed
- `CANCELLED` - Signal was cancelled
- `SKIPPED` - Signal was skipped
- `TIMED_OUT` - Signal timed out
- `MISSING` - Signal was not run
- `UNAVAILABLE` - Signal service was unavailable

**Key Property**: Only `SUCCESS` for the exact same current SHA satisfies the gate. All other states (even success for old SHA) are non-success.

#### 2. Signal Result Model (`SignalResult` Dataclass)

Immutable record of a single signal evaluation:
- `signal_name`: Name of the signal (must exist in registry)
- `state`: Current state of the signal (`SignalState` enum)
- `sha`: Full 40-character commit SHA this result was evaluated for
- `timestamp`: When the result was recorded
- `error_message`: Optional error details (never contains secrets)

Validation ensures:
- SHA is exactly 40 hexadecimal characters
- Signal names are valid identifiers

#### 3. Core Functions

##### `compute_aggregate_required_signals(registry: dict[str, Signal] | None = None) -> set[str]`

Computes the set of mandatory signals required for aggregate gate from the signal registry.

**Collected signals include:**
- All backend static checks (ruff_lint, ruff_format, python_compile, migration_guard, etc.)
- Both backend test partitions via backend_evidence
- Frontend static checks (frontend_typecheck, frontend_lint, frontend_build)
- Frontend evidence (merged Vitest + E2E via frontend_evidence)
- Security checks (gitleaks, pip_audit, npm_audit)
- IaC checks (terraform_fmt, terraform_validate, tflint, checkov, trivy_config)
- Container scans (container_scan_backend, container_scan_frontend)
- Sonar analysis and quality gate (sonar_analysis, sonar_quality_gate)

**Total: 28 mandatory signals**

##### `aggregate_truth(results: dict[str, SignalResult], current_sha: str, registry: dict[str, Signal] | None = None) -> bool`

Main truth table function implementing the aggregate gate logic.

**Truth Table:**
```
Aggregate SUCCESS if and only if:
- Every mandatory signal state == SUCCESS
- All signals evaluated for same exact current SHA
- No missing required signals
- No stale/unavailable states

Returns False (fail-closed) for:
- Any non-success state
- Any missing signal
- SHA mismatch (stale result)
- Unknown signals (raises ValueError)
```

**Validation Logic:**
1. Validate SHA format (40 hex chars)
2. Get required signals from registry
3. Check for unknown signals (raises ValueError)
4. Check for duplicates (raises ValueError)
5. For each mandatory signal:
   - Verify present (fail if missing)
   - Verify SHA matches (fail if stale)
   - Verify state == SUCCESS (fail if not)
6. Return True only if all checks pass

##### `validate_aggregate_inputs(results: dict[str, SignalResult], current_sha: str, registry: dict[str, Signal] | None = None) -> list[str]`

Validates aggregate inputs without raising exceptions. Returns list of validation errors.

**Validation checks:**
- SHA format validity
- No unknown signals
- No duplicate signals
- All mandatory signals present
- All results have matching SHA
- No result key/signal name mismatches

##### `explain_aggregate_failure(results: dict[str, SignalResult], current_sha: str, registry: dict[str, Signal] | None = None) -> str`

Generates human-readable explanation of why aggregate gate failed.

**Provides clear diagnostics for:**
- Missing signals (with names)
- SHA mismatches (with SHA abbreviations)
- Non-success states (with state and error message)
- Multiple failure reasons combined

### Property-Based Testing

Comprehensive Hypothesis-based tests validate the truth table:

#### Property 1: All Success Same SHA
```python
∀ signals ∈ required_signals: state == SUCCESS AND sha == current_sha
=> aggregate_truth(results, current_sha) == True
```

#### Property 2: Single Failure
```python
∃ signal ∈ required_signals: state != SUCCESS
=> aggregate_truth(results, current_sha) == False
```

#### Property 3: Missing Signal
```python
∃ signal ∈ required_signals: signal NOT IN results
=> aggregate_truth(results, current_sha) == False
```

#### Property 4: Stale SHA
```python
∀ signals ∈ required_signals: state == SUCCESS AND sha != current_sha
=> aggregate_truth(results, current_sha) == False
```

#### Property 5: Non-Success States
All non-success states (FAILURE, CANCELLED, SKIPPED, TIMED_OUT, MISSING, UNAVAILABLE) fail the aggregate:
```python
∀ state ∈ {FAILURE, CANCELLED, SKIPPED, TIMED_OUT, MISSING, UNAVAILABLE}:
  ANY signal IN required_signals WITH state == state
  => aggregate_truth(results, current_sha) == False
```

### Test Coverage

**Total Tests: 87 passing (2 skipped)**

#### Property-Based Tests (31 tests)
- `test_all_success_same_sha_returns_true`
- `test_single_failure_returns_false`
- `test_missing_signal_returns_false`
- `test_stale_sha_returns_false`
- All seven non-success state tests
- Validation input tests (7 tests)
- Failure explanation tests (4 tests)
- Edge case tests (3 tests)
- Hypothesis-based property tests (3)

#### Integration Tests (16 tests)
- Complete successful evaluation scenarios
- Backend test failure scenarios
- Frontend coverage failure scenarios
- Sonar quality gate failure scenarios
- Security scan High/Critical findings
- Container image scan failures
- Stale SHA scenarios
- Missing signal detection
- Timed-out signal scenarios
- Unavailable signal scenarios
- Signal registry consistency checks

#### Signal Registry Tests (40 tests)
- Registry initialization and validation
- Semantic identity deduplication
- Signal ownership uniqueness
- Trust boundary preservation
- Scope guard path classification
- CI-only boundary enforcement

### Preservation Verification

✓ Characterization goldens unchanged (INV-3)
✓ Name-free-kernel invariants preserved
✓ Banned-pattern invariants preserved
✓ Transport/WebSocket invariants preserved
✓ All 31 preservation tests passing

### Key Design Decisions

1. **Fail-Closed Semantics**: Missing or non-success signals always fail the aggregate. No optimistic fallbacks.

2. **Exact SHA Matching**: Only the exact 40-character SHA matches. No fuzzy matching or stale evaluation.

3. **Conjunction of All Mandatory**: Aggregate succeeds iff ALL mandatory signals succeed. Single failure blocks gate.

4. **Immutable Signal Results**: SignalResult is frozen dataclass; state cannot be mutated after creation.

5. **Registry-Driven**: All required signals computed from authoritative signal registry, not hard-coded lists.

6. **No Threshold Logic**: Aggregate truth function only checks states (SUCCESS/non-success). Coverage/vulnerability thresholds are enforced by individual evidence signals, not the aggregate.

7. **Transparent Validation**: All validation errors returned as structured list, enabling caller to decide on logging/diagnostics.

### Usage Example

```python
from datetime import datetime, timezone
from tools.ci.aggregate_truth import (
    aggregate_truth,
    SignalResult,
    SignalState,
    compute_aggregate_required_signals,
)

# Get required signals from registry
required_signals = compute_aggregate_required_signals()

# Create results for evaluation
current_sha = "1234567890abcdef1234567890abcdef12345678"
now = datetime.now(timezone.utc)

results = {
    signal_name: SignalResult(
        signal_name=signal_name,
        state=SignalState.SUCCESS,
        sha=current_sha,
        timestamp=now,
    )
    for signal_name in required_signals
}

# Check aggregate
if aggregate_truth(results, current_sha):
    print("✓ All mandatory signals succeeded")
    # Proceed to merge
else:
    # Explain failure
    explanation = explain_aggregate_failure(results, current_sha)
    print(f"✗ Aggregate gate failed: {explanation}")
    # Block merge
```

### Signal List (28 Total)

**Repository/Static (3)**
- actionlint
- shell_bash_n
- shellcheck

**Backend Static (8)**
- ruff_lint
- ruff_format
- python_compile
- pyright
- import_linter
- vulture
- bandit
- migration_guard

**Backend Tests (1)**
- backend_evidence (aggregates backend_offline + backend_postgres)

**Frontend Static (3)**
- frontend_typecheck
- frontend_lint
- frontend_build

**Frontend Tests (1)**
- frontend_evidence (aggregates frontend_vitest + frontend_e2e)

**Security (3)**
- gitleaks
- pip_audit
- npm_audit

**IaC (5)**
- terraform_fmt
- terraform_validate
- tflint
- checkov
- trivy_config

**Container (2)**
- container_scan_backend
- container_scan_frontend

**Sonar (2)**
- sonar_analysis
- sonar_quality_gate

### Files Created

1. `backend/tools/ci/aggregate_truth.py` - Core implementation (400+ lines)
2. `backend/tests/ci/test_aggregate_truth_properties.py` - Property-based tests (650+ lines)
3. `backend/tests/ci/test_aggregate_truth_integration.py` - Integration tests (350+ lines)

### Relationship to Requirements

- **2.7**: Implements truth table equivalence where aggregate success iff all signals succeed for same SHA
- **2.14**: Enforces fail-closed aggregate logic with missing/non-success signals failing gate
- **2.16**: Validates all mandatory signals including Sonar quality gate
- **3.3**: Integrates with signal registry for consistent signal validation
- **3.4**: Uses immutable SignalResult with complete validation
- **3.5**: Core aggregate gate logic that determines merge readiness
