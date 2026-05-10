variable "expected_account_id" {
  description = "AWS account ID this stack must run against. Plan/apply abort on mismatch. LocalStack default = 000000000000."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "availability_zone" {
  description = "Single AZ inside aws_region (e.g. eu-central-1a)."
  type        = string
  default     = "eu-central-1a"
}

variable "environment" {
  description = "Environment short name; appears in name_prefix and parameter paths."
  type        = string
  default     = "ls"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,15}$", var.environment))
    error_message = "environment must be lowercase, start with a letter, max 16 chars."
  }
}

variable "owner" {
  description = "Tag value for Owner (team contact)."
  type        = string
}

variable "cost_center" {
  description = "Tag value for CostCenter (finance code)."
  type        = string
}

# --- Network ----------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR for the project VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the public subnet."
  type        = string
  default     = "10.20.1.0/24"
}

variable "ssh_allowed_cidrs" {
  description = "List of CIDRs permitted SSH ingress. Empty = SSM-only."
  type        = list(string)
  default     = []
}

# --- Compute ----------------------------------------------------------------

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "m6i.2xlarge"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size."
  type        = number
  default     = 100
}

variable "data_volume_size_gb" {
  description = "Postgres data EBS volume size."
  type        = number
  default     = 50
}

variable "ssh_key_name" {
  description = "Existing EC2 keypair name. Empty disables --key-name."
  type        = string
  default     = ""
}

variable "ami_id" {
  description = "AMI ID override. Required for LocalStack since the Canonical filter doesn't resolve there. Empty falls back to data-source lookup."
  type        = string
  default     = ""
}

# --- DNS --------------------------------------------------------------------

variable "route53_zone_name" {
  description = "Existing Route 53 hosted zone name."
  type        = string
}

variable "app_subdomain" {
  description = "Subdomain (without zone) the app answers on."
  type        = string
  default     = "flowin"
}

variable "dns_ttl_seconds" {
  description = "TTL for the A record."
  type        = number
  default     = 60
}

# --- Bedrock / LLM ----------------------------------------------------------

variable "bedrock_model_id" {
  description = "Bedrock foundation-model ID."
  type        = string
  default     = "anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID."
  type        = string
  default     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "use_inference_profile_for_app" {
  description = "If true, /flowin/$${env}/llm/model_id is the inference profile ID."
  type        = bool
  default     = true
}

# --- Secrets / app config ---------------------------------------------------

variable "app_secret_key" {
  description = "App JWT signing key (>= 32 chars)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.app_secret_key) >= 32
    error_message = "app_secret_key must be at least 32 characters."
  }
}

variable "db_password" {
  description = "Postgres app user password (>= 16 chars)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "db_password must be at least 16 characters."
  }
}

variable "cors_origins" {
  description = "JSON-encoded list of CORS origins."
  type        = string
  default     = "[\"https://flowin.test\"]"
}

variable "access_token_expire_hours" {
  description = "JWT lifetime in hours."
  type        = number
  default     = 12
}

# --- Backups ----------------------------------------------------------------

variable "backup_bucket_name" {
  description = "Globally-unique name for the pg_dump backup bucket."
  type        = string
}

variable "daily_backup_retention_days" {
  description = "How long AWS Backup keeps each daily snapshot."
  type        = number
  default     = 35
}

# --- Monitoring -------------------------------------------------------------

variable "alert_email" {
  description = "Email subscribed to the SNS alerts topic."
  type        = string

  validation {
    condition     = can(regex("^[^@]+@[^@]+\\.[^@]+$", var.alert_email))
    error_message = "alert_email must look like a valid email address."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Log retention in days."
  type        = number
  default     = 30
}

variable "billing_alarm_threshold_usd" {
  description = "USD threshold for the EstimatedCharges alarm (us-east-1)."
  type        = number
  default     = 500
}

variable "bedrock_daily_token_threshold" {
  description = "Daily Bedrock InputTokenCount threshold (Sum over 24h). Default 5,000,000 input tokens."
  type        = number
  default     = 5000000
}
