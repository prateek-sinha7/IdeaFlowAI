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
  description = "Bedrock foundation-model ID VelocityAI invokes by default. Must be an `anthropic.`/`openai.` model ID, optionally geography-prefixed, to match the IAM Bedrock scope."
  type        = string
  default     = "anthropic.claude-haiku-4-5-20251001-v1:0"

  validation {
    condition     = can(regex("^((eu|us|apac|global)\\.)?(anthropic|openai)\\.", var.bedrock_model_id))
    error_message = "bedrock_model_id must be an `anthropic.` or `openai.` model ID, optionally prefixed with a geography (eu./us./apac./global.)."
  }
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID, used in IAM and as the active model_id when traffic must span regions."
  type        = string
  default     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "bedrock_allowed_inference_profile_ids" {
  description = <<-EOT
    Every Bedrock inference profile the EC2 instance role may invoke. The
    application can select any model in `backend/agents/capabilities/model_catalog.py`
    at run time, so each one needs to be in this grant — a catalogued model that
    is missing here fails mid-run with AccessDeniedException, not at deploy time.

    Profile IDs only; the foundation-model ARNs are derived in the iam module by
    stripping the geography prefix.

    DATA RESIDENCY: `eu.*` (Anthropic) profiles keep inference inside the EU.
    OpenAI GPT models publish no EU geographic profile — only `us.*` (not
    callable from an EU source region) and `global.*`, which routes to any
    commercial region where the model is deployed. The `global.openai.*` entries
    below therefore mean GPT prompts and completions may be processed outside
    the EU. Remove them to keep all inference EU-resident.
    https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html
  EOT
  type        = list(string)
  default = [
    # Anthropic — EU geographic profiles (EU-resident inference).
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu.anthropic.claude-sonnet-4-6",
    "eu.anthropic.claude-sonnet-4-20250514-v1:0",
    "eu.anthropic.claude-opus-4-5-20251101-v1:0",
    "eu.anthropic.claude-opus-4-6-v1",
    # OpenAI — global profiles (see DATA RESIDENCY above). eu-central-1 is a
    # valid SOURCE region for these; `us.openai.*` is not, so it is deliberately
    # absent.
    "global.openai.gpt-6-sol",
    "global.openai.gpt-6-luna",
    "global.openai.gpt-5.6-sol",
    "global.openai.gpt-5.6-terra",
    "global.openai.gpt-5.6-luna",
  ]

  validation {
    condition = alltrue([
      for id in var.bedrock_allowed_inference_profile_ids :
      can(regex("^(eu|us|apac|global)\\.[A-Za-z0-9][A-Za-z0-9.:_-]*$", id))
    ])
    error_message = "Each entry must be a geography-prefixed inference-profile ID (eu./us./apac./global.), e.g. global.openai.gpt-6-sol."
  }

  validation {
    condition     = contains(var.bedrock_allowed_inference_profile_ids, var.bedrock_inference_profile_id)
    error_message = "bedrock_allowed_inference_profile_ids must contain bedrock_inference_profile_id — the app's active profile has to be inside the IAM grant."
  }
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

# --- Cognito (mandatory as of Phase 4 of the Cognito-only auth migration) --
# Cognito is the sole authentication authority — there is no code path left
# that runs without a pool (backend/app/core/config.py's
# `_validate_cognito_config()` is unconditional outside development). The
# variable is KEPT rather than deleted outright: `module.cognito`'s `count`
# expression, `module.secrets`'s Cognito-parameter ternaries, and
# `module.iam`'s ARN plumbing all still read it, and forcing the value with a
# validation block is a smaller, more reviewable diff than rewriting every
# `var.cognito_enabled ? X : ""` conditional across three modules into an
# unconditional value in the same change that also drops three unrelated
# flags. The `false` escape hatch is gone: a plan that tries to set this to
# `false` fails validation instead of silently producing a Cognito-less stack.
variable "cognito_enabled" {
  description = "Create the Cognito User Pool + app client + groups for this environment. MUST be true — Cognito is the sole authentication authority as of Phase 4 of the Cognito-only auth migration (.kiro/specs/login/prompt.md); there is no supported deployment without it."
  type        = bool
  default     = true

  validation {
    condition     = var.cognito_enabled == true
    error_message = "cognito_enabled must be true. Cognito is the sole authentication authority; the application has no local-credential fallback to fall back to."
  }
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

variable "cognito_email_mfa_enabled" {
  description = <<-EOT
    Enable email one-time-password (EMAIL_OTP) as the second factor.

    Requires cognito_ses_source_arn to be set — Cognito rejects email MFA on a
    pool using the built-in sender.

    ACCEPTED TRADEOFF: AWS forbids email being both the second factor and the
    account-recovery channel, and this pool collects no phone numbers. Enabling
    this switches account recovery to `admin_only`, which SURRENDERS
    self-service password reset — resets become an administrator operation via
    POST /api/admin/users/{id}/reset-password. The backend is told via the
    SSM-published AUTH_EMAIL_MFA_ENABLED so /api/auth/forgot-password reports
    this explicitly rather than accepting a request that produces no email.
  EOT
  type        = bool
  default     = false

  validation {
    condition     = !var.cognito_email_mfa_enabled || length(var.cognito_ses_source_arn) > 0
    error_message = "cognito_email_mfa_enabled requires cognito_ses_source_arn to be set."
  }
}

variable "cognito_ses_source_arn" {
  description = "ARN of a VERIFIED SES identity (domain or email) for pool email. Empty keeps Cognito's built-in sender, which is rate limited well below production need and cannot carry email MFA."
  type        = string
  default     = ""
}

variable "cognito_ses_from_email_address" {
  description = "From: address for pool email. Must belong to the verified cognito_ses_source_arn identity. Required when that is set."
  type        = string
  default     = ""
}

variable "cognito_ses_reply_to_email_address" {
  description = "Optional Reply-To: address for pool email."
  type        = string
  default     = ""
}

variable "cognito_auth_session_validity_minutes" {
  description = "Lifetime of the Cognito auth-flow session, and therefore how long a delivered MFA code stays valid. 3-15 minutes; AWS defaults to 3, which is tight for emailed codes."
  type        = number
  default     = 10

  validation {
    condition     = var.cognito_auth_session_validity_minutes >= 3 && var.cognito_auth_session_validity_minutes <= 15
    error_message = "cognito_auth_session_validity_minutes must be between 3 and 15."
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

# --- Feature plan / threat protection (P2 fix, COGNITO-AUTH-QA-BUGS.md) ----
# The cognito module already supports both (Decision 8 / Phase 6 item 2), but
# the foundation layer never exposed them as variables -- ESSENTIALS and
# NO_ACTION were the only reachable values for every environment regardless
# of what an operator wanted, closing off threat protection entirely without
# a manual module-level Terraform edit.

variable "cognito_feature_plan" {
  description = "Cognito user pool feature plan: LITE, ESSENTIALS, or PLUS. ESSENTIALS (default) provides TOTP MFA. PLUS additionally enables threat protection (compromised-credential detection, adaptive auth) and costs more per MAU."
  type        = string
  default     = "ESSENTIALS"

  validation {
    condition     = contains(["LITE", "ESSENTIALS", "PLUS"], var.cognito_feature_plan)
    error_message = "cognito_feature_plan must be one of: LITE, ESSENTIALS, PLUS."
  }
}

variable "cognito_threat_protection_mode" {
  description = "Threat-protection enforcement for the standard auth flow. Requires cognito_feature_plan = PLUS; ignored (and the underlying resource skipped) otherwise. AUDIT logs risk assessments without blocking; ENFORCED applies the configured automatic responses; NO_ACTION disables it."
  type        = string
  default     = "NO_ACTION"

  validation {
    condition     = contains(["NO_ACTION", "AUDIT", "ENFORCED"], var.cognito_threat_protection_mode)
    error_message = "cognito_threat_protection_mode must be one of: NO_ACTION, AUDIT, ENFORCED."
  }
}

# --- Admin MFA (Cognito-only auth migration Phase 4) -----------------------
# auth_provider, auth_allow_legacy_jwt, and break_glass_enabled were REMOVED
# here in Phase 4 (.kiro/specs/login/prompt.md). Cognito is now the sole
# authentication authority — the backend's Settings class no longer declares
# AUTH_PROVIDER, AUTH_ALLOW_LEGACY_JWT, or BREAK_GLASS_ENABLED at all
# (backend/app/core/config.py), so publishing them to SSM would have been
# dead configuration nobody could read. See MERGE_NOTES.md §18 for the removal
# record and .planning/COGNITO-MIGRATION-PLAN.md's Amendment A1 for the
# decision (Decision 12 revoked).
#
# admin_mfa_required now DEFAULTS TO TRUE (Phase 4; it defaulted to false
# through Phase 1-3 so shipping the app-layer gate could not lock out admins
# who had not yet enrolled a factor). Every environment's admins have had the
# chance to enroll and complete a real MFA challenge by this phase — the gate
# is session-bound (core/identity.py::enforce_admin_mfa), so enrolling alone
# does not satisfy it; each admin must have signed in at least once through
# the challenge. An environment that genuinely still needs the old default
# sets `admin_mfa_required = false` explicitly in its own tfvars.
variable "admin_mfa_required" {
  description = "Require a confirmed second factor for admin operations (Phase 6 item 1 / P0 fix COGNITO-AUTH-QA-BUGS.md). Defaults to true as of Phase 4 of the Cognito-only auth migration — every admin is expected to have enrolled and completed a real MFA challenge (enrolling alone does not satisfy the session-bound gate; core/identity.py::enforce_admin_mfa checks iat against a stamp set only by a completed challenge). Set to false in a specific environment's tfvars only while its admins are still enrolling."
  type        = bool
  default     = true
}
