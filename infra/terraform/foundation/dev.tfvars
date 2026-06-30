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
