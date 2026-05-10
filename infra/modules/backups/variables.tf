variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod)."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the project CMK (encrypts S3 backup bucket and AWS Backup vault)."
  type        = string
}

variable "bucket_name" {
  description = "Name of the S3 backup bucket. Must be globally unique. Suggested: flowin-$${env}-pg-dumps-<account-id>."
  type        = string

  validation {
    condition     = length(var.bucket_name) >= 3 && length(var.bucket_name) <= 63
    error_message = "S3 bucket names must be 3-63 chars."
  }
}

variable "daily_backup_retention_days" {
  description = "How long AWS Backup keeps each daily snapshot. Default 365d matches docs/SIMPLE_AWS_DEPLOYMENT.md §11."
  type        = number
  default     = 365

  validation {
    condition     = var.daily_backup_retention_days >= 7 && var.daily_backup_retention_days <= 36500
    error_message = "daily_backup_retention_days must be between 7 and 36500 (100 years)."
  }
}

variable "cold_storage_after_days" {
  description = "Days after which a recovery point transitions to cold storage. AWS Backup requires (delete_after - cold_storage_after) >= 90."
  type        = number
  default     = 30

  validation {
    condition     = var.cold_storage_after_days >= 1
    error_message = "cold_storage_after_days must be at least 1."
  }

  validation {
    condition     = var.cold_storage_after_days <= var.daily_backup_retention_days - 90
    error_message = "AWS Backup requires (daily_backup_retention_days - cold_storage_after_days) >= 90 days. Default retention 365 + cold_storage 30 satisfies this; tightening retention requires bringing cold_storage_after down with it."
  }
}

variable "backup_schedule_cron" {
  description = "Cron expression (UTC) for the AWS Backup daily rule."
  type        = string
  default     = "cron(0 3 ? * * *)"
}

variable "backup_selection_tag_key" {
  description = "Tag key used by the AWS Backup selection. Resources tagged with this key=value are protected."
  type        = string
  default     = "Backup"
}

variable "backup_selection_tag_value" {
  description = "Tag value used by the AWS Backup selection."
  type        = string
  default     = "true"
}

variable "noncurrent_version_expiration_days" {
  description = "S3 lifecycle: delete noncurrent object versions after N days."
  type        = number
  default     = 90
}

variable "transition_to_glacier_ir_days" {
  description = "S3 lifecycle: transition current pg_dumps to Glacier IR after N days."
  type        = number
  default     = 30
}

variable "pg_dump_expiry_days" {
  description = "S3 lifecycle: expire current versions of objects under the postgres/ prefix after N days. Default 365 matches docs/SIMPLE_AWS_DEPLOYMENT.md §11.2 (matches the AWS Backup retention floor)."
  type        = number
  default     = 365

  validation {
    condition     = var.pg_dump_expiry_days >= 7
    error_message = "pg_dump_expiry_days must be at least 7."
  }

  validation {
    condition     = var.pg_dump_expiry_days >= var.transition_to_glacier_ir_days
    error_message = "pg_dump_expiry_days must be >= transition_to_glacier_ir_days (otherwise objects expire before they ever transition to Glacier IR)."
  }
}

# --- AWS Backup Vault Lock (opt-in) ----------------------------------------
#
# Vault Lock locks the AWS Backup vault's retention policy in *compliance
# mode*. Once applied:
#   - Recovery points cannot be deleted before their scheduled delete_after.
#   - Neither the operator nor AWS Support can shorten the retention.
#   - The lock itself becomes immutable after the cooling-off window
#     (changeable_for_days = 3 below). Before then, the lock can be deleted
#     (this is the only escape hatch).
# This is a ONE-WAY operation. Useful for regulatory requirements
# (PCI-DSS, HIPAA, SOX); risky for ops who haven't validated their
# retention values against real recovery drills. Default false; flip to
# true only after observing a few cycles of daily snapshot retention.

variable "enable_vault_lock" {
  description = "If true, applies AWS Backup Vault Lock in compliance mode. ONE-WAY: once on, recovery points cannot be deleted before delete_after, and the lock itself cannot be removed without a 3-day cooling-off window. Recommended for production AFTER you've validated daily_backup_retention_days and cold_storage_after_days against real recovery drills. Default false."
  type        = bool
  default     = false
}

variable "vault_lock_min_retention_days" {
  description = "Minimum retention enforced by Vault Lock (compliance mode). Set to a floor below daily_backup_retention_days but above the operator's expected mistake-recovery window."
  type        = number
  default     = 7

  validation {
    condition     = var.vault_lock_min_retention_days >= 1
    error_message = "vault_lock_min_retention_days must be at least 1."
  }
}

variable "vault_lock_max_retention_days" {
  description = "Maximum retention enforced by Vault Lock. Should be >= daily_backup_retention_days (otherwise the plan tries to keep recovery points longer than the lock allows, and AWS Backup fails the job)."
  type        = number
  default     = 365

  validation {
    condition     = var.vault_lock_max_retention_days >= var.vault_lock_min_retention_days
    error_message = "vault_lock_max_retention_days must be >= vault_lock_min_retention_days."
  }
}

# --- S3 Object Lock (opt-in, governance mode) -------------------------------
#
# Object Lock prevents overwrite/delete of objects in the backup bucket for
# a retention period. Two modes:
#   - Compliance: nobody (not even root) can delete or change. ONE-WAY.
#   - Governance: only IAM principals with s3:BypassGovernanceRetention can
#     override. We default to GOVERNANCE — operator can bump to COMPLIANCE
#     by editing the resource (one-way for objects already locked).
#
# **CREATION-TIME ONLY.** Object Lock requires the bucket to be created
# with object_lock_enabled = true. It cannot be retrofitted to an existing
# bucket. If the bucket already exists in prod (this module sets
# prevent_destroy = true on aws_s3_bucket.backups), flipping this flag has
# NO EFFECT — Terraform plans a bucket replacement, which prevent_destroy
# correctly blocks. Recommended for new deployments only.

variable "enable_object_lock" {
  description = "If true, the backup bucket is created with Object Lock enabled (governance mode by default). MUST BE SET AT BUCKET CREATION — cannot be retrofitted. If you're applying to an already-existing bucket without object_lock_enabled, this flag has no effect (and Terraform will plan a bucket replacement, which prevent_destroy correctly blocks). Recommended for new deployments only."
  type        = bool
  default     = false
}

variable "object_lock_retention_days" {
  description = "Default retention period (days) for Object Lock in Governance mode. An IAM principal with s3:BypassGovernanceRetention can override per object. Default 35 — bump in tandem with daily_backup_retention_days for stricter retention."
  type        = number
  default     = 35

  validation {
    condition     = var.object_lock_retention_days >= 1
    error_message = "object_lock_retention_days must be at least 1."
  }
}
