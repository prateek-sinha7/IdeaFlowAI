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
