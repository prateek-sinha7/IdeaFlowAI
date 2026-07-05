variable "expected_account_id" {
  description = "12-digit AWS account ID this layer must run against. The account_guard module aborts plan/apply on mismatch. Not committed in tfvars; the CI pipeline passes it (derived from `aws sts get-caller-identity`), and operators export TF_VAR_expected_account_id for manual runs."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for the shared resources (must match the rest of the stack)."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "owner" {
  description = "Tag value for Owner. Drives Cost Explorer / Billing reports filtered by tag. Override via TF_VAR_owner."
  type        = string
  default     = "velocityai"
}

variable "cost_center" {
  description = "Tag value for CostCenter (finance code). Override via TF_VAR_cost_center when spend must roll up into a specific budget."
  type        = string
  default     = "velocityai"
}

variable "assume_role_arn" {
  description = "Optional IAM role ARN the AWS provider assumes. Empty = use the caller's identity directly."
  type        = string
  default     = ""
}

variable "assume_role_external_id" {
  description = "Optional external ID for the assume-role call."
  type        = string
  default     = ""
}

# --- ECR (shared container registries) --------------------------------------

variable "ecr_repository_names" {
  description = "Container image repositories shared across all environments. Namespaced as velocityai/<image> so images are addressed as velocityai/<image>:<tag>."
  type        = list(string)
  default = [
    "velocityai/backend",
    "velocityai/frontend",
  ]
}

variable "ecr_image_tag_mutability" {
  description = "ECR tag mutability for the shared repos (MUTABLE or IMMUTABLE). MUTABLE lets a build retry re-push the same tag (the reference CI model)."
  type        = string
  default     = "MUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.ecr_image_tag_mutability)
    error_message = "ecr_image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "ecr_keep_last_images" {
  description = "Number of most-recent branch-build images to retain per repo, per environment tag prefix. Release-tagged images (no prefix) are retained indefinitely."
  type        = number
  default     = 10
}
