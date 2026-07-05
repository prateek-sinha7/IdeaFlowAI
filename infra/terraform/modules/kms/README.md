# Module: `kms`

Creates the per-environment project Customer-Managed Key (CMK) and a friendly
alias. The CMK encrypts everything the stack persists: EBS volumes, CloudWatch
log groups, the SNS alerts topic, S3 buckets (backup + audit trail), the AWS
Backup vault, and CloudTrail log files.

Rotation is enabled. Each service principal that needs the key (CloudWatch
Logs, SNS, S3, AWS Backup, CloudTrail) is granted via a toggle, and every
service grant is confused-deputy guarded (`aws:SourceAccount` / `aws:SourceArn`
conditions) so a leaked grant cannot be used cross-account.

## Resources created

- `aws_kms_key.this` — the project CMK (rotation on, configurable deletion window).
- `aws_kms_alias.this` — `alias/<name_prefix>` pointing at the key.

## Usage

```hcl
module "kms" {
  source = "../../modules/kms"

  name_prefix = local.name_prefix # e.g. velocityai-prod
  account_id  = module.account_guard.account_id
  region      = var.aws_region
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix, e.g. `velocityai-prod`. | `string` | — | yes |
| `account_id` | AWS account ID (key-policy root principal). | `string` | — | yes |
| `region` | AWS region (scopes service-principal grants for logs/sns). | `string` | — | yes |
| `deletion_window_in_days` | Days before the key is permanently deleted after `terraform destroy`. | `number` | `30` | no |
| `additional_principals` | Extra IAM principal ARNs allowed to use the key (e.g. an AWS Backup role). | `list(string)` | `[]` | no |
| `allow_logs_service` | Allow CloudWatch Logs to use the key for log-group encryption. | `bool` | `true` | no |
| `allow_sns_service` | Allow SNS to use the key (KMS-encrypted topics). | `bool` | `true` | no |
| `allow_s3_service` | Allow S3 to use the key (SSE-KMS buckets). | `bool` | `true` | no |
| `allow_backup_service` | Allow AWS Backup to use the key for vault encryption. | `bool` | `true` | no |
| `allow_cloudtrail_service` | Allow CloudTrail to use the key (guarded to the `<name_prefix>-audit` trail). | `bool` | `true` | no |

## Outputs

| Name | Description |
|------|-------------|
| `key_id` | KMS key ID. |
| `key_arn` | KMS key ARN. |
| `alias_name` | Alias name (e.g. `alias/velocityai-prod`). |
| `alias_arn` | Alias ARN. |

## Notes

- `deletion_window_in_days` is validated to the AWS-allowed `7..30` range.
- The CloudTrail grant pins `aws:SourceArn` to `<name_prefix>-audit` and the
  `kms:EncryptionContext:aws:cloudtrail:arn` — keep the trail name aligned with
  `name_prefix` (the `monitoring` module already does).
