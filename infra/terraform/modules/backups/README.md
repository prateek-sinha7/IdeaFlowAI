# Module: `backups`

Owns the environment's backup substrate: the S3 bucket that stores `pg_dump`
archives and the AWS Backup vault + plan + selection (tag-driven) that snapshots
the data EBS volume. Both are encrypted with the project CMK. Optional Vault
Lock and S3 Object Lock add write-once compliance guarantees.

## Resources created

- `aws_s3_bucket.backups` (`prevent_destroy`) + versioning, SSE-KMS,
  public-access block, and a lifecycle config (Glacier IR transition,
  noncurrent-version expiry, pg_dump expiry).
- `aws_backup_vault.this`, `aws_backup_plan.daily`, `aws_backup_selection`
  (selects resources tagged `Backup=true`), and the AWS Backup service role.
- Optional `aws_backup_vault_lock_configuration` (compliance mode) and S3
  Object Lock when the opt-in flags are set.

## Usage

```hcl
module "backups" {
  source = "../../modules/backups"

  name_prefix = local.name_prefix
  environment = var.environment
  kms_key_arn = module.kms.key_arn
  bucket_name = "velocityai-${var.environment}-pg-dumps-${module.account_guard.account_id}"
}
```

## Inputs (selected)

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| `name_prefix` | Resource name prefix, e.g. `velocityai-prod`. | `string` | — | yes |
| `environment` | Environment short name. | `string` | — | yes |
| `kms_key_arn` | Project CMK encrypting the bucket + vault. | `string` | — | yes |
| `bucket_name` | Globally-unique S3 backup bucket name (3–63 chars). | `string` | — | yes |
| `daily_backup_retention_days` | How long AWS Backup keeps each daily snapshot. | `number` | `365` | no |
| `cold_storage_after_days` | Days before a recovery point moves to cold storage (`retention - cold >= 90`). | `number` | `30` | no |
| `backup_schedule_cron` | UTC cron for the daily rule. | `string` | `"cron(0 3 ? * * *)"` | no |
| `backup_selection_tag_key` / `_value` | Tag selecting protected resources. | `string` | `"Backup"` / `"true"` | no |
| `transition_to_glacier_ir_days` / `pg_dump_expiry_days` / `noncurrent_version_expiration_days` | S3 lifecycle knobs. | `number` | `30` / `365` / `90` | no |
| `enable_vault_lock` + `vault_lock_min/max_retention_days` | Opt-in **one-way** Backup Vault Lock (compliance mode). | `bool`/`number` | `false` / `7` / `365` | no |
| `enable_object_lock` + `object_lock_retention_days` | Opt-in S3 Object Lock (creation-time only, governance mode). | `bool`/`number` | `false` / `35` | no |

## Outputs

| Name | Description |
|------|-------------|
| `backup_bucket_name` / `backup_bucket_arn` | The pg_dump S3 bucket (feed the ARN to the `iam` module). |
| `backup_vault_name` / `backup_vault_arn` | The AWS Backup vault. |
| `backup_plan_id` | The AWS Backup plan ID. |
| `backup_role_arn` | The AWS Backup service role ARN (used in selections). |

## Notes

- `enable_vault_lock` is a **one-way** operation — once locked (after a 3-day
  cooling-off), recovery points cannot be deleted before `delete_after` and the
  lock cannot be removed. Turn it on only after validating retention against a
  real recovery drill.
- `enable_object_lock` must be set at **bucket creation**; it cannot be
  retrofitted to the existing `prevent_destroy` bucket.
- Cross-variable validations enforce AWS Backup's `retention - cold_storage >=
  90` rule and `pg_dump_expiry >= glacier_ir_transition`.
