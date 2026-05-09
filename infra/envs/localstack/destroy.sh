#!/usr/bin/env bash
# Helper to tear down the LocalStack environment.
#
# A handful of resources have `lifecycle { prevent_destroy = true }` as a
# production safety. That isn't parametric on the resource, so for ephemeral
# test envs we drop those resources from state first, then destroy. The
# resources themselves disappear when LocalStack is reset / when `terraform
# destroy` removes their parents.
#
# Usage:  bash destroy.sh
set -eu  # NOTE: no `pipefail` — `grep -q` closes the pipe early and that
         # would otherwise mark the entire pipeline failed.

export PATH="${HOME}/Library/Python/3.9/bin:${PATH}"
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4666}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-west-2}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export TF_VAR_app_secret_key="${TF_VAR_app_secret_key:-localstack-destroy-placeholder-padding-32+chars}"
export TF_VAR_db_password="${TF_VAR_db_password:-localstack-destroy-pw-16chars}"

protected=(
  "module.kms.aws_kms_key.this"
  "module.backups.aws_s3_bucket.backups"
  "module.backups.aws_backup_vault.this"
  "module.compute.aws_ebs_volume.data"
)

state_snapshot=$(terraform state list)
for r in "${protected[@]}"; do
  if grep -qx "$r" <<<"$state_snapshot"; then
    echo "[destroy] removing $r from state (prevent_destroy lifecycle hardcoded for prod)"
    terraform state rm "$r"
  fi
done

terraform destroy -auto-approve "$@"
