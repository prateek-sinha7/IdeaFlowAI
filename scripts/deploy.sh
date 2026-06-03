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

# Owner: last segment of the caller ARN — for SSO that's usually the user's
# email or username; for IAM users it's the user name. Anything containing
# whitespace or weirder than `[A-Za-z0-9_.@-]` falls back to "flowin" rather
# than turning into a malformed tag value (some AWS resource tag schemas
# reject the `:` that appears in ARN-prefix substrings).
DETECTED_OWNER="${CALLER_ARN##*/}"
if [[ -z "$DETECTED_OWNER" || ! "$DETECTED_OWNER" =~ ^[A-Za-z0-9_.@+=-]+$ ]]; then
    DETECTED_OWNER="flowin"
fi

ENVIRONMENT="${FLOWIN_ENVIRONMENT:-prod}"
OWNER="${FLOWIN_OWNER:-$DETECTED_OWNER}"
COST_CENTER="${FLOWIN_COST_CENTER:-flowin}"
STATE_BUCKET="flowin-tfstate-${ACCOUNT_ID}-${REGION}"
BACKUP_BUCKET="flowin-${ENVIRONMENT}-pg-dumps-${ACCOUNT_ID}"
# DynamoDB lock table — must match the default in infra/bootstrap/variables.tf
# AND the hardcoded value in infra/envs/prod/backend.tf. Single source here.
LOCK_TABLE="flowin-tfstate-locks"
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
        -var "environment=$ENVIRONMENT"
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
        -backend-config="region=$REGION" \
        -backend-config="dynamodb_table=$LOCK_TABLE"
    terraform -chdir=infra/envs/prod apply -input=false -auto-approve "${PROD_TF_VARS[@]}"
else
    yellow "==> [2/5] SKIPPED (FLOWIN_SKIP_PROD_TF=1)"
fi

# Resolve outputs once for the next steps. `terraform output -raw` returns
# nonzero (and a confusing one-line "Warning") when the output is missing —
# usually because the prod apply was skipped on a tree that never had it.
# Wrap so the operator gets a useful diagnosis instead of `set -e` killing
# the script silently.
tf_out() {
    local val
    val=$(terraform -chdir=infra/envs/prod output -raw "$1" 2>/dev/null) \
        || die "terraform output '$1' is missing. Did the prod apply succeed? (If you set FLOWIN_SKIP_PROD_TF=1, the state must already contain this output.)"
    [[ -n "$val" ]] || die "terraform output '$1' is empty."
    printf '%s' "$val"
}

BACKEND_REPO=$(tf_out ecr_backend_repository_url)
FRONTEND_REPO=$(tf_out ecr_frontend_repository_url)
FQDN=$(tf_out fqdn)
INSTANCE_ID=$(tf_out instance_id)
REGISTRY="${BACKEND_REPO%/*}"

# ── Compute image tag (shared by step 5 build/push + step 6 SSM env) ──
# ECR repos are `image_tag_mutability = "IMMUTABLE"` (see infra/modules/ecr).
# Pushing the same tag twice fails with ImagePushNotAllowedException, so we
# can't use :latest — every deploy needs a unique tag. Default = current
# commit's short sha; uncommitted local changes get a `-dirty-<unixts>`
# suffix so iterating with WIP changes still produces unique tags. Operator
# can override via FLOWIN_IMAGE_TAG (mainly for FLOWIN_SKIP_IMAGES=1 mode,
# where you want the box to pull an already-pushed tag).
TAG="$(git rev-parse --short HEAD)"
if ! git diff --quiet HEAD 2>/dev/null \
    || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    DIRTY_SUFFIX="-dirty-$(date +%s)"
    yellow "    NOTE: uncommitted changes — tagging as ${TAG}${DIRTY_SUFFIX}"
    yellow "    (commit for a reproducible tag)"
    TAG="${TAG}${DIRTY_SUFFIX}"
fi
TAG="${FLOWIN_IMAGE_TAG:-$TAG}"

# ── 5. Build + push initial images ────────────────────────────────────
if [[ -z "${FLOWIN_SKIP_IMAGES:-}" ]]; then
    bold "==> [3/5] build + push images to ECR ($TAG)"

    aws ecr get-login-password --region "$REGION" \
        | docker login --username AWS --password-stdin "$REGISTRY"

    # --platform linux/amd64 is mandatory: the EC2 is m6i.2xlarge (x86_64),
    # but the operator's laptop may be Apple Silicon (arm64). Without this
    # flag Docker builds for the host arch, the EC2 runs the image, and
    # exec() fails with "exec format error" — flowin-app.service then loops
    # restarting and the deploy looks like a Bedrock/networking problem.
    # On Apple Silicon, Docker emulates amd64 via QEMU (slower build but
    # produces correct artefacts).
    docker build --platform linux/amd64 \
        -t "$BACKEND_REPO:$TAG" \
        backend/
    docker build --platform linux/amd64 \
        --build-arg "NEXT_PUBLIC_API_URL=https://$FQDN" \
        --build-arg "NEXT_PUBLIC_WS_URL=wss://$FQDN/ws/chat" \
        -t "$FRONTEND_REPO:$TAG" \
        frontend/

    docker push "$BACKEND_REPO:$TAG"
    docker push "$FRONTEND_REPO:$TAG"
else
    yellow "==> [3/5] SKIPPED (FLOWIN_SKIP_IMAGES=1)"
    # The box will try `docker compose pull` on this tag. If it doesn't
    # exist in ECR yet, flowin-app.service crash-loops with manifest-unknown
    # and the only signal is buried in `journalctl -u flowin-app`. Fail fast
    # here instead — saves a 15-min round trip.
    for repo in "$BACKEND_REPO" "$FRONTEND_REPO"; do
        repo_name="${repo##*/}"
        if ! aws ecr describe-images \
            --region "$REGION" \
            --repository-name "$repo_name" \
            --image-ids "imageTag=$TAG" >/dev/null 2>&1; then
            die "FLOWIN_SKIP_IMAGES=1 set, but $repo_name:$TAG isn't in ECR. Either unset FLOWIN_SKIP_IMAGES, or set FLOWIN_IMAGE_TAG to a tag that's been pushed."
        fi
    done
    yellow "    verified $TAG present in both ECR repos"
fi

# ── 6. SSM RunCommand: run bootstrap-ec2.sh on the instance ───────────
if [[ -z "${FLOWIN_SKIP_BOOTSTRAP_SSM:-}" ]]; then
    bold "==> [4/5] EC2 bootstrap via SSM RunCommand (~6 min)"

    # `terraform apply` returns when the instance is `running`, NOT when
    # cloud-init has finished writing /etc/flowin/bootstrap.env or when the
    # SSM Agent has registered. Two waits are needed before send-command:
    #   (a) ec2 wait instance-status-ok — passes both EC2 + system status,
    #       which implies cloud-init's user_data completed.
    #   (b) describe-instance-information — confirms the SSM Agent has
    #       connected to the SSM control plane. Without this, send-command
    #       returns InvalidInstanceId.
    echo "    waiting for EC2 instance-status-ok..."
    aws ec2 wait instance-status-ok --region "$REGION" --instance-ids "$INSTANCE_ID"

    echo "    waiting for SSM Agent registration..."
    for i in $(seq 1 60); do
        PING=$(aws ssm describe-instance-information \
            --region "$REGION" \
            --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
            --query 'InstanceInformationList[0].PingStatus' \
            --output text 2>/dev/null || echo "None")
        if [[ "$PING" == "Online" ]]; then
            echo "    SSM Agent online"
            break
        fi
        if [[ $i -ge 60 ]]; then
            die "SSM Agent did not register within 10 minutes. Check the EC2 console."
        fi
        sleep 10
    done

    # send-command's --timeout-seconds caps delivery (must START within this
    # window), not run-time. Run-time is the `executionTimeout` parameter
    # below — 1800s gives bootstrap-ec2.sh comfortable headroom past its
    # typical ~6 min runtime.
    #
    # AWS-RunShellScript runs the commands array under /bin/sh, which on
    # Ubuntu is dash (POSIX), not bash. bootstrap-ec2.sh is bash-specific:
    # `set -o pipefail`, `[[ ]]`, `${var^}`, `[[ "$x" =~ regex ]]`, etc.
    # Wrap the body in a quoted heredoc and pipe it to /bin/bash so the
    # entire script executes under bash regardless of what SSM dispatches
    # us under. The terminator __FLOWIN_BOOTSTRAP_EOF__ is unique vs. any
    # heredoc terminator inside bootstrap-ec2.sh (it uses EOF, UNIT, TIMER,
    # WRAPPER, SUDO, etc.). Quoted heredoc delimiter ('${EOF_TAG}') keeps
    # /bin/sh from doing $-expansion on the bash body before bash sees it.
    #
    # FLOWIN_IMAGE_TAG is set via `export` inside the bash heredoc so
    # bootstrap-ec2.sh's IMAGE_TAG="${FLOWIN_IMAGE_TAG:-latest}" picks up
    # the just-pushed git-sha tag.
    EOF_TAG="__FLOWIN_BOOTSTRAP_EOF__"
    SCRIPT_BODY="$(cat infra/scripts/bootstrap-ec2.sh)"
    # FLOWIN_ACME_EMAIL is exported here as a belt-and-suspenders for instances
    # whose /etc/flowin/bootstrap.env was written before TF started populating
    # the key (modules/compute/user_data.sh.tpl writes it via user_data_extra_env
    # going forward). bootstrap-ec2.sh's `${FLOWIN_ACME_EMAIL:-fallback}` keeps
    # the bootstrap.env-sourced value when present, otherwise our export wins —
    # safer than the placeholder `security@example.com` which Let's Encrypt
    # rejects as an invalid registration email.
    SSM_SCRIPT="exec /bin/bash <<'${EOF_TAG}'
export FLOWIN_IMAGE_TAG=$(printf %q "$TAG")
export FLOWIN_ACME_EMAIL=$(printf %q "$FLOWIN_ALERT_EMAIL")
${SCRIPT_BODY}
${EOF_TAG}"

    CMD_ID=$(aws ssm send-command \
        --region "$REGION" \
        --document-name AWS-RunShellScript \
        --instance-ids "$INSTANCE_ID" \
        --parameters "$(jq -n \
            --arg script "$SSM_SCRIPT" \
            '{commands: [$script], executionTimeout: ["1800"]}')" \
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
            Cancelling)
                echo "    status: Cancelling (will become Cancelled)"
                sleep 10
                ;;
            Delayed)
                echo "    status: Delayed (SSM control plane busy, waiting 30s)"
                sleep 30
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
# After SSM reports Success, three more things have to settle before
# /health responds via HTTPS:
#   - flowin-app.service ExecStartPre runs `docker compose pull`. Cold
#     ECR cache of two ~500 MB images takes 30-120s on a fresh box.
#   - alembic upgrade head runs as the container's entrypoint.
#   - On the very first deploy, certbot has to fetch and install the
#     Let's Encrypt cert (HTTP-01 challenge — 30-60s).
# Total post-bootstrap settle: typically 60-180s; cold path: up to 5 min.
# 10 attempts at 30s = 5 min budget.
for attempt in $(seq 1 10); do
    if curl -fsS --max-time 10 "https://$FQDN/health" >/dev/null 2>&1; then
        green ""
        green "  Flowin is live at https://$FQDN"
        green "  Login UI:     https://$FQDN/login"
        green "  Health:       https://$FQDN/health"
        green "  Instance:     $INSTANCE_ID ($REGION)"
        green ""
        # ── Tag the deployed commit so each release is traceable in git ──
        # ECR images are already tagged with the short SHA ($TAG); this adds a
        # repo-visible annotated git tag pointing at the exact deployed commit.
        # Skipped when the tree was dirty (there is no clean commit to point at).
        if [[ "$TAG" == *-dirty-* ]]; then
            yellow "  git deploy-tag skipped: working tree was dirty — commit for a traceable tag"
        else
            DEPLOY_TAG="deploy-${ENVIRONMENT}-$(date -u +%Y%m%d-%H%M%S)"
            if git tag -a "$DEPLOY_TAG" \
                -m "Deploy ${TAG} to ${ENVIRONMENT} (account ${ACCOUNT_ID}, region ${REGION}) by ${OWNER}" 2>/dev/null; then
                if git push origin "$DEPLOY_TAG" >/dev/null 2>&1; then
                    green "  git deploy-tag: $DEPLOY_TAG -> $TAG (pushed to origin)"
                else
                    yellow "  git deploy-tag: $DEPLOY_TAG created locally; push failed — run: git push origin $DEPLOY_TAG"
                fi
            fi
        fi
        exit 0
    fi
    if [[ $attempt -lt 10 ]]; then
        yellow "    /health not responding yet (attempt $attempt/10), retrying in 30s..."
        sleep 30
    fi
done

red ""
red "/health didn't respond within ~5 min of bootstrap completion."
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
