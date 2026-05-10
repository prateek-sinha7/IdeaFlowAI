terraform {
  # Audit B P2-9: bumped from 1.7.0 to 1.9.0 to enable cross-variable
  # validation (var.X reading var.Y inside a `validation { condition = ... }`
  # block). Used here for the availability_zone-must-live-in-aws_region
  # check; without 1.9+ that check would have to live as a precondition on
  # a terraform_data block in main.tf, which is uglier and slower to fail.
  # CI runs Terraform 1.15+; local dev should `tfenv install 1.9.0` (or
  # newer). 1.9 is back-compatible with all existing 1.7 syntax.
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3"
    }
  }
}
