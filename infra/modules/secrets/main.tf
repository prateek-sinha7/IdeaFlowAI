locals {
  prefix = "/flowin/${var.environment}"
}

# --- Plain-string config -----------------------------------------------------

resource "aws_ssm_parameter" "llm_provider" {
  name        = "${local.prefix}/llm/provider"
  description = "LLM provider toggle (bedrock|anthropic)."
  type        = "String"
  value       = var.llm_provider
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "llm_region" {
  name        = "${local.prefix}/llm/region"
  description = "Region in which Bedrock is invoked."
  type        = "String"
  value       = var.region
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "llm_model_id" {
  name        = "${local.prefix}/llm/model_id"
  description = "Bedrock model ID or cross-region inference profile ID the app invokes."
  type        = "String"
  value       = var.bedrock_model_id
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "cors_origins" {
  name        = "${local.prefix}/app/cors_origins"
  description = "JSON list of allowed CORS origins."
  type        = "String"
  value       = var.cors_origins
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "access_token_expire_hours" {
  name        = "${local.prefix}/app/access_token_expire_hours"
  description = "JWT lifetime in hours."
  type        = "String"
  value       = tostring(var.access_token_expire_hours)
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

# --- SecureStrings ----------------------------------------------------------

resource "aws_ssm_parameter" "app_secret_key" {
  name        = "${local.prefix}/app/secret_key"
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
  name        = "${local.prefix}/app/db_password"
  description = "Application Postgres user password."
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
  description = "Optional Anthropic API key (fallback for Bedrock outages)."
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
