# Example: cognito — User Pool + backend app client + tier/role groups.
#
# Illustrative only.

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

module "cognito" {
  source = "../../"

  name_prefix = "velocityai-dev"
  environment = "dev"

  deletion_protection = "INACTIVE" # ACTIVE in prod
  mfa_configuration   = "OPTIONAL"
}

output "user_pool_id" {
  value = module.cognito.user_pool_id
}

output "client_id" {
  value = module.cognito.client_id
}
