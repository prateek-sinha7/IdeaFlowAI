# Module: `monitoring`

Owns the environment's observability and audit surface: CloudWatch log groups,
the full alarm set (host CPU/memory/disk/inodes, nginx 5xx, DB connection
errors, Bedrock throttles/server-errors/daily-tokens, WebSocket disconnects,
billing, cert-renew, agent-error rate, stuck workflows, pg_dump heartbeat), the
SNS alert topics, and a CloudTrail management-event trail with metric-filter
alarms for unexpected secret reads / KMS decrypts.

## Resources created

- `aws_cloudwatch_log_group.groups` (per-suffix, KMS-encrypted, retention via
  `log_retention_days` + `log_retention_overrides`).
- ~25 `aws_cloudwatch_metric_alarm.*` (see `alarm_names` output for the list).
- `aws_sns_topic.alerts` (eu-central-1) + `aws_sns_topic.alerts_useast1`
  (billing alarms must publish to a same-region topic).
- `aws_cloudtrail.audit` + its S3 bucket + delivery log group + the
  `UnexpectedSecretRead` / `UnexpectedKmsDecrypt` metric filters/alarms.

## Usage

```hcl
module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix = local.name_prefix
  environment = var.environment
  instance_id = module.compute.instance_id
  kms_key_arn = module.kms.key_arn
  alert_email = var.alert_email

  bedrock_model_id        = local.effective_model_id
  instance_role_arn       = module.iam.instance_role_arn
  project_cmk_arn         = module.kms.key_arn
  secrets_path_prefix_arn = local.secrets_path_prefix_arn

  providers = { aws.useast1 = aws.useast1 }
}
```

## Inputs (selected)

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix. | `string` | — | yes |
| `environment` | Env short name (log-group paths). | `string` | — | yes |
| `instance_id` | EC2 instance ID alarms reference. | `string` | — | yes |
| `kms_key_arn` | CMK encrypting log groups + SNS topic. | `string` | — | yes |
| `bedrock_model_id` | Model ID the app invokes (Bedrock alarm `ModelId` dimension). | `string` | — | yes |
| `instance_role_arn` | EC2 instance role ARN (excluded from the unexpected-secret-read filter). | `string` | — | yes |
| `secrets_path_prefix_arn` | SSM parameter ARN prefix for the audit-trail filters. | `string` | — | yes |
| `project_cmk_arn` | Project CMK ARN (scopes the unexpected-KMS-decrypt filter). | `string` | — | yes |
| `alert_email` | Email subscribed to the SNS topic; empty disables the subscription. | `string` | `""` | no |
| `log_retention_days` + `log_retention_overrides` | Default + per-group CW Logs retention. | `number`/`map(number)` | `30` / `{}` | no |
| `*_threshold*` / `*_evaluation_periods` | Per-alarm tuning (CPU/mem/disk, Bedrock tokens/throttles, WS disconnects, agent errors, stuck workflows, billing). | `number` | various | no |
| `backup_vault_name` | Vault to wire job-state notifications onto; empty disables. | `string` | `""` | no |
| `audit_trail_*` | CloudTrail retention (CW/S3) + bucket force-destroy. | `number`/`bool` | `90` / `365` / `false` | no |

## Outputs

| Name | Description |
|------|-------------|
| `log_group_names` / `log_group_arns` | Map of friendly suffix → CW log group. |
| `alerts_topic_arn` / `alerts_topic_name` | The eu-central-1 SNS alert topic. |
| `alerts_useast1_topic_arn` | The us-east-1 topic used by the billing alarm. |
| `alarm_names` | Names of every alarm this module manages. |
| `audit_trail_name` / `_arn` / `_log_group_name` / `_bucket_name` | The CloudTrail audit trail surfaces. |

## Notes

- This module needs a `aws.useast1` provider alias passed in (billing/
  `EstimatedCharges` metrics only exist in us-east-1, and an alarm must publish
  to a same-region topic).
- `instance_role_arn` is excluded from the unexpected-secret-read filter so the
  legitimate `velocityai-load-secrets` reads don't page on-call; only
  unexpected principals trigger the alarm.
- Threshold defaults are tuned for a single instance at ~150 concurrent
  sessions — re-tune after a week of baseline data.
