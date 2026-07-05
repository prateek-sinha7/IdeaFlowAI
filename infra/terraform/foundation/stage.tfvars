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
