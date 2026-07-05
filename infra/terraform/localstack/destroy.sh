#!/usr/bin/env bash
# Tear down the LocalStack fixture.
#
# Several resources carry lifecycle.prevent_destroy = true (KMS CMK, S3 backup
# bucket, AWS Backup vault/plan/selection, data EBS volume, EIP, IAM role +
# instance profile). Plain `terraform destroy` refuses to remove them, so we
# drop them from the LOCAL state first (safe — LocalStack state is ephemeral
# and gitignored), then destroy the rest.
set -euo pipefail
cd "$(dirname "$0")"

PROTECTED=(
  'module.kms.aws_kms_key.this'
  'module.backups.aws_s3_bucket.backups'
  'module.backups.aws_backup_vault.this'
  'module.backups.aws_backup_plan.daily'
  'module.backups.aws_backup_selection.by_tag'
  'module.compute.aws_ebs_volume.data'
  'module.compute.aws_eip.this'
  'module.iam.aws_iam_role.instance'
  'module.iam.aws_iam_instance_profile.instance'
)

for addr in "${PROTECTED[@]}"; do
  terraform state rm "$addr" 2>/dev/null || echo "  (not in state: $addr)"
done

terraform destroy -auto-approve -var-file=localstack.tfvars
echo "LocalStack fixture destroyed."
