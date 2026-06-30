# Example: account_guard — abort on wrong account/region.
#
# Illustrative only. Replace the placeholder account ID with your own.
#   terraform init && terraform plan

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

module "account_guard" {
  source = "../../"

  expected_account_id = "123456789012" # <- your 12-digit account id
  expected_region     = "eu-central-1"
}

output "verified_account_id" {
  value = module.account_guard.account_id
}
