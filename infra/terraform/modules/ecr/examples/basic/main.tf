# Example: ecr — shared backend + frontend repositories.
#
# Illustrative only. In the real suite this is instantiated once in the
# shared layer (velocityai/shared.tfstate).

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

module "ecr" {
  source = "../../"

  repository_names = ["velocityai/backend", "velocityai/frontend"]
  keep_last_images = 10
  scan_on_push     = true
}

output "repository_urls" {
  value = module.ecr.repository_urls
}
