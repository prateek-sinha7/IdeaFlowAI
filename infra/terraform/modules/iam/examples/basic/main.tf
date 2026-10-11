# Example: iam — EC2 instance role + instance profile.
#
# Illustrative only. In the real suite kms_key_arn / backup_bucket_arn come
# from the kms and backups modules.

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

module "iam" {
  source = "../../"

  name_prefix = "velocityai-dev"
  environment = "dev"
  account_id  = "123456789012"
  region      = "eu-central-1"

  kms_key_arn       = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"
  backup_bucket_arn = "arn:aws:s3:::velocityai-dev-pg-dumps-123456789012"

  bedrock_model_id             = "anthropic.claude-haiku-4-5-20251001-v1:0"
  bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

  # Every profile the app may select. Foundation-model ARNs are derived from
  # these (geography prefix stripped), so no second list is needed. The
  # `global.openai.*` entries also pull in the `project/default` grant the
  # bedrock-runtime OpenAI path requires.
  bedrock_allowed_inference_profile_ids = [
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu.anthropic.claude-opus-4-5-20251101-v1:0",
    "global.openai.gpt-6-sol",
    "global.openai.gpt-6-luna",
    "global.openai.gpt-5.6-terra",
  ]

  # policies_dir defaults to "../../policies" relative to the module dir
  # (-> infra/terraform/policies), which is correct from any caller.
}

output "instance_profile_name" {
  value = module.iam.instance_profile_name
}
