# Example: network — single-AZ VPC with locked-down SGs + VPC endpoints.
#
# Illustrative only. kms_key_arn / backup_bucket_arn come from the kms and
# backups modules in the real suite.

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

module "network" {
  source = "../../"

  name_prefix       = "velocityai-dev"
  environment       = "dev"
  region            = "eu-central-1"
  account_id        = "123456789012"
  availability_zone = "eu-central-1a"

  vpc_cidr           = "10.40.0.0/16"
  public_subnet_cidr = "10.40.1.0/24"
  kms_key_arn        = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000000"

  ssh_allowed_cidrs = [] # SSM Session Manager only
}

output "app_security_group_id" {
  value = module.network.app_security_group_id
}
