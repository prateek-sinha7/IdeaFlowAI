# LocalStack-targeted variable values.
#
# This env runs against the local LocalStack Pro container on port 4666; values
# don't need to be production-grade. The AWS account ID is LocalStack's default
# (000000000000) and the account guard validates against it.

# ---- Identity guard --------------------------------------------------------

expected_account_id = "000000000000"
aws_region          = "eu-west-2"
availability_zone   = "eu-west-2a"
environment         = "ls"

# ---- Tagging ---------------------------------------------------------------

owner       = "flowin-platform-team@example.test"
cost_center = "UKI-FLOWIN-LOCALSTACK"

# ---- Network ---------------------------------------------------------------

vpc_cidr           = "10.20.0.0/16"
public_subnet_cidr = "10.20.1.0/24"
ssh_allowed_cidrs  = []

# ---- Compute ---------------------------------------------------------------

instance_type       = "m6i.xlarge"
root_volume_size_gb = 100
data_volume_size_gb = 50
ssh_key_name        = ""

# LocalStack ships a small set of stub AMIs; the real Canonical filter resolves
# to nothing. We pin one of LocalStack's defaults so the EC2 launch succeeds.
ami_id = "ami-03cf127a"

# ---- DNS -------------------------------------------------------------------

# Pre-created via:
#   aws route53 create-hosted-zone --name flowin.test --caller-reference flowin-localstack-<ts>
route53_zone_name = "flowin.test"
app_subdomain     = "app"
dns_ttl_seconds   = 60

# ---- Bedrock / LLM ---------------------------------------------------------

bedrock_model_id              = "anthropic.claude-haiku-4-5-20251001-v1:0"
bedrock_inference_profile_id  = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
use_inference_profile_for_app = true

# ---- Secrets — placeholders; supply via TF_VAR_app_secret_key etc. ---------

# Validated >= 32 chars but the real value comes from env vars at apply time.
app_secret_key = "localstack-placeholder-secret-key-32chars-minimum-padding"
db_password    = "localstack-placeholder-pw-16chars"

anthropic_api_key         = ""
cors_origins              = "[\"https://app.flowin.test\"]"
access_token_expire_hours = 12

# ---- Backups ---------------------------------------------------------------

backup_bucket_name          = "flowin-ls-pg-dumps-000000000000"
daily_backup_retention_days = 35

# ---- Monitoring ------------------------------------------------------------

alert_email                 = "flowin-oncall@example.test"
log_retention_days          = 30
billing_alarm_threshold_usd = 500
