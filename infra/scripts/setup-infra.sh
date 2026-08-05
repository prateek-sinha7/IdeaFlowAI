#!/bin/bash
#
# setup-infra.sh
#
# One-time-variable setup script for the VelocityAI Terraform layers.
#
# Edit the CONFIGURATION block below once, then run this script from
# anywhere (it locates the repo root relative to its own path). It runs,
# in order:
#
#     1. bootstrap   (state backend + GitHub OIDC roles)     - once per account
#     2. shared      (ECR repositories)                      - once per account
#     3. foundation  (VPC/KMS/SSM/backups) for each environment
#     4. app         (EC2 host/DNS/monitoring)  for each environment
#
# Each layer runs: init -> validate -> plan -> (pause for confirmation) -> apply,
# matching the fmt/validate/plan/scan/approve/apply order required for this
# workspace's Terraform changes. Nothing is applied without either an
# explicit "yes" at the prompt, or --auto-approve.
#
# Usage:
#   ./infra/scripts/setup-infra.sh [OPTIONS]
#
# OPTIONS:
#   --auto-approve              Skip the interactive "apply now?" prompt for every layer
#   --plan-only                 Run init + validate + plan for every layer and stop
#   --environments ENV1,ENV2    Subset of dev/stage/prod to provision (default: all)
#   --skip-bootstrap            Skip the bootstrap layer
#   --skip-shared               Skip the shared (ECR) layer
#   --run-security-scans        Run tflint/checkov/trivy/gitleaks if available
#

set -euo pipefail

# =============================================================================
# CONFIGURATION - edit these once, then just run the script.
# =============================================================================

# --- Account / region --------------------------------------------------------
# Leave EXPECTED_ACCOUNT_ID empty to auto-adopt whatever account your AWS CLI
# session is currently authenticated to. Set it to a 12-digit account id to
# make every layer's account_guard hard-fail on any mismatch (recommended for
# shared/multi-account setups).
EXPECTED_ACCOUNT_ID=""
AWS_REGION="eu-central-1"

# --- Terraform remote state backend (created by the bootstrap layer) --------
STATE_BUCKET_NAME="velocityai-tfstate"
LOCK_TABLE_NAME="velocityai-tfstate-locks"

# --- Tags (Cost Explorer / Billing) ------------------------------------------
OWNER="velocityai-platform-team@hexaware.com"
COST_CENTER="velocityai"

# --- GitHub Actions OIDC (bootstrap/github_oidc.tf) -------------------------
CREATE_GITHUB_OIDC=true
# EXACT "<owner>/<repo>", no wildcards. This org has "immutable identifiers in
# the OIDC subject" ENABLED, so GitHub emits the owner suffixed with @<org_id>
# and the repo with @<repo_id>. The trust policy is a StringEquals match on the
# subject, so it must use the SAME form GitHub sends or every deploy fails with
# "Not authorized to perform sts:AssumeRoleWithWebIdentity".
GITHUB_ORG_REPO="Hexaware-HnI@220132078/velocityai@1321162016"
# Optional IAM permissions boundary applied to every GitHub-assumable role.
# Recommended in a shared AWS account; leave empty if you don't have one yet.
DEPLOY_BOUNDARY_ARN=""

# --- Per-environment app-layer required input --------------------------------
# alert_email has NO module default (validated as a real email) - fill these
# in before running, or the app layer will fail plan/apply for that env.
declare -A ALERT_EMAILS=(
    [dev]="REPLACE_ME_dev@example.com"
    [stage]="REPLACE_ME_stage@example.com"
    [prod]="REPLACE_ME_prod@example.com"
)

# =============================================================================
# Parse CLI arguments
# =============================================================================

AUTO_APPROVE=false
PLAN_ONLY=false
ENVIRONMENTS=("dev" "stage" "prod")
SKIP_BOOTSTRAP=false
SKIP_SHARED=false
RUN_SECURITY_SCANS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --auto-approve)
            AUTO_APPROVE=true
            shift
            ;;
        --plan-only)
            PLAN_ONLY=true
            shift
            ;;
        --environments)
            IFS=',' read -ra ENVIRONMENTS <<< "$2"
            shift 2
            ;;
        --skip-bootstrap)
            SKIP_BOOTSTRAP=true
            shift
            ;;
        --skip-shared)
            SKIP_SHARED=true
            shift
            ;;
        --run-security-scans)
            RUN_SECURITY_SCANS=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# =============================================================================
# Paths - resolved relative to this script, not hardcoded.
# =============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_ROOT="$REPO_ROOT/infra/terraform"
BOOTSTRAP_DIR="$TERRAFORM_ROOT/bootstrap"
SHARED_DIR="$TERRAFORM_ROOT/shared"
FOUNDATION_DIR="$TERRAFORM_ROOT/foundation"
APP_DIR="$TERRAFORM_ROOT/app"

# =============================================================================
# Helpers
# =============================================================================

write_section() {
    local title="$1"
    echo ""
    echo "=== $title ===" >&2
}

confirm_apply() {
    local layer="$1"
    
    if [[ "$AUTO_APPROVE" == "true" ]]; then
        return 0
    fi
    
    read -p "Apply '$layer' now? Review the plan above. Type 'yes' to apply, anything else to skip: " resp
    if [[ "$resp" == "yes" ]]; then
        return 0
    else
        return 1
    fi
}

invoke_terraform() {
    local work_dir="$1"
    shift
    local args=("$@")
    
    echo "  > terraform ${args[*]}" >&2
    terraform -chdir="$work_dir" "${args[@]}"
    if [[ $? -ne 0 ]]; then
        echo "terraform ${args[0]} failed in '$work_dir'" >&2
        exit 1
    fi
}

test_prerequisites() {
    write_section "Checking prerequisites"
    
    for cmd in terraform aws; do
        if ! command -v "$cmd" &> /dev/null; then
            echo "'$cmd' is not installed or not on PATH." >&2
            exit 1
        fi
    done
    
    terraform version >&2
    aws --version >&2
    
    local identity_json
    identity_json=$(aws sts get-caller-identity --output json 2>/dev/null) || {
        echo "aws sts get-caller-identity failed - check your AWS credentials/session (SSO login, env vars, or profile)." >&2
        exit 1
    }
    
    echo "$identity_json"
}

command_exists() {
    command -v "$1" &> /dev/null
}

invoke_optional_scan() {
    local tool="$1"
    shift
    local args=("$@")
    local work_dir="${args[-1]}"
    
    if ! command_exists "$tool"; then
        echo "  [skip] $tool not found on PATH." >&2
        return
    fi
    
    echo "  > $tool ${args[@]}" >&2
    (cd "$work_dir" && "$tool" "${args[@]}" || {
        local exit_code=$?
        echo "  [warn] $tool reported findings (exit $exit_code). Review before applying." >&2
    })
}

invoke_security_scans() {
    if [[ "$RUN_SECURITY_SCANS" != "true" ]]; then
        return
    fi
    
    write_section "Security scans (best-effort, non-blocking)"
    invoke_optional_scan tflint --recursive "$TERRAFORM_ROOT"
    invoke_optional_scan checkov -d . "$TERRAFORM_ROOT"
    invoke_optional_scan trivy config . "$TERRAFORM_ROOT"
    invoke_optional_scan gitleaks detect --source . --no-git "$TERRAFORM_ROOT"
}

new_bootstrap_tfvars() {
    local path="$BOOTSTRAP_DIR/bootstrap.tfvars"
    
    if [[ -f "$path" ]]; then
        local backup="$path.bak"
        cp "$path" "$backup"
        echo "  Existing bootstrap.tfvars backed up to $backup" >&2
    fi
    
    cat > "$path" <<EOF
# Generated by infra/scripts/setup-infra.sh - edit the CONFIGURATION block
# in that script, not this file directly; it is regenerated on every run.

aws_region        = "$AWS_REGION"
state_bucket_name = "$STATE_BUCKET_NAME"
lock_table_name   = "$LOCK_TABLE_NAME"

owner       = "$OWNER"
cost_center = "$COST_CENTER"

create_github_oidc = $CREATE_GITHUB_OIDC
github_org_repo    = "$GITHUB_ORG_REPO"
EOF
    
    if [[ -n "$DEPLOY_BOUNDARY_ARN" ]]; then
        echo "deploy_permissions_boundary_arn = \"$DEPLOY_BOUNDARY_ARN\"" >> "$path"
    fi
    
    echo "  Wrote $path" >&2
}

invoke_layer() {
    local name="$1"
    local work_dir="$2"
    local backend_key="$3"
    shift 3
    local plan_vars=("$@")
    local var_file="${VAR_FILE:-}"
    
    write_section "Layer: $name"
    
    local init_args=(
        'init' '-reconfigure'
        "-backend-config=bucket=$STATE_BUCKET_NAME"
        "-backend-config=key=$backend_key"
        "-backend-config=region=$AWS_REGION"
        "-backend-config=dynamodb_table=$LOCK_TABLE_NAME"
        "-backend-config=encrypt=true"
    )
    invoke_terraform "$work_dir" "${init_args[@]}"
    
    invoke_terraform "$work_dir" validate
    
    local plan_file="setup-infra.auto.tfplan"
    local plan_args=('plan' "-out=$plan_file")
    
    if [[ -n "$var_file" ]]; then
        plan_args+=("-var-file=$var_file")
    fi
    
    plan_args+=("${plan_vars[@]}")
    
    invoke_terraform "$work_dir" "${plan_args[@]}"
    
    local plan_full_path="$work_dir/$plan_file"
    
    if [[ "$PLAN_ONLY" == "true" ]]; then
        echo "  -PlanOnly set: skipping apply for '$name'. Plan kept at $plan_full_path." >&2
        return
    fi
    
    if ! confirm_apply "$name"; then
        echo "  Skipped apply for '$name'." >&2
        rm -f "$plan_full_path"
        return
    fi
    
    invoke_terraform "$work_dir" apply "$plan_file"
    rm -f "$plan_full_path"
}

invoke_bootstrap_layer() {
    if [[ "$SKIP_BOOTSTRAP" == "true" ]]; then
        echo "-SkipBootstrap set: skipping bootstrap layer." >&2
        return
    fi
    
    write_section "Layer: bootstrap"
    new_bootstrap_tfvars
    
    # Bootstrap creates the remote backend itself, so it has no backend-config
    # of its own - it uses local state (see infra/terraform/RUNBOOK.md).
    invoke_terraform "$BOOTSTRAP_DIR" init
    invoke_terraform "$BOOTSTRAP_DIR" validate
    
    local plan_file="setup-infra.auto.tfplan"
    local plan_args=(
        'plan' "-out=$plan_file"
        '-var-file=bootstrap.tfvars'
        "-var=expected_account_id=$ACCOUNT_ID"
        "-var=aws_region=$AWS_REGION"
    )
    invoke_terraform "$BOOTSTRAP_DIR" "${plan_args[@]}"
    
    local plan_full_path="$BOOTSTRAP_DIR/$plan_file"
    
    if [[ "$PLAN_ONLY" == "true" ]]; then
        echo "  -PlanOnly set: skipping apply for 'bootstrap'. Plan kept at $plan_full_path." >&2
        return
    fi
    
    if ! confirm_apply 'bootstrap'; then
        echo "  Skipped apply for 'bootstrap'." >&2
        rm -f "$plan_full_path"
        return
    fi
    
    invoke_terraform "$BOOTSTRAP_DIR" apply "$plan_file"
    rm -f "$plan_full_path"
    
    # Bootstrap's own state is local (see comment above) - remind the operator
    # to protect it rather than silently leaving plaintext state on disk.
    echo "  NOTE: bootstrap layer state is LOCAL (infra/terraform/bootstrap/terraform.tfstate)." >&2
    echo "        It may contain sensitive values. Keep it out of git (already ignored) and back it up securely." >&2
}

# =============================================================================
# Main
# =============================================================================

main() {
    local identity_json
    identity_json=$(test_prerequisites)
    
    if [[ -n "$EXPECTED_ACCOUNT_ID" ]]; then
        ACCOUNT_ID="$EXPECTED_ACCOUNT_ID"
    else
        ACCOUNT_ID=$(echo "$identity_json" | grep -o '"Account": "[^"]*' | cut -d'"' -f4)
    fi
    
    write_section "Target"
    echo "  AWS Account : $ACCOUNT_ID" >&2
    echo "  AWS Region  : $AWS_REGION" >&2
    echo "  Environments: $(IFS=', '; echo "${ENVIRONMENTS[*]}")" >&2
    
    local mode
    if [[ "$PLAN_ONLY" == "true" ]]; then
        mode="PLAN ONLY (no apply)"
    elif [[ "$AUTO_APPROVE" == "true" ]]; then
        mode="AUTO-APPROVE (no prompts)"
    else
        mode="INTERACTIVE (confirm each apply)"
    fi
    echo "  Mode        : $mode" >&2
    
    if [[ "$AUTO_APPROVE" != "true" ]] && [[ "$PLAN_ONLY" != "true" ]]; then
        read -p "Continue against this account/region? Type 'yes' to proceed: " go
        if [[ "$go" != "yes" ]]; then
            echo "Aborted by user." >&2
            exit 0
        fi
    fi
    
    invoke_security_scans
    
    invoke_bootstrap_layer
    
    if [[ "$SKIP_SHARED" == "true" ]]; then
        echo "-SkipShared set: skipping shared (ECR) layer." >&2
    else
        invoke_layer "shared" "$SHARED_DIR" "velocityai/shared.tfstate" \
            "-var=expected_account_id=$ACCOUNT_ID" \
            "-var=aws_region=$AWS_REGION"
    fi
    
    for env_name in "${ENVIRONMENTS[@]}"; do
        invoke_layer "foundation ($env_name)" "$FOUNDATION_DIR" \
            "velocityai/$env_name/foundation.tfstate" \
            "-var-file=$env_name.tfvars" \
            "-var=expected_account_id=$ACCOUNT_ID" \
            "-var=aws_region=$AWS_REGION"
        
        local alert_email="${ALERT_EMAILS[$env_name]}"
        if [[ "$alert_email" == REPLACE_ME* ]]; then
            echo "  Skipping app layer for '$env_name': set a real alert_email in ALERT_EMAILS before running." >&2
            continue
        fi
        
        invoke_layer "app ($env_name)" "$APP_DIR" \
            "velocityai/$env_name/app.tfstate" \
            "-var-file=$env_name.tfvars" \
            "-var=expected_account_id=$ACCOUNT_ID" \
            "-var=aws_region=$AWS_REGION" \
            "-var=state_bucket=$STATE_BUCKET_NAME" \
            "-var=alert_email=$alert_email"
    done
    
    if [[ "$PLAN_ONLY" != "true" ]]; then
        write_section "Outputs"
        
        if [[ "$SKIP_BOOTSTRAP" != "true" ]]; then
            echo "-- bootstrap --" >&2
            invoke_terraform "$BOOTSTRAP_DIR" output
        fi
        
        if [[ "$SKIP_SHARED" != "true" ]]; then
            echo "-- shared --" >&2
            invoke_terraform "$SHARED_DIR" output
        fi
        
        for env_name in "${ENVIRONMENTS[@]}"; do
            echo "-- app ($env_name) --" >&2
            invoke_terraform "$APP_DIR" output || {
                echo "  Could not print every output (a layer may have been skipped or not applied). Run 'terraform -chdir=<dir> output' manually to inspect." >&2
            }
        done
        
        echo "" >&2
        echo "Next: use github_build_role_arn / github_deploy_role_arns (bootstrap output) and" >&2
        echo "ecr_registry_url (shared output) to configure the GitHub Environment variables/secrets" >&2
        echo "(AWS_BUILD_ROLE_ARN, AWS_DEPLOY_ROLE_ARN, ECR_REGISTRY, EC2_INSTANCE_ID, ...) - see docs/GITHUB_CICD_SETUP.md." >&2
    fi
    
    write_section "Done"
}

main "$@"
