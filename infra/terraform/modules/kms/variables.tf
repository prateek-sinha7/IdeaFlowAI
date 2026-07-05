variable "name_prefix" {
  description = "Resource name prefix, e.g. velocityai-prod."
  type        = string
}

variable "account_id" {
  description = "AWS account ID (for the key policy root principal)."
  type        = string
}

variable "deletion_window_in_days" {
  description = "Days before key is permanently deleted after `terraform destroy`."
  type        = number
  default     = 30

  validation {
    condition     = var.deletion_window_in_days >= 7 && var.deletion_window_in_days <= 30
    error_message = "KMS deletion window must be between 7 and 30 days."
  }
}

variable "additional_principals" {
  description = "Extra IAM principal ARNs allowed to use the key (e.g. AWS Backup service role). Empty by default."
  type        = list(string)
  default     = []
}

variable "region" {
  description = "AWS region (used to scope service-principal grants for logs / sns)."
  type        = string
}

variable "allow_logs_service" {
  description = "If true, allow CloudWatch Logs service principal to use the key for log-group encryption (scoped via condition)."
  type        = bool
  default     = true
}

variable "allow_sns_service" {
  description = "If true, allow SNS service principal to use the key (so KMS-encrypted topics work)."
  type        = bool
  default     = true
}

variable "allow_s3_service" {
  description = "If true, allow S3 service principal to use the key (so SSE-KMS works on encrypted buckets in this account)."
  type        = bool
  default     = true
}

variable "allow_backup_service" {
  description = "If true, allow AWS Backup service principal to use the key for backup vault encryption."
  type        = bool
  default     = true
}

variable "allow_cloudtrail_service" {
  description = "If true, allow CloudTrail service principal to use the key so trails configured with kms_key_id = this CMK can encrypt log files. Confused-deputy guarded by (a) aws:SourceAccount pinned to var.account_id, (b) aws:SourceArn pinned to the exact $${var.name_prefix}-audit trail in this account+region (string-level coupling via name_prefix, no resource-graph cycle), and (c) kms:EncryptionContext:aws:cloudtrail:arn pinned to the same trail ARN (defense in depth — CloudTrail auto-supplies this context on encryption operations)."
  type        = bool
  default     = true
}
