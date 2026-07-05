# Example: resourcegroups — all-resources group + per-component groups.
#
# Illustrative only. The Resource Groups created here only populate once
# resources carrying matching Project/Environment/Component tags exist.

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

  default_tags {
    tags = {
      Project     = "velocityai"
      Environment = "dev"
    }
  }
}

module "resourcegroups" {
  source = "../../"

  name_prefix = "velocityai-dev"
  environment = "dev"
}

output "all_group_name" {
  value = module.resourcegroups.all_group_name
}
