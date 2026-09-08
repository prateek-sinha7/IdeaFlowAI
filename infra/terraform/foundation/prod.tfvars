# VelocityAI foundation — prod environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/foundation apply \
#   -var-file=prod.tfvars -var="expected_account_id=$ACCOUNT_ID" -var="aws_region=$AWS_REGION"
#
# Secrets and per-env values are injected via TF_VAR_* from the CI runner / SSM
# — never committed here. Resource names derive from environment: prod ->
# velocityai (bare, no suffix).

environment = "prod"

# Production identity and authentication — Cognito enabled with strong security posture.
# Password policy: 12+ chars with mixed case, numbers, and symbols.
# MFA: optional for now (can be set to REQUIRED for full enforcement).
# Account recovery: email + phone.
# Threat protection: enabled for account takeover detection and response.
cognito_enabled = true
cognito_user_pool_config = {
  policies = {
    password_policy = {
      minimum_length                   = 12
      require_lowercase                = true
      require_numbers                  = true
      require_symbols                  = true
      require_uppercase                = true
      temporary_password_validity_days = 7
    }
  }
  account_recovery_setting = {
    recovery_mechanisms = [
      { priority = 1, name = "verified_email" },
      { priority = 2, name = "verified_phone_number" }
    ]
  }
  mfa_configuration = "OPTIONAL"
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]
  prevent_user_existence_errors = "ENABLED"
  account_takeover_risk_configuration = {
    compromised_credentials = { event_action = "BLOCK", high_action = "BLOCK", medium_action = "BLOCK" }
    account_takeover_action  = { high_action = "BLOCK", medium_action = "MFA_IF_CONFIGURED" }
  }
  # Legacy auth disabled; enforce token-based auth
  enable_token_revocation = true
  enable_propagate_additional_user_context_data = true
}

# Network — non-overlapping CIDR per environment (dev 10.40 / stage 10.30 / prod 10.20).
availability_zone  = "eu-central-1a"
vpc_cidr           = "10.20.0.0/16"
public_subnet_cidr = "10.20.1.0/24"

log_retention_days          = 30
daily_backup_retention_days = 365
cold_storage_after_days     = 30
pg_dump_expiry_days         = 365
