variable "name_prefix" {
  description = "Resource name prefix, e.g. velocityai-prod (used in tags)."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod). Used in parameter paths /velocityai/$${env}/... — top-level keys are UPPERCASE (SECRET_KEY, DATABASE_PASSWORD, CORS_ORIGINS, ACCESS_TOKEN_EXPIRE_HOURS); nested namespaces are lower-case (llm/*) and translated to env-var names by the on-host loader."
  type        = string
}

variable "region" {
  description = "AWS region (used as the LLM region parameter value)."
  type        = string
}

variable "kms_key_id" {
  description = "KMS key ID or ARN that encrypts SecureString parameters."
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock foundation model ID (or inference profile ID) the app will invoke."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Cross-region inference profile ID. Written to /velocityai/$${env}/llm/inference_profile_id; the on-host loader maps it to BEDROCK_INFERENCE_PROFILE_ID, which the app prefers over BEDROCK_MODEL_ID (see backend/app/agents/base.py:54)."
  type        = string
  default     = ""
}

variable "app_secret_key" {
  description = "App SECRET_KEY (used to sign JWTs). Generate via `openssl rand -hex 64`. Set via tfvars / TF_VAR_app_secret_key; never commit. Stored as SecureString. EMPTY DEFAULT: a 64-char random_password is generated on first apply and used instead — operator only sets this if they want to import an existing key (e.g. migration from another env)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "db_password" {
  description = "Postgres password for the application user. Stored as SecureString. EMPTY DEFAULT: a 32-char random_password is generated on first apply. Override only when restoring from a snapshot whose existing Postgres role uses a known password."
  type        = string
  sensitive   = true
  default     = ""
}

# --- LangSmith — three optional, count-guarded parameters ------------------
#
# All three are independently optional: empty values cause the resource
# count to be 0, so no parameter is created. The on-host loader maps these
# UPPERCASE top-level keys directly to env vars of the same name, and the
# LangChain client treats the env as "tracing disabled" if any of them are
# absent. So leaving the defaults empty is a clean opt-out.

variable "langsmith_tracing" {
  description = "LangSmith tracing toggle (e.g. \"true\"/\"false\"). Empty default disables creation of the parameter."
  type        = string
  default     = ""
}

variable "langsmith_api_key" {
  description = "LangSmith API key. Stored as SecureString. Empty default disables creation of the parameter."
  type        = string
  sensitive   = true
  default     = ""
}

variable "langsmith_project" {
  description = "LangSmith project name (e.g. velocityai-prod). Empty default disables creation of the parameter."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "JSON-encoded list of CORS origins, e.g. '[\"https://velocityai.example.com\"]'. EMPTY DEFAULT: bootstrap script's velocityai-load-secrets falls back to `[\"https://$VELOCITYAI_FQDN\"]` when this parameter is empty — operator only sets this for multi-origin deployments."
  type        = string
  default     = ""
}

variable "access_token_expire_hours" {
  description = "JWT lifetime in hours. NOTE (Cognito migration): once Cognito is the active auth provider, this setting governs break-glass local-admin tokens ONLY — Cognito controls its own access-token lifetime via the app client (see the cognito module's access_token_validity_minutes)."
  type        = number
  default     = 12

  validation {
    condition     = var.access_token_expire_hours > 0 && var.access_token_expire_hours <= 168
    error_message = "access_token_expire_hours must be between 1 and 168 (one week)."
  }
}

# --- Cognito (COGNITO-MIGRATION-PLAN §6.3 / §11) ---------------------------
# Four parameters written only when the caller opts in. Environments that
# haven't yet run Phase 1 of the Cognito migration get no new parameters — the
# backend's boot guard (core/config.py) treats an unset pool id as "Cognito not
# configured" and refuses to boot ONLY if AUTH_PROVIDER=cognito is also set, so
# this is safe to leave off during the transitional phases.

variable "cognito_enabled" {
  description = "Whether to create the COGNITO_* parameters. MUST be a plan-time-known boolean rather than a `length(var.cognito_user_pool_id) > 0` test, because the pool id/client id/secret are module outputs that are unknown until apply — counting on them yields \"The count value depends on resource attributes that cannot be determined until apply\"."
  type        = bool
  default     = false
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID (module.cognito.user_pool_id). Empty (default) skips creating any COGNITO_* parameters."
  type        = string
  default     = ""
}

variable "cognito_client_id" {
  description = "Cognito app client ID (module.cognito.client_id)."
  type        = string
  default     = ""
}

variable "cognito_client_secret" {
  description = "Cognito app client secret (module.cognito.client_secret). Stored as SecureString. Sensitive."
  type        = string
  sensitive   = true
  default     = ""
}

variable "cognito_region" {
  description = "AWS region the Cognito pool lives in. Empty default: on-host loader falls back to AWS_REGION when COGNITO_REGION is absent."
  type        = string
  default     = ""
}

# --- Auth cutover flags (COGNITO-MIGRATION-PLAN §7 Phase 5) -----------------
# These three are SSM-managed (not baked into the image) precisely so the
# cutover sequence -- deploy dual-accept, provision users, then flip
# AUTH_ALLOW_LEGACY_JWT to false -- is an operational parameter change plus a
# service restart, NOT a code change and redeploy. That is what makes step 7
# of the Phase 5 checklist safely reversible per environment.

variable "auth_provider" {
  description = "Active credential authority for NEW logins: \"local\" (pre-migration behaviour) or \"cognito\". Empty (default) omits the parameter, so the application keeps its own \"local\" default."
  type        = string
  default     = ""

  validation {
    condition     = var.auth_provider == "" || contains(["local", "cognito"], var.auth_provider)
    error_message = "auth_provider must be empty, \"local\", or \"cognito\"."
  }
}

variable "auth_allow_legacy_jwt" {
  description = "Dual-accept window (Decision 11). \"true\" during cutover so BOTH legacy HS256 and Cognito RS256 tokens are accepted (zero forced logouts); flip to \"false\" per environment once legacy tokens have aged out. Empty omits the parameter (application default: true)."
  type        = string
  default     = ""

  validation {
    condition     = var.auth_allow_legacy_jwt == "" || contains(["true", "false"], var.auth_allow_legacy_jwt)
    error_message = "auth_allow_legacy_jwt must be empty, \"true\", or \"false\"."
  }
}

variable "break_glass_enabled" {
  description = "Kill switch for the single local-password break-glass admin (Decision 12). Empty omits the parameter (application default: true)."
  type        = string
  default     = ""

  validation {
    condition     = var.break_glass_enabled == "" || contains(["true", "false"], var.break_glass_enabled)
    error_message = "break_glass_enabled must be empty, \"true\", or \"false\"."
  }
}
