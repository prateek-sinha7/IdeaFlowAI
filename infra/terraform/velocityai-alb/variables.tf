# =============================================================================
# velocityai-alb — standalone layer, parameterized by environment.
# =============================================================================
# Adds an internal ALB in front of the EXISTING VelocityAI EC2 instance for
# ONE environment per apply (provisioned outside this Terraform tree). See
# main.tf for what this composes and modules/alb_internal/README.md for the
# security model.

variable "environment" {
  description = "Deployment environment. Determines the resource name prefix (prod is bare 'velocityai'; dev/stage get an '-<environment>' suffix), the state key, and (unless overridden) the auto-derived log bucket name."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be one of: dev, stage, prod."
  }
}

variable "expected_account_id" {
  description = "12-digit AWS account ID this layer must run against. The account_guard module aborts plan/apply on mismatch."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region. Must match the region the existing VPC/instance live in."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "owner" {
  description = "Tag value for Owner."
  type        = string
  default     = "velocityai"
}

variable "cost_center" {
  description = "Tag value for CostCenter."
  type        = string
  default     = "velocityai"
}

variable "assume_role_arn" {
  description = "Optional IAM role ARN the AWS provider assumes."
  type        = string
  default     = ""
}

variable "assume_role_external_id" {
  description = "Optional external ID for the assume-role call."
  type        = string
  default     = ""
}

# --- Existing infrastructure (looked up, not created) -----------------------

variable "vpc_id" {
  description = "ID of the existing VelocityAI VPC for this environment."
  type        = string
}

variable "subnet_ids" {
  description = "IDs of the two existing application subnets (different AZs) to place the ALB in. Do NOT use the Transit Gateway attachment subnets."
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "subnet_ids must contain at least two subnets."
  }
}

variable "instance_id" {
  description = "ID of the existing VelocityAI EC2 instance for this environment."
  type        = string
}

# --- Access control -----------------------------------------------------------

variable "trusted_ingress_cidrs" {
  description = "Approved corporate VPN/TGW-routed CIDR(s) permitted to reach this environment's ALB on 443/tcp. MUST NOT contain 0.0.0.0/0."
  type        = list(string)

  validation {
    condition     = !contains(var.trusted_ingress_cidrs, "0.0.0.0/0")
    error_message = "trusted_ingress_cidrs must NEVER contain 0.0.0.0/0."
  }
}

variable "certificate_arn" {
  description = "ARN of an ACM certificate (private CA or imported) matching THIS environment's ALB generated DNS name. Provision out-of-band; never generate private key material with Terraform."
  type        = string
}

variable "alarm_email" {
  description = "Email subscribed to this environment's ALB alerts SNS topic. Empty disables the subscription."
  type        = string
  default     = ""
}

variable "kms_key_arn" {
  description = "Optional KMS CMK ARN to encrypt the SNS alerts topic. Empty uses the AWS-managed SNS key."
  type        = string
  default     = ""
}

variable "log_bucket_name" {
  description = "Optional explicit S3 bucket name for ALB access/connection logs. Empty auto-derives '<name_prefix>-alb-logs-<account_id>-euc1' (e.g. velocityai-dev-alb-logs-<account>-euc1, or bare velocityai-alb-logs-<account>-euc1 for prod)."
  type        = string
  default     = ""
}
