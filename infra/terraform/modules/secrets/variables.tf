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
  description = "JWT lifetime in hours."
  type        = number
  default     = 12

  validation {
    condition     = var.access_token_expire_hours > 0 && var.access_token_expire_hours <= 168
    error_message = "access_token_expire_hours must be between 1 and 168 (one week)."
  }
}
