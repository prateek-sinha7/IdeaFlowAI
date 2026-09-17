locals {
  prefix = "/velocityai/${var.environment}"
}

# --- Auto-generated secrets ------------------------------------------------
#
# When the operator does NOT pass var.app_secret_key / var.db_password, these
# random_password resources fill in a strong default. They're generated ONCE
# (no `keepers`) and persisted in state; subsequent plans reuse the same
# value. Manual rotation works out-of-band because the matching SSM parameter
# resources below set `lifecycle.ignore_changes = [value]`.
#
# `special = false` keeps the result to [a-zA-Z0-9] so the EnvironmentFile
# format used by systemd / docker-compose doesn't have to grapple with
# embedded quotes, backslashes, or `$` expansion. 64-char alphanumeric is
# ~380 bits of entropy — well past the >= 32-char policy in the prod env
# variable validations.
resource "random_password" "app_secret_key" {
  length  = 64
  special = false
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# Notes on the schema
# -------------------
# Terraform writes the canonical UPPERCASE top-level keys that the application's
# Settings (backend/app/core/config.py) reads directly, plus the nested
# `llm/*` namespace for Bedrock region/model id. The on-host loader translates
# the nested paths to env-var names per the rule documented in
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
  # SSM PutParameter requires value length >= 1. The host-side
  # velocityai-load-secrets (infra/scripts/bootstrap-ec2.sh ~line 389) handles
  # the missing-parameter case: when get-parameters-by-path doesn't return
  # CORS_ORIGINS, it falls back to ["https://$VELOCITYAI_FQDN"]. So when the
  # operator hasn't set var.cors_origins we skip creating the parameter
  # entirely rather than fail apply with an invalid empty string.
  count = length(var.cors_origins) > 0 ? 1 : 0

  name        = "${local.prefix}/CORS_ORIGINS"
  description = "JSON list of allowed CORS origins."
  type        = "String"
  value       = var.cors_origins
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

resource "aws_ssm_parameter" "llm_inference_profile_id" {
  # Created only when an inference profile ID is supplied. The on-host loader
  # (infra/scripts/bootstrap-ec2.sh) has always known how to translate the
  # nested key `llm/inference_profile_id` into `BEDROCK_INFERENCE_PROFILE_ID`,
  # but until this resource existed the parameter was never written and the
  # backend silently fell back to its hardcoded default in
  # ``backend/app/core/config.py``. Adding the resource closes that contract.
  count = length(var.bedrock_inference_profile_id) > 0 ? 1 : 0

  name        = "${local.prefix}/llm/inference_profile_id"
  description = "Cross-region inference profile ID. Loader maps to BEDROCK_INFERENCE_PROFILE_ID; preferred over llm/model_id in backend/app/agents/base.py."
  type        = "String"
  value       = var.bedrock_inference_profile_id
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
  value       = var.app_secret_key != "" ? var.app_secret_key : random_password.app_secret_key.result
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
  description = "Application Postgres user password. Loader composes DATABASE_URL from this value (postgresql://velocityai:$${pw}@127.0.0.1:5432/velocityai)."
  type        = "SecureString"
  key_id      = var.kms_key_id
  value       = var.db_password != "" ? var.db_password : random_password.db_password.result
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
  description = "LangSmith project name (e.g. velocityai-prod)."
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

# --- Cognito (COGNITO-MIGRATION-PLAN §6.3 / §11) ----------------------------
#
# All four are count-guarded on `cognito_user_pool_id` being non-empty, so an
# environment that hasn't run the cognito module yet gets none of these
# parameters — same "empty means opt-out" pattern as the LangSmith block
# above. The canonical loader allowlist lives in
# infra/scripts/velocityai-load-secrets.sh. It is delivered on every normal
# deploy and during first boot, so a change reaches existing hosts without a
# provisioning run; names outside it are intentionally excluded from app.env.

resource "aws_ssm_parameter" "cognito_user_pool_id" {
  count = var.cognito_enabled ? 1 : 0

  name        = "${local.prefix}/COGNITO_USER_POOL_ID"
  description = "Cognito User Pool ID."
  type        = "String"
  value       = var.cognito_user_pool_id
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "cognito_client_id" {
  count = var.cognito_enabled ? 1 : 0

  name        = "${local.prefix}/COGNITO_CLIENT_ID"
  description = "Cognito app client ID."
  type        = "String"
  value       = var.cognito_client_id
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "cognito_client_secret" {
  count = var.cognito_enabled ? 1 : 0

  name        = "${local.prefix}/COGNITO_CLIENT_SECRET"
  description = "Cognito app client secret. Used to compute SECRET_HASH on AdminInitiateAuth."
  type        = "SecureString"
  key_id      = var.kms_key_id
  value       = var.cognito_client_secret
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }

  lifecycle {
    ignore_changes = [
      # The app client secret is only regenerated by recreating the client;
      # this guard mirrors the other rotatable secrets so an out-of-band
      # rotation isn't fought by the next apply.
      value,
    ]
  }
}

resource "aws_ssm_parameter" "cognito_region" {
  count = var.cognito_enabled ? 1 : 0

  name        = "${local.prefix}/COGNITO_REGION"
  description = "AWS region of the Cognito user pool. Falls back to AWS_REGION when absent."
  type        = "String"
  value       = var.cognito_region
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

# --- Auth flags -------------------------------------------------------------
# SSM-managed so a flag flip is an operational change + restart, not a
# redeploy. auth_provider, auth_allow_legacy_jwt, and break_glass_enabled were
# REMOVED in Phase 4 of the Cognito-only auth migration
# (.kiro/specs/login/prompt.md) -- the backend's Settings class no longer
# declares any of the three (core/config.py), so these parameters would be
# dead configuration. See MERGE_NOTES.md §18.

resource "aws_ssm_parameter" "auth_email_mfa_enabled" {
  count = length(var.auth_email_mfa_enabled) > 0 ? 1 : 0

  name        = "${local.prefix}/AUTH_EMAIL_MFA_ENABLED"
  description = "Pool has email OTP as a second factor, so email is disqualified for account recovery and self-service password reset is unavailable."
  type        = "String"
  value       = var.auth_email_mfa_enabled
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}

resource "aws_ssm_parameter" "admin_mfa_required" {
  count = length(var.admin_mfa_required) > 0 ? 1 : 0

  name        = "${local.prefix}/ADMIN_MFA_REQUIRED"
  description = "Require a confirmed second factor for admin operations (P0 fix). The canonical loader allowlist is infra/scripts/velocityai-load-secrets.sh and is refreshed by every normal deploy."
  type        = "String"
  value       = var.admin_mfa_required
  tier        = "Standard"

  tags = {
    Component = "secrets"
  }
}
