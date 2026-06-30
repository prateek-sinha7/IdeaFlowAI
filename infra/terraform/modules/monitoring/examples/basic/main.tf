# Example: monitoring — log groups, alarms, SNS, CloudTrail audit trail.
#
# Illustrative only. instance_id / kms / iam ARNs come from sibling modules in
# the real suite. Note the required aws.useast1 provider alias (billing alarms
# must live in us-east-1).

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = "eu-central-1"
}

provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
}

module "monitoring" {
  source = "../../"

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
  }

  name_prefix = "velocityai-dev"
  environment = "dev"
  instance_id = "i-0123456789abcdef0"
  kms_key_arn = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"
  alert_email = "ops@example.com"

  bedrock_model_id        = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
  instance_role_arn       = "arn:aws:iam::123456789012:role/velocityai-dev-instance"
  project_cmk_arn         = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"
  secrets_path_prefix_arn = "arn:aws:ssm:eu-central-1:123456789012:parameter/velocityai/dev"
}

output "alerts_topic_arn" {
  value = module.monitoring.alerts_topic_arn
}
