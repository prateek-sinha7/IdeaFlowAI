# =============================================================================
# Foundation layer — base/shared variables.
# =============================================================================
# Foundation-specific inputs (network CIDRs, secrets, backups, bedrock, etc.)
# are added in their own section when the composition lands. This file holds
# the cross-layer conventions: the account guard, region, environment, and
# tag inputs.

variable "expected_account_id" {
  description = "12-digit AWS account ID this layer must run against. The account_guard module aborts plan/apply on mismatch. Not committed in tfvars; CI passes it (from `aws sts get-caller-identity`) and operators export TF_VAR_expected_account_id for manual runs."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  description = "AWS region for all foundation resources."
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

# --- Network ----------------------------------------------------------------

variable "availability_zone" {
  description = "Single AZ inside aws_region (e.g. eu-central-1a). The public subnet and the data EBS volume live here (single-AZ design)."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9][a-z]$", var.availability_zone))
    error_message = "availability_zone must look like e.g. eu-central-1a."
  }

  validation {
    # Cross-var (TF 1.9+): an AZ must belong to aws_region.
    condition     = startswith(var.availability_zone, var.aws_region)
    error_message = "availability_zone must be in aws_region (e.g. eu-central-1a for aws_region=eu-central-1)."
  }
}

variable "vpc_cidr" {
  description = "CIDR for the project VPC. MUST NOT overlap the other environments (dev 10.40/16, stage 10.30/16, prod 10.20/16 by convention)."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the public subnet (inside vpc_cidr)."
  type        = string
  default     = "10.20.1.0/24"
}

variable "ssh_allowed_cidrs" {
  description = "CIDRs permitted SSH ingress. Empty (default) = SSM Session Manager only (recommended). Must NOT contain 0.0.0.0/0 (rejected by the network module)."
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "Retention (days) for the VPC flow-logs CloudWatch log group. One of CloudWatch's allowed values."
  type        = number
  default     = 30
}

# --- Bedrock / LLM ----------------------------------------------------------

variable "bedrock_model_id" {
  description = "Bedrock foundation-model ID VelocityAI invokes. Must start with `anthropic.`, `eu.anthropic.`, or `us.anthropic.` to match the IAM Bedrock scope."
  type        = string
  default     = "anthropic.claude-haiku-4-5-20251001-v1:0"

  validation {
    condition     = startswith(var.bedrock_model_id, "anthropic.") || startswith(var.bedrock_model_id, "eu.anthropic.") || startswith(var.bedrock_model_id, "us.anthropic.")
    error_message = "bedrock_model_id must start with `anthropic.`, `eu.anthropic.`, or `us.anthropic.`."
  }
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID, used in IAM and as the active model_id when traffic must span regions."
  type        = string
  default     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "use_inference_profile_for_app" {
  description = "If true, the app's llm/model_id SSM parameter is the inference profile ID rather than the foundation-model ID."
  type        = bool
  default     = true
}

# --- Secrets / app config ---------------------------------------------------

variable "app_secret_key" {
  description = "Application JWT signing key. EMPTY DEFAULT: the secrets module generates a 64-char random_password on first apply. Override (>= 32 chars) only to import an existing key. Supply via TF_VAR_app_secret_key; never commit."
  type        = string
  sensitive   = true
  default     = ""

  validation {
    condition     = var.app_secret_key == "" || length(var.app_secret_key) >= 32
    error_message = "When set, app_secret_key must be at least 32 characters (or leave empty to auto-generate)."
  }
}

variable "db_password" {
  description = "Postgres password for the application user. EMPTY DEFAULT: the secrets module generates a 32-char random_password. Override (>= 16 chars) only when restoring a snapshot with a known role password. Supply via TF_VAR_db_password; never commit."
  type        = string
  sensitive   = true
  default     = ""

  validation {
    condition     = var.db_password == "" || length(var.db_password) >= 16
    error_message = "When set, db_password must be at least 16 characters (or leave empty to auto-generate)."
  }
}

variable "cors_origins" {
  description = "JSON-encoded list of CORS origins, e.g. '[\"https://velocityai.example.com\"]'. EMPTY DEFAULT: the on-host loader falls back to [\"https://$VELOCITYAI_FQDN\"]. Injected per-env via TF_VAR_cors_origins from the CI runner."
  type        = string
  default     = ""

  validation {
    condition     = var.cors_origins == "" || can(jsondecode(var.cors_origins))
    error_message = "When set, cors_origins must be valid JSON (a list of URL strings)."
  }

  validation {
    condition     = var.cors_origins == "" || (can(jsondecode(var.cors_origins)) ? alltrue([for o in jsondecode(var.cors_origins) : startswith(o, "https://") || startswith(o, "http://")]) : false)
    error_message = "When set, cors_origins entries must each start with http:// or https://."
  }
}

variable "access_token_expire_hours" {
  description = "JWT lifetime in hours."
  type        = number
  default     = 12
}

variable "langsmith_tracing" {
  description = "Optional LangSmith tracing toggle (e.g. \"true\"). Empty = no parameter created (tracing off)."
  type        = string
  default     = ""
}

variable "langsmith_api_key" {
  description = "Optional LangSmith API key. Empty = no parameter created. Supply via TF_VAR_langsmith_api_key."
  type        = string
  sensitive   = true
  default     = ""
}

variable "langsmith_project" {
  description = "Optional LangSmith project name (e.g. velocityai-prod). Empty = no parameter created."
  type        = string
  default     = ""
}

# --- Backups ----------------------------------------------------------------

variable "daily_backup_retention_days" {
  description = "How long AWS Backup keeps each daily snapshot. Module enforces (delete_after - cold_storage_after) >= 90."
  type        = number
  default     = 365
}

variable "cold_storage_after_days" {
  description = "Days after which a recovery point transitions to cold storage. AWS Backup requires (delete_after - cold_storage_after) >= 90."
  type        = number
  default     = 30
}

variable "pg_dump_expiry_days" {
  description = "Days after which current versions of pg_dump archives expire from the S3 backup bucket."
  type        = number
  default     = 365
}

variable "enable_vault_lock" {
  description = "If true, applies AWS Backup Vault Lock in compliance mode. ONE-WAY once the cooling-off window passes. Enable only after recovery drills."
  type        = bool
  default     = false
}

variable "vault_lock_min_retention_days" {
  description = "Minimum retention enforced by Vault Lock (compliance mode)."
  type        = number
  default     = 7
}

variable "vault_lock_max_retention_days" {
  description = "Maximum retention enforced by Vault Lock. Should be >= daily_backup_retention_days."
  type        = number
  default     = 365
}

variable "enable_object_lock" {
  description = "If true, the backup bucket is created with Object Lock (governance mode). MUST be set at bucket creation; cannot be retrofitted."
  type        = bool
  default     = false
}

variable "object_lock_retention_days" {
  description = "Default retention (days) for Object Lock in Governance mode."
  type        = number
  default     = 35
}

# --- Cognito (COGNITO-MIGRATION-PLAN Phase 1) -------------------------------

variable "cognito_enabled" {
  description = "Create the Cognito User Pool + app client + groups for this environment. Default false — an operator opts in per-environment (COGNITO-MIGRATION-PLAN §7 Phase 1). Creating a pool is not something to do by accident on a plan."
  type        = bool
  default     = false
}

variable "cognito_mfa_configuration" {
  description = "Pool-wide MFA setting. OFF/OPTIONAL/ON. OPTIONAL at cutover per the migration plan's Decision 4."
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.cognito_mfa_configuration)
    error_message = "cognito_mfa_configuration must be one of: OFF, OPTIONAL, ON."
  }
}

variable "cognito_access_token_validity_minutes" {
  description = "Cognito access/ID token lifetime in minutes."
  type        = number
  default     = 60
}

variable "cognito_refresh_token_validity_days" {
  description = "Cognito refresh token lifetime in days."
  type        = number
  default     = 30
}

# --- Auth cutover flags (COGNITO-MIGRATION-PLAN §7 Phase 5) -----------------
# Only take effect when cognito_enabled = true (see main.tf). Published to SSM
# so step 7 of the cutover checklist (flip AUTH_ALLOW_LEGACY_JWT to false) is a
# parameter change + restart per environment, not a code change.

variable "auth_provider" {
  description = "Active credential authority for NEW logins: \"local\" or \"cognito\". Stays \"local\" until this environment is actually cut over (Phase 5 step 1 deploys the code with Cognito available but not yet authoritative)."
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "cognito"], var.auth_provider)
    error_message = "auth_provider must be \"local\" or \"cognito\"."
  }
}

variable "auth_allow_legacy_jwt" {
  description = "Dual-accept window (Decision 11): accept BOTH legacy HS256 and Cognito RS256 tokens so cutover forces zero logouts. Flip to false only after step 8 (legacy tokens aged out)."
  type        = bool
  default     = true
}

variable "break_glass_enabled" {
  description = "Keep the single local-password break-glass admin reachable (Decision 12). Leave true unless you have a specific reason to close that path."
  type        = bool
  default     = true
}
