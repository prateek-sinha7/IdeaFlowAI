locals {
  prefix = "/flowin/${var.environment}"
}

# Notes on the schema
# -------------------
# Terraform writes the canonical UPPERCASE top-level keys that the application's
# Settings (backend/app/core/config.py) reads directly, plus the existing nested
# `llm/*` and `anthropic/*` namespaces. The on-host loader translates the nested
# paths to env-var names per the rule documented in
# docs/SIMPLE_AWS_DEPLOYMENT.md §9.3.
#
# The composite `DATABASE_URL` is intentionally NOT written here — Terraform
# doesn't know about the on-host Postgres (it lives at 127.0.0.1 inside the
# instance), so the loader composes it from `DATABASE_PASSWORD` at boot.
#
# `ENV` is intentionally NOT written here either — it is environment-defining,
# so it lives in the systemd unit (`Environment=ENV=production`) where it can't
# be misconfigured by an SSM rotation.

# --- Plain-string config -----------------------------------------------------

resource "aws_ssm_parameter" "cors_origins" {
  name        = "${local.prefix}/CORS_ORIGINS"
  description = "JSON list of allowed CORS origins."
  type        = "String"
  value       = var.cors_origins
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "access_token_expire_hours" {
  name        = "${local.prefix}/ACCESS_TOKEN_EXPIRE_HOURS"
  description = "JWT lifetime in hours."
  type        = "String"
  value       = tostring(var.access_token_expire_hours)
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "llm_provider" {
  name        = "${local.prefix}/llm/provider"
  description = "LLM provider toggle (bedrock|anthropic). Loader maps to LLM_PROVIDER."
  type        = "String"
  value       = var.llm_provider
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "llm_region" {
  name        = "${local.prefix}/llm/region"
  description = "Region in which Bedrock is invoked. Loader maps to AWS_REGION."
  type        = "String"
  value       = var.region
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "llm_model_id" {
  name        = "${local.prefix}/llm/model_id"
  description = "Bedrock model ID or cross-region inference profile ID the app invokes. Loader maps to BEDROCK_MODEL_ID."
  type        = "String"
  value       = var.bedrock_model_id
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

# --- SecureStrings ----------------------------------------------------------

resource "aws_ssm_parameter" "app_secret_key" {
  name        = "${local.prefix}/SECRET_KEY"
  description = "JWT signing key. Rotate yearly; rotation logs all users out."
  type        = "SecureString"
  key_id      = var.kms_key_id
  value       = var.app_secret_key
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      # Operators may rotate this out-of-band; don't fight them.
      value,
    ]
  }
}

resource "aws_ssm_parameter" "db_password" {
  name        = "${local.prefix}/DATABASE_PASSWORD"
  description = "Application Postgres user password. Loader composes DATABASE_URL from this value (postgresql://flowin:$${pw}@127.0.0.1:5432/flowin)."
  type        = "SecureString"
  key_id      = var.kms_key_id
  value       = var.db_password
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      value,
    ]
  }
}

resource "aws_ssm_parameter" "anthropic_api_key" {
  count = length(var.anthropic_api_key) > 0 ? 1 : 0

  name        = "${local.prefix}/anthropic/api_key"
  description = "Optional Anthropic API key (fallback for Bedrock outages). Loader maps to ANTHROPIC_API_KEY."
  type        = "SecureString"
  key_id      = var.kms_key_id
  value       = var.anthropic_api_key
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      value,
    ]
  }
}

# --- LangSmith (LangChain tracing) — optional ------------------------------
#
# Three count-guarded parameters; absent unless the operator opts in by
# supplying non-empty values in tfvars. The on-host loader already supports
# the canonical env-var names (LANGSMITH_TRACING / LANGSMITH_API_KEY /
# LANGSMITH_PROJECT) — see docs/SIMPLE_AWS_DEPLOYMENT.md §9.3 / Appendix D.
# When all three are absent, the LangSmith client treats the env as
# "tracing disabled" and is a no-op on every call.
#
# `lifecycle.ignore_changes = [value]` mirrors the other rotatable secrets:
# operators may rotate the API key out-of-band without Terraform reverting.

resource "aws_ssm_parameter" "langsmith_tracing" {
  count = length(var.langsmith_tracing) > 0 ? 1 : 0

  name        = "${local.prefix}/LANGSMITH_TRACING"
  description = "Toggle for LangSmith tracing (true|false). Empty default — created only when set in tfvars."
  type        = "String"
  value       = var.langsmith_tracing
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      value,
    ]
  }
}

resource "aws_ssm_parameter" "langsmith_api_key" {
  count = length(var.langsmith_api_key) > 0 ? 1 : 0

  name        = "${local.prefix}/LANGSMITH_API_KEY"
  description = "LangSmith API key. Stored as SecureString; rotated out-of-band by the operator."
  type        = "SecureString"
  key_id      = var.kms_key_id
  value       = var.langsmith_api_key
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      value,
    ]
  }
}

resource "aws_ssm_parameter" "langsmith_project" {
  count = length(var.langsmith_project) > 0 ? 1 : 0

  name        = "${local.prefix}/LANGSMITH_PROJECT"
  description = "LangSmith project name (e.g. flowin-prod)."
  type        = "String"
  value       = var.langsmith_project
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      value,
    ]
  }
}
