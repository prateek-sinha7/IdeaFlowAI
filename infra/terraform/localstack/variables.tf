# Union of the inputs the composed modules need. Real values live in
# localstack.tfvars (committed — hermetic, no secrets). Defaults are
# LocalStack-friendly so an operator can `terraform apply` with the tfvars
# alone.

variable "expected_account_id" {
  description = "LocalStack default account is 000000000000."
  type        = string
  default     = "000000000000"
}

variable "aws_region" {
  description = "AWS region (LocalStack honours the value for ARNs)."
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Short env tag for the fixture (e.g. ls). Drives name_prefix velocityai-<env> and SSM paths."
  type        = string
  default     = "ls"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,15}$", var.environment))
    error_message = "environment must be lowercase, start with a letter, max 16 chars."
  }
}

variable "owner" {
  description = "Owner tag."
  type        = string
  default     = "velocityai-platform-team@example.test"
}

variable "cost_center" {
  description = "CostCenter tag."
  type        = string
  default     = "UKI-VELOCITYAI-LOCALSTACK"
}

# --- Network ----------------------------------------------------------------
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}
variable "public_subnet_cidr" {
  type    = string
  default = "10.20.1.0/24"
}
variable "availability_zone" {
  type    = string
  default = "eu-central-1a"
}
variable "ssh_allowed_cidrs" {
  type    = list(string)
  default = []
}
variable "log_retention_days" {
  type    = number
  default = 30
}

# --- Bedrock ----------------------------------------------------------------
variable "bedrock_model_id" {
  type    = string
  default = "anthropic.claude-haiku-4-5-20251001-v1:0"
}
variable "bedrock_inference_profile_id" {
  type    = string
  default = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}
variable "use_inference_profile_for_app" {
  type    = bool
  default = true
}

# --- Secrets (placeholders; LocalStack only) --------------------------------
variable "app_secret_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "db_password" {
  type      = string
  sensitive = true
  default   = ""
}
variable "cors_origins" {
  type    = string
  default = ""
}
variable "access_token_expire_hours" {
  type    = number
  default = 12
}

# --- Backups ----------------------------------------------------------------
variable "daily_backup_retention_days" {
  type    = number
  default = 365
}

# --- ECR --------------------------------------------------------------------
variable "ecr_repository_names" {
  type    = list(string)
  default = ["velocityai/backend", "velocityai/frontend"]
}

# --- Compute ----------------------------------------------------------------
variable "instance_type" {
  type    = string
  default = "m6i.2xlarge"
}
variable "root_volume_size_gb" {
  type    = number
  default = 100
}
variable "data_volume_size_gb" {
  type    = number
  default = 50
}
variable "ssh_key_name" {
  type    = string
  default = ""
}
variable "ami_id" {
  description = "LocalStack stub AMI (the Canonical filter resolves to nothing under LocalStack)."
  type        = string
  default     = "ami-03cf127a"
}

# --- DNS --------------------------------------------------------------------
variable "route53_zone_name" {
  type    = string
  default = "velocityai.test"
}
variable "app_subdomain" {
  type    = string
  default = "app"
}
variable "dns_ttl_seconds" {
  type    = number
  default = 60
}

# --- Monitoring -------------------------------------------------------------
variable "alert_email" {
  type    = string
  default = "velocityai-oncall@example.test"
}
variable "billing_alarm_threshold_usd" {
  type    = number
  default = 500
}
variable "audit_trail_bucket_force_destroy" {
  description = "LocalStack: let `terraform destroy` empty the CloudTrail bucket."
  type        = bool
  default     = true
}
