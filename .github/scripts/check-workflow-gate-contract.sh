#!/bin/bash
#
# Workflow Gate Contract Assertion
#
# Validates that the GitHub Actions workflow (.github/workflows/deploy.yml) enforces
# the deployment quality gate as a mandatory dependency on the path to production.
#
# Contract: Every job on the dependency path from source to `deploy` must transitively
# depend on the `gate` job. This ensures no CI shortcut or refactoring can bypass the
# reusable gate job that validates tests, linting, and security scans.
#
# Exit codes:
#   0 - Contract satisfied, workflow is safe
#   1 - Contract violated, workflow has a bypass route
#

set -euo pipefail

WORKFLOW_FILE="${1:-.github/workflows/deploy.yml}"
VERBOSE="${2:---quiet}"

# Check if yq is available (for robust YAML parsing)
if ! command -v yq &> /dev/null; then
    echo "ERROR: yq is required to parse YAML. Install it with:"
    echo "  Ubuntu/Debian: sudo apt-get install yq"
    echo "  macOS: brew install yq"
    echo "  Or use the Python version: python3 .github/scripts/check-workflow-gate-contract.py"
    exit 1
fi

if [[ ! -f "$WORKFLOW_FILE" ]]; then
    echo "ERROR: Workflow file not found: $WORKFLOW_FILE"
    exit 1
fi

# Extract job names
JOBS=$(yq '.jobs | keys | .[]' "$WORKFLOW_FILE")

# Verify required jobs exist
for required in gate resolve build deploy; do
    if ! echo "$JOBS" | grep -q "^$required\$"; then
        echo "ERROR: Workflow is missing required job: $required"
        exit 1
    fi
done

CONTRACT_OK=true

# Helper function to extract needs for a job
get_job_needs() {
    local job_name="$1"
    yq ".jobs.$job_name.needs // []" "$WORKFLOW_FILE" | \
        yq '.[] | select(. != null)' 2>/dev/null || echo ""
}

# Helper function to check if gate is in transitive dependencies
has_transitive_dependency() {
    local job_name="$1"
    local target="$2"
    local visited=""
    local to_visit="$job_name"
    
    while [[ -n "$to_visit" ]]; do
        local current="${to_visit%% *}"
        to_visit="${to_visit#* }"
        
        if echo "$visited" | grep -q "^$current\$"; then
            continue
        fi
        visited="$visited $current"
        
        if [[ "$current" == "$target" ]] && [[ "$current" != "$job_name" ]]; then
            echo "true"
            return 0
        fi
        
        local needs=$(get_job_needs "$current")
        if [[ -n "$needs" ]]; then
            to_visit="$to_visit $needs"
        fi
    done
    
    echo "false"
    return 1
}

# Contract 1: `build` must directly depend on `gate`
BUILD_NEEDS=$(get_job_needs "build")
if ! echo "$BUILD_NEEDS" | grep -q "^gate\$"; then
    echo "VIOLATION: 'build' job does not directly depend on 'gate'"
    echo "  Current 'build' needs: $(echo "$BUILD_NEEDS" | tr '\n' ' ' | xargs)"
    CONTRACT_OK=false
elif [[ "$VERBOSE" != "--quiet" ]]; then
    echo "✓ 'build' job correctly depends on 'gate'"
fi

# Contract 2: `deploy` must directly depend on `gate` and `build`
DEPLOY_NEEDS=$(get_job_needs "deploy")
if ! echo "$DEPLOY_NEEDS" | grep -q "^gate\$"; then
    echo "VIOLATION: 'deploy' job does not directly depend on 'gate'"
    echo "  Current 'deploy' needs: $(echo "$DEPLOY_NEEDS" | tr '\n' ' ' | xargs)"
    CONTRACT_OK=false
elif [[ "$VERBOSE" != "--quiet" ]]; then
    echo "✓ 'deploy' job correctly depends on 'gate'"
fi

if ! echo "$DEPLOY_NEEDS" | grep -q "^build\$"; then
    echo "VIOLATION: 'deploy' job does not directly depend on 'build'"
    echo "  Current 'deploy' needs: $(echo "$DEPLOY_NEEDS" | tr '\n' ' ' | xargs)"
    CONTRACT_OK=false
elif [[ "$VERBOSE" != "--quiet" ]]; then
    echo "✓ 'deploy' job correctly depends on 'build'"
fi

# Print final result
if [[ "$CONTRACT_OK" == "true" ]]; then
    if [[ "$VERBOSE" != "--quiet" ]]; then
        echo ""
        echo "✓ Workflow gate contract is satisfied"
    fi
    exit 0
else
    echo ""
    echo "✗ Workflow gate contract is VIOLATED"
    exit 1
fi
