locals {
  # Reference naming convention (matches foundation/app): prod is bare,
  # non-prod carries a suffix.
  #   prod  -> velocityai
  #   stage -> velocityai-stage
  #   dev   -> velocityai-dev
  name_suffix = var.environment == "prod" ? "" : "-${var.environment}"
  name_prefix = "velocityai${local.name_suffix}"

  # Same bucket-naming shape used for the S3 log bucket. Auto-derived unless
  # var.log_bucket_name overrides it (e.g. to reuse a pre-existing bucket).
  log_bucket_name = var.log_bucket_name != "" ? var.log_bucket_name : "${local.name_prefix}-alb-logs-${module.account_guard.account_id}-euc1"
}
