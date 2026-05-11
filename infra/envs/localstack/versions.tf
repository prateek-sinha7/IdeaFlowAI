terraform {
  # Matches envs/prod/versions.tf — see the comment there for the rationale
  # (cross-variable validation in 1.9+).
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}
