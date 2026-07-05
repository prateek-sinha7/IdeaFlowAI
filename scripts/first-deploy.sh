#!/usr/bin/env bash
# scripts/first-deploy.sh
#
# One-shot operator script: build + push the initial backend and frontend
# Docker images to ECR, before the EC2 bootstrap is triggered. After this
# step succeeds, the GitLab CI pipeline (.gitlab-ci.yml :: build_and_deploy)
# takes over for every subsequent release.
#
# Why this exists separately from CI:
#   - The bootstrap script (infra/scripts/bootstrap-ec2.sh) runs
#     `docker compose pull` as part of velocityai-app.service ExecStartPre.
#     Until at least one tag exists in each ECR repo, that pull fails and
#     the systemd unit goes into restart-loop.
#   - The CI pipeline is `when: manual` on main — fine for steady-state
#     deploys, but on a fresh account/environment there's no prior `main`
#     commit to trigger from. This script is the bootstrap-of-the-bootstrap.
#
# Prerequisites:
#   - SSO / credentials active (`aws sts get-caller-identity` succeeds).
#   - Docker daemon running locally.
#   - `terraform apply` has run against $VELOCITYAI_TF_ENV_DIR (default:
#     infra/envs/prod) so `terraform output` resolves the ECR + FQDN values.
#
# Usage:
#   scripts/first-deploy.sh                    # tags both with :latest
#   scripts/first-deploy.sh v20260511-init     # tags with the given string
#
# Override the env directory (e.g. staging):
#   VELOCITYAI_TF_ENV_DIR=infra/envs/staging scripts/first-deploy.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_ENV_DIR="${VELOCITYAI_TF_ENV_DIR:-$REPO_ROOT/infra/envs/prod}"
TAG="${1:-latest}"

if [[ ! -d "$TF_ENV_DIR" ]]; then
    echo "ERROR: Terraform env dir does not exist: $TF_ENV_DIR" >&2
    exit 1
fi

# Resolve TF outputs once each. -raw strips the JSON quoting.
tf_out() {
    terraform -chdir="$TF_ENV_DIR" output -raw "$1"
}

REGION=$(tf_out verified_region)
BACKEND_REPO=$(tf_out ecr_backend_repository_url)
FRONTEND_REPO=$(tf_out ecr_frontend_repository_url)
FQDN=$(tf_out fqdn)
INSTANCE_ID=$(tf_out instance_id)
REGISTRY="${BACKEND_REPO%/*}"

cat <<EOF
──────────────────────────────────────────────
  region:    $REGION
  registry:  $REGISTRY
  fqdn:      $FQDN
  tag:       $TAG
  ec2:       $INSTANCE_ID
──────────────────────────────────────────────
EOF

# Sanity checks
aws sts get-caller-identity --region "$REGION" >/dev/null 2>&1 \
    || { echo "ERROR: aws sts get-caller-identity failed. Run 'aws sso login' first." >&2; exit 1; }

docker info >/dev/null 2>&1 \
    || { echo "ERROR: docker daemon not reachable. Is Docker Desktop running?" >&2; exit 1; }

echo "==> ECR login"
aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$REGISTRY"

cd "$REPO_ROOT"

echo "==> building backend  -> $BACKEND_REPO:$TAG"
docker build -t "$BACKEND_REPO:$TAG" backend/

echo "==> building frontend -> $FRONTEND_REPO:$TAG"
# NEXT_PUBLIC_* env vars are inlined at Next.js build time — they CAN'T be
# changed at runtime. So the image is bound to a single FQDN; staging needs
# its own build with its own FQDN.
docker build \
    --build-arg "NEXT_PUBLIC_API_URL=https://$FQDN" \
    --build-arg "NEXT_PUBLIC_WS_URL=wss://$FQDN/ws/chat" \
    -t "$FRONTEND_REPO:$TAG" \
    frontend/

echo "==> pushing"
docker push "$BACKEND_REPO:$TAG"
docker push "$FRONTEND_REPO:$TAG"

cat <<EOF

Images pushed:
  $BACKEND_REPO:$TAG
  $FRONTEND_REPO:$TAG

Next: trigger the EC2 bootstrap via SSM RunCommand.

  CMD_ID=\$(aws ssm send-command \\
    --region $REGION \\
    --document-name AWS-RunShellScript \\
    --instance-ids $INSTANCE_ID \\
    --parameters "commands=[\$(jq -Rs . < infra/scripts/bootstrap-ec2.sh)]" \\
    --output text --query 'Command.CommandId')
  echo "command id: \$CMD_ID"

  # Tail the run — it takes ~6 min on a clean box.
  watch -n 10 "aws ssm get-command-invocation \\
    --region $REGION \\
    --command-id \$CMD_ID \\
    --instance-id $INSTANCE_ID \\
    --query 'Status' --output text"

  # When Status=Success, smoke test:
  curl -fsS https://$FQDN/health
EOF
