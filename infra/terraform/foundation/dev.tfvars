# VelocityAI foundation — dev environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/foundation apply \
#   -var-file=dev.tfvars -var="expected_account_id=$ACCOUNT_ID" -var="aws_region=$AWS_REGION"
#
# Secrets (app_secret_key, db_password, langsmith_api_key) and per-env values
# (cors_origins, alert email, bedrock model) are injected via TF_VAR_* from the
# CI runner / SSM — never committed here. Resource names derive from
# environment: dev -> velocityai-dev.

environment = "dev"

# Network — non-overlapping CIDR per environment (dev 10.40 / stage 10.30 / prod 10.20).
availability_zone  = "eu-central-1a"
vpc_cidr           = "10.40.0.0/16"
public_subnet_cidr = "10.40.1.0/24"

# Cheaper retention for a throwaway environment (module floor: retention -
# cold_storage >= 90).
log_retention_days          = 14
daily_backup_retention_days = 120
cold_storage_after_days     = 30
pg_dump_expiry_days         = 120

# --- Cognito (COGNITO-MIGRATION-PLAN, Phase 1 + Phase 5) --------------------
# dev is the first environment cut over (dev -> stage -> prod). Creating the
# pool is safe and effectively free (MAU pricing, empty pool), and is a
# prerequisite for anything in Phase 5.
cognito_enabled = true

# Shorter refresh-token life in dev than prod (assumption A-4) — a leaked dev
# refresh token should die sooner, and dev sessions are disposable.
cognito_refresh_token_validity_days = 7

# CUTOVER SWITCHES — read these together:
#
#   auth_provider = "local"       -> Cognito EXISTS but is not yet the
#                                    credential authority. Login still uses the
#                                    local bcrypt path. This is Phase 5 step 1
#                                    ("deploy with dual-accept"), and it is the
#                                    correct value until the admin has been
#                                    bootstrapped INTO the pool and verified.
#   auth_provider = "cognito"     -> flip AFTER running
#                                    scripts/bootstrap_admin.py against the
#                                    pool and confirming a successful Cognito
#                                    login (Phase 5 steps 2-6).
#
#   auth_allow_legacy_jwt = true  -> dual-accept; zero forced logouts. Flip to
#                                    false only at step 7, after legacy tokens
#                                    have aged out (<= ACCESS_TOKEN_EXPIRE_HOURS).
auth_provider         = "local"
auth_allow_legacy_jwt = true
break_glass_enabled   = true
