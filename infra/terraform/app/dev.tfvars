# VelocityAI app — dev environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/app apply \
#   -var-file=dev.tfvars -var="expected_account_id=$ACCOUNT_ID" \
#   -var="aws_region=$AWS_REGION" -var="state_bucket=$TF_STATE_BUCKET" \
#   -var="image_tag=$IMAGE_TAG"
#
# alert_email, cors_origins, and the Bedrock model are injected via TF_VAR_*
# from the CI runner (bootstrap/cicd.tf). image_tag/state_bucket/account come
# from the pipeline. Resource names derive from environment: dev -> velocityai-dev.

environment = "dev"

# Compute — smaller box for a throwaway environment.
instance_type       = "m6i.xlarge"
root_volume_size_gb = 60
data_volume_size_gb = 30

# DNS — nip.io (no domain needed for dev).
use_nip_io = true

# Monitoring.
log_retention_days          = 14
billing_alarm_threshold_usd = 100
