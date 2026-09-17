# VelocityAI foundation — stage environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/foundation apply \
#   -var-file=stage.tfvars -var="expected_account_id=$ACCOUNT_ID" -var="aws_region=$AWS_REGION"
#
# Secrets and per-env values are injected via TF_VAR_* from the CI runner / SSM
# — never committed here. Resource names derive from environment: stage ->
# velocityai-stage.

environment = "stage"

# Network — non-overlapping CIDR per environment (dev 10.40 / stage 10.30 / prod 10.20).
availability_zone  = "eu-central-1a"
vpc_cidr           = "10.30.0.0/16"
public_subnet_cidr = "10.30.1.0/24"

log_retention_days          = 30
daily_backup_retention_days = 180
cold_storage_after_days     = 30
pg_dump_expiry_days         = 180

# --- Cognito (COGNITO-MIGRATION-PLAN, Phase 1 + Phase 5) --------------------
# Pool + backend app client + tier/role groups exist in stage. Creating the
# pool is cheap (MAU pricing, empty pool) and is the prerequisite for anything
# in Phase 5. Password policy comes from the module defaults (12 chars, mixed
# case + digits + symbols).
cognito_enabled = true

# Between dev (7) and prod (30): stage sessions are longer-lived than a
# throwaway dev box but a leaked stage refresh token should still die early.
cognito_refresh_token_validity_days = 14

# auth_provider, auth_allow_legacy_jwt, and break_glass_enabled were REMOVED
# in Phase 4 of the Cognito-only auth migration — see foundation/dev.tfvars.
