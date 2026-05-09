variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
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
  description = "Single AZ to deploy into (e.g. eu-west-2a). Single-AZ design — see SIMPLE_AWS_DEPLOYMENT.md §6."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", var.availability_zone))
    error_message = "availability_zone must look like e.g. eu-west-2a."
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
