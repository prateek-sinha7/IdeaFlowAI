# VelocityAI app — stage environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/app apply \
#   -var-file=stage.tfvars -var="expected_account_id=$ACCOUNT_ID" \
#   -var="aws_region=$AWS_REGION" -var="state_bucket=$TF_STATE_BUCKET" \
#   -var="image_tag=$IMAGE_TAG"
#
# alert_email, cors_origins, and the Bedrock model are injected via TF_VAR_*
# from the CI runner. Resource names derive from environment: stage ->
# velocityai-stage.

environment = "stage"

# Compute.
instance_type       = "m6i.xlarge"
root_volume_size_gb = 80
data_volume_size_gb = 40

# DNS — nip.io (set use_nip_io = false + route53_zone_name for a real domain).
use_nip_io = true

# Monitoring.
log_retention_days          = 30
billing_alarm_threshold_usd = 250
