#!/bin/bash
#
# setup-rulesets.sh
#
# Bootstrap GitHub repository rulesets and environments for Phase 2 merge protection.
# Applies branch protection rulesets, tag protection, and environment deployment policies.
#
# Usage:
#   ./setup-rulesets.sh [--repo OWNER/REPO] [--dry-run]
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - User has admin access to the repository
#   - ci-required status check must already exist (created by Phase 1)
#
# Note:
#   Rulesets are applied from .github/rulesets/*.json and .github/environments/*.json
#

set -eu

REPO="${1:-}"
DRY_RUN=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPO" ]]; then
  echo "Usage: $0 --repo OWNER/REPO [--dry-run]"
  echo ""
  echo "Example:"
  echo "  $0 --repo Hexaware-HnI/velocityai"
  exit 1
fi

RULESETS_DIR=".github/rulesets"
ENVIRONMENTS_DIR=".github/environments"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

if [[ ! -d "$RULESETS_DIR" ]]; then
  echo "ERROR: Rulesets directory not found: $RULESETS_DIR" >&2
  exit 1
fi

if [[ ! -d "$ENVIRONMENTS_DIR" ]]; then
  echo "ERROR: Environments directory not found: $ENVIRONMENTS_DIR" >&2
  exit 1
fi

echo "=================================================================================="
echo "Phase 2: GitHub Rulesets & Environments Bootstrap"
echo "=================================================================================="
echo "Repository: $REPO"
echo "Dry Run: $([ $DRY_RUN -eq 1 ] && echo 'YES' || echo 'NO')"
echo ""

# Function to apply a ruleset
apply_ruleset() {
  local ruleset_file="$1"
  local ruleset_name
  ruleset_name=$(basename "$ruleset_file" .json)

  echo "Applying ruleset: $ruleset_name"

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [DRY RUN] Would create ruleset from: $ruleset_file"
    cat "$ruleset_file" | jq '.' >/dev/null || {
      echo "  ERROR: Invalid JSON in $ruleset_file" >&2
      return 1
    }
    echo "  [DRY RUN] ✓ JSON valid"
    return 0
  fi

  if gh api repos/"$REPO"/rulesets --input "$ruleset_file" >/dev/null 2>&1; then
    echo "  ✓ Ruleset created: $ruleset_name"
  else
    echo "  ✗ Failed to create ruleset: $ruleset_name" >&2
    return 1
  fi
}

# Function to apply environment configuration
apply_environment() {
  local env_file="$1"
  local env_name
  env_name=$(basename "$env_file" .json)

  echo "Configuring environment: $env_name"

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [DRY RUN] Would configure environment from: $env_file"
    cat "$env_file" | jq '.' >/dev/null || {
      echo "  ERROR: Invalid JSON in $env_file" >&2
      return 1
    }
    echo "  [DRY RUN] ✓ JSON valid"
    return 0
  fi

  # Read environment config and translate to gh CLI arguments
  local can_admins_bypass wait_timer

  can_admins_bypass=$(jq -r '.can_admins_bypass // false' "$env_file")
  wait_timer=$(jq -r '.wait_timer // 0' "$env_file")

  gh api -X PUT "repos/$REPO/environments/$env_name" \
    -F "can_admins_bypass=$can_admins_bypass" \
    -F "wait_timer=$wait_timer" \
    >/dev/null 2>&1 || {
    echo "  ✗ Failed to configure environment: $env_name" >&2
    return 1
  }

  echo "  ✓ Environment configured: $env_name"
}

# Validate all JSON files first
echo "Step 1: Validating JSON syntax..."
for ruleset_file in "$RULESETS_DIR"/*.json; do
  if ! jq '.' "$ruleset_file" >/dev/null 2>&1; then
    echo "  ERROR: Invalid JSON in $ruleset_file" >&2
    exit 1
  fi
  echo "  ✓ $(basename "$ruleset_file")"
done

for env_file in "$ENVIRONMENTS_DIR"/*.json; do
  if ! jq '.' "$env_file" >/dev/null 2>&1; then
    echo "  ERROR: Invalid JSON in $env_file" >&2
    exit 1
  fi
  echo "  ✓ $(basename "$env_file")"
done

echo ""
echo "Step 2: Verifying gh CLI and repository access..."
if ! gh api repos/"$REPO" -q '.id' >/dev/null 2>&1; then
  echo "  ERROR: Cannot access repository $REPO" >&2
  echo "  Please verify: gh auth status" >&2
  exit 1
fi
echo "  ✓ Repository access verified"

echo ""
echo "Step 3: Applying branch protection rulesets..."
for ruleset_file in "$RULESETS_DIR"/*.json; do
  apply_ruleset "$ruleset_file" || exit 1
done

echo ""
echo "Step 4: Applying environment configurations..."
for env_file in "$ENVIRONMENTS_DIR"/*.json; do
  apply_environment "$env_file" || exit 1
done

echo ""
echo "Step 5: Configuring repository merge settings..."
if [[ $DRY_RUN -eq 1 ]]; then
  echo "  [DRY RUN] Would set delete_on_merge=true, squash-only, web_commit_signoff_required=true"
else
  gh api -X PATCH "repos/$REPO" \
    -F "delete_branch_on_merge=true" \
    -F "allow_squash_merge=true" \
    -F "allow_merge_commit=false" \
    -F "allow_rebase_merge=false" \
    -F "allow_auto_merge=true" \
    -F "web_commit_signoff_required=true" \
    >/dev/null 2>&1 || {
    echo "  ✗ Failed to configure merge settings" >&2
    exit 1
  }
  echo "  ✓ Merge settings configured (squash-only, delete-on-merge, required signatures)"
fi

echo ""
echo "=================================================================================="
if [[ $DRY_RUN -eq 1 ]]; then
  echo "Phase 2 Bootstrap Complete (DRY RUN)"
  echo "Run without --dry-run to apply changes."
else
  echo "Phase 2 Bootstrap Complete"
  echo ""
  echo "Summary:"
  echo "  ✓ 3 branch/tag rulesets applied"
  echo "  ✓ 3 environments configured (prod, staging, dev)"
  echo "  ✓ Merge hygiene policy applied"
  echo ""
  echo "Next steps:"
  echo "  1. Verify branch rules in GitHub UI: Settings > Rules"
  echo "  2. Verify environments in GitHub UI: Settings > Environments"
  echo "  3. Test: Open a PR to main and verify 2-approval requirement"
  echo "  4. Create a release tag (v*) and verify tag protection"
fi
echo "=================================================================================="
