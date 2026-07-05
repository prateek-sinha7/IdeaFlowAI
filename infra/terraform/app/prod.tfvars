# VelocityAI app — prod environment (NON-SECRET config only).
#
# Consumed by CI as: terraform -chdir=infra/terraform/app apply \
#   -var-file=prod.tfvars -var="expected_account_id=$ACCOUNT_ID" \
#   -var="aws_region=$AWS_REGION" -var="state_bucket=$TF_STATE_BUCKET" \
#   -var="image_tag=$IMAGE_TAG"
#
# alert_email, cors_origins, and the Bedrock model are injected via TF_VAR_*
# from the CI runner. Resource names derive from environment: prod ->
# velocityai (bare, no suffix).

environment = "prod"

# Compute.
instance_type       = "m6i.2xlarge"
root_volume_size_gb = 100
data_volume_size_gb = 50

# DNS — defaults to nip.io. For a real domain, set:
#   use_nip_io        = false
#   route53_zone_name = "example.com"   # an EXISTING Route 53 zone you own
#   app_subdomain     = "velocityai"
use_nip_io = true

# Monitoring.
log_retention_days          = 30
billing_alarm_threshold_usd = 500
