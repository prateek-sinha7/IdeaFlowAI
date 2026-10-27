# VelocityAI foundation — prod environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/foundation apply \
#   -var-file=prod.tfvars -var="expected_account_id=$ACCOUNT_ID" -var="aws_region=$AWS_REGION"
#
# Secrets and per-env values are injected via TF_VAR_* from the CI runner / SSM
# — never committed here. Resource names derive from environment: prod ->
# velocityai (bare, no suffix).

environment = "prod"

# --- Cognito (COGNITO-MIGRATION-PLAN, Phase 1 + Phase 5) --------------------
# Pool + backend app client + tier/role groups exist in prod.
#
# This block previously assigned a single `cognito_user_pool_config` object.
# That variable is NOT declared in foundation/variables.tf, so Terraform
# emitted "Value for undeclared variable" and DISCARDED all of it — none of
# the posture it described was ever applied. It also contradicted the module
# in three places: `ALLOW_USER_PASSWORD_AUTH` (the app client deliberately
# uses ALLOW_ADMIN_USER_PASSWORD_AUTH only — Decision 1, backend-mediated
# auth, no browser redirect), `verified_phone_number` recovery (the pool
# collects no phone numbers, so that mechanism is unavailable), and a second
# recovery mechanism at all (the module sets exactly one). It is replaced
# below with the variables that actually exist.
cognito_enabled = true

# Password policy (12 chars, lower + upper + digits + symbols, 7-day temporary
# password) is the modules/cognito default and needs no override here; the
# foundation layer intentionally does not expose it per-environment.
#
# Token revocation and prevent_user_existence_errors are hardcoded ON in the
# module's app client — not tunable, and not something prod wants to tune.

# MFA: TOTP available to every user, not forced pool-wide. Admin operations are
# gated separately by admin_mfa_required below, which is the app-layer
# "required for admins" control (Cognito has no per-group MFA requirement).
cognito_mfa_configuration = "OPTIONAL"

# Longest refresh-token life of the three environments (dev 7 / stage 14).
cognito_refresh_token_validity_days = 30

# THREAT PROTECTION — deliberately left off, not forgotten. Turning it on is
# two lines, but it requires the PLUS feature plan, which raises the per-MAU
# price for the whole pool, so it is an explicit budget decision rather than a
# default. Start at AUDIT (logs risk assessments without blocking) and review
# the signal before moving to ENFORCED, which maps to event_action = "BLOCK"
# on compromised credentials at sign-in and can lock real users out:
#
#   cognito_feature_plan           = "PLUS"
#   cognito_threat_protection_mode = "AUDIT"

# auth_provider, auth_allow_legacy_jwt, and break_glass_enabled were REMOVED
# in Phase 4 of the Cognito-only auth migration — see foundation/dev.tfvars.
# prod finished cutover (dev -> stage -> prod) by the time Phase 4 landed.

# Network — non-overlapping CIDR per environment (dev 10.40 / stage 10.30 / prod 10.20).
availability_zone  = "eu-central-1a"
vpc_cidr           = "10.20.0.0/16"
public_subnet_cidr = "10.20.1.0/24"

log_retention_days          = 30
daily_backup_retention_days = 365
cold_storage_after_days     = 30
pg_dump_expiry_days         = 365
runs_backup_expiry_days     = 365
