# =============================================================================
# App layer — base/shared variables.
# =============================================================================
# App-specific inputs (instance sizing, DNS strategy, monitoring thresholds,
# etc.) are added in their own section when the composition lands. This file
# holds the cross-layer conventions plus the two deploy-time inputs that make
# the app layer the "deployable unit": image_tag and state_bucket.

variable "expected_account_id" {
  description = "12-digit AWS account ID this layer must run against. The account_guard module aborts plan/apply on mismatch. Not committed in tfvars; CI passes it (from `aws sts get-caller-identity`) and operators export TF_VAR_expected_account_id for manual runs."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for all app resources."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like e.g. eu-central-1."
  }
}

variable "environment" {
  description = "Deployment environment. Drives name_prefix (velocityai / velocityai-stage / velocityai-dev), SSM parameter paths, and per-env state keys. No default on purpose so CI must pass it explicitly (prevents accidental prod targeting)."
  type        = string

  validation {
    condition     = contains(["dev", "stage", "prod"], var.environment)
    error_message = "environment must be one of: dev, stage, prod."
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

# --- Deploy-time inputs (make the app layer the deployable unit) ------------

variable "state_bucket" {
  description = "Name of the S3 bucket holding Terraform remote state. Used to read the foundation layer's outputs via terraform_remote_state (see data.tf). Same bucket configured in backend.tf; passed as TF_VAR_state_bucket because backend config is not available to data sources."
  type        = string
}

variable "image_tag" {
  description = "Container image tag the app deploys (e.g. v20260630-abc1234 for a release, or <env>-<short-sha> for a branch build). Drives the docker-compose.yml object the EC2 pulls, so changing it is what ships a new build."
  type        = string
  default     = "main"

  validation {
    condition     = length(var.image_tag) > 0 && length(var.image_tag) <= 250
    error_message = "image_tag must be a non-empty tag, max 250 chars."
  }
}

# --- Compute ----------------------------------------------------------------

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "m6i.2xlarge"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 100
}

variable "data_volume_size_gb" {
  description = "Postgres data EBS volume size in GiB."
  type        = number
  default     = 50
}

variable "ssh_key_name" {
  description = "Existing EC2 keypair name for emergency SSH. Empty (default) = SSM Session Manager only."
  type        = string
  default     = ""
}

variable "disable_api_termination" {
  description = "If true, the EC2 instance cannot be terminated via the API/console. Default true; flip in tfvars to deliberately roll the instance."
  type        = bool
  default     = true
}

variable "disable_api_stop" {
  description = "If true, the EC2 instance cannot be stopped via the API/console. Default true."
  type        = bool
  default     = true
}

variable "git_ref" {
  description = "Branch/tag/SHA threaded into the on-host bootstrap (VELOCITYAI_GIT_REF). Defaults to main."
  type        = string
  default     = "main"

  validation {
    condition     = length(var.git_ref) > 0 && length(var.git_ref) <= 250
    error_message = "git_ref must be a non-empty git ref."
  }
}

# --- DNS --------------------------------------------------------------------

variable "use_nip_io" {
  description = "If true, derive the public hostname from the EIP via nip.io (no Route 53 needed). If false, create an A record under an existing Route 53 zone. Default true for sandbox/dev/stage; set false + route53_zone_name for a real prod domain."
  type        = bool
  default     = true
}

variable "route53_zone_name" {
  description = "Existing Route 53 hosted zone name (e.g. example.com). MUST already exist. Ignored when use_nip_io = true; supply empty in that case."
  type        = string
  default     = ""

  validation {
    condition     = var.route53_zone_name == "" || (!startswith(var.route53_zone_name, "http") && !startswith(var.route53_zone_name, ".") && !endswith(var.route53_zone_name, "."))
    error_message = "route53_zone_name must be a bare DNS name (no http://, no leading/trailing dots), or empty when use_nip_io = true."
  }
}

variable "app_subdomain" {
  description = "Subdomain the app answers on, e.g. 'velocityai'. Ignored when use_nip_io = true."
  type        = string
  default     = "velocityai"
}

variable "dns_ttl_seconds" {
  description = "TTL for the A record. Ignored when use_nip_io = true."
  type        = number
  default     = 60
}

# --- Bedrock / LLM (for the monitoring dimension) ---------------------------

variable "bedrock_model_id" {
  description = "Bedrock foundation-model ID the app invokes. Used as the Bedrock CloudWatch alarm dimension."
  type        = string
  default     = "anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID. Becomes the active model_id dimension when use_inference_profile_for_app = true."
  type        = string
  default     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "use_inference_profile_for_app" {
  description = "If true, the Bedrock alarm dimension is the inference profile ID (matches what the SDK passes as modelId)."
  type        = bool
  default     = true
}

# --- Monitoring -------------------------------------------------------------

variable "alert_email" {
  description = "Email subscribed to the SNS alerts topic and used as the ACME (Let's Encrypt) registration address. Injected per-env via TF_VAR_alert_email from the CI runner."
  type        = string

  validation {
    condition     = can(regex("^[^@]+@[^@]+\\.[^@]+$", var.alert_email))
    error_message = "alert_email must look like a valid email address."
  }
}

variable "log_retention_days" {
  description = "Default CloudWatch Log retention (days) for app log groups."
  type        = number
  default     = 30
}

variable "log_retention_overrides" {
  description = "Per-log-group retention overrides (full log group name -> days)."
  type        = map(number)
  default     = {}
}

variable "billing_alarm_threshold_usd" {
  description = "USD threshold for the EstimatedCharges alarm (us-east-1)."
  type        = number
  default     = 500
}

variable "bedrock_daily_token_threshold" {
  description = "Daily Bedrock InputTokenCount threshold (Sum over 24h)."
  type        = number
  default     = 5000000
}

variable "bedrock_throttles_threshold" {
  description = "Sum threshold for the Bedrock InvocationThrottles alarm over 5 min."
  type        = number
  default     = 5
}

variable "bedrock_throttles_evaluation_periods" {
  description = "Consecutive 5-minute windows the Bedrock throttle threshold must be exceeded before paging."
  type        = number
  default     = 2
}

variable "agent_error_rate_threshold" {
  description = "AgentErrorCount threshold (5-min Sum, 2 consecutive windows) above which the agent-error alarm fires."
  type        = number
  default     = 20
}

variable "stuck_workflows_threshold" {
  description = "Count of WorkflowRun rows stuck in `running` >60 min above which the alarm fires."
  type        = number
  default     = 0
}

variable "stuck_workflows_check_period" {
  description = "Stuck-workflows alarm period in seconds."
  type        = number
  default     = 1800
}
