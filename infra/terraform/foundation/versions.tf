terraform {
  # 1.9+ for cross-variable validation (e.g. availability_zone must live in
  # aws_region). The CI pipeline pins an exact Terraform version in
  # infra/buildspec.yml; this floor keeps local `validate` honest.
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}
