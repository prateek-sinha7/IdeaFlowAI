# Example: kms — project CMK + alias.
#
# Illustrative only. Replace the placeholder account ID with your own.

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

module "kms" {
  source = "../../"

  name_prefix = "velocityai-dev"
  account_id  = "123456789012"
  region      = "eu-central-1"

  # Toggle off any service grant you don't need in this environment.
  allow_cloudtrail_service = false
}

output "key_arn" {
  value = module.kms.key_arn
}
