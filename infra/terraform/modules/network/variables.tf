variable "name_prefix" {
  description = "Resource name prefix, e.g. velocityai-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod, ls). Appears in the VPC flow-logs CloudWatch log-group path so it shares the `/velocityai/$${environment}/...` tree with the monitoring module's groups."
  type        = string
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,15}$", var.environment))
    error_message = "environment must be lowercase, start with a letter, max 16 chars."
  }
}

variable "vpc_cidr" {
  description = "Primary CIDR block for the project VPC."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid CIDR block."
  }
}

variable "public_subnet_cidr" {
  description = "CIDR for the single public subnet that hosts the EC2 instance."
  type        = string
  default     = "10.20.1.0/24"

  validation {
    condition     = can(cidrnetmask(var.public_subnet_cidr))
    error_message = "public_subnet_cidr must be a valid CIDR block."
  }
}

variable "availability_zone" {
  description = "Single AZ to deploy into (e.g. eu-central-1a). Single-AZ design — see SIMPLE_AWS_DEPLOYMENT.md §6."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", var.availability_zone))
    error_message = "availability_zone must look like e.g. eu-central-1a."
  }
}

variable "ssh_allowed_cidrs" {
  description = "List of CIDR blocks permitted to reach 22/tcp on the instance. Empty list = no SSH ingress at the SG level (use SSM Session Manager instead). MUST not contain 0.0.0.0/0."
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.ssh_allowed_cidrs, "0.0.0.0/0")
    error_message = "ssh_allowed_cidrs must NEVER contain 0.0.0.0/0. Use a bastion CIDR or leave empty and rely on SSM Session Manager."
  }

  validation {
    condition = alltrue([
      for cidr in var.ssh_allowed_cidrs : can(cidrnetmask(cidr))
    ])
    error_message = "Each ssh_allowed_cidrs entry must be a valid CIDR."
  }
}

variable "region" {
  description = "Region (used to construct VPC endpoint service names)."
  type        = string
}

# --- Flow logs / endpoint policies inputs -----------------------------------

variable "account_id" {
  description = "AWS account ID. Used by the VPC flow-logs IAM trust-policy aws:SourceAccount condition and by the VPC-endpoint policies' aws:PrincipalAccount condition. Mismatch with the deploying account fails plan/apply via the account_guard module."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "kms_key_arn" {
  description = "ARN of the project CMK used to encrypt the VPC flow-logs CloudWatch log group at rest. The KMS key policy must already permit logs.<region>.amazonaws.com (the modules/kms key policy does)."
  type        = string
}

variable "log_retention_days" {
  description = "Retention (days) for the VPC flow-logs CloudWatch log group. Same concern as the monitoring module's same-named variable but a separate value here so the network module stays self-contained — wire from the env composition with the same number used elsewhere."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be one of the values CloudWatch Logs accepts (1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 2192, 2557, 2922, 3288, 3653)."
  }
}

variable "backup_bucket_arn" {
  description = "ARN of the S3 backup bucket. Used to scope the S3 gateway VPC endpoint's Resource policy (see aws_vpc_endpoint.s3 in main.tf). Empty string falls back to a Resource:* allow-list — useful for ephemeral envs where the bucket isn't in the dependency graph yet. Always set in prod."
  type        = string
  default     = ""
}
