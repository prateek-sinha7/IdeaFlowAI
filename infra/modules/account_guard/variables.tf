variable "expected_account_id" {
  description = "12-digit AWS account ID Terraform must be authenticated to. Mismatch aborts plan/apply."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "expected_region" {
  description = "AWS region Terraform must be running in. Mismatch aborts plan/apply."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.expected_region))
    error_message = "expected_region must look like e.g. eu-west-2."
  }
}
