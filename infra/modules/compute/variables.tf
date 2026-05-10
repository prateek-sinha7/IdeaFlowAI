variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod)."
  type        = string
}

variable "region" {
  description = "AWS region (used in user-data templates)."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "m6i.2xlarge"
}

variable "subnet_id" {
  description = "Subnet ID to launch into."
  type        = string
}

variable "availability_zone" {
  description = "AZ for the data EBS volume — must match the subnet's AZ."
  type        = string
}

variable "security_group_id" {
  description = "Security group to attach to the primary ENI."
  type        = string
}

variable "iam_instance_profile_name" {
  description = "Instance profile to attach."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the project CMK; encrypts root + data EBS volumes."
  type        = string
}

variable "ssh_key_name" {
  description = "Name of an existing EC2 keypair for emergency SSH (the day-to-day path is SSM Session Manager). Empty string disables --key-name."
  type        = string
  default     = ""
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 100

  validation {
    condition     = var.root_volume_size_gb >= 30
    error_message = "Root volume must be at least 30 GiB."
  }
}

variable "data_volume_size_gb" {
  description = "Data EBS volume size in GiB. Mounted at /var/lib/postgresql."
  type        = number
  default     = 50

  validation {
    condition     = var.data_volume_size_gb >= 20
    error_message = "Data volume must be at least 20 GiB."
  }
}

variable "data_volume_device_name" {
  description = "Device name for the data volume attachment (block device name as seen by AWS)."
  type        = string
  default     = "/dev/sdh"
}

variable "ami_owner" {
  description = "AMI owner ID. Default 099720109477 = Canonical."
  type        = string
  default     = "099720109477"
}

variable "ami_name_pattern" {
  description = "AMI name filter pattern for the latest Ubuntu 24.04 LTS amd64 image."
  type        = string
  default     = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
}

variable "ami_id" {
  description = "Optional override for the AMI ID. When non-empty the data-source lookup is bypassed (useful for environments such as LocalStack where the Canonical filter doesn't resolve). Empty default preserves prod behaviour."
  type        = string
  default     = ""
}

variable "detailed_monitoring" {
  description = "Toggle EC2 detailed (1-minute) CloudWatch monitoring. Default true (matches prod). Set false in environments such as LocalStack where MonitorInstances isn't implemented."
  type        = bool
  default     = true
}

variable "ebs_optimized" {
  description = "Toggle EBS-optimized launch. Default true. Set false in environments where the chosen AMI doesn't support it."
  type        = bool
  default     = true
}

variable "user_data_extra_env" {
  description = "Extra key/value pairs injected into the user-data template (e.g. backup bucket name)."
  type        = map(string)
  default     = {}
}

variable "protect_eip" {
  description = "Documents the EIP-protection contract. Currently advisory only: Terraform's lifecycle.prevent_destroy field accepts only literal bools (verified on TF 1.15.1, May 2026), so the EIP is unconditionally `prevent_destroy = true` and ephemeral envs (LocalStack) state-rm it before `terraform destroy` — see envs/localstack/destroy.sh. The variable is plumbed through the modules so a future Terraform release that loosens this restriction can be adopted with a one-line change in modules/compute/main.tf."
  type        = bool
  default     = true
}
