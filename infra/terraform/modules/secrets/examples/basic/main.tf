# Example: secrets — SSM parameter tree with auto-generated SecureStrings.
#
# Illustrative only. app_secret_key / db_password are omitted so the module
# generates them; never commit real secret values to a tfvars file.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = "eu-central-1"
}

module "secrets" {
  source = "../../"

  name_prefix = "velocityai-dev"
  environment = "dev"
  region      = "eu-central-1"
  kms_key_id  = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"

  bedrock_model_id             = "anthropic.claude-haiku-4-5-20251001-v1:0"
  bedrock_inference_profile_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

output "parameter_path_prefix" {
  value = module.secrets.parameter_path_prefix
}
