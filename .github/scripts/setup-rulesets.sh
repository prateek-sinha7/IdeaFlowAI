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
# Prerequisites: gh (authenticated, admin), jq
#   - gh CLI installed and authenticated
#   - jq installed and on PATH (every API response below is parsed with jq)
#   - User has admin access to the repository
#   - ci-required status check must already exist (created by Phase 1)
#
# Note:
#   Rulesets are applied from .github/rulesets/*.json and .github/environments/*.json
#

# `pipefail` matters here: several checks below are `cmd | jq`-shaped, and without
# it a failure on the LEFT of a pipe is invisible — the pipeline's status is the
# last command's, so a `gh api` that failed while `jq` succeeded reported success.
set -euo pipefail

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

# Function to apply a ruleset — IDEMPOTENT: update in place if it already exists.
#
# This used to unconditionally POST to /rulesets, which CREATES. Re-running the
# script against a configured repository therefore either failed on a duplicate
# name or, worse, produced a SECOND ruleset with the same name and overlapping
# conditions — two rulesets both claiming refs/heads/main, where the effective
# policy is the union and neither is obviously the live one. Editing a JSON file
# here and re-running then had no visible effect on the ruleset anyone was
# reading.
#
# Now: look the name up, PUT to update it if present, POST to create it if not.
# The `name` comes from the JSON's own `.name` field, not the filename — that is
# what GitHub matches on (main.json declares "main-production-protection").
apply_ruleset() {
  local ruleset_file="$1"
  local ruleset_name existing_id
  ruleset_name=$(jq -r '.name' "$ruleset_file")

  if [[ -z "$ruleset_name" || "$ruleset_name" == "null" ]]; then
    echo "  ERROR: $ruleset_file has no .name field; cannot match it against existing rulesets" >&2
    return 1
  fi

  echo "Applying ruleset: $ruleset_name ($(basename "$ruleset_file"))"

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [DRY RUN] Would create-or-update ruleset '$ruleset_name' from: $ruleset_file"
    return 0
  fi

  # `|| true` guards ONLY the lookup: a repository with no rulesets yet is the
  # normal first-run case and must not abort. A genuine API failure leaves
  # existing_id empty and the POST below then reports the real error.
  existing_id="$(
    gh api "repos/${REPO}/rulesets" --paginate \
      -q ".[] | select(.name == \"${ruleset_name}\") | .id" 2>/dev/null || true
  )"

  # More than one match means the pre-idempotency version of this script already
  # created duplicates. Refuse to guess which one to update.
  if [[ "$(printf '%s\n' "$existing_id" | grep -c '[0-9]')" -gt 1 ]]; then
    echo "  ✗ Multiple rulesets are named '$ruleset_name' (ids: $(echo "$existing_id" | tr '\n' ' '))." >&2
    echo "    Delete the extras in Settings > Rules, then re-run." >&2
    return 1
  fi

  if [[ -n "$existing_id" ]]; then
    if gh api -X PUT "repos/${REPO}/rulesets/${existing_id}" --input "$ruleset_file" >/dev/null; then
      echo "  ✓ Ruleset updated: $ruleset_name (id $existing_id)"
    else
      echo "  ✗ Failed to update ruleset: $ruleset_name (id $existing_id)" >&2
      return 1
    fi
  else
    if gh api -X POST "repos/${REPO}/rulesets" --input "$ruleset_file" >/dev/null; then
      echo "  ✓ Ruleset created: $ruleset_name"
    else
      echo "  ✗ Failed to create ruleset: $ruleset_name" >&2
      return 1
    fi
  fi
}

# Resolve a reviewer entry from an environment JSON into an API actor id.
#
# Emits "<Type> <id>" on stdout, or nothing plus a non-zero status when the
# reviewer cannot be resolved. A Team is looked up by slug in the organisation
# that owns $REPO; a User by login.
resolve_reviewer() {
  local reviewer_type="$1" reviewer_ref="$2" org id
  org="${REPO%%/*}"

  case "$reviewer_type" in
    Team)
      if ! id="$(gh api "orgs/${org}/teams/${reviewer_ref}" -q '.id' 2>/dev/null)"; then
        echo "  ✗ Team '${org}/${reviewer_ref}' does not exist." >&2
        echo "    It is named as a required reviewer, so this environment cannot" >&2
        echo "    be configured as declared. Create the team (Settings > Teams)," >&2
        echo "    or remove it from the environment JSON — but do not leave the" >&2
        echo "    file claiming a protection that cannot be applied." >&2
        return 1
      fi
      ;;
    User)
      if ! id="$(gh api "users/${reviewer_ref}" -q '.id' 2>/dev/null)"; then
        echo "  ✗ User '${reviewer_ref}' does not exist." >&2
        return 1
      fi
      ;;
    *)
      echo "  ✗ Unknown reviewer type '${reviewer_type}' (expected Team or User)." >&2
      return 1
      ;;
  esac

  printf '%s %s\n' "$reviewer_type" "$id"
}

# Function to apply environment configuration.
#
# F-14: this used to send ONLY `can_admins_bypass` and `wait_timer`, as two `-F`
# form fields. `reviewers` and `deployment_branch_policy` are NESTED JSON and were
# never sent at all — so every protection the environment JSONs declare was
# silently discarded on every run. The live dev/stage/prod environments had ZERO
# protection rules and a null branch policy while the committed files described
# required reviewers and branch restrictions, and `deploy.yml`'s header asserted
# that "Prod additionally requires required-reviewer approval on the `prod` GitHub
# Environment" — which was not true of the live repository.
#
# It also ended in `>/dev/null 2>&1`, which threw away the API's error body, so the
# only diagnostic on failure was "Failed to configure environment: prod".
#
# Now: build one JSON payload, resolve every reviewer to a real actor id (failing
# loudly if the team or user does not exist), and PUT it with stderr preserved.
apply_environment() {
  local env_file="$1"
  local env_name
  env_name=$(basename "$env_file" .json)

  echo "Configuring environment: $env_name"

  local wait_timer prevent_self_review protected_branches custom_branch_policies
  wait_timer="$(jq -r '.wait_timer // 0' "$env_file")"
  # `can_admins_bypass: false` means an admin may NOT approve their own
  # deployment, which is what `prevent_self_review` expresses in the API.
  prevent_self_review="$(jq -r 'if (.can_admins_bypass // true) then false else true end' "$env_file")"
  protected_branches="$(jq -r '.deployment_branch_policy.protected_branches // false' "$env_file")"
  custom_branch_policies="$(jq -r '.deployment_branch_policy.custom_branch_policies // false' "$env_file")"

  # The API requires EXACTLY ONE of these to be true when a branch policy is set,
  # and rejects the pair otherwise. Catch it here, where the file name is in scope.
  if [[ "$protected_branches" == "true" && "$custom_branch_policies" == "true" ]]; then
    echo "  ✗ $env_name: deployment_branch_policy cannot set both protected_branches" >&2
    echo "    and custom_branch_policies. Choose one." >&2
    return 1
  fi

  # Resolve reviewers before writing anything, so a missing team aborts the whole
  # environment rather than applying a partially-protected configuration.
  local reviewers_json='[]'
  local count
  count="$(jq -r '(.reviewers // []) | length' "$env_file")"
  if [[ "$count" -gt 0 ]]; then
    local i type ref resolved actor_type actor_id
    reviewers_json='[]'
    for ((i = 0; i < count; i++)); do
      type="$(jq -r ".reviewers[$i].type" "$env_file")"
      ref="$(jq -r ".reviewers[$i].id" "$env_file")"
      if ! resolved="$(resolve_reviewer "$type" "$ref")"; then
        return 1
      fi
      actor_type="${resolved%% *}"
      actor_id="${resolved##* }"
      reviewers_json="$(
        jq -c --arg t "$actor_type" --argjson i "$actor_id" \
          '. + [{type: $t, id: $i}]' <<<"$reviewers_json"
      )"
      echo "  resolved reviewer: ${actor_type} ${ref} -> ${actor_id}"
    done
  fi

  local branch_policy='null'
  if [[ "$protected_branches" == "true" || "$custom_branch_policies" == "true" ]]; then
    branch_policy="$(
      jq -nc --argjson p "$protected_branches" --argjson c "$custom_branch_policies" \
        '{protected_branches: $p, custom_branch_policies: $c}'
    )"
  fi

  local payload
  payload="$(
    jq -nc \
      --argjson wait_timer "$wait_timer" \
      --argjson prevent_self_review "$prevent_self_review" \
      --argjson reviewers "$reviewers_json" \
      --argjson branch_policy "$branch_policy" \
      '{
         wait_timer: $wait_timer,
         prevent_self_review: $prevent_self_review,
         reviewers: $reviewers,
         deployment_branch_policy: $branch_policy
       }'
  )"

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [DRY RUN] Would PUT environments/${env_name} with:"
    jq . <<<"$payload" | sed 's/^/    /'
    return 0
  fi

  # stderr is NOT discarded: the API's error body is the only thing that explains
  # a 422, and losing it is what made the previous failure mode undebuggable.
  if ! jq . <<<"$payload" | gh api -X PUT "repos/$REPO/environments/$env_name" --input - >/dev/null; then
    echo "  ✗ Failed to configure environment: $env_name" >&2
    return 1
  fi

  echo "  ✓ Environment configured: $env_name (reviewers: ${count}, wait_timer: ${wait_timer}s)"

  # `allowed_branches` is NOT part of the environment payload. Custom branch
  # policies are separate sub-resources, so they are created here, after the
  # environment exists and has custom_branch_policies enabled.
  if [[ "$custom_branch_policies" == "true" ]]; then
    local pattern_count j pattern
    pattern_count="$(jq -r '(.deployment_branch_policy.allowed_branches // []) | length' "$env_file")"
    for ((j = 0; j < pattern_count; j++)); do
      pattern="$(jq -r ".deployment_branch_policy.allowed_branches[$j]" "$env_file")"
      # A ref written as refs/heads/x or refs/tags/x is stored as the bare
      # pattern by this endpoint.
      pattern="${pattern#refs/heads/}"
      pattern="${pattern#refs/tags/}"
      if gh api -X POST "repos/$REPO/environments/$env_name/deployment-branch-policies" \
        -f "name=$pattern" >/dev/null 2>&1; then
        echo "    ✓ branch policy: $pattern"
      else
        # Already present is the common case on a re-run and is not an error.
        echo "    - branch policy already present or rejected: $pattern"
      fi
    done
  fi
}

# jq is REQUIRED, not optional. The previous version fell back to
# `grep -q '{' && grep -q '}'` when jq was missing — a check that passes on any
# file containing a brace anywhere, including a truncated or malformed ruleset.
# It then went on to call jq unconditionally to read `.can_admins_bypass`, so a
# jq-less machine failed a few lines later anyway, with a worse error. Assert the
# dependency once, up front.
if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required (used to validate every JSON file and to read" >&2
  echo "       ruleset names and environment fields). Install it and re-run." >&2
  exit 1
fi

# Validate all JSON files ONCE, here. `apply_ruleset` / `apply_environment` used
# to re-validate on the dry-run path only, which meant a real run validated
# nothing the loop below had not already covered — two checks, neither placed
# where it helped.
echo "Step 1: Validating JSON syntax..."
ruleset_count=0
env_count=0
for ruleset_file in "$RULESETS_DIR"/*.json; do
  if ! jq . "$ruleset_file" >/dev/null 2>&1; then
    echo "  ERROR: Invalid JSON in $ruleset_file" >&2
    exit 1
  fi
  ruleset_count=$((ruleset_count + 1))
  echo "  ✓ $(basename "$ruleset_file")"
done

for env_file in "$ENVIRONMENTS_DIR"/*.json; do
  if ! jq . "$env_file" >/dev/null 2>&1; then
    echo "  ERROR: Invalid JSON in $env_file" >&2
    exit 1
  fi
  env_count=$((env_count + 1))
  echo "  ✓ $(basename "$env_file")"
done

if [[ "$ruleset_count" -eq 0 ]]; then
  echo "  ERROR: no ruleset JSON files found in $RULESETS_DIR" >&2
  exit 1
fi
if [[ "$env_count" -eq 0 ]]; then
  echo "  ERROR: no environment JSON files found in $ENVIRONMENTS_DIR" >&2
  exit 1
fi

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
env_names=""
for env_file in "$ENVIRONMENTS_DIR"/*.json; do
  apply_environment "$env_file" || exit 1
  env_names="${env_names:+${env_names}, }$(basename "$env_file" .json)"
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
  # Counted from the files actually processed, not hard-coded. The old summary
  # said "3 rulesets / 3 environments (prod, staging, dev)" regardless of what was
  # on disk, so adding a fourth file produced a run that applied it and then
  # reported three.
  echo "Summary:"
  echo "  ✓ ${ruleset_count} branch/tag ruleset(s) applied (create-or-update)"
  echo "  ✓ ${env_count} environment(s) configured: ${env_names}"
  echo "  ✓ Merge hygiene policy applied"
  echo ""
  echo "Next steps:"
  echo "  1. Verify branch rules in GitHub UI: Settings > Rules"
  echo "  2. Verify environments in GitHub UI: Settings > Environments"
  echo "  3. Test: Open a PR to main and verify the approval requirement (1 approval on main, 0 on dev/staging)"
  echo "  4. Create a release tag (v*) and verify tag protection"
fi
echo "=================================================================================="
