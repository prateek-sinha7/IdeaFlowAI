# LocalStack fixture values — hermetic, NO secrets (account 000000000000,
# stub AMI, dummy placeholders). Committed on purpose (see infra/.gitignore).
# Apply with:  terraform apply -var-file=localstack.tfvars

expected_account_id = "000000000000"
aws_region          = "eu-central-1"
availability_zone   = "eu-central-1a"
environment         = "ls"

owner       = "velocityai-platform-team@example.test"
cost_center = "UKI-VELOCITYAI-LOCALSTACK"

vpc_cidr           = "10.20.0.0/16"
public_subnet_cidr = "10.20.1.0/24"
ssh_allowed_cidrs  = []

instance_type       = "m6i.2xlarge"
root_volume_size_gb = 100
data_volume_size_gb = 50
ssh_key_name        = ""
# LocalStack ships stub AMIs; the Canonical filter resolves to nothing.
ami_id = "ami-03cf127a"

# Pre-create the zone:
#   awslocal route53 create-hosted-zone --name velocityai.test --caller-reference ls-$(date +%s)
route53_zone_name = "velocityai.test"
app_subdomain     = "app"
dns_ttl_seconds   = 60

bedrock_model_id              = "anthropic.claude-haiku-4-5-20251001-v1:0"
bedrock_inference_profile_id  = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
use_inference_profile_for_app = true

# Validated lengths; real values are irrelevant under LocalStack.
app_secret_key = "localstack-placeholder-secret-key-32chars-minimum-padding"
db_password    = "localstack-placeholder-pw-16chars"

cors_origins              = "[\"https://app.velocityai.test\"]"
access_token_expire_hours = 12

daily_backup_retention_days = 365

alert_email                 = "velocityai-oncall@example.test"
log_retention_days          = 30
billing_alarm_threshold_usd = 500

audit_trail_bucket_force_destroy = true
