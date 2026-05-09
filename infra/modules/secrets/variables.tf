variable "name_prefix" {
  description = "Resource name prefix, e.g. flowin-prod (used in tags)."
  type        = string
}

variable "environment" {
  description = "Environment short name (e.g. prod). Used in parameter paths /flowin/$${env}/..."
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

variable "llm_provider" {
  description = "LLM provider tag, e.g. bedrock or anthropic."
  type        = string
  default     = "bedrock"

  validation {
    condition     = contains(["bedrock", "anthropic"], var.llm_provider)
    error_message = "llm_provider must be 'bedrock' or 'anthropic'."
  }
}

variable "bedrock_model_id" {
  description = "Bedrock foundation model ID (or inference profile ID) the app will invoke."
  type        = string
}

variable "app_secret_key" {
  description = "App SECRET_KEY (used to sign JWTs). Generate via `openssl rand -hex 64`. Set via tfvars or environment variable; never commit. Stored as SecureString."
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Postgres password for the application user. Stored as SecureString."
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Optional fallback Anthropic API key for emergency continuity. Empty default — set out-of-band only when Bedrock is unavailable."
  type        = string
  sensitive   = true
  default     = ""
}

variable "cors_origins" {
  description = "JSON-encoded list of CORS origins, e.g. '[\"https://flowin.example.com\"]'."
  type        = string
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
