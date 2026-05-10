#!/usr/bin/env bash
# scripts/deploy.sh
#
# End-to-end Flowin deploy. Takes a fresh AWS account from "nothing" to
# "https://<fqdn>/health responding 200" in one invocation. Idempotent —
# re-running redeploys (rebuilds images + restarts flowin-app.service).
#
# Auto-detects from your active AWS profile / SSO session:
#   - account ID  (aws sts get-caller-identity)
#   - region      (aws configure get region, fallback eu-central-1)
#   - owner       (last segment of the caller ARN)
#
# Required interactive input (or set via env to suppress the prompt):
#   FLOWIN_ALERT_EMAIL — SNS subscription target for alarms
#
# Optional env overrides:
#   FLOWIN_ENVIRONMENT      default: prod
#   FLOWIN_OWNER            default: parsed from SSO ARN, fallback "flowin"
#   FLOWIN_COST_CENTER      default: flowin
#   FLOWIN_USE_NIP_IO       default: true
#   FLOWIN_ROUTE53_ZONE     required when FLOWIN_USE_NIP_IO=false
#   FLOWIN_APP_SUBDOMAIN    default: flowin (only used with route53)
#   FLOWIN_AUTO_APPROVE     skip the confirmation prompt (set to 1)
#
# Skip flags (resume a partial run):
#   FLOWIN_SKIP_BOOTSTRAP_TF=1     skip the bootstrap-stack apply
#   FLOWIN_SKIP_PROD_TF=1          skip the prod-stack apply
#   FLOWIN_SKIP_IMAGES=1           skip docker build + push
#   FLOWIN_SKIP_BOOTSTRAP_SSM=1    skip the EC2 SSM RunCommand
#
# Multi-profile users: set AWS_PROFILE before running. The script uses
# whatever `aws sts get-caller-identity` resolves to.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
bold()   { printf '\033[1m%s\033[0m\n' "$*"; }

die() { red "ERROR: $*" >&2; exit 1; }

# ── 0. Pre-flight ─────────────────────────────────────────────────────
command -v aws       >/dev/null 2>&1 || die "aws CLI not found in PATH"
command -v terraform >/dev/null 2>&1 || die "terraform not found in PATH"
command -v docker    >/dev/null 2>&1 || die "docker not found in PATH"
command -v jq        >/dev/null 2>&1 || die "jq not found in PATH (used to encode the bootstrap script for SSM)"

aws sts get-caller-identity >/dev/null 2>&1 \
    || die "aws sts get-caller-identity failed. Run 'aws sso login' (or set AWS credentials) first."

docker info >/dev/null 2>&1 \
    || die "docker daemon not reachable. Start Docker Desktop first."

# ── 1. Detect identity + config ───────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CALLER_ARN=$(aws sts get-caller-identity --query Arn --output text)

# Region: prefer AWS_REGION env, then `aws configure get region`, fallback.
REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}"
REGION="${REGION:-eu-central-1}"

# Owner: last segment of the caller ARN (SSO-shaped ARNs end in user.name).
# If the last segment looks like a role/session name (no `@`, no `.`), fall
# back to the role-name segment, then to "flowin".
DETECTED_OWNER="${CALLER_ARN##*/}"
if [[ "$DETECTED_OWNER" != *.*@* && "$DETECTED_OWNER" != *.* && "$DETECTED_OWNER" != *@* ]]; then
    DETECTED_OWNER=$(awk -F'/' '{print $(NF-1)}' <<< "$CALLER_ARN")
    [[ -n "$DETECTED_OWNER" && "$DETECTED_OWNER" != "sts" ]] || DETECTED_OWNER="flowin"
fi

ENVIRONMENT="${FLOWIN_ENVIRONMENT:-prod}"
OWNER="${FLOWIN_OWNER:-$DETECTED_OWNER}"
COST_CENTER="${FLOWIN_COST_CENTER:-flowin}"
STATE_BUCKET="flowin-tfstate-${ACCOUNT_ID}-${REGION}"
BACKUP_BUCKET="flowin-${ENVIRONMENT}-pg-dumps-${ACCOUNT_ID}"
USE_NIP_IO="${FLOWIN_USE_NIP_IO:-true}"

if [[ -z "${FLOWIN_ALERT_EMAIL:-}" ]]; then
    if [[ -t 0 ]]; then
        read -rp "Alert email (where SNS sends paging notifications): " FLOWIN_ALERT_EMAIL
    fi
    [[ -n "${FLOWIN_ALERT_EMAIL:-}" ]] \
        || die "FLOWIN_ALERT_EMAIL is required (set it as an env var or run interactively)."
fi

# ── 2. Confirm ────────────────────────────────────────────────────────
bold "──────────────────────────────────────────────"
cat <<EOF
  identity:      $CALLER_ARN
  account:       $ACCOUNT_ID
  region:        $REGION
  environment:   $ENVIRONMENT
  state bucket:  $STATE_BUCKET
  backup bucket: $BACKUP_BUCKET
  owner:         $OWNER
  cost center:   $COST_CENTER
  alert email:   $FLOWIN_ALERT_EMAIL
  DNS:           $([[ "$USE_NIP_IO" == "true" ]] && echo "nip.io (zero DNS config)" || echo "Route 53 (zone=$FLOWIN_ROUTE53_ZONE)")
EOF
bold "──────────────────────────────────────────────"

if [[ "$USE_NIP_IO" == "false" ]]; then
    [[ -n "${FLOWIN_ROUTE53_ZONE:-}" ]] \
        || die "FLOWIN_ROUTE53_ZONE is required when FLOWIN_USE_NIP_IO=false"
fi

if [[ "${FLOWIN_AUTO_APPROVE:-}" != "1" ]]; then
    if [[ -t 0 ]]; then
        read -rp "Proceed? [y/N] " CONFIRM
        [[ "$CONFIRM" =~ ^[Yy]$ ]] || { yellow "Aborted."; exit 1; }
    else
        die "Refusing to apply non-interactively without FLOWIN_AUTO_APPROVE=1"
    fi
fi

# ── 3. Bootstrap stack: state bucket + lock + CMK ─────────────────────
if [[ -z "${FLOWIN_SKIP_BOOTSTRAP_TF:-}" ]]; then
    bold "==> [1/5] bootstrap stack (state bucket + DynamoDB lock + KMS CMK)"
    terraform -chdir=infra/bootstrap init -input=false
    terraform -chdir=infra/bootstrap apply -input=false -auto-approve \
        -var "expected_account_id=$ACCOUNT_ID" \
        -var "aws_region=$REGION" \
        -var "owner=$OWNER" \
        -var "cost_center=$COST_CENTER" \
        -var "state_bucket_name=$STATE_BUCKET"
else
    yellow "==> [1/5] SKIPPED (FLOWIN_SKIP_BOOTSTRAP_TF=1)"
fi

# ── 4. Prod stack: VPC, EC2, ECR, KMS, ... ────────────────────────────
if [[ -z "${FLOWIN_SKIP_PROD_TF:-}" ]]; then
    bold "==> [2/5] prod stack (VPC, EC2, ECR, KMS, ...)"

    PROD_TF_VARS=(
        -var "expected_account_id=$ACCOUNT_ID"
        -var "aws_region=$REGION"
        -var "owner=$OWNER"
        -var "cost_center=$COST_CENTER"
        -var "alert_email=$FLOWIN_ALERT_EMAIL"
        -var "backup_bucket_name=$BACKUP_BUCKET"
        -var "use_nip_io=$USE_NIP_IO"
    )

    if [[ "$USE_NIP_IO" == "false" ]]; then
        PROD_TF_VARS+=(
            -var "route53_zone_name=$FLOWIN_ROUTE53_ZONE"
            -var "app_subdomain=${FLOWIN_APP_SUBDOMAIN:-flowin}"
        )
    fi

    # -reconfigure handles both first-time init AND re-init against a
    # potentially-different backend without prompting for state migration.
    terraform -chdir=infra/envs/prod init -input=false -reconfigure \
        -backend-config="bucket=$STATE_BUCKET" \
        -backend-config="region=$REGION"
    terraform -chdir=infra/envs/prod apply -input=false -auto-approve "${PROD_TF_VARS[@]}"
else
    yellow "==> [2/5] SKIPPED (FLOWIN_SKIP_PROD_TF=1)"
fi

# Resolve outputs once for the next steps.
tf_out() { terraform -chdir=infra/envs/prod output -raw "$1"; }

BACKEND_REPO=$(tf_out ecr_backend_repository_url)
FRONTEND_REPO=$(tf_out ecr_frontend_repository_url)
FQDN=$(tf_out fqdn)
INSTANCE_ID=$(tf_out instance_id)
REGISTRY="${BACKEND_REPO%/*}"

# ── 5. Build + push initial images ────────────────────────────────────
if [[ -z "${FLOWIN_SKIP_IMAGES:-}" ]]; then
    bold "==> [3/5] build + push initial images to ECR"
    TAG="latest"

    aws ecr get-login-password --region "$REGION" \
        | docker login --username AWS --password-stdin "$REGISTRY"

    docker build -t "$BACKEND_REPO:$TAG" backend/
    docker build \
        --build-arg "NEXT_PUBLIC_API_URL=https://$FQDN" \
        --build-arg "NEXT_PUBLIC_WS_URL=wss://$FQDN/ws/chat" \
        -t "$FRONTEND_REPO:$TAG" \
        frontend/

    docker push "$BACKEND_REPO:$TAG"
    docker push "$FRONTEND_REPO:$TAG"
else
    yellow "==> [3/5] SKIPPED (FLOWIN_SKIP_IMAGES=1)"
fi

# ── 6. SSM RunCommand: run bootstrap-ec2.sh on the instance ───────────
if [[ -z "${FLOWIN_SKIP_BOOTSTRAP_SSM:-}" ]]; then
    bold "==> [4/5] EC2 bootstrap via SSM RunCommand (~6 min)"

    CMD_ID=$(aws ssm send-command \
        --region "$REGION" \
        --document-name AWS-RunShellScript \
        --instance-ids "$INSTANCE_ID" \
        --parameters "commands=[$(jq -Rs . < infra/scripts/bootstrap-ec2.sh)]" \
        --timeout-seconds 1800 \
        --output text --query 'Command.CommandId')

    echo "    command id: $CMD_ID"

    while true; do
        STATUS=$(aws ssm get-command-invocation \
            --region "$REGION" \
            --command-id "$CMD_ID" \
            --instance-id "$INSTANCE_ID" \
            --query 'Status' --output text 2>/dev/null || echo "Pending")
        case "$STATUS" in
            Success)
                green "    bootstrap: Success"
                break
                ;;
            Failed|TimedOut|Cancelled)
                red "    bootstrap: $STATUS"
                echo "    investigate:"
                echo "      aws ssm get-command-invocation --region $REGION --command-id $CMD_ID --instance-id $INSTANCE_ID"
                exit 1
                ;;
            *)
                echo "    status: $STATUS (waiting 30s)"
                sleep 30
                ;;
        esac
    done
else
    yellow "==> [4/5] SKIPPED (FLOWIN_SKIP_BOOTSTRAP_SSM=1)"
fi

# ── 7. Smoke test ─────────────────────────────────────────────────────
bold "==> [5/5] smoke test https://$FQDN/health"
# certbot + nginx + flowin-app.service can take an extra 30-60s after the
# SSM run reports Success. Give it 3 retries on a 20s interval before
# declaring failure.
for attempt in 1 2 3 4 5; do
    if curl -fsS --max-time 10 "https://$FQDN/health" >/dev/null 2>&1; then
        green ""
        green "  Flowin is live at https://$FQDN"
        green "  Login UI:     https://$FQDN/login"
        green "  Health:       https://$FQDN/health"
        green "  Instance:     $INSTANCE_ID ($REGION)"
        green ""
        exit 0
    fi
    if [[ $attempt -lt 5 ]]; then
        yellow "    /health not responding yet (attempt $attempt/5), retrying in 20s..."
        sleep 20
    fi
done

red ""
red "/health didn't respond within ~100s of bootstrap completion."
red "Likely causes:"
red "  - flowin-app.service still pulling images (slow ECR / cold cache)"
red "  - cert not yet issued (DNS propagation if NOT using nip.io)"
red ""
red "Debug:"
red "  aws ssm start-session --region $REGION --target $INSTANCE_ID"
red "  # then on the box:"
red "  sudo systemctl status flowin-app.service"
red "  sudo docker compose -f /opt/flowin/docker-compose.yml logs --tail=200"
exit 1
