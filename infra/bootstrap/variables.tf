variable "expected_account_id" {
  description = "AWS account ID this bootstrap must run against. Plan/apply abort on mismatch."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for the state bucket and lock table."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "owner" {
  description = "Tag value for Owner. Drives AWS Cost Explorer / Billing reports filtered by tag — finance can answer 'how much is team X costing us?' when this is set. Default 'flowin' is fine for single-team / single-project accounts; override for multi-team / multi-project accounts where per-team cost allocation matters."
  type        = string
  default     = "flowin"
}

variable "cost_center" {
  description = "Tag value for CostCenter (finance code). Same Cost-Explorer reasoning as `owner`; default 'flowin' is the catch-all. Set to your org's real finance code (e.g. 'UKI-AI-001') when you want this stack's spend to roll up into a specific budget."
  type        = string
  default     = "flowin"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket name for the Terraform state. Suggested: flowin-tfstate-<account-id>-<region>."
  type        = string

  validation {
    condition     = length(var.state_bucket_name) >= 3 && length(var.state_bucket_name) <= 63
    error_message = "S3 bucket names must be 3-63 chars."
  }
}

variable "lock_table_name" {
  description = "DynamoDB table name for Terraform state locking."
  type        = string
  default     = "flowin-tfstate-locks"
}
